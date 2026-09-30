"""Independent #299 delta audit at 3a136bc8: public/synthetic evidence only.

Run in the archived candidate tree with repository Git read access. The strict
xfails distinguish ten PRE-FIX 58dc07e7 witnesses from five CURRENT 299g-R1
cross-stream chronology witnesses. --runxfail must expose assertion failures. No raw discovery,
physics, driver execution or writes outside pytest temporary directories.
"""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import types

import pytest


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = load("review_299g_public", "test_v6h_recorder_contract.py")
blinded = load("review_299g_synthetic", "test_v6h_blinded_run_manifest.py")
cp = contract.cp
ANALYSIS = "experiments/2026-09-30-pair-v6h-carry/analysis"
BASELINE = "58dc07e7607e86dd526bc0defe9374489f0ce931"


@pytest.fixture(scope="module")
def pre_fix():
    def historical_module(filename):
        path = contract.base.ROOT / ANALYSIS / filename
        source = subprocess.check_output(["git", "show", BASELINE + ":" + ANALYSIS + "/" + filename],
                                         cwd=contract.base.ROOT, text=True)
        module = types.ModuleType("review_299g_pre_fix_" + path.stem)
        module.__file__ = str(path)
        exec(compile(source, str(path) + ":58dc07e7", "exec"), module.__dict__)
        return module
    classifier = historical_module("classify_placements.py")
    classifier.rv = historical_module("recorder_v4c6b.py")
    return classifier


PRE_FIX = pytest.param("58dc07e7", marks=pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="Historical 299d P1 witness before d434fba9; current code must pass"))
WITNESSES = ["end_coordinates", "start_coordinates", "r1_start_0", "r1_start_1",
             "r2_start_0", "r2_start_1", "start_after_end", "negative_end", "stop_after_trace", "reader_distance"]


@pytest.mark.parametrize("version", ["candidate", PRE_FIX])
@pytest.mark.parametrize("damage", WITNESSES)
def test_ten_original_witnesses_and_their_specific_rejection(version, damage, pre_fix, tmp_path):
    classifier = cp if version == "candidate" else pre_fix
    if damage == "reader_distance":
        raw, seal, _ = contract.registered_fixture(tmp_path)
        assert classifier.analyse("clean", raw, sealed_manifest=seal)["summary"]["pass_placements"] == 1
        cid = seal["cases"][0]["attempts"][0]["case_id"]
        path = cp.ca.dra.case_dir(raw, cid) / "result.json"
        result = json.loads(path.read_text())
        for rid in cp.ROBOTS:
            result["chain_raw"][rid]["leg_end"]["1"]["gt"]["beam_xyz"][0] += 1.
        contract.base.write_json(path, result)
        out = classifier.analyse("contradictory", raw, sealed_manifest=seal)
        assert out["summary"]["pass_placements"] == 0
        attempt = next(a for a in out["attempts"] if a["case_id"] == cid)
        assert any("source/derived" in s and "contradiction" in s for s in attempt["hard_limit_chain"]["evidence_issues"])
        return
    data, context = contract.public_record()
    healthy = classifier.adjudicate_attempt(data["row"], data["result"], data["trace"], recorder_context=context)
    assert healthy["class"] == "PASS_CLEAN" and healthy["evidence_valid"]
    raw = data["result"]["chain_raw"]
    if damage in ("end_coordinates", "start_coordinates"):
        boundary = "leg_end" if damage.startswith("end") else "leg_start"
        for rid in cp.ROBOTS:
            raw[rid][boundary]["1"]["gt"]["beam_xyz"][0] += 1.
        expected = "source/derived"
    elif "_start_" in damage:
        rid, _, k = damage.split("_")
        del raw[rid]["leg_start"][k]
        expected = repr(k)  # KeyError from the required source start, not another validator.
    elif damage == "start_after_end":
        for rid in cp.ROBOTS:
            snap = raw[rid]["leg_start"]["1"]
            snap["sim_s"] = snap["gt"]["t"] = data["row"]["chain"]["legs"][1]["end_sim_s"] + 1.
        expected = "outside recorded window"
    elif damage == "negative_end":
        rid = min(cp.ROBOTS, key=lambda r: raw[r]["leg_end"]["1"]["sim_s"])
        snap = raw[rid]["leg_end"]["1"]
        snap["sim_s"] = snap["gt"]["t"] = -1.
        expected = "outside recorded window"
    else:
        data["result"]["gt_at_stop"]["t"] = data["trace"][-1]["t"] + 100.
        expected = "outside recorded window"
    out = classifier.adjudicate_attempt(data["row"], data["result"], data["trace"], recorder_context=context)
    assert out["state"] == "INVALID" and out["class"] is None, out
    assert any(expected in s for s in out["hard_limit_chain"]["evidence_issues"]), out


@pytest.mark.parametrize("damage", ["outside_id", "extra_alias", "row_seed", "case_swap", "commands_swap",
                                    "commands_bytes", "plan_bytes", "mid_read_commands", "missing_slot"])
def test_reader_admission_and_file_binding(tmp_path, monkeypatch, damage):
    raw, manifest_path, manifest, plan = blinded.synthetic_run(tmp_path, count=2)
    rows = [json.loads(s) for s in (raw / "cases.jsonl").read_text().splitlines()]
    first, second = plan["cases"][:2]
    directory = cp.ca.dra.case_dir(raw, first["case_id"])
    other = cp.ca.dra.case_dir(raw, second["case_id"])
    if damage in ("outside_id", "extra_alias"):
        outsider = copy.deepcopy(rows[0])
        outsider["case_id"] += "/not-planned"
        if damage == "outside_id":
            rows[0] = outsider
        else:
            rows.append(outsider)
    elif damage == "row_seed":
        rows[0]["seed"] = 999
        result = json.loads((directory / "result.json").read_text())
        result.update(seed=999, row=copy.deepcopy(rows[0]))
        blinded.base.write_json(directory / "result.json", result)
    elif damage == "case_swap":
        (directory / "case.json").write_bytes((other / "case.json").read_bytes())
    elif damage == "commands_swap":
        blinded.base.write_json(other / "commands.json", {"r1": ["other-case"], "r2": []})
        manifest["cases"][1]["commands_json_sha256"] = cp.sha256(other / "commands.json")
        (directory / "commands.json").write_bytes((other / "commands.json").read_bytes())
    elif damage == "commands_bytes":
        with (directory / "commands.json").open("a") as stream:
            stream.write("\n")
    elif damage == "plan_bytes":
        with (raw / "plan.json").open("a") as stream:
            stream.write("\n")
    elif damage == "missing_slot":
        rows.pop(0)
    elif damage == "mid_read_commands":
        read = cp.EvidenceReader.read
        def changing_read(reader, path, **kwargs):
            value = read(reader, path, **kwargs)
            if path == directory / "commands.json":
                path.write_bytes(path.read_bytes() + b"\n")
            return value
        monkeypatch.setattr(cp.EvidenceReader, "read", changing_read)
    blinded.base.write_rows(raw, rows)
    # Re-pin synthetic case-list changes, so membership/identity guards, rather
    # than a stale top-level hash, must detect them. Never edit real metadata.
    manifest["raw"]["cases_jsonl_sha256"] = cp.sha256(raw / "cases.jsonl")
    blinded.base.write_json(manifest_path, manifest)
    out = cp.analyse("review-synthetic", raw, recorded_run_manifest=manifest_path,
                     recorded_run_manifest_sha256=cp.sha256(manifest_path))
    first_out = next(a for a in out["attempts"] if a["case_id"] == first["case_id"])
    selected = next(c for p in out["placements"] for c in p["cases"] if c["case_id"] == first["case_id"])
    assert selected["class"] is None and selected["state"] == "INVALID", selected
    assert out["summary"]["denominator"] == 60 and out["summary"]["n_cases"] == 72
    assert out["summary"]["criterion"]["verdict"] == "NOT_EVALUABLE"
    if damage in ("outside_id", "extra_alias"):
        assert any("UNAUTHORIZED_ATTEMPT" in s for s in out["summary"]["cohort_evidence_issues"])
        assert not any(a["selected"] for a in out["attempts"] if a["case_id"] == outsider["case_id"])
        assert out["summary"]["cases_pass"] == 0
    elif damage.startswith("commands"):
        assert any("blinded commands hash mismatch" in s for s in first_out["hard_limit_chain"]["evidence_issues"])
    elif damage == "mid_read_commands":
        assert any("INPUT_CHANGED:" in s and s.endswith("commands.json") for s in out["summary"]["cohort_evidence_issues"])
        assert out["summary"]["cases_pass"] == 0
    elif damage == "missing_slot":
        assert out["summary"]["cases_pass"] == 1


def test_run_identity_uses_metadata_without_following_paths(tmp_path, monkeypatch):
    manifest, plan = blinded.metadata()
    before = cp.value_hash([manifest, plan])
    def forbid(*args, **kwargs):
        raise AssertionError("identity adapter must not read paths recorded in metadata")
    monkeypatch.setattr(Path, "read_bytes", forbid)
    monkeypatch.setattr(Path, "read_text", forbid)
    identity = cp.rv.blinded_run_identity(manifest, plan, blinded.PLAN_HASH)
    assert identity["source_sha"] == manifest["source"]["head_sha"]
    assert identity["driver_sha256"] == manifest["raw"]["driver_py_sha256"]
    assert identity["plan_sha256"] == manifest["raw"]["plan_json_sha256"]
    assert identity["registration_run_id"] == identity["bundle_id"] == "not_recorded"
    assert cp.value_hash([manifest, plan]) == before


@pytest.mark.parametrize("guard", ["commands", "plan_settings"])
def test_new_adapter_checks_are_load_bearing(monkeypatch, guard):
    (row, result, trace), context = blinded.synthetic_context()
    assert cp.adjudicate_attempt(row, result, trace, recorder_context=context)["class"] == "PASS_CLEAN"
    if guard == "commands":
        context["commands_sha256"] = "f" * 64
        old = 'if commands_sha256 != recorded["commands_json_sha256"]:'
    else:
        context["case"]["prior"]["r1"]["mean_xyyaw"][0] += .01
        old = 'if planned is None or {k: v for k, v in case.items() if k != "labels"} != planned:'
    assert cp.adjudicate_attempt(row, result, trace, recorder_context=context)["class"] is None
    path = Path(cp.rv.__file__)
    source = path.read_text()
    assert source.count(old) == 1
    mutant = types.ModuleType("review_299g_mutated_adapter")
    mutant.__file__ = str(path)
    exec(compile(source.replace(old, "if False:"), str(path) + ":mutant", "exec"), mutant.__dict__)
    monkeypatch.setattr(cp, "rv", mutant)
    out = cp.adjudicate_attempt(row, result, trace, recorder_context=context)
    assert out["class"] == "PASS_CLEAN" and out["evidence_valid"], out


CURRENT_R1 = pytest.mark.xfail(
    strict=True, raises=AssertionError,
    reason="299g-R1: pre-run entry/submit may follow recorded carry starts without rejection")


def reverse_cross_stream_time(data, damage):
    row, result = data["row"], data["result"]
    late = row["chain"]["legs"][1]["end_sim_s"] - .1
    assert late > row["chain"]["legs"][0]["start_sim_s"]
    if damage == "entry_after_carry_start":
        result["gt_at_entry"]["t"] = late
    elif damage == "teacher_and_entry_after_carry_start":
        result["teacher"]["gt_after_lift"]["t"] = result["gt_at_entry"]["t"] = late
    else:
        row["submit_t"] = result["submit_t"] = late
        result["row"] = copy.deepcopy(row)


@CURRENT_R1
@pytest.mark.parametrize("damage", ["entry_after_carry_start", "teacher_and_entry_after_carry_start",
                                    "submit_after_carry_start"])
def test_current_cross_stream_time_reversal_cannot_pass(damage):
    data, context = contract.public_record()
    out = contract.adjudicate(data, context)
    assert out["class"] == "PASS_CLEAN" and out["evidence_valid"]
    first_start = min(data["result"]["chain_raw"][r]["leg_start"]["0"]["sim_s"] for r in cp.ROBOTS)
    assert data["result"]["teacher"]["gt_after_lift"]["t"] <= data["result"]["gt_at_entry"]["t"]
    assert data["result"]["gt_at_entry"]["t"] < data["result"]["submit_t"] <= first_start
    reverse_cross_stream_time(data, damage)
    out = contract.adjudicate(data, context)
    assert out["state"] == "INVALID" and out["class"] is None, out


@CURRENT_R1
def test_current_registered_reader_cannot_count_late_entry(tmp_path):
    raw, seal, _ = contract.registered_fixture(tmp_path)
    assert cp.analyse("clean", raw, sealed_manifest=seal)["summary"]["pass_placements"] == 1
    cid = seal["cases"][0]["attempts"][0]["case_id"]
    path = cp.ca.dra.case_dir(raw, cid) / "result.json"
    result = json.loads(path.read_text())
    result["gt_at_entry"]["t"] = result["row"]["chain"]["legs"][1]["end_sim_s"] - .1
    contract.base.write_json(path, result)
    out = cp.analyse("late-entry", raw, sealed_manifest=seal)
    assert out["summary"]["pass_placements"] == 0, out["summary"]


@CURRENT_R1
def test_current_run_manifest_reader_cannot_count_late_entry(tmp_path):
    raw, path, _, plan = blinded.synthetic_run(tmp_path)
    assert blinded.analyse(raw, path)["summary"]["pass_placements"] == 1
    directory = cp.ca.dra.case_dir(raw, plan["cases"][0]["case_id"])
    result_path = directory / "result.json"
    result = json.loads(result_path.read_text())
    result["gt_at_entry"]["t"] = result["row"]["chain"]["legs"][1]["end_sim_s"] - .1
    blinded.base.write_json(result_path, result)
    out = blinded.analyse(raw, path)
    assert out["summary"]["cohort_evidence_issues"] == []  # All plan/command pins remain valid.
    assert out["summary"]["pass_placements"] == 0, out["summary"]
