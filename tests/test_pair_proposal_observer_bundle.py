"""Bundle/entry/outer wiring for the raw ProposalObserver (CPU only).

Scope
-----
This file covers the WIRING only -- the coordinator's frozen core
(``harness/pair_worker_audit.py`` and ``harness/pair_proposal_observer.py``)
is read-only here.  What is verified:

* the observer is copied into the **same** harness tree as the pinned
  controller, so ``harness.pair_proposal_observer`` is imported from the
  bundle and not from the caller's tree;
* the manifest binds **16** entries (7 pinned tree files + 4 candidate files
  + 5 read-only originals) and refuses an empty, incomplete, forged or
  drifted manifest -- with no ``ready`` line, no head worker and no file;
* the entry carries INDEPENDENT hashes for the audit module, the bundle
  helper and the observer, so a manifest that only agrees with itself is
  refused;
* ``--observe-raw-proposals`` is OPT-IN (default OFF): it is only passed
  when it was explicitly requested, it is refused together with
  ``--audit-worker off``, and it cannot be enabled without the whole
  audited option set;
* the four-operation protocol, the raw input (own JPEG + own issued history
  only), the 8-stage barrier and the READY->GO->ACK gates are UNCHANGED
  with the observer ON: the responses are byte-identical to the OFF run and
  the origins stay ``unknown``;
* the real CLI ``--prepare-only`` runs with the observer ON and leaves the
  bundle, the 16-entry manifest, the final argv and the not-executed state,
  without importing MuJoCo, without starting the head worker and without a
  model forward.

The pinned trees and the original runner are read-only inputs.  Only copies
created by the test itself are ever modified.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_HELPER = REPO_ROOT / 'harness' / 'pair_worker_bundle.py'
CANDIDATE_AUDIT = REPO_ROOT / 'harness' / 'pair_worker_audit.py'
CANDIDATE_ENTRY = REPO_ROOT / 'harness' / 'pair_worker_audit_entry.py'
CANDIDATE_OBSERVER = REPO_ROOT / 'harness' / 'pair_proposal_observer.py'
OWNED_RUNNER = REPO_ROOT / 'experiments' / '2026-11-05-pair-runner-wire' / \
    'run_cpu_joint_e2e_audit_wire.py'
CONSUMER_RUNNER = REPO_ROOT / 'experiments' / '2026-11-05-pair-consumer-audit' / \
    'run_cpu_joint_e2e_consumer_audit.py'

PINNED_TREE = Path('/home/ubuntu/UGRP/experiments/'
                   '2026-11-04-joint-act-4tree-assembly-diag-v1/out/trees/worker')
GEOMETRY_WORKER = Path('/home/ubuntu/ugrp-retrain-geom-20261029/received/final/'
                       'extracted/scripts/geometry_pair_worker.py')
HEAD_WORKER = Path('/home/ubuntu/ugrp-retrain-geom-20261029/implementation/'
                   'geometry_worker.py')
HEAD_POLICY = Path('/home/ubuntu/ugrp-retrain-geom-20261029/implementation/'
                   'geometry_policy.py')
CONFIG = Path('/home/ubuntu/ugrp-wt/codex-pair-fix-cpu-20261027/experiments/'
              '2026-10-21-pairact-r1/PAIRACT_R1_TRAIN_CONFIG_DRAFT.json')
ASTRA = Path('/home/ubuntu/UGRP/experiments/2026-11-04-astra-strict-eval-v1/'
             'snapshot/harness/pairact_student_eval.py')

# The coordinator's FROZEN core: these bytes must not change under this
# wiring.  They are the independent pins the entry and the runners carry.
CORE_AUDIT_SHA = 'cfe4cbfa2565003063aa69980abd759b5364877e0aa45cc709ebb6a32bef099d'
CORE_OBSERVER_SHA = ('19d2af7f1d972b25b0e3069424046539d995ade4eef0e62fd2b66013a3'
                      '9ea35d')

# 7 pinned tree files + 4 candidate files + 5 read-only originals.
MANIFEST_ENTRY_COUNT = 16
CANDIDATE_COUNT = 4
OBSERVER_OPTION = '--observe-raw-proposals'

pytestmark = pytest.mark.skipif(not PINNED_TREE.is_dir(),
                                reason='the pinned worker tree is not available')


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_file(path):
    hasher = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


@pytest.fixture(scope='session')
def bundle_helper():
    return _load(BUNDLE_HELPER, 'ugrp_pair_worker_bundle_observer_test')


@pytest.fixture(scope='session')
def runner():
    return _load(OWNED_RUNNER, 'ugrp_pair_runner_observer_test')


@pytest.fixture(scope='session')
def consumer_runner():
    return _load(CONSUMER_RUNNER, 'ugrp_pair_consumer_runner_observer_test')


@pytest.fixture(scope='session')
def entry_module():
    return _load(CANDIDATE_ENTRY, 'ugrp_pair_audit_entry_observer_test')


@pytest.fixture(scope='session')
def bundle_root(tmp_path_factory, bundle_helper):
    """A real bundle: the pinned tree byte for byte plus the 4 candidates."""
    dest = tmp_path_factory.mktemp('observer-bundle') / 'tree'
    bundle_helper.create_bundle(dest=dest, pinned_tree=PINNED_TREE,
                                candidates=[CANDIDATE_AUDIT, CANDIDATE_ENTRY,
                                            BUNDLE_HELPER, CANDIDATE_OBSERVER],
                                externals=[GEOMETRY_WORKER, HEAD_WORKER, HEAD_POLICY,
                                           CONFIG, ASTRA])
    return dest


# ------------------------------------------------------------- the frozen core

def test_the_core_files_are_the_frozen_coordinator_bytes():
    assert sha256_file(CANDIDATE_AUDIT) == CORE_AUDIT_SHA
    assert sha256_file(CANDIDATE_OBSERVER) == CORE_OBSERVER_SHA


# ------------------------------------------------------------- the same tree

def test_the_observer_is_copied_into_the_same_harness_tree(bundle_root):
    observer = bundle_root / 'harness' / 'pair_proposal_observer.py'
    controller = bundle_root / 'harness' / 'pairact_r1_student.py'
    assert observer.is_file()
    assert controller.is_file()
    assert observer.parent == controller.parent


def test_the_copied_observer_is_byte_identical_to_the_core(bundle_root):
    assert sha256_file(bundle_root / 'harness' / 'pair_proposal_observer.py') == \
        sha256_file(CANDIDATE_OBSERVER)
    assert sha256_file(bundle_root / 'harness' / 'pair_worker_audit.py') == \
        sha256_file(CANDIDATE_AUDIT)


def test_the_real_import_proves_the_observer_comes_from_the_bundle(bundle_root,
                                                                    bundle_helper):
    modules = bundle_helper.verify_import_same_tree(bundle_root)
    assert 'harness.pair_proposal_observer' in modules
    assert Path(modules['harness.pair_proposal_observer']).parent == \
        bundle_root / 'harness'


def test_an_incomplete_candidate_set_is_refused(bundle_helper, tmp_path):
    """A bundle without the observer would bind only 15 entries."""
    with pytest.raises(bundle_helper.BundleError):
        bundle_helper.create_bundle(dest=tmp_path / 'no-observer',
                                    pinned_tree=PINNED_TREE,
                                    candidates=[CANDIDATE_AUDIT, CANDIDATE_ENTRY,
                                                BUNDLE_HELPER])


def test_a_swapped_observer_is_refused_before_the_bundle_is_built(bundle_helper,
                                                                   tmp_path):
    fake = tmp_path / 'pair_proposal_observer.py'
    fake.write_text('# not the frozen observer\n', encoding='utf-8')
    with pytest.raises(bundle_helper.BundleError):
        bundle_helper.create_bundle(dest=tmp_path / 'swapped', pinned_tree=PINNED_TREE,
                                    candidates=[CANDIDATE_AUDIT, CANDIDATE_ENTRY,
                                                BUNDLE_HELPER, fake],
                                    externals=[GEOMETRY_WORKER, HEAD_WORKER,
                                               HEAD_POLICY, CONFIG, ASTRA])


# ------------------------------------------------------------- the manifest

def test_the_manifest_binds_sixteen_entries(bundle_root, bundle_helper):
    manifest = bundle_helper.load_manifest(bundle_root / 'bundle-manifest.json')
    assert len(manifest) == MANIFEST_ENTRY_COUNT
    verified = bundle_helper.verify_manifest(bundle_root / 'bundle-manifest.json')
    assert len(verified) == MANIFEST_ENTRY_COUNT


def test_the_manifest_binds_the_four_candidates_and_the_five_originals(
        bundle_root, bundle_helper):
    manifest = bundle_helper.load_manifest(bundle_root / 'bundle-manifest.json')
    for relative in bundle_helper.CANDIDATE_TREE_FILES:
        assert str(bundle_root / relative) in manifest
    assert sum(1 for entry in manifest.values() if entry['role'] == 'candidate') == \
        CANDIDATE_COUNT
    for external in (GEOMETRY_WORKER, HEAD_WORKER, HEAD_POLICY, CONFIG, ASTRA):
        assert str(external) in manifest
    assert manifest[str(bundle_root / 'harness' / 'pair_proposal_observer.py')][
        'sha256'] == CORE_OBSERVER_SHA


def test_an_empty_manifest_is_not_a_verified_pin(bundle_helper, tmp_path):
    empty = tmp_path / 'empty.json'
    empty.write_text('{}', encoding='utf-8')
    with pytest.raises(bundle_helper.BundleError):
        bundle_helper.verify_manifest(empty)


def test_a_manifest_without_the_observer_is_refused(bundle_root, bundle_helper,
                                                    tmp_path):
    manifest = bundle_helper.load_manifest(bundle_root / 'bundle-manifest.json')
    observer = str(bundle_root / 'harness' / 'pair_proposal_observer.py')
    trimmed = {key: value for key, value in manifest.items() if key != observer}
    path = tmp_path / 'no-observer.json'
    path.write_text(json.dumps(trimmed), encoding='utf-8')
    with pytest.raises(bundle_helper.BundleError):
        bundle_helper.verify_manifest(path, required=set(manifest))


def test_a_forged_observer_hash_is_refused(bundle_root, bundle_helper, tmp_path):
    manifest = bundle_helper.load_manifest(bundle_root / 'bundle-manifest.json')
    observer = str(bundle_root / 'harness' / 'pair_proposal_observer.py')
    forged = dict(manifest)
    forged[observer] = dict(manifest[observer], sha256='0' * 64)
    path = tmp_path / 'forged-observer.json'
    path.write_text(json.dumps(forged), encoding='utf-8')
    with pytest.raises(bundle_helper.BundleError):
        bundle_helper.verify_manifest(path)


# ------------------------------------------------------- the independent pins

def test_the_entry_carries_independent_hashes(entry_module):
    assert entry_module.EXPECTED_AUDIT_MODULE_SHA == sha256_file(CANDIDATE_AUDIT)
    assert entry_module.EXPECTED_OBSERVER_MODULE_SHA == sha256_file(CANDIDATE_OBSERVER)
    assert entry_module.EXPECTED_HELPER_SHA == sha256_file(BUNDLE_HELPER)
    assert entry_module.EXPECTED_OBSERVER_MODULE_SHA == CORE_OBSERVER_SHA


def test_the_entry_startup_scope_covers_the_observer(entry_module, bundle_root,
                                                     bundle_helper):
    """The entry requires ALL 16 manifest entries: the 15 independent expected
    hashes plus the entry file itself."""
    expected = entry_module.expected_startup_hashes(bundle_root)
    observer = str(bundle_root / 'harness' / 'pair_proposal_observer.py')
    assert observer in expected
    assert expected[observer] == CORE_OBSERVER_SHA
    manifest = bundle_helper.load_manifest(bundle_root / 'bundle-manifest.json')
    required = set(expected) | {str(bundle_root / 'harness' / 'pair_worker_audit_entry.py')}
    assert len(required) == MANIFEST_ENTRY_COUNT
    assert required == set(manifest)


def test_both_runners_pin_the_four_candidates(runner, consumer_runner):
    for module in (runner, consumer_runner):
        assert len(module.EXPECTED_CANDIDATE_SHAS) == CANDIDATE_COUNT
        for candidate, sha in module.EXPECTED_CANDIDATE_SHAS.items():
            assert sha256_file(candidate) == sha, candidate
        assert module.EXPECTED_CANDIDATE_SHAS[str(CANDIDATE_OBSERVER)] == \
            CORE_OBSERVER_SHA


def test_the_helper_and_the_runners_agree_on_the_observer_pin(runner, consumer_runner,
                                                               bundle_helper):
    assert bundle_helper.EXPECTED_OBSERVER_SHA == CORE_OBSERVER_SHA
    assert runner.EXPECTED_CANDIDATE_SHAS[str(CANDIDATE_OBSERVER)] == \
        bundle_helper.EXPECTED_OBSERVER_SHA
    assert consumer_runner.EXPECTED_CANDIDATE_SHAS[str(CANDIDATE_OBSERVER)] == \
        bundle_helper.EXPECTED_OBSERVER_SHA


# ---------------------------------------------------------- the outer runners

def _plan_args(**overrides):
    values = dict(audit_worker='on', audit_run_id='observer-plan-1',
                  audit_output_root=None, bundle_root=None, prepare_only=False,
                  observe_raw_proposals=False)
    values.update(overrides)
    return argparse.Namespace(**values)


def test_the_observer_option_is_off_by_default(runner, tmp_path):
    out = tmp_path / 'run'
    out.mkdir()
    plan = runner.plan_worker(out=out, trace_dir=out / 'trace', args=_plan_args())
    assert OBSERVER_OPTION not in plan['argv']
    assert plan['observe_raw_proposals'] is False


def test_the_observer_option_is_passed_to_the_entry_when_requested(runner, tmp_path):
    out = tmp_path / 'run'
    out.mkdir()
    plan = runner.plan_worker(out=out, trace_dir=out / 'trace',
                              args=_plan_args(observe_raw_proposals=True))
    assert plan['argv'][-1] == OBSERVER_OPTION
    assert plan['observe_raw_proposals'] is True
    # the rest of the audited argv is unchanged
    assert plan['argv'][plan['argv'].index('--model') + 1] == runner.CKPT
    assert plan['argv'][plan['argv'].index('--config') + 1] == runner.CONFIG
    assert plan['argv'][plan['argv'].index('--headworker') + 1] == runner.HEADWORKER
    assert plan['argv'][plan['argv'].index('--student-root') + 1] == str(out / 'bundle')


def test_the_observer_option_with_audit_off_is_refused(runner, tmp_path):
    out = tmp_path / 'run'
    out.mkdir()
    args = _plan_args(audit_worker='off', observe_raw_proposals=True)
    with pytest.raises(SystemExit):
        runner.plan_worker(out=out, trace_dir=out / 'trace', args=args)
    assert not (out / 'bundle').exists()


def test_the_consumer_runner_refuses_the_observer_with_audit_off(consumer_runner,
                                                                  tmp_path):
    out = tmp_path / 'run'
    out.mkdir()
    args = _plan_args(audit_worker='off', observe_raw_proposals=True)
    with pytest.raises(SystemExit):
        consumer_runner.plan_worker(out=out, trace_dir=out / 'trace', args=args)
    assert not (out / 'bundle').exists()


def test_the_consumer_runner_passes_the_observer_option(consumer_runner, tmp_path):
    out = tmp_path / 'run'
    out.mkdir()
    plan = consumer_runner.plan_worker(out=out, trace_dir=out / 'trace',
                                       args=_plan_args(observe_raw_proposals=True))
    assert plan['argv'][-1] == OBSERVER_OPTION


def test_the_on_plan_binds_the_observer_in_the_manifest(runner, tmp_path):
    out = tmp_path / 'run'
    out.mkdir()
    plan = runner.plan_worker(out=out, trace_dir=out / 'trace',
                              args=_plan_args(observe_raw_proposals=True))
    assert plan['manifest_entries'] == MANIFEST_ENTRY_COUNT
    manifest = json.loads(Path(plan['manifest_path']).read_text(encoding='utf-8'))
    observer = str(Path(plan['bundle_root']) / 'harness' / 'pair_proposal_observer.py')
    assert manifest[observer]['sha256'] == CORE_OBSERVER_SHA


# ------------------------------------------------------------ the entry CLI

def _entry_argv(bundle_root, workdir, run_id='observer-entry-1', manifest=None,
                extra=()):
    argv = [sys.executable, str(bundle_root / 'harness' / 'pair_worker_audit_entry.py'),
            '--student-root', str(bundle_root), '--geometry-worker', str(GEOMETRY_WORKER),
            '--headworker', str(HEAD_WORKER), '--config', str(CONFIG),
            '--synthetic-predictor',
            '--audit-run-id', run_id,
            '--audit-output-root', str(workdir / 'audit'),
            '--audit-sources', str(manifest or (bundle_root / 'bundle-manifest.json'))]
    argv += list(extra)
    return argv


def _run_entry_cli(argv, workdir):
    environment = dict(os.environ)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    return subprocess.run(argv, capture_output=True, text=True, env=environment,
                          cwd=str(workdir), timeout=300, input='')


def _assert_refused(proc, workdir):
    assert proc.returncode != 0, proc.stdout
    assert 'ready' not in proc.stdout
    assert proc.stderr.strip(), 'the refusal must be reported on stderr'
    audit_root = workdir / 'audit'
    assert not audit_root.exists() or list(audit_root.glob('*.jsonl')) == []
    assert list((workdir / 'trace').glob('*.jsonl')) == []


def test_the_entry_refuses_the_observer_without_the_audit_options(bundle_root, tmp_path):
    argv = [sys.executable, str(bundle_root / 'harness' / 'pair_worker_audit_entry.py'),
            '--student-root', str(bundle_root), '--geometry-worker', str(GEOMETRY_WORKER),
            '--headworker', str(HEAD_WORKER), '--config', str(CONFIG),
            '--synthetic-predictor', OBSERVER_OPTION]
    _assert_refused(_run_entry_cli(argv, tmp_path), tmp_path)


def test_the_entry_refuses_a_manifest_without_the_observer(bundle_root, tmp_path,
                                                            bundle_helper):
    manifest = bundle_helper.load_manifest(bundle_root / 'bundle-manifest.json')
    observer = str(bundle_root / 'harness' / 'pair_proposal_observer.py')
    trimmed = {key: value for key, value in manifest.items() if key != observer}
    path = tmp_path / 'missing-observer.json'
    path.write_text(json.dumps(trimmed), encoding='utf-8')
    argv = _entry_argv(bundle_root, tmp_path, manifest=path, extra=[OBSERVER_OPTION])
    _assert_refused(_run_entry_cli(argv, tmp_path), tmp_path)


def test_the_entry_refuses_a_drifted_observer(bundle_root, tmp_path):
    observer = bundle_root / 'harness' / 'pair_proposal_observer.py'
    original = observer.read_bytes()
    try:
        observer.write_bytes(original + b'\n# drift after the preparation\n')
        argv = _entry_argv(bundle_root, tmp_path, extra=[OBSERVER_OPTION])
        _assert_refused(_run_entry_cli(argv, tmp_path), tmp_path)
    finally:
        observer.write_bytes(original)


def test_the_entry_refuses_a_deleted_observer(bundle_root, tmp_path):
    observer = bundle_root / 'harness' / 'pair_proposal_observer.py'
    original = observer.read_bytes()
    try:
        observer.unlink()
        argv = _entry_argv(bundle_root, tmp_path, extra=[OBSERVER_OPTION])
        _assert_refused(_run_entry_cli(argv, tmp_path), tmp_path)
    finally:
        observer.write_bytes(original)


# ------------------------------------------------- the four-operation protocol

def _drive_entry(argv, ticks, workdir):
    """Speak the four-operation protocol to the entry process."""
    roles = ('r1', 'r2')
    pwm = {'1': 1500, '3': 1500, '4': 1500, '5': 1500, '6': 1500}

    def initial():
        return {'t': 0.0, 'wheels': [0.0] * 4, 'duration_s': [0.0] * 4,
                'pwm': dict(pwm)}

    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, bufsize=1,
                            cwd=str(workdir))
    responses = []

    def send(payload):
        proc.stdin.write(json.dumps(payload, allow_nan=False) + '\n')
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError('entry closed stdout: %s' % proc.stderr.read()[-2000:])
        value = json.loads(line)
        responses.append(value)
        return value

    hello = json.loads(proc.stdout.readline())
    send({'op': 'reset', 'roles': {'r1': 'teal', 'r2': 'blue'},
          'episode_id': 'ep-observer-wire', 'initial': {rid: initial() for rid in roles}})
    applied = {rid: initial() for rid in roles}
    for tick in range(ticks):
        now = round(0.1 * tick, 6)
        send({'op': 'propose', 't': now,
              'robots': {rid: {'jpeg': base64.b64encode(
                  ('%s-%04d' % (rid, tick)).encode('ascii')).decode('ascii'),
                  'issued': applied[rid]} for rid in roles}})
        permit = tick >= 4
        response = send({'op': 'issue', 't': now,
                         'permits': {rid: permit for rid in roles}})
        applied = {rid: response['robots'][rid]['command'] for rid in roles}
    send({'op': 'summary'})
    proc.stdin.close()
    proc.wait(timeout=60)
    return hello, responses, proc.returncode


def test_the_observer_on_and_off_give_identical_responses(bundle_root, tmp_path):
    off_dir = tmp_path / 'off'
    off_dir.mkdir()
    on_dir = tmp_path / 'on'
    on_dir.mkdir()
    _, off_responses, off_rc = _drive_entry(_entry_argv(bundle_root, off_dir), 6, off_dir)
    _, on_responses, on_rc = _drive_entry(
        _entry_argv(bundle_root, on_dir, extra=[OBSERVER_OPTION]), 6, on_dir)
    assert off_rc == on_rc == 0
    assert off_responses == on_responses


def test_the_observer_writes_the_independent_status_file(bundle_root, tmp_path):
    work = tmp_path / 'status'
    work.mkdir()
    _, _, rc = _drive_entry(
        _entry_argv(bundle_root, work, extra=[OBSERVER_OPTION]), 6, work)
    assert rc == 0
    status = work / 'audit' / 'proposal-status-observer-entry-1.json'
    assert status.is_file()
    payload = json.loads(status.read_text(encoding='utf-8'))
    assert payload['finished'] is True
    assert payload['attempted_ticks'] == 6
    assert payload['captured_ticks'] == 6
    assert payload['failed_ticks'] == 0
    assert payload['expected_robot_candidates'] == 12
    assert payload['captured_robot_candidates'] == 12
    assert payload['complete'] is True


def test_the_observer_writes_exactly_one_capture_summary_row(bundle_root, tmp_path):
    """The summary is written ONCE, at loop exit, and carries no body run_id.

    ``run_id`` is a RESERVED sink field: the observer drops it from the body
    before the write, because the existing sink envelope already supplies it.
    """
    work = tmp_path / 'summary-row'
    work.mkdir()
    _, _, rc = _drive_entry(
        _entry_argv(bundle_root, work, extra=[OBSERVER_OPTION]), 6, work)
    assert rc == 0
    audit_file = list((work / 'audit').glob('pair-audit-*.jsonl'))[0]
    rows = [json.loads(line) for line in
            audit_file.read_text(encoding='utf-8').splitlines() if line.strip()]
    summaries = [row for row in rows if row['kind'] == 'proposal_capture_summary']
    assert len(summaries) == 1
    summary = summaries[0]
    # the run id comes from the sink envelope, not from the observer body
    assert summary['run_id'] == 'observer-entry-1'
    assert summary['complete'] is True
    assert summary['attempted_ticks'] == 6
    assert summary['captured_robot_candidates'] == 12


def test_the_observer_keeps_the_origins_unknown(bundle_root, tmp_path):
    work = tmp_path / 'origins'
    work.mkdir()
    _, responses, rc = _drive_entry(
        _entry_argv(bundle_root, work, extra=[OBSERVER_OPTION]), 6, work)
    assert rc == 0
    audit_file = list((work / 'audit').glob('pair-audit-*.jsonl'))[0]
    records = [json.loads(line) for line in
               audit_file.read_text(encoding='utf-8').splitlines() if line.strip()]
    issues = [record for record in records if record['kind'] == 'issue_command']
    assert issues
    assert {record['origin'] for record in issues} == {'unknown'}
    # the raw input contract is unchanged: own JPEG + own issued history only
    assert all(set(record) >= {'robot_id', 't', 'command'} for record in issues)


# ------------------------------------------------------- the prepare-only CLI

def _prepare_cli(tmp_path, runner_path, *extra):
    run_dir = tmp_path / 'run'
    argv = [sys.executable, str(runner_path), '--run-dir', str(run_dir),
            '--prepare-only', '--ticks', '4']
    argv += list(extra)
    environment = dict(os.environ)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    proc = subprocess.run(argv, capture_output=True, text=True, env=environment,
                          cwd=str(REPO_ROOT), timeout=900)
    return proc, run_dir


def test_prepare_only_with_the_observer_binds_sixteen_entries(tmp_path):
    proc, run_dir = _prepare_cli(tmp_path, OWNED_RUNNER, '--audit-worker', 'on',
                                  '--audit-run-id', 'observer-prepare-1',
                                  OBSERVER_OPTION)
    assert proc.returncode == 0, proc.stderr
    prepare = json.loads((run_dir / 'prepare.json').read_text(encoding='utf-8'))
    assert prepare['manifest_verified'] is True
    assert prepare['same_tree_import_verified'] is True
    assert prepare['manifest_entries'] == MANIFEST_ENTRY_COUNT
    assert prepare['observe_raw_proposals'] is True
    assert prepare['executed'] is False
    assert prepare['model_forwards'] == 0
    assert prepare['worker_started'] is False
    assert prepare['mujoco_imported'] is False
    assert OBSERVER_OPTION in prepare['final_argv']


def test_prepare_only_with_the_observer_starts_nothing(tmp_path):
    proc, run_dir = _prepare_cli(tmp_path, OWNED_RUNNER, '--audit-worker', 'on',
                                  '--audit-run-id', 'observer-prepare-2',
                                  OBSERVER_OPTION)
    assert proc.returncode == 0, proc.stderr
    assert not (run_dir / 'scene.xml').exists()
    assert not (run_dir / 'scene.json').exists()
    assert not (run_dir / 'worker-stderr.log').exists()
    assert list((run_dir / 'trace').glob('*.jsonl')) == []
    assert not (run_dir / 'audit').exists() or \
        list((run_dir / 'audit').glob('*.jsonl')) == []


def test_prepare_only_with_the_observer_refuses_audit_off(tmp_path):
    proc, run_dir = _prepare_cli(tmp_path, OWNED_RUNNER, OBSERVER_OPTION)
    assert proc.returncode != 0
    assert 'observe-raw-proposals' in (proc.stderr + proc.stdout)
    assert not (run_dir / 'bundle').exists()


def test_the_consumer_prepare_only_with_the_observer(tmp_path):
    proc, run_dir = _prepare_cli(tmp_path, CONSUMER_RUNNER, '--audit-worker', 'on',
                                  '--audit-run-id', 'observer-consumer-1',
                                  OBSERVER_OPTION)
    assert proc.returncode == 0, proc.stderr
    prepare = json.loads((run_dir / 'prepare.json').read_text(encoding='utf-8'))
    assert prepare['manifest_entries'] == MANIFEST_ENTRY_COUNT
    assert prepare['observe_raw_proposals'] is True
    assert prepare['model_forwards'] == 0
    assert prepare['worker_started'] is False
    assert OBSERVER_OPTION in prepare['final_argv']
    # the consumer ledger is still NOT created in prepare-only mode
    assert not (run_dir / 'consumer-audit').exists()
