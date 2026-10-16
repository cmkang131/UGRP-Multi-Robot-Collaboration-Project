#!/usr/bin/env python3
"""Fail before expensive CI work when sparse checkout omitted frozen fixtures."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
# test_zone_study_review_r7_contract.py reads these tracked historical records.
# Keep this list shared with agent_worktree's sparse exceptions.
REQUIRED_FIXTURES = (
    "experiments/2026-09-26-zone-study-offline-smoke/v3/example_trial_record.json.gz",
    "experiments/2026-09-26-zone-study-offline-smoke/v4/example_trial_record.json.gz",
    "experiments/2026-09-26-zone-study-offline-smoke/v5/example_trial_record.json.gz",
)


def check_fixtures(root: Path = ROOT) -> bool:
    missing = [path for path in REQUIRED_FIXTURES if not (root / path).is_file()]
    if not missing:
        return True
    print("CI preflight: required frozen fixtures are missing:", file=sys.stderr)
    for path in missing:
        print(f"  {path}", file=sys.stderr)
    print(
        "Sparse checkout may exclude experiments/**/*.gz. Restore the tracked "
        "fixtures before retrying; do not skip their tests. In a sparse worktree run:\n"
        "  git sparse-checkout add "
        + " ".join(f"/{path}" for path in missing),
        file=sys.stderr,
    )
    return False


def main() -> int:
    if not check_fixtures():
        return 2
    print(f"CI preflight: {len(REQUIRED_FIXTURES)} frozen fixtures present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
