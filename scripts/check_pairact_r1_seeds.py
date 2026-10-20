"""pairact-r1 seed separation check (P3). Read-only; no simulator.

1. train/validation/heldout sizes are 200/20/20 and pairwise disjoint;
2. no proposed seed lies in a registered earlier beampair/beamact range;
3. optional ``--scan-refs``: ``git grep`` each ref for any 7-digit literal inside
   the proposed ranges, outside this experiment directory (catches seeds another
   worker already used but did not register here).
Exit 1 on any overlap.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'experiments/2026-10-21-pairact-r1/seeds.json'
SIZES = {'train': 200, 'validation': 20, 'heldout': 20}
OWN_DIR = 'experiments/2026-10-21-pairact-r1/'


def expand(r):
    if r['last'] < r['first']:
        raise ValueError('empty seed range')
    return set(range(r['first'], r['last'] + 1))


def check(spec):
    problems, splits = [], {k: expand(v) for k, v in spec['splits'].items()}
    if set(splits) != set(SIZES):
        problems.append(f'splits must be exactly {sorted(SIZES)}')
    for name, n in SIZES.items():
        if len(splits.get(name, ())) != n:
            problems.append(f'{name} has {len(splits.get(name, ()))} seeds, expected {n}')
    names = sorted(splits)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if splits[a] & splits[b]:
                problems.append(f'{a}/{b} overlap {len(splits[a] & splits[b])}')
    for known in spec['known_ranges']:
        hit = {n: len(s & expand(known)) for n, s in splits.items() if s & expand(known)}
        if hit:
            problems.append(f'overlap with {known["source"]}: {hit}')
    return problems


def scan(spec, refs):
    proposed = set().union(*(expand(v) for v in spec['splits'].values()))
    prefixes = sorted({str(s)[:4] for s in proposed})
    pattern = r'\b(' + '|'.join(prefixes) + r')[0-9]{3}\b'
    hits = []
    for ref in refs:
        out = subprocess.run(['git', '-C', str(ROOT), 'grep', '-n', '-I', '-o', '-E', pattern, ref, '--'],
                             capture_output=True, text=True)
        if out.returncode not in (0, 1):
            raise RuntimeError(f'git grep failed on {ref}: {out.stderr.strip()}')
        for line in out.stdout.splitlines():
            _, path, _, value = line.split(':', 3)
            if not path.startswith(OWN_DIR) and int(value) in proposed and 'pairact_r1' not in path:
                hits.append(dict(ref=ref, path=path, seed=int(value)))
    return hits


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--seeds', type=Path, default=DEFAULT)
    p.add_argument('--scan-refs', nargs='*', default=[])
    a = p.parse_args(argv)
    spec = json.loads(a.seeds.read_text())
    problems = check(spec)
    hits = scan(spec, a.scan_refs) if a.scan_refs else []
    report = dict(seeds=str(a.seeds), problems=problems, scan_refs=a.scan_refs, scan_hits=hits,
                  passed=not problems and not hits)
    print(json.dumps(report, indent=1))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
