"""No dynamics: homogeneous transforms, own-command equivalence, CV/MJ axes."""
from pathlib import Path
import ast
import importlib.util
import numpy as np
from scipy.spatial.transform import Rotation

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'experiments/2026-10-07-camera-frame-audit/code/kinematics_audit.py'
spec=importlib.util.spec_from_file_location('frame_audit',PATH)
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_v1_chain_at_identical_command_angles_and_pan_convention():
    from harness.servo_camera_fk import commanded_joints,transform_from_commands
    for pan in (1300,1500,1700):
        servo={1:2000,3:740,4:2320,5:1320,6:pan}
        q=commanded_joints(servo)[1]
        origin,rotation=transform_from_commands(servo,camera_pose='servo_fk_v1')[0]
        t=audit.chain(q)['camera_cv']
        np.testing.assert_array_equal(t[:3,3],origin)
        np.testing.assert_array_equal(t[:3,:3],rotation)
        assert np.sign(np.arctan2(rotation[1,2],rotation[0,2]))==np.sign(pan-1500)


def test_positive_yaw_optical_axes_projection_and_exact_dlt():
    from harness import wall_parallax as p
    from harness.servo_camera_fk import transform_from_commands
    origin,rotation=transform_from_commands({1:2000,3:740,4:2320,5:1320,6:1500},camera_pose='servo_fk_v1')[0]
    k=np.array([[600.,0,300.],[0,610.,220.],[0,0,1.]])
    poses=(np.array([.3,-.2,.2]),np.array([.3,-.05,.25]))
    xyz=np.array([1.,0.,0.])
    uv=[]
    for pose in poses:
        o,r=p.camera(pose,origin,rotation)
        v=k@r.T@(xyz-o)
        uv.append(v[:2]/v[2])
        t=audit.transform(o,r)
        np.testing.assert_allclose(np.linalg.inv(t)@np.r_[xyz,1.],np.r_[r.T@(xyz-o),1.],atol=1e-14)
    np.testing.assert_allclose(p.solve(*uv,*poses,origin,rotation,k),p.rz(poses[1][2]).T@(xyz-[*poses[1][:2],0.]),atol=1e-12)
    np.testing.assert_allclose(p.rz(np.pi/2)@[1.,0.,0.],[0.,1.,0.],atol=1e-14)
    # OpenCV u goes right = body -y. v goes down = toward ground.
    assert rotation[1,0]<0 and rotation[2,1]<0 and rotation[0,2]>0


def test_audit_never_steps_or_renders_and_legacy_source_is_not_mutated():
    tree=ast.parse(PATH.read_text())
    calls={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
    assert not calls & {'mj_step','mj_step1','mj_step2','mj_forward','Renderer','render'}
    assert {'mj_kinematics','mj_camlight'}<=calls
    from harness.servo_camera_fk import camera_output
    from harness.wall_parallax import detect
    raw=b'{"old": "bytes"}\n'
    assert camera_output(raw) is raw and detect(raw) is raw


def test_registered_grid_is_fixed_and_contains_general_base_attitudes():
    grid=list(audit.pose_grid())
    assert len(grid)==21*9*5
    assert len({tuple(r['rpy']) for r in grid})==5
    assert {r['joint'] for r in grid}=={None,3,4,5,6}
