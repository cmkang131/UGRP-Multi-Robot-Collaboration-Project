"""No dynamics/models: frozen off bytes, calibrated axes and abstention cases."""
import ast
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'experiments/2026-10-07-camera-pose-projection/code'),
              str(ROOT/'experiments/2026-10-07-online-camera-pitch/code')]
import audit as a
from harness import online_camera_pitch as p
from conditions import load_class,kinematics


def test_vendor_bytes_and_allowed_input_signature():
    dest=ROOT/'harness/vendor/lu_vp'
    manifest=json.loads((dest/'UPSTREAM.json').read_text())
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((dest/name).read_bytes()).hexdigest()==digest
    assert list(inspect.signature(p.correct_rotation).parameters)==[
        'undistorted_bgr','intrinsics','nominal_rotation','camera_pitch']
    source=inspect.getsource(p)
    assert not any(x in source for x in ('eval_only','robot_xyz_m','camera_cached','mujoco'))


def test_off_identity_without_image_or_intrinsic_read():
    rotation=object()
    assert p.correct_rotation(object(),object(),rotation)[0] is rotation
    with pytest.raises(ValueError,match='UNKNOWN_CAMERA_PITCH'):
        p.correct_rotation(None,None,rotation,camera_pitch='bad')


def test_projection_pitch_sign_with_nonzero_roll_and_yaw():
    for yaw,pitch,roll in [(17,-19,3),(-80,-32,-5),(120,12,6)]:
        true=a.rotation(np.radians([yaw,pitch,roll]))
        nominal=a.rotation(np.radians([yaw,pitch+2,roll]))
        recovered=p.rotation_with_pitch(nominal,true.T@np.array([0.,0.,1.]))
        np.testing.assert_allclose(recovered,true,atol=1e-12)
        assert np.linalg.det(recovered)==pytest.approx(1.)


def test_degenerate_images_abstain_without_entering_upstream_loop(monkeypatch):
    import cv2
    rotation=a.rotation(np.radians([0,-20,0]))
    im=np.zeros((480,640,3),np.uint8)
    r,m=p.correct_rotation(im,a.old.mp.K,rotation,camera_pitch=p.OPTION)
    assert r is rotation and m['reason']=='no_lines'
    class Detector:
        def detect(self,image):
            return (np.array([[[10.,10.,100.,10.]],[[10.,20.,100.,20.]]],np.float32),)
    monkeypatch.setattr(cv2,'createLineSegmentDetector',lambda _:Detector())
    r,m=p.correct_rotation(im,a.old.mp.K,rotation,camera_pitch=p.OPTION)
    assert r is rotation and m['reason']=='all_parallel'


def test_off_geometry_bytes_against_prechange_git_function():
    name='experiments/2026-10-05-ego-wall-map-probe/code/v3_confidence_replay.py'
    source=subprocess.check_output(['git','show','d857d79b:'+name],text=True,cwd=ROOT)
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='geometry')
    namespace=dict(a.old.__dict__)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<frozen d857d79b>','exec'),namespace)
    for mode,camera_pose in [('off','off'),('v3_unloaded_extrinsic_v1','off'),('off','servo_fk_v1')]:
        for key in a.old.calibration()['camera_models']['unloaded']:
            servo={1:2000,**dict(zip((3,4,5,6),map(int,key.split(','))))}
            before=namespace['geometry'](servo,mode,camera_pose=camera_pose)
            for kwargs in ({},{'camera_pitch':'off','own_bgr':object()}):
                after=a.old.geometry(servo,mode,camera_pose=camera_pose,**kwargs)
                assert before[2]==after[2]
                if before[0] is None:
                    assert after[0] is None
                    continue
                assert before[1].tobytes()==after[1].tobytes()
                for field in ('origin','_rot','q0','d','alpha','beta','gamma'):
                    assert getattr(before[0],field).tobytes()==getattr(after[0],field).tobytes()
                rows=np.linspace(340,450,len(a.COLS))
                assert before[0].floor_point(before[0].t_of_row(rows)).tobytes()==after[0].floor_point(after[0].t_of_row(rows)).tobytes()


def test_evaluation_load_and_motion_labels_are_not_command_truth():
    assert load_class(dict(finger_contacts=[True,True],cyan_min_z_m=.1))=='held_airborne'
    assert load_class(dict(finger_contacts=[True,False],cyan_min_z_m=.1))=='ambiguous'
    assert load_class(dict(finger_contacts=[False,False],cyan_min_z_m=0))=='unloaded_ground'
    rows=[dict(t=t,robot_xyz_m=[.5*t*t,0,0],robot_yaw_rad=0) for t in [0.,1.,2.,3.,4.]]
    v,dv,w=kinematics(rows)
    assert v[2]==pytest.approx(2.) and dv[2]==pytest.approx(1.)
    assert not w.any()


def test_real_lsd_to_upstream_voting_on_projected_manhattan_lines():
    import cv2
    image=np.zeros((480,640,3),np.uint8)
    k=np.array([[450.,0.,320.],[0.,450.,240.],[0.,0.,1.]])
    true=a.rotation(np.radians([20.,-20.,0.]))
    camera=np.array([0.,0.,.4])
    # Fixed wireframe fixture: no renderer, labels or external images.
    for x in [1.,1.5,2.,3.]:
        for y in [-1.,-.5,0.,.5,1.]:
            pairs=[([x,y,0.],[x,y,1.]),([x,y,0.],[x+1.,y,0.]),([x,y,0.],[x,y+.5,0.])]
            for first,second in pairs:
                points=(np.array([first,second])-camera)@true
                if np.any(points[:,2]<=0):continue
                uv=points@k.T
                uv=np.rint(uv[:,:2]/uv[:,2:]).astype(int)
                cv2.line(image,tuple(uv[0]),tuple(uv[1]),(255,255,255),2)
    result,meta=p.correct_rotation(image,k,true,camera_pitch=p.OPTION)
    assert meta['lines']>=10
    assert 'vps' in meta and np.isfinite(result).all()
    # Exercise actual OpenCV return format through the pinned full algorithm.
    assert meta['accepted'],meta
    assert abs(np.degrees(a.angles(result)[1])+20.) < 3.
