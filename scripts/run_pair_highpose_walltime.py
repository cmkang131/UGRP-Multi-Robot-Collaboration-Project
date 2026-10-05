"""Opt-in wall-time monitor around scripts/run_pair_highpose.py (DEV diagnostic sidecar).

The runner itself is unchanged and stays the default path. This wrapper runs the same
``main()`` in-process with sim.walltime_monitor installed and writes
``<--output>/walltime_profile.jsonl`` (run root, outside every case directory, so no case
manifest or other output byte changes). Same arguments, locks and slots as the runner::

    .venv-sim-worker-mac/bin/python scripts/run_pair_highpose_walltime.py [--walltime-window-sim-s 10] -- \
        --check carry --map-id ... --expected-source-sha ... --output /abs/outputs/<run> --execute ...

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
    sidecar = Path(args.output) / SIDECAR
    if not args.execute:
        return runner.main(rest)
    monitor = WalltimeMonitor(sidecar, window_sim_s=own.walltime_window_sim_s).install_v98(runner)
    try:
        return runner.main(rest)
    finally:
        monitor.close()
        if sidecar.is_file():
            print(json.dumps({'walltime_profile': str(sidecar), **summarize(sidecar)}), file=sys.stderr)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
