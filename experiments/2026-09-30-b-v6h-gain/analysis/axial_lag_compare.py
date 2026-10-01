#!/usr/bin/env python3
"""Axial-lag check (PR #286 proposal P1b): axial / cross-track / end error per leg, with vs without the axial lag on the same placements.

Usage: axial_lag_compare.py [--json out.json] <label>=<raw dir> ...     (reads cases.jsonl only; ground truth is evaluation only)

Per raw: leg pass (standard checks, both legs), and for L0 and L1 the distributions of the signed along-track error, the absolute
cross-track error and the end error (mm): mean, median, p90, max. The PR #286 model predicted for the confirmatory-like sheet-1.0 cases:
L1 along ~ +dx +- 4 mm (with the lag), cross-track mean |y| 31 mm / p90 59 mm / max 69 mm, worst end error 94 mm.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-30-door-relax-envelope/analysis'))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-29-door-guard-relax/analysis'))
from harness import pair_chain_probe as pcp  # noqa: E402
import chain_analysis as ca  # noqa: E402


def stats(v):
    v = np.array([x for x in v if x is not None], float) * 1000
    if not len(v):
        return None
    return {'n': len(v), 'mean': v.mean(), 'median': float(np.median(v)), 'p90': float(np.percentile(v, 90)), 'min': v.min(), 'max': v.max()}


def fmt(s):
    return 'n/a' if s is None else f"mean {s['mean']:+6.1f} med {s['median']:+6.1f} p90 {s['p90']:+6.1f} range [{s['min']:+6.1f}, {s['max']:+6.1f}]"


def analyse(label, root):
    rows = [json.loads(l) for l in open(root / 'cases.jsonl')]
    out = {'label': label, 'raw': str(root), 'n_cases': len(rows), 'per_case': []}
    passed = {0: 0, 1: 0}
    both = 0
    cols = {k: {'along': [], 'cross': [], 'end': []} for k in (0, 1)}
    for r in rows:
        chain = r.get('chain') or {'legs': []}
        item = {'cell': r['cell'], 'seed': r['seed'], 'legs': {}}
        ok = []
        for k in (0, 1):
            leg = chain['legs'][k] if len(chain['legs']) > k else {'recorded': False}
            if not leg.get('recorded'):
                ok.append(False)
                continue
            good = all(pcp.leg_checks(leg).values())
            ok.append(good)
            passed[k] += good
            for key, col in (('along_error_m', 'along'), ('cross_track_m', 'cross'), ('end_error_m', 'end')):
                cols[k][col].append(leg.get(key))
            item['legs'][k] = {'pass': good, 'along_mm': 1000 * leg['along_error_m'], 'cross_mm': 1000 * leg['cross_track_m'],
                               'end_mm': 1000 * leg['end_error_m']}
        both += all(ok)
        out['per_case'].append(item)
    out['pass'] = {'L0': passed[0], 'L1': passed[1], 'both': both}
    out['stats'] = {f'L{k}': {c: stats(v) for c, v in cols[k].items()} for k in (0, 1)}
    print(f'\n== {label}: {root.name}: cases {len(rows)}; L0 {passed[0]}, L1 {passed[1]}, both legs {ca.fmt_ci(both, len(rows))}')
    for k in (0, 1):
        for c in ('along', 'cross', 'end'):
            print(f'  L{k} {c:5s} mm: {fmt(out["stats"][f"L{k}"][c])}')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', type=Path)
    ap.add_argument('raws', nargs='+')
    a = ap.parse_args()
    res = []
    for spec in a.raws:
        label, _, path = spec.partition('=')
        res.append(analyse(label, Path(path)))
    if a.json:
        a.json.write_text(json.dumps(res, indent=1, default=float))


if __name__ == '__main__':
    main()
