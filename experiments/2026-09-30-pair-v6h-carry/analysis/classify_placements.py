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

CLASSES = ("PASS_CLEAN", "PASS_CONTACT_RECOVERED", "BLOCKED_BY_CONTACT", "FAIL", "FAIL_HARD_LIMIT")
PASS = CLASSES[:2]
REQUIRED_LEGS = (0, 1)


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


def classify_case(row, result, trace):
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
    for sample in trace:
        finite(sample.get("t"), "trace t")
        finite(sample.get("tilt_deg"), "trace tilt_deg")
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
        if k in by_leg:
            raise EvidenceError(f"duplicate leg {k}")
        by_leg[k] = leg
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
    if hard["violated"]:
        outcome = "FAIL_HARD_LIMIT"
    elif not failed:
        outcome = "PASS_CONTACT_RECOVERED" if episodes else "PASS_CLEAN"
    elif any(details[k]["contact_episodes"] for k in failed):
        outcome = "BLOCKED_BY_CONTACT"
    else:
        outcome = "FAIL"
    return {"case_id": row["case_id"], "placement": row["cell"], "seed": row["seed"], "class": outcome,
            "first_failure": first_failure, "raw_first_failure": row.get("first_failure"),
            "failed_legs": failed, "legs": details, "hard_limit_chain": hard,
            "contact_episodes_whole_chain": len(episodes), "unclassified_reason": None}


def summarize(cases, primary_seed=941):
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
    evaluable = len(placements) == 60 and len(classified) == 60 and not unclassified
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
                             "scope": "Observed pass criterion A + whole-chain safety veto only; sigma criterion B is NOT evaluated."},
               "probability_observed_count_criterion_n60": {str(p): binomial_tail(p) for p in (.70, .75, .80, .85)}}
    return placements, summary


def analyse(label, raw, primary_seed=941):
    raw = Path(raw).resolve()
    cases_path, manifest_path = raw / "cases.jsonl", raw / "manifest.json"
    initial_hash = sha256(cases_path)
    manifest = json.loads(manifest_path.read_text())
    cases = []
    inputs = {"cases.jsonl": initial_hash, "manifest.json": sha256(manifest_path), "chain_analysis.py": sha256(CHAIN_PATH)}
    with cases_path.open() as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
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
            # Keep only t/tilt; full image/PF/geometry records are not needed here.
            result = json.loads(result_path.read_text())
            trace = []
            with trace_path.open() as traces:
                for sample_line in traces:
                    sample = json.loads(sample_line)
                    trace.append({"t": sample.get("t"), "tilt_deg": sample.get("tilt_deg")})
            cases.append(classify_case(row, result, trace))
            for path in (result_path, trace_path):
                inputs[str(path.relative_to(raw))] = sha256(path)
    if sha256(cases_path) != initial_hash:
        raise EvidenceError("cases.jsonl changed during analysis; retry only on a stable cohort")
    placements, summary = summarize(cases, primary_seed)
    if manifest.get("state") != "completed" or manifest.get("source_changed") is not False:
        summary["criterion"].update(evaluable=False, verdict="NOT_EVALUABLE")
        summary["criterion"]["evidence_blocker"] = "manifest must be completed with source_changed=false"
    return {"schema": "ugrp.v6h_placement_classification.draft.v1", "label": label, "raw": str(raw),
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
              "Sigma criterion B NOT evaluated; this is not the prereg's full success declaration.",
              "P(X>=48 | n=60, true pass rate), count criterion only (no safety/sigma probability):"]
    lines += [f"  p={p}: {prob:.9f}" for p, prob in s["probability_observed_count_criterion_n60"].items()]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new directory for per-cohort JSON/TXT (never overwrite)")
    parser.add_argument("--primary-seed", type=int, default=941)
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
        reports = [analyse(label, Path(path), args.primary_seed) for label, _, path in specs]
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
