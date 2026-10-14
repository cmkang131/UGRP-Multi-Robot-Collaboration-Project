"""Scenario set v5: v4 without three-robot cargo (user 2026-10-14: "3명이서 하는 짐은 뺴주라").

v5 = v4 apart from ``scenario_id``, s7 (tri_frame order -> heavy_crate, renamed) and s8 (tri_frame order removed).
Offline only: config validation, routing and static-geometry feasibility, no simulator.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness import zone_environment_registry as env
from harness.zone_scenario_feasibility import evaluate
from harness.zone_study_scenarios import ROBOTS, leader_rotation, load_all, validate

ROOT = Path(__file__).resolve().parents[1]
V4 = ROOT / 'configs' / 'zone_study_scenarios_v4'
V5 = ROOT / 'configs' / 'zone_study_scenarios_v5'
CHANGED = {'s7_trio_rendezvous_v4': 's7_pair_with_solo_v5', 's8_mixed_tiers_v4': 's8_mixed_tiers_v5'}


@pytest.fixture(scope='module')
def scenarios():
    return load_all(directory=V5)


def test_eight_scenarios_with_unique_seeds_and_v5_ids(scenarios):
    assert len(scenarios) == 8
    assert all(sid.endswith('_v5') for sid in scenarios)
    seeds = [s for sc in scenarios.values() for s in sc['seeds']]
    assert len(seeds) == len(set(seeds)) == 24


def test_no_scenario_needs_more_than_two_robots_or_uses_tri_frame(scenarios):
    for sid, sc in scenarios.items():
        assert max(o['required_robots'] for o in sc['orders']) <= 2, sid
        assert all(o['kind'] != 'tri_frame' for o in sc['orders']), sid
        assert all(p['kind'] != 'tri_frame' for p in sc['eval']['setup']['placements']), sid


def test_s1_to_s6_equal_v4_except_scenario_id():
    for path in sorted(V4.glob('*.json')):
        v4 = json.loads(path.read_text())
        if v4['scenario_id'] in CHANGED:
            continue
        v5 = json.loads((V5 / path.name.replace('_v4', '_v5')).read_text())
        assert v5['scenario_id'] == v4['scenario_id'][:-3] + '_v5'
        v4['scenario_id'] = v5['scenario_id'] = 'x'
        assert v5 == v4, path.name


def test_s7_keeps_the_two_solo_orders_and_swaps_tri_frame_for_one_crate(scenarios):
    v4 = json.loads((V4 / 's7_trio_rendezvous_v4.json').read_text())
    v5 = scenarios['s7_pair_with_solo_v5']
    assert v5['orders'][1:] == v4['orders'][1:]
    first = v5['orders'][0]
    assert (first['kind'], first['required_robots'], first['item_ids']) == ('heavy_crate', 2, ['crate_1'])
    assert first['initial_location'] == v4['orders'][0]['initial_location']
    assert first['destination_zone'] == v4['orders'][0]['destination_zone']
    place = v5['eval']['setup']['placements'][0]
    assert (place['item_id'], place['kind'], place['pose_m']) == (
        'crate_1', 'heavy_crate', v4['eval']['setup']['placements'][0]['pose_m'])
    assert v5['eval']['setup']['placements'][1:] == v4['eval']['setup']['placements'][1:]


def test_s8_is_v4_minus_the_tri_frame_order(scenarios):
    v4 = json.loads((V4 / 's8_mixed_tiers_v4.json').read_text())
    v5 = scenarios['s8_mixed_tiers_v5']
    assert v5['orders'] == [o for o in v4['orders'] if o['kind'] != 'tri_frame']
    assert v5['eval']['setup']['placements'] == [
        p for p in v4['eval']['setup']['placements'] if p['kind'] != 'tri_frame']
    assert v5['seeds'] == v4['seeds'] and v5['eval']['budget'] == v4['eval']['budget']


def test_every_scenario_validates_and_rotates_all_leaders(scenarios):
    for sid, sc in scenarios.items():
        report = env.validate(sc)
        assert report.ok, (sid, report.problems)
        assert set(leader_rotation(sc['seeds']).values()) == set(ROBOTS), sid


@pytest.mark.parametrize('sid', sorted(p.stem for p in V5.glob('*.json')))
def test_registry_routes_v5_ids_to_the_v5_directory(sid):
    assert env.load_scenario(sid)['scenario_id'] == sid


def test_changed_scenarios_have_a_feasible_carry_route(scenarios):
    for sid in ('s7_pair_with_solo_v5', 's8_mixed_tiers_v5'):
        sc = scenarios[sid]
        report = evaluate(sc, maps_dir=env.maps_dir_for(sc['map_id']))
        verdicts = {item: route.verdict for item, route in report.routes.items()}
        assert set(verdicts.values()) == {'feasible'}, (sid, verdicts)


@pytest.mark.parametrize('sid', ['s7_pair_with_solo_v5', 's8_mixed_tiers_v5'])
def test_scene_builds_from_a_v5_scenario_id_string(sid):
    """The scene factory reads the scenario by id; it must find the v5 directory (review of PR #498)."""
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    scene = ScenarioFinalV3Scene.from_scenario(sid, 661)
    assert scene.scene['params']['scenario_setup']['scenario_id'] == sid
