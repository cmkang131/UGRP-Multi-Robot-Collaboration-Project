#!/usr/bin/env python3
"""Descriptive counts of usable frame pairs for the VIS7 R1 plan (read-only; cached boundary rows, no network).

A pair = two consecutive T0 (seed 0) estimate rows with the same arm/pan command (s3, s6), both settled, and at least
8 columns with a cached wall-floor boundary in both frames. GT only labels the pair; it never feeds an estimator.
Labels follow experiments/2026-09-28-vis6-recipe1/posthoc_v6.py (GT XY speed < 0.01 m/s and estimated > 0.05 m/s =
stuck-but-commanded; GT > 0.05 m/s = moving). Everything else is counted as `other`.
DESCRIPTIVE ONLY. Not a measurement of the R1 detector. Nothing here selects a threshold.

  python3 pair_counts.py --root /Users/changmin/projects/ugrp/outputs/vis6-recipe1-20260929 --output pair_counts.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'2026-09-28-vis6-recipe1'))
import posthoc_v6 as ph  # noqa: E402

EPISODES = ph.FIT + ['vl3-dev-s945', 'vl3-dev-s946', 'vl3-dev-s947']


def counts(root: Path, ep: str) -> dict:
    d = np.load(ph.OBS/f'{ep}.obs.npz', allow_pickle=True)
    idx = {int(f): i for i, f in enumerate(d['frame'])}
    b, kind = d['b_lo'], d['b_kind']
    gt = ph.gt_of(ep)
    rows = ph.est(root, 'T0', 0, ep)
    out = dict(rows=len(rows), consecutive=0, same_arm_settled=0, cache_ok=0, stuck_commanded=0, moving=0, other=0)
    stuck_t = []
    for p, q in zip(rows, rows[1:]):
        out['consecutive'] += 1
        if (p['s3'], p['s6']) != (q['s3'], q['s6']) or not (p['settled'] and q['settled']):
            continue
        out['same_arm_settled'] += 1
        if p['frame'] not in idx or q['frame'] not in idx:
            continue
        i, j = idx[p['frame']], idx[q['frame']]
        ok = (kind[i] > 0) & (kind[j] > 0) & (b[i] > -1000) & (b[j] > -1000)
        if ok.sum() < 8:
            continue
        out['cache_ok'] += 1
        (t0, g0), (t1, g1) = gt[p['frame']], gt[q['frame']]
        dt = max(t1 - t0, 1e-6)
        v_gt = math.hypot(g1[0]-g0[0], g1[1]-g0[1])/dt
        v_est = math.hypot(q['vision']['xyyaw'][0]-p['vision']['xyyaw'][0], q['vision']['xyyaw'][1]-p['vision']['xyyaw'][1])/dt
        if v_gt < .01 and v_est > .05:
            out['stuck_commanded'] += 1
            stuck_t.append(t0)
        elif v_gt > .05:
            out['moving'] += 1
        else:
            out['other'] += 1
    # stuck-labelled pairs in the first 3 s are the dock start (estimate settling), not a physical stall
    out['stuck_commanded_first_3s'] = sum(1 for t in stuck_t if t < 3.)
    out['stuck_commanded_after_3s'] = sum(1 for t in stuck_t if t >= 3.)
    if stuck_t:
        late = [t for t in stuck_t if t >= 3.]
        out['stuck_after_3s_t_range_s'] = [round(min(late), 1), round(max(late), 1)] if late else None
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    res = {ep: counts(a.root, ep) for ep in EPISODES if (a.root/'runs'/'T0'/'seed0'/f'{ep}.estimates.jsonl').exists()}
    a.output.write_text(json.dumps({'schema': 'ugrp.vis7.pair_counts.v1', 'note': 'descriptive counts only; not a detector result',
                                    'root': str(a.root), 'episodes': res}, indent=1))
    for ep, r in res.items():
        print(ep, {k: v for k, v in r.items()})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
