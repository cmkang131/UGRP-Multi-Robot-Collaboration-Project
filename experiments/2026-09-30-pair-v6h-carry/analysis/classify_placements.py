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
                       "L1_stop": "first_wait_lower_both_robots"}


class EvidenceError(ValueError):
    """Incomplete or ambiguous raw evidence must not produce a clean pass."""


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
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


def validate_trace(row, result, trace, confirmatory):
    times = [finite(s.get("t"), "trace t") for s in trace]
    if any(b <= a or b - a > TRACE_GAP_S + 1e-9 for a, b in zip(times, times[1:])):
        raise EvidenceError("trace: unordered times or missing samples (gap > .051 SIM s)")
    for sample in trace:
        tilt = finite(sample.get("tilt_deg"), "trace tilt_deg")
        if not 0 <= tilt <= 180:
            raise EvidenceError("trace tilt outside [0,180]")
    boundaries = [finite(l[key], key) for l in row["chain"]["legs"]
                  for key in ("start_sim_s", "end_sim_s") if l.get(key) is not None]
    if row.get("stop_sim_s") is not None:
        boundaries.append(finite(row["stop_sim_s"], "stop_sim_s"))
    if not boundaries or times[0] > min(boundaries) + TRACE_GAP_S or times[-1] < max(boundaries) - TRACE_GAP_S:
        raise EvidenceError("trace: truncated execution window")
    if not confirmatory:
        return
    coverage = result.get("evaluation_coverage") or {}
    start = finite(coverage.get("start_sim_s"), "record start")
    end = finite(coverage.get("end_sim_s"), "record end")
    termination = finite((result.get("termination") or {}).get("sim_s"), "termination time")
    if (abs(end - termination) > 1e-9 or start < 0 or end <= start or abs(times[0] - start) > TRACE_GAP_S or abs(times[-1] - end) > TRACE_GAP_S
            or coverage.get("trace_count") != len(trace) or min(boundaries) < start - TRACE_GAP_S
            or max(boundaries) > end + TRACE_GAP_S):
        raise EvidenceError("trace: full-record coverage/count mismatch")
    wall = (result.get("wall_contact") or {}).get("coverage") or {}
    for key in ("start_sim_s", "end_sim_s", "max_gap_s", "sample_period_s"):
        finite(wall.get(key), "wall coverage " + key)
    period = wall["sample_period_s"]
    count = wall.get("sample_count")
    if (period <= 0 or period > TRACE_GAP_S or not 0 <= wall["max_gap_s"] <= period + 1e-9
            or type(count) is not int or count < math.floor((end - start) / period)
            or wall["start_sim_s"] > start + period or wall["end_sim_s"] < end - period):
        raise EvidenceError("wall-contact: incomplete full-record coverage")
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
    if not all(legs.get(k, {}).get("recorded") for k in REQUIRED_LEGS):
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


def classify_case(row, result, trace, confirmatory=False):
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
    validate_trace(row, result, trace, confirmatory)
    all_tilt = max(sample["tilt_deg"] for sample in trace)
    # ca.analyse's hard_limit_chain uses ALL trace samples and ALL episodes,
    # including lower/open/regrasp and any additional recorded legs. Reuse its
    # shared predicate, not the leg-only classes or a copy of the thresholds.
    hard = {"violated": ca.hard_limit_violated(episodes, all_tilt),
            "max_tilt_deg": all_tilt, "max_pen_m": max((e["max_pen_m"] for e in episodes), default=0.)}
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
    handover = handover_checks(chain, trace) if confirmatory else None
    end_window = validate_end_window(row, result, by_leg) if confirmatory else None
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


def load_sealed_manifest(path, expected_sha256):
    """Consume a coordinator-owned seal. This tool never creates or edits it."""
    path = Path(path).resolve()
    if not expected_sha256 or sha256(path) != expected_sha256:
        raise EvidenceError("sealed manifest hash mismatch or missing independently pinned hash")
    seal = json.loads(path.read_text())
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


def select_confirmatory_rows(rows, raw, manifest, seal):
    if (manifest.get("execution_identity") != seal["execution_identity"]
            or manifest.get("state") != "completed" or manifest.get("source_changed") is not False
            or manifest.get("source", {}).get("source_sha") != seal["execution_identity"]["source_sha"]):
        raise EvidenceError("completed raw source/policy/bundle identity differs from seal")
    inventory = (manifest.get("source", {}).get("execution_tree") or {}).get("files", [])
    if {f["path"]: f["sha256"] for f in inventory} != seal["execution_identity"]["source_files_sha256"]:
        raise EvidenceError("recorded execution file hashes differ from sealed source inventory")
    ids = {r["case_id"] for r in rows}
    if len(ids) != len(rows) or not set(seal["_originals"]) <= ids or not ids <= set(seal["_attempts"]):
        raise EvidenceError("raw cases must match all 72 sealed originals and only allowed retries")
    by_id = {r["case_id"]: r for r in rows}
    selected = []
    for row in rows:
        entry, index = seal["_attempts"][row["case_id"]]
        attempt = entry["attempts"][index]
        spec = ca.dra.case_dir(raw, row["case_id"]) / "case.json"
        case = json.loads(spec.read_text())
        original = seal["_plan_specs"][entry["attempts"][0]["case_id"]]
        if (row.get("cell") != entry["placement"] or row.get("seed") != entry["seed"]
                or sha256(spec) != attempt["case_sha256"]
                or {k: v for k, v in case.items() if k != "case_id"} != {k: v for k, v in original.items() if k != "case_id"}
                or case["case_id"] != row["case_id"]):
            raise EvidenceError("raw case hash/contents differ from sealed plan")
        if index:
            original_row = by_id[entry["attempts"][0]["case_id"]]
            if not (original_row.get("host_error") or str(original_row.get("category", "")).startswith("HOST_ERROR")):
                raise EvidenceError("only HOST_ERROR may be replaced (never retry controller failure)")
        if index or not any(a["case_id"] in ids for a in entry["attempts"][1:]):
            selected.append(row)
    return selected


def summarize(cases, primary_seed=941, sealed_manifest=None):
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
                           "hard_limit_any_seed": any((c.get("hard_limit_chain") or {}).get("violated") for c in members),
                           "cases": sorted(members, key=lambda c: c["seed"])})
    classified = [p for p in placements if p["class"] is not None]
    counts = {name: sum(p["class"] == name for p in placements) for name in CLASSES}
    passed = sum(counts[name] for name in PASS)
    hard_cases = sum((c.get("hard_limit_chain") or {}).get("violated", False) for c in cases)
    unclassified = [c["case_id"] for c in cases if c["class"] is None]
    # A is a fixed 60-placement test, never scale 48/60 to a small dev cohort.
    expected = {(e["placement"], e["seed"]) for e in sealed_manifest["cases"]} if sealed_manifest else set()
    evaluable = (bool(sealed_manifest) and primary_seed == 941 and len(placements) == 60
                 and len(classified) == 60 and not unclassified and len(cases) == 72
                 and {(c["placement"], c["seed"]) for c in cases} == expected
                 and all(c.get("confirmatory_evidence_checked") for c in cases))
    rule_pass = passed >= 48 and hard_cases == 0
    verdict = ("PASS_OBSERVED_CRITERION" if rule_pass else "FAIL_OBSERVED_CRITERION") if evaluable else "NOT_EVALUABLE"
    summary = {"n_cases": len(cases), "n_placements": len(placements), "n_classified_primary": len(classified),
               "primary_seed": primary_seed, "counts": counts, "pass_placements": passed,
               "wilson95_primary_classified": ca.wilson(passed, len(classified)) if classified else None,
               "unclassified_cases": unclassified,
               "unclassified_placements": [p["placement"] for p in placements if p["class"] is None],
               "hard_limit_chain_cases": hard_cases,
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


def analyse(label, raw, primary_seed=941, sealed_manifest=None):
    raw = Path(raw).resolve()
    cases_path, manifest_path = raw / "cases.jsonl", raw / "manifest.json"
    initial_hash = sha256(cases_path)
    manifest_hash = sha256(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    cases = []
    inputs = {"cases.jsonl": initial_hash, "manifest.json": manifest_hash, "chain_analysis.py": sha256(CHAIN_PATH), str(SIGMA_PATH): sha256(SIGMA_PATH)}
    for path in (Path(__file__).resolve(), Path(ca.pcp.__file__).resolve(), Path(ca.dra.__file__).resolve()):
        inputs[str(path)] = sha256(path)
    rows = [json.loads(line) for line in cases_path.read_text().splitlines() if line.strip()]
    attempt_ids = [r["case_id"] for r in rows]
    if sealed_manifest:
        inputs[sealed_manifest["_path"]] = sealed_manifest["_sha256"]
        inputs.update(sealed_manifest["_input_hashes"])
        for r in rows:
            path = ca.dra.case_dir(raw, r["case_id"]) / "case.json"
            inputs[str(path.relative_to(raw))] = sha256(path)
        rows = select_confirmatory_rows(rows, raw, manifest, sealed_manifest)
    for row in rows:
        if row.get("stage") != "chain":
            raise EvidenceError(f"{row['case_id']}: not a chain cohort (single-leg probes are outside this classifier)")
        category = str(row.get("category") or "")
        if row.get("host_error") or category.startswith("HOST_ERROR"):
            cases.append({"case_id": row["case_id"], "placement": row["cell"], "seed": row["seed"], "class": None,
                          "first_failure": row.get("first_failure"), "hard_limit_chain": None,
                          "unclassified_reason": row.get("host_error") or category})
            continue
        directory = ca.dra.case_dir(raw, row["case_id"])
        result_path, trace_path = directory / "result.json", directory / "eval_only/trace.jsonl"
        for path in (result_path, trace_path):
            inputs[str(path.relative_to(raw))] = sha256(path)
        # Full eval fields are needed for handover and the separate sigma gate.
        result = json.loads(result_path.read_text())
        if sealed_manifest and (result.get("execution_identity") != sealed_manifest["execution_identity"]
                or result.get("row") != row):
            raise EvidenceError("result identity/row differs from sealed execution and cases record")
        trace = []
        with trace_path.open() as traces:
            for sample_line in traces:
                sample = json.loads(sample_line)
                trace.append(sample)
        case = classify_case(row, result, trace, confirmatory=bool(sealed_manifest))
        if sealed_manifest:
            case["sigma"] = sigma_case(row, trace)
        cases.append(case)
    if sha256(cases_path) != initial_hash:
        raise EvidenceError("cases.jsonl changed during analysis; retry only on a stable cohort")
    for name, digest in inputs.items():
        path = Path(name) if Path(name).is_absolute() else (CHAIN_PATH if name == "chain_analysis.py" else raw / name)
        if sha256(path) != digest:
            raise EvidenceError(f"input changed during analysis: {path}")
    placements, summary = summarize(cases, primary_seed, sealed_manifest)
    if sealed_manifest:
        summary["sigma_criterion_B"] = summarize_sigma(cases)
        summary["attempt_case_ids"] = attempt_ids
        summary["selected_case_ids"] = [c["case_id"] for c in cases]
        av = summary["criterion"]["verdict"]
        bv = summary["sigma_criterion_B"]["verdict"]
        summary["full_verdict"] = ("NOT_EVALUABLE" if "NOT_EVALUABLE" in (av, bv)
            else "PASS_A_B_SAFETY" if av == "PASS_OBSERVED_CRITERION" and bv == "PASS" else "FAIL_A_B_SAFETY")
    if manifest.get("state") != "completed" or manifest.get("source_changed") is not False:
        summary["criterion"].update(evaluable=False, verdict="NOT_EVALUABLE")
        summary["criterion"]["evidence_blocker"] = "manifest must be completed with source_changed=false"
    return {"schema": "ugrp.v6h_placement_classification.draft.v2", "label": label, "raw": str(raw),
            "source_sha": manifest.get("source", {}).get("source_sha"), "manifest_state": manifest.get("state"),
            "source_changed": manifest.get("source_changed"), "input_sha256": inputs,
            "interpretations": "Provisional pre-seal interpretations in analysis/CLASSIFY_NOTES.md; not an approved preregistration.",
            "placements": placements, "summary": summary}


def report_text(report):
    s = report["summary"]
    lines = [f"== {report['label']}: {report['raw']}",
             "DRAFT / eval-only; 고정 60곳의 관측 통과율 기준이며 모집단 80 %를 입증하지 않는다.",
             f"Primary seed={s['primary_seed']}; cases={s['n_cases']}; placements={s['n_placements']}; classified primary={s['n_classified_primary']}",
             "placement | primary class | first failure phase/code | per-seed classes | hard any seed"]
    for p in report["placements"]:
        ff = p["first_failure"] or {}
        members = ", ".join(f"{c['seed']}:{c['class'] or c['unclassified_reason']}" for c in p["cases"])
        lines.append(f"{p['placement']} | {p['class'] or p['unclassified_reason']} | {ff.get('phase', '-')}/{ff.get('code', '-')} | {members} | {p['hard_limit_any_seed']}")
    lines += [f"Primary counts: {json.dumps(s['counts'])}",
              f"Primary pass: {s['pass_placements']}/{s['n_classified_primary']} classified; total placements={s['n_placements']}"]
    if s["wilson95_primary_classified"]:
        lo, hi = s["wilson95_primary_classified"]
        lines.append(f"Wilson 95% (classified primary placements only): {100 * lo:.2f}-{100 * hi:.2f}%")
    lines += [f"All recorded cases pass: {s['cases_pass']}/{s['n_cases']}; placements all/any recorded seeds pass: "
              f"{s['placements_all_recorded_seeds_pass']}/{s['placements_any_recorded_seed_pass']}",
              f"Whole-chain hard limits: {s['hard_limit_chain_cases']} cases, {s['hard_limit_chain_placements_any_seed']} placements (all seeds)",
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
