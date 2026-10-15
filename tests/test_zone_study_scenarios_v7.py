"""Three offline regressions: v7 inventory, static geometry, XML/input provenance."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

from harness import zone_environment_registry as env
from harness import zone_study_inputs as inputs
from harness import zone_study_prompts_ko as prompts
from harness.static_keepouts import keepout_rects
from harness.zone_scenario_feasibility import (item_rects, landing_fits, passage_fit,
                                               scenario_items, zone_rect)
from harness.zone_study_contract import ContractViolation, MAIN_CONDITIONS
from harness.zone_study_scenarios import load_all, scenario_ids
from harness.zone_team_footprint import pose_clear
from sim.zone_scenario_scene import ScenarioFinalV3Scene

ROOT = Path(__file__).resolve().parents[1]
V6 = ROOT / 'configs/zone_study_scenarios_v6'
V7 = ROOT / 'configs/zone_study_scenarios_v7'
CHANGED = {'s2_unmapped_blockage_v7': 'order-3', 's7_pair_with_solo_v7': 'order-1',
           's8_mixed_tiers_v7': 'order-3'}


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for name in ('mujoco', 'torch', 'sim.multi_masterpi_production'):
        monkeypatch.setitem(sys.modules, name, None)


def test_v7_replaces_all_three_crates_preserving_counts_and_legacy_defaults():
    old, new = load_all(directory=V6), load_all(directory=V7)
    assert len(old) == len(new) == 8
    assert len({seed for s in new.values() for seed in s['seeds']}) == 24
    assert all(not sid.endswith('_v7') for sid in scenario_ids())
    replaced = {}
    for sid, sc in new.items():
        before = old[sid[:-3] + '_v6']
        assert env.load_scenario(sid) == sc
        assert env.load_scenario(before['scenario_id']) == before
        assert sc['seeds'] == before['seeds'] and sc['map_id'] == before['map_id']
        assert sc['eval']['budget'] == before['eval']['budget']
        assert sc['eval']['hidden_events'] == before['eval']['hidden_events']
        assert len(sc['eval']['setup']['placements']) == len(before['eval']['setup']['placements'])
        for a, b in zip(before['orders'], sc['orders']):
            assert {k: v for k, v in a.items() if k not in ('kind', 'item_ids')} == {
                k: v for k, v in b.items() if k not in ('kind', 'item_ids')}
            if a['kind'] == 'heavy_crate':
                assert (a['item_ids'], b['kind'], b['item_ids'], b['required_robots']) == (
                    ['crate_1'], 'long_beam', ['beam_1'], 2)
                replaced[sid] = b['order_id']
            else:
                assert a == b
        for a, b in zip(before['eval']['setup']['placements'], sc['eval']['setup']['placements']):
            if a['kind'] == 'heavy_crate':
                assert b['item_id'] == 'beam_1' and b['kind'] == 'long_beam'
                assert b['slot'] == a['slot'] and b['order_id'] == a['order_id']
                assert b['pose_m'] == [*a['pose_m'][:2], 1.5708]
            else:
                assert a == b
        if sid not in CHANGED:
            expected = copy.deepcopy(before)
            expected['scenario_id'] = sid
            assert sc == expected
    assert replaced == CHANGED
    assert set(inputs.V7_ITEM_KINDS) == {'cyan', 'red', 'green', 'yellow', 'long_beam'}
    for kind in ('heavy_crate', 'can', 'tile', 'tri_frame'):
        invalid = copy.deepcopy(new['s2_unmapped_blockage_v7'])
        invalid['orders'][2]['kind'] = kind
        invalid['orders'][2]['required_robots'] = inputs.REQUIRED_ROBOTS[kind]
        with pytest.raises(ContractViolation, match='v7 excludes item kinds'):
            inputs.validate_scenario(invalid)
        # These kinds remain in the legacy catalogue for replay.
        invalid['scenario_id'] = 'legacy_fixture'
        assert inputs.validate_scenario(invalid)['orders'][2]['kind'] == kind


def test_v7_existing_static_checks_accept_slots_walls_cargo_and_beam_landing():
    for sid, sc in load_all(directory=V7).items():
        report = env.validate(sc)
        assert report.ok, (sid, report.problems)
        scene = ScenarioFinalV3Scene.from_scenario(sid, sc['seeds'][0])
        static = scene.config['static_map']
        items = scenario_items(sc)
        # Same idle-chassis vs cargo check used by test_zone_scenario_scene.
        for spawn in scene.config['setup_only']['spawns'].values():
            for item in items:
                for cx, cy, hx, hy, yaw in item_rects(item.kind, item.pose):
                    dx, dy = spawn[0] - cx, spawn[1] - cy
                    local_x = math.cos(yaw) * dx + math.sin(yaw) * dy
                    local_y = -math.sin(yaw) * dx + math.cos(yaw) * dy
                    assert max(abs(local_x) - hx, 0) ** 2 + max(abs(local_y) - hy, 0) ** 2 > .17 ** 2
        if sid not in CHANGED:
            continue
        beam = next(i for i in items if i.kind == 'long_beam')
        rects = tuple(keepout_rects(static, perimeter=True)) + tuple(
            rect for i in items if i != beam for rect in item_rects(i.kind, i.pose))
        footprint = beam.footprint()
        assert pose_clear(beam.pose, footprint, rects, bounds=static['bounds_m'])
        target = zone_rect(static, beam.destination_zone)
        landing = (*target[:2], math.pi / 2)
        assert landing_fits(beam.kind, landing, target)
        assert pose_clear(landing, footprint, rects, bounds=static['bounds_m'])
        assert passage_fit(static, footprint)['door_wide']['fits']
        invalid = copy.deepcopy(sc)
        next(p for p in invalid['eval']['setup']['placements'] if p['kind'] == 'long_beam')[
            'pose_m'] = [2.2, -2.15, 1.5708]
        # Check that this is a working rejection, not an always-green loader.
        assert not env.validate(invalid).ok


def test_v7_scene_xml_hashes_and_four_condition_requests_exclude_retired_cargo(monkeypatch):
    from sim import research_scene_xml, research_dispatch_arena
    # Existing offline XML fixture: native robot/dispatch template is stubbed;
    # real zone walls, cargo bodies, replicas and contact transforms are used.
    template = ET.Element('mujoco')
    ET.SubElement(template, 'option', timestep='.002')
    world = ET.SubElement(template, 'worldbody')
    ET.SubElement(world, 'geom', name='floor')
    ET.SubElement(world, 'camera', name='cctv_top')
    box = ET.SubElement(world, 'body', name='dispatch_box')
    ET.SubElement(box, 'freejoint', name='dispatch_box_free')
    ET.SubElement(box, 'geom', name='dispatch_box_geom', type='box', size='.03 .02 .016', mass='.03')
    beam = ET.SubElement(world, 'body', name='team_beam')
    ET.SubElement(beam, 'geom', name='team_beam_geom')
    for rid in ('r1', 'r2', 'r3'):
        for side in ('left', 'right'):
            ET.SubElement(world, 'geom', name=f'{rid}__{side}_finger')
    monkeypatch.setattr(research_scene_xml, 'plain_beam_xml', lambda xml: xml)
    monkeypatch.setattr(research_dispatch_arena, 'build_scene_xml',
                        lambda xml, config: (xml, {'robot_xml_sha256': {}}))
    source_xml = ET.tostring(template, encoding='unicode')
    for sid, sc in load_all(directory=V7).items():
        old_id = sid[:-3] + '_v6'
        scene = ScenarioFinalV3Scene.from_scenario(sid, sc['seeds'][0])
        legacy = ScenarioFinalV3Scene.from_scenario(old_id, sc['seeds'][0])
        assert scene.record()['resolved_sha256'] != legacy.record()['resolved_sha256']
        xml = scene.transform(source_xml)
        root = ET.fromstring(xml)
        assert root.find('option').get('noslip_iterations') == '10'
        assert scene.manifest['weld'] == 'off'
        assert scene.manifest['scene_xml_sha256'] == hashlib.sha256(xml.encode()).hexdigest()
        assert scene.manifest['scenario_setup']['config_sha256'] != legacy.config['setup_only']['scenario']['config_sha256']
        assert set(scene.inventory) == {p['item_id'] for p in sc['eval']['setup']['placements']}
        for cargo in scene.cargo:
            assert cargo.kind == 'long_beam'
            body = root.find(f"worldbody/body[@name='{cargo.body}']")
            assert list(map(float, body.get('pos').split()))[:2] == list(cargo.pose[:2])
            assert list(map(float, body.get('quat').split())) == pytest.approx(
                [math.cos(cargo.pose[2] / 2), 0., 0., math.sin(cargo.pose[2] / 2)])
            assert body.find('freejoint').get('name') == cargo.joint
        assert 'crate_1' not in xml
        bundle = env.bundle_for(sc, schematic=False)
        orders = inputs.OrderSheetSource(sc, bundle)
        jpeg = b'\xff\xd8offline-bound-frame\xff\xd9'
        ref = inputs.own_rgb_ref('r1', 0, 0., hashlib.sha256(jpeg).hexdigest())
        for condition in MAIN_CONDITIONS:
            payload = inputs.build_call_input(robot_id='r1', condition_name=condition,
                request_id='v7-input-1', sim_time_s=0., static_map=inputs.static_map_for_call(bundle),
                source=orders, own_rgb_refs=[ref], seed=sc['seeds'][0])
            study = prompts.StudyInputs(payload, wrist_jpeg=jpeg, seed=sc['seeds'][0], pinned=orders.pinned)
            window = {'window': {'window_id': 'window-1'}} if condition != 'no_comm' else {}
            request = prompts.build_request(study, **window)
            assert set(orders.sheet()['kinds']) <= set(inputs.V7_ITEM_KINDS)
            assert not {'heavy_crate', 'can', 'tile', 'tri_frame', 'crate_1'} & set(study.vocabulary().items)
            text = json.dumps(request['messages'], ensure_ascii=False)
            assert all(k not in text for k in ('heavy_crate', 'crate_1', 'pose_m', 'placements', 'hidden_events'))
