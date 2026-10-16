"""Scenario set v3: every cargo kind, every carrier tier, and 3-robot (trio) carrying.

v3 = the six v2 scenarios (unchanged apart from ``scenario_id``) + s7 (trio) + s8 (all tiers).
Offline only: config validation and static-geometry feasibility, no simulator.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import harness.zone_final_env as fe
from harness.zone_scenario_feasibility import evaluate
from harness.zone_study_scenarios import ROBOTS, leader_rotation, load_all, validate
from sim.zone_arena import COLORS
from sim.zone_cargo import CATALOGUE

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / 'configs' / 'zone_study_scenarios_v2'
V3 = ROOT / 'configs' / 'zone_study_scenarios_v3'
NEW = ('s7_trio_rendezvous_v3', 's8_mixed_tiers_v3')
ALL_KINDS = set(COLORS) | set(CATALOGUE)


@pytest.fixture(scope='module')
def scenarios():
    return load_all(directory=V3)


def _maps_dir(scenario):
    return fe.maps_dir_for(scenario['map_id'])


def test_eight_scenarios_with_unique_seeds(scenarios):
    assert len(scenarios) == 8
    seeds = [s for sc in scenarios.values() for s in sc['seeds']]
    assert len(seeds) == len(set(seeds)) == 24
    assert all(len(sc['seeds']) == 3 for sc in scenarios.values())


def test_every_scenario_validates_and_rotates_all_leaders(scenarios):
    for sid, sc in scenarios.items():
        report = validate(sc, maps_dir=_maps_dir(sc))
        assert report.ok, (sid, report.problems)
        assert set(leader_rotation(sc['seeds']).values()) == set(ROBOTS), sid


def test_six_v2_scenarios_are_carried_forward_unchanged(scenarios):
    for path in sorted(V2.glob('*.json')):
        v2 = json.loads(path.read_text())
        v3 = json.loads(json.dumps(scenarios[v2['scenario_id'][:-3] + '_v3']))
        assert v3['scenario_id'].endswith('_v3')
        v3['scenario_id'] = v2['scenario_id']
        assert v3 == v2, path.name


def test_every_cargo_kind_is_ordered_somewhere(scenarios):
    ordered = {o['kind'] for sc in scenarios.values() for o in sc['orders']}
    assert ordered == ALL_KINDS, sorted(ALL_KINDS - ordered)


def test_every_carrier_tier_appears_and_matches_the_catalogue(scenarios):
    demand = {o['required_robots'] for sc in scenarios.values() for o in sc['orders']}
    assert demand == {1, 2, 3}
    for sc in scenarios.values():
        for order in sc['orders']:
            if order['kind'] in CATALOGUE:
                assert order['required_robots'] == CATALOGUE[order['kind']].required_carriers


def test_trio_orders_exist_only_where_a_wide_door_exists(scenarios):
    trio = {sid for sid, sc in scenarios.items() if any(o['required_robots'] == 3 for o in sc['orders'])}
    assert trio == set(NEW)
    for sid in trio:
        assert scenarios[sid]['map_id'] == 'zone_wide_two_doors_final_v1'


@pytest.fixture(scope='module')
def new_reports(scenarios):
    """Feasibility of the two new scenarios (the six carried forward are covered by their v2 twins)."""
    return {sid: evaluate(scenarios[sid], maps_dir=_maps_dir(scenarios[sid])) for sid in NEW}


def test_every_item_of_the_new_scenarios_has_a_feasible_carry_route(new_reports):
    for sid, report in new_reports.items():
        verdicts = {item: route.verdict for item, route in report.routes.items()}
        assert set(verdicts.values()) == {'feasible'}, (sid, verdicts)


def test_trio_frame_cannot_pass_the_single_narrow_door_map(scenarios):
    """Negative control: the same s7 on the 0.5 m door map has no route (why s7 needs two doors)."""
    sc = json.loads(json.dumps(scenarios['s7_trio_rendezvous_v3']))
    base = json.loads((ROOT / 'maps' / 'zones' / 'zone_wide_door_geometry_v2.json').read_text())
    report = evaluate(sc, static_map=base)
    assert report.routes['frame_1'].verdict == 'infeasible'


def test_new_scenarios_are_structural_with_no_hidden_events(scenarios):
    for sid in NEW:
        assert scenarios[sid]['eval']['hidden_events'] == []
        assert scenarios[sid]['landmark_detail'] == 'none'
        assert scenarios[sid]['eval']['setup']['weld'] == 'off'


def test_s8_needs_all_three_tiers_and_more_carriers_than_robots(new_reports):
    per_item = new_reports['s8_mixed_tiers_v3'].robots
    assert sorted(set(per_item['per_item'].values())) == [1, 2, 3]
    assert sum(per_item['per_item'].values()) > per_item['team_size']
