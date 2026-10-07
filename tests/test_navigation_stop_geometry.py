"""Evaluation-only geometry certificates and preservation of navigation semantics."""
import importlib.util
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('stop_audit',ROOT/'experiments/2026-10-07-mapfree-stop-geometry/code/audit.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


def test_disk_distance_and_continuous_certificate():
    rects=[dict(center=[0.,0.],half=[.1,.2],yaw=0.)]
    np.testing.assert_allclose(a.disk_margin([[.3,0],[0,0]],rects,[-2,2,-2,2],.05),[.15,-.15])
    cert=a.path_certificate([[.3,-1],[.3,1]],rects,[-2,2,-2,2],.05)
    assert .148<cert['continuous_clearance_lower_m']<=.15
    assert a.path_certificate([[0,-1],[0,1]],rects,[-2,2,-2,2],.05)['continuous_clearance_lower_m']<0


def test_route_witness_and_impossibility_not_overclaimed():
    rects=[dict(center=[0.,.8],half=[.1,.55],yaw=0.),dict(center=[0.,-.8],half=[.1,.55],yaw=0.)]
    w=a.witness([-.6,0],[.6,0],rects,[-1,1,-1.4,1.4],a.HALF)
    assert w['found'] and w['continuous_clearance_lower_m']>0
    assert a.rectangle_contacts([0,0,0],rects,[-1,1,-1.4,1.4],a.HALF)==[]
    bad=a.witness([0,.2],[.6,0],rects,[-1,1,-1.4,1.4],a.HALF)
    assert not bad['found'] and 'not_impossibility_proof' in bad['reason']


def test_inflation_outer_radius_is_soft_not_required_door_width():
    from harness.public_navigation.costmap import Costmap,HALF
    raw=np.zeros((30,30),np.uint8);raw[10,:]=254
    cm=Costmap(raw,[-1.5,-1.5])
    assert 0<cm.costs[13,15]<253
    assert cm.costs[11,15]==253
    assert 2*np.linalg.norm(HALF)<.5
    assert cm.pose_clear([.05,-.05,0])


def test_replay_own_pose_without_mutating_live_odometry_property():
    from harness.public_navigation_persistent import PersistentActor
    actor=PersistentActor('own_frontier',navigation='public_ros_v3')
    log=dict(t=2.,pose_odom=[1.,0.,0.],observation=dict(robot_id='r1',frame_id=0,
        floor_xy=[[.05,.05]],wall_xy=[[.25,.05]],floor_source='floor_visible'))
    a.replay_observation(actor,log)
    assert actor.latest[(12,0)]
    assert actor.grid.odds[(12,0)]>0


def test_oriented_prefix_clearance_certificate_and_original_outline():
    import sys
    sys.path.insert(0,str(ROOT/'experiments/2026-10-07-mapfree-stop-geometry/code'))
    from report import rectangle_certificate,original_outline_collision
    rects=[dict(center=[0.,0.],half=[.1,.2],yaw=0.)]
    cert=rectangle_certificate([[.3,-.1,0],[.3,.1,.1]],rects,[-2,2,-2,2],a.HALF)
    assert cert['continuous_clearance_lower_m']>0
    assert rectangle_certificate([[.2,0,0],[.05,0,0]],rects,[-2,2,-2,2],a.HALF)['continuous_clearance_lower_m']<0
    from harness.public_navigation.costmap import Costmap
    raw=np.zeros((20,20),np.uint8);raw[10,11]=254
    assert original_outline_collision(Costmap(raw,[-1,-1]),np.array([0,0,0]))
