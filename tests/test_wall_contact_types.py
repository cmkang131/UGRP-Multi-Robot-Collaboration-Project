"""Offline evaluation geometry, and (later) detector adapter default equivalence."""
import importlib.util
from pathlib import Path
import sys
import numpy as np

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
