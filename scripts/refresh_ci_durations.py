#!/usr/bin/env python3
"""Build configs/ci_test_durations.json from downloaded offline-shard JUnit files.

Usage (no scheduled automation; run by hand when shards drift out of balance):

    gh run download <run-id> -D outputs/ci-durations/<run-id> -p 'offline-shard-*'
    python3 scripts/refresh_ci_durations.py outputs/ci-durations/* --output configs/ci_test_durations.json

Per-file cost is the sum of its testcase times in each run; the largest value
across runs is kept so a noisy fast run cannot hide an expensive file. Files
that no longer exist in the current CI list are dropped. A file with no
measurement (for example one inside a shard that hit the timeout and left no
JUnit) is reported and is scheduled at the median cost by run_ci_tests.py.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))

from scripts import run_ci_tests


def file_times(xml_path: Path) -> dict[str, float]:
    """Sum testcase seconds per test file in one JUnit report."""
    totals: dict[str, float] = defaultdict(float)
    for case in ET.parse(xml_path).getroot().iter("testcase"):
        path = case.get("file")
        if not path:  # legacy reports: fall back to the dotted classname
            module = (case.get("classname") or "").split(".")
            for end in range(len(module), 0, -1):
                candidate = "/".join(module[:end]) + ".py"
                if (ROOT / candidate).is_file():
                    path = candidate
                    break
        if path:
            totals[path] += float(case.get("time") or 0.0)
    return totals


def aggregate(run_dirs: list[Path]) -> dict[str, float]:
    """Max over runs of the per-run, per-file total."""
    best: dict[str, float] = {}
    for run_dir in run_dirs:
        per_run: dict[str, float] = defaultdict(float)
        for xml_path in sorted(run_dir.rglob("*.xml")):
            for path, seconds in file_times(xml_path).items():
                per_run[path] += seconds
        for path, seconds in per_run.items():
            best[path] = max(best.get(path, 0.0), seconds)
    return best


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dirs", nargs="+", type=Path, help="directories holding downloaded offline-shard-* artifacts")
    parser.add_argument("--output", type=Path, default=ROOT / "configs" / "ci_test_durations.json")
    parser.add_argument("--top", type=int, default=10, help="slowest files to print")
    args = parser.parse_args(argv)

    current = set(run_ci_tests.collect_test_files(ROOT, run_ci_tests.TEST_PATTERNS))
    measured = aggregate(args.run_dirs)
    kept = {path: round(seconds, 2) for path, seconds in sorted(measured.items()) if path in current}
    missing = sorted(current - set(kept))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(kept, indent=1, sort_keys=True) + "\n")
    print(f"wrote {args.output}: {len(kept)} files, {sum(kept.values()):.0f}s total")
    for path, seconds in sorted(kept.items(), key=lambda item: -item[1])[: args.top]:
        print(f"  {seconds:8.1f}s  {path}")
    if missing:
        print(f"{len(missing)} current files have no measurement (median cost is used): {missing}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
