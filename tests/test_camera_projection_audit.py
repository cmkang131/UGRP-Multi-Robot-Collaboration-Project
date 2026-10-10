"""Evaluation transform convention and single-factor counterfactual tests."""
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments/2026-10-07-camera-pose-projection/code'))
from audit import angles,rotation,actual_camera,rz,swap,project


def test_camera_angles_and_single_factor_roundtrip():
    a=np.radians([31,-25,4])
    r=rotation(a)
    np.testing.assert_allclose(angles(r),a,atol=1e-12)
    first=(np.array([.1,.2,.3]),r)
    second=(np.array([.2,-.3,.5]),rotation(np.radians([-20,-35,-3])))
    for i in range(6):
        x=swap(first,second,i)
        xo,xa=x[0],angles(x[1])
        expected=np.r_[first[0],angles(first[1])]
        expected[i]=np.r_[second[0],angles(second[1])][i]
        np.testing.assert_allclose(np.r_[xo,xa],expected,atol=1e-12)


def test_world_camera_to_floor_heading_does_not_subtract_base_height_twice():
    yaw=.7
    origin=np.array([.1,.02,.25])
    rot=rotation(np.radians([15,-20,3]))
    body=dict(robot_xyz_m=[2,3,.033],robot_yaw_rad=yaw)
    row=dict(camera_cached_xyz_m=([2,3,0]+rz(yaw)@origin).tolist(),
             camera_cached_optical_rotation=(rz(yaw)@rot).tolist())
    o,r=actual_camera(row,body)
    np.testing.assert_allclose(o,origin,atol=1e-12)
    np.testing.assert_allclose(r,rot,atol=1e-12)


def test_ground_intersection_positive_depth_and_fixed_denominator_range():
    o=np.array([0.,0.,.2])
    # Optical centre ray intersects x=.2/tan(20deg); 4m is reported separately.
    from audit import old
    uv=np.array([[old.mp.K[0,2],old.mp.K[1,2]]])
    xy,valid,distance=project(uv,o,rotation([0,np.radians(-20),0]))
    assert valid[0]
    np.testing.assert_allclose(xy,[[.2/np.tan(np.radians(20)),0]],atol=1e-12)
    assert not project(uv,o,rotation([0,np.radians(20),0]))[1][0]
