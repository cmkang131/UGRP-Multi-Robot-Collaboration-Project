"""Scenario set v4: scenario v3 (s1-s8) with only the map fields moved to the final robot-v3 maps.

v4 = v3 apart from ``scenario_id`` (_v3 -> _v4), ``map_id`` and ``eval.setup.map_file_sha256``.
The map geometry of v2/final_v1 and v3 is identical (ids, robot_model, version and parent hash differ).
Offline only: config validation, file hashes and static-geometry feasibility, no simulator.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from harness.zone_scenario_feasibility import evaluate
from harness.zone_study_scenarios import ROBOTS, leader_rotation, load_all, validate

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / 'configs' / 'zone_study_scenarios_v3'
V4 = ROOT / 'configs' / 'zone_study_scenarios_v4'
# scenario v3 map id -> (robot-v3 map file, the old map file it must be geometrically identical to)
MAPS = {
    'zone_wide_door_geometry_v2': (ROOT / 'maps' / 'zones' / 'zone_wide_door_geometry_v3.json',
                                   ROOT / 'maps' / 'zones' / 'zone_wide_door_geometry_v2.json'),
    'zone_wide_two_doors_final_v1': (ROOT / 'maps' / 'zones_final_v3' / 'zone_wide_two_doors_final_v3.json',
                                     ROOT / 'maps' / 'zones_final' / 'zone_wide_two_doors_final_v1.json'),
    'zone_wide_corridor_final_v1': (ROOT / 'maps' / 'zones_final_v3' / 'zone_wide_corridor_final_v3.json',
                                    ROOT / 'maps' / 'zones_final' / 'zone_wide_corridor_final_v1.json'),
}
MAP_ID_DIFFERENCES = {'map_id', 'version', 'robot_model', 'parent_scene'}
NEW_TRIO = ('s7_trio_rendezvous_v4', 's8_mixed_tiers_v4')


@pytest.fixture(scope='module')
def scenarios():
    return load_all(directory=V4)


def _maps_dir(scenario):
    for new_file, _ in MAPS.values():
        if new_file.stem == scenario['map_id']:
            return new_file.parent
    raise AssertionError(scenario['map_id'])


def test_eight_scenarios_with_unique_seeds(scenarios):
    assert len(scenarios) == 8
    seeds = [s for sc in scenarios.values() for s in sc['seeds']]
    assert len(seeds) == len(set(seeds)) == 24
    assert all(len(sc['seeds']) == 3 for sc in scenarios.values())
    assert all(sid.endswith('_v4') for sid in scenarios)


def test_every_scenario_validates_against_its_v3_map_and_rotates_all_leaders(scenarios):
    for sid, sc in scenarios.items():
        report = validate(sc, maps_dir=_maps_dir(sc))
        assert report.ok, (sid, report.problems)
        assert set(leader_rotation(sc['seeds']).values()) == set(ROBOTS), sid


def test_v4_equals_v3_except_scenario_id_and_map_fields():
    v3_files = sorted(V3.glob('*.json'))
    assert [p.name.replace('_v3', '_v4') for p in v3_files] == sorted(p.name for p in V4.glob('*.json'))
    for path in v3_files:
        v3 = json.loads(path.read_text())
        v4 = json.loads((V4 / path.name.replace('_v3', '_v4')).read_text())
        assert v4['scenario_id'] == v3['scenario_id'][:-3] + '_v4'
        for value in (v3, v4):
            value['scenario_id'] = 'x'
            value['map_id'] = 'x'
            value['eval']['setup']['map_file_sha256'] = 'x'
        assert v4 == v3, path.name


def test_map_fields_point_at_the_robot_v3_map_file_and_its_hash(scenarios):
    new_ids = {new.stem for new, _ in MAPS.values()}
    for sid, sc in scenarios.items():
        assert sc['map_id'] in new_ids, sid
        new_file = next(new for new, _ in MAPS.values() if new.stem == sc['map_id'])
        assert json.loads(new_file.read_text())['robot_model'] == 'masterpi_v3'
        assert sc['eval']['setup']['map_file_sha256'] == hashlib.sha256(new_file.read_bytes()).hexdigest(), sid


def test_each_v3_map_has_the_same_geometry_as_the_map_the_v3_scenarios_used():
    """Why the map switch needs no new design: only ids, version, robot model and parent hash differ."""
    for new_file, old_file in MAPS.values():
        new, old = json.loads(new_file.read_text()), json.loads(old_file.read_text())
        differing = {k for k in set(new) | set(old) if new.get(k) != old.get(k)}
        assert differing <= MAP_ID_DIFFERENCES, (new_file.name, differing)
        assert {'map_id', 'robot_model'} <= differing


def test_v4_keeps_the_v3_map_assignment_per_scenario(scenarios):
    for path in sorted(V3.glob('*.json')):
        v3 = json.loads(path.read_text())
        v4 = scenarios[v3['scenario_id'][:-3] + '_v4']
        assert v4['map_id'] == MAPS[v3['map_id']][0].stem
        assert v4['eval']['setup']['arena_variant'] == v3['eval']['setup']['arena_variant']


def test_study_inputs_stay_tag_free_weld_off_and_unchanged(scenarios):
    for sid, sc in scenarios.items():
        assert sc['landmark_detail'] == 'none', sid
        assert sc['eval']['setup']['weld'] == 'off', sid
        assert sc['eval']['setup']['contact_profile'] == 'cargo_noslip_v1', sid


@pytest.fixture(scope='module')
def trio_reports(scenarios):
    """Feasibility on the v3 maps of the two scenarios with the heaviest geometry demand (trio, 3 tiers)."""
    return {sid: evaluate(scenarios[sid], maps_dir=_maps_dir(scenarios[sid])) for sid in NEW_TRIO}


def test_trio_and_mixed_tier_items_have_a_feasible_carry_route_on_the_v3_map(trio_reports):
    for sid, report in trio_reports.items():
        verdicts = {item: route.verdict for item, route in report.routes.items()}
        assert set(verdicts.values()) == {'feasible'}, (sid, verdicts)
