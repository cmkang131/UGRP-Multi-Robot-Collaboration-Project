"""Only committed outcome-free metadata and synthetic worker records.

Never follow paths inside the metadata. Blinded raw is not a test dependency.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("blinded_run_builders", Path(__file__).with_name("test_classify_review_299.py"))
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)
cp = base.cp
FIXTURES = Path(__file__).parent / "fixtures/v6h_blinded_run_metadata"
MANIFEST_HASH = "99723de36d20a55f348ea5b25ca203cf1db910dd9a620d3a8c4a17f27407f210"
PLAN_HASH = "d627f9cda827d07bab5b86c04f9e45ffceb474e97a8dda566c4956372d5fb026"


def metadata():
    return [json.loads((FIXTURES / name).read_bytes()) for name in ("RUN_MANIFEST.json", "plan.json")]


def synthetic_record(case):
    """Fresh perfect geometry/timelines, no public or blinded outcome copied."""
    row, result, trace = base.record(case["cell"], case["seed"])
    row["case_id"] = case["case_id"]
    result.pop("evidence_sha256")
    result.pop("evaluation_coverage")
    result["wall_contact"].pop("coverage")
    result["wall_contact"]["steps"] = {}
    result["chain_raw"] = {r: {"timeline": [], "leg_start": {}, "leg_end": {}} for r in cp.ROBOTS}

    def gt(t, xy):
        return {"t": t, "beam_xyz": [*xy, .05], "lift_m": .05, "tilt_deg": 1.,
                "jaws": {r: [True, True] for r in cp.ROBOTS}}

    for leg in row["chain"]["legs"]:
        k = leg["leg"]
        p0, p1 = case["route"][k:k + 2]
        length = p1[0] - p0[0]  # Both synthetic measured legs are eastbound.
        leg.update(planned_length_m=length, travel_m=length, along_error_m=0., cross_track_m=0.,
                   end_error_m=0., leg_error_m=0., step_error_m=0.)
        for r in cp.ROBOTS:
            for boundary, t, xy, state in (("leg_start", leg["start_sim_s"], p0, "wait_carry"),
                                           ("leg_end", leg["end_sim_s"], p1, "wait_lower")):
                result["chain_raw"][r][boundary][str(k)] = {"sim_s": t, "gt": gt(t, xy)}
                result["chain_raw"][r]["timeline"].append([t, k, state])
    result.update({k: row[k] for k in ("case_id", "cell", "seed", "stage")})
    result.update(row=copy.deepcopy(row), teacher={"gt_after_lift": gt(0., case["route"][0])},
                  gt_at_entry=gt(0., case["route"][0]), gt_at_stop=gt(3.01, case["route"][2]),
                  gt_at_end=gt(3.25, case["route"][2]))
    return row, result, trace


def synthetic_context():
    manifest, plan = metadata()
    case = copy.deepcopy(plan["cases"][0])
    command_hash = hashlib.sha256(b'{"r1": [], "r2": []}\n').hexdigest()
    manifest["cases"][0]["commands_json_sha256"] = command_hash
    context = {"manifest": manifest, "case": case, "run_plan": plan,
               "plan_sha256": PLAN_HASH, "commands_sha256": command_hash}
    return synthetic_record(case), context


def synthetic_run(tmp_path, count=1):
    manifest, plan = metadata()
    raw = tmp_path / "synthetic"
    raw.mkdir()
    (raw / "plan.json").write_bytes((FIXTURES / "plan.json").read_bytes())
    rows = []
    for case in plan["cases"][:count]:
        row, result, trace = synthetic_record(case)
        directory = cp.ca.dra.case_dir(raw, case["case_id"])
        (directory / "eval_only").mkdir(parents=True)
        base.write_json(directory / "case.json", {**case, "labels": plan["labels"]})
        base.write_json(directory / "result.json", result)
        base.write_json(directory / "commands.json", {r: [] for r in cp.ROBOTS})
        (directory / "eval_only/trace.jsonl").write_text("".join(json.dumps(s) + "\n" for s in trace))
        next(c for c in manifest["cases"] if c["case_id"] == case["case_id"])["commands_json_sha256"] = cp.sha256(directory / "commands.json")
        rows.append(row)
    base.write_rows(raw, rows)
    # Only synthetic evidence digests are substituted. Provenance/plan and all
    # 72 case identities/settings remain the committed outcome-free metadata.
    manifest["raw"]["cases_jsonl_sha256"] = cp.sha256(raw / "cases.jsonl")
    path = tmp_path / "SYNTHETIC_RUN_MANIFEST.json"
    base.write_json(path, manifest)
    return raw, path, manifest, plan


def analyse(raw, path, **kwargs):
    return cp.analyse("synthetic", raw, recorded_run_manifest=path,
                      recorded_run_manifest_sha256=cp.sha256(path), **kwargs)


def test_committed_metadata_bytes_and_worker_identity():
    assert cp.sha256(FIXTURES / "RUN_MANIFEST.json") == MANIFEST_HASH
    assert cp.sha256(FIXTURES / "plan.json") == PLAN_HASH
    manifest, plan = metadata()
    identity = cp.rv.blinded_run_identity(manifest, plan, PLAN_HASH)
    assert identity == {"source_sha": "4c6b439f3f7c9a147c901f8b260a1e214d4eb396",
                        "driver_sha256": "7a35229e431409904dffec27b5e9572f290cd900f0595c8e0babc5ef92cf3e56",
                        "plan_sha256": PLAN_HASH, "policy_id": "b-v6h1",
                        "bundle_id": "not_recorded", "registration_run_id": "not_recorded"}
    assert len(plan["cases"]) == 72
    assert all("registration_run_id" not in c for c in plan["cases"])


@pytest.mark.parametrize("damage", ["schema", "source", "changed", "dirty", "end_dirty", "driver", "plan_hash",
    "plan_source", "admission", "run_tracking", "plan_tracking", "incomplete", "retry", "case_missing",
    "case_duplicate", "case_seed", "case_path", "commands_path", "commands_hash", "case_status", "plan_duplicate"])
def test_metadata_contradictions_reject(damage):
    manifest, plan = metadata()
    digest = PLAN_HASH
    if damage == "schema": manifest["schema"] = "v6h1-confirm-blinded.run.v1"
    elif damage == "source": manifest["source"]["head_sha"] = "f" * 40
    elif damage == "changed": manifest["source"]["source_changed_during_run"] = True
    elif damage == "dirty": manifest["source"]["git_status_porcelain_at_start"] = " M driver.py"
    elif damage == "end_dirty": manifest["source"]["git_status_porcelain_at_end_clean"] = False
    elif damage == "driver": manifest["raw"]["driver_py_sha256"] = "f" * 64
    elif damage == "plan_hash": digest = "f" * 64
    elif damage == "plan_source": plan["source_sha"] = "f" * 40
    elif damage == "admission": manifest["admission"] = "registered"
    elif damage == "run_tracking": manifest["run"]["contact_track"] = False
    elif damage == "plan_tracking": plan["pf_track"] = False
    elif damage == "incomplete": manifest["completion"]["finished"] = 71
    elif damage == "retry": manifest["reruns"] = 1
    elif damage == "case_missing": manifest["cases"].pop()
    elif damage == "case_duplicate": manifest["cases"][-1] = copy.deepcopy(manifest["cases"][0])
    elif damage == "case_seed": manifest["cases"][0]["seed"] = 943
    elif damage == "case_path": manifest["cases"][0]["case_dir"] = "../outside"
    elif damage == "commands_path": manifest["cases"][0]["commands_json"] = "../outside/commands.json"
    elif damage == "commands_hash": manifest["cases"][0]["commands_json_sha256"] = None
    elif damage == "case_status": manifest["cases"][0]["status"] = "running"
    else: plan["cases"][-1] = copy.deepcopy(plan["cases"][0])
    with pytest.raises(ValueError):
        cp.rv.blinded_run_identity(manifest, plan, digest)


def test_synthetic_record_uses_same_strict_contract_and_retains_unsealed_admission():
    (row, result, trace), context = synthetic_context()
    out = cp.adjudicate_attempt(row, result, trace, recorder_context=context)
    assert out["class"] == "PASS_CLEAN" and out["confirmatory_evidence_checked"], out
    contract = out["recorder_contract"]
    assert contract["admission"] == "unsealed_stage_probe"
    assert contract["identity"]["commands_sha256"] == context["commands_sha256"]
    assert contract["wall_contact"]["sample_count"] == contract["record_time_evidence_sha256"] == "not_recorded"


@pytest.mark.parametrize("damage", ["start", "distance", "time", "handover", "pf", "trace", "coverage", "receipt",
                                    "row_identity", "case_settings", "commands", "registration"])
def test_custom_driver_does_not_relax_per_case_evidence(damage):
    (row, result, trace), context = synthetic_context()
    if damage == "start": del result["chain_raw"]["r1"]["leg_start"]["0"]
    elif damage == "distance": result["chain_raw"]["r1"]["leg_end"]["1"]["gt"]["beam_xyz"][0] += 1.
    elif damage == "time": result["chain_raw"]["r1"]["leg_start"]["1"]["sim_s"] = 4.
    elif damage == "handover":
        for sample in trace:
            sample["jaws"] = {r: [True, True] for r in cp.ROBOTS}
    elif damage == "pf":
        for sample in trace:
            if sample["t"] >= 2.7:
                sample["pf"]["r1"]["cov"] = None
    elif damage == "trace": trace[:] = trace[:-10]
    elif damage == "coverage": result["evaluation_coverage"] = {"start_sim_s": 0., "end_sim_s": 100., "trace_count": 66}
    elif damage == "receipt": result["evidence_sha256"] = "f" * 64
    elif damage == "row_identity": result["row"]["seed"] = 943
    elif damage == "case_settings": context["case"]["prior"]["r1"]["mean_xyyaw"][0] += .01
    elif damage == "commands": context["commands_sha256"] = "f" * 64
    else: context["case"]["registration_run_id"] = "invented"
    out = cp.adjudicate_attempt(row, result, trace, recorder_context=context)
    if damage == "handover":
        assert out["class"] == "FAIL" and out["evidence_valid"], out
    else:
        assert out["class"] not in cp.PASS and not out["evidence_valid"], out


def test_host_unclassified_and_hard_limit_precedence_are_unchanged():
    (row, result, trace), context = synthetic_context()
    row.update(category="HOST_ERROR:ENOSPC", host_error="ENOSPC")
    result.update(host_error={"classification": "HOST_ERROR", "enospc": True}, row=copy.deepcopy(row))
    out = cp.adjudicate_attempt(row, result, trace, recorder_context=context)
    assert out["state"] == "HOST_SAFE" and out["class"] is None and out["evidence_valid"], out
    trace[0]["tilt_deg"] = 16.
    context["commands_sha256"] = "f" * 64
    out = cp.adjudicate_attempt(row, result, trace, recorder_context=context)
    assert out["class"] == "FAIL_HARD_LIMIT" and not out["evidence_valid"], out


def test_missing_records_do_not_shrink_72_slots_or_60_placements(tmp_path):
    raw, path, _, _ = synthetic_run(tmp_path)
    out = analyse(raw, path)
    summary = out["summary"]
    assert summary["cohort_evidence_issues"] == []
    assert summary["n_cases"] == 72 and summary["denominator"] == 60
    assert summary["cases_pass"] == summary["pass_placements"] == 1, out["attempts"][0]
    assert len(summary["unclassified_cases"]) == 71
    assert summary["criterion"]["mode"] == "unsealed_stage_probe"
    assert summary["criterion"]["verdict"] == "NOT_EVALUABLE"
    assert out["source_sha"] == cp.rv.BLINDED_SOURCE_SHA
    assert "manifest.json" not in out["input_sha256"]  # no speculative raw-manifest schema
    assert any(p.endswith("commands.json") for p in out["input_sha256"])


@pytest.mark.parametrize("damage", ["plan_bytes", "case_settings", "commands_bytes", "commands_missing", "cases_bytes", "manifest_pin"])
def test_file_hash_and_case_identity_link_is_checked(tmp_path, damage):
    raw, path, _, plan = synthetic_run(tmp_path)
    directory = cp.ca.dra.case_dir(raw, plan["cases"][0]["case_id"])
    if damage == "manifest_pin":
        with pytest.raises(cp.EvidenceError, match="pinned hash"):
            cp.analyse("synthetic", raw, recorded_run_manifest=path, recorded_run_manifest_sha256="f" * 64)
        return
    if damage == "case_settings":
        case = json.loads((directory / "case.json").read_text())
        case["contact_track"] = False
        base.write_json(directory / "case.json", case)
    elif damage == "commands_missing": (directory / "commands.json").unlink()
    else:
        target = {"plan_bytes": raw / "plan.json", "commands_bytes": directory / "commands.json",
                  "cases_bytes": raw / "cases.jsonl"}[damage]
        target.write_bytes(target.read_bytes() + b"\n")
    out = analyse(raw, path)
    assert out["summary"]["cases_pass"] == 0
    assert out["summary"]["denominator"] == 60
    assert out["attempts"][0]["state"] == "INVALID", out["attempts"][0]


def test_cli_complete_synthetic_run_and_no_retrospective_registration(tmp_path):
    raw, path, _, _ = synthetic_run(tmp_path, count=72)
    dest = tmp_path / "classified"
    assert cp.main(["--output", str(dest), "--recorded-run-manifest", str(path),
                    "--recorded-run-manifest-sha256", cp.sha256(path), "synthetic=" + str(raw)]) == 0
    out = json.loads((dest / "synthetic.json").read_text())
    assert out["summary"]["cases_pass"] == 72 and out["summary"]["pass_placements"] == 60
    assert out["summary"]["criterion"]["verdict"] == "NOT_EVALUABLE"
    with pytest.raises(cp.EvidenceError, match="retrospectively"):
        analyse(raw, path, sealed_manifest={"state": "sealed"})
    with pytest.raises(cp.EvidenceError, match="both"):
        cp.analyse("synthetic", raw, recorded_run_manifest=path)


def test_new_contract_is_in_offline_ci():
    from scripts import run_ci_tests
    assert "tests/test_v6h_blinded_run_manifest.py" in run_ci_tests.collect_test_files(base.ROOT, run_ci_tests.TEST_PATTERNS)
