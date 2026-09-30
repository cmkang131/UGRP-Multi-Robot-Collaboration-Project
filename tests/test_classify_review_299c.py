"""Independent third review of f32d5fd9: JSON only, no physics or hidden raw.

The first review's builder supplies a valid synthetic recording and a 60+12
admission fixture. New mutations and expectations are defined here. Receipts
are calculated when the synthetic recorder writes the contradictory evidence;
these tests do NOT claim to defeat SHA-256 by modifying files after hashing.
"""
import copy
import importlib.util
import itertools
import json
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "review_299c_builders", Path(__file__).with_name("test_classify_review_299.py"))
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)
cp = base.cp
AUDIT = (Path(__file__).resolve().parents[1] /
         "experiments/2026-09-30-pair-v6h-carry/analysis/review_299c_validation/recorder_audit.json")


def damage_handover(row, trace, kind):
    if kind == "no_release":
        for sample in trace:
            sample.update(lift_m=.05, jaws={r: [True, True] for r in base.ROBOTS})
    elif kind == "no_regrasp":
        for sample in trace:
            if 1.95 <= sample["t"] <= 2.:
                sample["jaws"]["r1"] = [False, False]
    else:
        row["chain"]["restaging_between_legs"] = True


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="299c R3: cleanup HOST bypasses completed handover/restaging failure")
@pytest.mark.parametrize("kind", ["no_release", "no_regrasp", "restaging"])
def test_cleanup_host_cannot_replace_completed_handover_failure(tmp_path, kind):
    raw, seal, rows, identity = base.sealed_cohort(tmp_path, retry_seed=941)
    row, result, trace = base.record()
    damage_handover(row, trace, kind)
    base.record_receipt(row, result, trace)
    # Before the cleanup label, precisely the same completed task is not PASS.
    assert cp.adjudicate_attempt(row, result, trace)["class"] not in cp.PASS
    row.update(category="HOST_ERROR:ENOSPC", host_error="ENOSPC after L1 completion")
    result["termination"]["outcome"] = "HOST_ERROR"
    rows[0] = row
    base.write_record(raw, row, result, trace, identity)
    retry, res, tr = base.record()
    retry["case_id"] = seal["cases"][0]["attempts"][1]["case_id"]
    rows.append(retry)
    base.write_record(raw, retry, res, tr, identity)
    base.write_rows(raw, rows)
    report = cp.analyse("review299c", raw, sealed_manifest=seal)
    assert report["summary"]["full_verdict"] != "PASS_A_B_SAFETY", report["summary"]


def contradict(row, result, trace, kind):
    if kind == "result_host_error":
        # This is a real runner field (run_pair_stage_probes.py:657), not an
        # invented error flag. It conflicts with row and normal termination.
        result["host_error"] = {"type": "OSError", "classification": "HOST_ERROR", "enospc": True}
    elif kind == "endpoint_gt":
        # The summary and BOTH source endpoint snapshots disagree at precisely
        # the same instant. No asynchronous-sampling tolerance is involved.
        result["chain_raw"] = {r: {"leg_end": {"1": {
            "sim_s": 3.01, "gt": {"t": 3.01, "tilt_deg": 1., "lift_m": 0.,
                                      "jaws": {r: [False, False] for r in base.ROBOTS}}}}}
            for r in base.ROBOTS}
    elif kind == "missing_teacher_prefix":
        result["teacher"] = {"gt_after_lift": {"t": .1, "tilt_deg": 1.}}
        result["gt_at_entry"] = {"t": .1, "tilt_deg": 1.}
        trace[:] = trace[5:]
        result["evaluation_coverage"].update(start_sim_s=.25, trace_count=len(trace))
        result["wall_contact"]["coverage"].update(start_sim_s=.25, sample_count=len(trace))
    elif kind == "impossible_contact_coverage":
        # 66 samples at 0.05 s cannot cover a 1100 s interval; negative SIM
        # time is also impossible. All supplied values are finite JSON numbers.
        result["wall_contact"]["coverage"].update(start_sim_s=-100., end_sim_s=1000.)
    else:
        raise AssertionError(kind)


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="299c R4/R5: internally contradictory recorder evidence is accepted")
@pytest.mark.parametrize("kind", ["result_host_error", "endpoint_gt", "missing_teacher_prefix",
                                  "impossible_contact_coverage"])
def test_contradictory_evidence_cannot_pass_entire_cohort(tmp_path, kind):
    raw, seal, rows, identity = base.sealed_cohort(tmp_path)
    row, result, trace = base.record()
    contradict(row, result, trace, kind)
    rows[0] = row
    base.write_record(raw, row, result, trace, identity)
    base.write_rows(raw, rows)
    report = cp.analyse("review299c", raw, sealed_manifest=seal)
    assert report["summary"]["full_verdict"] != "PASS_A_B_SAFETY", report["summary"]


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="299c R2: prereg excludes HOST_ERROR from task PASS/FAIL; v3 converts it to FAIL")
@pytest.mark.parametrize("missing_trace", [False, True])
def test_unresolved_host_is_unclassified_under_registered_rule(missing_trace):
    row, result, trace = base.record()
    row.update(category="HOST_ERROR:ENOSPC", host_error="ENOSPC")
    result["termination"]["outcome"] = "HOST_ERROR"
    base.record_receipt(row, result, trace)
    if missing_trace:
        trace.clear()
    attempt = cp.adjudicate_attempt(row, result, trace)
    selected = cp.classify_attempt_sequence([attempt])
    # Keep admission and all positive safety evidence. Neither success nor a
    # measured task failure is licensed by a host error; completion is blocked.
    assert not selected["hard_limit_chain"]["violated"]
    assert selected["class"] is None, selected


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="299c R1: 4c6b439f recorder has no v3 required fields (public acceptance inventory)")
@pytest.mark.parametrize("field", [
    "result.evidence_sha256", "result.execution_identity", "result.evaluation_coverage",
    "result.wall_contact.coverage",
])
def test_registered_recorder_produces_required_fields(field):
    # Frozen read-only inventory, per-file SHA-256 and reproduction script are
    # committed together. No lookup of any confirmatory output path occurs.
    audit = json.loads(AUDIT.read_text())
    assert audit["runner_byte_identical"] is True
    absent = [case["case_id"] for case in audit["cases"] if field in case["missing_required"]]
    assert absent == [], absent


@pytest.mark.parametrize("kind", ["unchanged", "extra_planned_legs", "contact_at_limit", "small_negative_rest_height"])
def test_complete_valid_pass_controls(kind):
    row, result, trace = base.record()
    if kind == "extra_planned_legs":
        row["chain"]["n_legs"] = 8
        row["chain"]["legs"].extend({"leg": k, "recorded": False,
                                      "start_sim_s": None, "end_sim_s": None} for k in range(2, 8))
    elif kind == "contact_at_limit":
        result["wall_contact"]["episodes"] = [{"t_first": .5, "t_last": .6, "max_pen_m": .005}]
        row["wall_contact"].update(episodes=1, max_penetration_m=.005)
    elif kind == "small_negative_rest_height":
        for sample in trace:
            if 1.25 <= sample["t"] <= 1.5:
                sample["lift_m"] = -1e-6
    base.record_receipt(row, result, trace)
    out = cp.adjudicate_attempt(row, result, trace)
    assert out["evidence_valid"] and out["class"] in cp.PASS, out


@pytest.mark.parametrize("kind", ["partial_host", "stale_receipt", "summary_hard", "offgrid_endpoint_hard"])
def test_earlier_finding_generalizations_remain_closed(kind):
    row, result, trace = base.record()
    if kind == "partial_host":
        row.update(category="HOST_ERROR:ENOSPC", host_error="ENOSPC")
        result["termination"]["outcome"] = "HOST_ERROR"
        base.record_receipt(row, result, trace)
        trace[:] = trace[:30]
    elif kind == "stale_receipt":
        result["gt_at_stop"] = {"t": 3.01, "tilt_deg": 16.}
        base.record_receipt(row, result, trace)
        del result["gt_at_stop"]
    elif kind == "summary_hard":
        row["wall_contact"]["max_penetration_m"] = .006
    else:
        row["chain"]["legs"][0]["tilt_deg"] = 15.00000001
    out = cp.adjudicate_attempt(row, result, trace)
    assert out["class"] not in cp.PASS
    if kind in ("summary_hard", "offgrid_endpoint_hard"):
        assert out["class"] == "FAIL_HARD_LIMIT"


def test_state_table_is_total_and_terminal_failures_never_recover():
    events = ("PASS", "FAIL", "HARD", "INVALID", "HOST_SAFE")
    assert all(set(row) == set(events) for row in cp.TRANSITIONS.values())
    assert cp.classify_attempt_sequence([])["state"] == "INVALID"
    for n in (1, 2, 3):
        for states in itertools.product(events, repeat=n):
            attempts = [{"case_id": str(i), "state": s,
                         "class": "PASS_CLEAN" if s == "PASS" else "FAIL_HARD_LIMIT" if s == "HARD" else "FAIL",
                         "evidence_valid": s != "INVALID", "hard_limit_chain": {"violated": s == "HARD"}}
                        for i, s in enumerate(states)]
            out = cp.classify_attempt_sequence(attempts)
            assert out["state"] in {"PASS", "FAIL", "HARD", "INVALID"}
            if "HARD" in states:
                assert out["class"] == "FAIL_HARD_LIMIT"
            elif "FAIL" in states or "INVALID" in states:
                assert out["class"] not in cp.PASS


@pytest.mark.parametrize("field", ["chain", "wall_contact", "failures", "termination", "trace"])
def test_malformed_containers_have_total_attempt_result(field):
    row, result, trace = base.record()
    if field in ("chain", "wall_contact"):
        row[field] = []
    elif field == "trace":
        trace = [None, 1, "bad"]
    else:
        result[field] = []
    out = cp.adjudicate_attempt(row, result, trace)
    assert out["state"] == "INVALID" and out["class"] == "FAIL"
