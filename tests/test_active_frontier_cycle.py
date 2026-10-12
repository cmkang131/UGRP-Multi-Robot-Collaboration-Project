import json,math
import numpy as np
import pytest
from harness.active_frontier_cycle import make_mapper,OPTION,CycleNavigator,SWEEP_RAD,VisibilityMapper
from harness.active_wall_recovery import make_mapper as original,RecoveryMapper
from harness.active_camera import SEARCH
from harness.public_navigation_unknown import UnknownCostmap
from harness.public_navigation_recovery import issued_twist
from harness.self_map_prob import wrap

ARGS=dict(active_mapping='frontier_rbpf_v1',active_recovery='nav2_frontier_v1',navigation_map='public_ros_v8',motion_model='s2_pulse_v122_rotL_v1')

def clear():return UnknownCostmap(np.zeros((120,120),np.uint8),[-3,-3],.05)

def test_off_bytes_and_invalid_option():
    a=make_mapper('r3',0,SEARCH,**ARGS)
    b=original('r3',0,SEARCH,**ARGS)
    assert type(a) is type(b) is RecoveryMapper
    obs=dict(segments=[],features=[],floor_xy=[[.7,-.2],[.7,.2]],camera=[.124,0.])
    rgb=np.zeros((480,640,3),np.uint8)
    for i,t in enumerate([2.,2.2,3.]):
        x=a.receive(robot_id='r3',t=t,frame_id=i,rgb=rgb,servo=SEARCH,observation=obs)
        y=b.receive(robot_id='r3',t=t,frame_id=i,rgb=rgb,servo=SEARCH,observation=obs)
        assert json.dumps([x,a.memory.self_map.export(),a.navigator.events])==json.dumps([y,b.memory.self_map.export(),b.navigator.events])
    with pytest.raises(ValueError):make_mapper('r3',0,SEARCH,frontier_observation='bad',**ARGS)


def test_sweep_wrap_signed_yaw_and_timeout():
    n=CycleNavigator();c=clear();pose=np.array([0.,0.,3.1]);plan=n.update(c,pose,0.)
    assert plan['status']=='sensor_sweep'
    for i,angle in enumerate(np.arange(.05,SWEEP_RAD+.051,.05)):
        command=n.command(c,[0,0,wrap(3.1+angle)],plan,i*.2+.2)
    assert n.phase is None
    assert n.events[-1]['reason']=='sensor_sweep_completed'
    assert np.all(issued_twist(command)==0)
    n.request_sweep(30,'test');n.update(c,pose,30)
    n.command(c,pose,plan,60)
    assert n.events[-1]['reason']=='sensor_sweep_incomplete' and n.phase is None


def test_back_and_forth_is_not_full_sweep():
    n=CycleNavigator();c=clear();p=n.update(c,[0,0,0],0)
    for i,yaw in enumerate([1.,0.]*5):n.command(c,[0,0,yaw],p,i+1)
    assert n.sweep_rotation==pytest.approx(0) and n.phase=='sensor_sweep'


def test_goal_committed_despite_periodic_reselection_and_arrival():
    n=CycleNavigator();n.sweep_pending=None;c=clear()
    n.target=n.frontier=np.array([.5,0.]);n.locked=True
    n.select_frontier(c,[0,0,0],100)
    np.testing.assert_array_equal(n.target,[.5,0.])
    result=n.update(c,np.array([.48,0,0]),101)
    assert result['status']=='sensor_sweep' and n.target is None
    assert n.blocked([.5,0.],.05) and len(n.visited)==1


def test_progress_failure_blacklists_then_sweeps():
    n=CycleNavigator();n.sweep_pending=None;n.target=n.frontier=np.array([1.,0.]);n.locked=True
    n.failure(10,'controller_no_progress')
    assert n.blocked([1,0],.05) and n.sweep_pending and not n.failed and not n.locked
    assert n.update(clear(),np.zeros(3),10.2)['status']=='sensor_sweep'


def test_sweep_collision_stop_and_no_stale_velocity():
    n=CycleNavigator();c=clear();pose=np.zeros(3);plan=n.update(c,pose,0.)
    c.pose_clear=lambda p:False
    command=n.command(c,pose,plan,.2)
    assert not np.any(issued_twist(command)) and n.phase=='sensor_sweep'
    assert n.events[-1]['reason']=='sensor_sweep_collision_hold'


def test_information_goal_cannot_preempt_live_cycle(monkeypatch):
    a=make_mapper('r3',0,SEARCH,frontier_observation=OPTION,**ARGS)
    calls=[];monkeypatch.setattr(RecoveryMapper,'choose_information',lambda *args:calls.append(1))
    a.choose_information(20,clear());assert not calls
    a.navigator.sweep_pending=None;a.navigator.locked=True;a.choose_information(30,clear());assert not calls
    a.navigator.locked=False;a.choose_information(40,clear());assert calls==[1]


def test_graph_frame_change_preserves_sweep_yaw(monkeypatch):
    a=make_mapper('r3',0,SEARCH,frontier_observation=OPTION,**ARGS)
    n=a.navigator;n.sweep_last_yaw=1.;n.visited=[np.array([1.,0.])]
    def graph(self,t):self.map_to_odom=np.array([0.,0.,.3])
    monkeypatch.setattr(RecoveryMapper,'graph',graph)
    a.graph(20)
    assert n.sweep_last_yaw==pytest.approx(1.3)
    np.testing.assert_allclose(n.visited[0],[math.cos(.3),math.sin(.3)])


def test_bundle_changes_only_preregistered_fields():
    from scripts.run_active_wall_rotleft import frozen_bundle
    from scripts.run_active_frontier_cycle import bundle
    a,b=frozen_bundle('new-seed','a'*40),bundle('a'*40)
    assert b['case_cap_s']==180 and b['task']['seed']==45001
    assert b['options'].pop('frontier_observation')==OPTION
    b['task']['seed']=a['task']['seed']
    for k in ('execution_bundle_id','check','admission'):b[k]=a[k]
    b.pop('preregistration')
    assert a==b
