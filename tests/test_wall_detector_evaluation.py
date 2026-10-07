"""Offline scorer denominators and ray conventions, no simulator imports."""
import importlib.util
from pathlib import Path
import numpy as np

path=Path(__file__).resolve().parents[1]/'experiments/2026-10-07-wall-floor-boundary/code/evaluate.py'
spec=importlib.util.spec_from_file_location('floor_evaluation',path)
ev=importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def test_ray_plane_positive_depth_and_range():
    # Camera looks down, optical x = body x, optical y = -body y.
    xyz,r,ok=ev.project([[0,0],[1,0],[5,0]],np.array([0.,0.,1.]),np.diag([1.,-1.,-1.]),np.eye(3))
    assert ok.tolist()==[True,True,False]
    np.testing.assert_allclose(xyz,[[0,0],[1,0],[5,0]])
    assert not ev.project([[0,0]],np.array([0.,0.,1.]),np.eye(3),np.eye(3))[2].any()


def test_polylines_do_not_bridge_doorway():
    rows,ignore=ev.annotation_rows(dict(polylines=[[[0,1],[2,3]],[[4,8],[5,9]]],ignore=[[3,3]]),np.arange(6))
    np.testing.assert_allclose(rows[[0,1,2,4,5]],[1,2,3,8,9])
    assert np.isnan(rows[3]) and ignore.tolist()==[False,False,False,True,False,False]


def test_precision_recall_have_separate_distance_denominators_and_empty_is_na():
    pred=np.array([True,True,False])
    labels=np.array([True,False,True])
    pixel=np.array([True,False,False])
    metric=np.array([False,False,False])
    counts=ev.measures(pred,labels,pixel,metric,np.array([1.9,2.5,np.nan]),
                       np.array([2.1,np.nan,3.5]),np.array([.2,1.,np.nan]))
    assert ev.finalize(counts['all'])['pixel_precision']==.5
    assert ev.finalize(counts['all'])['pixel_recall']==.5
    assert ev.finalize(counts['all'])['metric_recall']==0
    assert ev.finalize(counts['0-2m'])['pixel_precision']==1
    assert ev.finalize(counts['0-2m'])['pixel_recall'] is None
    assert ev.finalize(counts['2-3m'])['pixel_precision']==0
    assert ev.finalize(counts['2-3m'])['pixel_recall']==1
    assert ev.finalize(counts['3-4m'])['metric_precision'] is None
    assert ev.finalize(counts['3-4m'])['metric_recall']==0
