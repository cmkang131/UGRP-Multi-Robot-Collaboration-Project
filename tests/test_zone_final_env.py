"""Final study environment v1 (#218, prereg blocker B5): tag-free walls_v3 maps + scenario v2.

Static only: map files, scenario configs and ``harness.zone_final_env``. No MuJoCo,
no scene, no model call. The frozen hashes below are the published v1 files and
the reused ``zone_wide_door_geometry_v2`` map: they must never change.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from harness import zone_final_env as fe
from harness.zone_map_schematic import MAP_DIR, load_map, public_map
from harness.zone_scenario_feasibility import CARRY_RADIUS_M, ROBOT_RADIUS_M
from harness.zone_study_scenarios import validate

ROOT = Path(__file__).resolve().parents[1]
# Published v1 files (byte-identical forever) and the reused tag-free door map.
FROZEN_V1_SCENARIOS = {
    's1_normal_mixed': '97709cbd901c15d2', 's2_unmapped_blockage': '7a08d478d2adf91e',
    's3_late_rendezvous': 'db261ce07a558947', 's4_narrow_door_standoff': 'a108895c7740186a',
    's5_moved_dropped_item': '6720b8f03fb480ee', 's6_novel_relation': '2c165d0971717ca8'}
FROZEN_V1_MAPS = {
    'zone_wide_door_tags_v1': 'f86fc314ed3c4c2866f9b5c8448b9b1919462f0c1a958bedf46442513604ea14',
    'zone_wide_two_doors_tags_v1': '2562d2f09940e9ba864cf1fe71740592e5305835a6c1af24b3493298a583c4ed',
    'zone_wide_corridor_tags_v1': 'a349d42d60f3fcefd1efa29016aeb39e15e40c0092268c0485814e7f9f3916db'}
REUSED_DOOR_MAP_SHA = '0a8f5fdc3b3ad01710971a9f5caf020eb76c7e90f3da5713e669d035b4e7ebaf'
FROZEN_FINAL_MAPS = {'zone_wide_two_doors_final_v1': 'e93bce155c01aef3',
                     'zone_wide_corridor_final_v1': 'f968251ae0e9a3af'}


def _sha(path: Path) -> str:
    return fe.sha256_bytes(Path(path).read_bytes())


def _map(map_id: str) -> dict:
    return load_map(map_id, maps_dir=fe.maps_dir_for(map_id))[0]


def _v2(v1_id: str) -> dict:
    return json.loads((fe.V2_SCENARIO_DIR / (fe.v2_id(v1_id) + '.json')).read_text())


# ---------------------------------------------------------------------------
# v1 stays byte-identical; the new files are registered with their hashes

def test_v1_scenarios_and_tag_maps_are_unchanged():
    for sid, prefix in FROZEN_V1_SCENARIOS.items():
        assert _sha(fe.V1_SCENARIO_DIR / f'{sid}.json').startswith(prefix), sid
    for map_id, sha in FROZEN_V1_MAPS.items():
        assert _sha(MAP_DIR / f'{map_id}.json') == sha, map_id
    assert _sha(MAP_DIR / 'zone_wide_door_geometry_v2.json') == REUSED_DOOR_MAP_SHA


def test_catalog_matches_the_files_and_pins_every_hash():
    stored = json.loads(fe.CATALOG_PATH.read_text())
    assert stored == fe.catalog()
    assert stored['tags'] == 0 and stored['wall_profile'] == 'walls_v3'
    for map_id, prefix in FROZEN_FINAL_MAPS.items():
        assert stored['maps'][map_id]['file_sha256'].startswith(prefix)
    assert stored['maps']['zone_wide_door_geometry_v2']['reused_existing_file'] is True
    for sid, entry in stored['scenarios'].items():
        v2 = _v2(sid[:-len(fe.V2_SUFFIX)])
        assert entry['map_file_sha256'] == v2['eval']['setup']['map_file_sha256'] \
            == stored['maps'][v2['map_id']]['file_sha256']
        assert entry['v1']['map_file_sha256'] == FROZEN_V1_MAPS[entry['v1']['map_id']]


def test_the_recipe_reproduces_the_reused_door_map_byte_for_byte():
    path = MAP_DIR / 'zone_wide_door_geometry_v2.json'
    assert path.read_text() == fe._dump(fe.final_map('zone_wide_door_geometry_v2'))


@pytest.mark.parametrize('final_id,tags_v3', [('zone_wide_two_doors_final_v1', 'zone_wide_two_doors_tags_v3'),
                                              ('zone_wide_corridor_final_v1', 'zone_wide_corridor_tags_v3')])
def test_new_maps_are_the_registered_env_v3_maps_without_landmarks(final_id, tags_v3):
    """Cross-check against another published walls_v3 build: same map minus the tag block."""
    ours, theirs = _map(final_id), load_map(tags_v3)[0]
    theirs.pop('landmarks')
    for key in ('map_id', 'version'):
        ours.pop(key), theirs.pop(key)
    assert ours == theirs


def test_write_refuses_to_change_a_published_file(tmp_path, monkeypatch):
    target = tmp_path / 'zone_wide_two_doors_final_v1.json'
    target.write_text('{}\n')
    monkeypatch.setitem(fe.FINAL_MAPS, 'zone_wide_two_doors_final_v1', ('zone_wide_two_doors', tmp_path))
    with pytest.raises(fe.FinalEnvError, match='differs from its definition'):
        fe.write_maps()
    assert target.read_text() == '{}\n'


def test_write_never_creates_a_file_under_maps_zones(monkeypatch):
    monkeypatch.setattr(fe, 'FINAL_MAPS', {'zone_wide_door_final_probe': ('zone_wide_door', MAP_DIR)})
    with pytest.raises(fe.FinalEnvError, match='maps/zones is not written here'):
        fe.write_maps()
    assert not (MAP_DIR / 'zone_wide_door_final_probe.json').exists()


# ---------------------------------------------------------------------------
# Map schema, zero tag fields, walls_v3

@pytest.mark.parametrize('map_id', sorted(fe.FINAL_MAPS))
def test_final_maps_pass_schema_and_carry_no_tag_field(map_id):
    assert fe.check_map(map_id) == []
    data = _map(map_id)
    assert fe.tag_hits(data) == [] and 'landmarks' not in data
    assert {o['height_m'] for o in data['obstacles']} == {.40}
    projection = public_map(data, landmark_detail='none')
    assert 'landmarks' not in projection and fe.tag_hits({k: v for k, v in projection.items()
                                                          if k != 'landmark_detail'}) == []


def test_check_map_reports_unknown_ids_instead_of_raising():
    assert fe.check_map('zone_wide_door_tags_v1')[0].startswith('zone_wide_door_tags_v1: cannot load')
    assert fe.check_map('')[0].startswith(': cannot load')


@pytest.mark.parametrize('value,expected', [
    ({'landmarks': {'tags': []}}, ['landmarks', 'landmarks.tags']),
    ({'note': 'AprilTag on the post'}, ["note='AprilTag on the post'"]),
    ({'family': 'tag36h11'}, ["family='tag36h11'"]),
    ({'walls': [{'id': 'wall_1', 'stage': 'storage'}]}, []),
    ({}, []), ([], []), (None, []), (0, []), (float('nan'), [])])
def test_tag_hits_finds_keys_and_values_only(value, expected):
    assert fe.tag_hits(value) == expected


# ---------------------------------------------------------------------------
# Passage widths

EXPECTED_PASSAGES = {'zone_wide_door_geometry_v2': {'door_1': (.5, 1)},
                     'zone_wide_two_doors_final_v1': {'door_narrow': (.5, 1), 'door_wide': (1., 2)},
                     'zone_wide_corridor_final_v1': {'corridor_1': (.5, 1)}}


@pytest.mark.parametrize('map_id', sorted(fe.FINAL_MAPS))
def test_passage_widths_are_measured_from_the_walls(map_id):
    rows, problems = fe.passage_widths(_map(map_id))
    assert problems == []
    got = {r['id']: (r['measured_m'], r['lanes']) for r in rows}
    assert got == EXPECTED_PASSAGES[map_id]


@pytest.mark.parametrize('width', [.6, 0, 0., None, float('nan'), float('inf'), True, '0.5'])
def test_a_wrong_declared_width_is_reported(width):
    data = copy.deepcopy(_map('zone_wide_door_geometry_v2'))
    data['passages'][0]['width_m'] = width
    problems = fe.passage_widths(data)[1]
    assert len(problems) == 1 and problems[0].startswith('door_1')


def test_a_wall_moved_into_the_door_is_measured_as_closed():
    data = copy.deepcopy(_map('zone_wide_door_geometry_v2'))
    data['obstacles'].append({'id': 'probe', 'kind': 'wall', 'center_m': [2.2, .05],
                              'half_extents_m': [.025, .1], 'height_m': .4})
    rows, problems = fe.passage_widths(data)
    assert rows[0]['measured_m'] == 0. and 'measured wall gap 0.0 m' in problems[0]


def test_a_narrowed_door_is_measured_not_trusted():
    data = copy.deepcopy(_map('zone_wide_two_doors_final_v1'))
    wall = next(o for o in data['obstacles'] if o['id'] == 'wall_divider_1')
    # wall_divider_1 runs between the two doors (y -2.125..-0.2); stretch its north
    # end to y 0.0 so door_narrow (declared 0.50 m) keeps only 0.30 m.
    wall['half_extents_m'][1] += .1
    wall['center_m'][1] += .1
    problems = fe.passage_widths(data)[1]
    assert problems and 'measured wall gap' in problems[0]


@pytest.mark.parametrize('bad', [{'center_m': [float('nan'), 0.], 'half_extents_m': [.025, .25]},
                                 {'center_m': [2.2], 'half_extents_m': [.025, .25]},
                                 {'center_m': None, 'half_extents_m': [.025, .25]}])
def test_corrupted_passage_frames_fail_loudly(bad):
    data = copy.deepcopy(_map('zone_wide_door_geometry_v2'))
    data['passages'][0].update(bad)
    problems = fe.passage_widths(data)[1]
    assert len(problems) == 1 and problems[0].startswith('door_1:')


@pytest.mark.parametrize('passages', [[], None])
def test_a_map_without_passages_is_reported(passages):
    data = copy.deepcopy(_map('zone_wide_door_geometry_v2'))
    data['passages'] = passages
    assert fe.passage_widths(data) == ([], ['the map declares no passage'])


# ---------------------------------------------------------------------------
# Reachability on the static map graph

@pytest.mark.parametrize('sid', sorted(FROZEN_V1_SCENARIOS))
@pytest.mark.parametrize('radius', [ROBOT_RADIUS_M, CARRY_RADIUS_M])
def test_every_v2_order_is_reachable(sid, radius):
    v2 = _v2(sid)
    graph, problems = fe.reachability(_map(v2['map_id']), v2['orders'], radius_m=radius)
    assert problems == []
    assert len(graph['orders']) == len(v2['orders'])
    assert all(o['reachable'] and o['via'] for o in graph['orders'].values())


def _door_block(data, passage_id):
    p = next(p for p in data['passages'] if p['id'] == passage_id)
    return ((p['center_m'][0], p['center_m'][1], .05, p['half_extents_m'][1], 0.),)


def test_blocking_the_only_door_disconnects_every_order():
    v2 = _v2('s1_normal_mixed')
    data = _map(v2['map_id'])
    graph, problems = fe.reachability(data, v2['orders'], extra_rects=_door_block(data, 'door_1'))
    assert len(problems) == len(v2['orders']) and not any(o['reachable'] for o in graph['orders'].values())


def test_blocking_the_narrow_door_leaves_the_wide_door():
    v2 = _v2('s2_unmapped_blockage')
    data = _map(v2['map_id'])
    graph, problems = fe.reachability(data, v2['orders'], extra_rects=_door_block(data, 'door_narrow'))
    assert problems == [] and all(o['via'] == ['door_wide'] for o in graph['orders'].values())


def test_a_disc_wider_than_the_door_cannot_pass():
    v2 = _v2('s1_normal_mixed')
    problems = fe.reachability(_map(v2['map_id']), v2['orders'], radius_m=.26)[1]
    assert problems and all('not connected' in p for p in problems)


def test_radius_zero_is_a_point_robot_not_the_default():
    v2 = _v2('s1_normal_mixed')
    graph, problems = fe.reachability(_map(v2['map_id']), v2['orders'], radius_m=0.)
    assert problems == [] and graph['radius_m'] == 0.


@pytest.mark.parametrize('radius', [float('nan'), float('inf'), -.1, None, True])
def test_bad_radius_raises(radius):
    with pytest.raises(fe.FinalEnvError):
        fe.reachability(_map('zone_wide_door_geometry_v2'), [{'order_id': 'o'}], radius_m=radius)


@pytest.mark.parametrize('orders,needle', [
    ([], 'non-empty'), (None, 'non-empty'), ('orders', 'non-empty'), ([None], 'must be an object'),
    ([{'order_id': 'o', 'initial_location': None, 'destination_zone': 'A'}], 'initial_location'),
    ([{'order_id': 'o', 'initial_location': {'slot': 'P9-9'}, 'destination_zone': 'A'}], 'not a slot/bay'),
    ([{'order_id': 'o', 'initial_location': {'pickup_bay': 'P1', 'slot': 'P9-9'}, 'destination_zone': 'A'}],
     'not a slot/bay'),
    ([{'order_id': 'o', 'initial_location': {'slot': 'P1-1'}, 'destination_zone': 'D'}], 'destination_zone'),
    ([{'order_id': 'o', 'initial_location': {'slot': 'P1-1'}, 'destination_zone': None}], 'destination_zone')])
def test_bad_orders_are_reported(orders, needle):
    problems = fe.reachability(_map('zone_wide_door_geometry_v2'), orders)[1]
    assert problems and needle in problems[0]


def test_a_bay_without_slot_is_accepted():
    order = {'order_id': 'o', 'initial_location': {'pickup_bay': 'P2'}, 'destination_zone': 'C'}
    graph, problems = fe.reachability(_map('zone_wide_door_geometry_v2'), [order])
    assert problems == [] and graph['orders']['o']['pickup'] == 'P2'


# ---------------------------------------------------------------------------
# Scenario v2: only the map pin changes, and the study checks still pass

@pytest.mark.parametrize('sid', sorted(FROZEN_V1_SCENARIOS))
def test_v2_changes_only_the_map_pin(sid):
    v1 = json.loads((fe.V1_SCENARIO_DIR / f'{sid}.json').read_text())
    v2 = _v2(sid)
    assert fe.diff_paths(v1, v2) == list(fe.ALLOWED_DIFF)
    assert fe.scenario_diff(v1, v2) == []
    assert v2 == fe.scenario_v2(v1)
    assert v2['landmark_detail'] == 'none' and v2['map_id'] == fe.V1_MAP_TO_FINAL[v1['map_id']]
    for key in ('seeds', 'orders'):
        assert v2[key] == v1[key]
    for key in ('hidden_events', 'budget'):
        assert v2['eval'][key] == v1['eval'][key]
    assert v2['eval']['setup']['placements'] == v1['eval']['setup']['placements']
    assert [h for h in fe.tag_hits(v2) if h != 'landmark_detail'] == []


@pytest.mark.parametrize('sid', sorted(FROZEN_V1_SCENARIOS))
def test_v2_passes_the_study_scenario_validator(sid):
    v2 = _v2(sid)
    report = validate(v2, maps_dir=fe.maps_dir_for(v2['map_id']))
    assert report.ok, report.problems
    assert report.manifest['map']['has_landmarks'] is False
    assert report.manifest['map']['map_file_sha256'] == v2['eval']['setup']['map_file_sha256']


def test_scenario_diff_flags_any_other_change():
    v1 = json.loads((fe.V1_SCENARIO_DIR / 's3_late_rendezvous.json').read_text())
    v2 = fe.scenario_v2(v1)
    v2['seeds'] = [621, 622, 624]
    v2['orders'][0]['count'] = 0
    v2['eval']['hidden_events'] = []
    problems = fe.scenario_diff(v1, v2)
    assert any('seeds[2]' in p for p in problems) and any('orders[0].count' in p for p in problems)
    assert any('eval.hidden_events' in p for p in problems)
    assert fe.scenario_diff(v1, copy.deepcopy(v1))[-1].endswith('map_id was not moved off the tag map')


@pytest.mark.parametrize('bad', [None, {}, [], {'map_id': 'zone_wide_door'}, {'map_id': 'zone_wide_door_tags_v3'}])
def test_scenario_v2_refuses_non_v1_inputs(bad):
    with pytest.raises(fe.FinalEnvError):
        fe.scenario_v2(bad)


def test_diff_paths_distinguishes_types_and_missing_keys():
    assert fe.diff_paths({'a': 0}, {'a': 0.}) == ['a']
    assert fe.diff_paths({'a': 1}, {'b': 1}) == ['a', 'b']
    assert fe.diff_paths([1, 2], [1]) == ['']
    assert fe.diff_paths({'x': [float('inf')]}, {'x': [float('inf')]}) == []
    assert math.isnan(float('nan')) and fe.diff_paths(float('nan'), float('nan')) == ['']


def test_check_all_is_clean():
    assert {k: v for k, v in fe.check_all().items() if v} == {}


def test_ci_collects_this_file():
    from scripts.run_ci_tests import TEST_PATTERNS
    matched = [p for p in TEST_PATTERNS if 'test_zone_final_env' in p]
    assert matched and all(list(ROOT.glob(p)) == [ROOT / 'tests/test_zone_final_env.py'] for p in matched)
