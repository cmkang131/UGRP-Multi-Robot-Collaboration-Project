"""L2 E2E seed separation check. Read-only; no simulator.

1. the L2 range is disjoint from every registered range in
   ``experiments/2026-11-05-e2e-l2/seeds.json``;
2. ``--pairact-ref``: every range of the pairact-r1 seeds.json at that git ref
   (splits, train_extension, pilot, known_ranges) is listed in our registered
   ranges, so a later pairact edit cannot silently drift past this check;
3. ``--scan-refs``: ``git grep`` each ref for a 7-digit literal inside the L2
   range outside this experiment directory and the L2 code/tests.
Exit 1 on any problem.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'experiments/2026-11-05-e2e-l2/seeds.json'
OWN = ('experiments/2026-11-05-e2e-l2/', 'harness/e2e_l2', 'scripts/run_e2e_l2.py', 'scripts/check_e2e_l2_seeds.py',
       'tests/test_e2e_l2', 'tests/test_run_e2e_l2.py', 'tests/test_check_e2e_l2_seeds.py')


def expand(r):
    if r['last'] < r['first']:
        raise ValueError('empty seed range')
    return set(range(r['first'], r['last'] + 1))


def check(spec):
    l2 = expand(spec['l2'])
    problems = []
    for r in spec['registered_ranges']:
        n = len(l2 & expand(r))
        if n:
            problems.append(f'L2 overlaps {r["name"]} ({r["source"]}): {n}')
    return problems


def pairact_ranges(seeds_json):
    spec = json.loads(seeds_json)
    out = [dict(v, name='split_' + k) for k, v in spec['splits'].items()]
    out += [dict(spec[k], name=k) for k in ('train_extension', 'pilot') if k in spec]
    out += [dict(v, name='known') for v in spec.get('known_ranges', [])]
    return out


def drift(spec, ref):
    raw = subprocess.run(['git', '-C', str(ROOT), 'show', f'{ref}:{spec["pairact_r1_source"]["path"]}'],
                         capture_output=True, text=True)
    if raw.returncode:
        return [f'pairact seeds.json not readable at {ref}: {raw.stderr.strip()}']
    ours = [expand(r) for r in spec['registered_ranges']]
    return [f'pairact range {r["name"]} {r["first"]}-{r["last"]} not covered by registered_ranges'
            for r in pairact_ranges(raw.stdout) if not any(expand(r) <= s for s in ours)]


def scan(spec, refs):
    l2 = expand(spec['l2'])
    prefixes = sorted({str(s)[:4] for s in l2})
    pattern = r'(?<![0-9A-Za-z.])(' + '|'.join(prefixes) + r')[0-9]{3}(?![0-9A-Za-z.])'
    hits = []
    for ref in refs:
        out = subprocess.run(['git', '-C', str(ROOT), 'grep', '-n', '-I', '-o', '-P', pattern, ref, '--'],
                             capture_output=True, text=True)
        if out.returncode not in (0, 1):
            raise RuntimeError(f'git grep failed on {ref}: {out.stderr.strip()}')
        for line in out.stdout.splitlines():
            _, path, _, value = line.split(':', 3)
            if int(value) in l2 and not path.startswith(OWN):
                hits.append(dict(ref=ref, path=path, seed=int(value)))
    return hits


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--seeds', type=Path, default=DEFAULT)
    p.add_argument('--pairact-ref')
    p.add_argument('--scan-refs', nargs='*', default=[])
    a = p.parse_args(argv)
    spec = json.loads(a.seeds.read_text())
    problems = check(spec) + (drift(spec, a.pairact_ref) if a.pairact_ref else [])
    hits = scan(spec, a.scan_refs) if a.scan_refs else []
    report = dict(seeds=str(a.seeds), l2=spec['l2'], problems=problems, pairact_ref=a.pairact_ref,
                  scan_refs=a.scan_refs, scan_hits=hits, passed=not problems and not hits)
    print(json.dumps(report, indent=1))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
