"""Actual route dispatch across a clipped planner window, without physics."""
import copy
import numpy as np
import pytest
from tests.test_e2e18_route_guard import goal,route
from harness.e2e_route_extent import GoalEnvelopeView
from harness.e2e_route_coverage import map_completed
from harness.own_map_navigation import ObservedGrid
from harness.zone_study_contract import ContractViolation


def cropped_goal():
    g=goal();g.e2e_route_coverage='native_v1';g.e2e_carrier_axes='beam_v1'
    grid=ObservedGrid('r1',.1)
    grid.observe(robot_id='r1',frame_id=1,pose=[0.,0.,0.],floor_xy=[(x/10+.05,y/10+.05) for x in range(-8,8) for y in range(-8,8)])
    g.explorer.grid=grid
    return g


def test_real_route_reaches_own_goal_outside_storage_bounds_without_changing_map():
    g=cropped_goal();grid=g.explorer.grid;before=copy.deepcopy(vars(grid))
    with pytest.raises(ContractViolation,match='GRID_ROUTE'):route(g,.3)
    assert g.e2e_route_diagnostics['nominal_footprint_cells']['target']['outside']>0
    g.e2e_route_extent='goal_envelope_v1';packet=route(g,.3)
    assert packet['route']['waypoints'][-1]==pytest.approx([2.,0.])
    assert not packet['observed_coverage_complete']
    assert g.e2e_route_diagnostics['planning_extent']['added_unknown_cells']>0
    assert g.e2e_route_diagnostics['attempts'][-1]['target_clear']
    assert not map_completed([dict(event='own_map_B_route_generated',observed_coverage_complete=False)])
    assert grid.odds==before['odds'] and grid.floor_frames==before['floor_frames'] and grid.wall_frames==before['wall_frames']
    assert grid.revision==before['revision'] and grid.seen==before['seen']


def test_expansion_never_clears_occupied_goal_or_enclosing_wall():
    g=cropped_goal();g.e2e_route_extent='goal_envelope_v1';grid=g.explorer.grid
    grid.odds[grid.cell([2.,0.])]=4.;grid.wall_frames[grid.cell([2.,0.])]={1}
    with pytest.raises(ContractViolation,match='GRID_ROUTE'):route(g)
    g=cropped_goal();g.e2e_route_extent='goal_envelope_v1';grid=g.explorer.grid
    for i in range(-10,11):
        for c in ((i,-10),(i,10),(-10,i),(10,i)):
            grid.odds[c]=4.;grid.wall_frames[c]={1}
    with pytest.raises(ContractViolation,match='GRID_ROUTE'):route(g)


def test_resource_cap_and_endpoint_validation():
    grid=cropped_goal().explorer.grid
    with pytest.raises(ValueError,match='RESOURCE'):GoalEnvelopeView(grid,[0.,0.],[1e6,1e6]).dense()
    with pytest.raises(ValueError,match='ENDPOINTS'):GoalEnvelopeView(grid,[0.,0.],[np.nan,1.])


def test_registered_extent_profile_and_dependency_closure():
    from scripts.run_e2e_ownmap_live import bundle
    from tests.test_e2e18 import options,ROOT
    from harness.e2e_runtime_registration import require_current
    b=bundle('a'*40,61001,'study_gemma4_31b_v1',**options(),speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1')
    assert b['execution_bundle_id']=='e2e18-v225';require_current(b,ROOT)
    assert 'harness/e2e_route_extent.py' in b['source_sha256']
    b['e2e_options']['route_extent']='off'
    with pytest.raises(ValueError,match='ENVELOPE'):require_current(b,ROOT)
