"""Unloaded recovery safety/coverage contracts, no physics or renderer."""
import copy
import math

import numpy as np
import pytest

from harness.zone_final_environment import resolve
from sim.grasp_act_release_teacher import ReleaseTeacher, check_wheels
from sim.lookaround_localization import LookaroundLocalizer
from sim.release_global_observation import recovery_round
from sim.release_setdown_lookaround import script
from sim.visible_belief import odometry


@pytest.fixture
def pair():
    loc = LookaroundLocalizer(resolve('zone_wide_door_geometry_v3')[0], [-.15, 0., 0.],
                             mode='setdown_global_v1', map_pose_known=False)
    # An ambiguous RGB hypothesis is usable for clearance, never as a pose.
    loc.decision = dict(accepted=False, credible_hypotheses=[dict(pose=[4.70, 1.09, -1.44])])
    teacher = ReleaseTeacher('r2', 'blue', {1:2000,3:820,4:2320,5:1320,6:1500},
                             handoff_pose_estimate=None, zone_rect=(4.6,.4,.3,.7))
    teacher.holding = False
    teacher.belief.observe('released_band', [.39,0.,math.pi], 0., source='own_command')
    return loc, teacher


def test_unaccepted_pose_allows_bounded_unloaded_look_without_accepting_it(pair):
    loc, teacher = pair
    before = copy.deepcopy(loc.decision)
    steps, entry = script(loc, teacher, 30., [0.,0.,0.])
    assert entry['action']=='setdown_lookaround_v1' and entry['capture_count']==12
    assert not loc.map_pose_known and loc.decision==before
    assert entry['retrace_m']==.10
    headings = {s['label'].split('_')[2] for s in steps if s['label'].startswith('setdown_view')}
    assert headings=={'-90', '+90'}
    delta=np.zeros(3)
    for i, step in enumerate(steps):
        if 'wheels' not in step:
            continue
        assert steps[i-1]['label'].startswith('setdown_fold')
        for wheels, durations in step['wheels']:
            check_wheels(wheels, durations)
            delta+=odometry(wheels,max(durations))
    assert delta==pytest.approx([.10,0.,0.],abs=1e-10)
    assert steps[-1]['label']=='restore_arm'


@pytest.mark.parametrize('case,reason', [
    ('held','cargo_not_set_down'), ('closed','cargo_not_set_down'),
    ('trace','release_command_trace_missing'), ('turned','not_on_issued_backoff_trace'),
    ('short','not_on_issued_backoff_trace'), ('sideways','not_on_issued_backoff_trace'),
    ('beam','released_beam_turn_clearance'), ('memory','release_command_memory_missing'),
    ('unknown','map_clearance_unknown'), ('unsafe','map_clearance_unsafe')])
def test_recovery_rejects_unsafe_or_unknown_without_any_commands(pair,case,reason):
    loc,t=pair;anchor=[0.,0.,0.]
    if case=='held':t.holding=True
    elif case=='closed':t.pwm[1]=1500
    elif case=='trace':anchor=None
    elif case=='turned':loc.command_own.x[2]=.1
    elif case=='short':loc.command_own.x[0]=-.05
    elif case=='sideways':loc.command_own.x[1]=.1
    elif case=='beam':t.belief.items['released_band']['pose'][0]=.30
    elif case=='memory':t.belief.items.clear()
    elif case=='unknown':loc.decision={}
    elif case=='unsafe':loc.decision['credible_hypotheses'].append(dict(pose=[5.1,1.1,0.]))
    steps,entry=script(loc,t,30.,anchor)
    assert steps==[] and entry['reason']==reason


def test_one_attempt_budget_accepted_robot_waits_and_failure_is_atomic(pair):
    loc,t=pair;ls={r:loc for r in ('r1','r2')};ts={r:t for r in ls}
    reports={'r1':dict(kind='localized_margin'),'r2':dict(kind='none')}
    stages={'r1':0,'r2':1};anchors={r:[0.,0.,0.] for r in ls}
    steps,entries=recovery_round(ls,ts,reports,stages,30.,active_recovery='setdown_lookaround_v1',
                                release_command_poses=anchors)
    assert steps['r1']==[] and steps['r2'] and stages=={'r1':0,'r2':2}
    assert recovery_round(ls,ts,reports,stages,60.,active_recovery='setdown_lookaround_v1',
                          release_command_poses=anchors)==(None,[])
    # Planning one robot must not consume its budget if the other is unsafe.
    stages={'r1':1,'r2':1};reports['r1']['kind']='none';anchors.pop('r2')
    steps,_=recovery_round(ls,ts,reports,stages,30.,active_recovery='setdown_lookaround_v1',
                           release_command_poses=anchors)
    assert steps is None and stages=={'r1':1,'r2':1}


def test_native_yaw_profile_matches_saved_motion_and_keeps_legacy_default():
    """Independent recorded native motion, not an encoder/decoder round trip."""
    import json
    from pathlib import Path
    from sim.visible_belief import rates
    from sim.lookaround_localization import rotate_plan
    fixture=json.loads((Path(__file__).parent/'fixtures/release8_native_yaw.json').read_text())
    samples=fixture['samples'];assert len(samples)==36
    assert min(abs(s['error_deg']) for s in samples)>172.
    assert max(abs(s['sign_corrected_error_deg']) for s in samples)<8.
    assert rates('off')==(.129,.08,.35)
    assert rates('native_yaw_v1')==(.129,.08,-.35)
    for desired in (-math.pi/2,math.pi/2):
        plan=rotate_plan(desired,'native_yaw_v1')
        # Saved native v7 (-,+,-,+) rotates CW, hence desired CCW needs (+,-,+,-).
        assert math.copysign(1,plan[0][0][0])==math.copysign(1,desired)
        realized=sum(odometry(w,max(ds),'native_yaw_v1')[2] for w,ds in plan)
        assert realized==pytest.approx(desired,abs=.015)
        assert all(max(ds)<=.15 and max(map(abs,w))<=.35 for w,ds in plan)
    assert rotate_plan(math.pi/2)==rotate_plan(math.pi/2,'off')


def test_native_pose_and_released_memory_share_one_command_frame(pair):
    from scripts.run_grasp_act_release import CommandPose
    loc,t=pair;loc.profile=t.odometry_profile='native_yaw_v1'
    loc.own.x=loc.command_own.x=np.zeros(3)
    issued=CommandPose('native_yaw_v1')
    t.belief.observe('released_band',[1.,0.,0.],0.,source='own_command')
    wheels=[-.35,.35,-.35,.35]
    for _ in range(10):
        issued.propagate(wheels,.1);loc.propagate(wheels,.1);t.dead_reckon(wheels,.1)
    assert issued.x==pytest.approx([0.,0.,-.35])
    assert loc.own.x==pytest.approx(issued.x)
    assert loc.command_own.x==pytest.approx(issued.x)
    # A static point moves CCW in the body frame when the body turns CW.
    assert t.belief.get('released_band',1.)['pose']==pytest.approx([math.cos(.35),math.sin(.35),.35])
