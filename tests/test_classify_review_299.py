"""Independent PR #299 audit: synthetic JSON only; no physics or model calls.

R1/R2 xfails assert the intended safety result, NOT the known-bad output.
Use --runxfail to expose the counterexamples as ordinary failing tests.
The JSON builders below are independent of the author's test fixtures.
"""
import copy
import importlib.util
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
    # A JSON round-trip ensures fixtures contain only actual JSON types.
    return json.loads(json.dumps([row, result, trace], allow_nan=False))


def write_json(path, obj):
    path.write_text(json.dumps(obj, sort_keys=True, allow_nan=False) + "\n")


def write_record(raw, row, result, trace, identity):
    directory = cp.ca.dra.case_dir(raw, row["case_id"])
    (directory / "eval_only").mkdir(parents=True, exist_ok=True)
    write_json(directory / "result.json", dict(result, row=row, execution_identity=identity))
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


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="R1: endpoint tilt >15 is absent from whole-chain safety maximum")
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


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="R2: retry selection discards the original attempt's recorded hard violations")
@pytest.mark.parametrize("seed", [941, 943])
@pytest.mark.parametrize("hard", ["tilt", "penetration"])
def test_host_retry_must_not_erase_known_safety_violation(tmp_path, seed, hard):
    raw, seal, rows, identity = sealed_cohort(tmp_path, retry_seed=seed)
    original_id = add_host_retry(raw, seal, rows, identity, seed, hard)
    s = analyse(raw, seal)
    assert original_id in s["attempt_case_ids"] and original_id not in s["selected_case_ids"]
    assert (s["n_cases"], s["n_placements"]) == (72, 60)  # count selected attempt only, retain safety from all
    assert s["full_verdict"] == "FAIL_A_B_SAFETY", s


def test_host_retry_without_hard_violation_counts_once(tmp_path):
    raw, seal, rows, identity = sealed_cohort(tmp_path, retry_seed=941)
    add_host_retry(raw, seal, rows, identity)
    s = analyse(raw, seal)
    assert (len(s["attempt_case_ids"]), len(s["selected_case_ids"]), s["n_cases"]) == (73, 72, 72)
    assert s["pass_placements"] == 60 and s["full_verdict"] == "PASS_A_B_SAFETY"


@pytest.mark.parametrize("seed", [941, 943])
def test_unreplaced_host_error_blocks_evaluation_and_is_not_a_failure(tmp_path, seed):
    raw, seal, rows, identity = sealed_cohort(tmp_path)
    row = next(r for r in rows if r["cell"] == "C01" and r["seed"] == seed)
    row["category"] = "HOST_ERROR:worker_exit_-15"
    write_rows(raw, rows)
    s = analyse(raw, seal)
    assert s["full_verdict"] == "NOT_EVALUABLE"
    assert s["n_cases"] == 72 and s["n_placements"] == 60
    assert s["unclassified_cases"] == [row["case_id"]]
    assert s["counts"]["FAIL"] == 0


@pytest.mark.parametrize("mutation", ["missing_primary", "missing_auxiliary", "duplicate", "arbitrary_name"])
def test_sealed_cohort_rejects_wrong_inventory(tmp_path, mutation):
    raw, seal, rows, identity = sealed_cohort(tmp_path)
    if mutation == "missing_primary": rows.pop(0)
    if mutation == "missing_auxiliary": rows.pop(1)
    if mutation == "duplicate": rows.append(copy.deepcopy(rows[0]))
    if mutation == "arbitrary_name": rows[0]["cell"] = "P0"
    write_rows(raw, rows)
    with pytest.raises(cp.EvidenceError):
        analyse(raw, seal)
