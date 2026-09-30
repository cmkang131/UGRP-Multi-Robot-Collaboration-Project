"""Independent seal reproducibility checks; no blinded raw, physics or render.

Run from the review branch with pytest. A temporary shared clone of the exact
reviewed commit is removed at session teardown. Set V6H_REVIEW_COMMIT to a fixed
successor SHA for a new review; the strict xfails must then be reassessed.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SEAL = os.environ.get("V6H_REVIEW_COMMIT", "266118d2c2337bbf1cff507690da131c63e2db11")
EXECUTION = "4c6b439f3f7c9a147c901f8b260a1e214d4eb396"
CLASSIFIER = "1f0e4eb501a8f1b87077df943382fc1f0777dc69"
PREFIX = "experiments.2026-09-30-pair-v6h-carry."
BASE = "experiments/2026-09-30-pair-v6h-carry/"


def git(root, *args, input=None):
    return subprocess.check_output(["git", "-C", str(root), *args], input=input)


@pytest.fixture(scope="session")
def checkout():
    value = json.loads(git(ROOT, "show", SEAL + ":" + BASE + "prereg_v6h.json"))
    paths = set(value["pin_sets"]["analysis"]["files"]) | set(value["pin_sets"]["execution"]["files"])
    paths.update({BASE + "prereg_v6h.json", "experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json"})
    patterns = ["/" + p for p in sorted(paths)] + [
        "/tests/__init__.py", "/tests/test_classify_review_299.py",
        "/tests/test_v6h_blinded_run_manifest.py", "/tests/test_zone_pair_v6h_seal.py",
        "/tests/fixtures/v6h_blinded_run_metadata/",
    ]
    with tempfile.TemporaryDirectory(prefix="ugrp-seal-test-") as directory:
        root = Path(directory) / "source"
        subprocess.run(["git", "clone", "--shared", "--no-checkout", str(ROOT), str(root)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        git(root, "sparse-checkout", "init", "--no-cone")
        git(root, "sparse-checkout", "set", "--no-cone", "--stdin", input="\n".join(patterns).encode())
        git(root, "checkout", "--detach", SEAL)
        yield root, value


def run_json(checkout, body):
    root, _ = checkout
    prelude = f'''
import importlib, json, sys, socket
from pathlib import Path
sys.dont_write_bytecode = True
def no_blinded_access(event, args):
    if event in ('open', 'os.listdir', 'os.scandir') and args:
        if '/outputs/v6h1-confirm-' in str(args[0]):
            raise AssertionError('blinded raw is forbidden in reproducibility checks')
sys.addaudithook(no_blinded_access)
def forbidden(*args, **kwargs):
    raise AssertionError('physics, render and network are forbidden')
socket.socket.connect = socket.socket.connect_ex = forbidden
import mujoco
for name in ('mj_step', 'mj_step1', 'mj_step2', 'mj_forward', 'mj_inverse', 'Renderer'):
    setattr(mujoco, name, forbidden)
PREFIX = {PREFIX!r}
BASE = Path({BASE!r})
'''
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-B", "-c", prelude + body], cwd=root, env=env,
                            text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def test_all_execution_and_analysis_pins_match_git_objects(checkout):
    root, value = checkout
    requests = [(commit, path, receipt) for name, commit in (("execution", EXECUTION), ("analysis", SEAL))
                for path, receipt in value["pin_sets"][name]["files"].items()]
    data = git(root, "cat-file", "--batch", input="".join(f"{c}:{p}\n" for c, p, _ in requests).encode())
    stream = io.BytesIO(data)
    for commit, path, receipt in requests:
        oid, kind, size = stream.readline().split()
        assert kind == b"blob", (commit, path)
        raw = stream.read(int(size))
        assert stream.read(1) == b"\n"
        assert hashlib.sha256(raw).hexdigest() == receipt["sha256"], path
        actual_oid = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        assert actual_oid == oid.decode() == receipt["git_blob_sha"], path
    assert len(value["pin_sets"]["execution"]["files"]) == 274
    assert len(value["pin_sets"]["analysis"]["files"]) == 288


def test_worker_entry_reads_are_pinned_before_world_construction(checkout):
    seal_root, value = checkout
    cases = [{k: v for k, v in value["cases"][i].items() if k != "registration_run_id"} for i in (0, 71)]
    with tempfile.TemporaryDirectory(prefix="ugrp-seal-worker-test-") as directory:
        root = Path(directory) / "source"
        subprocess.run(["git", "clone", "--shared", "--no-checkout", str(ROOT), str(root)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        git(root, "sparse-checkout", "init", "--no-cone")
        git(root, "sparse-checkout", "set", "--no-cone", "--stdin",
            input=(seal_root / ".git/info/sparse-checkout").read_bytes())
        git(root, "checkout", "--detach", EXECUTION)
        result = run_json((root, value), '''
import os
root = Path.cwd().resolve()
reads = set()
def opened(event, args):
    if event != 'open' or not isinstance(args[0], str): return
    if isinstance(args[1], str) and any(c in args[1] for c in 'wax+'): return
    path = Path(args[0]).absolute()
    if not path.is_relative_to(root): return
    rel = path.relative_to(root).as_posix()
    if '/__pycache__/' in rel:
        rel = rel.split('/__pycache__/')[0] + '/' + path.name.split('.cpython-')[0] + '.py'
    reads.add(rel)
sys.addaudithook(opened)
class BeforeWorld(BaseException): pass
def stop_before_world(frame, event, arg):
    if (event == 'call' and frame.f_code.co_filename.endswith('/sim/multi_masterpi_production.py')
            and frame.f_code.co_name == '__init__'):
        raise BeforeWorld()
worker = importlib.import_module('scripts.run_pair_stage_probes')
''' + f"cases = json.loads({json.dumps(cases)!r})\n" + '''
stopped = 0
for i, case in enumerate(cases):
    sys.setprofile(stop_before_world)
    try:
        worker.run_case(case, root.parent / ('dry-' + str(i)))
    except BeforeWorld:
        stopped += 1
    finally:
        sys.setprofile(None)
# This literal dynamic skill is selected by run_case; importing it does not
# create a controller, world, image or observation.
importlib.import_module('harness.wrist_zone_skill_v9')
print(json.dumps({'stopped_before_world': stopped, 'repo_reads': sorted(reads)}))
''')
    assert result["stopped_before_world"] == 2
    assert set(result["repo_reads"]) <= value["pin_sets"]["execution"]["files"].keys()


def test_builder_literal_case_bytes_and_seed_selection(checkout):
    result = run_json(checkout, '''
b = importlib.import_module(PREFIX + 'build_prereg_v6h')
cases = b.build()['cases']
text = (BASE / 'analysis/seal/plan.json').read_text()
start = text.index('"cases": ') + len('"cases": ')
expected_cases, length = json.JSONDecoder().raw_decode(text[start:])
clean = [{k: v for k, v in c.items() if k != 'registration_run_id'} for c in cases]
actual = json.dumps(clean, indent=2, allow_nan=False).replace('\\n', '\\n  ')
assert actual == text[start:start + length]
assert [(c['cell'], c['seed']) for c in clean] == [(f'C{i:02d}', seed)
    for seed, n in ((941, 60), (943, 12)) for i in range(1, n + 1)]
import hashlib
print(json.dumps({'cases': len(cases), 'sha256': hashlib.sha256(actual.encode()).hexdigest()}))
''')
    assert result == {"cases": 72, "sha256": "f476c3d3103daa86fcab4553e9e2cfaf3b0abf500b71b6151554de7cbd2a4269"}


def test_classifier_and_disclosures_are_fixed(checkout):
    root, value = checkout
    for path in (BASE + "analysis/" + name for name in ("classify_placements.py", "recorder_v4c6b.py", "CLASSIFY_NOTES.md")):
        assert git(root, "show", SEAL + ":" + path) == git(root, "show", CLASSIFIER + ":" + path)
    actual = []
    for path, receipt in value["pin_sets"]["execution"]["files"].items():
        sha = value["pin_sets"]["analysis"]["files"][path]["sha256"]
        if sha != receipt["sha256"]:
            actual.append({"path": path, "execution_sha256": receipt["sha256"], "seal_sha256": sha})
    assert actual == value["notes"]["working_tree_differences"]
    assert len(actual) == 10  # six main changes and four registration/metadata changes


def test_sealed_state_rejects_redigested_tampering(checkout):
    result = run_json(checkout, f'''
import copy
s = importlib.import_module(PREFIX + 'analysis.seal_registration')
v = json.loads((BASE / 'prereg_v6h.json').read_bytes())
assert s.verify_seal(v, {SEAL!r})['analysis_files'] == 288
from scripts.zone_pair_authorization import digest, registration_payload
v['analysis_gate']['primary']['minimum_pass'] = 47
v['registration_sha256'] = digest(registration_payload(v))
try:
    s.verify_seal(v, {SEAL!r})
except ValueError as e:
    print(json.dumps({{'rejected': True, 'reason': str(e)}}))
else:
    print(json.dumps({{'rejected': False}}))
''')
    assert result["rejected"]


def test_primary_gate_host_enospc_and_missing_are_fail_closed(checkout):
    result = run_json(checkout, '''
t = importlib.import_module('tests.test_zone_pair_v6h_seal')
b = importlib.import_module('tests.test_v6h_blinded_run_manifest')
gate = importlib.import_module(PREFIX + 'analysis.apply_sealed_analysis')
verdicts = []
for n, missing in ((48, None), (47, None), (60, (1,941)), (60, (1,943))):
    report, cls = t.synthetic_report(n, missing)
    summary = gate.apply_gate(report, t.sealed(), cls)
    assert summary['n_placements'] == 60 and summary['n_cases'] == 72
    if missing == (1,941): assert summary['wilson95_primary_classified'] is None
    verdicts.append(summary['full_verdict'])
(row, result, trace), context = b.synthetic_context()
import copy
row.update(category='HOST_ERROR:ENOSPC', host_error='ENOSPC')
result.update(host_error={'classification':'HOST_ERROR', 'enospc':True}, row=copy.deepcopy(row))
out = b.cp.adjudicate_attempt(row, result, trace, recorder_context=context)
assert out['class'] is None and out['state'] == 'HOST_SAFE'
print(json.dumps(verdicts))
''')
    assert result == ["PASS_A_B_SAFETY", "FAIL_A_B_SAFETY", "NOT_EVALUABLE", "NOT_EVALUABLE"]


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="P1: acquisition raw-manifest hash is never checked before analysis")
def test_missing_acquisition_inventory_must_block_pass(checkout):
    result = run_json(checkout, '''
import tempfile
b = importlib.import_module('tests.test_v6h_blinded_run_manifest')
gate = importlib.import_module(PREFIX + 'analysis.apply_sealed_analysis')
with tempfile.TemporaryDirectory() as tmp:
    raw, manifest, _, plan = b.synthetic_run(Path(tmp), 72)
    report = b.analyse(raw, manifest)
    assert not (raw / 'raw_manifest.json').exists()
    summary = gate.apply_gate(report, plan, b.cp)
    print(json.dumps({'verdict': summary['full_verdict'], 'issues': summary['cohort_evidence_issues']}))
''')
    assert result["verdict"] != "PASS_A_B_SAFETY", result


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="P1: pre-analysis PF trace edits evade the pinned acquisition inventory")
def test_trace_edit_cannot_flip_failed_B_to_pass_with_same_pinned_inputs(checkout):
    result = run_json(checkout, '''
import tempfile
b = importlib.import_module('tests.test_v6h_blinded_run_manifest')
gate = importlib.import_module(PREFIX + 'analysis.apply_sealed_analysis')
with tempfile.TemporaryDirectory() as tmp:
    raw, manifest_path, manifest, plan = b.synthetic_run(Path(tmp), 72)
    paths = [b.cp.ca.dra.case_dir(raw, c['case_id'])/'eval_only/trace.jsonl'
             for c in plan['cases'] if c['seed'] == 941]
    def set_x(x):
        for path in paths:
            trace = [json.loads(line) for line in path.read_text().splitlines()]
            for sample in trace:
                for robot in b.cp.ROBOTS: sample['pf'][robot]['x'] = x
            path.write_text(''.join(json.dumps(s)+'\\n' for s in trace))
    set_x(1.)
    # Minimal synthetic acquisition inventory, not a guess at the blinded schema.
    # The current reader ignores this file regardless of its contents or absence.
    inventory = raw/'raw_manifest.json'
    b.base.write_json(inventory, {'files': {str(p.relative_to(raw)): b.cp.sha256(p) for p in paths}})
    manifest['raw']['raw_manifest_json_sha256'] = b.cp.sha256(inventory)
    b.base.write_json(manifest_path, manifest)
    pinned = b.cp.sha256(manifest_path)
    protected = [manifest_path, inventory, raw/'cases.jsonl', raw/'plan.json']
    protected += [b.cp.ca.dra.case_dir(raw,c['case_id'])/'commands.json' for c in plan['cases']]
    original = [b.cp.sha256(p) for p in protected]
    def verdict():
        report = b.cp.analyse('synthetic', raw, recorded_run_manifest=manifest_path,
                             recorded_run_manifest_sha256=pinned)
        summary = gate.apply_gate(report, plan, b.cp)
        return {'verdict': summary['full_verdict'], 'issues': summary['cohort_evidence_issues']}
    before = verdict()
    set_x(0.)
    after = verdict()
    assert [b.cp.sha256(p) for p in protected] == original
    print(json.dumps({'before': before, 'after': after}))
''')
    assert result["before"]["verdict"] == "FAIL_A_B_SAFETY", result
    assert result["after"]["verdict"] != "PASS_A_B_SAFETY", result
