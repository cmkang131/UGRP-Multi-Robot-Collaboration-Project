"""Synthetic-only v91 identity, chronology, scoring parity and byte preservation."""
import copy
from datetime import datetime, timezone
from functools import lru_cache
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tarfile

import numpy as np
import pytest

from harness import zone_final_pair_fast as acquisition
from harness.zone_final_pair_calibration import schedule
from scripts import validate_consumer_criterion_b as old
from scripts import validate_consumer_criterion_b_v91 as new
from tests.test_consumer_criterion_b import synthetic

MAPS = tuple(sorted(old.criterion()['held_out']['allowed_maps']))
AFTER = datetime(2026, 10, 2, 19, tzinfo=timezone.utc).timestamp()
COMMITTED = new.utc('2026-10-02T18:04:39Z').timestamp()


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for module in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
        monkeypatch.setitem(sys.modules, module, None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def get(path):
    return json.loads(path.read_text())


def receipts(root):
    folder = root / get(root / 'plan.json')['cases'][0]['id']
    result = get(root / 'result.json')
    result['cases'] = [get(folder / 'result.json')]
    put(root / 'result.json', result)
    put(folder / 'artifacts.sha256.json', {str(p.relative_to(folder)): old.sha(p.read_bytes())
        for p in folder.rglob('*') if p.is_file() and p.name != 'artifacts.sha256.json'})


@lru_cache(maxsize=2)
def acquisition_source_hashes(paths):
    """Synthetic receipts describe the pinned acquisition, not today's checkout."""
    archive = subprocess.check_output(['git', 'archive', new.SOURCE, '--', *paths], cwd=new.ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
        return {path: old.sha(tree.extractfile(path).read()) for path in paths}


def make_raw(root, map_id):
    bundle = {**acquisition.bundle(map_id, acquisition.CHECK),
              'case': acquisition.cases(acquisition.CHECK, map_id)[0], 'source_sha': new.SOURCE}
    bundle['source_sha256'] = dict(acquisition_source_hashes(tuple(sorted(bundle['source_sha256']))))
    folder = root / map_id
    put(folder / 'bundle.json', bundle)
    put(folder / 'inputs/schedule.json', schedule(acquisition.CHECK))
    u, _ = old.plan_arrays(bundle['measurement'], 7400, .05)
    candidate = get(old.CANDIDATE)
    increments = sum(old.c.legacy_increments({'u': u, 'dt': .05},
        candidate['candidate_axes'][axis]['consumer_fields']) for axis in ('forward', 'left'))
    xyz = np.vstack((np.zeros(3), np.cumsum(increments, axis=0)))
    # No physics: translations are the exact frozen means, yaw is fabricated zero.
    poses = [{'t': 1.+i*.05, 'sample_index': i, 'base_position_m': p.tolist(),
              'base_rotation': np.eye(3).tolist(), 'requested_check': acquisition.CHECK,
              'map_id': map_id, 'load_state': 'unloaded'} for i, p in enumerate(xyz)]
    commands = [{**e['action'], 't': 1.+e['t']} for e in schedule(acquisition.CHECK)
                if e['robot_id'] == 'r1']
    for name, values in [('eval_only/r1/pose.jsonl', poses), ('robots/r1/commands.jsonl', commands)]:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(json.dumps(v)+'\n' for v in values))
    host = {'loadavg': [0., 0., 0.], 'physics_holder': {'acquired_unix': AFTER},
            'concurrent_holders': [{'acquired_unix': AFTER+1}, {'acquired_unix': AFTER+2}]}
    result = {**new.ROLE, 'status': 'COLLECTED_UNQUALIFIED', 'protocol_complete': True,
              'check': acquisition.CHECK, 'case': bundle['case'], 'check_sim_s': 370., 'host_start': host}
    put(folder / 'result.json', result)
    put(root / 'plan.json', {**new.ROLE, 'execution_bundle_id': new.BUNDLE, 'check': acquisition.CHECK,
        'source_sha': new.SOURCE, 'seed': 911, 'execution_started': True, 'runnable': True,
        'blocked_on': [], 'denominator': 1, 'cases': [bundle['case']],
        'bundles_sha256': [new.canonical_sha(bundle)], 'host_start': host})
    put(root / 'result.json', {**new.ROLE, 'status': 'COLLECTED_UNQUALIFIED', 'denominator': 1,
        'source_unchanged': True, 'unattempted': [], 'cases': [result], 'host_start': host})
    receipts(root)
    return root


@pytest.fixture(scope='module')
def templates(tmp_path_factory):
    base = tmp_path_factory.mktemp('synthetic-v91-only')
    return [make_raw(base / m, m) for m in MAPS]


@pytest.fixture
def raw(tmp_path, templates):
    return Path(shutil.copytree(templates[0], tmp_path / 'raw'))


def assert_ineligible(report):
    assert report['scope'] == 'INELIGIBLE'
    assert report['pass'] is None
    assert report['axis_pass'] == dict.fromkeys(old.AXES)
    assert report['ordering_evidence']['verified'] is False


def test_frozen_files_registrations_and_handoff_prefix_are_byte_identical():
    receipt = get(new.RECORD / 'preservation.json')
    for name, sha in receipt['unchanged_sha256'].items():
        assert old.sha((new.ROOT / name).read_bytes()) == sha, name
    prefix = receipt['handoff_prefix']
    assert old.sha((new.ROOT / 'PHYSICS_HANDOFF.md').read_bytes()[:prefix['bytes']]) == prefix['sha256']
    assert new.verify_commitment([])['created_at'] == '2026-10-02T18:04:39Z'


@pytest.mark.parametrize('axis', [0, 1, 2])
@pytest.mark.parametrize('failure', [False, True])
def test_same_synthetic_case_has_exact_frozen_scores(axis, failure):
    data, candidate, _ = synthetic(axis)
    if failure:
        data['pose'][:, axis] *= 10
    gate = old.criterion()
    before = copy.deepcopy(gate)
    original = old.score([data], candidate, gate)
    adapted = new.score([data], candidate, gate, chronology_verified=True)
    assert gate == before
    for name in old.AXES:
        a, b = original['cases'][0]['axes'][name], adapted['cases'][0]['axes'][name]
        assert a['metrics'] == b['metrics']
        if a['metrics'] is not None:
            assert b['pass'] is a['numerical_pass']
            assert b['numerical_pass'] == a['numerical_pass']
            assert set(a['metrics']['steps']) == {'0.2', '0.5', '1.0', '2.0', '3.0', '3.2'}
            assert all(len(row['component_pass']) == 3 for row in old.all_rows(a['metrics']))
        else:
            assert b == a  # frozen missing-axis reason and null decisions
    assert adapted['axis_pass'][old.AXES[axis]] is not failure
    assert adapted['pass'] is (False if failure else None)


@pytest.mark.parametrize('reason', ['training', 'previously_seen', 'training_map', 'missing_prbs', 'null_candidate'])
def test_chronology_does_not_bypass_frozen_vetoes(reason):
    data, candidate, _ = synthetic()
    if reason == 'training': data['training'] = True
    if reason == 'previously_seen': candidate['previously_seen_pose_sha256'] = [data['pose_sha256']]
    if reason == 'training_map': data['map_id'] = old.criterion()['held_out']['training_map']
    if reason == 'missing_prbs': data['segments']['forward']['prbs'] = []
    if reason == 'null_candidate': candidate['candidate_axes']['forward'] = None
    report = new.score([data], candidate, old.criterion(), chronology_verified=True)
    assert report['axis_pass'] == dict.fromkeys(old.AXES)
    assert report['pass'] is None


def test_two_complete_synthetic_maps_use_frozen_candidate_and_keep_rotation_null(templates):
    report = new.validate(templates)
    assert report['scope'] == 'HELD_OUT_VALIDATION', report.get('eligibility_reason')
    assert report['axis_pass'] == {'forward': True, 'left': True, 'rotate': None}
    assert report['pass'] is None
    assert report['maps_not_supplied'] == []
    assert report['ordering_evidence']['verified'] is True
    assert report['ordering_evidence']['earliest']['kind'] == 'lock_acquisition_lower_bound'
    for root in templates:
        assert str(root / 'plan.json') in {i['path'] for i in report['input_files']}


def test_synthetic_bundles_match_acquisition_source_counts_and_pinned_digests(templates):
    counts = {'zone_wide_corridor_final_v3': 254, 'zone_wide_door_geometry_v3': 253}
    contract = get(new.CONTRACT)
    for root in templates:
        bundle = get(root / root.name / 'bundle.json')
        assert len(bundle['source_sha256']) == counts[root.name]
        assert new.canonical_sha(bundle) == contract['bundle_canonical_sha256'][root.name]


def test_new_slot_source_cannot_relabel_the_pinned_acquisition(raw):
    path = raw / MAPS[0] / 'bundle.json'
    bundle = get(path)
    bundle['source_sha256']['scripts/agent_sim_slots.py'] = old.sha(
        (new.ROOT / 'scripts/agent_sim_slots.py').read_bytes())
    put(path, bundle)
    plan = get(raw / 'plan.json')
    plan['bundles_sha256'] = [new.canonical_sha(bundle)]
    put(raw / 'plan.json', plan)
    receipts(raw)
    assert_ineligible(new.validate([raw]))


@pytest.mark.parametrize('scope', ['plan', 'bundle', 'case', 'root'])
@pytest.mark.parametrize('field,value', [('collection_role', 'TRAINING'), ('training_eligible', True),
                                       ('teacher_only', False), ('training_eligible', 0)])
def test_labels_are_required_everywhere(raw, scope, field, value):
    paths = {'plan': raw/'plan.json', 'bundle': raw/MAPS[0]/'bundle.json',
             'case': raw/MAPS[0]/'result.json', 'root': raw/'result.json'}
    path = paths[scope]
    data = get(path)
    data[field] = value
    put(path, data)
    receipts(raw)
    assert_ineligible(new.validate([raw]))


@pytest.mark.parametrize('field,value', [('execution_bundle_id', 'zone-final-pair-v88'),
    ('execution_bundle_id', 'zone-final-pair-v90'), ('workflow_id', 'zone-final-pair-heldout-v90'),
    ('workflow_version', '3.2.0'), ('source_sha', '0'*40), ('seed', 912),
    ('map_id', 'zone_wide_two_doors_final_v3'), ('map_id', 'unregistered')])
def test_exact_acquisition_identity(raw, field, value):
    path = raw/MAPS[0]/'bundle.json'
    bundle = get(path)
    bundle[field] = value
    put(path, bundle)
    receipts(raw)
    assert_ineligible(new.validate([raw]))


@pytest.mark.parametrize('version', [88, 90])
def test_relabelled_old_bundle_cannot_be_admitted(raw, version):
    if version == 88:
        from harness import zone_final_pair_contract as v
        value = v.bundle('zone_wide_two_doors_final_v3', 'calibration-unloaded')
    else:
        from harness import zone_final_pair_heldout as v
        value = v.bundle(MAPS[0], 'calibration-unloaded')
    expected = get(raw/MAPS[0]/'bundle.json')
    for key in ('execution_bundle_id', 'workflow_id', 'workflow_version', 'source_sha', 'schema',
                'map_id', 'case', 'seed', 'measurement', *new.ROLE):
        value[key] = expected[key]
    put(raw/MAPS[0]/'bundle.json', value)
    receipts(raw)
    report = new.validate([raw])
    assert_ineligible(report)
    assert 'exact v91 source contract' in report['eligibility_reason']


@pytest.mark.parametrize('record', ['plan', 'root', 'case'])
@pytest.mark.parametrize('delta', [-1, 0])
def test_earliest_start_anywhere_must_be_strictly_after_commitment(raw, record, delta):
    path = {'plan': raw/'plan.json', 'root': raw/'result.json', 'case': raw/MAPS[0]/'result.json'}[record]
    data = get(path)
    data['host_start']['concurrent_holders'][1]['acquired_unix'] = COMMITTED+delta
    put(path, data)
    receipts(raw)
    # Filesystem dates deliberately disagree; they must never influence eligibility.
    os.utime(path, (AFTER+100000, AFTER+100000))
    report = new.validate([raw])
    assert_ineligible(report)
    assert 'strictly before' in report['eligibility_reason']


@pytest.mark.parametrize('bad', ['missing', None, '2026-10-02T19:00:00', True, 'not-a-time'])
def test_missing_or_invalid_runner_clock_fails_closed(raw, bad):
    path = raw/'plan.json'
    data = get(path)
    if bad == 'missing':
        data.pop('host_start')
    else:
        data['host_start']['physics_holder']['acquired_unix'] = bad
    put(path, data)
    assert_ineligible(new.validate([raw]))


@pytest.mark.parametrize('value', ['2026-10-02T18:04:39Z', '2026-10-02T18:00:00+00:00',
                                  '2026-10-02T20:00:00', 'invalid'])
def test_explicit_start_utc_cannot_be_ignored(raw, value):
    path = raw/'result.json'
    data = get(path)
    data['started_utc'] = value
    put(path, data)
    assert_ineligible(new.validate([raw]))


@pytest.mark.parametrize('mutation', ['plan_binding', 'schedule', 'receipt', 'incomplete',
                                     'missing_pose', 'missing_command', 'source_changed'])
def test_raw_provenance_and_frozen_audits_fail_closed(raw, mutation):
    folder = raw/MAPS[0]
    if mutation == 'schedule':
        (folder/'inputs/schedule.json').write_text('[]')
    elif mutation == 'receipt':
        put(folder/'artifacts.sha256.json', {})
    elif mutation == 'missing_pose':
        (folder/'eval_only/r1/pose.jsonl').unlink()
    elif mutation == 'missing_command':
        p = folder/'robots/r1/commands.jsonl'
        lines = p.read_text().splitlines()
        j = next(i for i, line in enumerate(lines) if json.loads(line)['kind'] == 'mecanum')
        lines.pop(j)
        p.write_text('\n'.join(lines)+'\n')
    else:
        p = raw/('plan.json' if mutation == 'plan_binding' else 'result.json')
        data = get(p)
        if mutation == 'plan_binding': data['bundles_sha256'] = ['0'*64]
        if mutation == 'incomplete': data['status'] = 'RUNNING'
        if mutation == 'source_changed': data['source_unchanged'] = False
        put(p, data)
    if mutation != 'receipt': receipts(raw)
    assert_ineligible(new.validate([raw]))


@pytest.mark.parametrize('name', list(new.FROZEN_HASHES))
def test_commitment_hashes_must_match_actual_bytes(tmp_path, monkeypatch, name):
    for path in new.FROZEN_HASHES:
        target = tmp_path/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((new.ROOT/path).read_bytes())
    (tmp_path/name).write_bytes((tmp_path/name).read_bytes()+b' ')
    monkeypatch.setattr(new, 'ROOT', tmp_path)
    report = new.validate([])
    assert_ineligible(report)
    assert 'actual byte hash mismatch' in report['eligibility_reason']


def test_snapshot_tamper_and_missing_snapshot_fail_closed(tmp_path, monkeypatch):
    target = tmp_path/'commitment.json'
    monkeypatch.setattr(new, 'PINNED', {target: new.PINNED[new.SNAPSHOT]})
    assert_ineligible(new.validate([]))
    snapshot = get(new.SNAPSHOT)
    snapshot['created_at'] = '2020-01-01T00:00:00Z'
    put(target, snapshot)
    assert_ineligible(new.validate([]))


@pytest.mark.parametrize('mode', ['match', 'edited', 'unavailable'])
def test_optional_github_refetch_is_exact_and_fail_closed(monkeypatch, mode):
    remote = get(new.SNAPSHOT)
    def fetch(argv, **kwargs):
        assert argv == ['gh', 'api', new.COMMENT_API]
        if mode == 'unavailable': raise subprocess.TimeoutExpired(argv, 30)
        if mode == 'edited': remote['body'] += ' changed'
        return json.dumps(remote)
    monkeypatch.setattr(new.subprocess, 'check_output', fetch)
    if mode == 'match':
        assert new.verify_commitment([], refetch=True)['id'] == 5958329647
    else:
        with pytest.raises(ValueError, match='unavailable|changed'):
            new.verify_commitment([], refetch=True)
        assert_ineligible(new.validate([], refetch=True))


def test_post_score_input_mutation_revokes_all_decisions(raw, monkeypatch):
    original = new.score
    def changed(*args, **kwargs):
        report = original(*args, **kwargs)
        (raw/'plan.json').write_text('{}')
        return report
    monkeypatch.setattr(new, 'score', changed)
    report = new.validate([raw])
    assert_ineligible(report)
    assert 'changed during validation' in report['eligibility_reason']


@pytest.mark.parametrize('name', ['robots/r1/commands.jsonl', 'eval_only/r1/pose.jsonl'])
def test_malformed_nested_raw_is_reported_ineligible(raw, name):
    path = raw/MAPS[0]/name
    path.write_text('["not an object"]\n'+path.read_text())
    receipts(raw)
    assert_ineligible(new.validate([raw]))


def test_cli_valid_and_ineligible_exit_two_and_failure_exit_one(raw, tmp_path):
    assert new.main(['--raw', str(raw), '--output', str(tmp_path/'ok.json')]) == 2
    assert get(tmp_path/'ok.json')['axis_pass']['forward'] is True
    folder = raw/MAPS[0]
    path = folder/'eval_only/r1/pose.jsonl'
    poses = old.rows(path.read_bytes())
    for p in poses: p['base_position_m'][0] *= 10
    path.write_text(''.join(json.dumps(p)+'\n' for p in poses))
    receipts(raw)
    assert new.main(['--raw', str(folder), '--output', str(tmp_path/'failed.json')]) == 1
    assert get(tmp_path/'failed.json')['axis_pass']['rotate'] is None
    (raw/'plan.json').unlink()
    assert new.main(['--raw', str(raw), '--output', str(tmp_path/'ineligible.json')]) == 2
    assert_ineligible(get(tmp_path/'ineligible.json'))


def test_output_never_writes_within_collection_even_with_case_selection(raw):
    with pytest.raises(ValueError, match='outside'):
        new.main(['--raw', str(raw/MAPS[0]), '--output', str(raw/'new-report.json')])
    assert not (raw/'new-report.json').exists()


def test_new_suite_is_collected_without_workflow_edits():
    from scripts.run_ci_tests import collect_test_files, TEST_PATTERNS
    assert collect_test_files(new.ROOT, TEST_PATTERNS).count('tests/test_consumer_criterion_b_v91.py') == 1
