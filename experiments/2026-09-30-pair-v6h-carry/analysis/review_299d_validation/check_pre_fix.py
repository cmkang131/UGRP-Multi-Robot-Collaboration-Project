#!/usr/bin/env python3
"""Run the former 13 review witnesses on the archived PR and pre-fix classifier.

Uses checked-in public fixtures and temporary synthetic cohorts only. No raw
lookup, simulation, network, source edits, or hidden cohort access.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import types


def load(path):
    spec = importlib.util.spec_from_file_location("review_299d_witnesses", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", required=True, type=Path, help="58dc07e7 archive directory")
    parser.add_argument("--repo", required=True, type=Path, help="read-only Git history source")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a new output file")
    relative = "experiments/2026-09-30-pair-v6h-carry/analysis/classify_placements.py"
    review = load(args.tree / "tests/test_classify_review_299c.py")
    current = review.cp
    code = subprocess.check_output(["git", "show", "f32d5fd9:" + relative], cwd=args.repo, text=True)
    pre = types.ModuleType("pre_fix")
    pre.__file__ = str(args.tree / relative)
    exec(compile(code, "f32d5fd9_classifier", "exec"), pre.__dict__)
    original = pre.adjudicate_attempt

    # API compatibility only: ignore the new consumer-adapter keyword on the
    # old API. The old adjudicator body is unchanged. A TypeError is not a kill.
    def compatible(*positional, recorder_context=None, **keyword):
        return original(*positional, **keyword)
    pre.adjudicate_attempt = compatible
    results = []
    for sha, module in (("58dc07e7", current), ("f32d5fd9", pre)):
        review.cp = review.base.cp = module
        jobs = []
        for kind in ("no_release", "no_regrasp", "restaging"):
            jobs.append(("R3_" + kind, lambda p, k=kind:
                         review.test_cleanup_host_cannot_replace_completed_handover_failure(p, k)))
        for kind in ("result_host_error", "endpoint_gt", "missing_teacher_prefix", "impossible_contact_coverage"):
            jobs.append(("R4R5_" + kind, lambda p, k=kind:
                         review.test_contradictory_evidence_cannot_pass_entire_cohort(p, k)))
        for missing in (False, True):
            jobs.append(("R2_missing_trace_" + str(missing), lambda p, k=missing:
                         review.test_unresolved_host_is_unclassified_under_registered_rule(k)))
        for field in ("result.evidence_sha256", "result.execution_identity", "result.evaluation_coverage",
                      "result.wall_contact.coverage"):
            jobs.append(("R1_" + field, lambda p, k=field:
                         review.test_classifier_accepts_registered_recorder_format(k)))
        for name, test in jobs:
            with tempfile.TemporaryDirectory(prefix="review299d-pre-") as folder:
                try:
                    test(Path(folder))
                except AssertionError:
                    outcome = "assertion_failed"
                else:
                    outcome = "passed"
                results.append({"code": sha, "test": name, "outcome": outcome})
    assert sum(r["outcome"] == "passed" for r in results if r["code"] == "58dc07e7") == 13, results
    assert sum(r["outcome"] == "assertion_failed" for r in results if r["code"] == "f32d5fd9") == 13, results
    args.output.write_text(json.dumps({"results": results, "current_pass": 13, "pre_fix_assertion_fail": 13,
        "shim": "Ignore recorder_context on old API; original classifier body unchanged",
        "unexpected_exceptions": 0}, indent=2) + "\n")
    print("current 13 PASS; pre-fix 13 AssertionError; unexpected exceptions 0")


if __name__ == "__main__":
    main()
