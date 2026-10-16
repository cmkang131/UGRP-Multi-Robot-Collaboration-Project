"""Saved stalls, permitted inputs and bounded recovery. No physics or rendering."""
import json
import math
from copy import deepcopy
from pathlib import Path
import pytest
from sim.grasp_act_progress import ApproachProgress
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_visible_route import constraints,free,waypoint,segment_free
from scripts.zone_teacher import FOLDED

CASES=json.loads((Path(__file__).parent/'fixtures/grasp_act_search7_stalls.json').read_text())['cases']


def teacher(row,mode='approach_progress_v1'):
    t=VisibleOnlyGraspTeacher(row['rid'],row['end'],row['pwm'],bounds=(-20,20,-20,20),
        teacher_stability='align_relook_v1',teacher_search='search_body_scan_v2',
        approach_goal_set='approach_goal_set_v1',nominal_blocked_handoff='nominal_blocked_handoff_v1',
        approach_progress=mode)
    t.folded_ready=True
    return t


def test_watchdog_uses_net_translation_not_yaw_time_or_repeat_calls():
    p=ApproachProgress()
    assert p.observe((0,0),0) is None
    for _ in range(10):assert p.observe((0,0),2.9) is None
    assert p.observe((0,0),3)=='replan'
    assert p.observe((0,0),5.9) is None
    assert p.observe((0,0),6)=='handoff'
    assert p.observe((.011,0),6.1) is None
    assert p.observe((.011,0),9.1)=='replan'
    p.reset()
    assert p.observe((.011,0),20) is None


@pytest.mark.parametrize('row',CASES,ids=['ep12-segment','ep15-cargo'])
def test_recorded_stall_replans_once_then_cleanly_hands_off(row):
    t=teacher(row);w=row['world'];pose,g,heading,goal=t._geometry(w)
    radius,discs,rects=constraints(w,t.rid,True)
    if row['episode']==12:
        assert free(goal,discs,rects,radius)
        assert row['path'] and waypoint(pose[:2],row['path'],discs,rects,radius) is None
        assert all(not segment_free(pose[:2],p,discs,rects,radius) for p in row['path'])
    else:
        assert not free(goal,discs,rects,radius)
        cargo=w['objects']['green_1']
        assert math.dist(goal,cargo['xy'])-cargo['radius']-.005-radius==pytest.approx(-.0432374457)
    original=deepcopy(w)
    for dt in (0.,.1,1.,2.,2.9,3.,3.1,4.,5.9,6.):
        value,_=t._approach(w,row['t']+dt)
        assert not any(value['wheels']) and value['pwm']['1']==2000
        assert t.phase=='approach'
    assert w==original  # Never clear obstacle evidence to manufacture a path.
    assert t.outcome=='approach_blocked_handoff' and not t.path
    assert [r['approach_progress'] for r in t.progress_log]==['replan','handoff']
    value,done=t.step(w,row['t']+100,permit_pick=True)
    assert not done and not any(value['wheels']) and t.phase!='pick'


@pytest.mark.parametrize('row',CASES)
def test_off_keeps_original_indefinite_hold(row):
    t=teacher(row,'off');w=row['world']
    for dt in (0.,3.,6.,30.):
        value,_=t._approach(w,row['t']+dt)
        assert not any(value['wheels'])
    assert t.outcome is None and not t.progress_log


def test_invalid_profile_rejected_before_world_creation(tmp_path):
    from scripts.run_grasp_act_teacher import run
    for mode in ('bogus','approach_progress_v1'):
        with pytest.raises(ValueError,match='approach progress'):
            VisibleOnlyGraspTeacher('r1','teal',FOLDED,approach_progress=mode)
    for kw in ({'teacher_profile':'legacy'}, {'teacher_profile':'visible_only','teacher_stability':'off'},
               {'teacher_profile':'visible_only','teacher_stability':'align_relook_v1','self_pose_source':'perfect_self_comparison'}):
        with pytest.raises(ValueError,match='approach progress'):
            run({},tmp_path,approach_progress='approach_progress_v1',**kw)


def test_ready_wait_is_exempt_and_alignment_has_its_own_checker():
    row=CASES[0];t=teacher(row);t.progress.observe((0,0),0)
    t.phase='ready';t.started=True;t.phase_t=row['t'];t.skill_started=row['t']
    # Terminal READY path via mocked step isolates protocol wait from routing.
    t._step=lambda *a,**kw:(t._hold(row['t']),False)
    t.step(row['world'],row['t'])
    assert t.progress.anchor is None and not t.progress_log


def test_speed_gate_cannot_mix_progress_profiles(tmp_path,monkeypatch):
    from scripts import run_grasp_act_batch as batch
    import scripts.grasp_act_host as host
    prior=tmp_path/'runs'/'probe';prior.mkdir(parents=True)
    (prior/'RUN_META.json').write_text(json.dumps({'sha':'old'}))
    (prior/'resource-admission.json').write_text('{}')
    monkeypatch.setattr(batch.subprocess,'check_output',lambda *a,**kw:'old\n')
    monkeypatch.setattr(batch,'execution_tree',lambda *a:{})
    monkeypatch.setattr(batch,'same_machine',lambda *a:None)
    with pytest.raises(ValueError,match='approach progress mode mismatch'):
        batch.reuse_speed_gate(prior,tmp_path/'plan.json',16,3.5,{},approach_progress='approach_progress_v1')


def test_v3_goal_error_window_accepts_alignment_but_rejects_oscillation_and_slip():
    from sim.grasp_act_progress import GoalProgress
    p=GoalProgress()
    assert p.observe_goal((0,0,0),(1,0),1.,0.) is None
    # Heading error decreases while translation is stationary.
    assert p.observe_goal((0,0,.1),(1,0),1.,2.9) is None
    assert p.observe_goal((0,0,.2),(1,0),1.,5.8) is None
    assert p.observe_goal((0,0,.1),(1,0),1.,8.8)=='replan'
    assert p.observe_goal((0,0,.2),(1,0),1.,11.8)=='handoff'
    p.reset()
    # Issued odometry moves, but the observed relative distance stays 1 m.
    # Do not credit command issuance as actual approach progress.
    assert p.observe_goal((0,0,0),(1,0),0.,0.) is None
    assert p.observe_goal((.2,0,0),(1.2,0),0.,3.)=='replan'
    assert p.observe_goal((.4,0,0),(1.4,0),0.,6.)=='handoff'
    assert p.observe_goal((.4,0,0),(1.38,0),0.,6.1) is None
