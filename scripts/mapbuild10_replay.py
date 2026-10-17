"""Coarse-start-prior offline adapter. Missing operator region fails closed.

Reuses mapbuild9's exact own LK/command fusion, scan joins, raw hashes and
prediction seals. No eval-only, spawn or simulator reads in this process.
"""
import argparse
from pathlib import Path
from mapbuild9_replay import run


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('input', 'saved', 'output', 'calibration', 'requirements', 'queue',
                 'stack-check', 'command-model', 'initial-prior'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--scan-source', type=Path)
    p.add_argument('--seed', type=int, default=20261017)
    args = p.parse_args()
    args.profile = 'nav2_defaults_v1'
    run(args)
