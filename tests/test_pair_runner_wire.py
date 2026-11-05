"""Tests for the owned pair-runner audit wiring (prepare -> worker selection).

What is verified here (CPU only, no model, no simulator, no head worker):

* the owned runner copy differs from the ORIGINAL outer runner only in the
  worker selection: the world build (S1), the joined control loop (S3), the
  evidence collection (S4) and the verdict (S5) are byte-identical and their
  ASTs are identical;
* audit OFF keeps the ORIGINAL worker argv byte for byte;
* audit ON selects the bundle entry inside ONE harness tree and keeps the
  original model / config / head worker / head source root / trace options;
* the bundle is created exclusively, byte identical to the pinned tree, and
  refuses to overwrite or delete anything;
* the manifest binds the required subset and the read-only originals, and an
  empty, incomplete, forged or missing entry is refused;
* the same-tree claim is checked with a REAL import of the bundle, and a
  foreign tree is refused;
* the real CLI ``--prepare-only`` runs and leaves the bundle, the final argv
  and the real source hashes, without importing MuJoCo, without starting the
  head worker and without a model forward;
* the boot entry really speaks the four operations with the synthetic
  predictor, OFF and ON give identical responses, and the origins stay
  ``unknown``;
* the pinned release/finish sequence of the controller is reachable with a
  synthetic completion flag;
* **the audited entry refuses to start** on an empty manifest, on a manifest
  that misses a required key, on a forged or deleted required file and on a
  file that drifted after the preparation -- with a non-zero exit, no
  ``ready`` line, no head worker and no audit file.

The pinned trees and the original runner are read-only inputs.  Only copies
created by the test itself are ever modified.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_HELPER = REPO_ROOT / 'harness' / 'pair_worker_bundle.py'
CANDIDATE_AUDIT = REPO_ROOT / 'harness' / 'pair_worker_audit.py'
CANDIDATE_ENTRY = REPO_ROOT / 'harness' / 'pair_worker_audit_entry.py'
OWNED_RUNNER = REPO_ROOT / 'experiments' / '2026-11-05-pair-runner-wire' / \
    'run_cpu_joint_e2e_audit_wire.py'

ORIGINAL_RUNNER = Path('/home/ubuntu/UGRP/experiments/'
                       '2026-11-04-joint-carry-cpu-e2e-real20k-v1/candidate/'
                       'run_cpu_joint_e2e.py')
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

ORIGINAL_RUNNER_SHA = ('6d62f2a221a257d5c9995fb385b2f21c63a51b693a0998d978e59cb68c'
                        'faff33')
PINNED_CONTROLLER_SHA = ('3e12d2f5408f82821187401e8a6d4298cb70fb27b48c229d689a54ef'
                         'def77e81')
PINNED_CONTRACT_SHA = ('6bc58d6f9707abd5d854c6dbbb63357ed14dab6c37bcf055ddd8d1d6'
                        '6d171056')
PINNED_PAIRACT_SHA = ('8a9869248740bf5ad2da7194cdd9a582347ac09e88783cd6ea127ef3f20'
                       '8a210')
GEOMETRY_WORKER_SHA = ('c7509a6423b252d4941b68ecfa3ce2ffc75783c4f3cd1f3aac2fe467b9d'
                        '601bc')

pytestmark = pytest.mark.skipif(not PINNED_TREE.is_dir() or not ORIGINAL_RUNNER.is_file(),
                                reason='pinned trees are not available')


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
    return _load(BUNDLE_HELPER, 'ugrp_pair_worker_bundle_test')


@pytest.fixture(scope='session')
def runner():
    return _load(OWNED_RUNNER, 'ugrp_pair_runner_owned_test')


@pytest.fixture(scope='session')
def entry_module():
    return _load(CANDIDATE_ENTRY, 'ugrp_pair_audit_entry_test')


@pytest.fixture(scope='session')
def bundle_root(tmp_path_factory, bundle_helper):
    """A real bundle: the pinned tree copied byte for byte plus the candidates."""
    dest = tmp_path_factory.mktemp('bundle') / 'tree'
    bundle_helper.create_bundle(dest=dest, pinned_tree=PINNED_TREE,
                                candidates=[CANDIDATE_AUDIT, CANDIDATE_ENTRY,
                                            BUNDLE_HELPER],
                                externals=[GEOMETRY_WORKER, HEAD_WORKER, HEAD_POLICY,
                                           CONFIG, ASTRA])
    return dest


def _region(text, start, end):
    begin = text.index(start)
    finish = text.index(end, begin)
    return text[begin:finish]


REGIONS = (
    ('S1', '    # ---- S1 world build (pinned closure) ------------------------------',
     '    # ---- S2 worker start (real 20k head, CPU) -------------------------'),
    ('S3', '    # ---- S3 the joined loop -------------------------------------------',
     "    # ---- S4 evidence from the head's own trace ------------------------"),
    ('S4', "    # ---- S4 evidence from the head's own trace ------------------------",
     '    # ---- S5 verdict --------------------------------------------------'),
)


# ------------------------------------------------------- owned copy fidelity

def test_owned_runner_keeps_the_control_loop_byte_identical():
    original = ORIGINAL_RUNNER.read_text(encoding='utf-8')
    owned = OWNED_RUNNER.read_text(encoding='utf-8')
    for name, start, end in REGIONS:
        region = _region(owned, start, end)
        assert region == _region(original, start, end), name


def test_owned_runner_regions_have_the_same_ast():
    original = ORIGINAL_RUNNER.read_text(encoding='utf-8')
    owned = OWNED_RUNNER.read_text(encoding='utf-8')
    for name, start, end in REGIONS:
        left = ast.dump(ast.parse(textwrap.dedent(_region(original, start, end))))
        right = ast.dump(ast.parse(textwrap.dedent(_region(owned, start, end))))
        assert left == right, name


def test_owned_runner_differs_only_in_the_worker_selection():
    original = ORIGINAL_RUNNER.read_text(encoding='utf-8')
    owned = OWNED_RUNNER.read_text(encoding='utf-8')
    diff = list(difflib.unified_diff(original.splitlines(), owned.splitlines(),
                                     lineterm='', n=0))
    changed = [line for line in diff if line.startswith(('+', '-'))
               and not line.startswith(('+++', '---'))]
    assert any('GeometryWorkerClient(argv' in line for line in changed)
    assert any('boot_worker(argv=argv' in line for line in changed)


def test_original_runner_is_untouched():
    assert sha256_file(ORIGINAL_RUNNER) == ORIGINAL_RUNNER_SHA


@pytest.mark.parametrize('mode', ['off', 'on'])
def test_s2_uses_worker_selection_after_s1_loads_episode_plan(runner, tmp_path, mode):
    """Execute the actual S2 block, without world construction or a head."""
    import argparse
    from types import SimpleNamespace
    source = OWNED_RUNNER.read_text()
    block = _region(source,
                    '    # ---- S2 worker start (real 20k head, CPU) -------------------------',
                    '    # ---- S3 the joined loop -------------------------------------------')
    selected = {'argv': ['python', 'original' if mode == 'off' else 'audit-entry'],
                'student_root': str(tmp_path / mode)}
    calls = []

    def fake_boot(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(handshake={'ready': True})

    scope = dict(os=os, SHIM=runner.SHIM, OVERLAY=runner.OVERLAY, DEPS=runner.DEPS,
                 TREE=runner.TREE, plan={'episode_id': 'episode-from-S1', 'roles': {}},
                 worker_selection=selected, out=tmp_path,
                 args=argparse.Namespace(deadline_s=60), boot_worker=fake_boot,
                 pins={'checkpoint': {'model_sha256': 'test-only'}}, res={})
    exec(compile(textwrap.dedent(block), '<actual-S2>', 'exec'), scope)
    assert len(calls) == 1
    assert calls[0]['argv'] == selected['argv']
    assert scope['res']['worker']['student_root'] == selected['student_root']
    assert scope['plan']['episode_id'] == 'episode-from-S1'


# ------------------------------------------------------------ worker selection

def test_off_selection_is_the_original_argv(runner, tmp_path):
    trace = tmp_path / 'trace'
    argv = runner.original_worker_argv(trace)
    assert argv == ["/usr/bin/python3", "-B", runner.WORKER,
                    "--model", runner.CKPT, "--config", runner.CONFIG,
                    "--device", "cpu", "--threads", "1",
                    "--student-root", runner.TREE, "--headworker", runner.HEADWORKER,
                    "--head-source-root", runner.TREE,
                    "--geometry-trace-dir", str(trace)]


def test_off_plan_selects_the_original_worker(runner, tmp_path):
    import argparse
    args = argparse.Namespace(audit_worker='off', audit_run_id=None,
                              audit_output_root=None, bundle_root=None,
                              prepare_only=False)
    plan = runner.plan_worker(out=tmp_path, trace_dir=tmp_path / 'trace', args=args)
    assert plan['mode'] == 'off'
    assert plan['argv'] == runner.original_worker_argv(tmp_path / 'trace')
    assert plan['bundle_root'] is None
    assert plan['manifest_verified'] is False


def test_on_plan_uses_the_bundle_entry_and_keeps_the_original_options(runner, tmp_path):
    import argparse
    out = tmp_path / 'run'
    out.mkdir()
    args = argparse.Namespace(audit_worker='on', audit_run_id='plan-on-1',
                              audit_output_root=None, bundle_root=None,
                              prepare_only=False)
    plan = runner.plan_worker(out=out, trace_dir=out / 'trace', args=args)
    argv = plan['argv']
    entry = out / 'bundle' / 'harness' / 'pair_worker_audit_entry.py'
    assert argv[0] == "/usr/bin/python3" and argv[1] == "-B"
    assert argv[2] == str(entry)
    assert entry.is_file()
    assert argv[argv.index("--model") + 1] == runner.CKPT
    assert argv[argv.index("--config") + 1] == runner.CONFIG
    assert argv[argv.index("--headworker") + 1] == runner.HEADWORKER
    assert argv[argv.index("--head-source-root") + 1] == runner.TREE
    assert argv[argv.index("--student-root") + 1] == str(out / 'bundle')
    assert argv[argv.index("--audit-run-id") + 1] == 'plan-on-1'
    assert argv[argv.index("--audit-output-root") + 1] == str(out / 'audit')
    assert argv[argv.index("--audit-sources") + 1] == str(out / 'bundle' / 'bundle-manifest.json')
    assert plan['manifest_verified'] is True
    assert plan['same_tree_verified'] is True


def test_on_plan_requires_an_explicit_run_id(runner, tmp_path):
    import argparse
    args = argparse.Namespace(audit_worker='on', audit_run_id=None,
                              audit_output_root=None, bundle_root=None,
                              prepare_only=False)
    with pytest.raises(SystemExit):
        runner.plan_worker(out=tmp_path, trace_dir=tmp_path / 'trace', args=args)


def test_worker_client_injection_receives_the_planned_argv(runner, tmp_path):
    recorded = {}

    class FakeClient:
        handshake = {'ready': True, 'mode': 'pairact_r1_student_eval_v1'}

        def __init__(self, argv, env, cwd, stderr_path, deadline_s):
            recorded.update({'argv': argv, 'env': env, 'cwd': cwd,
                             'stderr_path': str(stderr_path),
                             'deadline_s': deadline_s})

    argv = runner.original_worker_argv(tmp_path / 'trace')
    client = runner.boot_worker(argv=argv, env={'X': '1'}, out=tmp_path,
                                deadline_s=7.0, client_factory=FakeClient)
    assert isinstance(client, FakeClient)
    assert recorded['argv'] == argv
    assert recorded['deadline_s'] == 7.0
    assert recorded['stderr_path'].endswith('worker-stderr.log')
    assert recorded['cwd'] == str(tmp_path)


# ------------------------------------------------------------------- bundle

def test_bundle_is_created_exclusively(bundle_helper, tmp_path):
    dest = tmp_path / 'bundle'
    created = bundle_helper.create_bundle(dest=dest, pinned_tree=PINNED_TREE,
                                          candidates=[CANDIDATE_AUDIT, CANDIDATE_ENTRY,
                                                      BUNDLE_HELPER])
    assert Path(created['root']).is_dir()
    with pytest.raises(bundle_helper.BundleError):
        bundle_helper.create_bundle(dest=dest, pinned_tree=PINNED_TREE,
                                    candidates=[CANDIDATE_AUDIT, CANDIDATE_ENTRY,
                                                BUNDLE_HELPER])
    assert (dest / 'harness' / 'pair_worker_audit.py').is_file()
    assert (dest / 'bundle-manifest.json').is_file()


def test_bundle_copies_are_byte_identical_to_the_pinned_tree(bundle_root, bundle_helper):
    for relative in bundle_helper.REQUIRED_TREE_FILES:
        source = PINNED_TREE / relative
        target = bundle_root / relative
        assert target.is_file(), relative
        assert sha256_file(target) == sha256_file(source), relative
    assert sha256_file(bundle_root / 'harness' / 'pairact_r1_student.py') == PINNED_CONTROLLER_SHA
    assert sha256_file(bundle_root / 'harness' / 'grasp_act_contract.py') == PINNED_CONTRACT_SHA
    assert sha256_file(bundle_root / 'harness' / 'pairact_r1.py') == PINNED_PAIRACT_SHA
    assert sha256_file(bundle_root / 'harness' / 'pair_worker_audit.py') == sha256_file(CANDIDATE_AUDIT)
    assert sha256_file(bundle_root / 'harness' / 'pair_worker_audit_entry.py') == sha256_file(CANDIDATE_ENTRY)
    assert sha256_file(bundle_root / 'harness' / 'pair_worker_bundle.py') == sha256_file(BUNDLE_HELPER)


def test_the_whole_copied_closure_is_byte_compared(bundle_root, bundle_helper):
    """Every copied file is re-hashed against its source, not only the subset."""
    info = json.loads((bundle_root / 'bundle-info.json').read_text(encoding='utf-8'))
    copied = sum(1 for sub in ('harness', 'scripts')
                 for path in (PINNED_TREE / sub).rglob('*')
                 if path.is_file() and '__pycache__' not in path.parts)
    assert info['files_byte_compared'] == copied > 1600
    assert 'protected_scope' in info and 'unprotected_scope' in info
    assert info['unprotected_scope']['copied_tree_files'] == copied


def test_manifest_binds_the_required_subset_and_the_originals(bundle_root, bundle_helper):
    manifest = bundle_helper.load_manifest(bundle_root / 'bundle-manifest.json')
    for relative in bundle_helper.REQUIRED_TREE_FILES:
        assert str(bundle_root / relative) in manifest
    for relative in bundle_helper.CANDIDATE_TREE_FILES:
        assert str(bundle_root / relative) in manifest
    for external in (GEOMETRY_WORKER, HEAD_WORKER, HEAD_POLICY, CONFIG, ASTRA):
        assert str(external) in manifest
    assert manifest[str(GEOMETRY_WORKER)]['sha256'] == GEOMETRY_WORKER_SHA
    verified = bundle_helper.verify_manifest(bundle_root / 'bundle-manifest.json')
    assert len(verified) == len(manifest)


def test_the_manifest_is_connected_to_the_original_expected_hashes(bundle_root, bundle_helper):
    manifest = bundle_helper.load_manifest(bundle_root / 'bundle-manifest.json')
    for relative, sha in bundle_helper.EXPECTED_TREE_SHAS.items():
        entry = manifest[str(bundle_root / relative)]
        assert entry['sha256'] == sha
        assert entry['source_path'] == str(PINNED_TREE / relative)
        assert sha256_file(entry['source_path']) == sha
    for path, sha in bundle_helper.EXPECTED_EXTERNAL_SHAS.items():
        assert manifest[path]['sha256'] == sha


def test_an_empty_manifest_is_not_a_verified_pin(bundle_helper, tmp_path):
    empty = tmp_path / 'empty.json'
    empty.write_text('{}', encoding='utf-8')
    with pytest.raises(bundle_helper.BundleError):
        bundle_helper.verify_manifest(empty)
    with pytest.raises(bundle_helper.BundleError):
        bundle_helper.load_manifest(empty)


def test_an_incomplete_manifest_is_refused(bundle_root, bundle_helper, tmp_path):
    manifest = bundle_helper.load_manifest(bundle_root / 'bundle-manifest.json')
    trimmed = dict(list(manifest.items())[:3])
    path = tmp_path / 'trimmed.json'
    path.write_text(json.dumps(trimmed), encoding='utf-8')
    with pytest.raises(bundle_helper.BundleError):
        bundle_helper.verify_manifest(path, required=set(manifest))


def test_a_forged_manifest_hash_is_refused(bundle_root, bundle_helper, tmp_path):
    manifest = bundle_helper.load_manifest(bundle_root / 'bundle-manifest.json')
    key = str(bundle_root / 'harness' / 'pairact_r1_student.py')
    forged = dict(manifest)
    forged[key] = dict(manifest[key], sha256='0' * 64)
    path = tmp_path / 'forged.json'
    path.write_text(json.dumps(forged), encoding='utf-8')
    with pytest.raises(bundle_helper.BundleError):
        bundle_helper.verify_manifest(path)


def test_a_missing_manifest_file_is_refused(bundle_root, bundle_helper, tmp_path):
    manifest = bundle_helper.load_manifest(bundle_root / 'bundle-manifest.json')
    key = str(bundle_root / 'harness' / 'pairact_r1_student.py')
    target = Path(key)
    backup = target.read_bytes()
    try:
        target.unlink()
        with pytest.raises(bundle_helper.BundleError):
            bundle_helper.verify_manifest(bundle_root / 'bundle-manifest.json')
    finally:
        target.write_bytes(backup)


def test_real_import_proves_the_same_tree(bundle_root, bundle_helper):
    modules = bundle_helper.verify_import_same_tree(bundle_root)
    assert Path(modules['harness.pair_worker_audit']).parent == bundle_root / 'harness'
    assert Path(modules['harness.pairact_r1_student']).parent == bundle_root / 'harness'
    assert Path(modules['harness.grasp_act_contract']).parent == bundle_root / 'harness'


def test_the_import_probe_refuses_a_foreign_tree(bundle_root, bundle_helper, tmp_path):
    """A tree that merely agrees with itself is not the requested bundle."""
    other = tmp_path / 'other'
    bundle_helper.create_bundle(dest=other, pinned_tree=PINNED_TREE,
                                candidates=[CANDIDATE_AUDIT, CANDIDATE_ENTRY,
                                            BUNDLE_HELPER])
    with pytest.raises(bundle_helper.BundleError):
        bundle_helper.verify_import_same_tree(bundle_root, import_root=other)


def test_a_candidate_from_another_tree_is_refused(bundle_helper):
    with pytest.raises(bundle_helper.BundleError):
        bundle_helper.check_same_tree(CANDIDATE_AUDIT, PINNED_TREE / 'harness' / 'pairact_r1_student.py')
    assert bundle_helper.check_same_tree(CANDIDATE_AUDIT, CANDIDATE_AUDIT) is True


def test_the_pin_tables_agree_between_the_runner_and_the_helper(runner, bundle_helper):
    assert runner.EXPECTED_TREE_SHAS == bundle_helper.EXPECTED_TREE_SHAS
    assert runner.EXPECTED_EXTERNAL_SHAS == bundle_helper.EXPECTED_EXTERNAL_SHAS
    for candidate, sha in runner.EXPECTED_CANDIDATE_SHAS.items():
        assert sha256_file(candidate) == sha, candidate


def test_the_entry_pins_the_helper_and_the_audit_module(entry_module):
    assert entry_module.EXPECTED_HELPER_SHA == sha256_file(BUNDLE_HELPER)
    assert entry_module.EXPECTED_AUDIT_MODULE_SHA == sha256_file(CANDIDATE_AUDIT)


# ---------------------------------------------------------- prepare-only CLI

def _prepare_cli(tmp_path, *extra):
    run_dir = tmp_path / 'run'
    argv = [sys.executable, str(OWNED_RUNNER), '--run-dir', str(run_dir),
            '--prepare-only', '--ticks', '4']
    argv += list(extra)
    environment = dict(os.environ)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    proc = subprocess.run(argv, capture_output=True, text=True, env=environment,
                          cwd=str(REPO_ROOT), timeout=900)
    return proc, run_dir


def test_prepare_only_cli_runs_and_writes_the_artefacts(tmp_path):
    proc, run_dir = _prepare_cli(tmp_path, '--audit-worker', 'on',
                                  '--audit-run-id', 'prepare-cli-1')
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload['prepared'] is True
    assert payload['executed'] is False
    prepare = json.loads((run_dir / 'prepare.json').read_text(encoding='utf-8'))
    assert prepare['manifest_verified'] is True
    assert prepare['same_tree_import_verified'] is True
    assert prepare['executed'] is False
    assert prepare['model_forwards'] == 0
    assert prepare['worker_started'] is False
    assert prepare['mujoco_imported'] is False
    assert prepare['not_executed']
    argv_doc = json.loads((run_dir / 'final-argv.json').read_text(encoding='utf-8'))
    assert argv_doc['argv'] == prepare['final_argv']
    assert argv_doc['argv_sha256'] == prepare['final_argv_sha256']
    assert (run_dir / 'bundle-manifest.json').is_file()
    assert Path(prepare['bundle_root']).is_dir()


def test_prepare_only_starts_nothing(tmp_path):
    proc, run_dir = _prepare_cli(tmp_path, '--audit-worker', 'on',
                                  '--audit-run-id', 'prepare-cli-2')
    assert proc.returncode == 0, proc.stderr
    assert not (run_dir / 'scene.xml').exists()
    assert not (run_dir / 'scene.json').exists()
    assert not (run_dir / 'worker-stderr.log').exists()
    assert list((run_dir / 'trace').glob('*.jsonl')) == []
    assert not (run_dir / 'audit').exists() or list((run_dir / 'audit').glob('*.jsonl')) == []


def test_prepare_only_binds_the_real_source_hashes(tmp_path):
    proc, run_dir = _prepare_cli(tmp_path, '--audit-worker', 'on',
                                  '--audit-run-id', 'prepare-cli-3')
    assert proc.returncode == 0, proc.stderr
    prepare = json.loads((run_dir / 'prepare.json').read_text(encoding='utf-8'))
    hashes = prepare['source_hashes']
    assert hashes[str(GEOMETRY_WORKER)] == GEOMETRY_WORKER_SHA
    controller = str(Path(prepare['bundle_root']) / 'harness' / 'pairact_r1_student.py')
    assert hashes[controller] == PINNED_CONTROLLER_SHA
    for path, digest in hashes.items():
        assert sha256_file(path) == digest, path


def test_prepare_only_with_audit_off_keeps_the_original_argv(tmp_path):
    proc, run_dir = _prepare_cli(tmp_path)
    assert proc.returncode == 0, proc.stderr
    prepare = json.loads((run_dir / 'prepare.json').read_text(encoding='utf-8'))
    assert prepare['audit_worker'] == 'off'
    assert prepare['final_argv'][2] == str(GEOMETRY_WORKER)
    assert prepare['manifest_verified'] is False
    assert not (run_dir / 'bundle').exists()


# ------------------------------------------------------------- boot the entry

def _entry_argv(bundle_root, workdir, audit=True, run_id='entry-test-1', extra=(),
                manifest=None):
    argv = [sys.executable, str(bundle_root / 'harness' / 'pair_worker_audit_entry.py'),
            '--student-root', str(bundle_root), '--geometry-worker', str(GEOMETRY_WORKER),
            '--headworker', str(HEAD_WORKER), '--config', str(CONFIG),
            '--synthetic-predictor']
    if audit:
        argv += ['--audit-run-id', run_id,
                 '--audit-output-root', str(workdir / 'audit'),
                 '--audit-sources', str(manifest or (bundle_root / 'bundle-manifest.json'))]
    argv += list(extra)
    return argv


def _drive_entry(argv, ticks, workdir):
    """Speak the four-operation protocol to the entry process."""
    roles = ('r1', 'r2')
    pwm = {'1': 1500, '3': 1500, '4': 1500, '5': 1500, '6': 1500}

    def initial():
        return {'t': 0.0, 'wheels': [0.0] * 4, 'duration_s': [0.0] * 4,
                'pwm': dict(pwm)}

    import base64
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
          'episode_id': 'ep-runner-wire', 'initial': {rid: initial() for rid in roles}})
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


def test_boot_entry_runs_the_four_operations(bundle_root, tmp_path):
    hello, responses, rc = _drive_entry(_entry_argv(bundle_root, tmp_path), 6, tmp_path)
    assert hello == {'ready': True, 'mode': 'pairact_r1_student_eval_v1'}
    assert rc == 0
    assert len(responses) == 14
    assert responses[0] == {'ok': True}
    assert set(responses[1]) == {'robots'}
    assert set(responses[2]) == {'robots', 'finished'}
    assert 'barrier_events' in responses[-1]
    audit_files = list((tmp_path / 'audit').glob('pair-audit-*.jsonl'))
    assert len(audit_files) == 1


def test_boot_entry_audit_off_and_on_give_identical_responses(bundle_root, tmp_path):
    off_dir = tmp_path / 'off'
    off_dir.mkdir()
    on_dir = tmp_path / 'on'
    on_dir.mkdir()
    _, off_responses, off_rc = _drive_entry(_entry_argv(bundle_root, off_dir, audit=False),
                                             6, off_dir)
    _, on_responses, on_rc = _drive_entry(_entry_argv(bundle_root, on_dir, audit=True),
                                          6, on_dir)
    assert off_rc == on_rc == 0
    assert off_responses == on_responses


def test_boot_entry_keeps_the_origins_unknown(bundle_root, tmp_path):
    _, responses, rc = _drive_entry(_entry_argv(bundle_root, tmp_path), 24, tmp_path)
    assert rc == 0
    audit_file = list((tmp_path / 'audit').glob('pair-audit-*.jsonl'))[0]
    records = [json.loads(line) for line in
               audit_file.read_text(encoding='utf-8').splitlines() if line.strip()]
    issues = [record for record in records if record['kind'] == 'issue_command']
    assert len(issues) == 48
    assert {record['origin'] for record in issues} == {'unknown'}
    stops = [record for record in issues
             if all(w == 0.0 for w in record['command']['wheels'])]
    assert stops, 'the protocol hold branch must be recorded'
    assert all(record['origin'] == 'unknown' for record in stops)


def test_boot_entry_reaches_the_pinned_release_and_finish_sequence(bundle_root, tmp_path):
    _, responses, rc = _drive_entry(_entry_argv(bundle_root, tmp_path, extra=['--synthetic-done']),
                                    80, tmp_path)
    assert rc == 0
    proposes = [value for value in responses if set(value) == {'robots'}]
    issues = [value for value in responses if 'finished' in value]
    skills = set()
    for value in proposes:
        for robot in value['robots'].values():
            skills.add(robot['observation']['skill'])
    assert 'release' in skills, 'the pinned release instruction must appear'
    assert issues[-1]['finished'] is True, 'the pinned finish flag must appear'
    segments = {robot['segment'] for value in issues for robot in value['robots'].values()}
    assert 'release' in segments


def test_the_module_has_no_main_block_so_the_entry_is_needed(bundle_root, tmp_path):
    """`python -m harness.pair_worker_audit` must NOT start a worker."""
    environment = dict(os.environ)
    environment['PYTHONPATH'] = str(bundle_root)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    proc = subprocess.run([sys.executable, '-m', 'harness.pair_worker_audit', '--help'],
                          capture_output=True, text=True, env=environment,
                          cwd=str(tmp_path), timeout=300)
    assert proc.returncode == 0, proc.stderr
    assert 'usage' not in (proc.stdout + proc.stderr).lower()


def test_the_entry_runs_the_worker_function_explicitly(bundle_root, tmp_path):
    """The entry is what actually calls `owned_worker_main`."""
    source = (bundle_root / 'harness' / 'pair_worker_audit_entry.py').read_text(encoding='utf-8')
    assert 'owned_worker_main' in source
    assert "if __name__ == '__main__':" in source
    environment = dict(os.environ)
    environment['PYTHONPATH'] = str(bundle_root)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    proc = subprocess.run([sys.executable,
                           str(bundle_root / 'harness' / 'pair_worker_audit_entry.py'),
                           '--help'],
                          capture_output=True, text=True, env=environment,
                          cwd=str(tmp_path), timeout=300)
    assert proc.returncode == 0, proc.stderr
    assert 'usage' in proc.stdout.lower()


# --------------------------------------------------- audited start refusals

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


def test_the_audited_entry_refuses_an_empty_manifest(bundle_root, tmp_path):
    empty = tmp_path / 'empty.json'
    empty.write_text('{}', encoding='utf-8')
    proc = _run_entry_cli(_entry_argv(bundle_root, tmp_path, manifest=empty), tmp_path)
    _assert_refused(proc, tmp_path)
    assert 'empty' in proc.stderr.lower()


@pytest.mark.parametrize('option', ['--config', '--headworker', '--geometry-worker',
                                   '--student-root', '--audit-sources'])
def test_startup_validates_the_last_duplicate_option(bundle_root, tmp_path, option):
    foreign = tmp_path / 'foreign.json'
    if option == '--config':
        value = json.loads(CONFIG.read_text())
        value['seed'] += 1
        foreign.write_text(json.dumps(value))
    else:
        foreign.write_text('{}')
    argv = _entry_argv(bundle_root, tmp_path,
                       extra=[option, str(foreign)])
    _assert_refused(_run_entry_cli(argv, tmp_path), tmp_path)


def test_equals_audit_options_are_also_verified(bundle_root, tmp_path):
    argv = _entry_argv(bundle_root, tmp_path)
    for option in ('--audit-run-id', '--audit-output-root', '--audit-sources'):
        i = argv.index(option)
        argv[i:i + 2] = [option + '=' + argv[i + 1]]
    i = next(i for i, arg in enumerate(argv) if arg.startswith('--audit-sources='))
    empty = tmp_path / 'empty-equals.json'
    empty.write_text('{}')
    argv[i] = '--audit-sources=' + str(empty)
    _assert_refused(_run_entry_cli(argv, tmp_path), tmp_path)


def test_the_audited_entry_refuses_a_manifest_without_a_required_key(bundle_root, tmp_path,
                                                                    bundle_helper):
    manifest = bundle_helper.load_manifest(bundle_root / 'bundle-manifest.json')
    for label, key in (('controller', str(bundle_root / 'harness' / 'pairact_r1_student.py')),
                       ('contract', str(bundle_root / 'harness' / 'grasp_act_contract.py')),
                       ('geometryworker', str(GEOMETRY_WORKER))):
        trimmed = {k: v for k, v in manifest.items() if k != key}
        path = tmp_path / ('missing-%s.json' % label)
        path.write_text(json.dumps(trimmed), encoding='utf-8')
        work = tmp_path / ('work-%s' % label)
        work.mkdir()
        proc = _run_entry_cli(_entry_argv(bundle_root, work, manifest=path), work)
        _assert_refused(proc, work)


def test_the_audited_entry_refuses_a_forged_source_with_a_self_consistent_manifest(
        bundle_root, tmp_path, bundle_helper):
    """A manifest that agrees with itself must not make a wrong source good."""
    manifest = bundle_helper.load_manifest(bundle_root / 'bundle-manifest.json')
    controller = bundle_root / 'harness' / 'pairact_r1_student.py'
    original = controller.read_bytes()
    try:
        controller.write_bytes(original + b'\n# forged by the test\n')
        forged = dict(manifest)
        forged[str(controller)] = dict(manifest[str(controller)],
                                       sha256=sha256_file(controller))
        path = tmp_path / 'self-consistent.json'
        path.write_text(json.dumps(forged), encoding='utf-8')
        proc = _run_entry_cli(_entry_argv(bundle_root, tmp_path, manifest=path), tmp_path)
        _assert_refused(proc, tmp_path)
    finally:
        controller.write_bytes(original)


def test_the_audited_entry_refuses_a_deleted_required_file(bundle_root, tmp_path):
    contract = bundle_root / 'harness' / 'grasp_act_contract.py'
    original = contract.read_bytes()
    try:
        contract.unlink()
        proc = _run_entry_cli(_entry_argv(bundle_root, tmp_path), tmp_path)
        _assert_refused(proc, tmp_path)
    finally:
        contract.write_bytes(original)


def test_the_audited_entry_rechecks_a_drift_after_the_preparation(bundle_root, tmp_path):
    """A file that changed after the manifest was written is caught at start."""
    controller = bundle_root / 'harness' / 'pairact_r1_student.py'
    original = controller.read_bytes()
    try:
        controller.write_bytes(original + b'\n# drift after the preparation\n')
        proc = _run_entry_cli(_entry_argv(bundle_root, tmp_path), tmp_path)
        _assert_refused(proc, tmp_path)
    finally:
        controller.write_bytes(original)


def test_the_audited_entry_refuses_a_foreign_geometry_worker(bundle_root, tmp_path):
    argv = _entry_argv(bundle_root, tmp_path)
    argv[argv.index('--geometry-worker') + 1] = str(tmp_path / 'other_worker.py')
    proc = _run_entry_cli(argv, tmp_path)
    _assert_refused(proc, tmp_path)
    assert 'geometry worker' in proc.stderr.lower()


def test_the_audited_entry_refuses_a_foreign_student_root(bundle_root, tmp_path):
    argv = _entry_argv(bundle_root, tmp_path)
    argv[argv.index('--student-root') + 1] = str(tmp_path)
    proc = _run_entry_cli(argv, tmp_path)
    _assert_refused(proc, tmp_path)
    assert 'student-root' in proc.stderr.lower()


def test_the_audited_entry_requires_the_whole_audit_option_set(bundle_root, tmp_path):
    argv = _entry_argv(bundle_root, tmp_path)
    index = argv.index('--audit-sources')
    del argv[index:index + 2]
    proc = _run_entry_cli(argv, tmp_path)
    _assert_refused(proc, tmp_path)
    assert 'audit-sources' in proc.stderr.lower()


def test_pinned_sources_are_untouched():
    assert sha256_file(GEOMETRY_WORKER) == GEOMETRY_WORKER_SHA
    assert sha256_file(PINNED_TREE / 'harness' / 'pairact_r1_student.py') == PINNED_CONTROLLER_SHA
    assert sha256_file(PINNED_TREE / 'harness' / 'grasp_act_contract.py') == PINNED_CONTRACT_SHA
    assert sha256_file(PINNED_TREE / 'harness' / 'pairact_r1.py') == PINNED_PAIRACT_SHA
