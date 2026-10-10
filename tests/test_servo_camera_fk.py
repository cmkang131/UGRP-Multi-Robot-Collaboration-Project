"""Command-only TF composition, frozen off behavior, strict projection gate."""
import ast
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
import v3_confidence_replay as replay
from harness.servo_camera_fk import (
    camera_output,transform_from_commands,commanded_joints,MODEL,MODEL_SHA256)

SEARCH={1:2000,3:740,4:2320,5:1320,6:1500}


def test_fk_known_chain_and_pan_equivariance():
    # Independent planar link sum, shoulder origin from v3 structural drawing.
    _,j=commanded_joints(SEARCH)
    shoulder,elbow,wrist=j[5],j[4],j[3]
    pitch=shoulder+elbow+wrist
    ex=np.array([np.cos(pitch),0,np.sin(pitch)])
    ez=np.array([-np.sin(pitch),0,np.cos(pitch)])
    expected=np.array([.0482,0,.0325+.0605+.0347])
    expected+=.065*np.array([np.cos(shoulder),0,np.sin(shoulder)])
    expected+=.062*np.array([np.cos(shoulder+elbow),0,np.sin(shoulder+elbow)])
    expected+=.0529820099255583*ex+.0281521739130435*ez
    (o,r),reason=transform_from_commands(SEARCH,camera_pose='servo_fk_v1')
    assert reason=='servo_fk_nominal_unloaded'
    np.testing.assert_allclose(o,expected,atol=1e-12)
    assert abs(np.degrees(np.arcsin(r[2,2]))-(np.degrees(pitch)+10))<1e-10
    from harness.servo_camera_fk import axis_rotation
    pan=axis_rotation([0,0,1],np.radians(18))
    (oo,rr),_=transform_from_commands({**SEARCH,6:1700},camera_pose='servo_fk_v1')
    origin=np.array([.0482,0,0])
    np.testing.assert_allclose(oo,origin+pan@(o-origin),atol=1e-12)
    np.testing.assert_allclose(rr,pan@r,atol=1e-12)


def test_per_frame_commands_not_fixed_pose_and_scope():
    first,_=transform_from_commands(SEARCH,camera_pose='servo_fk_v1')
    next_,_=transform_from_commands({**SEARCH,3:807,4:1897,5:2187},camera_pose='servo_fk_v1')
    assert np.linalg.norm(first[0]-next_[0])>.01
    assert not np.allclose(first[1],next_[1])
    assert transform_from_commands({**SEARCH,1:1500},camera_pose='servo_fk_v1')[0] is None
    with pytest.raises(ValueError):
        transform_from_commands({**SEARCH,'qpos':[1,2,3]},camera_pose='servo_fk_v1')
    with pytest.raises(ValueError):
        transform_from_commands({**SEARCH,3:float('nan')},camera_pose='servo_fk_v1')
    with pytest.raises(ValueError):
        transform_from_commands(SEARCH,camera_pose='unknown')


def test_off_golden_transform_and_full_detection_bytes(tmp_path):
    raw=b'{"camera":"legacy","unchanged":true}\n'
    assert camera_output(raw) is raw
    assert transform_from_commands(None)==(None,'off')
    path='experiments/2026-10-05-ego-wall-map-probe/code/v3_confidence_replay.py'
    before=subprocess.check_output(['git','show','4bbaa79b:'+path],cwd=ROOT)
    oldfile=tmp_path/'before.py'
    oldfile.write_bytes(before)
    spec=importlib.util.spec_from_file_location('fk_legacy_replay',oldfile)
    legacy=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    for mode in ['off','v3_unloaded_extrinsic_v1']:
        a,ao,ar=legacy.geometry(SEARCH,mode)
        b,bo,br=replay.geometry(SEARCH,mode,camera_pose='off')
        assert ar==br and ao.tobytes()==bo.tobytes()
        for field in ('origin','_rot','q0','d','alpha','beta'):
            assert getattr(a,field).tobytes()==getattr(b,field).tobytes()
        # Nonempty scan/segment regression is also covered by frozen detector suite.
    new,offset,reason=replay.geometry(SEARCH,'off',camera_pose='servo_fk_v1')
    assert reason=='servo_fk_nominal_unloaded' and not offset.any()
    with pytest.raises(ValueError,match='CONFLICT'):
        replay.geometry(SEARCH,'v3_unloaded_extrinsic_v1',camera_pose='servo_fk_v1')


def test_geometry_frozen_and_runtime_has_no_truth_import():
    assert hashlib.sha256(MODEL.read_bytes()).hexdigest()==MODEL_SHA256
    source=(ROOT/'harness/servo_camera_fk.py').read_text()
    tree=ast.parse(source)
    imports=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    imports += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
    assert not any(any(x in name for x in ('mujoco','audit','evaluate','scene','openai','genai')) for name in imports)


def test_projection_gate_rejects_empty_or_unchanged_half_metre_error():
    sys.path.insert(0,str(ROOT/'experiments/2026-10-07-camera-pose-projection/code'))
    from evaluate_fk import gate
    assert not gate(dict(median=.5),dict(median=.5,p90=.6),300,300,300)['passed']
    assert not gate(dict(median=.5),dict(median=None,p90=None),0,0,0)['passed']
    assert not gate(dict(median=.5),dict(median=.05,p90=.1),300,280,280)['passed']
    assert gate(dict(median=.5),dict(median=.05,p90=.1),300,300,300)['passed']
