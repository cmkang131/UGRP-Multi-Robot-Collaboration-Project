"""v2 seal mutations, offline only; legacy verification is tested separately."""
import copy
import json
from pathlib import Path
import shutil

import pytest

from harness.execution_dependency_contract import (ROOT, SCHEMA, SPEC_SCHEMA, VERIFIER_SOURCES, WORKFLOW_SOURCES,
                                                  build_contract, digest, read_json,
                                                  verify_contract, workflow_spec)
from scripts.build_execution_dependency_contract import main


@pytest.fixture
def candidate(tmp_path):
    files = {
        'entry.py': 'from pkg import policy\nraise AssertionError("do not execute the policy")\n',
        'pkg/__init__.py': 'from . import init_dep\n',
        'pkg/init_dep.py': 'VALUE = 1\n',
        'pkg/policy.py': 'def tick():\n from . import helper\n',
        'pkg/helper.py': 'VALUE = 2\n',
        'worker.py': 'from pkg import policy\n',
        'unused.py': 'VALUE = 3\n',
        'calibration.json': '{"gain": 1}',
        'configs/simulation_workflows.json': json.dumps({
            'schema': 'ugrp.local_workflow_catalog.v1', 'workflows': [
                {'id': 'used', 'entry': 'entry.py', 'runner': 'entry', 'version': '1', 'args': {'gain': 1}},
                {'id': 'unrelated', 'entry': 'unused.py', 'runner': 'unused', 'version': '1'}]}),
    }
    catalog = json.loads(files['configs/simulation_workflows.json'])
    for row in catalog['workflows']:
        row.update(output_flag=None, output_kind='directory', required_inputs=[], side_effect='offline_analysis')
    files['configs/simulation_workflows.json'] = json.dumps(catalog)
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    for name in (*VERIFIER_SOURCES, *WORKFLOW_SOURCES):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, tmp_path / name)
    spec = workflow_spec('used', root=tmp_path, entry_points=['worker.py'], inputs=['calibration.json'])
    receipt = build_contract(spec, root=tmp_path)
    return tmp_path, spec, receipt


def verify(root, receipt):
    return verify_contract(receipt, expected_sha256=receipt['sha256'], root=root)


def catalog_change(root, change):
    path = root / 'configs/simulation_workflows.json'
    value = read_json(path)
    change(value)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=4))


def test_new_builder_defaults_to_v2_and_never_executes_sources(candidate):
    root, spec, receipt = candidate
    assert receipt['schema'] == SCHEMA
    assert {'entry.py', 'worker.py', 'pkg/__init__.py', 'pkg/init_dep.py', 'pkg/policy.py',
            'pkg/helper.py', 'calibration.json', *VERIFIER_SOURCES, *WORKFLOW_SOURCES} == set(receipt['source_sha256'])
    assert verify(root, receipt)['registry_entries'] == 1
    assert spec['schema'] == SPEC_SCHEMA


def test_unrelated_entry_addition_edit_and_reorder_leave_seal_identical(candidate):
    root, spec, receipt = candidate
    def change(value):
        value['workflows'][1]['version'] = '2'
        value['workflows'].insert(0, {**value['workflows'][1], 'id': 'brand-new', 'entry': 'new.py'})
        value['workflows'].reverse()
    (root / 'new.py').write_text('NEW = True\n')
    catalog_change(root, change)
    assert build_contract(spec, root=root) == receipt
    assert verify(root, receipt)['sha256'] == receipt['sha256']
    # New workflow declarations also resolve by ID, not the old array position.
    assert workflow_spec('used', root=root, entry_points=['worker.py'], inputs=['calibration.json']) == spec


@pytest.mark.parametrize('field,value', [('version', '2'), ('args', {'gain': 2}),
                                        ('entry', 'unused.py'), ('runner', 'unused')])
def test_used_entry_change_breaks_seal(candidate, field, value):
    root, _, receipt = candidate
    catalog_change(root, lambda c: c['workflows'][0].__setitem__(field, value))
    with pytest.raises(ValueError, match='registry_entries_changed=True'):
        verify(root, receipt)


@pytest.mark.parametrize('name', ['entry.py', 'pkg/__init__.py', 'pkg/init_dep.py', 'pkg/helper.py',
                                 'worker.py', 'calibration.json', *VERIFIER_SOURCES])
def test_changed_imported_module_worker_asset_or_verifier_breaks_seal(candidate, name):
    root, _, receipt = candidate
    path = root / name
    path.write_text(path.read_text() + '\n# changed\n')
    with pytest.raises(ValueError, match='execution dependency drift'):
        verify(root, receipt)


def test_unimported_file_and_registration_notes_are_not_execution_inputs(candidate):
    root, spec, receipt = candidate
    (root / 'unused.py').write_text('raise RuntimeError("changed unused policy")')
    (root / 'REGISTRATION_PLAN.md').write_text('Add the next candidate to the plan.\n')
    assert build_contract(spec, root=root) == receipt
    verify(root, receipt)


def test_new_import_and_disappearing_import_are_rejected(candidate):
    root, _, receipt = candidate
    (root / 'pkg/helper.py').write_text('import unused\n')
    with pytest.raises(ValueError, match='unused.py'):
        verify(root, receipt)
    (root / 'pkg/helper.py').unlink()
    with pytest.raises(ValueError, match='helper.py'):
        verify(root, receipt)


@pytest.mark.parametrize('statement', [
    'import importlib\nimportlib.import_module("unused")\n',
    'import importlib as il\nil.import_module("unused")\n',
    'from importlib import import_module as load\nload("unused")\n',
    '__import__("unused")\n',
])
def test_literal_dynamic_import_is_followed_without_execution(candidate, statement):
    root, spec, _ = candidate
    (root / 'pkg/helper.py').write_text(statement)
    receipt = build_contract(spec, root=root)
    assert 'unused.py' in receipt['source_sha256']
    (root / 'unused.py').write_text('CHANGED = True')
    with pytest.raises(ValueError, match='unused.py'):
        verify(root, receipt)


def test_unknown_dynamic_import_requires_declaration_and_pins_selected_module(candidate):
    root, spec, _ = candidate
    (root / 'pkg/helper.py').write_text('from importlib import import_module as load\nload(config_module)\n')
    with pytest.raises(ValueError, match='undeclared dynamic import: pkg/helper.py'):
        build_contract(spec, root=root)
    spec['dynamic_imports'] = {'pkg/helper.py': ['unused']}
    receipt = build_contract(spec, root=root)
    assert 'unused.py' in receipt['source_sha256']
    (root / 'unused.py').write_text('CHANGED = True')
    with pytest.raises(ValueError, match='unused.py'):
        verify(root, receipt)


def test_import_fromlist_requires_explicit_submodule_coverage(candidate):
    root, spec, _ = candidate
    (root / 'pkg/selected.py').write_text('SELECTED = True\n')
    (root / 'pkg/helper.py').write_text('__import__("pkg", fromlist=["selected"])\n')
    with pytest.raises(ValueError, match='undeclared dynamic import: pkg/helper.py'):
        build_contract(spec, root=root)
    spec['dynamic_imports'] = {'pkg/helper.py': ['pkg.selected']}
    receipt = build_contract(spec, root=root)
    assert 'pkg/selected.py' in receipt['source_sha256']
    (root / 'pkg/selected.py').write_text('SELECTED = False\n')
    with pytest.raises(ValueError, match='selected.py'):
        verify(root, receipt)


def test_catalog_schema_shared_defaults_and_dict_entries_are_pinned(candidate):
    root, spec, _ = candidate
    catalog_change(root, lambda c: c.update(defaults={'timeout': 10}, policies={'pair': {'weld': False}}))
    spec['registries'] += [{'path': 'configs/simulation_workflows.json', 'keys': ['defaults']},
                           {'path': 'configs/simulation_workflows.json', 'keys': ['policies', 'pair']}]
    receipt = build_contract(spec, root=root)
    catalog_change(root, lambda c: c['defaults'].update(timeout=11))
    with pytest.raises(ValueError, match='registry_entries_changed=True'):
        verify(root, receipt)
    receipt = build_contract(spec, root=root)
    catalog_change(root, lambda c: c.update(schema='workflow.v2'))
    with pytest.raises(ValueError, match='unsupported workflow catalog schema'):
        verify(root, receipt)


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'duplicate_key', 'nonfinite', 'overflow'])
def test_missing_or_ambiguous_registry_never_passes(candidate, fault):
    root, _, receipt = candidate
    path = root / 'configs/simulation_workflows.json'
    if fault == 'missing':
        catalog_change(root, lambda c: c['workflows'].pop(0))
    elif fault == 'duplicate':
        catalog_change(root, lambda c: c['workflows'].append(c['workflows'][0]))
    elif fault == 'duplicate_key':
        path.write_text('{"schema": "a", "schema": "b"}')
    elif fault == 'nonfinite':
        path.write_text('{"workflows": NaN}')
    else:
        catalog_change(root, lambda c: c.update(unrelated_number='REPLACE_OVERFLOW'))
        path.write_text(path.read_text().replace('"REPLACE_OVERFLOW"', '1e9999'))
    with pytest.raises(ValueError):
        verify(root, receipt)


def test_seal_anchors_declarations_and_does_not_accept_self_resealed_omissions(candidate):
    root, _, receipt = candidate
    changed = copy.deepcopy(receipt)
    changed['declaration']['inputs'] = []
    changed = build_contract(changed['declaration'], root=root)
    with pytest.raises(ValueError, match='seal mismatch'):
        verify_contract(changed, expected_sha256=receipt['sha256'], root=root)
    changed = copy.deepcopy(receipt)
    del changed['source_sha256']['pkg/helper.py']
    changed['sha256'] = digest({k: v for k, v in changed.items() if k != 'sha256'})
    with pytest.raises(ValueError, match='execution dependency drift'):
        verify(root, changed)  # recomputed closure catches omissions even under a new digest


def test_unsafe_or_whole_registry_inputs_are_refused(candidate, tmp_path):
    root, spec, _ = candidate
    for path in ('../outside.py', '/tmp/outside.py', 'pkg/../entry.py'):
        bad = copy.deepcopy(spec)
        bad['inputs'].append(path)
        with pytest.raises(ValueError, match='nonlocal dependency'):
            build_contract(bad, root=root)
    spec['inputs'].append('configs/simulation_workflows.json')
    with pytest.raises(ValueError, match='both a whole-file input and an entry pin'):
        build_contract(spec, root=root)


def test_legacy_schema_is_never_silently_migrated(candidate):
    root, spec, receipt = candidate
    spec['schema'] = 'ugrp.execution_dependency_spec.v1'
    with pytest.raises(ValueError, match='no legacy migration'):
        build_contract(spec, root=root)
    receipt['schema'] = 'ugrp.execution_dependency_contract.v1'
    with pytest.raises(ValueError, match='legacy verifier'):
        verify(root, receipt)


def test_cli_build_and_verify_never_overwrite_existing_seal(candidate, capsys):
    root, spec, receipt = candidate
    spec_file, output = root / 'spec.json', root / 'receipt.json'
    spec_file.write_text(json.dumps(spec))
    command = ['--root', str(root), 'build', '--spec', str(spec_file), '--output', str(output)]
    assert main(command) == 0
    assert read_json(output) == receipt
    assert main(['--root', str(root), 'verify', '--contract', str(output),
                 '--expected-sha256', receipt['sha256']]) == 0
    assert json.loads(capsys.readouterr().out)['sha256'] == receipt['sha256']
    with pytest.raises(FileExistsError):
        main(command)
    assert read_json(output) == receipt


def test_real_pair_runtime_keeps_teacher_arm_and_provider_dependencies():
    """A real UGRP closure, not policy imports or a new runnable registration."""
    spec = workflow_spec(
        'zone-study-integration-run', modules=['harness.wrist_zone_skill_v9'],
        inputs=['experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json'],
        dynamic_imports={
            'harness/zone_own_team_host.py': ['harness.wrist_zone_skill_v9'],
            'harness/zone_robot_model_runtime.py': ['harness.wrist_zone_skill_v9'],
            'harness/zone_study_integration.py': ['harness.owncam_pose_source'],
        })
    value = build_contract(spec)
    assert {'harness/zone_pair_executor.py', 'harness/visual_arm.py', 'scripts/zone_teacher.py',
            'harness/owncam_pose_source.py', 'harness/owncam_localizer.py', 'sim/session_scenes.py',
            'sim/workflow_manager.py'} <= set(value['source_sha256'])
    assert 'configs/simulation_workflows.json' not in value['source_sha256']
    assert value['registry_entries'][0]['selector']['keys'] == ['workflows', {'id': 'zone-study-integration-run'}]
    verify(ROOT, value)
