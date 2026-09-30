#!/usr/bin/env python3
"""Remove chronology guards in memory; only verdict assertions kill mutants.

Inputs are public golden projections or fresh synthetic records. No simulator,
raw discovery, source edits, or extraction directories are used.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SPEC = importlib.util.spec_from_file_location("mutation_299g_tests", ROOT / "tests/test_classify_review_299g.py")
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be new")
    cp = review.cp
    path = HERE / "classify_placements.py"
    before = cp.sha256(path)
    source = path.read_text()
    block_start = source.index("        starts = [t for _, boundary, t in boundaries if boundary == 0]")
    block_end = source.index('        done = stream.get("done")', block_start)
    block = source[block_start:block_end]
    # Bind each parameter now, not to a later loop variable.
    cross_stream_witnesses = [
        lambda damage=damage: review.test_current_cross_stream_time_reversal_cannot_pass(damage)
        for damage in ("entry_after_carry_start", "teacher_and_entry_after_carry_start", "submit_after_carry_start")
    ]
    mutations = [
        ("cross_stream_order_removed", block, "", cross_stream_witnesses),
        ("submit_equality_allowed", "if not submit < first_start or not row_submit < first_start:",
         "if not submit <= first_start or not row_submit <= first_start:",
         [lambda: review.test_pre_execution_times_strictly_precede_earliest_robot_start("submit", "equal")]),
        ("entry_submit_equality_allowed", "if not entry < submit or not entry < row_submit:",
         "if not entry <= submit or not entry <= row_submit:",
         [lambda: review.test_entry_strictly_precedes_scheduled_submission(0., False)]),
        ("last_carry_start_used", "first_start = min(starts)", "first_start = max(starts)",
         [lambda: review.test_current_cross_stream_time_reversal_cannot_pass("submit_after_carry_start"),
          lambda: review.test_submission_cannot_hide_between_asynchronous_robot_starts("r1")]),
        ("row_submit_binding_removed", "if abs(submit - row_submit) > 1e-9:", "if False:",
         [lambda: review.test_recorded_submit_time_is_required_finite_and_consistent("row", "mismatch")]),
        ("r1_stream_skipped", '    for rid, stream in raw.items():\n',
         '    for rid, stream in raw.items():\n        if rid == "r1":\n            continue\n',
         [lambda: review.test_submission_cannot_hide_between_asynchronous_robot_starts("r1")]),
    ]
    results = []
    for name, old, new, witnesses in mutations:
        for witness in witnesses:
            witness()
        assert source.count(old) == 1, name
        mutant = types.ModuleType("mutation_299g_" + name)
        mutant.__file__ = str(path)
        exec(compile(source.replace(old, new), str(path) + ":" + name, "exec"), mutant.__dict__)
        original = cp.validate_recorder_chronology
        cp.validate_recorder_chronology = mutant.validate_recorder_chronology
        killed = 0
        try:
            for witness in witnesses:
                try:
                    witness()
                except AssertionError:
                    killed += 1
            assert killed, name + ": mutant survived"
        finally:
            cp.validate_recorder_chronology = original
        results.append({"mutation": name, "baseline_pass": True, "mutant": "KILLED",
                        "verdict_assertions_failed": killed, "witnesses": len(witnesses),
                        "deleted": old, "replacement": new})
    assert cp.sha256(path) == before
    report = {"source_sha256": before, "source_unchanged": True,
              "killed": len(results), "survived": 0, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("killed", "survived", "source_unchanged")}))


if __name__ == "__main__":
    main()
