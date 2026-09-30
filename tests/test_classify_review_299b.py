"""Independent re-review of #299 at 8a1631b9: JSON arithmetic only, no physics.

Reuse the first independent review's JSON builders, not implementer expectations.
Every re-pinned manifest here is SYNTHETIC test input, never an actual seal.
All review counterexamples are mandatory; v3 contract migrations are documented.
"""
import copy
import importlib.util
import json
import math
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "review_299b_builders", ROOT / "tests/test_classify_review_299.py")
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)
cp = base.cp


def cohort(tmp_path, retries=()):
    raw, _, rows, identity = base.sealed_cohort(tmp_path)
    path = tmp_path / "seal.json"
    seal = json.loads(path.read_text())
    for cell, seed in retries:
        entry = next(e for e in seal["cases"] if (e["placement"], e["seed"]) == (cell, seed))
        original = entry["attempts"][0]["case_id"]
        case = json.loads((cp.ca.dra.case_dir(raw, original) / "case.json").read_text())
        case["case_id"] += ":retry1"
        directory = cp.ca.dra.case_dir(raw, case["case_id"])
        directory.mkdir()
        base.write_json(directory / "case.json", case)
        entry["attempts"].append({"case_id": case["case_id"], "replaces": original,
                                   "case_sha256": cp.sha256(directory / "case.json")})
    base.write_json(path, seal)
    return raw, cp.load_sealed_manifest(path, cp.sha256(path)), rows, identity


def saved(raw, row):
    directory = cp.ca.dra.case_dir(raw, row["case_id"])
    result = json.loads((directory / "result.json").read_text())
    trace = [json.loads(line) for line in (directory / "eval_only/trace.jsonl").read_text().splitlines()]
    return result, trace


def change(raw, rows, identity, row, result, trace):
    base.write_record(raw, row, result, trace, identity)
    base.write_rows(raw, rows)


def host(row, result):
    row.update(category="HOST_ERROR:ENOSPC", host_error="ENOSPC during cleanup")
    result["termination"]["outcome"] = "HOST_ERROR"


def ordinary_failure(row, result):
    row["chain"]["legs"][1]["end_error_m"] = .11
    failure = {"phase": "carry", "leg": 1, "code": "END_ERROR", "sim_s": 3.01}
    row["chain"]["first_failure"] = failure
    result["failures"]["r1"] = copy.deepcopy(failure)


def retry(raw, seal, rows, identity, cell="C01", seed=941):
    entry = next(e for e in seal["cases"] if (e["placement"], e["seed"]) == (cell, seed))
    row, result, trace = base.record(cell, seed)
    row["case_id"] = entry["attempts"][1]["case_id"]
    rows.append(row)
    change(raw, rows, identity, row, result, trace)
    return row, result, trace


def report(raw, seal):
    return cp.analyse("review299b", raw, sealed_manifest=seal)


@pytest.mark.parametrize("t", [.249999, 1.010001, 1.999999, 3.010001, 3.249999])
@pytest.mark.parametrize("above", [False, True])
def test_r1_asynchronous_gt_at_other_times_and_next_float_boundary(t, above):
    row, result, trace = base.record()
    # Both robots' snapshots count; a low second value must not overwrite a high one.
    value = math.nextafter(15., math.inf) if above else 15.
    result["chain_raw"] = {
        "r1": {"leg_end": {"1": {"sim_s": t, "gt": {"t": t, "tilt_deg": value}}}},
        "r2": {"leg_end": {"1": {"sim_s": t, "gt": {"t": t, "tilt_deg": 1.}}}},
    }
    out = cp.classify_case(row, result, trace, confirmatory=True)
    assert out["hard_limit_chain"]["max_tilt_deg"] == value
    assert out["hard_limit_chain"]["violated"] is above
    assert out["class"] == ("FAIL_HARD_LIMIT" if above else "PASS_CLEAN")


@pytest.mark.parametrize("t", [.000001, .249999, 1.010001, 1.999999, 3.249999])
@pytest.mark.parametrize("above", [False, True])
def test_contact_hard_limit_at_new_times_and_next_float_boundary(t, above):
    row, result, trace = base.record()
    pen = math.nextafter(.005, math.inf) if above else .005
    result["wall_contact"]["episodes"] = [{"t_first": t, "t_last": t, "max_pen_m": pen}]
    out = cp.classify_case(row, result, trace, confirmatory=True)
    assert out["hard_limit_chain"]["violated"] is above
    assert out["class"] == ("FAIL_HARD_LIMIT" if above else "PASS_CONTACT_RECOVERED")


@pytest.mark.parametrize("field", ["jaws", "lift_m", "end_sim_s", "tilt_deg"])
def test_r1_missing_endpoint_fields_never_become_pass(field):
    row, result, trace = base.record()
    row["chain"]["legs"][0]["tilt_deg"] = 16.
    del row["chain"]["legs"][0][field]
    # Input errors are documented as exit 2, not successful adjudications.
    with pytest.raises(cp.EvidenceError):
        cp.classify_case(row, result, trace, confirmatory=True)


@pytest.mark.parametrize("seed", [941, 943])
@pytest.mark.parametrize("kind", ["tilt", "penetration"])
@pytest.mark.parametrize("where", ["cases_only", "result_row_only", "both"])
def test_r2_saved_contact_summary_must_keep_known_violation(tmp_path, seed, kind, where):
    raw, seal, rows, identity = cohort(tmp_path, [("C01", seed)])
    original = next(r for r in rows if (r["cell"], r["seed"]) == ("C01", seed))
    result, trace = saved(raw, original)
    host(original, result)
    # This is the actual recorder's row.wall_contact schema (contact_outcome),
    # not a new hypothetical field. It can outlive the large result/trace files.
    summary = {"episodes": 1, "who": ["beam"], "max_penetration_m": .006 if kind == "penetration" else .004,
               "first_contact_sim_s": 1.25, "wall_geoms": ["wall"],
               "max_tilt_deg_stage": 16. if kind == "tilt" else 1.,
               "hard_limits": {"max_tilt_deg": 15., "max_penetration_m": .005}}
    original["wall_contact"] = summary
    change(raw, rows, identity, original, result, trace)
    retry(raw, seal, rows, identity, seed=seed)
    directory = cp.ca.dra.case_dir(raw, original["case_id"])
    if where == "cases_only":
        (directory / "result.json").unlink()
        (directory / "eval_only/trace.jsonl").unlink()
    elif where == "result_row_only":
        del original["wall_contact"]  # differing partial copies must retain the known maximum
        base.write_rows(raw, rows)
    out = report(raw, seal)
    s = out["summary"]
    assert (s["n_cases"], s["n_attempts"], s["pass_placements"]) == (72, 73, 59 if seed == 941 else 60)
    assert s["full_verdict"] == "FAIL_A_B_SAFETY", s
    assert s["hard_limit_attempt_case_ids"] == [original["case_id"]]


@pytest.mark.parametrize("corruption", ["empty", "line_aligned_tail", "missing_middle", "duplicate_time", "reverse_time"])
def test_host_stored_trace_contradiction_is_not_silent_success(tmp_path, corruption):
    raw, seal, rows, identity = cohort(tmp_path, [("C01", 941)])
    original = rows[0]
    result, trace = saved(raw, original)
    host(original, result)
    change(raw, rows, identity, original, result, trace)
    retry(raw, seal, rows, identity)
    path = cp.ca.dra.case_dir(raw, original["case_id"]) / "eval_only/trace.jsonl"
    if corruption == "empty":
        trace = []
    elif corruption == "line_aligned_tail":
        trace = trace[:21]
    elif corruption == "missing_middle":
        trace = trace[:10] + trace[40:]
    elif corruption == "duplicate_time":
        trace[20]["t"] = trace[19]["t"]
    else:
        trace.reverse()
    # Every remaining line is valid JSON; saved evaluation_coverage still says
    # 66 rows spanning 0..3.25. This tests contradictory saved evidence, not an
    # interrupted attempt with absent metadata or genuinely missing files.
    path.write_text("".join(json.dumps(s) + "\n" for s in trace))
    out = report(raw, seal)
    s = out["summary"]
    assert s["full_verdict"] == "FAIL_A_B_SAFETY", s
    assert s["safety_evidence_issues"].get(original["case_id"])


def test_known_host_violation_survives_line_aligned_truncation_and_missing_B(tmp_path):
    raw, seal, rows, identity = cohort(tmp_path, [("C01", 941)])
    original = rows[0]
    result, trace = saved(raw, original)
    host(original, result)
    trace[1]["tilt_deg"] = 16.
    change(raw, rows, identity, original, result, trace[:5])
    retry_row, retry_result, retry_trace = retry(raw, seal, rows, identity)
    for sample in retry_trace:
        sample.pop("pf")
    change(raw, rows, identity, retry_row, retry_result, retry_trace)
    s = report(raw, seal)["summary"]
    assert s["sigma_criterion_B"]["verdict"] == "NOT_EVALUABLE"
    assert s["hard_limit_attempt_case_ids"] == [original["case_id"]]
    assert s["full_verdict"] == "FAIL_A_B_SAFETY"


@pytest.mark.parametrize("missing", ["tilt_deg", "max_pen_m"])
def test_host_present_observation_with_missing_metric_blocks_pass(tmp_path, missing):
    raw, seal, rows, identity = cohort(tmp_path, [("C01", 941)])
    row = rows[0]
    result, trace = saved(raw, row)
    host(row, result)
    if missing == "tilt_deg":
        result["gt_at_stop"] = {"t": 3.01}
    else:
        result["wall_contact"]["episodes"] = [{"t_first": 1.25, "t_last": 1.3}]
    change(raw, rows, identity, row, result, trace)
    retry(raw, seal, rows, identity)
    s = report(raw, seal)["summary"]
    assert s["safety_evidence_issues"][row["case_id"]]
    assert s["full_verdict"] == "FAIL_A_B_SAFETY"


def test_many_legal_retries_are_order_independent_and_count_unique_placements(tmp_path):
    pairs = [("C01", 941), ("C01", 943), ("C02", 941), ("C60", 941)]
    raw, seal, rows, identity = cohort(tmp_path, pairs)
    for i, pair in enumerate(pairs):
        row = next(r for r in rows if (r["cell"], r["seed"]) == pair)
        result, trace = saved(raw, row)
        host(row, result)
        if i % 2:
            result["wall_contact"]["episodes"] = [{"t_first": 3.249, "t_last": 3.25, "max_pen_m": .006}]
        else:
            result["teacher"] = {"gt_after_lift": {"t": .249, "tilt_deg": 16.}}
        change(raw, rows, identity, row, result, trace)
        retry(raw, seal, rows, identity, *pair)
    rows.reverse()  # retries precede originals in the file; inventory controls selection
    base.write_rows(raw, rows)
    out = report(raw, seal)
    s = out["summary"]
    assert (s["n_cases"], s["n_attempts"], s["n_placements"], s["pass_placements"]) == (72, 76, 60, 57)
    assert s["hard_limit_chain_cases"] == 4
    assert s["hard_limit_chain_placements_any_seed"] == 3
    assert s["full_verdict"] == "FAIL_A_B_SAFETY"
    assert len(s["selected_case_ids"]) == len(set(s["selected_case_ids"])) == 72


@pytest.mark.parametrize("after", ["FAIL", "HOST_ERROR"])
@pytest.mark.parametrize("hard", [False, True])
def test_host_then_fail_or_host_keeps_the_selected_outcome(tmp_path, after, hard):
    raw, seal, rows, identity = cohort(tmp_path, [("C01", 941)])
    row = rows[0]
    result, trace = saved(raw, row)
    host(row, result)
    if hard:
        result["gt_at_entry"] = {"t": .249, "tilt_deg": 16.}
    change(raw, rows, identity, row, result, trace)
    rr, res, tr = retry(raw, seal, rows, identity)
    if after == "FAIL":
        ordinary_failure(rr, res)
    else:
        host(rr, res)
    change(raw, rows, identity, rr, res, tr)
    s = report(raw, seal)["summary"]
    assert (s["n_cases"], s["n_attempts"], s["pass_placements"]) == (72, 73, 59)
    assert s["counts"]["FAIL"] == (0 if hard else 1)
    assert s["counts"]["FAIL_HARD_LIMIT"] == int(hard)
    assert s["unclassified_cases"] == []
    assert s["full_verdict"] == ("FAIL_A_B_SAFETY" if hard else
                                 "PASS_A_B_SAFETY" if after == "FAIL" else "FAIL_A_B_SAFETY")


@pytest.mark.parametrize("before", ["PASS", "FAIL"])
def test_retry_cannot_replace_non_host_original(tmp_path, before):
    raw, seal, rows, identity = cohort(tmp_path, [("C01", 941)])
    if before == "FAIL":
        row = rows[0]
        result, trace = saved(raw, row)
        ordinary_failure(row, result)
        change(raw, rows, identity, row, result, trace)
    retry(raw, seal, rows, identity)
    s = report(raw, seal)["summary"]
    assert s["pass_placements"] == 59
    assert rows[0]["case_id"] in s["selected_case_ids"]
    if before == "PASS":
        assert s["full_verdict"] == "FAIL_A_B_SAFETY" and s["invalid_cases"]
    else:
        assert s["counts"]["FAIL"] == 1
        assert s["full_verdict"] == "FAIL_A_B_SAFETY"  # unauthorized retry cannot certify a valid chain


@pytest.mark.parametrize("sequence", ["HOST_HOST_PASS", "HOST_FAIL_PASS"])
def test_third_attempt_is_rejected_even_when_first_is_host(tmp_path, sequence):
    raw, seal, rows, identity = cohort(tmp_path, [("C01", 941)])
    row = rows[0]
    result, trace = saved(raw, row)
    host(row, result)
    change(raw, rows, identity, row, result, trace)
    rr, res, tr = retry(raw, seal, rows, identity)
    (host if sequence == "HOST_HOST_PASS" else ordinary_failure)(rr, res)
    change(raw, rows, identity, rr, res, tr)
    third, res, tr = base.record()
    third["case_id"] += ":retry2"
    rows.append(third)
    path = cp.ca.dra.case_dir(raw, third["case_id"])
    path.mkdir()
    spec = json.loads((cp.ca.dra.case_dir(raw, row["case_id"]) / "case.json").read_text())
    base.write_json(path / "case.json", dict(spec, case_id=third["case_id"]))
    change(raw, rows, identity, third, res, tr)
    s = report(raw, seal)["summary"]
    assert s["full_verdict"] == "FAIL_A_B_SAFETY"
    assert any("UNAUTHORIZED_ATTEMPT" in e for e in s["cohort_evidence_issues"])
    seal_path = tmp_path / "seal.json"
    doc = json.loads(seal_path.read_text())
    doc["cases"][0]["attempts"].append({"case_id": third["case_id"], "replaces": row["case_id"],
                                       "case_sha256": cp.sha256(path / "case.json")})
    base.write_json(seal_path, doc)
    with pytest.raises(cp.EvidenceError, match="at most one"):
        cp.load_sealed_manifest(seal_path, cp.sha256(seal_path))


def test_controller_failures_followed_by_cleanup_errors_cannot_be_retried_to_pass(tmp_path):
    pairs = [(f"C{i:02d}", 941) for i in range(1, 14)]
    raw, seal, rows, identity = cohort(tmp_path, pairs)
    for pair in pairs:
        row = next(r for r in rows if (r["cell"], r["seed"]) == pair)
        result, trace = saved(raw, row)
        ordinary_failure(row, result)  # actual END_ERROR before a later save/cleanup fault
        change(raw, rows, identity, row, result, trace)
    control = report(raw, seal)["summary"]
    assert control["pass_placements"] == 47
    assert control["full_verdict"] == "FAIL_A_B_SAFETY"
    for pair in pairs:
        row = next(r for r in rows if (r["cell"], r["seed"]) == pair)
        result, trace = saved(raw, row)
        host(row, result)
        change(raw, rows, identity, row, result, trace)
        retry(raw, seal, rows, identity, *pair)
    try:
        s = report(raw, seal)["summary"]
    except cp.EvidenceError:
        return  # Rejecting the contradictory/retry-ineligible original is also valid.
    assert s["full_verdict"] != "PASS_A_B_SAFETY", s


@pytest.mark.parametrize("mutation", ["duplicate_original", "duplicate_retry", "duplicate_placement_seed", "duplicate_placement_name"])
def test_duplicate_inventory_is_rejected(tmp_path, mutation):
    raw, seal, rows, identity = cohort(tmp_path, [("C01", 941)])
    if mutation == "duplicate_original":
        rows.append(copy.deepcopy(rows[0]))
    elif mutation == "duplicate_retry":
        row = rows[0]
        result, trace = saved(raw, row)
        host(row, result)
        change(raw, rows, identity, row, result, trace)
        rr, _, _ = retry(raw, seal, rows, identity)
        rows.append(copy.deepcopy(rr))
    elif mutation == "duplicate_placement_seed":
        rows[2]["cell"] = "C01"  # another case ID claims the same placement + seed
    else:
        path = tmp_path / "placements.json"
        placements = json.loads(path.read_text())
        placements[1]["name"] = "C01"
        base.write_json(path, placements)
        seal_path = tmp_path / "seal.json"
        doc = json.loads(seal_path.read_text())
        doc["placements_sha256"] = cp.sha256(path)
        base.write_json(seal_path, doc)
        with pytest.raises(cp.EvidenceError, match="ordered C01..C60"):
            cp.load_sealed_manifest(seal_path, cp.sha256(seal_path))
        return
    base.write_rows(raw, rows)
    s = report(raw, seal)["summary"]
    assert s["full_verdict"] == "FAIL_A_B_SAFETY"
    assert s["invalid_cases"] and s["denominator"] == 60
