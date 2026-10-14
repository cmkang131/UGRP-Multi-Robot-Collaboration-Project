"""Information/safety invariants for the offline release NBV planner."""
import copy
import math
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_pair_highpose_contract as contract
from sim.active_lookaround import OwnPose
from sim.grasp_act_release_teacher import ReleaseTeacher
from sim.lookaround_localization import LookaroundLocalizer
from sim.release_global_observation import recovery_round
from sim import release_nbv_observation as nbv


@pytest.fixture
def localizer():
    loc = LookaroundLocalizer(contract.resolve('zone_wide_two_doors_final_v3')[0], [0., 0., 0.],
                             mode='setdown_global_v1', map_pose_known=False)
    loc.decision = dict(accepted=False, reason='ambiguous_global_landmarks',
                       alternatives=[dict(pose=[4.6, .4, math.pi/2])])
    return loc


def teacher():
    t = ReleaseTeacher('r1', 'teal', {1:2000,3:820,4:2320,5:1320,6:1500},
                       handoff_pose_estimate=None, zone_rect=(4.6,.4,.3,.7))
    t.holding = False
    return t


def test_entropy_gain_matches_closed_form_and_requires_new_observation(localizer, monkeypatch):
    # Rank two geometry is more informative than many repeats of one normal.
    points = [dict(type='wall',group='x',id='xa',xy=(1.,0.),normal=(1.,0.),model='line_point',sigma=.05),
              dict(type='wall',group='x',id='xb',xy=(1.,.4),normal=(1.,0.),model='line_point',sigma=.05),
              dict(type='wall',group='y',id='ya',xy=(0.,1.),normal=(0.,1.),model='line_point',sigma=.05),
              dict(type='wall',group='y',id='yb',xy=(.4,1.),normal=(0.,1.),model='line_point',sigma=.05)]
    localizer.landmarks = points
    localizer.decision['alternatives'] = [dict(pose=[0.,0.,0.])]
    monkeypatch.setattr(localizer.global_matcher, 'free', lambda poses, **kw: np.zeros(len(poses),bool))
    monkeypatch.setattr(nbv, 'visible_fn_for', lambda *a, **kw:
                        lambda pose, yaw, pan, lm: pan==90. or (pan==0. and lm['group']=='x'))
    monkeypatch.setattr(nbv, 'VIEW_BUDGET', 1)
    before = copy.deepcopy(localizer.decision)
    planned = nbv.plan(localizer)
    assert planned['body_yaw_deg']==0 and planned['backstep_m']==0
    assert planned['views'][0]['pan_deg']==90.
    P = np.diag([.05**2,.05**2,math.radians(3)**2])
    J = nbv.information([0.,0.,0.], points)
    expected = .5*np.linalg.slogdet(np.eye(3)+P@J)[1]
    assert planned['expected_gain_nats']==pytest.approx(expected)
    assert localizer.decision==before and not localizer.map_pose_known
    # A recorded command-frame view cannot be selected again.
    used=[planned['views'][0]['key']]
    again=nbv.plan(localizer, used=used)
    assert again['views'][0]['key']!=used[0]


def test_every_alternative_blocks_unsafe_motion_but_camera_remains_available(localizer, monkeypatch):
    localizer.decision['alternatives'].append(dict(pose=[5.19,.4,0.]))
    original=localizer.global_matcher.free
    def check(poses, **kw):
        assert len(poses)==2 and kw['extra_clearance']==.15
        return original(poses, **kw)
    monkeypatch.setattr(localizer.global_matcher, 'free', check)
    steps, entry=nbv.script(localizer,teacher(),0.)
    assert entry['action']=='map_nbv' and entry['hypothesis_count']==2
    assert entry['body_yaw_deg']==entry['backstep_m']==0
    assert not entry['all_retained_hypotheses_clear']
    assert steps and not any('wheels' in s for s in steps)


def test_no_hypothesis_or_held_cargo_never_creates_motion(localizer):
    localizer.decision={}
    steps, entry=nbv.script(localizer,teacher(),0.)
    assert not steps and entry['reason']=='no_new_informative_safe_view'
    t=teacher();t.holding=True
    steps, entry=nbv.script(localizer,t,0.)
    assert not steps and entry['reason']=='cargo_not_set_down'


def test_extra_round_budget_waits_for_accepted_robot_and_is_atomic(localizer):
    locs={'r1':localizer,'r2':localizer};teachers={r:teacher() for r in locs}
    reports={'r1':dict(kind='localized_margin'),'r2':dict(kind='none')}
    stages={'r1':1,'r2':3};history={'r1':[],'r2':[]}
    assert recovery_round(locs,teachers,reports,stages,0.)==(None,[])
    before=copy.deepcopy(localizer.decision)
    for i in range(nbv.MAX_ROUNDS):
        steps, entries=recovery_round(locs,teachers,reports,stages,0.,
                                      active_recovery='map_nbv_v1',nbv_history=history)
        assert steps['r1']==[] and steps['r2']
        assert entries[0]['robot']=='r2' and entries[0]['action']=='map_nbv'
    assert stages=={'r1':1,'r2':6}
    assert recovery_round(locs,teachers,reports,stages,0.,active_recovery='map_nbv_v1',
                          nbv_history=history)==(None,[])
    assert localizer.decision==before and not localizer.map_pose_known


def test_body_turn_returns_before_regrasp_and_pan_slew_settles(localizer, monkeypatch):
    monkeypatch.setattr(nbv, 'plan', lambda *a, **kw:dict(body_yaw_deg=-90.,backstep_m=.1,
        views=[dict(arm='surroundings',pan_deg=-90.),dict(arm='floor',pan_deg=90.)]))
    steps, _=nbv.script(localizer,teacher(),0.)
    turns=[s for s in steps if s['label'].startswith('nbv_turn')]
    from sim.visible_belief import odometry
    delta=np.zeros(3)
    for step in turns:
        for wheels,durations in step['wheels']:
            assert max(durations)<=.15 and max(abs(w) for w in wheels)<=.35
            delta+=odometry(wheels,max(durations))
    assert delta==pytest.approx([0.,0.,0.],abs=1e-10)
    captures=[s for s in steps if s.get('capture')]
    assert captures[1]['wait']>=1.3
    assert steps[-1]['label']=='restore_arm'
