"""Pinned S2 geometry reuse and GT-free prediction boundary (no runtime actor)."""
import ast
import copy
from pathlib import Path
import sys
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'experiments/2026-10-07-s2-projection-comparison/code'),
              str(ROOT/'experiments/2026-10-07-camera-pose-projection/code')]
import s2_path
import audit as a

SEARCH={1:2000,3:740,4:2320,5:1320,6:1500}


def test_original_table_and_runtime_path_remain_identical_unloaded():
    table,models=s2_path.models()
    original=a.old.calibration()['camera_models']['unloaded']
    assert len(original)==21 and len(models['unloaded'])==22
    assert all(models['unloaded'][key]==record for key,record in original.items())
    cm=s2_path.column_model_factory(a.old.mp,a.COLS)(SEARCH)
    old,_,_=a.old.geometry(SEARCH,'v3_unloaded_extrinsic_v1')
    for key in ('origin','_rot','q0','d','alpha','beta','gamma'):
        assert getattr(cm,key).tobytes()==getattr(old,key).tobytes()
    assert set(models['unloaded'])-set(original)=={'600,2200,1400,1500'}


def test_loaded_sag_is_not_applied_to_unloaded_and_no_input_mutation():
    table,models=s2_path.models()
    before=copy.deepcopy(table)
    key='600,2200,1400,1500'
    assert models['unloaded'][key]==table['camera_models']['unloaded'][key]
    assert models['loaded'][key]['origin_m']==models['unloaded'][key]['origin_m']
    angle=-.02711
    delta=np.array([[1,0,0],[0,np.cos(angle),-np.sin(angle)],[0,np.sin(angle),np.cos(angle)]])
    np.testing.assert_array_equal(models['loaded'][key]['rotation'],np.array(models['unloaded'][key]['rotation'])@delta)
    assert table==before
    # Missing posture is not approximated/interpolated from GT.
    with pytest.raises(ValueError,match='UNMEASURED'):
        s2_path.column_model_factory(a.old.mp,a.COLS)({**SEARCH,3:741})


def test_same_pixels_column_projection_matches_ray_plane_and_pan():
    factory=s2_path.column_model_factory(a.old.mp,a.COLS)
    table,models=s2_path.models()
    for key in ['740,2320,1320,1500','1072,2400,1482,1230']:
        servo=dict(zip((3,4,5,6),map(int,key.split(','))))
        cm=factory(servo)
        origin,rotation=np.array(a.floor_camera(models['unloaded'][key])['origin_m']),np.array(a.floor_camera(models['unloaded'][key])['rotation'])
        yaw=table['pan_base_yaw']['unloaded']*(servo[6]-1500)
        np.testing.assert_allclose(cm.origin,a.rz(yaw)@origin,atol=1e-12)
        np.testing.assert_allclose(cm._rot,a.rz(yaw)@rotation,atol=1e-12)
        rows=np.linspace(340,450,len(a.COLS))
        xy,ok,_=a.project(np.c_[a.COLS,rows],cm.origin,cm._rot)
        assert ok.all()
        np.testing.assert_allclose(cm.floor_point(cm.t_of_row(rows)),xy,atol=1e-12)


def test_prediction_path_has_no_truth_or_simulator_construction():
    s2_path.verify_sources()
    tree=ast.parse((s2_path.EXP/'code/s2_path.py').read_text())
    names=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    names += [x.name for n in ast.walk(tree) if isinstance(n,ast.Import) for x in n.names]
    assert not any(x.startswith(('mujoco','openai','genai')) for x in names)
    assert 'eval_only' not in (s2_path.EXP/'code/s2_path.py').read_text()
    # Source AST copies cannot silently become modified "equivalent" math.
    src=ast.parse((s2_path.EXP/'sources/vision_pose_source_highpose.py').read_text())
    f=next(n for n in ast.walk(src) if isinstance(n,ast.FunctionDef) and n.name=='column_model_for')
    factory=s2_path.column_model_factory(a.old.mp,a.COLS)
    assert factory.__code__.co_firstlineno==f.lineno
    assert factory.__code__.co_filename.endswith('sources/vision_pose_source_highpose.py')
