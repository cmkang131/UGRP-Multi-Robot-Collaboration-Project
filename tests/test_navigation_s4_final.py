"""Exact cell/geometry diagnosis; no physical or model runtime."""
import importlib.util
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('s4_diagnosis',ROOT/'experiments/2026-10-07-mapfree-s4-final/code/diagnose.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)


def test_cell_boundary_versus_padding_only_classification():
    from harness.public_navigation_outline import OutlineCostmap
    cm=OutlineCostmap(np.zeros((20,20),np.uint8),[-1,-1],.1)
    centre=d.transform([[.05,.05]],d.a.START)[0]
    rect=dict(center=centre.tolist(),half=[.01,.01],yaw=0,kind='wall')
    r=d.classify_cell((10,10),cm,[rect])
    assert r['classification']=='true_wall_center'
    shifted=dict(rect,center=(centre+np.array([.06,0])).tolist())
    assert d.classify_cell((10,10),cm,[shifted])['classification']=='wall_boundary_cell'
    far=dict(rect,center=(centre+np.array([.12,0])).tolist())
    assert d.classify_cell((10,10),cm,[far])['classification']=='raster_padding_only'


def test_rectangle_intersection_area_and_no_touch_area():
    assert abs(d.overlap(d.polygon([0,0],[.1,.1]),d.polygon([0,0],[.1,.1]))-.04)<1e-7
    assert d.overlap(d.polygon([0,0],[.1,.1]),d.polygon([.3,0],[.1,.1]))==0
