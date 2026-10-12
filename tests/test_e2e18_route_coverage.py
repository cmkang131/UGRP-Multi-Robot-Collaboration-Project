import math
import pytest
from tests.test_e2e18_route_guard import goal,route
from harness.e2e_route_coverage import fully_observed
from harness.zone_study_contract import ContractViolation


def test_unknown_endpoint_can_plan_dev_without_fabricating_map_completion():
    g=goal();grid=g.explorer.grid
    for cell in list(grid.odds):
        if -.1<grid.point(cell)[0]<.2:grid.odds.pop(cell)
    original=dict(grid.odds)
    with pytest.raises(ContractViolation,match='GRID_ROUTE'):route(g)
    g.e2e_route_coverage='native_v1';p=route(g)
    assert p['compiled']['source']=='own_map' and not fully_observed(p)
    assert grid.odds==original
    d=g.e2e_route_diagnostics
    assert d['would_stop_unknown'] and d['nominal_footprint_cells']['start']['unknown']>0
    assert not d['nominal_footprint_cells']['start']['occupied']
    assert d['attempts'][-1]['path_cells']>0


def test_native_keeps_occupied_barrier_and_finite_grid():
    g=goal();grid=g.explorer.grid;g.e2e_route_coverage='native_v1'
    # Closed occupied ring: a finite wall segment can legitimately be bypassed.
    for i in range(-10,11):
        for cell in ((i,-10),(i,10),(-10,i),(10,i)):
            grid.odds[cell]=4.;grid.wall_frames[cell]={1}
    with pytest.raises(ContractViolation,match='GRID_ROUTE'):route(g)
    g=goal();g.e2e_route_coverage='native_v1';g.entities['B']['center_m']=[20.,0.]
    with pytest.raises(ContractViolation,match='GRID_ROUTE'):route(g)


def test_strict_success_and_default_coverage_still_count():
    assert fully_observed(route(goal()))
    assert fully_observed({'compiled':{}})
    assert not fully_observed(None)


def test_native_bundle_profile():
    from scripts.run_e2e_ownmap_live import bundle
    from tests.test_e2e18 import options,ROOT
    from harness.e2e_runtime_registration import require_current
    b=bundle('a'*40,61004,'study_gemma4_31b_v1',**options(),speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1')
    assert b['execution_bundle_id']=='e2e18-v223';require_current(b,ROOT)
    b['e2e_options']['route_coverage']='off'
    with pytest.raises(ValueError,match='COVERAGE'):require_current(b,ROOT)


def test_actual_completion_rejects_native_only_event():
    from harness.e2e_route_coverage import map_completed
    assert not map_completed([{'event':'own_map_B_route_generated','observed_coverage_complete':False}])
    assert map_completed([{'event':'own_map_B_route_generated','observed_coverage_complete':True}])
    assert map_completed([{'event':'own_map_B_route_generated'}])
    assert not map_completed([{'event':'own_route_wait'}])
