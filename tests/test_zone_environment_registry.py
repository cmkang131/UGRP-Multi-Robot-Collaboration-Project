"""P01 file/fake-factory seams. No Scene/World construction or model execution.

The all-scenario bundle test uses an explicitly fake P03 support decision and
host-spec factory; production rejects unregistered maps/calibrations. It proves
file routing only, never cargo/physical support or localisation quality.
"""
import copy
import hashlib
import importlib
import json
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import zone_environment_registry as env
from harness import zone_final_env as fe
from harness import zone_study_scenarios as scenarios
from harness.zone_map_schematic import digest, map_bundle
from scripts import run_zone_study_integration as legacy_runner
from scripts import zone_environment_bundle as runner
from sim.zone_environment_scene_provider import own_scene, scene_static_map

ROOT = env.ROOT
CATALOG = json.loads(fe.CATALOG_PATH.read_text())
CALIBRATION = 'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json'


@pytest.fixture(autouse=True)
def no_runtime_side_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('P01 forbids renderer/Scene/World/worker/network construction')
    for module in ('mujoco', 'torch', 'sim.multi_masterpi_production'):
        monkeypatch.setitem(sys.modules, module, None)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    from harness import zone_map_schematic
    monkeypatch.setattr(zone_map_schematic, 'render_schematic', forbidden)
    from sim.session_scenes import Scene
    monkeypatch.setattr(Scene, '__init__', forbidden)
    monkeypatch.setattr(legacy_runner, 'StudyTeamHost', forbidden)
    monkeypatch.setattr(runner.zi, 'build_pose_provider', forbidden)
    from harness.vision_loc_client import VisionWorkerClient, InProcessWorker
    monkeypatch.setattr(VisionWorkerClient, '__init__', forbidden)
    monkeypatch.setattr(InProcessWorker, '__init__', forbidden)
    monkeypatch.setattr(VisionWorkerClient, 'observe', forbidden)
    monkeypatch.setattr(InProcessWorker, 'observe', forbidden)
    from harness.wall_tags import TagDetector
    monkeypatch.setattr(TagDetector, 'detect', forbidden)


@pytest.mark.parametrize('map_id', sorted(CATALOG['maps']))
def test_three_final_maps_share_pinned_resolver_and_fake_scene_factory(map_id):
    static, file_sha = env.resolve_static_map(map_id)
    pin = CATALOG['maps'][map_id]
    assert file_sha == pin['file_sha256'] and digest(static) == pin['static_map_sha256']
    assert scene_static_map(map_id) == static
    assert fe.maps_dir_for(map_id) == env.maps_dir_for(map_id)
    entry = env.environment_entry(map_id)
    assert entry['robot_model'] == 'masterpi_v2' and entry['wall_profile'] == 'walls_v3'
    assert entry['research_result'] is False
    module, _, name = entry['scene_factory'].partition(':')
    from sim.session_scenes import Scene
    assert issubclass(getattr(importlib.import_module(module), name), Scene)
    assert name == ('GeometryCargoZoneScene' if map_id == 'zone_wide_door_geometry_v2'
                    else 'FinalGeometryCargoZoneScene')
    seen, sentinel = [], object()
    def fake_factory(spec, profile):
        seen.append((copy.deepcopy(spec), profile))
        return sentinel
    spec = {'map': map_id, 'seed': 700, 'goal': {'A': {'cyan': 1}},
            'robot_model': 'masterpi_v2', 'static_map_sha256': pin['static_map_sha256']}
    assert own_scene(spec, 'cargo_noslip_v1', scene_factory=fake_factory) is sentinel
    assert seen == [(spec, 'local_contact_fine')]


@pytest.mark.parametrize('sid', sorted(CATALOG['scenarios']))
def test_six_scenarios_validate_and_project_through_opt_in_adapter(sid):
    scenario = scenarios.load(sid, directory=fe.V2_SCENARIO_DIR)
    report = env.validate(scenario)
    assert report.ok, report.problems
    bundle = env.bundle_for(scenario)
    assert bundle == scenarios.bundle_for(scenario, maps_dir=fe.maps_dir_for(scenario['map_id']))
    assert bundle['map_file'] == CATALOG['maps'][scenario['map_id']]['file']
    assert bundle['public_map_sha256'] == CATALOG['maps'][scenario['map_id']]['public_map_sha256']
    assert hashlib.sha256((fe.V2_SCENARIO_DIR / f'{sid}.json').read_bytes()).hexdigest() == CATALOG['scenarios'][sid]['file_sha256']


@pytest.mark.parametrize('mid', ['missing', '../zone_wide_door', '', None])
def test_unknown_or_unsafe_maps_are_refused_before_factory(mid):
    with pytest.raises((ValueError, OSError)):
        own_scene({'map': mid, 'seed': 700, 'goal': {}}, 'cargo_noslip_v1',
                  scene_factory=lambda *a: pytest.fail('unknown map reached factory'))
    assert not env.validate({'schema': scenarios.SCENARIO_SCHEMA, 'map_id': mid}).ok


@pytest.mark.parametrize('override', [{'robot_model': 'masterpi_v3'}, {'robot_model': 'unknown'},
                                     {'static_map_sha256': '0' * 64}])
def test_wrong_map_model_or_hash_stops_fake_scene_factory(override):
    with pytest.raises(ValueError, match='mismatch'):
        own_scene({'map': 'zone_wide_two_doors_final_v1', **override}, 'cargo_noslip_v1',
                  scene_factory=lambda *a: pytest.fail('invalid identity reached factory'))


def _copy_contract(tmp_path):
    names = [env.REGISTRY_FILE, *[r['file'] for r in env.registry()['catalogs'].values()],
             *[r['file'] for r in CATALOG['maps'].values()], CALIBRATION]
    for name in names:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())


@pytest.mark.parametrize('changed', ['map', 'catalog', 'static_pin'])
def test_changed_file_catalog_or_static_pin_is_refused(tmp_path, changed):
    _copy_contract(tmp_path)
    mid = 'zone_wide_two_doors_final_v1'
    if changed == 'map':
        path = env.static_map_path(mid, root=tmp_path)
        path.write_bytes(path.read_bytes() + b' ')
    else:
        path = tmp_path / 'maps/zones_final/catalog.json'
        catalog = json.loads(path.read_text())
        catalog['maps'][mid]['static_map_sha256'] = '0' * 64
        path.write_text(json.dumps(catalog))
        if changed == 'static_pin':
            reg_path = tmp_path / env.REGISTRY_FILE
            reg = json.loads(reg_path.read_text())
            reg['catalogs']['final']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            reg_path.write_text(json.dumps(reg))
    with pytest.raises(ValueError, match='hash mismatch'):
        env.resolve_static_map(mid, root=tmp_path)


def test_registry_cannot_relabel_an_implicit_v2_map_as_robot_v3(tmp_path):
    _copy_contract(tmp_path)
    path = tmp_path / env.REGISTRY_FILE
    value = json.loads(path.read_text())
    value['maps']['zone_wide_two_doors_final_v1']['robot_model'] = 'masterpi_v3'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='map/model mismatch'):
        env.resolve_static_map('zone_wide_two_doors_final_v1', root=tmp_path)


def test_existing_v2_support_is_calibration_pinned_and_v3_is_refused(tmp_path):
    mid = 'zone_wide_door_geometry_v2'
    provider = runner.zi.pose_provider_spec('vision_zero_tag_v2', map_id=mid)
    binding = env.provider_binding(mid, provider, CALIBRATION)
    assert binding['status'] == 'DRAFT_UNSEALED' and not binding['research_result']
    with pytest.raises(ValueError, match='calibration'):
        env.provider_binding(mid, provider, 'experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json')
    _copy_contract(tmp_path)
    (tmp_path / CALIBRATION).write_bytes(b'{}')
    with pytest.raises(ValueError, match='calibration'):
        env.provider_binding(mid, provider, CALIBRATION, root=tmp_path)
    for v3 in ('zone_wide_door_geometry_v3', 'zone_wide_door_geometry_v3_dock_v1'):
        assert env.resolve_static_map(v3)[0]['robot_model'] == 'masterpi_v3'
        with pytest.raises(ValueError, match='v2 motion/camera'):
            env.provider_binding(v3, provider, CALIBRATION)


@pytest.mark.parametrize('mid', ['zone_wide_two_doors_final_v1', 'zone_wide_corridor_final_v1'])
def test_new_map_provider_support_is_explicitly_blocked_even_with_fake_allowlist(mid):
    provider = runner.zi.pose_provider_spec('vision_zero_tag_v2', map_id='zone_wide_door_geometry_v2')
    provider['maps'].append(mid)
    with pytest.raises(ValueError, match='not validated'):
        env.provider_binding(mid, provider, CALIBRATION)
    with pytest.raises(runner.zi.ContractViolation, match='not registered'):
        runner.zi.pose_provider_spec('vision_zero_tag_v2', map_id=mid)


def test_tagged_map_cannot_enter_tagfree_provider_even_if_allowlist_claims_support():
    provider = runner.zi.pose_provider_spec('vision_zero_tag_v2', map_id='zone_wide_door_geometry_v2')
    provider['maps'].append('zone_wide_door_tags_v2')
    with pytest.raises(ValueError, match='map with landmarks'):
        env.provider_binding('zone_wide_door_tags_v2', provider, CALIBRATION)


def test_legacy_tag_input_bytes_and_all_249_frozen_files_stay_identical():
    legacy = json.loads((ROOT / 'configs/masterpi_v3_scenes.json').read_text())
    for name, expected in legacy['legacy_files_sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    scenario = json.loads((ROOT / 'configs/zone_study_integration/i1_cyan_three_slots.json').read_text())
    before = map_bundle(scenario['map_id'], landmark_detail=scenario['landmark_detail'], schematic=False)
    after = scenarios.bundle_for(scenario)
    assert json.dumps(before, sort_keys=True).encode() == json.dumps(after, sort_keys=True).encode()


@pytest.mark.parametrize('sid', sorted(CATALOG['scenarios']))
def test_all_scenario_bundle_file_routing_with_fake_p03_and_host_seams(monkeypatch, sid):
    """No actual provider support is added; cargo capability remains P02/P09."""
    reg = env.registry()
    for row in reg['maps'].values():
        if row['robot_model'] == 'masterpi_v2':
            row['providers']['vision_zero_tag_v2'] = copy.deepcopy(
                reg['maps']['zone_wide_door_geometry_v2']['providers']['vision_zero_tag_v2'])
    monkeypatch.setattr(env, 'registry', lambda root=ROOT: copy.deepcopy(reg))
    provider = runner.zi.pose_provider_spec('vision_zero_tag_v2', map_id='zone_wide_door_geometry_v2')
    provider['maps'] = list(CATALOG['maps'])
    monkeypatch.setattr(runner.zi, 'pose_provider_spec', lambda *a, **k: copy.deepcopy(provider))
    monkeypatch.setattr(runner, 'host_spec', lambda scenario, episode, bundle: {'fake_setup': True})
    pre = legacy_runner.load_prereg(ROOT / 'configs/zone_study_integration/pair_dev_DRAFT.json')
    pre['pose_provider'] = provider['provider_id']
    pre['student']['calibration'] = CALIBRATION
    episode = copy.deepcopy(pre['episodes'][0])
    scenario = scenarios.load(sid, directory=fe.V2_SCENARIO_DIR)
    episode.update(map=scenario['map_id'], scenario=f'configs/zone_study_scenarios_v2/{sid}.json',
                   base_map=CATALOG['maps'][scenario['map_id']]['base_map']['map_id'])
    bundle, _, public, _ = runner.run_bundle(pre, episode)
    assert bundle['map_file_sha256'] == public['map_file_sha256'] == CATALOG['scenarios'][sid]['map_file_sha256']
    assert bundle['scene_static_map_sha256'] == CATALOG['maps'][scenario['map_id']]['static_map_sha256']
    entry = bundle['environment_binding']
    assert entry['robot_model'] == 'masterpi_v2' and entry['status'] == 'DRAFT_UNSEALED'
    for name in (env.REGISTRY_FILE, entry['catalog_file'], entry['map_file'],
                 entry['scene_factory'].partition(':')[0].replace('.', '/') + '.py'):
        assert name in bundle['runtime_files_sha256']


def test_runner_refuses_scenario_episode_map_disagreement():
    pre = legacy_runner.load_prereg(ROOT / 'configs/zone_study_integration/pair_dev_DRAFT.json')
    episode = {**pre['episodes'][0], 'map': 'zone_wide_corridor_final_v1'}
    with pytest.raises(SystemExit, match='scenario map_id'):
        runner.run_bundle(pre, episode)


@pytest.mark.parametrize('changed', [env.REGISTRY_FILE, 'maps/zones_final/catalog.json'])
def test_environment_configuration_is_pinned_even_on_legacy_tagged_bundle(monkeypatch, changed):
    pre = legacy_runner.load_prereg(ROOT / 'configs/zone_study_integration/pair_dev_DRAFT.json')
    original = runner.run_bundle(pre, pre['episodes'][0])[0]
    assert changed in original['runtime_files_sha256']
    file_sha = runner.zi.file_sha256
    monkeypatch.setattr(runner.zi, 'file_sha256', lambda p: 'f' * 64 if Path(p) == ROOT / changed else file_sha(p))
    mutated = runner.run_bundle(pre, pre['episodes'][0])[0]
    assert runner.digest(original) != runner.digest(mutated)
    assert 'environment_binding' not in original


@pytest.mark.parametrize('mid', ['zone_wide_door_geometry_v3', 'zone_wide_door_geometry_v3_dock_v1'])
def test_v3_scene_model_and_injected_class_are_checked_before_construction(mid):
    with pytest.raises(ValueError, match='map/model mismatch'):
        own_scene({'map': mid, 'robot_model': 'masterpi_v2'}, 'cargo_noslip_v1',
                  scene_factory=lambda *a: pytest.fail('v3 mismatch reached factory'))
    with pytest.raises(ValueError, match='registered v3 Scene'):
        own_scene({'map': mid}, 'cargo_noslip_v1', scene=SimpleNamespace())


def test_final_scene_resolve_uses_base_contract_without_constructing_scene(monkeypatch):
    from sim.zone_final_scene import FinalGeometryCargoZoneScene, CargoZoneScene
    for mid in ('zone_wide_two_doors_final_v1', 'zone_wide_corridor_final_v1'):
        static, _ = env.resolve_static_map(mid)
        base, _ = env.resolve_static_map(static['base_map']['map_id'])
        reads = []
        fake = SimpleNamespace(selection='zones/' + mid, config={}, cargo=[], inventory=[],
                               _read=lambda path: reads.append(str(path)), _verify_camera=lambda: None)
        def resolve_base(scene):
            assert scene.selection == 'zones/' + static['base_map']['map_id']
            scene.config = {'static_map': base}
        monkeypatch.setattr(CargoZoneScene, '_resolve', resolve_base)
        FinalGeometryCargoZoneScene._resolve(fake)
        assert fake.selection == 'zones/' + mid
        assert fake.config['static_map'] == static and fake.bounds == static['bounds_m']
        assert str(env.static_map_path(mid)) in reads


def test_ci_collects_the_new_contract_file():
    from scripts.run_ci_tests import TEST_PATTERNS
    assert 'tests/test_zone_environment_registry.py' in TEST_PATTERNS


@pytest.mark.parametrize('use_adapter', [False, True])
def test_review_a305_1_dock_reaches_existing_factory(monkeypatch, use_adapter):
    from sim.zone_dock_scene import DockTaggedCargoZoneScene
    from sim.zone_start_dock import MAP_ID, dock_map
    from sim.zone_own_scene_provider import own_scene as legacy_scene
    calls, sentinel = [], object()
    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel
    monkeypatch.setattr(DockTaggedCargoZoneScene, 'from_tagged_cargo', fake)
    spec = {'map': MAP_ID, 'seed': 911, 'goal': {}, 'team_cargo': [{'item_id': 'beam'}]}
    assert env.resolve_static_map(MAP_ID)[0] == dock_map()
    assert (own_scene if use_adapter else legacy_scene)(spec, 'cargo_noslip_v1') is sentinel
    assert len(calls) == 1 and calls[0][0] == (MAP_ID, 911)
    assert calls[0][1]['contact_profile'] == 'local_contact_fine'


def test_review_a305_2_v6e_pinned_sources_and_legacy_closure_remain_unchanged():
    from harness.python_source_closure import source_closure
    pre = json.loads((ROOT / 'experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json').read_text())
    for name, expected in pre['v6_contract']['source_sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    # A305-3's hidden #292 dependency disappears from the legacy import graph.
    closure = source_closure(ROOT, legacy_runner.RUNTIME_ENTRY_POINTS)
    assert 'harness/zone_environment_registry.py' not in closure
    assert 'sim/zone_environment_scene_provider.py' not in closure


@pytest.mark.parametrize('mid', [
    'zone_wide_door_tags_v2_dock_v3', 'zone_wide_door_geometry_v2',
    'zone_wide_two_doors_final_v1', 'zone_wide_corridor_final_v1',
    'zone_wide_door_geometry_v3', 'zone_wide_door_geometry_v3_dock_v1',
])
def test_review_a305_3_composed_candidate_explicitly_pins_environment_inputs(mid):
    from harness.zone_environment_candidate import candidate_contract, verify_candidate_contract
    path = 'scripts/run_zone_study_integration.py'
    base = {'source_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()},
            'policy': 'unsealed-preview'}
    original = copy.deepcopy(base)
    candidate = candidate_contract(base, mid)
    assert base == original and candidate['base_contract'] == base
    assert candidate['base_contract'] is not base
    assert verify_candidate_contract(candidate, base) == candidate
    pins = candidate['source_sha256']
    assert env.REGISTRY_FILE in pins and 'maps/zones_final/catalog.json' in pins
    assert env.static_map_path(mid).relative_to(ROOT).as_posix() in pins
    entry = env.environment_entry(mid)
    if entry:
        module = entry['scene_factory'].partition(':')[0]
        assert candidate['dynamic_imports'] == [module]
        assert module.replace('.', '/') + '.py' in pins
    assert not candidate['runnable'] and not candidate['research_result']


def test_environment_candidate_rejects_a_stale_base_source():
    from harness.zone_environment_candidate import candidate_contract
    base = {'source_sha256': {'scripts/run_zone_study_integration.py': '0' * 64}}
    with pytest.raises(ValueError, match='base candidate source hash mismatch'):
        candidate_contract(base, 'zone_wide_door_tags_v2_dock_v3')


def test_opt_in_validator_does_not_fall_back_when_registry_is_invalid(monkeypatch):
    scenario = json.loads((ROOT / 'configs/zone_study_integration/i1_cyan_three_slots.json').read_text())
    def invalid(root=ROOT):
        raise ValueError('invalid unsealed environment registry')
    monkeypatch.setattr(env, 'registry', invalid)
    report = env.validate(scenario)
    assert not report.ok and 'invalid unsealed environment registry' in str(report.problems)
    assert not env.validate(None).ok


@pytest.mark.parametrize('changed', [
    env.REGISTRY_FILE, 'maps/zones_final/catalog.json', 'configs/masterpi_v3_scenes.json',
    'maps/zones_final/zone_wide_two_doors_final_v1.json',
    'sim/zone_final_scene.py', 'sim/zone_environment_scene_provider.py',
])
def test_review_a305_3_candidate_rejects_each_mutated_dependency(tmp_path, changed):
    from harness.zone_environment_candidate import candidate_contract, verify_candidate_contract
    mid = 'zone_wide_two_doors_final_v1'
    base = {'candidate': 'v6h-preview'}
    candidate = candidate_contract(base, mid)
    assert changed in candidate['source_sha256']
    for name in candidate['source_sha256']:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    assert verify_candidate_contract(candidate, base, root=tmp_path) == candidate
    path = tmp_path / changed
    if changed == env.REGISTRY_FILE:
        reg = json.loads(path.read_text())
        reg['status'] = 'INVALID'
        path.write_text(json.dumps(reg))
    else:
        path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='environment source hash mismatch'):
        verify_candidate_contract(candidate, base, root=tmp_path)


def test_review_a305_3_candidate_rejects_missing_pins_and_changed_base():
    from harness.zone_environment_candidate import candidate_contract, verify_candidate_contract
    base = {'candidate': 'v6h-preview'}
    candidate = candidate_contract(base, 'zone_wide_door_tags_v2_dock_v3')
    with pytest.raises(ValueError, match='candidate contract mismatch'):
        verify_candidate_contract(candidate, {'candidate': 'different'})
    del candidate['source_sha256'][env.REGISTRY_FILE]
    with pytest.raises(ValueError, match='candidate contract mismatch'):
        verify_candidate_contract(candidate, base)


def test_environment_bundle_preview_cannot_inherit_registered_execution_id():
    pre = legacy_runner.load_prereg(ROOT / 'configs/zone_study_integration/pair_dev_DRAFT.json')
    preview = runner.run_bundle(pre, pre['episodes'][0])[0]
    assert preview['execution_bundle_id'] is None
    assert preview['base_execution_bundle_id'] == legacy_runner.zi.EXECUTION_BUNDLE_ID
    assert preview['status'] == 'DRAFT_UNSEALED' and preview['runnable'] is False
    assert preview['environment_contract']['source_sha256'].items() <= preview['runtime_files_sha256'].items()
