#!/usr/bin/env python3
"""Rerun manifest for planner faults (PREREG 7: a fault is rerun once under a new name, the first record is kept).

  python3 rerun_halted.py --manifest manifests/v36/core-main308.csv --evidence evidence/physical --out manifests/v36/rerun-halted.csv

A run counts as a planner fault when its brain-record.json has a non-null `halted` (for example 'ResponseError':
the model used the whole output cap on hidden reasoning). Such runs exit 0 with status complete, so the dispatcher
does not retry them by itself. Each fault row is written with run_id '<id>-rr1' (analyze_main reads both '-rr1' and
'-retry1'). A run that already has a '-rr1' record is skipped. Standard library only, reads files only.
"""
import argparse
import csv
import json
import sys
from pathlib import Path


def halted(evidence, run_id):
    path = evidence / run_id / "brain-record.json"
    try:
        return json.loads(path.read_text()).get("halted")
    except (OSError, ValueError):
        return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", type=Path, action="append", required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    rows, fields = [], None
    for m in a.manifest:
        with m.open(newline="") as f:
            r = csv.DictReader(f)
            fields = fields or r.fieldnames
            rows += list(r)
    out = []
    for row in rows:
        rid = row["run_id"]
        if rid.endswith("-rr1") or (a.evidence / (rid + "-rr1")).exists():
            continue
        why = halted(a.evidence, rid)
        if why:
            out.append(dict(row, run_id=rid + "-rr1"))
            print("fault %s: halted=%s" % (rid, why))
    with a.out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    print("wrote %d rerun rows of %d -> %s" % (len(out), len(rows), a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
