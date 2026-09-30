#!/usr/bin/env python3
"""Read-only, eval-only placement classification for the UNSEALED v6h draft.

Usage: classify_placements.py --output NEW_DIR [--primary-seed 911] cB=/absolute/raw ...
Default primary seed is 941 (prereg); historical cohorts must select 911 explicitly.
No simulation, controller mutation, model call, registration or sealing occurs here.
Provisional interpretations and remaining decisions: CLASSIFY_NOTES.md.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]
CHAIN_PATH = ROOT / "experiments/2026-09-30-door-relax-envelope/analysis/chain_analysis.py"
_spec = importlib.util.spec_from_file_location("v6h_chain_analysis", CHAIN_PATH)
ca = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ca)
SIGMA_PATH = ROOT / "experiments/2026-09-30-b-v6h-gain/analysis/gain_cohort_analysis.py"
_spec = importlib.util.spec_from_file_location("v6h_sigma_analysis", SIGMA_PATH)
ga = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ga)
RECORDER_PATH = Path(__file__).with_name("recorder_v4c6b.py")
_spec = importlib.util.spec_from_file_location("v6h_registered_recorder", RECORDER_PATH)
rv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rv)

CLASSES = ("PASS_CLEAN", "PASS_CONTACT_RECOVERED", "BLOCKED_BY_CONTACT", "FAIL", "FAIL_HARD_LIMIT")
PASS = CLASSES[:2]
REQUIRED_LEGS = (0, 1)
ROBOTS = ("r1", "r2")
# Recommended draft limits, not a seal. The recorder samples at 0.05 SIM s.
TRACE_GAP_S = .051
PF_MAX_AGE_S = .30
EVALUATION_PROTOCOL = {"include_teacher": True, "end_boundary": "termination",
                       "trace_max_gap_s": TRACE_GAP_S, "pf_max_age_s": PF_MAX_AGE_S,
                       "primary_sigma_seed": 941, "destination_setdown": False,
                       "handover": "L0_end_to_L1_start_rest_release_then_lift",
                       "L1_stop": "first_wait_lower_both_robots",
                       "hard_limit_observations": "trace_endpoints_and_saved_gt",
                       "host_error_safety": "complete_safe_original_without_task_failure_only",
                       "accounting": "admitted_placements_unclassified_blocks_claim",
                       "attempt_machine": "terminal_failure_v1",
                       "stored_safety_summary": "required",
                       "evidence_integrity": "registered_producer_contract_or_canonical_attempt_sha256_v1"}


class EvidenceError(ValueError):
    """Incomplete or ambiguous raw evidence must not produce a clean pass."""


def finite(value, name):
    try:
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise EvidenceError(f"{name}: expected a finite number, got {value!r}")
    return value


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def binomial_tail(p, n=60, minimum=48):
    """P(X >= 48 | n=60, p); safety and sigma criteria are not modeled."""
    return math.fsum(math.comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(minimum, n + 1))


def jaws_valid(jaws):
    if (not isinstance(jaws, dict) or set(jaws) != set(ROBOTS)
            or any(not isinstance(jaws[r], list) or len(jaws[r]) != 2
                   or any(type(v) is not bool for v in jaws[r]) for r in ROBOTS)):
        raise EvidenceError("jaws: require r1/r2, two boolean jaw contacts each")
    return jaws


def validate_teacher_window(result, start, end):
    if not EVALUATION_PROTOCOL["include_teacher"]:
        return
    for name, snap in (("teacher.gt_after_lift", (result.get("teacher") or {}).get("gt_after_lift")),
                       ("gt_at_entry", result.get("gt_at_entry"))):
        if snap is not None:
            t = finite(snap.get("t"), name + ".t")
            if not start - 1e-9 <= t <= end + 1e-9:
                raise EvidenceError(name + ": outside recorded window")


def validate_trace(row, result, trace, confirmatory, recorder=None):
    if not isinstance(trace, list) or not trace or any(not isinstance(s, dict) for s in trace):
        raise EvidenceError("trace: require nonempty object array")
    times = [finite(s.get("t"), "trace t") for s in trace]
    if times[0] < 0 or any(b <= a or b - a > TRACE_GAP_S + 1e-9 for a, b in zip(times, times[1:])):
        raise EvidenceError("trace: unordered times or missing samples (gap > .051 SIM s)")
    for sample in trace:
        tilt = finite(sample.get("tilt_deg"), "trace tilt_deg")
        if not 0 <= tilt <= 180:
            raise EvidenceError("trace tilt outside [0,180]")
    boundaries = [finite(l[key], key) for l in row["chain"]["legs"]
                  for key in ("start_sim_s", "end_sim_s") if l.get(key) is not None]
    if row.get("stop_sim_s") is not None:
        boundaries.append(finite(row["stop_sim_s"], "stop_sim_s"))
    if ((not boundaries and not host_signal(row, result)) or (boundaries and
            (times[0] > min(boundaries) + TRACE_GAP_S or times[-1] < max(boundaries) - TRACE_GAP_S))):
        raise EvidenceError("trace: truncated execution window")
    if not confirmatory:
        return
    if recorder is not None and "evaluation_coverage" not in result and "coverage" not in (result.get("wall_contact") or {}):
        # The pinned v4c6b producer has no coverage receipt. These are observed
        # timestamps, NOT invented acquisition start/end or contact cadence.
        if len(times) < 2 or times[-1] <= times[0]:
            raise EvidenceError("trace: empty recorded window")
        term = result.get("termination") or {}
        if term.get("sim_s") is not None and abs(finite(term["sim_s"], "termination time") - times[-1]) > TRACE_GAP_S:
            raise EvidenceError("trace: truncated termination window")
        validate_teacher_window(result, times[0], times[-1])
        wall = result.get("wall_contact") or {}
        if not isinstance(wall.get("steps"), dict) or any(type(n) is not int or n < 0 for n in wall["steps"].values()):
            raise EvidenceError("wall-contact: invalid recorded contact steps")
        by_who = defaultdict(list)
        for episode in wall["episodes"]:
            n = episode.get("steps")
            if type(n) is not int or n < 1 or episode.get("who") not in wall["steps"]:
                raise EvidenceError("wall-contact: episode/contact steps mismatch")
            by_who[episode["who"]].append(n)
        for who, n in wall["steps"].items():
            counts = by_who.get(who, [])
            if not max(counts, default=0) <= n <= sum(counts):
                raise EvidenceError("wall-contact: positive steps contradict episodes")
        # The recorder tracks contacts every physics step, earlier/later than
        # the trace grid by up to one sample. No total sample count is stored.
        if any(e["t_first"] < times[0] - TRACE_GAP_S or e["t_last"] > times[-1] + TRACE_GAP_S
               for e in wall["episodes"]):
            raise EvidenceError("wall episode outside recorded trace window")
        for sample in trace:
            finite(sample.get("lift_m"), "trace lift_m")
            jaws_valid(sample.get("jaws"))
        return
    coverage = result.get("evaluation_coverage") or {}
    start = finite(coverage.get("start_sim_s"), "record start")
    end = finite(coverage.get("end_sim_s"), "record end")
    termination = finite((result.get("termination") or {}).get("sim_s"), "termination time")
    if (abs(end - termination) > 1e-9 or start < 0 or end <= start or abs(times[0] - start) > TRACE_GAP_S or abs(times[-1] - end) > TRACE_GAP_S
            or type(coverage.get("trace_count")) is not int
            or coverage.get("trace_count") != len(trace) or min(boundaries) < start - TRACE_GAP_S
            or max(boundaries) > end + TRACE_GAP_S):
        raise EvidenceError("trace: full-record coverage/count mismatch")
    wall = (result.get("wall_contact") or {}).get("coverage") or {}
    for key in ("start_sim_s", "end_sim_s", "max_gap_s", "sample_period_s"):
        finite(wall.get(key), "wall coverage " + key)
    period = wall["sample_period_s"]
    count = wall.get("sample_count")
    if (period <= 0 or period > TRACE_GAP_S or not 0 <= wall["max_gap_s"] <= period + 1e-9
            or wall["start_sim_s"] < 0 or wall["end_sim_s"] <= wall["start_sim_s"]
            or type(count) is not int or count < 2
            or abs((count - 1) * period - (wall["end_sim_s"] - wall["start_sim_s"])) > period + 1e-9
            or (count - 1) * wall["max_gap_s"] < wall["end_sim_s"] - wall["start_sim_s"] - 1e-9
            or wall["start_sim_s"] > start + period or wall["end_sim_s"] < end - period):
        raise EvidenceError("wall-contact: incomplete full-record coverage")
    validate_teacher_window(result, max(start, times[0]), min(end, times[-1]))
    if any(e["t_first"] < start - 1e-9 or e["t_last"] > end + 1e-9 for e in result["wall_contact"]["episodes"]):
        raise EvidenceError("wall episode outside full record")
    for sample in trace:
        finite(sample.get("lift_m"), "trace lift_m")
        jaws_valid(sample.get("jaws"))


def validate_leg(leg):
    if type(leg.get("recorded")) is not bool:
        raise EvidenceError("leg recorded must be boolean")
    if not leg["recorded"]:
        if leg.get("end_sim_s") is not None:
            raise EvidenceError("unrecorded leg cannot have an endpoint")
        return
    start, end = (finite(leg.get(k), k) for k in ("start_sim_s", "end_sim_s"))
    if start < 0 or end <= start:
        raise EvidenceError("recorded leg requires ordered start/end")
    for key in ("lift_m", "tilt_deg", "end_error_m", "leg_error_m"):
        value = finite(leg.get(key), key)
        if (key != "lift_m" and value < 0) or (key == "tilt_deg" and value > 180):
            raise EvidenceError(f"{key}: invalid range")
    jaws_valid(leg.get("jaws"))


def handover_checks(chain, trace):
    """Evaluation only: L0 end -> L1 start; destination setdown is outside this probe."""
    legs = {l["leg"]: l for l in chain["legs"]}
    if not legs.get(0, {}).get("recorded") or legs.get(1, {}).get("start_sim_s") is None:
        return {"rest_release": False, "regrasp_lift": False}
    start, end = legs[0]["end_sim_s"], legs[1]["start_sim_s"]
    if end <= start:
        raise EvidenceError("L0 handover must precede L1 start")
    samples = [s for s in trace if start <= s["t"] <= end]
    # One simultaneous rest/release observation; no teacher restaging between legs.
    rest_release = any(s["lift_m"] <= .005 and s["tilt_deg"] <= 3.
                       and not any(v for contacts in s["jaws"].values() for v in contacts) for s in samples)
    at_start = [s for s in samples if end - s["t"] <= TRACE_GAP_S]
    regrasp = bool(at_start) and at_start[-1]["lift_m"] >= .03 and all(all(v) for v in at_start[-1]["jaws"].values())
    if chain.get("restaging_between_legs") is not False:
        raise EvidenceError("handover: must explicitly record no teacher restaging")
    return {"rest_release": rest_release, "regrasp_lift": regrasp,
            "window_sim_s": (start, end)}


def validate_end_window(row, result, legs):
    """A failed run may stop early; a completed L1 must stop at first wait_lower."""
    if not legs.get(1, {}).get("recorded"):
        return {"intended_L1_stop": False}
    end = legs[1]["end_sim_s"]
    stop = finite(row.get("stop_sim_s"), "stage stop")
    term = result.get("termination") or {}
    # Recorder's final cleanup may continue sampling after the stage boundary;
    # the safety window still includes it. Destination setdown is outside A.
    if (abs(stop - end) > 1e-6 or term.get("outcome") != "STUDY_LAYER_DONE"
            or finite(term.get("sim_s"), "termination time") < stop
            or row.get("final_states") != {r: "wait_lower" for r in ROBOTS}
            or result.get("final_states") != row["final_states"]):
        raise EvidenceError("completed L1 differs from intended first wait_lower stage stop")
    return {"intended_L1_stop": True, "L1_end_sim_s": end, "stage_stop_sim_s": stop,
            "record_end_sim_s": term["sim_s"], "destination_setdown_evaluated": False}


def failed_leg_window(leg, first_failure, stop_sim_s, trace_end):
    """Closed recorded window, or started-but-aborted carry window (notes #2)."""
    start, end = leg.get("start_sim_s"), leg.get("end_sim_s")
    if start is None:
        return None, "leg_not_started"
    finite(start, "leg start")
    source = "recorded_leg_end"
    if end is None:
        ff = first_failure or {}
        if ff.get("phase") == "carry" and ff.get("leg") == leg["leg"] and ff.get("sim_s") is not None:
            end, source = ff["sim_s"], "first_failure_sim_s"
        elif stop_sim_s is not None:
            end, source = stop_sim_s, "stop_sim_s"
        else:
            end, source = trace_end, "last_trace_sim_s"
    finite(end, "leg end")
    if end < start - 1e-9:
        raise EvidenceError(f"leg {leg['leg']}: end precedes start")
    return (start, end), source


def observed_hard_limits(row, result, trace, *, partial=False):
    """Union of saved safety observations, not an assertion of complete coverage.

    GT snapshots are asynchronous to the trace; neither can replace the other.
    A HOST_ERROR may leave partial evidence. Keep every valid observation even
    if another value is malformed; report those issues separately to block PASS.
    """
    tilts, episodes, issues = [], [], []

    def container(value, kind, name):
        if value is None:
            return kind()
        if isinstance(value, kind):
            return value
        message = f"{name}: expected {kind.__name__}"
        if not partial:
            raise EvidenceError(message)
        issues.append(message)
        return kind()

    def mapping(value, name):
        return container(value, dict, name)

    def observe(value, name, target, maximum=None):
        try:
            finite(value, name)
            target.append(value)
            if value < 0 or (maximum is not None and value > maximum):
                raise EvidenceError(f"{name}: invalid range")
        except EvidenceError as error:
            if not partial:
                raise
            issues.append(str(error))

    def snapshot(snap, name):
        if snap is not None:
            observe(mapping(snap, name).get("tilt_deg"), name + ".tilt_deg", tilts, 180)

    for sample in trace:
        snapshot(sample, "trace")
    for label, record in (("row", row), ("result.row", result.get("row") or {})):
        record = mapping(record, label)
        chain = mapping(record.get("chain"), label + ".chain")
        for leg in container(chain.get("legs"), list, label + ".chain.legs"):
            leg = mapping(leg, label + ".chain.leg")
            if "tilt_deg" in leg:
                snapshot(leg, label + ".chain.leg")
        if "tilt_deg" in mapping(chain.get("setdown"), label + ".chain.setdown"):
            snapshot(chain["setdown"], label + ".chain.setdown")
        if record.get("max_tilt_deg") is not None:
            observe(record["max_tilt_deg"], label + ".max_tilt_deg", tilts, 180)
        # Recorder contact_outcome() persists these even when larger files fail.
        stored = mapping(record.get("wall_contact"), label + ".wall_contact")
        if stored:
            observe(stored.get("max_tilt_deg_stage"), label + ".wall_contact.max_tilt_deg_stage", tilts, 180)
            pens = []
            observe(stored.get("max_penetration_m"), label + ".wall_contact.max_penetration_m", pens)
            episodes.extend({"max_pen_m": v} for v in pens)
    if result.get("max_tilt_deg") is not None:
        observe(result["max_tilt_deg"], "result.max_tilt_deg", tilts, 180)
    for key in ("gt_at_entry", "gt_at_stop", "gt_at_end"):
        snapshot(result.get(key), key)
    snapshot(mapping(result.get("teacher"), "teacher").get("gt_after_lift"), "teacher.gt_after_lift")
    for rid, robot in mapping(result.get("chain_raw"), "chain_raw").items():
        robot = mapping(robot, f"chain_raw.{rid}")
        for boundary in ("leg_start", "leg_end"):
            name = f"chain_raw.{rid}.{boundary}"
            for k, snap in mapping(robot.get(boundary), name).items():
                snapshot(mapping(snap, f"{name}.{k}").get("gt"), f"{name}.{k}.gt")
        snapshot(mapping(robot.get("done"), f"chain_raw.{rid}.done").get("gt"), f"chain_raw.{rid}.done.gt")
    for rid, snap in mapping(result.get("exits"), "exits").items():
        snapshot(mapping(snap, f"exits.{rid}").get("gt"), f"exits.{rid}.gt")
    wall = mapping(result.get("wall_contact"), "wall_contact")
    for episode in container(wall.get("episodes"), list, "wall_contact.episodes"):
        episode = mapping(episode, "contact")
        penetrations = []
        observe(episode.get("max_pen_m"), "contact.max_pen_m", penetrations)
        if penetrations:
            episodes.append({"max_pen_m": penetrations[0]})
    max_tilt = max(tilts, default=None)
    return {"violated": ca.hard_limit_violated(episodes, max_tilt or 0.),
            "max_tilt_deg": max_tilt,
            "max_pen_m": max((e["max_pen_m"] for e in episodes), default=0. if "episodes" in wall else None),
            "evidence_issues": issues}


def classify_case(row, result, trace, confirmatory=False, recorder=None):
    """Classify one completed seed case; whole-run hard limits have precedence."""
    chain = row.get("chain")
    if not chain or not trace:
        raise EvidenceError(f"{row['case_id']}: missing chain or nonempty eval trace")
    wall = result.get("wall_contact")
    if not isinstance(wall, dict) or not isinstance(wall.get("episodes"), list):
        raise EvidenceError(f"{row['case_id']}: missing wall-contact episode record (zero is not assumed)")
    episodes = wall["episodes"]
    for episode in episodes:
        for key in ("t_first", "t_last", "max_pen_m"):
            finite(episode.get(key), f"contact {key}")
        if episode["t_last"] < episode["t_first"] or episode["max_pen_m"] < 0:
            raise EvidenceError("invalid contact interval or penetration")
    validate_trace(row, result, trace, confirmatory, recorder)
    if confirmatory:
        validate_required_record(row, result)
    first_failure = chain.get("first_failure")
    by_leg = {}
    for leg in chain["legs"]:
        k = leg["leg"]
        if type(k) is not int or k < 0:
            raise EvidenceError("leg index must be a nonnegative integer")
        if k in by_leg:
            raise EvidenceError(f"duplicate leg {k}")
        by_leg[k] = leg
        validate_leg(leg)
    hard = observed_hard_limits(row, result, trace)
    if all(by_leg.get(k, {}).get("recorded") for k in REQUIRED_LEGS):
        if by_leg[1]["start_sim_s"] <= by_leg[0]["end_sim_s"]:
            raise EvidenceError("L0 end must precede L1 start")
    details = {}
    trace_end = max(sample["t"] for sample in trace)
    for k in REQUIRED_LEGS:
        leg = by_leg.get(k, {"leg": k, "recorded": False})
        checks = ca.pcp.leg_checks(leg)
        ok = bool(leg.get("recorded")) and bool(checks) and all(checks.values())
        window, window_source = failed_leg_window(leg, first_failure, row.get("stop_sim_s"), trace_end)
        contacts = ca.contacts_in(episodes, *window) if window else []
        details[f"L{k}"] = {"standard_pass": ok, "recorded": bool(leg.get("recorded")), "checks": checks,
                             "window_sim_s": window, "window_source": window_source, "contact_episodes": len(contacts)}
    failed = [k for k, detail in details.items() if not detail["standard_pass"]]
    failures = []
    for failure in (first_failure, row.get("first_failure")):
        if failure is not None:
            if not isinstance(failure, dict) or not failure:
                raise EvidenceError("invalid non-null first failure")
            failures.append(failure)
    raw_failures = result.get("failures")
    if raw_failures is not None and not isinstance(raw_failures, dict):
        raise EvidenceError("failures: require robot mapping or null")
    # Null robot entries explicitly mean NO failure. Empty/unknown non-null
    # entries are malformed evidence, never silently treated as a pass.
    for rid, failure in (raw_failures or {}).items():
        if failure is None:
            continue
        if rid not in ROBOTS or not isinstance(failure, dict) or not failure:
            raise EvidenceError("invalid non-null failure entry")
        failures.append(failure)
    # A controller failure cannot be repaired by a later good endpoint. An
    # intended --chain-stop-leg 1 has no first_failure; destination checks are
    # deliberately not used as L0 handover evidence.
    termination = result.get("termination") or {}
    if termination.get("outcome") not in (None, "STUDY_LAYER_DONE"):
        failures.append({"phase": "termination", "code": termination["outcome"], "sim_s": termination.get("sim_s")})
    unresolved = bool(failures)
    # Success-only handover/stop requirements cannot demote a known violation
    # to an ordinary failure or an unevaluable completion (e.g. failure stop).
    check_completion = confirmatory and not hard["violated"]
    handover = handover_checks(chain, trace) if check_completion else None
    end_window = validate_end_window(row, result, by_leg) if check_completion else None
    handover_failed = bool(handover and not all(handover[k] for k in ("rest_release", "regrasp_lift")))
    if hard["violated"]:
        outcome = "FAIL_HARD_LIMIT"
    elif not failed and not unresolved and not handover_failed:
        outcome = "PASS_CONTACT_RECOVERED" if episodes else "PASS_CLEAN"
    elif any(details[k]["contact_episodes"] for k in failed) or any(
            f.get("phase") == "carry" and f.get("leg") in REQUIRED_LEGS
            and details[f"L{f['leg']}"]["contact_episodes"] for f in failures):
        outcome = "BLOCKED_BY_CONTACT"
    else:
        outcome = "FAIL"
    return {"case_id": row["case_id"], "placement": row["cell"], "seed": row["seed"], "class": outcome,
            "first_failure": first_failure or row.get("first_failure") or (failures[0] if failures else None),
            "raw_first_failure": row.get("first_failure"),
            "failed_legs": failed, "legs": details, "hard_limit_chain": hard,
            "contact_episodes_whole_chain": len(episodes), "unclassified_reason": None,
            "unresolved_failure_records": failures,
            "handover": handover, "end_window": end_window, "unresolved_failure": unresolved,
            "completion_checks_skipped_for_hard_limit": confirmatory and hard["violated"],
            "confirmatory_evidence_checked": confirmatory}


def sigma_case(row, trace):
    out = {}
    legs = {l["leg"]: l for l in row["chain"]["legs"]}
    for k in REQUIRED_LEGS:
        leg = legs.get(k, {})
        reached = leg.get("recorded") is True
        out[f"L{k}"] = {"reached": reached, "signed": {
            r: ga.signed_error(trace, leg["end_sim_s"], r, PF_MAX_AGE_S) for r in ROBOTS} if reached else {}}
    return out


def summarize_sigma(cases):
    """B = AND of six leg/axis tests, primary 941 only; auxiliary 943 separate."""
    output = {"primary_seed": 941, "weighting": "two equal robot samples per reached primary placement/leg",
              "sample_max_age_s": PF_MAX_AGE_S, "secondary_seed_943": {}, "legs": {}}
    for seed, target in ((941, output["legs"]), (943, output["secondary_seed_943"])):
        members = [c for c in cases if c["seed"] == seed]
        for key in ("L0", "L1"):
            reached, unreached, missing, samples = [], [], [], []
            covered = [0, 0, 0]
            for c in members:
                leg = (c.get("sigma") or {}).get(key)
                if not leg:
                    missing.append(c["placement"])
                elif not leg["reached"]:
                    unreached.append(c["placement"])
                else:
                    sig = leg["signed"]
                    if any(sig.get(r) is None for r in ROBOTS):
                        missing.append(c["placement"])
                    else:
                        reached.append(c["placement"])
                        pair = [sig[r] for r in ROBOTS]
                        samples.extend(pair)
                        for j in range(3):
                            covered[j] += all(s["z2"][j] <= 4. for s in pair)
            n = len(samples)
            cov = [sum(s["z2"][j] <= 4. for s in samples) / n for j in range(3)] if n else None
            mean = [math.fsum(s["z2"][j] for s in samples) / n for j in range(3)] if n else None
            passed = [cov[j] >= .90 and mean[j] <= 1.3 for j in range(3)] if n else [False] * 3
            target[key] = {"n_samples": n, "n_observed_placements": len(reached),
                           "unreached_placements": unreached, "missing_pf_placements": missing,
                           "cov2sigma_samples_xyyaw": cov, "mean_z2_xyyaw": mean, "axis_pass_xyyaw": passed,
                           "covered_placements_xyyaw": covered,
                           "wilson95_placements_nominal": [ca.wilson(c, len(reached)) for c in covered] if reached else None,
                           "verdict": "NOT_EVALUABLE" if missing or not n else "PASS" if all(passed) else "FAIL"}
    verdicts = [l["verdict"] for l in output["legs"].values()]
    output["verdict"] = ("NOT_EVALUABLE" if "NOT_EVALUABLE" in verdicts
                         else "PASS" if all(v == "PASS" for v in verdicts) else "FAIL")
    return output


def value_hash(value):
    """Canonical hashes bind placement contents and PF prior, not just names."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def evidence_digest(row, result, trace):
    """Record-time completeness receipt; not authentication or a seal.

    Covers optional observations too, so deleting a sole GT violation cannot
    restore PASS. Duplicate row and execution identity are covered as well as
    checked against their independently supplied counterparts.
    The classifier only compares this value; it never repairs a stored receipt.
    """
    payload = {k: v for k, v in result.items() if k != "evidence_sha256"}
    return value_hash({"row": row, "result": payload, "trace": trace})


def load_sealed_manifest(path, expected_sha256):
    """Consume a coordinator-owned seal. This tool never creates or edits it."""
    path = Path(path).resolve()
    if not expected_sha256 or sha256(path) != expected_sha256:
        raise EvidenceError("sealed manifest hash mismatch or missing independently pinned hash")
    seal = json.loads(path.read_text())
    if seal.get("schema") == rv.REGISTERED_SCHEMA:
        source = Path(seal["placements"]["path"])
        source = source if source.is_absolute() else (ROOT if source.parts[0] == "experiments" else path.parent) / source
        pinned = seal["placements"]["sha256"]
        if sha256(source) != pinned:
            raise EvidenceError("registered placements hash mismatch")
        try:
            normalized = rv.normalize_registration(seal, json.loads(source.read_text()))
        except (KeyError, ValueError, TypeError) as error:
            raise EvidenceError("registered recorder contract: " + str(error)) from error
        normalized.update(_path=str(path), _sha256=expected_sha256, _input_hashes={str(source): pinned})
        return normalized
    if (seal.get("state") != "sealed" or seal.get("schema") != "ugrp.v6h_confirmatory.v1"
            or seal.get("primary_seed") != 941 or seal.get("secondary_seed") != 943):
        raise EvidenceError("require sealed v6h manifest with seeds 941/943")
    if seal.get("evaluation_protocol") != EVALUATION_PROTOCOL:
        raise EvidenceError("sealed evaluation protocol differs from implemented draft definition")
    identity = seal.get("execution_identity") or {}
    if (set(identity) != {"source_sha", "policy_id", "bundle_id", "source_files_sha256"}
            or not re.fullmatch(r"[0-9a-f]{40}", identity.get("source_sha", ""))
            or not identity.get("policy_id") or not identity.get("bundle_id")
            or not identity.get("source_files_sha256")):
        raise EvidenceError("sealed source/policy/bundle/file hashes required")
    for digest in identity["source_files_sha256"].values():
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise EvidenceError("invalid sealed source file hash")
    loaded = {}
    for kind in ("placements", "plan"):
        source = path.parent / seal[f"{kind}_file"]
        if sha256(source) != seal[f"{kind}_sha256"]:
            raise EvidenceError(f"sealed {kind} file hash mismatch")
        loaded[kind] = json.loads(source.read_text())
        seal.setdefault("_input_hashes", {})[str(source)] = seal[f"{kind}_sha256"]
    placements = loaded["placements"]
    if (len(placements) != 60 or [p["name"] for p in placements] != [f"C{k:02d}" for k in range(1, 61)]):
        raise EvidenceError("sealed placements must be ordered C01..C60")
    for placement in placements:
        for key in ("x", "y", "yaw_deg"):
            finite(placement.get(key), "placement " + key)
        if not placement.get("prior") or placement.get("sheet") != "coarse":
            raise EvidenceError("placement prior/coarse sheet required")
    expected = {(p["name"], seed) for p in placements for seed in ((941, 943) if int(p["name"][1:]) <= 12 else (941,))}
    entries = seal.get("cases") or []
    if len(entries) != 72 or {(e["placement"], e["seed"]) for e in entries} != expected:
        raise EvidenceError("sealed cases must match exactly 60+12 placement/seed pairs")
    if loaded["plan"].get("execution_identity") != identity:
        raise EvidenceError("sealed plan execution identity mismatch")
    specs = loaded["plan"]["cases"]
    spec_by_id = {s["case_id"]: s for s in specs}
    if len(specs) != 72 or len(spec_by_id) != 72:
        raise EvidenceError("sealed plan requires 72 unique original cases")
    attempts, selected = {}, {}
    by_name = {p["name"]: p for p in placements}
    for entry in entries:
        p = by_name[entry["placement"]]
        chain = entry.get("attempts") or []
        if len(chain) not in (1, 2) or "selected_attempt" in entry:
            raise EvidenceError("one original plus at most one predeclared HOST_ERROR retry; selection is runtime-only")
        for index, attempt in enumerate(chain):
            cid = attempt["case_id"]
            if cid in attempts or attempt.get("replaces") != (chain[0]["case_id"] if index else None):
                raise EvidenceError("duplicate attempt or missing original/retry link")
            original = spec_by_id.get(chain[0]["case_id"])
            if (not original or original.get("cell") != p["name"] or original.get("seed") != entry["seed"]
                    or original.get("beam_xyyaw") != [p["x"], p["y"], math.radians(p["yaw_deg"])]
                    or original.get("policy_id") != identity["policy_id"]
                    or original.get("source_sha") != identity["source_sha"]
                    or original.get("bundle_id") != identity["bundle_id"]
                    or original.get("prior_id") != p["prior"]
                    or original.get("chain_stop_leg") != 1 or original.get("coarse_order_sheet") is None
                    or entry.get("placement_sha256") != value_hash(p)
                    or entry.get("prior_sha256") != value_hash(original.get("prior"))
                    or not isinstance(original.get("prior"), dict) or set(original["prior"]) != set(ROBOTS)
                    or not re.fullmatch(r"[0-9a-f]{64}", attempt.get("case_sha256", ""))):
                raise EvidenceError("case/placement/prior/policy/plan mismatch")
            attempts[cid] = (entry, index)
        selected[chain[0]["case_id"]] = entry
    seal["_attempts"], seal["_originals"] = attempts, selected
    seal["_path"], seal["_sha256"] = str(path), expected_sha256
    seal["_plan_specs"] = spec_by_id
    return seal



def summarize(cases, primary_seed=941, sealed_manifest=None, safety_attempts=None):
    # Success/sigma use one selected attempt per placement/seed. Safety uses
    # every executed attempt, including replaced or unreplaced HOST_ERRORs.
    safety_attempts = cases if safety_attempts is None else safety_attempts
    hard_attempts = [c for c in safety_attempts if (c.get("hard_limit_chain") or {}).get("violated")]
    hard_placements = {c["placement"] for c in hard_attempts}
    grouped = defaultdict(list)
    for case in cases:
        grouped[case["placement"]].append(case)
    placements = []
    for name, members in sorted(grouped.items()):
        if len({c["seed"] for c in members}) != len(members):
            raise EvidenceError(f"{name}: duplicate placement/seed; split policies/cohorts before classifying")
        primary = next((c for c in members if c["seed"] == primary_seed), None)
        placements.append({"placement": name, "primary_seed": primary_seed,
                           "class": primary["class"] if primary else None,
                           "first_failure": primary["first_failure"] if primary else None,
                           "unclassified_reason": primary["unclassified_reason"] if primary else "missing_primary_seed",
                           "primary_case_id": primary["case_id"] if primary else None,
                           "hard_limit_any_seed": name in hard_placements,
                           "cases": sorted(members, key=lambda c: c["seed"])})
    classified = [p for p in placements if p["class"] is not None]
    counts = {name: sum(p["class"] == name for p in placements) for name in CLASSES}
    passed = sum(counts[name] for name in PASS)
    hard_cases = len(hard_attempts)
    unclassified = [c["case_id"] for c in cases if c["class"] is None]
    # A is a fixed 60-placement test, never scale 48/60 to a small dev cohort.
    expected = {(e["placement"], e["seed"]) for e in sealed_manifest["cases"]} if sealed_manifest else set()
    evaluable = (bool(sealed_manifest) and primary_seed == 941 and len(placements) == 60
                 and len(classified) == 60 and not unclassified and len(cases) == 72
                 and {(c["placement"], c["seed"]) for c in cases} == expected
                 and all(c.get("confirmatory_evidence_checked") for c in cases))
    rule_pass = passed >= 48 and hard_cases == 0
    if sealed_manifest and hard_cases:
        verdict = "FAIL_OBSERVED_CRITERION"
    elif evaluable:
        verdict = "PASS_OBSERVED_CRITERION" if rule_pass else "FAIL_OBSERVED_CRITERION"
    else:
        verdict = "NOT_EVALUABLE"
    summary = {"n_cases": len(cases), "n_attempts": sum(a.get("record_present", True) for a in safety_attempts),
               "n_adjudicated_attempt_slots": len(safety_attempts),
               "n_placements": len(placements), "n_classified_primary": len(classified),
               "primary_seed": primary_seed, "counts": counts, "pass_placements": passed,
               "wilson95_primary_classified": ca.wilson(passed, len(placements)) if placements and len(classified) == len(placements) else None,
               "unclassified_cases": unclassified,
               "unclassified_placements": [p["placement"] for p in placements if p["class"] is None],
               "hard_limit_chain_cases": hard_cases,
               "hard_limit_attempt_case_ids": sorted(c["case_id"] for c in hard_attempts),
               "hard_limit_chain_placements_any_seed": sum(p["hard_limit_any_seed"] for p in placements),
               "case_counts": dict(Counter(c["class"] for c in cases if c["class"] is not None)),
               "cases_pass": sum(c["class"] in PASS for c in cases),
               "placements_all_recorded_seeds_pass": sum(all(c["class"] in PASS for c in v) for v in grouped.values()),
               "placements_any_recorded_seed_pass": sum(any(c["class"] in PASS for c in v) for v in grouped.values()),
               "criterion": {"minimum_pass": 48, "required_placements": 60, "maximum_hard_limit_cases": 0,
                             "evaluable": evaluable, "verdict": verdict,
                             "mode": "confirmatory" if sealed_manifest else "historical_endpoints",
                             "scope": "Observed criterion A + whole-chain safety; see separate sigma_criterion_B in confirmatory mode."},
               "probability_observed_count_criterion_n60": {str(p): binomial_tail(p) for p in (.70, .75, .80, .85)}}
    return placements, summary


# The public adjudicator is total over admitted attempts. Low-level validators
# raise EvidenceError; only this boundary converts them to INVALID (unclassified).
# See CLASSIFY_NOTES.md for the schema, transition table and reference methods.
def require_object(value, keys, name):
    if not isinstance(value, dict) or not set(keys) <= value.keys():
        raise EvidenceError(f"{name}: require object fields {','.join(keys)}")
    return value


def validate_required_record(row, result):
    require_object(row, ("case_id", "cell", "seed", "stage", "chain", "wall_contact"), "row")
    if (not isinstance(row["case_id"], str) or not row["case_id"]
            or not isinstance(row["cell"], str) or not row["cell"]
            or type(row["seed"]) is not int or row["stage"] != "chain"):
        raise EvidenceError("row: invalid attempt identity/stage")
    chain = require_object(row["chain"], ("legs", "first_failure"), "chain")
    if not isinstance(chain["legs"], list) or not {0, 1} <= {l.get("leg") for l in chain["legs"] if isinstance(l, dict)}:
        raise EvidenceError("chain: require L0 and L1 evidence")
    # pair_chain_probe persists the entire planned route, including unstarted
    # L2..L7. These remain validated and safety-scanned; only L0/L1 define A.
    if "n_legs" in chain and (type(chain["n_legs"]) is not int or chain["n_legs"] < 2
            or {l.get("leg") for l in chain["legs"]} != set(range(chain["n_legs"]))):
        raise EvidenceError("chain: planned leg inventory mismatch")
    wall = require_object(row["wall_contact"],
        ("episodes", "max_penetration_m", "max_tilt_deg_stage", "hard_limits"), "stored safety summary")
    if type(wall["episodes"]) is not int or wall["episodes"] < 0:
        raise EvidenceError("stored safety summary: invalid episode count")
    for key, upper in (("max_penetration_m", math.inf), ("max_tilt_deg_stage", 180)):
        if not 0 <= finite(wall[key], "stored safety " + key) <= upper:
            raise EvidenceError("stored safety summary: invalid maximum")
    if wall["hard_limits"] != {"max_tilt_deg": 15., "max_penetration_m": .005}:
        raise EvidenceError("stored safety summary: wrong hard limits")
    require_object(result, ("wall_contact", "failures"), "result")
    missing_host_termination = "termination" not in result and bool(result.get("host_error"))
    failures = require_object(result["failures"], ROBOTS, "failures")
    if set(failures) != set(ROBOTS):
        raise EvidenceError("failures: require exactly r1/r2")
    for failure in [chain["first_failure"], row.get("first_failure"), *failures.values()]:
        if failure is not None:
            # pair_stage_probe's controller event and pair_chain_probe's
            # derived phase/code are two explicit schemas, not arbitrary dicts.
            require_object(failure, (), "failure")
            keys = ("phase", "code") if "phase" in failure or "code" in failure else ("reason", "robot_id", "sim_s")
            require_object(failure, keys, "failure")
            text_keys = ("phase", "code") if keys[0] == "phase" else ("reason",)
            if not all(isinstance(failure[k], str) and failure[k] for k in text_keys):
                raise EvidenceError("failure: require nonempty phase/code or controller reason")
            if keys[0] == "reason" and failure["robot_id"] not in (*ROBOTS, None):
                raise EvidenceError("failure: unknown robot")
            if failure.get("sim_s") is not None:
                t = finite(failure["sim_s"], "failure time")
                if t < 0 or (not missing_host_termination and t > finite(result["termination"].get("sim_s"), "termination time")):
                    raise EvidenceError("failure time outside record")
    if missing_host_termination:
        return  # real except-path stores host_error, not a fabricated termination
    term = require_object(result["termination"], ("outcome", "sim_s"), "termination")
    if not isinstance(term["outcome"], str) or not term["outcome"]:
        raise EvidenceError("termination: missing outcome")
    finite(term["sim_s"], "termination time")


def completed_handover_failure(chain, trace):
    """Negative handover evidence requires the reached, fully observed window.

    An unvisited future handover or a hole in its trace is not a task failure.
    Explicit teacher restaging is positive evidence, even after a host stop.
    """
    if chain.get("restaging_between_legs") is True:
        return True
    legs = {l["leg"]: l for l in chain["legs"]}
    if not legs.get(0, {}).get("recorded") or legs.get(1, {}).get("start_sim_s") is None:
        return False
    validate_leg(legs[0])
    if legs[1].get("recorded"):
        validate_leg(legs[1])
    finite(legs[1]["start_sim_s"], "handover L1 start")
    start, end = legs[0]["end_sim_s"], legs[1]["start_sim_s"]
    samples = [s for s in trace if start - TRACE_GAP_S <= finite(s.get("t"), "handover t") <= end + TRACE_GAP_S]
    if (not samples or end <= start or samples[0]["t"] > start + TRACE_GAP_S
            or samples[-1]["t"] < end - TRACE_GAP_S
            or any(b["t"] <= a["t"] or b["t"] - a["t"] > TRACE_GAP_S + 1e-9 for a, b in zip(samples, samples[1:]))):
        return False
    for sample in samples:
        finite(sample.get("lift_m"), "handover lift")
        finite(sample.get("tilt_deg"), "handover tilt")
        jaws_valid(sample.get("jaws"))
    checks = handover_checks(chain, samples)
    return not all(checks[k] for k in ("rest_release", "regrasp_lift"))


def confirmed_task_failure(row, result, trace=(), *, confirmatory=False):
    """Positive failure evidence survives a later host/cleanup status overwrite.

    An unrecorded leg on its own is not a confirmed failure during a host abort.
    Wrapper passed/outcome_class refer to destination setdown, outside this task.
    """
    for rec in (row, result.get("row")):
        if not isinstance(rec, dict):
            continue
        chain = rec.get("chain")
        if not isinstance(chain, dict):
            continue
        first = rec.get("first_failure")
        host_marker = isinstance(first, dict) and first.get("reason") == "HOST_ERROR" and "phase" not in first and "code" not in first
        if (first and not host_marker) or chain.get("first_failure"):
            return True
        if confirmatory:
            try:
                if completed_handover_failure(chain, trace):
                    return True
            except (EvidenceError, KeyError, TypeError, ValueError, AttributeError):
                pass  # incomplete evidence cannot establish a negative event
        for leg in chain.get("legs", []) if isinstance(chain.get("legs"), list) else []:
            if isinstance(leg, dict) and leg.get("recorded") is True:
                try:
                    validate_leg(leg)
                    if not all(ca.pcp.leg_checks(leg).values()):
                        return True
                except (EvidenceError, KeyError, TypeError, ValueError):
                    pass  # invalidity is handled by schema validation, never PASS
    failures = result.get("failures")
    if isinstance(failures, dict) and any(v is not None for v in failures.values()):
        return True
    term = result.get("termination")
    return isinstance(term, dict) and term.get("outcome") not in (None, "STUDY_LAYER_DONE", "HOST_ERROR")


def host_signal(row, result):
    return bool(row.get("host_error") or str(row.get("category", "")).startswith("HOST_ERROR")
                or result.get("host_error") or (isinstance(result.get("termination"), dict)
                                               and result["termination"].get("outcome") == "HOST_ERROR"))


def validate_source_to_derived(row, result):
    """Real producer copies the later robot endpoint GT without rounding.

    Compare lift/tilt/jaws only at the SAME GT time as the derived end. Earlier
    asynchronous robot snapshots remain separate safety witnesses. 1e-9 is
    numerical serialization tolerance, not the 0.05s trace sampling period.
    """
    row_host = bool(row.get("host_error") or str(row.get("category", "")).startswith("HOST_ERROR"))
    result_host = bool(result.get("host_error"))
    term = result.get("termination") or {}
    if result_host and not row_host:
        raise EvidenceError("HOST_ERROR result/row contradiction")
    if term.get("outcome") == "HOST_ERROR" and not row_host:
        raise EvidenceError("HOST_ERROR termination/row mismatch")
    if row_host and not result_host and term.get("outcome") != "HOST_ERROR":
        raise EvidenceError("HOST_ERROR row/termination mismatch")
    raw = result.get("chain_raw") or {}
    for leg in row["chain"]["legs"]:
        if not leg.get("recorded"):
            continue
        endpoints = [((raw.get(r) or {}).get("leg_end") or {}).get(str(leg["leg"])) for r in ROBOTS]
        if all(endpoints) and abs(max(finite(s.get("sim_s"), "source endpoint time") for s in endpoints) - leg["end_sim_s"]) > 1e-9:
            raise EvidenceError("endpoint source/derived timestamp contradiction")
        for rid in ROBOTS:
            snap = ((raw.get(rid) or {}).get("leg_end") or {}).get(str(leg["leg"]))
            if snap is None:
                continue
            gt = snap.get("gt")
            if gt is None:
                continue
            t = finite(gt.get("t"), "endpoint GT time")
            if abs(t - finite(snap.get("sim_s"), "endpoint time")) > 1e-9:
                raise EvidenceError("endpoint GT/source timestamp contradiction")
            if abs(t - leg["end_sim_s"]) <= 1e-9:
                for key in ("lift_m", "tilt_deg"):
                    if abs(finite(gt.get(key), "endpoint GT " + key) - leg[key]) > 1e-9:
                        raise EvidenceError("endpoint GT/derived " + key + " contradiction")
                if jaws_valid(gt.get("jaws")) != leg["jaws"]:
                    raise EvidenceError("endpoint GT/derived jaws contradiction")


def validate_record_consistency(row, result):
    """Match contact_outcome's persisted stage summary, including its rounding.

    The tilt maximum is sampled; asynchronous endpoint/GT maxima may exceed it
    and are separately unioned. Neither is substituted for the other.
    """
    stored = row["wall_contact"]
    if "max_tilt_deg" in result:
        if stored["max_tilt_deg_stage"] != finite(result["max_tilt_deg"], "result maximum tilt"):
            raise EvidenceError("stored safety summary differs from result maximum tilt")
    episodes = result["wall_contact"]["episodes"]
    start = result.get("submit_t")
    end = (result.get("gt_at_stop") or {}).get("t") or (result.get("termination") or {}).get("sim_s")
    if start is not None:
        finite(start, "submit time")
    if end is not None:
        finite(end, "summary end time")
    stage = [e for e in episodes if (start is None or e["t_last"] >= start - 1e-9)
             and (end is None or e["t_first"] <= end + 1e-9)]
    if (stored["episodes"] != len(stage)
            or stored["max_penetration_m"] != round(max((e["max_pen_m"] for e in stage), default=0.), 6)):
        raise EvidenceError("stored safety summary differs from stage contact episodes")


def adjudicate_attempt(row, result, trace, *, confirmatory=True, issues=(), recorder_context=None):
    """Validate first, then emit one of PASS/FAIL/HARD/INVALID/HOST_SAFE.

    Salvaging positive hard evidence is independent of validation. It can only
    veto success, never certify safety. Every validator error remains in output.
    """
    problems = list(issues)
    row = row if isinstance(row, dict) else {}
    result = result if isinstance(result, dict) else {}
    trace = trace if isinstance(trace, list) else []
    hard = observed_hard_limits(row, result, trace, partial=True)
    problems.extend(hard["evidence_issues"])
    host = host_signal(row, result)
    failed = confirmed_task_failure(row, result, trace, confirmatory=confirmatory)
    detail = {}
    recorder = None
    try:
        if recorder_context is not None:
            recorder = rv.adapt(row, result, trace, **recorder_context)
        validate_required_record(row, result)
        if confirmatory and (recorder is None or "evidence_sha256" in result) and (not isinstance(result.get("evidence_sha256"), str)
                or result["evidence_sha256"] != evidence_digest(row, result, trace)):
            problems.append("EVIDENCE_DIGEST_MISMATCH: missing or changed record-time receipt")
        # Coverage validation applies equally to HOST_ERROR and ordinary results.
        validate_trace(row, result, trace, confirmatory, recorder)
        # Structural/leg/contact validators are shared with historical arithmetic.
        detail = classify_case(row, result, trace, confirmatory=False)
        try:
            validate_record_consistency(row, result)
            validate_source_to_derived(row, result)
        except (EvidenceError, KeyError, TypeError, ValueError, AttributeError) as error:
            problems.append(str(error))
        if confirmatory and not host and not failed and not hard["violated"]:
            detail = classify_case(row, result, trace, confirmatory=True, recorder=recorder)
        if confirmatory:
            detail["sigma"] = sigma_case(row, trace)
            if any(leg["reached"] and any(leg["signed"].get(r) is None for r in ROBOTS)
                   for leg in detail["sigma"].values()):
                raise EvidenceError("reached endpoint missing valid PF evidence")
    except (EvidenceError, KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError) as error:
        problems.append(str(error))
    if hard["violated"]:
        state, outcome, reason = "HARD", "FAIL_HARD_LIMIT", "HARD_LIMIT_OBSERVED"
    elif problems:
        state, outcome, reason = "INVALID", None, "UNCLASSIFIABLE_RECORDER_FORMAT" if recorder_context is not None and recorder is None else "INVALID_EVIDENCE"
    elif failed:
        state, outcome, reason = "FAIL", detail.get("class", "FAIL"), "TASK_FAILURE"
        if outcome in PASS:
            outcome = "FAIL"
    elif host:
        state, outcome, reason = "HOST_SAFE", None, "HOST_ERROR_PENDING_RETRY"
    else:
        outcome = detail["class"]
        state, reason = ("PASS", "COMPLETE_PASS") if outcome in PASS else ("FAIL", "TASK_FAILURE")
    hard["evidence_issues"] = sorted(set(problems))
    return {**detail, "case_id": row.get("case_id"), "placement": row.get("cell"), "seed": row.get("seed"),
            "class": outcome, "state": state, "reason_code": reason, "host_error": host,
            "first_failure": detail.get("first_failure", row.get("first_failure")),
            "unclassified_reason": reason if outcome is None else None, "hard_limit_chain": hard,
            "classification_status": "UNCLASSIFIABLE" if reason == "UNCLASSIFIABLE_RECORDER_FORMAT" else "UNCLASSIFIED" if outcome is None else "CLASSIFIED",
            "recorder_contract": recorder,
            "confirmed_task_failure": failed, "evidence_valid": not problems,
            "confirmatory_evidence_checked": confirmatory and not problems}


# Explicit, total transition function: the only replaceable state is RETRY.
# HARD dominates even an invalid/unauthorized later attempt; FAIL and INVALID
# never become PASS. A second host abort exhausts the single preregistered retry.
TRANSITIONS = {
    "NEW":     dict(PASS="PASS", FAIL="FAIL", HARD="HARD", INVALID="INVALID", HOST_SAFE="RETRY"),
    "RETRY":   dict(PASS="PASS", FAIL="FAIL", HARD="HARD", INVALID="INVALID", HOST_SAFE="INVALID"),
    "PASS":    dict(PASS="INVALID", FAIL="INVALID", HARD="HARD", INVALID="INVALID", HOST_SAFE="INVALID"),
    "FAIL":    dict(PASS="FAIL", FAIL="FAIL", HARD="HARD", INVALID="FAIL", HOST_SAFE="FAIL"),
    "INVALID": dict(PASS="INVALID", FAIL="INVALID", HARD="HARD", INVALID="INVALID", HOST_SAFE="INVALID"),
    "HARD":    dict(PASS="HARD", FAIL="HARD", HARD="HARD", INVALID="HARD", HOST_SAFE="HARD"),
}


def classify_attempt_sequence(attempts):
    state, chosen, transitions, issues = "NEW", None, [], []
    for index, attempt in enumerate(attempts):
        event = attempt.get("state", "INVALID")
        if event not in TRANSITIONS[state]:
            event = "INVALID"
        old = state
        if old == "RETRY" and any(chosen.get(k) != attempt.get(k) for k in ("placement", "seed")):
            event = "HARD" if event == "HARD" else "INVALID"
            issues.append("RETRY_PLACEMENT_SEED_MISMATCH")
        if old == "RETRY" and chosen.get("recorder_contract") is not None:
            original_identity = chosen["recorder_contract"]["identity"]
            retry_identity = (attempt.get("recorder_contract") or {}).get("identity")
            if retry_identity != original_identity:
                event = "HARD" if event == "HARD" else "INVALID"
                issues.append("RETRY_RECORDED_IDENTITY_MISMATCH")
        if index and old != "RETRY":
            issues.append(f"RETRY_NOT_ALLOWED_AFTER_{old}:{attempt['case_id']}")
        state = TRANSITIONS[state][event]
        if chosen is None or old == "RETRY":
            chosen = attempt
        transitions.append({"case_id": attempt["case_id"], "from": old, "event": event, "to": state})
    if chosen is None:
        return {"case_id": None, "state": "INVALID", "class": None, "reason_code": "MISSING_ORIGINAL", "unclassified_reason": "missing_primary_seed",
                "invalid_evidence": True, "attempt_transitions": []}
    out = dict(chosen)
    out["state"] = state if state not in ("NEW", "RETRY") else "INVALID"
    if state == "HARD":
        out.update({"class": "FAIL_HARD_LIMIT", "reason_code": "HARD_LIMIT_OBSERVED", "unclassified_reason": None,
                    "classification_status": "CLASSIFIED"})
        hard = {"violated": True, "evidence_issues": sorted({issue for a in attempts
            for issue in a.get("hard_limit_chain", {}).get("evidence_issues", [])})}
        for key in ("max_tilt_deg", "max_pen_m"):
            values = [a.get("hard_limit_chain", {}).get(key) for a in attempts]
            hard[key] = max((v for v in values if v is not None), default=None)
        out["hard_limit_chain"] = hard
    elif state in ("INVALID", "NEW", "RETRY"):
        incompatible = out.get("classification_status") == "UNCLASSIFIABLE"
        out.update({"class": None, "reason_code": "HOST_ERROR_RETRY_EXHAUSTED" if state == "RETRY"
                    or (transitions and transitions[-1]["from"] == "RETRY" and transitions[-1]["event"] == "HOST_SAFE")
                    else "UNCLASSIFIABLE_RECORDER_FORMAT" if incompatible else "INVALID_ATTEMPT_SEQUENCE"})
        out["unclassified_reason"] = out["reason_code"]
        out["classification_status"] = "UNCLASSIFIABLE" if incompatible else "UNCLASSIFIED"
    out["attempt_transitions"] = transitions
    out["sequence_issues"] = issues
    out["invalid_evidence"] = bool(issues) or any(not a.get("evidence_valid", False) for a in attempts) or out["state"] == "INVALID"
    return out


class EvidenceReader:
    """Hash exact bytes, retain parseable observations, verify stable input set."""
    def __init__(self, raw):
        self.raw, self.hashes, self.missing = raw, {}, []
        self.unexecuted_paths = []

    def read(self, path, *, lines=False):
        name = str(path.relative_to(self.raw)) if path.is_relative_to(self.raw) else str(path)
        try:
            data = path.read_bytes()
        except OSError as error:
            self.missing.append(name)
            return ([] if lines else {}), [f"MISSING_EVIDENCE:{name}:{error.__class__.__name__}"]
        self.hashes[name] = hashlib.sha256(data).hexdigest()
        values, issues = [], []
        records = data.splitlines() if lines else [data]
        if not records:
            issues.append(f"EMPTY_EVIDENCE:{name}")
        for i, record in enumerate(records, 1):
            try:
                def pairs(items):
                    if len({k for k, _ in items}) != len(items):
                        issues.append(f"DUPLICATE_JSON_KEY:{name}:{i}")
                    return dict(items)

                def constant(value):
                    issues.append(f"NONFINITE_JSON_NUMBER:{name}:{i}")
                    return None

                value = json.loads(record, object_pairs_hook=pairs, parse_constant=constant)
                if not isinstance(value, dict):
                    raise ValueError("expected object")
                values.append(value)
            except (ValueError, UnicodeError, RecursionError) as error:
                issues.append(f"INVALID_JSON:{name}:{i}:{error.__class__.__name__}")
        return (values if lines else values[0] if values else {}), issues

    def verify(self):
        issues = []
        for name, digest in self.hashes.items():
            path = Path(name) if Path(name).is_absolute() else self.raw / name
            try:
                if sha256(path) != digest:
                    issues.append(f"INPUT_CHANGED:{name}")
            except OSError:
                issues.append(f"INPUT_CHANGED:{name}")
        issues.extend(f"INPUT_APPEARED:{name}" for name in self.missing if (self.raw / name).exists())
        issues.extend(f"INPUT_APPEARED:{path.relative_to(self.raw)}" for path in self.unexecuted_paths if path.exists())
        return issues


def analyse(label, raw, primary_seed=941, sealed_manifest=None):
    raw = Path(raw).resolve()
    reader = EvidenceReader(raw)
    for source in (Path(__file__).resolve(), RECORDER_PATH, CHAIN_PATH, SIGMA_PATH, Path(ca.pcp.__file__).resolve(), Path(ca.dra.__file__).resolve()):
        reader.hashes[str(source)] = sha256(source)
    rows, cohort_issues = reader.read(raw / "cases.jsonl", lines=True)
    manifest, problems = reader.read(raw / "manifest.json")
    cohort_issues += problems
    seal = sealed_manifest
    runtime_plan = {}
    if manifest.get("state") != "completed" or manifest.get("source_changed") is not False:
        cohort_issues.append("INVALID_MANIFEST: requires completed/source_changed=false")
    by_id = defaultdict(list)
    for row in rows:
        cid = row.get("case_id")
        if not isinstance(cid, str) or not cid:
            cohort_issues.append("INVALID_ATTEMPT_ID")
        else:
            by_id[cid].append(row)
    if seal:
        entries = seal["cases"]
        for name, expected_hash in {seal["_path"]: seal["_sha256"], **seal["_input_hashes"]}.items():
            try:
                reader.hashes[name] = sha256(Path(name))
                if reader.hashes[name] != expected_hash:
                    cohort_issues.append("CHANGED_SEALED_INPUT:" + name)
            except OSError:
                cohort_issues.append("MISSING_SEALED_INPUT:" + name)
        identity = seal.get("execution_identity")
        try:
            if "_registered" in seal:
                rv.source_identity(manifest)
                runtime_plan, errors = reader.read(raw / "plan.json")
                cohort_issues += errors
                if (manifest.get("cases") != len(runtime_plan["cases"])
                        or manifest.get("cases_sha256") != value_hash(runtime_plan["cases"])):
                    raise EvidenceError("registered runtime plan count/hash mismatch")
            else:
                inventory = manifest["source"]["execution_tree"]["files"]
                if (manifest.get("execution_identity") != identity or manifest["source"]["source_sha"] != identity["source_sha"]
                        or len(inventory) != len(identity["source_files_sha256"])
                        or {f["path"]: f["sha256"] for f in inventory} != identity["source_files_sha256"]):
                    raise EvidenceError("source inventory differs from seal")
        except (KeyError, TypeError, ValueError) as error:
            cohort_issues.append(f"INVALID_EXECUTION_IDENTITY:{error}")
        allowed = set(seal["_attempts"])
        if set(by_id) - allowed:
            cohort_issues.append("UNAUTHORIZED_ATTEMPT: only allowed retries are admitted")
    else:
        # Historical admissions come from the recorded plan, not successful rows.
        planned = manifest.get("cases")
        if type(planned) is int:
            plan, problems = reader.read(raw / "plan.json")
            cohort_issues += problems
            planned = plan.get("cases")
            if not isinstance(planned, list) or len(planned) != manifest["cases"]:
                cohort_issues.append("INVALID_HISTORICAL_ADMISSION_PLAN")
            elif value_hash(planned) != manifest.get("cases_sha256"):
                cohort_issues.append("INVALID_HISTORICAL_PLAN_HASH")
        planned = planned if isinstance(planned, list) and all(isinstance(c, dict) for c in planned) else []
        specs = {c["case_id"]: c for c in planned if isinstance(c.get("case_id"), str)}
        specs.update({cid: rs[0] for cid, rs in by_id.items() if cid not in specs})
        groups = defaultdict(list)
        for cid, spec in sorted(specs.items()):
            cell, seed = spec.get("cell"), spec.get("seed")
            if not isinstance(cell, str) or type(seed) is not int:
                cohort_issues.append("INVALID_ADMISSION_IDENTITY")
                cell, seed = "invalid:" + cid, primary_seed
            groups[(cell, seed)].append({"case_id": cid})
        entries = [{"placement": cell, "seed": seed, "attempts": attempts}
                   for (cell, seed), attempts in sorted(groups.items())]
        if any(len(e["attempts"]) > 1 for e in entries):
            cohort_issues.append("DUPLICATE_PLACEMENT_SEED_WITHOUT_RETRY_REGISTRATION")
        allowed = set(specs)
    attempts, cases = [], []
    for entry in entries:
        sequence = []
        for index, registered in enumerate(entry["attempts"]):
            cid = registered["case_id"]
            directory = ca.dra.case_dir(raw, cid)
            if index and cid not in by_id:
                artifacts = [directory / "result.json", directory / "eval_only/trace.jsonl"]
                if not any(path.exists() for path in artifacts):
                    reader.unexecuted_paths.extend(artifacts)
                    continue  # case.json alone only declares a permitted retry
                # Existing artifacts prove this slot cannot be called unexecuted.
                # The absent row is invalid, but its files can still prove HARD.
            candidates = by_id.get(cid, [])
            local_issues = list(cohort_issues)
            if len(candidates) != 1:
                local_issues.append("MISSING_OR_DUPLICATE_ATTEMPT")
            row = candidates[0] if candidates else {"case_id": cid, "cell": entry["placement"], "seed": entry["seed"]}
            result, problems = reader.read(directory / "result.json")
            local_issues += problems
            trace, problems = reader.read(directory / "eval_only/trace.jsonl", lines=True)
            local_issues += problems
            recorder_context = None
            if seal:
                spec_path = directory / "case.json"
                spec, problems = reader.read(spec_path)
                local_issues += problems
                original = seal["_plan_specs"][entry["attempts"][0]["case_id"]]
                if "_registered" in seal:
                    recorder_context = {"manifest": manifest, "case": spec, "registration": seal["_registered"]}
                    runtime_specs = [c for c in runtime_plan.get("cases", []) if c.get("case_id") == cid]
                    if len(runtime_specs) != 1 or {k: v for k, v in spec.items() if k != "labels"} != {
                            k: v for k, v in runtime_specs[0].items() if k != "labels"}:
                        local_issues.append("INVALID_CASE_IDENTITY: runtime plan/case mismatch")
                elif (reader.hashes.get(str(spec_path.relative_to(raw))) != registered["case_sha256"]
                        or spec.get("case_id") != cid or row.get("cell") != entry["placement"] or row.get("seed") != entry["seed"]
                        or {k: v for k, v in spec.items() if k != "case_id"} != {k: v for k, v in original.items() if k != "case_id"}):
                    local_issues.append("INVALID_CASE_IDENTITY: raw case hash/contents differ from sealed plan")
                if ("_registered" not in seal and result.get("execution_identity") != identity) or result.get("row") != row:
                    local_issues.append("INVALID_RESULT_IDENTITY: result identity/row differs from cases record")
            # Duplicate rows are invalid but cannot hide a positive hard observation.
            evidence = adjudicate_attempt(row, result, trace, confirmatory=bool(seal), issues=local_issues,
                                          recorder_context=recorder_context)
            for duplicate in candidates[1:]:
                extra = observed_hard_limits(duplicate, {}, [], partial=True)
                combined = evidence["hard_limit_chain"]
                combined["violated"] |= extra["violated"]
                combined["evidence_issues"] = sorted(set(combined["evidence_issues"] + extra["evidence_issues"]))
                for key in ("max_tilt_deg", "max_pen_m"):
                    values = [v for v in (combined[key], extra[key]) if v is not None]
                    combined[key] = max(values) if values else None
                if combined["violated"]:
                    evidence.update(state="HARD", reason_code="HARD_LIMIT_OBSERVED", **{"class": "FAIL_HARD_LIMIT"})
            evidence.update(placement=entry["placement"], seed=entry["seed"], selected=False, record_present=bool(candidates))
            sequence.append(evidence)
            attempts.append(evidence)
        case = classify_attempt_sequence(sequence)
        for attempt in sequence:
            attempt["selected"] = attempt["case_id"] == case["case_id"]
        cases.append(case)
    # Extra rows never enter the denominator, but their evidence must veto safety.
    for cid in sorted(set(by_id) - allowed):
        directory = ca.dra.case_dir(raw, cid)
        result, ri = reader.read(directory / "result.json")
        trace, ti = reader.read(directory / "eval_only/trace.jsonl", lines=True)
        for row in by_id[cid]:
            extra = adjudicate_attempt(row, result, trace, issues=ri + ti + ["UNAUTHORIZED_ATTEMPT"])
            if not isinstance(extra["placement"], str):
                extra["placement"] = "unregistered:" + cid
            extra["selected"] = False
            attempts.append(extra)
    cohort_issues += reader.verify()
    if cohort_issues:
        for case in cases:
            case["invalid_evidence"] = True
            if case["class"] != "FAIL_HARD_LIMIT":
                case.update({"class": None, "state": "INVALID", "reason_code": "INVALID_COHORT_EVIDENCE",
                             "unclassified_reason": "INVALID_COHORT_EVIDENCE", "classification_status": "UNCLASSIFIED"})
    placements, summary = summarize(cases, primary_seed, seal, attempts)
    summary["admitted_placement_count"] = len({e["placement"] for e in entries})
    summary["denominator"] = summary["n_placements"]
    summary["invalid_cases"] = [c["case_id"] for c in cases if c["invalid_evidence"]]
    summary["cohort_evidence_issues"] = sorted(set(cohort_issues))
    if cohort_issues:
        summary["criterion"]["evidence_blocker"] = "; ".join(sorted(set(cohort_issues)))
    summary["safety_evidence_issues"] = {a["case_id"]: a["hard_limit_chain"]["evidence_issues"]
        for a in attempts if a["hard_limit_chain"]["evidence_issues"]}
    if seal:
        summary["sigma_criterion_B"] = summarize_sigma(cases)
        summary["attempt_case_ids"] = sorted(a["case_id"] for a in attempts)
        summary["selected_case_ids"] = [c["case_id"] for c in cases]
        invalid = bool(summary["invalid_cases"] or cohort_issues)
        if invalid:
            summary["criterion"].update(evaluable=False, verdict="FAIL_OBSERVED_CRITERION" if summary["hard_limit_chain_cases"] else "NOT_EVALUABLE")
        summary["full_verdict"] = ("PASS_A_B_SAFETY" if not invalid and not summary["hard_limit_chain_cases"]
            and summary["criterion"]["verdict"] == "PASS_OBSERVED_CRITERION"
            and summary["sigma_criterion_B"]["verdict"] == "PASS" else
            "FAIL_A_B_SAFETY" if summary["hard_limit_chain_cases"] or summary["criterion"]["verdict"] == "FAIL_OBSERVED_CRITERION"
            or summary["sigma_criterion_B"]["verdict"] == "FAIL" else "NOT_EVALUABLE")
    return {"schema": "ugrp.v6h_placement_classification.draft.v4", "label": label, "raw": str(raw),
            "source_sha": (manifest.get("source") if isinstance(manifest.get("source"), dict) else {}).get("source_sha"), "manifest_state": manifest.get("state"),
            "source_changed": manifest.get("source_changed"), "input_sha256": reader.hashes,
            "attempts": attempts, "missing_host_evidence": reader.missing,
            "interpretations": "Fail-closed draft v4; unresolved/invalid is unclassified. See CLASSIFY_NOTES.md.",
            "placements": placements, "summary": summary}


def report_text(report):
    s = report["summary"]
    lines = [f"== {report['label']}: {report['raw']}",
             "DRAFT / eval-only; 고정 60곳의 관측 통과율 기준이며 모집단 80 %를 입증하지 않는다.",
             f"Primary seed={s['primary_seed']}; selected cases={s['n_cases']}; attempts={s['n_attempts']}; placements={s['n_placements']}; classified primary={s['n_classified_primary']}",
             "placement | primary class | first failure phase/code | per-seed classes | hard any seed"]
    for p in report["placements"]:
        ff = p["first_failure"] or {}
        members = ", ".join(f"{c['seed']}:{c['class'] or c['unclassified_reason']}" for c in p["cases"])
        lines.append(f"{p['placement']} | {p['class'] or p['unclassified_reason']} | {ff.get('phase', '-')}/{ff.get('code', '-')} | {members} | {p['hard_limit_any_seed']}")
    lines += [f"Primary counts: {json.dumps(s['counts'])}",
             f"Primary pass: {s['pass_placements']}/{s['n_placements']} admitted; classified primary={s['n_classified_primary']}"]
    if s["wilson95_primary_classified"]:
        lo, hi = s["wilson95_primary_classified"]
        lines.append(f"Wilson 95% (all admitted placements; unclassified reported separately): {100 * lo:.2f}-{100 * hi:.2f}%")
    lines += [f"Selected cases pass: {s['cases_pass']}/{s['n_cases']}; placements all/any recorded seeds pass: "
              f"{s['placements_all_recorded_seeds_pass']}/{s['placements_any_recorded_seed_pass']}",
              f"Whole-chain hard limits: {s['hard_limit_chain_cases']} attempts, {s['hard_limit_chain_placements_any_seed']} placements (all seeds and HOST_ERROR attempts)",
              f"Hard-limit attempt IDs: {s['hard_limit_attempt_case_ids']}; safety evidence issues: {s['safety_evidence_issues']}",
              f"Unclassified primary placements: {s['unclassified_placements']}; unclassified cases: {s['unclassified_cases']}",
              f"Observed criterion: >=48/60 AND zero whole-chain hard violations; {s['criterion']['verdict']}",
              (f"Sigma B: {s['sigma_criterion_B']['verdict']}; full: {s['full_verdict']}" if "sigma_criterion_B" in s
               else "Sigma criterion B NOT evaluated in historical mode; this is not the prereg's full success declaration."),
              "P(X>=48 | n=60, true pass rate), count criterion only (no safety/sigma probability):"]
    lines += [f"  p={p}: {prob:.9f}" for p, prob in s["probability_observed_count_criterion_n60"].items()]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new directory for per-cohort JSON/TXT (never overwrite)")
    parser.add_argument("--primary-seed", type=int, default=941)
    parser.add_argument("--sealed-manifest", type=Path, help="existing coordinator-owned manifest; required for confirmatory A/B")
    parser.add_argument("--sealed-manifest-sha256", help="independently pinned SHA-256 of that manifest")
    parser.add_argument("raws", nargs="+", help="LABEL=/absolute/cohort-directory")
    args = parser.parse_args(argv)
    specs = [spec.partition("=") for spec in args.raws]
    labels = [label for label, _, _ in specs]
    if len(set(labels)) != len(labels) or any(not sep or not path or not re.fullmatch(r"[A-Za-z0-9_-]+", label) for label, sep, path in specs):
        parser.error("use unique safe LABEL=PATH arguments")
    if args.output.exists():
        parser.error("output directory already exists; choose a new path to preserve previous evidence")
    if any(args.output.resolve().is_relative_to(Path(path).resolve()) for _, _, path in specs):
        parser.error("output must be outside read-only raw cohort directories")
    try:
        if bool(args.sealed_manifest) != bool(args.sealed_manifest_sha256):
            raise EvidenceError("supply both sealed manifest and its pinned hash")
        seal = load_sealed_manifest(args.sealed_manifest, args.sealed_manifest_sha256) if args.sealed_manifest else None
        reports = [analyse(label, Path(path), args.primary_seed, seal) for label, _, path in specs]
    except (EvidenceError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.exit(2, f"incomplete/invalid evidence: {error}\n")
    args.output.mkdir(parents=True)
    for report in reports:
        text = report_text(report)
        (args.output / f"{report['label']}.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        (args.output / f"{report['label']}.txt").write_text(text)
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
