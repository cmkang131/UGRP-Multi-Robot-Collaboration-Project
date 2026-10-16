from types import SimpleNamespace
import numpy as np
import pytest
from sim.ultrasonic_range import MujocoUltrasonic
from harness.ultrasonic_model import DEFAULT_SPEC,ray_pattern
from harness.e2e_sonar_frame import compose,VERSIONS


def sensor(option,yaw=0.):
    # Site defined by zaxis=(1,0,0): local +X is DOWN, +Z is body forward.
    R=np.array([[0.,0.,1.],[0.,1.,0.],[-1.,0.,0.]])
    c,s=np.cos(yaw),np.sin(yaw);R=np.array([[c,-s,0],[s,c,0],[0,0,1.]])@R
    return SimpleNamespace(site_id=0,site_frame=option,spec=DEFAULT_SPEC,
        data=SimpleNamespace(site_xmat=np.array([R.ravel()]),site_xpos=np.array([[.084,0.,.054]])))


@pytest.mark.parametrize('yaw',[0.,np.pi/2,np.pi])
def test_actual_pose_math_aims_entire_cone_forward_and_origin_at_face(yaw):
    old_origin,old_R=MujocoUltrasonic.pose(sensor('off',yaw))
    origin,R=MujocoUltrasonic.pose(sensor('site_z_v1',yaw))
    assert np.allclose(old_R[:,0],[0,0,-1])
    assert np.allclose(old_origin,[.084,0,.048])
    assert np.allclose(R[:,0],[np.cos(yaw),np.sin(yaw),0.])
    assert np.allclose(origin,[.084,0,.054]) and np.linalg.det(R)==pytest.approx(1.)
    rays,_=ray_pattern();world=rays@R.T
    assert np.all(world@R[:,0]>=np.cos(np.deg2rad(15.))-1e-12)


@pytest.mark.parametrize('option,parent',[('off',241),('range_v1',242),('range_wall_v1',243),('range_wall_slots_v1',244)])
def test_fixed_sonar_variants_preserve_parent_and_are_not_baseline(option,parent):
    b={'execution_bundle_id':f'e2e18-v{parent}','e2e_options':{'arm_clearance':option}}
    assert compose(b,'off')==() and b['execution_bundle_id']==f'e2e18-v{parent}'
    compose(b,'site_z_v1')
    assert b['execution_bundle_id']==f'e2e18-v{VERSIONS[option]}'
    assert not b['sonar_mount_interpretation']['old_results_inherited']
