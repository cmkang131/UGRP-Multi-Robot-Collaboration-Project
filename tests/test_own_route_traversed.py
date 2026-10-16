import json
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pytest
from harness import grid_acceleration as acceleration
from harness import goal_route_continuous as legacy
from harness import own_route_reference as m
from harness.own_traversed_free import TraversedFree
from scripts import run_own_route_references as old
from scripts import run_own_route_traversed as runner
from test_goal_route_continuous import fake_controller
from test_own_traversal_graph import sample


def prepared(monkeypatch, near=False, no_path=False):
    c=fake_controller();e=c.explorer
    c.dev_light=True
    c.graph.observe(sample(1))
    c._entity('B',[.1 if near else 1.,0],1,1,'x');c._select(1)
    e.memory=SimpleNamespace(self_map=SimpleNamespace(odom=SimpleNamespace(covariance=np.eye(3)*1e-8)))
    e.pose=np.zeros(3);e.map_to_odom=np.zeros(3);e.grid=None;e.latest={};e.motion_model='off'
    e.goal.options.temporal_center_max_m=.1;e.goal.tracks=[]
    active=[]
    def receive(**kw):
        active.append(acceleration.enabled())
        return {'kind':'hold'},dict(t=kw['t'],frame_id=kw['frame_id'],local_pose=[0,0,0],status='probe',goal={})
    e.receive=receive
    c.sensor=SimpleNamespace(measure=lambda *args:[]);c.detect_boxes=lambda *args:[]
    costmap=m.Costmap(np.zeros((40,40),np.uint8),[-2,-2],.1)
    monkeypatch.setattr(legacy,'own_measurement',lambda *args:[])
    monkeypatch.setattr(legacy,'remembered_goal',lambda *args,**kw:None)
    for module in [legacy,m]:monkeypatch.setattr(module,'from_observed_grid',lambda *args:costmap)
    c.navigator=SimpleNamespace(phase=None,clear_requested=False,core=SimpleNamespace(collision_time=lambda *args:float("inf")),
        update=lambda *args,**kw:dict(path_m=[] if no_path else [[0,0],[1,0]],status='probe'),
        command=lambda *args:dict(forward=0,left=0,turn=0))
    c.heading_host=SimpleNamespace(command=Mock(return_value=({'kind':'hold'},{'reason':'fixture'})))
    acceleration.install(c,map_acceleration=acceleration.OPTION)
    return c,active


def frame(c):
    return c.receive(robot_id='r3',t=2.,frame_id=2,rgb=np.zeros((12,16,3),np.uint8),servo={},
        observation={'segments':[[[1.,-.5],[1.,.5]]],'camera':[0.,0.]},frame_sha256='x')


@pytest.mark.parametrize('condition',list(old.CONDITIONS))
def test_six_conditions_first_live_receive_with_real_acceleration_wrapper(monkeypatch,condition):
    c,active=prepared(monkeypatch)
    options=old.CONDITIONS[condition]
    m.install(c,options)
    audit=[];runner.execution_audit(c,options,audit.append)
    _,trace=frame(c)
    assert active==[True] and not acceleration.enabled()
    assert len(audit)==1 and audit[0]['valid'] and audit[0]['call']==1
    if condition!='baseline':
        execution=trace['reference_navigation']['execution']
        assert execution['dispatched']==asdict(options)
        assert all(execution['exercised'][k] for k in ('receive','localize','arrival','heading'))
    else:assert 'reference_navigation' not in trace


def test_missing_path_fsm_fallback_executes_through_checkpoint_wrapper(monkeypatch):
    c,active=prepared(monkeypatch,near=True,no_path=True)
    m.install(c,m.Options(arrival_verify_fsm=True))
    _,trace=frame(c)
    assert active==[True]
    assert trace['reference_navigation']['execution']['exercised']['heading']
    assert c._verify is not None and c._host_t==2


def test_default_off_audit_preserves_full_frame_and_snapshot_bytes(monkeypatch):
    a,_=prepared(monkeypatch);b,_=prepared(monkeypatch)
    m.install(b);audit=[];runner.execution_audit(b,m.Options(),audit.append)
    outa=frame(a);outb=frame(b)
    assert json.dumps(outa,sort_keys=True)==json.dumps(outb,sort_keys=True)
    assert json.dumps(a.snapshot(),sort_keys=True)==json.dumps(b.snapshot(),sort_keys=True)


@pytest.mark.parametrize('res',[.05,.1])
def test_traversed_prefix_and_new_pose_make_route_without_mutating_wall_evidence(res):
    graph=SimpleNamespace(nodes=[dict(frame_id=1,pose=[-.8,0,0])],
        edges=[dict(samples=[dict(frame_id=i+2,pose=[x,0,0]) for i,x in enumerate(np.arange(-.75,.8,.04))])],pending=[])
    history=TraversedFree.from_graph(graph);history.add([.8,0,0],100)
    size=round(4/res)
    raw=np.full((size,size),255,np.uint8);raw[size//2,size//2]=254
    original=raw.tobytes();cm=m.Costmap(raw,[-2,-2],res);core=m.PublicCore()
    assert m.free_plan(core,cm,[.8,0,0],[-.8,0])==[]
    overlay=history.overlay(cm,[0,0,0])
    assert m.free_plan(core,overlay,[.8,0,0],[-.8,0])
    assert raw.tobytes()==original and overlay.raw[0,0]==255
    assert history.diagnostics()['cleared_occupied']==1
    assert history.diagnostics()['cleared_unknown']>0


def test_pose_jump_does_not_fabricate_a_free_shortcut_and_map_tf_moves_support():
    history=TraversedFree();history.add([-1,0,0],1);history.add([1,0,0],2)
    cm=m.Costmap(np.full((60,60),255,np.uint8),[-3,-3],.1)
    overlay=history.overlay(cm,[0,0,0])
    assert m.free_plan(m.PublicCore(),overlay,[-1,0,0],[1,0])==[]
    rotated=history.overlay(cm,[0,0,np.pi/2])
    for p in [[0,1],[0,-1]]:
        x,y=rotated.world_to_map(p);assert rotated.raw[y,x]==0
    x,y=rotated.world_to_map([1,0]);assert rotated.raw[y,x]==255


def test_new_batch_24_fixed_same_seeds_budgets_and_initial_marker_required(tmp_path):
    jobs=runner.jobs(tmp_path)
    assert len(jobs)==24 and len({j['output'] for j in jobs})==24
    assert set(j['seed'] for j in jobs)==set(range(63001,63007))
    for j in jobs:
        b=runner.bundle(j['seed'],'a'*40,j['condition'],'stage')
        assert b['case_cap_s']==540 and b['phase_budgets_s']=={'B_approach':270.,'return':270.}
    from test_own_route_references_batch import write_fixture
    write_fixture(tmp_path,[{'forward':.3}]*101,[i*.001 for i in range(101)])
    assert runner.early_check(tmp_path,100,181)['anomaly']=='missing_or_invalid_execution_path'
    (tmp_path/'execution-path.jsonl').write_text(json.dumps(dict(t=100,valid=True))+'\n')
    assert runner.early_check(tmp_path,100,181)['anomaly'] is None
