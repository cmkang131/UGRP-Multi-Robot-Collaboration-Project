"""Offline contracts, unknown-space counterexamples and frozen-source tests."""
import ast
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np
import pytest

from harness.own_map_navigation import (NavigationOptions, OwnMapNavigator, ObservedGrid,
    Footprint, PAIR_FOOTPRINT, DoorMemory, astar, footprint_clearance, frontier_candidates)

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT/'experiments/2026-10-07-mapfree-explore'


def rectangle_grid():
    grid = ObservedGrid('r1')
    floor = [(x*.1+.05,y*.1+.05) for x in range(-10,21) for y in range(-10,11)]
    grid.observe(robot_id='r1',frame_id=1,pose=(0,0,0),floor_xy=floor)
    return grid


def test_off_preserves_real_legacy_bytes_and_identity():
    p = ROOT/'tests/fixtures/floor_goal/pre_goal_snapshot.json'
    raw = p.read_bytes()
    value = json.loads(raw)
    for option in [None,NavigationOptions(exploration='off',door_detection='off',partial_planning='off')]:
        nav = OwnMapNavigator('r1',option)
        assert nav.update(raw) is raw
        assert nav.update(value) is value
        assert nav.update(raw) == p.read_bytes()


def test_invalid_and_independent_options():
    with pytest.raises(ValueError):
        NavigationOptions(exploration='own_frontier_v1')
    with pytest.raises(ValueError):
        NavigationOptions(door_detection='own_gap_v0')
    nav = OwnMapNavigator('r1',NavigationOptions(door_detection='own_gap_v1'))
    assert nav.update(b'legacy',grid=rectangle_grid())['path_m']==[]


def test_floor_provenance_wall_does_not_carve_and_duplicate_peer_refused():
    grid = ObservedGrid('r1')
    grid.observe(robot_id='r1',frame_id=1,pose=(0,0,0),wall_xy=[[2.,0.]])
    assert grid.state((5,0))==0
    for kw in [dict(robot_id='r2',frame_id=2),dict(robot_id='r1',frame_id=1),
               dict(robot_id='r1',frame_id=2,floor_source='missing_wall')]:
        with pytest.raises(ValueError):
            grid.observe(pose=(0,0,0),**kw)
    grid.observe(robot_id='r1',frame_id=2,pose=(1,0,math.pi/2),floor_xy=[[.5,.05]])
    assert grid.state(grid.cell([.95,.5]))==-1


def test_astar_unknown_barrier_detour_and_no_diagonal_corner_cut():
    clear = np.ones((9,9),bool)
    clear[:8,4] = False
    path = astar(clear,(1,1),(7,1))
    assert path and max(y for x,y in path)==8
    clear[8,4] = False
    assert astar(clear,(1,1),(7,1)) is None
    diagonal = np.eye(2,dtype=bool)
    assert astar(diagonal,(0,0),(1,1)) is None


def test_whole_cargo_footprint_not_chassis_only():
    grid = rectangle_grid()
    # Thin horizontal known-free corridor: one chassis fits; pair rotation sweep does not.
    _,solo,_,lo = footprint_clearance(grid,Footprint(),.02)
    _,pair,_,_ = footprint_clearance(grid,PAIR_FOOTPRINT,.02)
    assert solo.sum()>pair.sum()
    assert PAIR_FOOTPRINT.cross_width([1.,0.],0)==1.25
    assert PAIR_FOOTPRINT.cross_width([0.,1.],0)==.4


def test_frontier_viewpoints_reachable_no_hidden_bounds():
    grid = rectangle_grid()
    opt = NavigationOptions(exploration='own_frontier_v1',partial_planning='own_astar_v1')
    candidates = frontier_candidates(grid,(0.,0.,0.),opt)
    assert candidates
    for c in candidates:
        assert c['gain_area_m2']>0
        assert all(grid.state(grid.cell(p))==-1 for p in c['path_m'])


def test_door_gap_needs_both_jambs_free_connection_and_width():
    grid = rectangle_grid()
    walls = [[1.05,y*.1+.05] for y in range(-10,11) if not -4<=y<=3]
    grid.observe(robot_id='r1',frame_id=2,pose=(0,0,0),wall_xy=walls)
    memory = DoorMemory('r1')
    first = memory.update(grid,(0,0,0))
    assert first and all(x['reason']=='jamb_reobserve' for x in first)
    grid.observe(robot_id='r1',frame_id=3,pose=(.1,0,0),wall_xy=np.array(walls)-[.1,0])
    again = memory.update(grid,(0,0,0))
    assert any(x['payload_clearance_feasible'] for x in again)
    cargo = memory.update(grid,(0,0,math.pi/2),PAIR_FOOTPRINT)
    assert all(not x['payload_clearance_feasible'] for x in cargo)
    assert all(not x['visually_confirmed_passage'] for x in cargo)


def test_replanning_new_obstacle_and_transport_exploration_refusal():
    g = rectangle_grid()
    nav = OwnMapNavigator('r1',NavigationOptions(exploration='own_frontier_v1',partial_planning='own_astar_v1'))
    assert nav.update(None,grid=g,carrying=True)['status']=='shared_carry_action_required'
    old = nav.update(None,grid=g)
    assert old['status']=='frontier'
    g.observe(robot_id='r1',frame_id=2,pose=(0,0,0),wall_xy=[[.45,y*.1+.05] for y in range(-10,11)])
    new = nav.update(None,grid=g)
    assert new['revision']==2
    assert all(p[0]<.45 for p in new['path_m'])


def test_sensor_joint_distribution_frozen_and_floor_v3_untouched():
    model = json.loads((EXP/'sensor-model.json').read_text())
    assert hashlib.sha256((EXP/'sensor-errors.npz').read_bytes()).hexdigest()==model['sensor_errors_sha256']
    data = np.load(EXP/'sensor-errors.npz')
    for split in ('development','confirmation'):
        a = data['wall_'+split]
        assert a.ndim==3 and a.shape[1:]==(96,4)
        assert .8<float((a[:,:,0]==1).mean())<=1
        assert np.nanmin(a[:,:,2])<0<np.nanmax(a[:,:,2])
    assert len(model['B_false_patches'])==14
    for rel in ['harness/floor_goal.py','experiments/2026-10-07-mapfree-goal-floor/v3-selection.json']:
        assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==model['sources'][rel]


def load_world():
    spec = importlib.util.spec_from_file_location('test_grid_world',EXP/'code/grid_world.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_2d_geometry_ray_occlusion_and_fov_no_engine_import():
    before = set(sys.modules)
    m = load_world()
    r = [dict(center=[1,0],half=[.05,1],yaw=0.)]
    assert m.ray_hits([0,0],np.array([0.,math.pi]),r).tolist()==pytest.approx([.95,4.])
    uv,v,_ = m.project(np.array([[-1,0],[1,0]]),m.SEARCH)
    assert not v[0] and v[1]
    assert 'mujoco' not in set(sys.modules)-before
    actor_tree = ast.parse((ROOT/'harness/own_map_navigation.py').read_text())
    imports = [n.module or '' for n in ast.walk(actor_tree) if isinstance(n,ast.ImportFrom)]
    assert not any('grid_world' in x or 'sim.' in x for x in imports)


def test_all_scenario_assets_resolve_without_scene_builder():
    m = load_world()
    layouts = [m.load_layout(i) for i in range(1,9)]
    assert len({x[1]['map_id'] for x in layouts})==3
    assert all(x[2] for x in layouts)


def test_json_serializable_native_cells_and_initial_static_baseline_path():
    g = rectangle_grid()
    json.dumps({'cells':[[*c,v] for c,v in g.odds.items()]},allow_nan=False)
    sys.path.insert(0,str(EXP/'code'))
    try:
        import run_grid
        w = run_grid.GridWorld(1,run_grid.STARTS['A'],1701,'development')
        g,target = run_grid.static_inputs(w)
        actor = run_grid.Actor('static_map',g,target)
        assert actor.plan()['path_m']
    finally:
        sys.path.remove(str(EXP/'code'))


def test_executor_does_not_shortcut_a_star_bend_or_read_truth():
    sys.path.insert(0,str(EXP/'code'))
    try:
        import run_grid
        actor = run_grid.Actor('own_frontier')
        # A one-cell elbow must not be replaced with the diagonal to its second successor.
        plan = {'status':'frontier','path_m':[[0.,0.],[.1,0.],[.1,.1]],'doors':[]}
        cmd = actor.command(plan)
        gain = np.asarray(run_grid.motion_profiles()['motion']['gain'])
        expected = gain@np.array([cmd['forward'],cmd['left'],cmd['turn']])
        assert abs(expected[1])<.001
        assert actor.static_goal is None
        assert not hasattr(actor,'world')
    finally:
        sys.path.remove(str(EXP/'code'))
