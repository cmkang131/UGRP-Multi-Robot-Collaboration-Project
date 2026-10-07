"""Offline evaluation geometry, and (later) detector adapter default equivalence."""
import importlib.util
from pathlib import Path
import sys
import json
import types
import numpy as np
import pytest
import cv2

CODE=Path(__file__).resolve().parents[1]/'experiments/2026-10-08-wall-contact-types/code'
def load_module(name):
    sys.path.insert(0,str(CODE))
    spec=importlib.util.spec_from_file_location('contact_types_'+name,CODE/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def test_actual_column_pixel_projection_roundtrip():
    common=load_module('common')
    from harness.active_camera import SEARCH,transform
    origin,rotation=transform(SEARCH)
    points=np.array([[1.,0.],[2.,.2]])
    uv=common.uv_of(points,SEARCH)
    rays=np.c_[uv,np.ones(2)]@np.linalg.inv(common.modules()[0].K).T@rotation.T
    xyz=origin-origin[2]*rays/rays[:,2,None]
    np.testing.assert_allclose(xyz[:,:2],points,atol=1e-12)

def test_evaluation_first_occluder_is_not_hidden_floor():
    m=load_module('diagnose');labels=m.Labels.__new__(m.Labels)
    labels.walls=np.array([[2.,0.,.025,1.]])
    labels.setup={'spawns':{'r3':[0,0,0]}}
    truth={'cyan_rotation':np.eye(3).ravel().tolist(),'cyan_xyz_m':[20,20,.1],'box_half_m':[.1,.1,.1]}
    surface,points=labels.surface(np.array([0.,0.,.23]),np.array([[1,0,-.02],[1,0,-1.]]),truth)
    assert surface.tolist()==['wall','floor']
    np.testing.assert_allclose(points[0,0],1.975)
    np.testing.assert_allclose(points[1,2],0)

def fixture():
    folder=Path(__file__).parent/'fixtures/wall_contact_types'
    frame=json.loads((folder/'frame.json').read_text())
    image=cv2.cvtColor(cv2.imread(str(folder/'dev326.jpg')),cv2.COLOR_BGR2RGB)
    return folder,image,{int(k):v for k,v in frame['commanded_servo'].items()}

def test_active_detector_off_nonempty_real_rgb_frozen_bytes():
    from harness.active_wall_vision import observe
    from harness.self_wall_segment_points import contact_points
    folder,image,servo=fixture()
    for name,fn,key in [('active_wall_vision_before',observe,'segments'),('segment_points_before',contact_points,'points')]:
        old=types.ModuleType(name);old.__file__=sys.modules[fn.__module__].__file__
        exec((folder/f'{name}.py.txt').read_text(),old.__dict__)
        original=getattr(old,fn.__name__)(image,servo)
        assert len(original[key])>0
        assert json.dumps(original).encode()==json.dumps(fn(image,servo)).encode()==json.dumps(fn(image,servo,wall_detector='off')).encode()
        with pytest.raises(ValueError,match='UNKNOWN'):fn(image,servo,wall_detector='bad')

def test_new_option_is_exact_frozen_appearance_algorithm():
    from harness.wall_contact_detector import detect,OPTION
    from harness.active_wall_vision import modules
    from harness.active_camera import transform
    folder,image,servo=fixture();mp,hfw,_=modules();origin,rotation=transform(servo)
    cm=mp.ColumnModel(tuple(sorted(servo.items())),0.,mp.column_positions(96,2),camera_transform=(origin,rotation))
    und=mp.undistort(cv2.cvtColor(image,cv2.COLOR_RGB2BGR))
    params={'floor_patch_max_m':.81,'run_step_window':3,'top_edge_px':4}
    old=hfw.detect(und,cm,params=params,loaded=False,wall_detector='floor_boundary_v1')
    new=detect(hfw,und,cm,params=params,loaded=False,wall_detector=OPTION)
    assert set(old)==set(new)
    assert all(old[k].tobytes()==new[k].tobytes() for k in old)
