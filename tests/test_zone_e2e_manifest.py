"""P07 negative admission and side-effect sentinels; no simulation/model/DB."""
import builtins
import copy
import http.client
import importlib
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import types

import pytest

from harness import zone_e2e_manifest as p
from scripts import plan_zone_e2e as cli


@pytest.fixture(scope='module')
def template():
    return p.build_draft(p.default_options('p07-test-not-reserved'))


@pytest.fixture
def draft(template, tmp_path):
    value = copy.deepcopy(template)
    value['options']['raw_root'] = str(tmp_path / 'outputs')
    return reseal(value)


def reseal(value):
    value['draft_content_sha256'] = p.digest({k: v for k, v in value.items() if k != 'draft_content_sha256'})
    return value


def check(value):
    return p.check_draft(value, primary_outputs=value['options']['raw_root'])


def test_separate_denominators_order_caps_leader_balance_and_no_completion(draft):
    summary = check(draft)
    cohorts = draft['cohorts']
    assert [c['planned_runs'] for c in cohorts] == [4, 4, 24, 72]
    assert len({c['cohort_id'] for c in cohorts}) == 4
    assert len({c['claim_scope'] for c in cohorts}) == 4
    assert all(t['map_id'] == 'zone_wide_door_geometry_v3' for c in cohorts[:2] for t in c['trials'])
    assert [s['step'] for s in summary['execution_order']] == ['C0', 'C1', 'C2', 'C3', 'C4', 'C5a', 'C5b', 'C6', 'C7']
    assert sum(s['sim_cap_s'] for s in summary['execution_order'][:7]) == 39450
    assert summary['total_sim_cap_s'] == 212250
    for cohort in cohorts:
        blocks = {}
        for trial in cohort['trials']:
            key = (trial['scenario_id'], trial['seed'])
            blocks.setdefault(key, []).append(trial['condition'])
        assert all(sorted(c) == sorted(p.CONDITIONS) for c in blocks.values())
        assert cohort['completed_runs'] == 0 and cohort['completed_claims'] == []
    leaders = summary['leader_balance']
    assert leaders[cohorts[2]['cohort_id']] == dict(r1=2, r2=2, r3=2)
    assert leaders[cohorts[3]['cohort_id']] == dict(r1=6, r2=6, r3=6)
    assert sum(leaders[cohorts[0]['cohort_id']].values()) == 1
    assert not Path(draft['options']['raw_root']).exists()
    assert len(summary['raw_destinations']) == len(set(summary['raw_destinations'])) == 228
    assert set(summary) == {'execution_order', 'total_sim_cap_s', 'leader_balance', 'raw_destinations', 'unmet_conditions'}


def test_claims_keep_sources_tests_history_conditions_unknowns_and_approval(draft):
    assert set(draft['claims']) == set(p.CLAIM_IDS)
    for claim in draft['claims'].values():
        for key in ('sources', 'tests', 'existing_results', 'conditions', 'unmeasured'):
            assert claim[key]
        assert claim['execution_approval'] is None and claim['completed'] is False
    unmet = '\n'.join(check(draft)['unmet_conditions'])
    for gate in ('PR292_ACCEPTANCE', 'PR293_CONFIRMATION', 'M1_FINAL', 'M2_FINAL', 'P09_ALL_CAPABILITIES',
                 'P01_SUPPORTED_COMBINATION', 'P03_SUPPORTED_COMBINATION', 'FINAL_FREEZE', 'COST_APPROVAL',
                 'BUNDLE_RESERVATION', 'HOST_ADMISSION', 'STANDARD_ENTRY', 'FINAL_CALIBRATION'):
        assert gate in unmet
    assert draft['physical_ready'] is False and draft['runnable'] is False
    assert all(draft[k] is None for k in ('execution_approval', 'cost_approval', 'execution_source_sha',
                                         'execution_bundle_id', 'bundle_sha256', 'registered'))


@pytest.mark.parametrize('key,value', [
    ('physical_ready', True), ('runnable', True), ('registered', 'today'),
    ('execution_source_sha', '1' * 40), ('execution_bundle_id', 'zone-pair-v83-carry-door-gain'),
    ('bundle_sha256', 'a' * 64), ('execution_approval', {}), ('cost_approval', 'approved'),
    ('status', 'REGISTERED'), ('audit_main_sha', '2' * 40), ('planning_base_sha', '3' * 40),
])
def test_false_completion_approval_and_source_sha_even_rehashed_are_rejected(draft, key, value):
    draft[key] = value
    with pytest.raises(p.PlanError, match='mismatch'):
        check(reseal(draft))


@pytest.mark.parametrize('fault', ['reduced', 'reuse', 'count', 'condition', 'seed', 'map', 'scope', 'leader', 'completed'])
def test_four_dev_runs_cannot_complete_formal_24_or_pilot_72(draft, fault):
    formal = draft['cohorts'][2]
    if fault == 'reduced': formal['trials'] = formal['trials'][:4]
    elif fault == 'reuse': formal['trials'] = copy.deepcopy(draft['cohorts'][0]['trials']) * 6
    elif fault == 'count': formal['planned_runs'] = 4
    elif fault == 'condition': formal['trials'][0]['condition'] = 'reference_R'
    elif fault == 'seed': formal['trials'][0]['seed'] = None
    elif fault == 'map': formal['trials'][0]['map_id'] = 'unknown'
    elif fault == 'scope': draft['cohorts'][0]['claim_scope'] = formal['claim_scope']
    elif fault == 'leader': formal['trials'][0]['leader'] = 'r9'
    else: formal['completed_runs'] = 24
    with pytest.raises(p.PlanError, match='mismatch'):
        check(reseal(draft))


@pytest.mark.parametrize('cid', ['S01', 'PR292_ACCEPTANCE', 'PR293_CONFIRMATION', 'M1_FINAL', 'M2_FINAL', 'C6', 'C7'])
@pytest.mark.parametrize('fault', ['remove', 'null', 'completed', 'approval', 'unit_as_physical'])
def test_missing_gates_and_unit_results_never_imply_physical_ready(draft, cid, fault):
    if fault == 'remove': del draft['claims'][cid]
    elif fault == 'null': draft['claims'][cid]['unmeasured'] = None
    elif fault == 'completed': draft['claims'][cid]['completed'] = True
    elif fault == 'approval': draft['claims'][cid]['execution_approval'] = 'unit tests passed'
    else:
        draft['claims'][cid]['unmeasured'] = []
        draft['claims'][cid]['existing_results'] = ['unit tests passed', 'a' * 64]
    with pytest.raises(p.PlanError, match='mismatch'):
        check(reseal(draft))


@pytest.mark.parametrize('field', [
    'robot_model', 'wall_profile', 'tags', 'render_profile', 'camera', 'pose_provider', 'memory',
    'sensors', 'pair_policy', 'contact_profile', 'weld', 'timing', 'llm', 'sim_cost', 'evaluation', 'environment',
])
def test_every_required_configuration_field_is_hash_bound_and_null_rejected(draft, field):
    previous = draft['draft_content_sha256']
    draft['configuration'][field] = None
    assert reseal(draft)['draft_content_sha256'] != previous
    with pytest.raises(p.PlanError, match='configuration'):
        check(draft)


@pytest.mark.parametrize('field,value', [('memory', 'auto'), ('ultrasonic_front', 'on'),
                                        ('render_profile', 'softshadow_v1'), ('plan_id', '../old'),
                                        ('raw_root', 'outputs'), ('raw_root', '/tmp/../outputs')])
def test_unknown_options_never_fall_back_to_defaults(draft, field, value):
    draft['options'][field] = value
    with pytest.raises(p.PlanError):
        check(reseal(draft))


def test_sensor_and_memory_variants_are_separate_hashes_with_common_four_condition_config(tmp_path):
    off = p.build_draft(p.default_options('p07-off', raw_root=tmp_path))
    on = p.build_draft(p.default_options('p07-on', raw_root=tmp_path, memory='owncam_memory_v3', ultrasonic_front='on_v1'))
    assert off['draft_content_sha256'] != on['draft_content_sha256']
    assert all('sensors' not in trial for c in on['cohorts'] for trial in c['trials'])
    unmet = '\n'.join(p.check_draft(on, primary_outputs=tmp_path)['unmet_conditions'])
    assert 'SENSOR_ON' in unmet and 'MEMORY_ON' in unmet
    assert 'sim/ultrasonic_input.py' in on['runtime_files_sha256']


@pytest.mark.parametrize('target', ['harness/visual_arm.py', 'sim/session_scenes.py',
                                    'configs/vision_loc_worker.json', 'harness/zone_sim_cost.py',
                                    'harness/zone_e2e_manifest.py'])
def test_changed_runtime_or_planner_source_fails_saved_draft(monkeypatch, draft, target):
    original = p.file_sha
    monkeypatch.setattr(p, 'file_sha', lambda root, name: 'a' * 64 if name == target else original(root, name))
    with pytest.raises(p.PlanError, match='mismatch'):
        check(draft)


def test_source_pins_cannot_be_removed_even_with_recomputed_digest(draft):
    del draft['runtime_files_sha256']['sim/session_scenes.py']
    with pytest.raises(p.PlanError, match='runtime_files_sha256'):
        check(reseal(draft))


def test_dynamic_vis3_sources_and_calibrations_are_pinned_without_import(draft):
    pins = draft['runtime_files_sha256']
    for name in ('vision_loc.py', 'vision_pf.py', 'seg_model.py', 'calibration_train.json',
                 'selected_config_v3.json', 'prereg_v3.json'):
        assert 'experiments/2026-09-26-vision-loc/' + name in pins
    assert 'experiments/2026-09-26-markerless-probe/markerless_probe.py' in pins
    assert draft['configuration']['llm']['call_policy']['max_retries'] == 0


def test_existing_provider_allowlist_is_not_final_v3_support(draft):
    contract = draft['support_contracts']['P03']
    assert contract['file']['path'] == p.P03_PATH
    assert contract['status'] == 'blocked' and contract['admitted_combinations'] == []
    rows = {row['map_id']: row for row in contract['combinations']}
    assert 'map outside provider allow-list' in rows['zone_wide_door_geometry_v3']['reasons']
    assert not rows['zone_wide_door_geometry_v2']['supported_for_proposal']
    assert all(not row['supported_for_proposal'] for row in rows.values())


@pytest.mark.parametrize('fault', ['none', 'schema', 'catalog_hash', 'calibration_hash'])
def test_p01_static_contract_pins_and_v2_v3_boundary(tmp_path, template, fault):
    registry = tmp_path / p.P01_PATH
    registry.parent.mkdir()
    (tmp_path / 'catalog.json').write_text('{}')
    (tmp_path / 'calibration.json').write_text('{}')
    data = {'schema': 'ugrp.zone_final_environment_registry.v1', 'status': 'DRAFT_UNSEALED',
            'catalogs': {'final': {'file': 'catalog.json', 'sha256': p.file_sha(tmp_path, 'catalog.json')}},
            'maps': {'zone_wide_door_geometry_v2': {
                'robot_model': 'masterpi_v2', 'wall_profile': 'walls_v3',
                'providers': {'vision_zero_tag_v2': {
                    'supported': True, 'calibration': 'calibration.json',
                    'calibration_sha256': p.file_sha(tmp_path, 'calibration.json')}}}}}
    if fault == 'schema': data['schema'] = 'unknown'
    elif fault == 'catalog_hash': data['catalogs']['final']['sha256'] = 'a' * 64
    elif fault == 'calibration_hash':
        data['maps']['zone_wide_door_geometry_v2']['providers']['vision_zero_tag_v2']['calibration_sha256'] = 'a' * 64
    registry.write_text(json.dumps(data))
    def inspect():
        return p._support_contract(tmp_path, p.P01_PATH, 'P01', template['configuration'],
                                   {'zone_wide_door_geometry_v2', 'zone_wide_door_geometry_v3'})
    if fault != 'none':
        with pytest.raises(p.PlanError, match='schema|hash mismatch'):
            inspect()
    else:
        contract = inspect()
        assert contract['admitted_combinations'] == []
        assert contract['combinations'][0]['reasons'][0] == 'map robot_model differs from proposed masterpi_v3'
        assert 'map not registered' in contract['combinations'][1]['reasons']


def test_missing_owner_contract_and_forged_supported_tuple_never_admit(tmp_path, draft):
    missing = p._support_contract(tmp_path, p.P01_PATH, 'P01', draft['configuration'], {'unknown'})
    assert missing['status'] == 'unavailable' and missing['admitted_combinations'] == []
    draft['support_contracts']['P03']['combinations'][0]['supported_for_proposal'] = True
    with pytest.raises(p.PlanError, match='support_contracts'):
        check(reseal(draft))


@pytest.mark.parametrize('fault', ['map_id', 'map_hash', 'scenario_hash', 'tags'])
def test_map_scenario_mismatch_cannot_be_regenerated(monkeypatch, draft, fault):
    original = p.read_json
    def altered(path):
        data = original(path)
        if Path(path).name == 's1_normal_mixed_v2.json':
            if fault == 'map_id': data['map_id'] = 'zone_wide_two_doors_final_v1'
            elif fault == 'map_hash': data['eval']['setup']['map_file_sha256'] = 'a' * 64
            elif fault == 'tags': data['landmark_detail'] = 'full'
        if fault == 'scenario_hash' and Path(path).as_posix().endswith(p.CATALOG_PATH):
            data['scenarios']['s1_normal_mixed_v2']['file_sha256'] = 'a' * 64
        return data
    monkeypatch.setattr(p, 'read_json', altered)
    with pytest.raises(p.PlanError, match='mismatch'):
        check(draft)


@pytest.mark.parametrize('fault', ['file_hash', 'robot_model'])
def test_v3_map_catalog_mismatch_cannot_be_regenerated(monkeypatch, draft, fault):
    original = p.read_json
    def altered(path):
        data = original(path)
        if fault == 'file_hash' and Path(path).name == 'masterpi_v3_scenes.json':
            data['scenes']['zone_wide_door_geometry_v3']['file_sha256'] = 'a' * 64
        if fault == 'robot_model' and Path(path).name == 'zone_wide_door_geometry_v3.json':
            data['robot_model'] = 'masterpi_v2'
        return data
    monkeypatch.setattr(p, 'read_json', altered)
    with pytest.raises(p.PlanError, match='v3 source/map mismatch'):
        check(draft)


@pytest.mark.parametrize('occupied', ['empty_dir', 'file', 'raw', 'dangling_symlink'])
def test_previous_raw_and_write_conflicts_are_refused_without_modification(draft, occupied):
    target = Path(draft['options']['raw_root']) / draft['options']['plan_id']
    target.parent.mkdir()
    if occupied == 'file': target.write_text('old raw')
    elif occupied == 'dangling_symlink': target.symlink_to(target.parent / 'missing')
    else:
        target.mkdir()
        if occupied == 'raw': (target / 'commands.json').write_text('preserve')
    with pytest.raises(p.PlanError, match='previous raw reuse/write conflict'):
        check(draft)
    if occupied == 'raw': assert (target / 'commands.json').read_text() == 'preserve'


def test_raw_must_be_primary_outputs_and_parent_must_be_directory(draft, tmp_path):
    with pytest.raises(p.PlanError, match='primary checkout'):
        p.check_draft(draft, primary_outputs=tmp_path / 'other')
    Path(draft['options']['raw_root']).write_text('not a folder')
    with pytest.raises(p.PlanError, match='not a directory'):
        check(draft)


def test_exclusive_draft_write_preserves_old_prereg_and_refuses_raw_path(draft, tmp_path):
    old = tmp_path / 'prereg.json'
    old.write_bytes(b'original prereg\n')
    with pytest.raises(p.PlanError, match='write conflict'):
        cli.write_new_draft(old, draft)
    assert old.read_bytes() == b'original prereg\n'
    raw = Path(draft['options']['raw_root']) / draft['options']['plan_id'] / 'draft.json'
    with pytest.raises(p.PlanError, match='outside'):
        cli.write_new_draft(raw, draft)
    assert not raw.parent.exists()


@pytest.mark.parametrize('text', ['{"status":"DRAFT","status":"REGISTERED"}', '{"x":NaN}', '{"x":Infinity}'])
def test_ambiguous_or_nonfinite_json_is_rejected(tmp_path, text):
    path = tmp_path / 'bad.json'
    path.write_text(text)
    with pytest.raises(p.PlanError):
        p.read_json(path)


def test_dry_run_fresh_import_has_no_world_worker_network_process_database_or_write(monkeypatch, template, tmp_path, capsys):
    path = tmp_path / 'draft.json'
    path.write_text(json.dumps(template))
    def forbidden(*args, **kwargs):
        raise AssertionError('World/worker/network/process/database/write sentinel reached')
    for name in ('Popen', 'run', 'check_output', 'call'):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(http.client.HTTPConnection, 'connect', forbidden)
    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    monkeypatch.setattr(Path, 'mkdir', forbidden)
    original_open = builtins.open
    original_path_open = Path.open
    def guard_open(file, mode='r', *args, **kwargs):
        if any(flag in mode for flag in 'wax+'):
            forbidden()
        return original_open(file, mode, *args, **kwargs)
    def guard_path_open(self, mode='r', *args, **kwargs):
        if any(flag in mode for flag in 'wax+'):
            forbidden()
        return original_path_open(self, mode, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', guard_open)
    monkeypatch.setattr(Path, 'open', guard_path_open)
    original_import = builtins.__import__
    def no_runtime(name, *args, **kwargs):
        if name.startswith(('sim', 'mujoco', 'torch', 'harness.vision_pose_source',
                            'harness.vision_loc', 'scripts.run_zone_study', 'harness.zone_main_budget')):
            forbidden()
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', no_runtime)
    for name in ('sim.world', 'mujoco', 'harness.vision_pose_source', 'harness.vision_loc_worker'):
        fake = types.ModuleType(name)
        fake.World = fake.Renderer = fake.VisionPoseSourceV2 = fake.VisionWorkerClient = forbidden
        monkeypatch.setitem(sys.modules, name, fake)
    importlib.reload(p)
    importlib.reload(cli)
    assert cli.main(['dry-run', str(path)]) == 3
    summary = json.loads(capsys.readouterr().out)
    assert summary['unmet_conditions'] and summary['total_sim_cap_s'] == 212250


def test_cli_has_no_execute_seal_approval_or_budget_creation_options(capsys):
    for argv in (['execute'], ['seal'], ['dry-run', 'x', '--execute'],
                 ['draft', '--plan-id', 'p07-test', '--output', 'x', '--create-budget']):
        with pytest.raises(SystemExit) as error:
            cli.main(argv)
        assert error.value.code == 2
    capsys.readouterr()
