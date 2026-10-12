import json
import numpy as np
import pytest
from harness.active_camera import SEARCH
from harness.active_wall_recovery import make_mapper
from harness.public_navigation_resolution import RESOLUTION
from harness.public_navigation_unknown import from_observed_grid


def actor(option='off'):
    return make_mapper('r3',1.3,SEARCH,active_mapping='frontier_rbpf_v1',
        active_loop='information_gain_v1',active_recovery='nav2_frontier_v1',navigation_map=option)


def test_off_same_output_bytes():
    a=actor();b=make_mapper('r3',1.3,SEARCH,active_mapping='frontier_rbpf_v1',
        active_loop='information_gain_v1',active_recovery='nav2_frontier_v1')
    obs=dict(segments=[],features=[],camera=[.124,0.],floor_xy=[[.5,.1],[.5,-.1]])
    for t in [3.3,3.5,3.7]:
        kw=dict(robot_id='r3',t=t,frame_id=round(t*10),rgb=np.zeros((480,640,3),np.uint8),servo=SEARCH,observation=obs)
        assert json.dumps(a.receive(**kw))==json.dumps(b.receive(**kw))
    assert a.grid.resolution==.1
    with pytest.raises(ValueError,match='NAVIGATION_MAP'):actor('invalid')


def test_navigation_native_resolution_survives_reset_and_graph(monkeypatch):
    a=actor('public_ros_v8')
    assert a.grid.resolution==RESOLUTION==.05 and a.memory.self_map.resolution_m==.1
    frame=dict(t=3.3,frame_id=11,segments=[],features=[],camera=[.124,0.],floor_xy=[[.5,.1],[.5,-.1]])
    a.frames=[frame];a.poses=[dict(t=3.3,pose=[0.,0.,0.],robot_id='r3')]
    a.clear_navigation(3.3)
    assert a.grid.resolution==.05 and a.grid.odds
    a.memory.self_map.ledger=[{},{}]
    monkeypatch.setattr(a.memory,'finalize_pose_graph',lambda poses:dict(poses=poses,diagnostics={}))
    a.graph(3.3)
    assert a.grid.resolution==.05 and a.grid.odds and a.memory.self_map.resolution_m==.1


def test_active_information_uses_costmap_units(monkeypatch):
    a=actor('public_ros_v8');a.active_loop='information_gain_v1'
    a.next_gain=0;seen=[]
    monkeypatch.setattr(a.navigator.core,'frontiers',lambda raw,origin,res,xy:seen.append(res) or [])
    cost=from_observed_grid(a.grid,a.pose,a.latest,set())
    a.choose_information(2.,cost)
    assert seen==[.05]


def test_frozen_new_bundle_only_seed_and_navigation():
    from scripts.run_active_wall_nav2 import frozen_bundle
    from scripts.run_active_wall_recovery import frozen_bundle as old
    a,b=old('new-seed','f'*40),frozen_bundle('new-seed','f'*40)
    assert b['options'].pop('navigation_map')=='public_ros_v8'
    assert b['task']['seed']==31001
    b['task']['seed']=a['task']['seed']
    for k in ('execution_bundle_id','check'):b[k]=a[k]
    assert a==b
