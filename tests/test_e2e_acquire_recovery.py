"""Regression: rejected camera command must not become an infinite wait."""
import copy
from types import SimpleNamespace
import numpy as np
import pytest
from harness import e2e_acquire_recovery as m, e2e_pregrasp_acquire as acquire
from tests.test_e2e_align_progress import setup_transport


def test_actual_acquire_rejects_cancelled_view_on_three_distinct_frames():
    tr=setup_transport(pregrasp_acquire=acquire.OPTION)
    tr.acquire_recovery='cancel_v1';tr.grasp_once='track_gaze_v1'
    r=tr.robots['r2'];r.beam=r.last_beam=None
    r.servo[6]=1250;r.last_obs={'frame_id':10}
    a=dict(phase='scan',started=0.,cycles=0,view=1,view_pose={6:1500},view_frame=9,
           yaw=0.,sector_search=dict(origin_yaw=0.,direction=1,index=0,tried=[]))
    state={'acquisition':a}
    for frame,t in [(10,30.),(10,30.1),(11,30.4)]:
        r.last_obs={'frame_id':frame};acquire.acquire(tr,'r2',t,state,None)
        assert a['view']==1
    r.last_obs={'frame_id':12};acquire.acquire(tr,'r2',30.8,state,None)
    assert a['view']==2
    rejected=[e for e in tr.events if e['event']=='own_acquisition_view_rejected']
    assert len(rejected)==1 and rejected[0]['observed'] is False
    assert 'station' not in state and r.beam is None


def test_off_and_busy_never_reject_or_count_a_scheduled_posture():
    tr=setup_transport();r=tr.robots['r2'];r.last_obs={'frame_id':1}
    a=dict(view=0,view_pose={6:987})
    assert not m.failed_view(tr,'r2',30.,a,False)
    tr.acquire_recovery='cancel_v1'
    for frame in range(10):
        r.last_obs={'frame_id':frame}
        assert not m.failed_view(tr,'r2',30.+frame,a,True)
    assert 'view_failure_count' not in a
    r.servo[6]=987
    assert not m.failed_view(tr,'r2',50.,a,False)


def test_resume_preserves_native_failed_goal_and_recovery_cursor():
    events=[]
    n=SimpleNamespace(blacklist=[[1.,2.]],visited=[[3.,4.]],phase='spin',retry=4,round_index=2,
                      target=[5.,6.],finished=True,event=lambda *a,**k:events.append((a,k)))
    e=SimpleNamespace(navigator=n,plan={'old':1},last_plan_t=4.)
    m.resume(SimpleNamespace(goal=SimpleNamespace(explorer=e)),10.)
    assert n.blacklist==[[1.,2.]] and n.visited==[[3.,4.]]
    assert n.phase=='spin' and n.retry==4 and n.round_index==2 and n.target==[5.,6.]
    assert not n.finished and n.initial_scan_used and e.plan is None


def test_three_unchanged_choices_use_native_alternative_not_restart_same_recovery():
    from harness.e2e_exploration import Navigator
    driver=SimpleNamespace(pose=np.zeros(3));n=Navigator(driver)
    n.target=n.frontier=np.array([1.,2.]);n.locked=True
    e=SimpleNamespace(local_pose=np.zeros(3),navigator=n,plan={},last_plan_t=0.)
    tr=SimpleNamespace(robots={'r1':SimpleNamespace(goal=SimpleNamespace(explorer=e))},event=lambda *a,**k:None)
    a={};command={'kind':'hold'}
    for t in (1.,2.,3.):m.filter_choice(tr,'r1',t,a,command)
    assert n.phase=='backup' and any(np.allclose(p,[1.,2.]) for p in n.blacklist)
    for t in (4.,5.,6.):m.filter_choice(tr,'r1',t,a,command)
    assert n.phase!='backup'  # native round-robin failure, not resetting the same backup
    assert n.blacklist


def test_moving_command_is_not_excluded():
    n=SimpleNamespace(action_failed=lambda *a:pytest.fail('moving command was rejected'))
    e=SimpleNamespace(local_pose=np.zeros(3),navigator=n)
    tr=SimpleNamespace(robots={'r1':SimpleNamespace(goal=SimpleNamespace(explorer=e))})
    a={};command=dict(kind='mecanum',forward=.35,left=0.,turn=0.,duration_s=.1)
    for t in range(10):
        e.local_pose[0]=t*.01
        assert m.filter_choice(tr,'r1',float(t),a,command)==command


def test_stage_registration_contains_four_distinct_color_recovery_candidates():
    import json
    from pathlib import Path
    from scripts.run_e2e_stage_probe import MODES
    for v in range(426,430):
        assert MODES[f'v{v}']=='track_gaze_v1'
        w=json.loads(Path(f'configs/simulation_workflows.d/e2e18_v{v}.json').read_text())['workflows'][0]
        assert w['id']==f'e2e18-v{v}'
