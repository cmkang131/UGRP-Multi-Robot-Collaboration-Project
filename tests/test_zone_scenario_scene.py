"""Offline authored setup only: no MuJoCo imports, rendering, stepping or models."""
import copy
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import zone_environment_registry as registry
from harness.zone_map_schematic import pickup_bays
from harness.zone_study_scenarios import half_footprint, public_part
from sim.session_scenes import Scene
from sim.zone_arena import BOX_HALF, COLORS
from sim.zone_environment_scene_provider import scenario_scene
from sim.zone_final_v3_scene import FinalV3Scene
from sim.zone_scenario_scene import ScenarioFinalV3Scene, load_scenario, scene_spec

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ['dev_s1lite', *sorted(p.stem for p in (ROOT / 'configs/zone_study_scenarios_v4').glob('*.json'))]


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for name in ('mujoco', 'torch', 'sim.multi_masterpi_production'):
        monkeypatch.setitem(sys.modules, name, None)


@pytest.mark.parametrize('sid', SCENARIOS)
def test_exact_colour_and_catalogue_placement_on_three_robot_scene(sid):
    scenario = load_scenario(sid)
    scene = scenario_scene(sid, 911)
    assert isinstance(scene, (Scene, FinalV3Scene, ScenarioFinalV3Scene))
    setup = scene.config['setup_only']
    placements = scenario['eval']['setup']['placements']
    expected = {p['item_id']: p for p in placements}
    assert set(scene.inventory) == set(expected)
    assert set(setup['spawns']) == {'r1', 'r2', 'r3'}
    assert scene.config['robot_model'] == 'masterpi_v3'
    assert scene.scene['contact_profile'] == 'cargo_noslip_v1'
    assert len(setup['objects']) + len(scene.cargo) == len(expected)
    for oid, obj in setup['objects'].items():
        p = expected[oid]
        assert obj['kind'] == p['kind']
        assert obj['position_m'] == [*p['pose_m'][:2], BOX_HALF[2]]
        assert obj['half_extents_m'] == list(BOX_HALF)
        assert obj['body_name'] == 'cargo_' + oid and obj['joint_name'] == 'cargo_' + oid + '_free'
    assert {c.item_id: (c.kind, list(c.pose)) for c in scene.cargo} == {
        p['item_id']: (p['kind'], p['pose_m']) for p in placements if p['kind'] not in COLORS}
    source = registry.static_map_path(scenario['map_id'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == setup['scenario']['map_file_sha256']
    assert scene.config['static_map'] == registry.resolve_static_map(scenario['map_id'])[0]
    # The existing placement check accepts the instantiated inventory, without a World.
    from scripts.run_zone_study_integration import placements_match
    placements_match(scenario, SimpleNamespace(objects=setup['objects'], spec=scene.spec))


@pytest.mark.parametrize('sid', SCENARIOS)
def test_authored_footprints_do_not_overlap_and_stay_in_static_slots(sid):
    scenario = load_scenario(sid)
    scene = scenario_scene(scenario, 911)
    slots = {s['slot_id']: s for b in pickup_bays(scene.config['static_map']) for s in b['slots']}
    rects = []
    for p in scenario['eval']['setup']['placements']:
        x, y, yaw = p['pose_m']
        hx, hy = half_footprint(p['kind'], yaw)
        slot = slots[p['slot']]
        assert abs(x - slot['center_m'][0]) + hx <= slot['half_extents_m'][0]
        assert abs(y - slot['center_m'][1]) + hy <= slot['half_extents_m'][1]
        for ox, oy, ohx, ohy in rects:
            assert abs(x - ox) >= hx + ohx or abs(y - oy) >= hy + ohy
        rects.append((x, y, hx, hy))
    for spawn in scene.config['setup_only']['spawns'].values():
        # Static idle chassis disc; no runtime or measured pose is consulted.
        for x, y, hx, hy in rects:
            dx, dy = max(abs(spawn[0] - x) - hx, 0), max(abs(spawn[1] - y) - hy, 0)
            assert dx * dx + dy * dy > .17 ** 2


def test_dev_fixture_has_two_orders_ew_beam_to_b_and_one_cyan():
    s = load_scenario('dev_s1lite')
    assert [(o['kind'], o['count'], o['destination_zone']) for o in s['orders']] == [
        ('cyan', 1, 'A'), ('long_beam', 1, 'B')]
    assert scene_spec(s, 911)['team_cargo'] == [
        {'item_id': 'beam_1', 'kind': 'long_beam', 'pose': [1.275, .05, 0.]}]


@pytest.mark.parametrize('change,needle', [
    ('hash', 'map_file_sha256'), ('overlap', 'within'), ('slot', 'not inside'),
    ('yaw', 'zero setup yaw'), ('weld', 'weld'), ('model', 'allow-listed')])
def test_bad_setup_is_refused_before_scene_construction(change, needle):
    s = load_scenario('s1_normal_mixed_v4')
    setup = s['eval']['setup']
    if change == 'hash':
        setup['map_file_sha256'] = '0' * 64
    elif change == 'overlap':
        setup['placements'][1]['pose_m'] = list(setup['placements'][0]['pose_m'])
    elif change == 'slot':
        setup['placements'][0]['pose_m'] = [1.6, -2.45, 0.]
    elif change == 'yaw':
        setup['placements'][0]['pose_m'][2] = .1
    elif change == 'weld':
        setup['weld'] = 'on'
    else:
        s['map_id'] = 'zone_wide_door_geometry_v2'
    with pytest.raises(ValueError, match=needle):
        scenario_scene(s, 911)


def test_colour_coordinates_are_seed_independent_and_never_projected_to_robot_inputs():
    s = load_scenario('s1_normal_mixed_v4')
    original = copy.deepcopy(s)
    a, b = scenario_scene(s, 601), scenario_scene(s, 602)
    assert a.config['setup_only']['objects'] == b.config['setup_only']['objects']
    assert s == original
    bundle = registry.bundle_for(s)
    text = json.dumps({'orders': public_part(s), 'map': bundle['public_map']})
    assert all(key not in text for key in ('pose_m', 'position_m', 'placements', 'spawns', 'hidden_events'))


def test_legacy_final_scene_keeps_pair_only_and_random_box_behavior():
    spec = {'map': 'zone_wide_door_geometry_v3', 'seed': 911, 'goal': {'A': {'cyan': 1}},
            'team_cargo': [{'item_id': 'beam', 'kind': 'long_beam', 'pose': [1., .05, 0.]}]}
    pair = FinalV3Scene.from_spec(spec, 'local_contact_fine')
    assert pair.config['setup_only']['objects'] == {} and pair.inventory == []
    solo = FinalV3Scene.from_spec({**spec, 'team_cargo': []}, 'local_contact_fine')
    assert list(solo.config['setup_only']['objects']) == ['box_00']
    assert 'scenario' not in solo.config['setup_only']


@pytest.mark.parametrize('sid', ['dev_s1lite', 's1_normal_mixed_v4', 's5_moved_dropped_item_v4',
                                's8_mixed_tiers_v4'])
def test_xml_contains_colours_catalogue_poses_and_contact_pairs_without_native_model(sid, monkeypatch):
    # Only the upstream robot/dispatch template is fake. Exercise the real zone
    # replicas, catalogue XML and contact transforms; never compile/step a model.
    from sim import research_scene_xml, research_dispatch_arena
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
            ET.SubElement(world, 'geom', name=rid + '__' + side + '_finger')
    monkeypatch.setattr(research_scene_xml, 'plain_beam_xml', lambda xml: xml)
    monkeypatch.setattr(research_dispatch_arena, 'build_scene_xml',
                        lambda xml, config: (xml, {'robot_xml_sha256': {}}))
    scene = scenario_scene(sid, 911)
    xml = scene.transform(ET.tostring(template, encoding='unicode'))
    root = ET.fromstring(xml)
    assert root.find('option').get('noslip_iterations') == '10'
    assert scene.manifest['weld'] == 'off'
    assert scene.manifest['scene_xml_sha256'] == hashlib.sha256(xml.encode()).hexdigest()
    for oid, obj in scene.config['setup_only']['objects'].items():
        body = root.find(f"worldbody/body[@name='{obj['body_name']}']")
        assert list(map(float, body.get('pos').split())) == obj['position_m']
        assert body.find('freejoint').get('name') == obj['joint_name']
        geom = body.find('geom')
        assert geom.get('rgba') == COLORS[obj['kind']]
        assert len(root.findall(f"contact/pair[@geom2='{geom.get('name')}']")) == 6
    for cargo in scene.cargo:
        body = root.find(f"worldbody/body[@name='{cargo.body}']")
        assert list(map(float, body.get('pos').split()))[:2] == list(cargo.pose[:2])
        assert body.find('freejoint').get('name') == cargo.joint
    assert len(root.findall('worldbody/body')) == len(scene.inventory) + 2  # two hidden prototypes


def test_ci_collects_scenario_scene_file():
    from scripts.run_ci_tests import TEST_PATTERNS
    assert 'tests/test_zone_scenario_scene.py' in TEST_PATTERNS
