"""Independent PR292 delta audit; run in the disposable 9e13c76b Git archive.

Set V6H_FIX_ARCHIVE=1 and use the two no-physics/blinding pytest plugins.
Only RAW/OUT globals are redirected in the exact committed generator frame.
No recorded raw or real inventory is read. Mutants are strict AssertionError
xfails; --runxfail must yield precisely the two final integrity assertions.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("V6H_FIX_ARCHIVE") != "1",
                               reason="requires disposable reviewed archive")
ROOT = Path(__file__).resolve().parents[1]
BASE = "experiments/2026-09-30-pair-v6h-carry/"
PREFIX = "experiments.2026-09-30-pair-v6h-carry."
OLD = "266118d2c2337bbf1cff507690da131c63e2db11"
HEAD = "9e13c76b0ead36ace257e05cab7cb5e60d42df72"
SEAL = "5be4330eca9b23d2cbde3657dcbb215ee1923b25"
EXEC = "4c6b439f3f7c9a147c901f8b260a1e214d4eb396"
META = "0b77ae4b9a3500de29adad74c7ecd0439ccdf545"
META_DIR = "experiments/2026-10-01-v6h1-confirm-blinded/"
GENERATOR_SHA = "cf7c618c1bcc43c8e737690c6e6b186a217aa5843f7431f439bec4e2ff6452c4"


def git(*args, input=None):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], input=input)


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture(scope="module")
def modules():
    assert git("rev-parse", "HEAD").decode().strip() == HEAD
    gate = importlib.import_module(PREFIX + "analysis.apply_sealed_analysis")
    base = importlib.import_module("tests.test_v6h_blinded_run_manifest")
    return gate, base


def exact_generator(raw, output):
    source = git("show", META + ":" + META_DIR + "make_acquisition_inventory.py")
    assert sha(source) == GENERATOR_SHA
    code = compile(source, "committed-make_acquisition_inventory.py", "exec")
    tree = ast.parse(source)
    first_io = next(node.lineno for node in tree.body if isinstance(node, ast.Expr)
                    and isinstance(node.value, ast.Call)
                    and ast.unparse(node.value.func) == "os.makedirs")
    assert all(isinstance(node, (ast.Expr, ast.Import, ast.Assign))
               for node in tree.body if node.lineno < first_io)
    redirected = []
    def redirect(frame, event, arg):
        if frame.f_code is code and event == "line" and frame.f_lineno == first_io:
            # Both original assignments have run; the first I/O has not.
            frame.f_globals.update(RAW=str(raw), OUT=str(output))
            redirected.append(True)
        return redirect
    def forbid_recorded_path(event, values):
        if event in ("open", "os.mkdir", "os.listdir", "os.scandir", "os.remove", "os.chmod"):
            if any("/outputs/v6h1-confirm-" in str(v) for v in values):
                raise RuntimeError("generator attempted a recorded path")
    sys.addaudithook(forbid_recorded_path)
    old_trace = sys.gettrace()
    stream = io.StringIO()
    try:
        sys.settrace(redirect)
        with contextlib.redirect_stdout(stream):
            exec(code, {"__name__": "__main__"})
    finally:
        sys.settrace(old_trace)
    assert redirected == [True]
    inventory = output / "acquisition_inventory.json"
    doc = json.loads(inventory.read_bytes())
    receipt = json.loads(stream.getvalue())
    assert receipt["inventory_sha256"] == sha(inventory.read_bytes())
    assert receipt["file_count"] == doc["file_count"] == len(doc["files"])
    assert doc["total_bytes"] == sum(f["bytes"] for f in doc["files"])
    pin = {k: doc[k] for k in ("schema", "raw", "file_count", "total_bytes")}
    pin["inventory_sha256"] = receipt["inventory_sha256"]
    return inventory, pin


def setup_raw(tmp_path, modules, bad_trace=False):
    gate, base = modules
    raw, manifest_path, manifest, plan = base.synthetic_run(tmp_path, 72)
    paths = [gate.classifier.ca.dra.case_dir(raw, c["case_id"]) / "eval_only/trace.jsonl"
             for c in plan["cases"] if c["seed"] == 941]
    if bad_trace:
        set_x(paths, 1., gate)
    (raw / "manifest.json").write_text(json.dumps({"end_unix": time.time(), "status": "synthetic"}))
    inventory, pin = exact_generator(raw, tmp_path / "synthetic-inventory")
    manifest["raw"].update(path=str(raw), file_count=pin["file_count"], total_bytes=pin["total_bytes"],
                           raw_manifest_json_sha256=sha((raw / "manifest.json").read_bytes()))
    base.base.write_json(manifest_path, manifest)
    return (raw, plan, manifest_path, sha(manifest_path.read_bytes()), inventory, pin), paths


def set_x(paths, x, gate):
    for path in paths:
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            for robot in gate.classifier.ROBOTS:
                row["pf"][robot]["x"] = x
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_git_pins_preservation_cases_and_metadata(modules):
    value = json.loads(git("show", SEAL + ":" + BASE + "analysis/seal_v2/prereg_v6h.json"))
    assert value == json.loads((ROOT / BASE / "analysis/seal_v2/prereg_v6h.json").read_bytes())
    old = json.loads(git("show", OLD + ":" + BASE + "prereg_v6h.json"))
    assert value["pin_sets"]["execution"] == old["pin_sets"]["execution"]
    paths = git("ls-tree", "-r", "--name-only", OLD, "--", BASE + "prereg_v6h.json",
                BASE + "analysis/seal/").decode().splitlines()
    assert len(paths) == 19
    for path in paths:
        assert git("show", OLD + ":" + path) == git("show", HEAD + ":" + path)
    requests = [(commit, p, r) for name, commit in (("execution", EXEC), ("analysis", SEAL))
                for p, r in value["pin_sets"][name]["files"].items()]
    stream = io.BytesIO(git("cat-file", "--batch", input="".join(f"{c}:{p}\n" for c,p,_ in requests).encode()))
    for commit, path, receipt in requests:
        oid, kind, size = stream.readline().split()
        assert kind == b"blob"
        data = stream.read(int(size))
        assert stream.read(1) == b"\n"
        assert sha(data) == receipt["sha256"], (commit, path)
        assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == oid.decode() == receipt["git_blob_sha"]
    builder = importlib.import_module(PREFIX + "build_prereg_v6h")
    seal = importlib.import_module(PREFIX + "analysis.seal_registration")
    assert seal.verify_cases(builder.build()["cases"]) == value["case_equality"]
    assert seal.verify_seal(value, SEAL)["analysis_commit"] == SEAL
    pin = value["acquisition_inventory"]
    assert (pin["inventory_sha256"], pin["file_count"], pin["total_bytes"]) == (
        "d7ceca9824d4098956c7bfc5cbd7298ee5b0cfa5dacdb12586d07c2ee07ec03f", 104415, 1916385247)
    recorded = json.loads((ROOT / BASE / "analysis/seal/RUN_MANIFEST.json").read_bytes())
    assert recorded["raw"]["raw_manifest_json_sha256"] == "07f623b7b30374da25cd0a8d2df62a70bbfdcae47b80279be6e310d7def27950"
    for name, digest in pin["metadata_sha256"].items():
        assert sha(git("show", META + ":" + META_DIR + name)) == digest


def test_exact_generator_and_all_raw_opens(modules, tmp_path, monkeypatch):
    gate, _ = modules
    args, _ = setup_raw(tmp_path, modules)
    raw = args[0]
    state = {"active": True, "reads": [], "bypass": []}
    def audit(event, values):
        if event != "open" or not state["active"] or not isinstance(values[0], str):
            return
        path = Path(values[0])
        if not path.is_relative_to(raw):
            return
        mode = values[1]
        if isinstance(mode, str) and any(x in mode for x in "wax+"):
            pytest.fail("analysis wrote raw")
        frame = sys._getframe(1)
        routes = []
        while frame:
            if isinstance(frame.f_locals.get("self"), gate.AcquisitionReader):
                routes.append(frame.f_code.co_name)
            frame = frame.f_back
        state["reads"].append(str(path.relative_to(raw)))
        if not ({"read", "verify"} & set(routes)):
            state["bypass"].append(str(path))
    sys.addaudithook(audit)
    try:
        report, result = gate.analyse_acquisition(*args)
    finally:
        state["active"] = False
    assert result["status"] == "ANALYSED" and result["summary"]["full_verdict"] == "PASS_A_B_SAFETY"
    expected = {f["path"] for f in json.loads(args[4].read_bytes())["files"]}
    assert len(expected) == 291 and set(state["reads"]) == expected
    assert not state["bypass"]
    assert expected <= report["input_sha256"].keys()
    assert set(state["reads"]) <= report["input_sha256"].keys()


def remove_check(gate, monkeypatch):
    class NoAcquisitionCheck(gate.classifier.EvidenceReader):
        def __init__(self, raw, manifest, digest):
            super().__init__(raw)
            self.manifest = manifest
        def load_inventory(self, *args):
            pass
    monkeypatch.setattr(gate, "AcquisitionReader", NoAcquisitionCheck)


MUTATION = pytest.param(True, marks=pytest.mark.xfail(strict=True, raises=AssertionError,
    reason="removing acquisition admission must restore the P1 counterexample"), id="remove-check")


@pytest.mark.parametrize("mutant", [pytest.param(False, id="fixed"), MUTATION])
@pytest.mark.parametrize("damage", ["missing_inventory", "trace_edit"])
def test_original_counterexamples_exact_generator(modules, tmp_path, monkeypatch, damage, mutant):
    gate, _ = modules
    args, traces = setup_raw(tmp_path, modules, bad_trace=damage == "trace_edit")
    report, before = gate.analyse_acquisition(*args)
    expected = "FAIL_A_B_SAFETY" if damage == "trace_edit" else "PASS_A_B_SAFETY"
    if report is None or before.get("summary", {}).get("full_verdict") != expected:
        pytest.fail("healthy generator fixture did not reach the expected initial gate")
    protected = [args[2], args[4], args[0]/"manifest.json", args[0]/"plan.json", args[0]/"cases.jsonl"]
    protected += [gate.classifier.ca.dra.case_dir(args[0], c["case_id"])/"commands.json" for c in args[1]["cases"]]
    hashes = [sha(p.read_bytes()) for p in protected]
    if damage == "missing_inventory":
        args[4].unlink()
        reason = "MISSING_EVIDENCE:"
    else:
        set_x(traces, 0., gate)
        if hashes != [sha(p.read_bytes()) for p in protected]:
            pytest.fail("trace mutation changed a protected input")
        reason = "ACQUISITION_HASH_MISMATCH:" + str(traces[0].relative_to(args[0]))
    if mutant:
        remove_check(gate, monkeypatch)
    report, after = gate.analyse_acquisition(*args)
    if mutant and (report is None or after.get("summary", {}).get("full_verdict") != "PASS_A_B_SAFETY"):
        pytest.fail("mutant did not reproduce the original false pass")
    assert report is None, "removed acquisition check emitted PASS_A_B_SAFETY"
    assert after["status"] == "INVALID" and after["analysis_status"] == "NOT_ANALYSED"
    assert after["reason"].startswith(reason)
    assert "summary" not in after and "full_verdict" not in after
