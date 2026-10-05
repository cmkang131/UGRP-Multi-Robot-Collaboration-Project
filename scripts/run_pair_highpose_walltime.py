"""Opt-in wall-time monitor (and opt-in bit-exact speedups) around scripts/run_pair_highpose.py.

The runner itself is unchanged and stays the default path. This wrapper runs the same
``main()`` in-process with sim.walltime_monitor installed and writes
``<--output>/walltime_profile.jsonl`` (run root, outside every case directory, so no case
manifest or other output byte changes). Same arguments, locks and slots as the runner::

    .venv-sim-worker-mac/bin/python scripts/run_pair_highpose_walltime.py [--walltime-window-sim-s 10] \
        [--no-monitor] [--speedups none|v98-exact-v1|v98-exact-v2|v98-exact-v3|v98-exact-v4|v98-exact-v5|v98-exact-v6] -- \
        --check carry --map-id ... --expected-source-sha ... --output /abs/outputs/<run> --execute ...

``--speedups`` installs harness.zone_pair_highpose_exact_speedups (default 'none' = original path) and
records the set, item status and cache counters in ``<--output>/speedups.json`` (run root). Equivalence of
a set on a run: ``python scripts/compare_v98_runs.py <caseA> <caseB>``.

Summary of a finished sidecar: ``python -m sim.walltime_monitor <run>/walltime_profile.jsonl``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def split_argv(argv):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--walltime-window-sim-s', type=float, default=10.)
    p.add_argument('--no-monitor', action='store_true', help='speedups only, no walltime_profile.jsonl')
    p.add_argument('--speedups', default='none', help='harness.zone_pair_highpose_exact_speedups set name')
    if '--' in argv:
        i = argv.index('--')
        own, rest = argv[:i], argv[i + 1:]
    else:
        own, rest = [], list(argv)
    return p.parse_args(own), rest


def main(argv=None):
    own, rest = split_argv(sys.argv[1:] if argv is None else argv)
    from scripts import run_pair_highpose as runner
    from sim.walltime_monitor import SIDECAR, WalltimeMonitor, summarize
    args = runner.parser().parse_args(rest)
    out = Path(args.output)
    sidecar = out / SIDECAR
    if not args.execute:
        return runner.main(rest)
    existed = out.exists()      # the runner refuses an existing output; never write into it
    from harness import zone_pair_highpose_exact_speedups as speed
    record, undo = speed.install(own.speedups)
    monitor = None if own.no_monitor else WalltimeMonitor(
        sidecar, window_sim_s=own.walltime_window_sim_s).install_v98(runner)
    rc = None
    try:
        rc = runner.main(rest)
        return rc
    finally:
        if monitor is not None:
            monitor.close()
        undo()
        if out.is_dir() and not existed:
            (out / 'speedups.json').write_text(json.dumps({'schema': 'ugrp.v98_run_speedups.v1', 'monitor': monitor is not None,
                'speedups': speed.summary(record), 'runner_rc': rc}, indent=1) + '\n')
        if sidecar.is_file() and not existed:
            print(json.dumps({'walltime_profile': str(sidecar), **summarize(sidecar)}), file=sys.stderr)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
