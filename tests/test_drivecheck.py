"""No MuJoCo import/physics: evaluator namespace and quaternion contracts."""
import math
import numpy as np
from scripts.drivecheck import roller_wheel
from scripts.drivecheck_analyze import pose,tilt,delta


def test_physical_roller_namespace_excludes_visual_and_other_robots():
    # Names observed in the frozen scene. The initial recorder wrongly omitted v3.
    assert [roller_wheel(f'r1__v3_wheel_{w}_roller_7_body_contact') for w in ('fl','fr','rl','rr')]==[0,1,2,3]
    assert roller_wheel('r1__v3_wheel_fl_roller_7')==-1
    assert roller_wheel('r2__v3_wheel_fl_roller_7_body_contact')==-1


def test_tilted_quaternion_yaw_uses_projected_body_axis():
    # Rz(90deg) Ry(30deg); normalize deliberately nonunit stored quaternion.
    q=np.array([math.cos(math.pi/4)*math.cos(math.pi/12),
        -math.sin(math.pi/4)*math.sin(math.pi/12),math.cos(math.pi/4)*math.sin(math.pi/12),
        math.sin(math.pi/4)*math.cos(math.pi/12)])*2
    state=np.r_[0.,0.,0.,q]
    assert np.isclose(pose(state)[2],math.pi/2)
    assert np.isclose(tilt(state),30.)


def test_relative_translation_rotates_into_initial_heading():
    q=[math.cos(math.pi/4),0.,0.,math.sin(math.pi/4)]
    a=np.r_[1.,2.,0.,q];b=np.r_[1.,3.,0.,q]
    np.testing.assert_allclose(delta(a,b),[1.,0.,0.],atol=1e-14)
