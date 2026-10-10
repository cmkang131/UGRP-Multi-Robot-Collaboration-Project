import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pytest
from harness import own_route_reference as m
from test_goal_route_continuous import fake_controller
from test_own_traversal_graph import sample


def attach(**options):
    c=fake_controller()
    c.heading_host=SimpleNamespace(command=Mock(return_value=({'kind':'hold'},{'reason':'fixture'})))
    c.explorer.goal.options.temporal_center_max_m=.10
    c.graph.observe(sample(1))
    c._entity('B',[.1,0],1,1,'x')
    c._select(1)
    return m.install(c,m.Options(**options))


def test_off_does_not_read_input_and_sixth_terminal_frame_bytes_equal():
    class Poison:
        def __getattribute__(self,name):raise AssertionError(name)
    p=Poison();assert m.install(p) is p
    c=fake_controller();c.done=True;c.stage='declared';c.declared=True;c.last_trace={'foo':'original'}
    def output():
        return json.dumps([c.receive(robot_id='r3',t=i,frame_id=i,rgb=None,servo=None,observation=None,frame_sha256='x') for i in range(6)],sort_keys=True).encode()
    before=output();method=c.receive.__func__;m.install(c)
    assert c.receive.__func__ is method and output()==before


def test_options_are_explicit_and_return_comparators_cannot_mix():
    with pytest.raises(ValueError):m.Options(progress_lookahead='on')
    with pytest.raises(ValueError):m.Options(return_local_vtr=True,return_own_free_astar=True)


def test_interpolated_carrot_ignores_dense_7cm_waypoint():
    p=m.carrot([[0,0],[.07,0],[.2,.1],[1,.1]],[0,0])
    assert np.linalg.norm(p)==pytest.approx(.6)
    assert p[0]>.5
    assert np.allclose(m.carrot([[0,0],[.2,0]],[0,0]),[.2,0])


def test_segment_progress_passes_overshot_point_without_visiting_5cm():
    p=m.Progress([[0,0],[.1,0],[.2,0],[1,0]])
    p.update([.25,.08])
    assert p.index==2 and p.distance==pytest.approx(.25)
    p.update([.21,.08]);assert p.distance==pytest.approx(.25)


def test_crossing_does_not_jump_to_later_route_branch():
    p=m.Progress([[0,0],[1,0],[1,1],[0,1],[0,0],[0,-1]])
    p.update([.01,.02]);assert p.index==0
    assert p.ratio<.01


def test_free_planner_blocks_unknown_without_changing_sensor_grid():
    raw=np.zeros((40,40),np.uint8);raw[:,20]=255
    cm=m.Costmap(raw,[-2,-2],.1);saved=cm.raw.tobytes()
    core=Mock();core.plan.return_value=np.empty((0,2))
    assert m.free_plan(core,cm,[-1,0,0],[1,0])==[]
    costs=core.plan.call_args.args[0]
    assert np.all(costs[:,20]==254) and cm.raw.tobytes()==saved
    core.reset_mock()
    assert m.free_plan(core,cm,[-1,0,0],[.01,0])==[] and not core.plan.called


def test_real_vendored_navfn_does_not_cross_unknown_barrier():
    raw=np.zeros((40,40),np.uint8);raw[:,20]=255
    core=m.PublicCore()
    assert m.free_plan(core,m.Costmap(raw,[-2,-2],.1),[-1,0,0],[1,0])==[]
    raw[15:25,20]=0
    assert len(m.free_plan(core,m.Costmap(raw,[-2,-2],.1),[-1,0,0],[1,0]))>2


def test_return_progress_updates_existing_declaration_cursor_only_at_end():
    c=attach(progress_lookahead=True)
    c.route={'samples':[{'pose':[x,0,0]} for x in [1,.5,0]],'nodes':[0]}
    c.stage='return'
    c._return_target(np.array([.4,.06,0]));assert c.cursor==1
    c._return_target(np.array([0,.03,0]));assert c.cursor==3


def test_vtr_uses_temporal_segment_not_spatial_nearest_future(monkeypatch):
    c=attach(return_local_vtr=True);c.stage='return'
    c.graph.nodes=[dict(id=i,frame_id=i*10,pose=[0,0,0]) for i in range(10)]
    c.route=dict(nodes=list(range(9,-1,-1)),samples=[{'pose':[1,0,0],'frame_id':90},{'pose':[0,0,0],'frame_id':0}])
    calls=[]
    def match(graph,s,node):
        calls.append(node);return dict(status='rejected',reason='low_overlap',node=node,t=s['t'],frame_id=s['frame_id'])
    monkeypatch.setattr(m.TraversalGraph,'match',match)
    s=sample(100);s['pose']=[1,0,0];c._localize(s,100)
    assert calls==[9,8,7] and c._repeat_blocked
    c._localize(s,101);assert len(calls)==3
    cmd,info=c.heading_host.command(t=101,pose=[1,0,0])
    assert cmd['kind']=='hold' and info['reason']=='repeat_localization_wait'


def test_arrival_requires_same_current_B_and_five_consecutive_frames():
    c=attach(arrival_verify_fsm=True);c.labels=np.ones((3,3))
    c.current_patches=[{'confirmed_t':1,'center_odom_m':[1,1]}]
    for i in range(2,10):c._arrival(i,i,np.zeros(3),False)
    assert not c.reached and c._visual_reason=='unconfirmed_or_other_B'
    c.current_patches=[{'confirmed_t':1,'center_odom_m':[.1,0]}]
    for i in range(10,14):c._arrival(i,i,np.zeros(3),False)
    assert not c.reached
    c._arrival(14,14,np.zeros(3),False);assert 'B' in c.reached


def test_latched_distance_does_not_waive_current_20cm_gate():
    c=attach(arrival_verify_fsm=True);c.labels=np.ones((3,3))
    c.current_patches=[];c._arrival(2,2,np.zeros(3),False)
    assert c._verify is not None
    c.current_patches=[{'confirmed_t':1,'center_odom_m':[.1,0]}]
    for i in range(3,10):c._arrival(i,i,np.array([1,0,0]),False)
    assert not c.reached and c.streak==0


def test_visual_reobserve_is_bounded_and_no_stale_declaration():
    c=attach(arrival_verify_fsm=True);c._arrival(2,2,np.zeros(3),False)
    for t in (3,14,25):
        cmd,info=c.heading_host.command(t=t,pose=np.zeros(3),path=[],goal=[.1,0])
    assert info['reason']=='arrival_verify_exhausted' and not c.reached


def test_arrival_current_evidence_holds_for_five_frames():
    c=attach(arrival_verify_fsm=True);c.labels=np.ones((3,3))
    c.current_patches=[{'confirmed_t':1,'center_odom_m':[.1,0]}]
    c._arrival(2,2,np.zeros(3),False)
    cmd,info=c.heading_host.command(t=2,pose=np.zeros(3))
    assert cmd['kind']=='hold' and info['reason']=='arrival_verify_current_evidence'
