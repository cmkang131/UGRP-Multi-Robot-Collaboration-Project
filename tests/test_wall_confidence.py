"""No simulation: fixed calibration, own-only evidence and signed ray updates."""
import json
from pathlib import Path
import sys
import numpy as np
import pytest
from harness.wall_camera_calibration import camera_transform,calibration
from harness.wall_confidence import confidence,weighted_insert
from harness.self_odom_grid import OdomGrid

FEATURE={'height_m':.2,'fy':622.,'contrast':30.,'band_std':1.,'sharpness':30.,'body_settling':1.}
SEG=np.array([[1.,-.2],[1.,.2]])

def test_calibration_compose_once_and_loaded_unknown_fail_closed():
    assert camera_transform(object())==(None,'off')
    key=next(iter(calibration()['camera_models']['unloaded']))
    s=dict(zip((3,4,5,6),map(int,key.split(','))))|{1:2000}
    (o,r),reason=camera_transform(s,wall_camera_calibration='v3_unloaded_extrinsic_v1')
    entry=calibration()['camera_models']['unloaded'][key]
    np.testing.assert_allclose(o,np.array(entry['origin_m'])+[0,0,.0325])
    np.testing.assert_allclose(r,entry['rotation'])
    assert reason=='calibrated_unloaded'
    for bad in [s|{1:1500},s|{3:1}]:
        assert camera_transform(bad,wall_camera_calibration='v3_unloaded_extrinsic_v1')[0] is None


def test_factors_decrease_with_uncertainty_range_and_low_edge_quality():
    def w(seg=SEG,f=FEATURE,cov=None):
        return confidence(seg,[0.,0.],f,np.zeros((3,3)) if cov is None else cov)['weight']
    reference=w()
    assert 0<reference<1
    assert w(SEG*3)<reference
    assert w(cov=np.diag([.1,.1,.01]))<reference
    assert w(f=FEATURE|{'sharpness':0.})==0
    assert w(f=FEATURE|{'contrast':5.})<reference
    assert w(f=FEATURE|{'body_settling':.5})==reference*.5
    assert w(np.array([[.5,0.],[1.5,0.]]))==0
    with pytest.raises(ValueError): w(cov=-np.eye(3))


def test_weighted_free_carving_and_once_per_frame_hit_precedence():
    legacy,weighted=OdomGrid('r1'),OdomGrid('r1')
    legacy.insert([0.,0.],[SEG])
    weighted_insert(weighted,[0.,0.],[SEG],[1.])
    assert legacy.export()==weighted.export()
    half=OdomGrid('r1')
    weighted_insert(half,[0.,0.],[SEG,SEG],[.2,.5])
    assert all(v==legacy.cells[k]*.5 for k,v in half.cells.items())
    assert any(v<0 for v in half.cells.values())
    hit=(10,0)
    before=half.cells[hit]
    weighted_insert(half,[0.,0.],[SEG*2],[1.])
    assert half.cells[hit]<before
