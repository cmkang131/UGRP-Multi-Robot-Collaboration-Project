"""Tests for the opt-in pair-worker provenance audit.

Two layers:

* in-process unit tests of the audit module itself (digests, exclusive file
  creation, source hash verification, origin policy, fail-closed tree
  mixing);
* subprocess integration tests that run the OWNED four-operation entry of the
  pinned geometry worker against the PINNED controller with a FIXED SYNTHETIC
  predictor (no learned model, no simulator, no GPU, no head worker process).

The pinned trees are read-only inputs; the integration tests copy them into a
scratch tree and never modify the originals.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = REPO_ROOT / 'harness' / 'pair_worker_audit.py'
SCENARIO = REPO_ROOT / 'tests' / 'pair_worker_audit_scenario.py'

PINNED_WORKER_TREE = Path(os.environ.get(
    'UGRP_PINNED_WORKER_TREE',
    '/home/ubuntu/UGRP/experiments/2026-11-04-joint-act-4tree-assembly-diag-v1/'
    'out/trees/worker'))
GEOMETRY_WORKER = Path(os.environ.get(
    'UGRP_GEOMETRY_WORKER',
    '/home/ubuntu/ugrp-retrain-geom-20261029/received/final/extracted/scripts/'
    'geometry_pair_worker.py'))
SOURCE_MANIFEST = Path(os.environ.get(
    'UGRP_PAIR_RUNTIME_SOURCES',
    '/home/ubuntu/OpenBot/Agents/agent-24194e08-01b9-4e93-a6d7-0a8195436830/'
    'context/20261105-history-producer/publish/pair-runtime-sources.json'))

PINNED_CONTROLLER = PINNED_WORKER_TREE / 'harness' / 'pairact_r1_student.py'
PINNED_CONTROLLER_SHA = ('3e12d2f5408f82821187401e8a6d4298cb70fb27b48c229d689a'
                         '54efdef77e81')
PINNED_GEOMETRY_SHA = ('c7509a6423b252d4941b68ecfa3ce2ffc75783c4f3cd1f3aac2fe'
                        '467b9d601bc')
TICKS = 24
ROLES = ('r1', 'r2')

pytestmark = pytest.mark.skipif(not PINNED_WORKER_TREE.is_dir(),
                                reason='pinned worker tree is not available')


def _python():
    return sys.executable


def _run(args, env=None, cwd=None):
    environment = dict(os.environ)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    if env:
        environment.update(env)
    proc = subprocess.run([_python(), str(args[0])] + [str(a) for a in args[1:]],
                          capture_output=True, text=True, env=environment,
                          cwd=str(cwd or REPO_ROOT), timeout=600)
    return proc


@pytest.fixture(scope='session')
def scratch(tmp_path_factory):
    return tmp_path_factory.mktemp('pair-worker-audit')


@pytest.fixture(scope='session')
def tree(scratch):
    """A byte-identical copy of the pinned harness plus the candidate module."""
    dest = scratch / 'tree'
    proc = _run([SCENARIO, 'prepare', '--pinned-root', PINNED_WORKER_TREE,
                 '--candidate', CANDIDATE, '--dest', dest])
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)['prepared'] == str(dest)
    return dest


def _scenario(tree_root, audit, run_id, output_root, ticks=TICKS, extra=()):
    argv = [SCENARIO, 'run', '--student-root', tree_root,
            '--geometry-worker', GEOMETRY_WORKER, '--audit', audit,
            '--run-id', run_id, '--ticks', ticks]
    if audit == 'on':
        argv += ['--output-root', output_root]
    argv += list(extra)
    proc = _run(argv, env={'PYTHONPATH': str(tree_root)})
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.fixture(scope='session')
def audit_on(tree, scratch):
    return _scenario(tree, 'on', 'pytest-on', scratch / 'out-on')


@pytest.fixture(scope='session')
def audit_off(tree, scratch):
    return _scenario(tree, 'off', 'pytest-off', scratch / 'out-off')


@pytest.fixture(scope='session')
def records(audit_on):
    return audit_on['audit_records']


def _of_kind(records, kind):
    return [record for record in records if record['kind'] == kind]


# --------------------------------------------------------------------- unit

def test_digest_is_canonical_and_order_independent():
    from harness import pair_worker_audit as audit
    assert audit.digest({'a': 1, 'b': 2}) == audit.digest({'b': 2, 'a': 1})
    assert audit.digest({'a': 1}) != audit.digest({'a': 2})
    assert len(audit.digest({'a': 1})) == 64


def test_sink_writes_contiguous_sequences_with_verifiable_digests(tmp_path):
    from harness import pair_worker_audit as audit
    sink = audit.AuditSink(run_id='unit-1', output_root=tmp_path)
    try:
        first = sink.write({'kind': 'a', 'value': 1})
        second = sink.write({'kind': 'b', 'value': 2})
    finally:
        sink.close()
    assert (first, second) == (0, 1)
    rows = [json.loads(line) for line in
            (tmp_path / 'pair-audit-unit-1.jsonl').read_text().splitlines()]
    assert [row['seq'] for row in rows] == [0, 1]
    assert all(row['schema'] == audit.SCHEMA for row in rows)
    assert all(row['run_id'] == 'unit-1' for row in rows)
    assert 'environment application' in rows[0]['claim']
    for row in rows:
        body = {k: v for k, v in row.items() if k != 'record_digest'}
        assert audit.digest(body) == row['record_digest']


def test_sink_refuses_to_reuse_a_run_id_or_overwrite_a_file(tmp_path):
    from harness import pair_worker_audit as audit
    sink = audit.AuditSink(run_id='unit-2', output_root=tmp_path)
    sink.close()
    with pytest.raises(audit.AuditError):
        audit.AuditSink(run_id='unit-2', output_root=tmp_path)
    other = audit.AuditSink(run_id='unit-3', output_root=tmp_path)
    other.close()
    assert (tmp_path / 'pair-audit-unit-2.jsonl').exists()
    assert (tmp_path / 'pair-audit-unit-3.jsonl').exists()


def test_sink_refuses_an_unsafe_run_id(tmp_path):
    from harness import pair_worker_audit as audit
    with pytest.raises(audit.AuditError):
        audit.AuditSink(run_id='../escape', output_root=tmp_path)


def test_check_same_tree_refuses_mixed_harness_trees(tmp_path):
    from harness import pair_worker_audit as audit
    mine = tmp_path / 'mine' / 'harness'
    theirs = tmp_path / 'theirs' / 'harness'
    mine.mkdir(parents=True)
    theirs.mkdir(parents=True)
    assert audit.check_same_tree(mine / 'a.py', mine / 'b.py') is True
    with pytest.raises(audit.AuditError):
        audit.check_same_tree(mine / 'a.py', theirs / 'b.py')
    with pytest.raises(audit.AuditError):
        audit.check_same_tree(mine / 'a.py', tmp_path / 'not_harness' / 'b.py')


def test_verify_sources_is_fail_closed(tmp_path):
    from harness import pair_worker_audit as audit
    target = tmp_path / 'pinned.py'
    target.write_text('x = 1\n', encoding='utf-8')
    good = audit.file_digest(target)
    assert audit.verify_sources({str(target): good}) == {str(target): good}
    with pytest.raises(audit.AuditError):
        audit.verify_sources({str(target): '0' * 64})
    with pytest.raises(audit.AuditError):
        audit.verify_sources({str(tmp_path / 'missing.py'): good})


def test_origin_is_never_inferred_from_the_command_values(tmp_path):
    from harness import pair_worker_audit as audit
    sink = audit.AuditSink(run_id='origin-unit', output_root=tmp_path)
    audit_state = audit.PairWorkerAudit(run_id='origin-unit', sink=sink)
    stop = {'t': 1.0, 'wheels': [0.0] * 4, 'duration_s': [0.0] * 4,
            'pwm': {'1': 1500, '3': 1500, '4': 1500, '5': 1500, '6': 1500}}
    seq = audit_state.record_issue_command('r1', stop)
    same = audit_state.record_issue_command('r1', dict(stop, t=2.0))
    declared = audit_state.record_issue_command('r1', dict(stop, t=3.0),
                                                origin='protocol_hold')
    with pytest.raises(audit.AuditError):
        audit_state.record_issue_command('r1', stop, origin='because_zero')
    sink.close()
    rows = [json.loads(line) for line in
            (tmp_path / 'pair-audit-origin-unit.jsonl').read_text().splitlines()]
    origins = [row['origin'] for row in rows]
    assert origins == ['unknown', 'unknown', 'protocol_hold']
    assert 'values never imply' in rows[0]['origin_source']
    assert rows[0]['supersedes_observation_seq'] is None
    assert [row['issue_number'] for row in rows] == [1, 2, 3]
    assert seq != same != declared


def test_observation_requires_a_sample_id_and_the_contract_window(tmp_path):
    from harness import pair_worker_audit as audit

    class Contract:
        HISTORY = 16

    sink = audit.AuditSink(run_id='obs-unit', output_root=tmp_path)
    state = audit.PairWorkerAudit(run_id='obs-unit', sink=sink)
    issued = [{'t': 0.0}] * 16
    with pytest.raises(audit.AuditError):
        state.record_observation('r1', {'issued': issued}, contract=Contract)
    with pytest.raises(audit.AuditError):
        state.record_observation('r1', {'sample_id': 'x', 'issued': issued[:4]},
                                 contract=Contract)
    seq = state.record_observation('r1', {'sample_id': 'x', 'issued': issued,
                                          't': 0.0}, contract=Contract)
    assert seq >= 0
    sink.close()


def test_close_marks_an_unpaired_issue(tmp_path):
    from harness import pair_worker_audit as audit
    sink = audit.AuditSink(run_id='pair-unit', output_root=tmp_path)
    state = audit.PairWorkerAudit(run_id='pair-unit', sink=sink)
    command = {'t': 1.0, 'wheels': [0.0] * 4, 'duration_s': [0.0] * 4,
               'pwm': {'1': 1500, '3': 1500, '4': 1500, '5': 1500, '6': 1500}}
    issue_seq = state.record_issue_command('r1', command)
    state.close()
    rows = [json.loads(line) for line in
            (tmp_path / 'pair-audit-pair-unit.jsonl').read_text().splitlines()]
    pending = [row for row in rows if row['kind'] == 'pending_observation']
    assert len(pending) == 1
    assert pending[0]['issue_seq'] == issue_seq
    assert pending[0]['unpaired'] is True
    assert pending[0]['robot_id'] == 'r1'


def test_load_source_manifest_accepts_both_shapes(tmp_path):
    from harness import pair_worker_audit as audit
    manifest = tmp_path / 'sources.json'
    manifest.write_text(json.dumps({'/a.py': {'sha256': 'aa', 'bytes': 1},
                                    '/b.py': 'bb'}), encoding='utf-8')
    assert audit.load_source_manifest(manifest) == {'/a.py': 'aa', '/b.py': 'bb'}


# -------------------------------------------------------------- integration

def test_audit_off_produces_no_audit_file(audit_off, scratch):
    assert 'audit_file' not in audit_off
    assert not list((scratch / 'out-off').glob('*.jsonl'))


def test_audit_on_produces_exactly_one_new_jsonl_file(audit_on):
    assert audit_on['audit_file'].endswith('pair-audit-pytest-on.jsonl')
    assert Path(audit_on['audit_file']).is_file()


def test_audit_on_and_off_produce_identical_protocol_responses(audit_on, audit_off):
    assert audit_on['stdout'] == audit_off['stdout']
    assert len(audit_on['stdout']) == 2 * TICKS + 3      # ready + reset + 2*24 + summary


def test_protocol_responses_carry_no_audit_metadata(audit_on):
    text = json.dumps(audit_on['stdout'])
    for key in ('audit', 'origin', 'record_digest', 'provenance', 'run_id'):
        assert '"%s"' % key not in text


def test_audit_records_are_sequential_and_digest_verifiable(records):
    from harness import pair_worker_audit as audit
    assert [record['seq'] for record in records] == list(range(len(records)))
    for record in records:
        body = {k: v for k, v in record.items() if k != 'record_digest'}
        assert audit.digest(body) == record['record_digest']
        assert record['schema'] == audit.SCHEMA
        assert record['run_id'] == 'pytest-on'


def test_inventory_names_the_candidate_and_the_pinned_controller(records):
    inventory = _of_kind(records, 'inventory')[0]
    assert inventory['candidate_is_the_pinned_worker'] is False
    assert inventory['audited_controller_sha256'] == PINNED_CONTROLLER_SHA
    assert inventory['audit_module_sha256'] != PINNED_CONTROLLER_SHA
    assert inventory['audit_module_sha256'] != PINNED_GEOMETRY_SHA
    assert inventory['origin_policy'].startswith('declared only')
    assert Path(inventory['tree_root']).name == 'harness'


def test_reset_padding_is_recorded_per_robot(records):
    padding = _of_kind(records, 'reset_padding')
    assert len(padding) == 2
    assert sorted(row['robot_id'] for row in padding) == list(ROLES)
    for row in padding:
        assert row['count'] == 16
        assert row['identical_rows'] is True
        assert row['contract_history'] == 16


def test_the_two_robots_are_recorded_separately(records):
    issues = _of_kind(records, 'issue_command')
    assert sorted({row['robot_id'] for row in issues}) == list(ROLES)
    for robot_id in ROLES:
        numbers = [row['issue_number'] for row in issues if row['robot_id'] == robot_id]
        assert numbers == list(range(1, TICKS + 1))
    observations = _of_kind(records, 'observation')
    for robot_id in ROLES:
        mine = [row for row in observations if row['robot_id'] == robot_id]
        assert len(mine) == TICKS
        assert len({row['sample_id'] for row in mine}) == TICKS


def test_the_hold_branch_and_the_real_issue_branch_are_both_kept(records):
    issues = _of_kind(records, 'issue_command')
    stops = [row for row in issues if all(w == 0.0 for w in row['command']['wheels'])]
    moves = [row for row in issues if any(w != 0.0 for w in row['command']['wheels'])]
    assert stops, 'the protocol hold branch must be recorded'
    assert moves, 'the real issued command must be recorded'
    ops = _of_kind(records, 'issue_op')
    assert any(row['robots']['r1']['permit'] is False for row in ops)
    assert any(row['robots']['r1']['permit'] is True for row in ops)
    # The hold must be visible in the protocol view as well, and it must not
    # be turned into an origin label.
    held = [row for row in ops if row['permits']['r1'] is False]
    assert held
    for row in stops:
        assert row['origin'] == 'unknown'
        assert 'values never imply' in row['origin_source']


def test_the_window_rolls_after_twenty_issues(records):
    observations = [row for row in _of_kind(records, 'observation')
                    if row['robot_id'] == 'r1']
    assert len(observations) == TICKS
    assert all(row['issued_count'] == 16 for row in observations)
    assert observations[0]['window_digest'] != observations[-1]['window_digest']
    issues = [row for row in _of_kind(records, 'issue_command')
              if row['robot_id'] == 'r1']
    assert issues[-1]['issue_number'] == TICKS > 20


def test_observations_and_issues_are_cross_linked(records):
    by_seq = {record['seq']: record for record in records}
    observations = _of_kind(records, 'observation')
    issues = _of_kind(records, 'issue_command')
    linked = 0
    for observation in observations:
        seq = observation['linked_issue_seq']
        if seq is None:
            continue
        linked += 1
        issue = by_seq[seq]
        assert issue['kind'] == 'issue_command'
        assert issue['robot_id'] == observation['robot_id']
        assert issue['seq'] < observation['seq']
    assert linked == len(observations) - len(ROLES)
    superseded = [row['supersedes_observation_seq'] for row in issues
                  if row['supersedes_observation_seq'] is not None]
    assert superseded
    for seq in superseded:
        target = by_seq[seq]
        assert target['kind'] == 'observation'


def test_the_propose_view_matches_the_observations(records):
    proposes = _of_kind(records, 'propose_op')
    observations = _of_kind(records, 'observation')
    assert len(proposes) == TICKS
    for proposal in proposes:
        for robot_id in ROLES:
            sample_id = proposal['robots'][robot_id]['sample_id']
            assert any(row['robot_id'] == robot_id and row['sample_id'] == sample_id
                       for row in observations)
            assert proposal['robots'][robot_id]['stage'] is not None


def test_the_last_issue_without_an_observation_is_marked_unpaired(records):
    pending = _of_kind(records, 'pending_observation')
    assert sorted(row['robot_id'] for row in pending) == list(ROLES)
    for row in pending:
        assert row['unpaired'] is True
        issue = next(r for r in records if r['seq'] == row['issue_seq'])
        assert issue['kind'] == 'issue_command'


def test_a_summary_record_closes_the_run(records):
    summary = _of_kind(records, 'summary_op')
    assert len(summary) == 1
    assert len(summary[0]['summary_digest']) == 64


def test_the_pinned_sources_are_verified_against_the_manifest(tree, scratch):
    result = _scenario(tree, 'on', 'pytest-manifest', scratch / 'out-manifest',
                       extra=['--audit-sources', SOURCE_MANIFEST])
    inventory = _of_kind(result['audit_records'], 'inventory')[0]
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding='utf-8'))
    assert set(inventory['pinned_sources']) == set(manifest)
    for name, entry in manifest.items():
        assert inventory['pinned_sources'][name] == entry['sha256']


def test_a_wrong_pinned_hash_stops_the_run(tree, scratch):
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding='utf-8'))
    broken = scratch / 'broken-manifest.json'
    payload = {name: {'sha256': '0' * 64} for name in manifest}
    broken.write_text(json.dumps(payload), encoding='utf-8')
    result = _scenario(tree, 'on', 'pytest-broken', scratch / 'out-broken',
                       extra=['--audit-sources', broken])
    assert result['error_type'] == 'AuditError'
    assert 'hash mismatch' in result['error']


def test_a_mixed_harness_tree_is_refused(scratch):
    result = _scenario(PINNED_WORKER_TREE, 'on', 'pytest-mix', scratch / 'out-mix',
                       ticks=3, extra=['--candidate', CANDIDATE])
    assert result['error_type'] == 'AuditError'
    assert 'harness tree mixing refused' in result['error']
    assert result['stdout'] == [{'mode': 'pairact_r1_student_eval_v1',
                                  'ready': True}]


def test_the_pinned_trees_are_untouched(tree, scratch):
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding='utf-8'))
    for name, entry in manifest.items():
        assert hashlib_sha256(name) == entry['sha256']
    assert hashlib_sha256(str(PINNED_CONTROLLER)) == PINNED_CONTROLLER_SHA
    assert hashlib_sha256(str(GEOMETRY_WORKER)) == PINNED_GEOMETRY_SHA
    assert (tree / 'harness' / 'pair_worker_audit.py').is_file()


def hashlib_sha256(path):
    import hashlib
    hasher = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


@pytest.mark.parametrize('field,value', [('schema','fake'),('seq',999),('run_id','other'),
                                         ('claim','environment applied'),('record_digest','fake')])
def test_sink_reserved_envelope_is_immutable(tmp_path, field, value):
    from harness import pair_worker_audit as audit
    sink = audit.AuditSink(run_id='protected', output_root=tmp_path)
    try:
        with pytest.raises(audit.AuditError):
            sink.write({'kind':'test', field:value})
        assert sink.write({'kind':'test'}) == 0
    finally:
        sink.close()


def test_explicit_filename_cannot_escape_root(tmp_path):
    from harness import pair_worker_audit as audit
    with pytest.raises(audit.AuditError):
        audit.AuditSink(run_id='safe', output_root=tmp_path, filename='../escape.jsonl')
    assert not (tmp_path.parent / 'escape.jsonl').exists()


def test_prepare_tree_preserves_existing_destination(tmp_path):
    from tests.pair_worker_audit_scenario import prepare_tree
    dest = tmp_path/'existing'; dest.mkdir(); sentinel=dest/'original.txt'
    sentinel.write_text('preserve')
    with pytest.raises(FileExistsError):
        prepare_tree(PINNED_WORKER_TREE, CANDIDATE, dest)
    assert sentinel.read_text() == 'preserve'


def test_bad_origin_rejected_before_producer_mutation(tmp_path):
    from harness import pair_worker_audit as audit, grasp_act_contract as contract
    from collections import deque
    class Owner:
        def __init__(self):
            self.issued=deque([{'t':0.,'wheels':[0.]*4,'duration_s':[0.]*4,
                                'pwm':{str(s):1500 for s in contract.SERVOS}}]*16,maxlen=16)
        def issue(self,value):
            self.issued.append(contract.command(value))
    state=audit.PairWorkerAudit(run_id='bad-origin',output_root=tmp_path)
    state.contract=contract; owner=Owner()
    proxy=audit.AuditedInputs(owner,audit=state,robot_id='r1')
    before=list(owner.issued)
    try:
        with pytest.raises(audit.AuditError):
            proxy.issue(dict(before[-1],t=.1),origin='invented')
        assert list(owner.issued)==before
        assert state._robots.get('r1',{}).get('issue_count',0)==0
    finally:
        state.close()
