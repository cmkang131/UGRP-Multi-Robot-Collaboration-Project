"""v6 config/routing/input regressions, without physics, rendering or models."""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

import pytest

from harness import zone_environment_registry as env
from harness import zone_study_inputs as inputs
from harness import zone_study_prompts_ko as prompts
from harness.zone_study_contract import ContractViolation, MAIN_CONDITIONS, ROBOTS
from harness.zone_study_scenarios import leader_rotation, load_all

ROOT = Path(__file__).resolve().parents[1]
V5 = ROOT / 'configs/zone_study_scenarios_v5'
V6 = ROOT / 'configs/zone_study_scenarios_v6'
BOX_KINDS = ('cyan', 'red', 'green', 'yellow')
REPLACEMENTS = {
    's1_normal_mixed_v6': {'can_1': ('yellow_1', 'yellow'), 'tile_1': ('red_2', 'red')},
    's3_late_rendezvous_v6': {'tile_1': ('green_1', 'green')},
    's5_moved_dropped_item_v6': {'can_1': ('green_1', 'green')},
    's6_novel_relation_v6': {'can_1': ('red_1', 'red')},
    's7_pair_with_solo_v6': {'tile_1': ('red_1', 'red')},
    's8_mixed_tiers_v6': {'can_1': ('cyan_1', 'cyan')},
}
IDS = sorted(p.stem for p in V6.glob('*.json'))


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for module in ('mujoco', 'torch', 'sim.multi_masterpi_production'):
        monkeypatch.setitem(sys.modules, module, None)


@pytest.fixture(scope='module')
def scenarios():
    return load_all(directory=V6)


def test_eight_v6_scenarios_keep_24_seeds_and_two_carrier_limit(scenarios):
    assert len(scenarios) == 8
    seeds = [s for sc in scenarios.values() for s in sc['seeds']]
    assert len(seeds) == len(set(seeds)) == 24
    for sid, sc in scenarios.items():
        assert sid.endswith('_v6')
        assert max(o['required_robots'] for o in sc['orders']) <= 2
        assert {o['kind'] for o in sc['orders']} <= set(inputs.V6_ITEM_KINDS)
        assert {p['kind'] for p in sc['eval']['setup']['placements']} <= set(inputs.V6_ITEM_KINDS)
        assert {o['kind'] for o in sc['orders'] if o['required_robots'] == 1} <= set(BOX_KINDS)
        assert set(leader_rotation(sc['seeds']).values()) == set(ROBOTS)


@pytest.mark.parametrize('sid', IDS)
def test_only_kind_colour_identifiers_and_private_labels_change(sid, scenarios):
    old = json.loads((V5 / (sid[:-3] + '_v5.json')).read_text())
    new = scenarios[sid]
    assert new['eval']['hidden_events'] == old['eval']['hidden_events']
    expected = copy.deepcopy(old)
    expected['scenario_id'] = sid
    by_order = {}
    renamed = REPLACEMENTS.get(sid, {})
    for p in expected['eval']['setup']['placements']:
        if p['item_id'] in renamed:
            new_id, new_kind = renamed[p['item_id']]
            by_order[p['order_id']] = new_kind
            p['item_id'], p['kind'] = new_id, new_kind
    for o in expected['orders']:
        o['kind'] = by_order.get(o['order_id'], o['kind'])
        if 'item_ids' in o:
            o['item_ids'] = [renamed.get(i, (i, None))[0] for i in o['item_ids']]
    # s6's private design labels follow the renamed object; its authored
    # poses, event schedule, budgets, map/hash and all numeric notes stay fixed.
    def labels(value):
        if isinstance(value, dict):
            return {k: labels(v) for k, v in value.items()}
        if isinstance(value, list):
            return [labels(v) for v in value]
        if isinstance(value, str):
            for old_id, (new_id, kind) in renamed.items():
                value = value.replace(old_id, new_id)
                value = re.sub(r'(?<![A-Za-z0-9_])' + old_id.split('_')[0] + r'(?![A-Za-z0-9_])', kind, value)
        return value
    assert new == labels(expected)


@pytest.mark.parametrize('sid', IDS)
def test_replacements_choose_unused_then_least_used_colour(sid, scenarios):
    old = json.loads((V5 / (sid[:-3] + '_v5.json')).read_text())
    counts = Counter(p['kind'] for p in old['eval']['setup']['placements'] if p['kind'] in BOX_KINDS)
    for before, after in zip(old['orders'], scenarios[sid]['orders']):
        if before['kind'] not in ('can', 'tile'):
            continue
        assert after['kind'] == min(BOX_KINDS, key=lambda k: counts[k])
        counts[after['kind']] += after['count']


@pytest.mark.parametrize('sid', IDS)
def test_registry_and_scene_route_v6_id_and_exact_inventory(sid, scenarios):
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    sc = scenarios[sid]
    assert env.load_scenario(sid) == sc
    report = env.validate(sc)
    assert report.ok, report.problems
    scene = ScenarioFinalV3Scene.from_scenario(sid, sc['seeds'][0])
    assert scene.scene['params']['scenario_setup'] == sc
    assert scene.inventory == [p['item_id'] for p in sc['eval']['setup']['placements'] if p['kind'] in BOX_KINDS] + [
        p['item_id'] for p in sc['eval']['setup']['placements'] if p['kind'] not in BOX_KINDS]
    boxes = scene.config['setup_only']['objects']
    for p in sc['eval']['setup']['placements']:
        if p['kind'] in BOX_KINDS:
            assert boxes[p['item_id']]['kind'] == p['kind']
            assert boxes[p['item_id']]['position_m'][:2] == p['pose_m'][:2]
    assert all(c.kind not in ('can', 'tile', 'tri_frame') for c in scene.cargo)


@pytest.mark.parametrize('sid', IDS)
@pytest.mark.parametrize('condition', MAIN_CONDITIONS)
def test_v6_orders_kinds_prompts_vocabulary_and_candidate_targets(sid, condition, scenarios):
    from harness.zone_study_offline import FixtureActor
    sc = scenarios[sid]
    bundle = env.bundle_for(sc, schematic=False)
    source = inputs.OrderSheetSource(sc, bundle)
    jpeg = b'\xff\xd8offline-bound-frame\xff\xd9'
    ref = inputs.own_rgb_ref('r1', 0, 0., hashlib.sha256(jpeg).hexdigest())
    payload = inputs.build_call_input(robot_id='r1', condition_name=condition,
        request_id='v6-input-1', sim_time_s=0., static_map=inputs.static_map_for_call(bundle),
        source=source, own_rgb_refs=[ref], seed=sc['seeds'][0])
    study = prompts.StudyInputs(payload, wrist_jpeg=jpeg, seed=sc['seeds'][0], pinned=source.pinned)
    kwargs = {'window': {'window_id': 'window-1'}} if condition != 'no_comm' else {}
    request = prompts.build_request(study, **kwargs)
    text = json.dumps(request['messages'], ensure_ascii=False)
    assert not re.search(r'\b(?:can|tile)(?:_\d+)?\b', text)
    assert set(source.sheet()['kinds']) == {o['kind'] for o in sc['orders']}
    assert not {'can', 'tile', 'tri_frame'} & set(study.vocabulary().items)
    # The offline selector consumes the same order list as the decision prompt.
    # Cycle across every candidate, rather than checking only the first order.
    actor = FixtureActor('r1', condition, sc['seeds'][0])
    for i in range(len(sc['orders'])):
        candidate_payload = copy.deepcopy(payload)
        candidate_payload['own_command_history'] = [{}] * i
        assert actor._target_order(candidate_payload)['kind'] in inputs.V6_ITEM_KINDS


@pytest.mark.parametrize('kind', ['can', 'tile', 'tri_frame'])
def test_v6_input_guard_does_not_remove_legacy_catalogue(kind, scenarios):
    sc = copy.deepcopy(scenarios['s1_normal_mixed_v6'])
    sc['orders'][0]['kind'] = kind
    sc['orders'][0]['required_robots'] = inputs.REQUIRED_ROBOTS[kind]
    with pytest.raises(ContractViolation, match='v6 excludes item kinds'):
        inputs.validate_scenario(sc)
    sc['scenario_id'] = sc['scenario_id'][:-3] + '_v5'
    assert inputs.validate_scenario(sc)['orders'][0]['kind'] == kind


def test_mapping_records_new_and_existing_same_colour_zone_groups():
    report = json.loads((ROOT / 'experiments/2026-10-14-scenario-v6/replacements.json').read_text())
    assert len(report['replacements']) == 7
    marked = [r for r in report['replacements'] if r['same_colour_same_zone']]
    assert [(r['scenario_id'], r['old_kind'], r['new_kind']) for r in marked] == [
        ('s1_normal_mixed_v6', 'tile', 'red')]
    assert marked[0]['same_colour_same_zone']['item_ids'] == ['red_1', 'red_2']
    assert len(report['collisions']) == 5  # four pre-existing groups + one new
