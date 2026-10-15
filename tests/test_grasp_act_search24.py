"""Finite IRM certificates, invariance and deterministic budgeting. No physics."""
import argparse
import json
import math
from copy import deepcopy
from unittest.mock import patch
import pytest
import numpy as np
from sim.grasp_act_search24 import reachability_map, choices_for_world
from sim.grasp_act_pregrasp import jaw_geometry
from sim.grasp_act_teacher import grasp_poses
from sim.grasp_act_goal_set import geometry
from sim.grasp_act_search20 import PlanningBudget, PlanningBudgetExceeded
from sim.grasp_act_search15_modes import add_arguments, options, validate, match
from tests.test_grasp_act_search23 import teacher
from tests.test_grasp_act_search22 import FIX


def test_default_off_and_provenance_dependency():
    p=argparse.ArgumentParser();add_arguments(p);m=options(p.parse_args([]))
    assert m['search24_irm']==m['search24_budget']=='off'
    with pytest.raises(ValueError,match='search24 requires search23'):
        validate({'search24_irm':'search24_irm_v1'},recovery='progress_view_recovery_v3')
    with pytest.raises(ValueError,match='search24_irm mode mismatch'):
        match({}, {'search24_irm':'search24_irm_v1'},'gate')


@pytest.mark.parametrize('z',[.012,.016,.022,.032])
def test_every_map_cell_has_unchanged_full_ik_and_jaw_certificate(z):
    cells=reachability_map(z);assert cells
    for a,d,inverse,commands in cells:
        hover,descent=grasp_poses((d,0.,z))
        assert tuple(tuple(sorted(p.items())) for p in (hover,*descent))==commands
        assert jaw_geometry(a,descent[-1])['allowed']
        assert inverse==pytest.approx((-d*math.cos(a),-d*math.sin(a),a))
    # Exact height matters: cached certificates never reuse a rounded height.
    assert reachability_map(z+.00001) is not cells


def test_task_transform_is_equivariant_and_fresh_target_required():
    t=teacher();t.search15_modes['search24_irm']='search24_irm_v1'
    w=deepcopy(FIX['world']);cells=choices_for_world(t,w);assert cells
    point=w['beam']['ends'][t.end]
    for c in cells:
        _,p,h,g=geometry(w,t.rid,t.end,c)
        assert math.dist(p[:2],g)==pytest.approx(c[1])
        assert (p[0]-g[0])*math.sin(h)-(p[1]-g[1])*math.cos(h)==pytest.approx(0.)
    w['visibility'][t.rid]['observations']['band_'+t.end]['seen_t']=w['t']-1.
    assert choices_for_world(t,w)==[]


def test_budget_ignores_wall_clock_and_stops_at_exact_logical_count():
    b=PlanningBudget(max_checks=3,max_s=None)
    with patch('sim.grasp_act_search20.time.perf_counter',side_effect=[0.,1e9,2e9,3e9]):
        for _ in range(3):b.check()
        with pytest.raises(PlanningBudgetExceeded):b.check()
    assert b.checks==3 and b.exhausted


def test_pick_cloud_cache_has_equal_logical_cost_and_bytes():
    from sim.grasp_act_search23 import BodyNavigation,_PICK_CLOUDS
    from sim.grasp_act_pregrasp import band_view
    t=teacher();t.search15_modes['search24_budget']='search24_checks_v1'
    w=deepcopy(FIX['world']);nav=BodyNavigation(t,w,admission=True)
    _,view=band_view(w,t.rid,t.end,w['robots'][t.rid]['pose'],nav.pwm)
    z=w['beam']['ends'][t.end][2];d=reachability_map(z)[0][1]
    _PICK_CLOUDS.clear();costs=[];values=[]
    for _ in range(2):
        t.search20_budget=PlanningBudget(max_checks=98304,max_s=None)
        values.append(nav.pick_cloud(view,d,z));costs.append(t.search20_budget.checks)
    assert costs[0]==costs[1] and costs[0]>1
    assert all(np.array_equal(a,b) for a,b in zip(*values))


def test_rejection_records_preserve_named_blocker_and_gap():
    from sim.grasp_act_search22 import record_candidates
    t=teacher();t.search15_modes['search24_irm']='search24_irm_v1';w=deepcopy(FIX['world'])
    rows=[{'reason':'blocked_retreat','failure_audit':[{'id':'r2','gap_m':.004,'category':'current_geometry'}]},
          {'reason':'connector_connector_band_not_visible'}]
    record_candidates(t,w,rows,w['t'])
    assert rows[0]['blocked_object']=='r2' and rows[0]['min_gap_m']==.004
    assert rows[1]['blocked_object'] and rows[1]['gap_scope']
    json.dumps(rows,allow_nan=False)


def test_frozen_failed_scene_selects_only_certified_cells_without_wall_deadline():
    from pathlib import Path
    from sim.grasp_act_search19 import body_fallback
    fixture=json.loads((Path(__file__).parent/'fixtures/grasp_act_search23_000.json').read_text())
    t=teacher();t.search15_modes.update(search24_irm='search24_irm_v1',search24_budget='search24_checks_v1')
    t.sink.pwm.update({int(k):v for k,v in fixture['pwm'].items()})
    t.search20_budget=PlanningBudget(max_checks=98304,max_s=None)
    selected,rows=body_fallback(t,fixture['world'],fixture['world']['t'])
    assert selected is not None
    assert all(r['reason'] not in ('ik_unreachable','gripper_angle') for r in rows)
    assert all('blocked_object' in r and 'min_gap_m' in r and r['reason'] for r in rows)
    assert selected['choice'] in [(a,d) for a,d,_,_ in reachability_map(fixture['world']['beam']['ends'][t.end][2])]
