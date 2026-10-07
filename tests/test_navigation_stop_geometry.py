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


def test_v4_opt_in_legacy_bytes_and_nav2_outline_cell_difference():
    import pytest,subprocess
    from harness.public_navigation_outline import OutlineActor,OutlineCostmap,navigation_output_v4
    from harness.public_navigation.costmap import Costmap
    # Triangle-edge rasterization of an oriented rectangle: filled pixel vs edge.
    raw=np.zeros((25,25),np.uint8);raw[11,10]=254
    cm=Costmap(raw,[-1,-1]);new=OutlineCostmap(raw,[-1,-1])
    # General corner/unknown guards retain rejection.
    assert not new.pose_clear([.15,.25,0.])
    cm.raw[11,10]=255;cm.costs=cm.inflate()
    assert not OutlineCostmap(cm.raw,cm.origin).pose_clear([.15,.25,0.])
    payload=b'legacy off\x00\n'
    assert navigation_output_v4(payload) is payload
    with pytest.raises(ValueError):OutlineActor('own_frontier')
    a=OutlineActor('own_frontier',navigation='public_ros_v4')
    a.plan();assert isinstance(a.costmap,OutlineCostmap)
    for name in ('harness/public_navigation_persistent.py','harness/public_navigation_recovery.py',
                 'harness/public_navigation/costmap.py','experiments/2026-10-07-mapfree-navigation-persistence/code/run_persistent.py'):
        assert (ROOT/name).read_bytes()==subprocess.check_output(['git','show','b494873c:'+name],cwd=ROOT)


def test_v4_matches_nav2_boundary_raster_on_rotated_polygon():
    from harness.public_navigation_outline import OutlineCostmap
    from harness.public_navigation.costmap import Costmap
    import report
    rng=np.random.default_rng(409)
    raw=np.where(rng.random((30,30))<.10,254,0).astype(np.uint8)
    old=Costmap(raw,[-1.5,-1.5]);new=OutlineCostmap(raw,[-1.5,-1.5])
    for angle in np.linspace(-np.pi,np.pi,31):
        p=np.array([.31,.22,angle])
        assert new.pose_clear(p)==(not report.original_outline_collision(old,p))
    # Isolate the actual s5 first-rejection raster cell (full source in audit).
    raw=np.zeros((10,10),np.uint8);raw[4,4]=254
    pose=np.array([3.5218258383377905,.5006998370063818,-1.2604850427902354])
    old=Costmap(raw,[2.9,0]);new=OutlineCostmap(raw,[2.9,0])
    assert not old.pose_clear(pose) and new.pose_clear(pose)
