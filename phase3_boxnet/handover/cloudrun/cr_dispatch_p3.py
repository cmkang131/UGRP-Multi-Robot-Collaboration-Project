#!/usr/bin/env python3
"""Phase-3 front end for the phase-2 dispatcher 20261118-cloudrun-p2/cr_dispatch_p2.py. That file is imported unchanged (it patches cr_dispatch.py and dispatch.py in memory only).

What this file adds to cr_dispatch_p2:
  * the phase-3 groups are added to dispatch.ALL_GROUPS the way cr_dispatch_p2.py adds p2core, p2pilot and p2gate
    (dispatch.load_manifest rejects a group that is not in ALL_GROUPS)
  * a manifest with any row whose sha is not 40 lowercase hex characters is refused (plan and run, before the dispatcher runs). The dispatcher's real-run check
    refuses TODO and PLACEHOLDER only, so the v8 placeholder PENDING-V8-EXEC-COMMIT would pass it.
  Everything else is cr_dispatch_p2's: a real run (--go) refuses TODO rows, rows without --fixed need --allow-llm, the job, quota and timeout checks, and `plan` is a
  simulation (the real Scheduler with a fake gcloud and a fake clock; no network).

  cr_dispatch_p3.py plan --manifest M.csv --size 3 --regions us-central1=S1,us-east1=S2,us-west1=S3 --image-tag T --batch B     # simulation, prints the commands
  cr_dispatch_p3.py run  --manifest M.csv --dir runs/D --size 3 --regions ... --image-tag T --allow-llm --go                    # REAL RUN (money); no test starts it
  cr_dispatch_p3.py status|cancel|stop|fetch --dir D ...                                                                          # forwarded unchanged
"""
import argparse
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
P2_DIR = HERE.parent / "test_support/20261118-cloudrun-p2"                   # the phase-2 dispatcher folder (not modified)
sys.dont_write_bytecode = True
sys.path.insert(0, str(P2_DIR))
import cr_dispatch_p2 as P2D  # noqa: E402  (imports cr_dispatch.py and dispatch.py; registers p2core, p2pilot, p2gate)
import dispatch  # noqa: E402  (the same module object that cr_dispatch_p2 patched)

P3_GROUPS = ("p3core", "p3chk", "p3v8core", "p3v8chk", "p3v10core", "p3v10chk", "p3v11", "p3v11chk",
             "p3v11budget", "p3v11budgetchk", "p3v11static", "p3v11staticchk")
dispatch.ALL_GROUPS = tuple(dispatch.ALL_GROUPS) + tuple(g for g in P3_GROUPS if g not in dispatch.ALL_GROUPS)
SHA40 = re.compile(r"[0-9a-f]{40}")


def bad_sha_rows(manifest):
    """The run ids of the rows whose sha is not 40 lowercase hex characters."""
    with open(manifest, encoding="utf-8", newline="") as stream:
        return [r.get("run_id", "?") for r in csv.DictReader(stream) if not SHA40.fullmatch((r.get("sha") or "").strip())]


def manifest_of(argv):
    """The --manifest of a plan or run command line; None for the other subcommands."""
    if not argv or argv[0] not in ("plan", "run"):
        return None
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--manifest", type=Path)
    known, _rest = p.parse_known_args(argv[1:])
    return known.manifest


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    manifest = manifest_of(argv)
    if manifest is not None:
        try:
            bad = bad_sha_rows(manifest)
        except OSError as error:
            print(f"refuse: cannot read {manifest}: {error}", file=sys.stderr)
            return 2
        if bad:
            print(f"refuse: {len(bad)} row(s) of {manifest.name} have no 40-hex executor commit in sha (first: {bad[0]}); the dispatcher's real-run check does not catch "
                  "the v8 placeholder, so the wrapper refuses it", file=sys.stderr)
            return 2
    return P2D.main(argv)


if __name__ == "__main__":
    sys.exit(main())
