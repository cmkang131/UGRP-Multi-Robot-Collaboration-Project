import importlib.util
from pathlib import Path
import numpy as np
from harness.self_pose_graph import rebuild

spec=importlib.util.spec_from_file_location('cell_attribution',Path(__file__).resolve().parents[1]/'experiments/2026-10-08-wall-cell-attribution/code/diagnose.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_provenance_matches_weighted_rebuild_including_free_clamp_and_overlap():
    rows=[dict(t=i,frame_id=i,pose=[.01*i,0,0],camera=[0,0],
               segments=[[[1,-.5],[1,.5]],[[1.2,-.5],[1.2,.5]]],insertion_weights=[.4,.8]) for i in range(25)]
    grid,mass=m.provenance(rows)
    assert grid.export()['cells']==rebuild('r3',rows).export()['cells']
    assert any(v<0 for v in grid.cells.values())
    for k,v in grid.cells.items():
        if v>0:assert abs(sum(s['mass'] for s in mass[k])-v)<1e-10


def test_numpy_ray_first_hit_and_miss():
    d=m.first_box_hit(np.array([0.,0.,0.]),np.array([[1,.1,.1],[-1,.1,.1]]),[1,-1,-1],[2,1,1])
    assert d[0]==1 and np.isinf(d[1])
