"""Independent PR #299 audit: synthetic JSON only; no physics or model calls.

Copied from review de16cbc96becf19755f09197b9ef139609f00fe9.
R1/R2 are mandatory regression assertions (the review xfail markers are removed).
Original JSON builders are independent of the author's fixtures. V3 adds the
required safety summary/receipt and migrates incompatible accounting assertions;
see analysis/redesign_validation/README.md.
"""
import copy
import importlib.util
import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "review_299_classifier",
    ROOT / "experiments/2026-09-30-pair-v6h-carry/analysis/classify_placements.py",
)
cp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cp)
ROBOTS = ("r1", "r2")


def record(cell="C01", seed=941):
    """Teacher prefix, L0, release/regrasp, L1, and cleanup; fresh PF at both ends."""
    legs = []
    for k, start, end in ((0, .25, 1.01), (1, 2., 3.01)):
        legs.append({"leg": k, "recorded": True, "start_sim_s": start, "end_sim_s": end,
                     "lift_m": .05, "tilt_deg": 1., "end_error_m": .01, "leg_error_m": .01,
                     "jaws": {r: [True, True] for r in ROBOTS}})
    row = {"case_id": f"review299:{cell}:s{seed}", "stage": "chain", "cell": cell, "seed": seed,
           "stop_sim_s": 3.01, "category": "STAGE_BUDGET_EXHAUSTED",
           "final_states": {r: "wait_lower" for r in ROBOTS},
           "chain": {"legs": legs, "first_failure": None, "restaging_between_legs": False}}
    row["wall_contact"] = {"episodes": 0, "max_penetration_m": 0., "max_tilt_deg_stage": 1., "hard_limits": {"max_tilt_deg": 15., "max_penetration_m": .005}}
    trace = []
    for i in range(66):
        t = round(i * .05, 8)
        released = 1.25 <= t <= 1.5
        trace.append({"t": t, "tilt_deg": 1., "lift_m": 0. if released else .05,
                      "jaws": {r: [not released, not released] for r in ROBOTS},
                      "robots": {r: [0., 0., 0.] for r in ROBOTS},
                      "pf": {r: {"initialized": True, "t": t, "x": 0., "y": 0., "yaw": 0.,
                                 "cov": [[.01, 0., 0.], [0., .01, 0.], [0., 0., .01]]}
                             for r in ROBOTS}})
    result = {"failures": {r: None for r in ROBOTS}, "final_states": copy.deepcopy(row["final_states"]),
              "termination": {"outcome": "STUDY_LAYER_DONE", "sim_s": 3.25},
              "evaluation_coverage": {"start_sim_s": 0., "end_sim_s": 3.25, "trace_count": len(trace)},
              "wall_contact": {"episodes": [], "coverage": {
                  "start_sim_s": 0., "end_sim_s": 3.25, "sample_period_s": .05,
                  "max_gap_s": .05, "sample_count": len(trace)}}}
    record_receipt(row, result, trace)
    # A JSON round-trip ensures fixtures contain only actual JSON types.
    return json.loads(json.dumps([row, result, trace], allow_nan=False))


def record_receipt(row, result, trace):
    """Synthetic recorder fixture: commit evidence before loss/corruption tests.

    Independent canonical serializer; production never fills in absent receipts.
    """
    payload = {k: v for k, v in result.items() if k != 'evidence_sha256'}
    value = {'row': row, 'result': payload, 'trace': trace}
    result['evidence_sha256'] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, sort_keys=True, allow_nan=False) + "\n")


def write_record(raw, row, result, trace, identity):
    directory = cp.ca.dra.case_dir(raw, row["case_id"])
    (directory / "eval_only").mkdir(parents=True, exist_ok=True)
    stored = dict(result, row=row, execution_identity=identity)
    record_receipt(row, stored, trace)
    write_json(directory / "result.json", stored)
    (directory / "eval_only/trace.jsonl").write_text(
        "".join(json.dumps(s, allow_nan=False) + "\n" for s in trace))


def write_rows(raw, rows):
    (raw / "cases.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def sealed_cohort(tmp_path, retry_seed=None):
    """Pin 72 original cases and optional C01 retry BEFORE writing any outcomes."""
    raw = tmp_path / "raw"
    raw.mkdir()
    identity = {"source_sha": "a" * 40, "policy_id": "b-v6h1", "bundle_id": "v83",
                "source_files_sha256": {"synthetic/controller.py": "b" * 64}}
    placements, specs, entries = [], [], []
    for i in range(1, 61):
        p = {"name": f"C{i:02d}", "x": round(.92 + i * .002, 4), "y": .05,
             "yaw_deg": 0., "prior": "hR2_01", "sheet": "coarse"}
        placements.append(p)
        for seed in ((941, 943) if i <= 12 else (941,)):
            cid = f"review299:{p['name']}:s{seed}"
            spec = {"case_id": cid, "stage": "chain", "cell": p["name"], "seed": seed,
                    "beam_xyyaw": [p["x"], p["y"], 0.], "prior_id": p["prior"],
                    "prior": {r: {"mean": [0., 0., 0.]} for r in ROBOTS},
                    "coarse_order_sheet": {"beam_xyyaw": [round(p["x"], 1), 0., 0.]},
                    "source_sha": identity["source_sha"], "policy_id": identity["policy_id"],
                    "bundle_id": identity["bundle_id"], "chain_stop_leg": 1}
            specs.append(spec)
            attempts = []
            for case_id in ([cid, cid + ":retry1"] if i == 1 and seed == retry_seed else [cid]):
                d = cp.ca.dra.case_dir(raw, case_id)
                d.mkdir(parents=True)
                write_json(d / "case.json", dict(spec, case_id=case_id))
                attempts.append({"case_id": case_id, "case_sha256": cp.sha256(d / "case.json"),
                                 "replaces": None if case_id == cid else cid})
            entries.append({"placement": p["name"], "seed": seed, "attempts": attempts,
                            "placement_sha256": cp.value_hash(p), "prior_sha256": cp.value_hash(spec["prior"])})
    place_path, plan_path = tmp_path / "placements.json", tmp_path / "plan.json"
    write_json(place_path, placements)
    write_json(plan_path, {"execution_identity": identity, "cases": specs})
    seal = {"schema": "ugrp.v6h_confirmatory.v1", "state": "sealed", "primary_seed": 941, "secondary_seed": 943,
            "execution_identity": identity, "evaluation_protocol": cp.EVALUATION_PROTOCOL,
            "placements_file": place_path.name, "placements_sha256": cp.sha256(place_path),
            "plan_file": plan_path.name, "plan_sha256": cp.sha256(plan_path), "cases": entries}
    seal_path = tmp_path / "seal.json"
    write_json(seal_path, seal)
    pinned_hash = cp.sha256(seal_path)
    loaded = cp.load_sealed_manifest(seal_path, pinned_hash)
    write_json(raw / "manifest.json", {"state": "completed", "source_changed": False, "execution_identity": identity,
               "source": {"source_sha": identity["source_sha"], "execution_tree": {
                   "files": [{"path": k, "sha256": v} for k, v in identity["source_files_sha256"].items()]}}})
    rows = []
    for spec in specs:
        row, result, trace = record(spec["cell"], spec["seed"])
        rows.append(row)
        write_record(raw, row, result, trace, identity)
    write_rows(raw, rows)
    return raw, loaded, rows, identity


def analyse(raw, seal):
    return cp.analyse("review299", raw, sealed_manifest=seal)["summary"]


@pytest.mark.parametrize("passes", [0, 47, 48, 60])
def test_full_pipeline_keeps_all_attempted_placements_in_denominator(tmp_path, passes):
    raw, seal, rows, identity = sealed_cohort(tmp_path)
    for idx, row in enumerate(rows):
        if row["seed"] != 941 or int(row["cell"][1:]) <= passes:
            continue
        r, result, trace = record(row["cell"], row["seed"])
        # A real incomplete L1: complete safety trace and a controller failure.
        r["chain"]["legs"][1] = {"leg": 1, "recorded": False, "start_sim_s": 2., "end_sim_s": None}
        r["chain"]["first_failure"] = {"phase": "carry", "leg": 1, "sim_s": 3.01, "code": "COLLISION_GUARD"}
        r["final_states"] = result["final_states"] = {robot: "failed" for robot in ROBOTS}
        result["termination"]["outcome"] = "FAILED"
        rows[idx] = r
        write_record(raw, r, result, trace, identity)
    write_rows(raw, rows)
    s = analyse(raw, seal)
    assert (s["n_cases"], s["n_placements"], s["n_classified_primary"], s["pass_placements"]) == (72, 60, 60, passes)
    assert s["counts"]["FAIL"] == 60 - passes
    expected = "PASS_OBSERVED_CRITERION" if passes >= 48 else "FAIL_OBSERVED_CRITERION"
    assert s["criterion"]["verdict"] == expected
    if passes:
        assert s["full_verdict"] == ("PASS_A_B_SAFETY" if passes >= 48 else "FAIL_A_B_SAFETY")


@pytest.mark.parametrize("t", [0., .5, 1.25, 2.5, 3.2])
@pytest.mark.parametrize("kind", ["tilt", "penetration"])
def test_full_chain_hard_limit_beats_ordinary_failure(t, kind):
    row, result, trace = record()
    row["chain"]["legs"][1]["end_error_m"] = .11
    if kind == "tilt":
        trace[round(t / .05)]["tilt_deg"] = 15.001
    else:
        result["wall_contact"]["episodes"] = [{"t_first": t, "t_last": t, "max_pen_m": .005001}]
    out = cp.classify_case(row, result, trace, confirmatory=True)
    assert out["class"] == "FAIL_HARD_LIMIT"
    assert out["hard_limit_chain"]["violated"]


def test_exact_hard_limits_and_null_failures_pass():
    row, result, trace = record()
    trace[0]["tilt_deg"] = 15.
    result["wall_contact"]["episodes"] = [{"t_first": 0., "t_last": .1, "max_pen_m": .005}]
    assert cp.classify_case(row, result, trace, confirmatory=True)["class"] == "PASS_CONTACT_RECOVERED"


@pytest.mark.parametrize("phase", ["carry", "setdown", "regrasp"])
def test_actual_failure_with_good_endpoints_cannot_pass(phase):
    row, result, trace = record()
    result["failures"]["r1"] = {"phase": phase, "leg": 1, "code": "FAILED", "sim_s": 2.5}
    assert cp.classify_case(row, result, trace, confirmatory=True)["class"] == "FAIL"


@pytest.mark.parametrize("seed", [941, 943])
def test_auxiliary_and_primary_hard_limits_veto_cohort(tmp_path, seed):
    raw, seal, rows, identity = sealed_cohort(tmp_path)
    row, result, trace = record("C01", seed)
    trace[25]["tilt_deg"] = 16.
    write_record(raw, row, result, trace, identity)
    s = analyse(raw, seal)
    assert s["full_verdict"] == "FAIL_A_B_SAFETY"
    assert s["hard_limit_chain_cases"] == 1


@pytest.mark.parametrize("leg", [0, 1])
def test_endpoint_hard_limit_between_trace_samples_must_veto_cohort(tmp_path, leg):
    raw, seal, rows, identity = sealed_cohort(tmp_path)
    row, result, trace = record()
    row["chain"]["legs"][leg]["tilt_deg"] = 16.
    row["chain"]["first_failure"] = {"phase": "carry", "leg": leg, "code": "TILT",
        "source": "gt_criterion", "sim_s": row["chain"]["legs"][leg]["end_sim_s"]}
    for sample in trace:
        if abs(sample["t"] - row["chain"]["legs"][leg]["end_sim_s"]) < .051:
            sample["tilt_deg"] = 14.9
    # Endpoints 1.01/3.01 are not on the trace's 0.05-second sampling grid.
    assert row["chain"]["legs"][leg]["end_sim_s"] not in {s["t"] for s in trace}
    rows[0] = row
    write_record(raw, row, result, trace, identity)
    write_rows(raw, rows)
    s = analyse(raw, seal)
    assert s["full_verdict"] == "FAIL_A_B_SAFETY", s
    assert s["hard_limit_chain_cases"] == 1
    assert s["counts"]["FAIL_HARD_LIMIT"] == 1


def add_host_retry(raw, seal, rows, identity, seed=941, hard=None):
    row, result, trace = record("C01", seed)
    row["host_error"] = "ENOSPC during result cleanup"
    row["category"] = "HOST_ERROR:ENOSPC"
    result["termination"]["outcome"] = "HOST_ERROR"
    if hard == "tilt":
        trace[25]["tilt_deg"] = 16.
    elif hard == "penetration":
        result["wall_contact"]["episodes"] = [{"t_first": 1.25, "t_last": 1.3, "max_pen_m": .006}]
    index = next(i for i, r in enumerate(rows) if r["case_id"] == row["case_id"])
    rows[index] = row
    write_record(raw, row, result, trace, identity)
    retry, retry_result, retry_trace = record("C01", seed)
    entry = next(e for e in seal["cases"] if e["placement"] == "C01" and e["seed"] == seed)
    retry["case_id"] = entry["attempts"][1]["case_id"]
    rows.append(retry)
    write_record(raw, retry, retry_result, retry_trace, identity)
    write_rows(raw, rows)
    return row["case_id"]


@pytest.mark.parametrize("seed", [941, 943])
@pytest.mark.parametrize("hard", ["tilt", "penetration"])
def test_host_retry_must_not_erase_known_safety_violation(tmp_path, seed, hard):
    raw, seal, rows, identity = sealed_cohort(tmp_path, retry_seed=seed)
    original_id = add_host_retry(raw, seal, rows, identity, seed, hard)
    s = analyse(raw, seal)
    assert original_id in s["attempt_case_ids"] and original_id in s["selected_case_ids"]
    assert (s["n_cases"], s["n_placements"]) == (72, 60)  # count selected attempt only, retain safety from all
    assert s["full_verdict"] == "FAIL_A_B_SAFETY", s


def test_host_retry_without_hard_violation_counts_once(tmp_path):
    raw, seal, rows, identity = sealed_cohort(tmp_path, retry_seed=941)
    add_host_retry(raw, seal, rows, identity)
    s = analyse(raw, seal)
    assert (len(s["attempt_case_ids"]), len(s["selected_case_ids"]), s["n_cases"]) == (73, 72, 72)
    assert s["pass_placements"] == 60 and s["full_verdict"] == "PASS_A_B_SAFETY"


@pytest.mark.parametrize("seed", [941, 943])
def test_unreplaced_host_error_is_invalid_unclassified(tmp_path, seed):
    raw, seal, rows, identity = sealed_cohort(tmp_path)
    row = next(r for r in rows if r["cell"] == "C01" and r["seed"] == seed)
    row["category"] = "HOST_ERROR:worker_exit_-15"
    write_rows(raw, rows)
    s = analyse(raw, seal)
    assert s["full_verdict"] == "NOT_EVALUABLE"
    assert s["n_cases"] == 72 and s["n_placements"] == 60
    assert s["unclassified_cases"] == [row["case_id"]]
    assert s["counts"]["FAIL"] == 0
    assert row["case_id"] in s["invalid_cases"]


@pytest.mark.parametrize("mutation", ["missing_primary", "missing_auxiliary", "duplicate", "arbitrary_name"])
def test_sealed_cohort_rejects_wrong_inventory(tmp_path, mutation):
    raw, seal, rows, identity = sealed_cohort(tmp_path)
    if mutation == "missing_primary": rows.pop(0)
    if mutation == "missing_auxiliary": rows.pop(1)
    if mutation == "duplicate": rows.append(copy.deepcopy(rows[0]))
    if mutation == "arbitrary_name": rows[0]["cell"] = "P0"
    write_rows(raw, rows)
    s = analyse(raw, seal)
    assert s["full_verdict"] == "NOT_EVALUABLE"
    assert s["invalid_cases"] and s["n_placements"] == s["denominator"] == 60


# Follow-up coverage for the same R1/R2 fixes. Original independent builders and
# Original 33 review scenarios remain; v3 terminal/invalid accounting expectations
# and required fixture fields are explicitly migrated in redesign_validation/README.md.
@pytest.mark.parametrize("source", ["gt_at_entry", "gt_at_stop", "gt_at_end", "teacher",
                                    "leg_start", "leg_end", "done", "exits", "setdown", "maximum"])
def test_async_gt_safety_observations_are_not_lost(source):
    row, result, trace = record()
    gt = {"t": 1.01, "tilt_deg": 16.}
    if source.startswith("gt_at_"):
        result[source] = gt
    elif source == "teacher":
        result["teacher"] = {"gt_after_lift": gt}
    elif source in ("leg_start", "leg_end"):
        result["chain_raw"] = {"r1": {source: {"0": {"gt": gt}}}}
    elif source == "done":
        result["chain_raw"] = {"r2": {"done": {"gt": gt}}}
    elif source == "exits":
        result["exits"] = {"r1": {"gt": gt}}
    elif source == "setdown":
        row["chain"]["setdown"] = {"reached": False, "tilt_deg": 16.}
    else:
        result["max_tilt_deg"] = 16.
    out = cp.classify_case(row, result, trace, confirmatory=True)
    assert out["class"] == "FAIL_HARD_LIMIT"
    assert out["hard_limit_chain"]["max_tilt_deg"] == 16.


def test_endpoint_at_exact_hard_limit_can_still_fail_ordinary_leg_limit():
    row, result, trace = record()
    for leg in row["chain"]["legs"]:
        leg["tilt_deg"] = 15.
    out = cp.classify_case(row, result, trace, confirmatory=True)
    assert out["class"] == "FAIL"  # ordinary leg tilt <=10 degrees still applies
    assert out["hard_limit_chain"]["max_tilt_deg"] == 15.
    assert not out["hard_limit_chain"]["violated"]


@pytest.mark.parametrize("seed", [941, 943])
def test_replaced_host_evidence_is_hashed_and_counted_once(tmp_path, seed):
    raw, seal, rows, identity = sealed_cohort(tmp_path, retry_seed=seed)
    original_id = add_host_retry(raw, seal, rows, identity, seed, "tilt")
    report = cp.analyse("review299", raw, sealed_manifest=seal)
    s = report["summary"]
    attempt = next(a for a in report["attempts"] if a["case_id"] == original_id)
    assert attempt["selected"] and attempt["host_error"]
    assert attempt["hard_limit_chain"]["max_tilt_deg"] == 16.
    assert s["hard_limit_attempt_case_ids"] == [original_id]
    assert s["hard_limit_chain_cases"] == s["hard_limit_chain_placements_any_seed"] == 1
    assert (s["pass_placements"], s["cases_pass"], s["n_attempts"]) == (59 if seed == 941 else 60, 71, 73)
    assert s["full_verdict"] == "FAIL_A_B_SAFETY"
    assert next(p for p in report["placements"] if p["placement"] == "C01")["hard_limit_any_seed"]
    directory = cp.ca.dra.case_dir(raw, original_id)
    for name in ("result.json", "eval_only/trace.jsonl"):
        path = directory / name
        assert report["input_sha256"][str(path.relative_to(raw))] == cp.sha256(path)


@pytest.mark.parametrize("retained", ["row", "result", "trace", "truncated_trace", "malformed_metric"])
def test_partial_host_error_keeps_known_safety_violation(tmp_path, retained):
    raw, seal, rows, identity = sealed_cohort(tmp_path, retry_seed=941)
    original_id = add_host_retry(raw, seal, rows, identity, hard="tilt")
    directory = cp.ca.dra.case_dir(raw, original_id)
    result_path, trace_path = directory / "result.json", directory / "eval_only/trace.jsonl"
    if retained == "row":
        rows[0]["chain"]["legs"][0]["tilt_deg"] = 16.
        write_rows(raw, rows)
        result_path.unlink()
        trace_path.unlink()
    elif retained == "result":
        saved = json.loads(result_path.read_text())
        saved["gt_at_end"] = {"tilt_deg": 16., "t": 3.25}
        write_json(result_path, saved)
        trace_path.unlink()
    elif retained == "trace":
        result_path.unlink()
    elif retained == "truncated_trace":
        result_path.write_text('{"incomplete":')
        with trace_path.open("ab") as stream:
            stream.write(b'{"t":3.3,"tilt_deg":')
    else:
        saved = json.loads(result_path.read_text())
        saved["gt_at_end"] = {"tilt_deg": "invalid"}
        saved["chain_raw"] = {"r1": {"leg_start": ["invalid"]}}
        write_json(result_path, saved)
    report = cp.analyse("review299", raw, sealed_manifest=seal)
    s = report["summary"]
    assert s["hard_limit_attempt_case_ids"] == [original_id]
    assert s["full_verdict"] == "FAIL_A_B_SAFETY"
    assert s["pass_placements"] == 59
    if retained in ("truncated_trace", "malformed_metric"):
        assert s["safety_evidence_issues"][original_id]
        assert not s["criterion"]["evaluable"]


@pytest.mark.parametrize("hard", ["tilt", "penetration"])
def test_unreplaced_host_violation_dominates_incomplete_A_and_B(tmp_path, hard):
    raw, seal, rows, identity = sealed_cohort(tmp_path, retry_seed=941)
    original_id = add_host_retry(raw, seal, rows, identity, hard=hard)
    write_rows(raw, rows[:-1])  # predeclared retry was never executed
    s = analyse(raw, seal)
    assert s["unclassified_cases"] == []
    assert s["counts"]["FAIL"] == 0 and s["counts"]["FAIL_HARD_LIMIT"] == 1
    assert s["pass_placements"] == 59
    assert s["sigma_criterion_B"]["verdict"] == "PASS"  # complete recorded PF remains available
    assert s["hard_limit_chain_cases"] == 1
    assert s["full_verdict"] == "FAIL_A_B_SAFETY"


def test_retry_and_original_violations_count_as_two_attempts_one_placement(tmp_path):
    raw, seal, rows, identity = sealed_cohort(tmp_path, retry_seed=941)
    add_host_retry(raw, seal, rows, identity, hard="penetration")
    retry = rows[-1]
    _, result, trace = record()
    retry["chain"]["legs"][1]["tilt_deg"] = 16.
    write_record(raw, retry, result, trace, identity)
    write_rows(raw, rows)
    s = analyse(raw, seal)
    assert (s["n_cases"], s["n_placements"], s["pass_placements"]) == (72, 60, 59)
    assert (s["hard_limit_chain_cases"], s["hard_limit_chain_placements_any_seed"]) == (2, 1)
    assert s["counts"]["FAIL_HARD_LIMIT"] == 1
    assert s["full_verdict"] == "FAIL_A_B_SAFETY"


def test_unreadable_host_evidence_cannot_be_assumed_safe(tmp_path):
    raw, seal, rows, identity = sealed_cohort(tmp_path, retry_seed=941)
    original_id = add_host_retry(raw, seal, rows, identity)
    path = cp.ca.dra.case_dir(raw, original_id) / "result.json"
    path.write_text('{"incomplete":')
    report = cp.analyse("review299", raw, sealed_manifest=seal)
    s = report["summary"]
    assert s["safety_evidence_issues"][original_id]
    assert s["full_verdict"] == "NOT_EVALUABLE"
    assert report["input_sha256"][str(path.relative_to(raw))] == cp.sha256(path)


def test_absent_host_files_are_explicit_and_original_invalid_is_terminal(tmp_path):
    raw, seal, rows, identity = sealed_cohort(tmp_path, retry_seed=941)
    original_id = add_host_retry(raw, seal, rows, identity)
    directory = cp.ca.dra.case_dir(raw, original_id)
    for name in ("result.json", "eval_only/trace.jsonl"):
        (directory / name).unlink()
    report = cp.analyse("review299", raw, sealed_manifest=seal)
    assert len(report["missing_host_evidence"]) == 2
    assert report["summary"]["full_verdict"] == "NOT_EVALUABLE"
    assert report["summary"]["pass_placements"] == 59
    assert original_id in report["summary"]["invalid_cases"]


def test_changed_replaced_host_file_is_rejected(tmp_path, monkeypatch):
    raw, seal, rows, identity = sealed_cohort(tmp_path, retry_seed=941)
    original_id = add_host_retry(raw, seal, rows, identity)
    path = cp.ca.dra.case_dir(raw, original_id) / "eval_only/trace.jsonl"
    original_sha256 = cp.sha256
    reads = 0

    def changing_sha256(candidate):
        nonlocal reads
        if candidate == path:
            reads += 1
            if reads == 1:  # first sha256 call is the stable-input recheck; initial hash uses read bytes
                return "f" * 64
        return original_sha256(candidate)

    monkeypatch.setattr(cp, "sha256", changing_sha256)
    s = cp.analyse("review299", raw, sealed_manifest=seal)["summary"]
    assert s["full_verdict"] == "NOT_EVALUABLE"
    assert any("INPUT_CHANGED" in e for e in s["cohort_evidence_issues"])


def test_independent_review_regressions_are_in_offline_ci():
    from scripts import run_ci_tests
    assert "tests/test_classify_review_299.py" in run_ci_tests.collect_test_files(ROOT, run_ci_tests.TEST_PATTERNS)


def test_hard_endpoint_beats_failure_termination_instead_of_requiring_success_stop():
    row, result, trace = record()
    row["chain"]["legs"][1]["tilt_deg"] = 16.
    result["termination"]["outcome"] = "FAILED"
    row["final_states"] = result["final_states"] = {r: "failed" for r in ROBOTS}
    out = cp.classify_case(row, result, trace, confirmatory=True)
    assert out["class"] == "FAIL_HARD_LIMIT"
    assert out["completion_checks_skipped_for_hard_limit"]
