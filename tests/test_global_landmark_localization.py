"""Offline geometry/command-only regressions; no physics or renderer."""
import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_pair_highpose_contract as contract
from sim.global_landmark_localization import GlobalLandmarkMatcher, rotation
from sim.lookaround_localization import LookaroundLocalizer
from sim.release_global_observation import margin_report, pair_choice, recovery_script, BACKSTEP_M, MAX_SHIFT_M


@pytest.fixture(scope='module')
def matcher():
    return GlobalLandmarkMatcher(contract.resolve('zone_wide_two_doors_final_v3')[0])


def scene_views(matcher, pose, command=(0,0,0), *, only_parallel=False):
    features=[]
    for e in matcher.edges:
        if e['kind']!='floor_line' or not e['group'].startswith('zone_A:'):
            continue
        if only_parallel and abs(e['n'][0])<.5:
            continue
        # Partial edge, not a correspondence of visible endpoints to corners.
        a,b=e['p'];p=np.array([.7*a+.3*b,.3*a+.7*b])
        features.append(dict(kind='floor_line',hue=e['hue'],endpoints=((p-np.array(pose[:2]))@rotation(pose[2])).tolist(),
                             normal=(rotation(-pose[2])@e['n']).tolist()))
    return [dict(prior=list(command),features=copy.deepcopy(features),wall_points_body=[],t=i) for i in range(2)]


def test_global_pose_without_prior_and_partial_endpoints(matcher):
    pose=[4.5,-.5,.72];views=scene_views(matcher,pose)
    out=matcher.fit(views,[0,0,0])
    assert out['accepted'] and not out['prior_used']
    assert out['proposed']==pytest.approx(pose,abs=.001)
    # Arbitrary odometry-origin change cannot move the estimated map pose.
    for view in views:view['prior']=[-100.,80.,1.8]
    shifted=matcher.fit(views,[-100.,80.,1.8])
    assert shifted['proposed']==pytest.approx(out['proposed'],abs=1e-8)


def test_motion_compensation_across_views(matcher):
    first=[4.5,-.5,.72];delta=[-.10,0,.4]
    current=[*(np.array(first[:2])+rotation(first[2])@delta[:2]),first[2]+delta[2]]
    views=scene_views(matcher,first)[:1]+scene_views(matcher,current,delta)[:1]
    out=matcher.fit(views,delta)
    assert out['accepted'] and out['proposed']==pytest.approx(current,abs=.001)


def test_parallel_or_empty_geometry_does_not_create_map_anchor(matcher):
    out=matcher.fit(scene_views(matcher,[4.5,-.5,.72],only_parallel=True),[0,0,0])
    assert not out['accepted']
    loc=LookaroundLocalizer(matcher.static,[0,0,0],mode='setdown_global_v1',map_pose_known=False)
    assert not loc.finalize()['accepted'] and not loc.map_pose_known


def test_symmetric_map_stays_ambiguous(matcher):
    static=copy.deepcopy(matcher.static)
    static['regions']['zone_B']['rgba']=static['regions']['zone_A']['rgba']
    m=GlobalLandmarkMatcher(static)
    out=m.fit(scene_views(m,[4.5,-.5,.72]),[0,0,0])
    assert not out['accepted'] and out['reason']=='ambiguous_global_landmarks'


def test_global_localizer_acceptance_changes_map_frame_not_command_frame(matcher):
    pose=[4.5,-.5,.72]
    loc=LookaroundLocalizer(matcher.static,[0,0,0],mode='setdown_global_v1',map_pose_known=False)
    loc.views=scene_views(matcher,pose)
    assert loc.finalize()['accepted'] and loc.map_pose_known
    assert loc.own.x==pytest.approx(pose,abs=.001)
    assert loc.command_own.x==pytest.approx([0,0,0])
    loc.propagate([.35]*4,.1)
    assert loc.command_own.x[0]>0 and loc.command_own.x[1]==0


def test_margins_use_own_camera_pose_and_messages_only(matcher):
    loc=SimpleNamespace(own=SimpleNamespace(x=[4.6,-.5,math.pi/2]),
                        decision=dict(accepted=True,sigma=[.05,.05,.05]))
    teacher=SimpleNamespace(zone_rect=(4.6,.4,.3,.7),end_and_outward=lambda t:((.25,0),(-1,0),'commands'))
    row=margin_report(loc,teacher,0)
    assert row['kind']=='localized_margin' and row['margin_m']==pytest.approx(.05)
    assert not any(k in row for k in ('pose','center','features','image'))
    other={**row,'margin_m':.75}
    reports={'r1':row,'r2':other};out=pair_choice(reports,('r1','r2'),0)
    assert out['action']=='shift' and out['shift_m']==MAX_SHIFT_M
    assert pair_choice({'r1':row,'r2':dict(kind='none')},('r1','r2'),0)['action']=='observe'
    assert pair_choice({'r1':{**row,'margin_m':.4},'r2':{**row,'margin_m':.4}},('r1','r2'),0)['action']=='lower'


def test_lateral_recovery_keeps_guard_and_rejects_conflicting_intervals():
    robots=('r1','r2')
    row=dict(kind='localized_margin',margin_m=.4,lateral_clearance_m=.025,
             lateral_shift_lo_m=.015,lateral_shift_hi_m=.43)
    reports=dict(r1=row,r2={**row,'lateral_shift_lo_m':.02})
    assert pair_choice(reports,robots,0)['reason']=='lateral_clearance_unresolved'
    choice=pair_choice(reports,robots,0,lateral_recovery='bounded_v1')
    assert choice['action']=='shift' and choice['lateral_shift_m']==.1
    assert choice['lateral_interval_m']==[.02,.43]
    for other in ({**row,'lateral_shift_lo_m':-.4,'lateral_shift_hi_m':-.02},
                  dict(kind='localized_margin',margin_m=.4,lateral_clearance_m=.03)):
        assert pair_choice(dict(r1=row,r2=other),robots,0,lateral_recovery='bounded_v1')['action']=='observe'


def test_lateral_pwm_is_same_world_translation_for_opposite_own_headings():
    from sim.release_global_observation import lateral_shift_plans
    from sim.visible_belief import odometry
    angles=dict(r1=math.pi/2+.12,r2=-math.pi/2+.10)
    locs={r:SimpleNamespace(own=SimpleNamespace(x=[0.,0.,a]),decision={'accepted':True}) for r,a in angles.items()}
    teachers={r:SimpleNamespace(zone_rect=(4.6,.4,.3,.7)) for r in angles}
    plans=lateral_shift_plans(locs,teachers,.1)
    assert len(plans['r1'])==len(plans['r2'])
    for rid,plan in plans.items():
        got=np.zeros(3)
        for levels,durations in plan:
            assert all(.04<=d<=.1 for d in durations)
            got+=odometry([w*d/.1 for w,d in zip(levels,durations)],.1)
        a=angles[rid];c,s=math.cos(a),math.sin(a)
        assert [c*got[0]-s*got[1],s*got[0]+c*got[1],got[2]]==pytest.approx([.1,0.,0.],abs=1e-10)
    locs['r1'].decision={'accepted':False}
    with pytest.raises(ValueError,match='own RGB'):lateral_shift_plans(locs,teachers,.1)


def test_recovery_order_motion_bounds_and_no_blind_translation(matcher):
    from sim.grasp_act_release_teacher import ReleaseTeacher
    loc=SimpleNamespace(global_matcher=matcher,profile='off',decision=dict(alternatives=[dict(pose=[4.6,-.5,math.pi/2])]))
    teacher=ReleaseTeacher('r1','teal',{1:2000,3:820,4:2320,5:1320,6:1500},handoff_pose_estimate=None,zone_rect=(4.6,.4,.3,.7))
    plans=[recovery_script(loc,teacher,i,0) for i in (1,2,3)]
    assert [d['action'] for _,d in plans]==['pan','backstep','body_turn']
    assert not any('wheels' in step for step in plans[0][0])
    assert plans[1][1]['backstep_cap_m']==BACKSTEP_M==.10
    for steps,_ in plans:
        assert all(max(d)<=.15 for step in steps for _,d in step.get('wheels',[]))
    turns=[s for s in plans[2][0] if 'wheels' in s]
    assert len(turns)==2 and turns[-1]['label']=='recovery_turn_return'
    loc.decision={}
    steps,entry=recovery_script(loc,teacher,2,0)
    assert not any('wheels' in s for s in steps) and 'skipped' in entry['action']
    assert any(s.get('capture') for s in steps)


def test_saved_camera_detections_recover_unique_pose_and_reject_ambiguity(matcher):
    fixture=json.loads((Path(__file__).parent/'fixtures/release_global_landmarks.json').read_text())
    for row in fixture['cases']:
        out=matcher.fit(row['views'],row['command_pose'])
        assert out['accepted']==row['expect_accepted']
        if out['accepted']:
            # Test/evaluation side only: the estimator never sees this label.
            assert math.dist(out['proposed'][:2],row['evaluation_truth'][:2])<.10


def test_map_support_keeps_near_wall_hypotheses_without_authorizing_motion(matcher):
    m = GlobalLandmarkMatcher(matcher.static, localization_support='map_free_v1')
    poses = [[4.7, 1.31, -1.5], [4.7, 1.45, 0.], [6., 0., 0.]]
    assert m.pose_supported(poses).tolist() == [True, False, False]
    assert not matcher.pose_supported(poses).any()
    assert np.array_equal(m.free(poses), matcher.free(poses))
    assert np.array_equal(m.free(poses, extra_clearance=.15), matcher.free(poses, extra_clearance=.15))
    assert not m.free(poses, extra_clearance=.15).any()
    with pytest.raises(ValueError):
        GlobalLandmarkMatcher(matcher.static, localization_support='unknown')


def test_saved_74963_sensor_evidence_recovers_pose_deleted_by_motion_inflation():
    fixture = json.loads((Path(__file__).parent/'fixtures/release9_map_support.json').read_text())
    static = contract.resolve(fixture['map_id'])[0]
    old = GlobalLandmarkMatcher(static)
    new = GlobalLandmarkMatcher(static, localization_support='map_free_v1')
    for row in fixture['cases']:
        before = old.fit(row['views'], row['command_pose'])
        after = new.fit(row['views'], row['command_pose'])
        assert before['accepted'] == row['old_accepted']
        assert after['accepted'] and after['normal_rank'] == 2
        assert after['score_gap'] >= .75 and all(after['acceptance_checks'].values())
        # Evaluation label is read only AFTER both estimates have been computed.
        assert math.dist(after['proposed'][:2], row['evaluation_truth'][:2]) < .05
        assert math.dist(before['proposed'][:2], row['evaluation_truth'][:2]) > .5
        assert not new.free([after['proposed']])[0]


def test_map_support_does_not_accept_symmetric_or_parallel_evidence(matcher):
    static = copy.deepcopy(matcher.static)
    static['regions']['zone_B']['rgba'] = static['regions']['zone_A']['rgba']
    m = GlobalLandmarkMatcher(static, localization_support='map_free_v1')
    assert not m.fit(scene_views(m, [4.5, -.5, .72]), [0, 0, 0])['accepted']
    assert not m.fit(scene_views(m, [4.5, -.5, .72], only_parallel=True), [0, 0, 0])['accepted']
    loc = LookaroundLocalizer(static, [0, 0, 0], mode='setdown_global_v1',
                             map_pose_known=False, localization_support='map_free_v1')
    assert loc.record()['localization_support'] == 'map_free_v1'
    assert not loc.finalize()['accepted'] and not loc.map_pose_known
