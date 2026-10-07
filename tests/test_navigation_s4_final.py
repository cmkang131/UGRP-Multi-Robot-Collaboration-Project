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


def test_resolution_option_preserves_off_and_original_paths():
    import pytest,subprocess
    from harness.public_navigation_resolution import ResolutionActor,navigation_output_v5,authored_inputs
    from harness.own_map_navigation import ObservedGrid
    blob=b'legacy off\0\n'
    assert navigation_output_v5(blob) is blob
    with pytest.raises(ValueError):ResolutionActor('own_frontier')
    with pytest.raises(ValueError):ResolutionActor('static_map',ObservedGrid('r1'),[0,0],navigation='public_ros_v5')
    actor=ResolutionActor('own_frontier',navigation='public_ros_v5')
    assert actor.grid.resolution==.05
    for name in ['harness/public_navigation_outline.py','harness/public_navigation_persistent.py',
                 'harness/public_navigation/costmap.py','experiments/2026-10-07-mapfree-explore/code/run_grid.py']:
        assert (ROOT/name).read_bytes()==subprocess.check_output(['git','show','69054a84:'+name],cwd=ROOT)
    static=dict(bounds_m=[-1,1,-1,1],obstacles=[dict(center_m=[.4,0],half_extents_m=[.025,.5])],
                regions=dict(zone_B=dict(center_m=[.8,0])))
    grid,goal=authored_inputs(static,np.array([.1,.2,.3]))
    np.testing.assert_allclose(d.transform([goal],[.1,.2,.3])[0],[.8,0],atol=1e-12)
    assert grid.resolution==.05 and any(v>0 for v in grid.odds.values())
    # Raster occupies a half-cell margin, not the old fixed .05m at every resolution.
    grid,_=authored_inputs(static,np.zeros(3))
    assert grid.odds[(6,0)]<0 and grid.odds[(7,0)]>0


def test_frontier_aborted_moves_on_static_goal_does_not_become_frontier():
    from harness.public_navigation_persistent import PersistentNavigator
    from harness.public_navigation_outline import OutlineCostmap
    from types import SimpleNamespace
    nav=PersistentNavigator()
    nav.frontier=np.array([0.,0.]);nav.target=np.array([-.1,0.])
    nav.action_failed(0.,'round_robin_exhausted')
    assert not nav.failed and not nav.finished and len(nav.blacklist)==1
    nav.core=SimpleNamespace(frontiers=lambda *_:[np.array([0.,0.,0.,0.,1.]),np.array([1.,1.,0.,0.,2.])])
    nav.plan_to=lambda cm,pose,target:[list(pose[:2]),list(target)]
    cm=OutlineCostmap(np.zeros((50,50),np.uint8),[-1,-1],.05)
    nav.select_frontier(cm,np.zeros(3),1.)
    np.testing.assert_array_equal(nav.frontier,[1.,1.])
    assert not nav.finished
    nav.action_failed(2.,'round_robin_exhausted')
    nav.select_frontier(cm,np.zeros(3),3.)
    assert nav.finished
    static=PersistentNavigator();static.static_mode=True
    static.action_failed(0.,'round_robin_exhausted')
    assert static.failed and not static.blacklist


def test_grid_output_metadata_matches_resolution_without_rewriting_cells():
    import sys
    sys.path.insert(0,str(ROOT/'experiments/2026-10-07-mapfree-s4-final/code'))
    from run_resolution import serialized_grid
    original=dict(resolution_m=.1,cells=[[1,2,4.]])
    new=serialized_grid(original)
    assert original['resolution_m']==.1 and new['resolution_m']==.05
    assert new['cells'] is original['cells']
