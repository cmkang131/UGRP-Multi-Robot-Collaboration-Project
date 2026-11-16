#!/usr/bin/env python3
"""VIS6 post-hoc descriptive diagnostics (NOT preregistered, NOT a selection input).

Reads a finished VIS6 output root (estimates of T0 and a few candidates, fit seeds 0-2) plus the eval-only GT
of the dev renders. GT is used only for scoring/labelling here, never fed back to any estimator.

  1. stuck vs non-stuck fit episodes: error p50/p90, lost (>0.30 m) share, XY 95% coverage, >3 sigma share
  2. T0 lost windows: GT path length vs estimated path length vs number of own commands in the window
  3. dock start phase: error and reported sigma of T0 at the last frame before the first drive command
  4. boundary-row disparity: median |delta row| of the cached wall-floor boundary (obs-w6) between consecutive
     settled same-arm frames, for GT-stuck-but-commanded pairs vs GT-moving pairs (feasibility hint only)

  python3 posthoc_v6.py --root /Users/changmin/projects/ugrp/outputs/vis6-recipe1-20260929 --output posthoc.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'2026-09-26-vision-loc'))
import vis6_metrics as vm6  # noqa: E402

PRIMARY = Path('/Users/changmin/projects/ugrp/outputs')
RENDER = PRIMARY/'vision-loc-20260926'/'render'
OBS = PRIMARY/'vision-loc-20260926'/'r3'/'obs-w6'
FIT = ['vl-dev-s909', 'vl-dev-s910', 'vl-dev-s911', 'vl3-dev-s941', 'vl3-dev-s942', 'vl3-dev-s943']
STUCK = ['vl-dev-s909', 'vl3-dev-s941']      # teacher stuck at the approach point (see README)
LOST_M = 0.30


def jl(p: Path) -> list:
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def gt_of(ep: str) -> dict:
    return {r['frame']: (float(r['t']), r['gt']) for r in jl(RENDER/ep/'eval_only'/'frames_eval.jsonl')}


def est(root: Path, cand: str, k: int, ep: str) -> list:
    return jl(root/'runs'/cand/f'seed{k}'/f'{ep}.estimates.jsonl')


def split_metrics(root: Path, cands: list) -> dict:
    out = {}
    for grp, eps in (('stuck2', STUCK), ('nonstuck4', [e for e in FIT if e not in STUCK])):
        for cand in cands:
            err, nees = [], []
            for k in (0, 1, 2):
                for ep in eps:
                    gt = gt_of(ep)
                    for r in est(root, cand, k, ep):
                        v = r['vision']
                        t = vm6.frame_terms(v['xyyaw'], v['cov'], gt[r['frame']][1])
                        err.append(t['err_m']); nees.append(t['nees_xy'])
            err, nees = np.array(err), np.array(nees)
            out[f'{grp}/{cand}'] = {'episodes': eps, 'seeds': [0, 1, 2], 'frames': int(len(err)),
                                    'err_p50_m': float(np.percentile(err, 50)), 'err_p90_m': float(np.percentile(err, 90)),
                                    'lost_share': float(np.mean(err > LOST_M)),
                                    'coverage95_xy': float(np.mean(nees <= vm6.CHI2_2_95)),
                                    'exceed3_xy': float(np.mean(nees > vm6.CHI2_2_3SIG))}
    return out


def lost_windows(root: Path) -> dict:
    out = {}
    for ep in STUCK:
        gt = gt_of(ep)
        rows = est(root, 'T0', 0, ep)
        segs, cur = [], None
        for r in rows:
            g = gt[r['frame']][1]; v = r['vision']['xyyaw']
            lost = math.hypot(v[0]-g[0], v[1]-g[1]) > LOST_M
            if lost and cur is None:
                cur = {'t0': r['t'], 'std_xy_at_start_m': r['vision']['std_xy_m']}
            if not lost and cur is not None:
                cur['t1'] = r['t']; segs.append(cur); cur = None
        if cur is not None:
            cur['t1'] = rows[-1]['t']; segs.append(cur)
        cmds = jl(RENDER/ep/'inputs'/'commands.jsonl')
        res = []
        for s in segs:
            if s['t1'] - s['t0'] < 2.:
                continue
            gseg = [gt[r['frame']][1] for r in rows if s['t0'] <= r['t'] <= s['t1']]
            eseg = [r['vision'] for r in rows if s['t0'] <= r['t'] <= s['t1']]
            gpath = sum(math.hypot(b[0]-a[0], b[1]-a[1]) for a, b in zip(gseg, gseg[1:]))
            epath = sum(math.hypot(b['xyyaw'][0]-a['xyyaw'][0], b['xyyaw'][1]-a['xyyaw'][1]) for a, b in zip(eseg, eseg[1:]))
            res.append({**s, 'gt_path_m': gpath, 'est_path_m': epath,
                        'own_mecanum_commands': sum(1 for c in cmds if c.get('kind') == 'mecanum'
                                                    and s['t0'] <= float(c['t']) <= s['t1']),
                        'std_xy_p50_m': float(np.median([e['std_xy_m'] for e in eseg])),
                        'max_err_m': max(math.hypot(e['xyyaw'][0]-g[0], e['xyyaw'][1]-g[1]) for e, g in zip(eseg, gseg))})
        out[ep] = res
    return out


def start_phase(root: Path) -> dict:
    out = {}
    for ep in FIT:
        cmds = jl(RENDER/ep/'inputs'/'commands.jsonl')
        tm = next(float(c['t']) for c in cmds if c.get('kind') == 'mecanum')
        gt = gt_of(ep)
        per = []
        for k in (0, 1, 2):
            r = [x for x in est(root, 'T0', k, ep) if x['t'] < tm][-1]
            g, v = gt[r['frame']][1], r['vision']
            per.append({'seed': k, 't': r['t'], 'err_m': math.hypot(v['xyyaw'][0]-g[0], v['xyyaw'][1]-g[1]),
                        'yaw_err_deg': abs(math.degrees(vm6.wrap(v['xyyaw'][2]-g[2]))),
                        'std_xy_m': v['std_xy_m'], 'std_yaw_deg': math.degrees(v['std_yaw_rad'])})
        out[ep] = {'first_mecanum_t': tm, 'per_seed': per}
    return out


def disparity(root: Path) -> dict:
    out = {}
    for ep in FIT:
        d = np.load(OBS/f'{ep}.obs.npz', allow_pickle=True)
        idx = {int(f): i for i, f in enumerate(d['frame'])}
        b, kind = d['b_lo'], d['b_kind']
        gt = gt_of(ep)
        rows = est(root, 'T0', 0, ep)
        groups = {'gt_stuck_commanded': [], 'gt_moving': []}
        for p, q in zip(rows, rows[1:]):
            if (p['s3'], p['s6']) != (q['s3'], q['s6']) or not (p['settled'] and q['settled']):
                continue
            if p['frame'] not in idx or q['frame'] not in idx:
                continue
            (t0, g0), (t1, g1) = gt[p['frame']], gt[q['frame']]
            dt = max(t1 - t0, 1e-6)
            v_gt = math.hypot(g1[0]-g0[0], g1[1]-g0[1])/dt
            v_est = math.hypot(q['vision']['xyyaw'][0]-p['vision']['xyyaw'][0],
                               q['vision']['xyyaw'][1]-p['vision']['xyyaw'][1])/dt
            i, j = idx[p['frame']], idx[q['frame']]
            ok = (kind[i] > 0) & (kind[j] > 0) & (b[i] > -1000) & (b[j] > -1000)
            if ok.sum() < 8:
                continue
            disp = float(np.median(np.abs(b[j][ok] - b[i][ok])))
            if v_gt < .01 and v_est > .05:
                groups['gt_stuck_commanded'].append(disp)
            elif v_gt > .05:
                groups['gt_moving'].append(disp)
        out[ep] = {k: {'pairs': len(x), 'p50_px': float(np.median(x)) if x else None,
                       'p90_px': float(np.percentile(x, 90)) if x else None} for k, x in groups.items()}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    if a.output.exists():
        raise SystemExit(f'refusing to overwrite {a.output}')
    res = {'schema': 'ugrp.vision_loc.vis6.posthoc.v1', 'root': str(a.root),
           'note': 'post-hoc descriptive only; not preregistered; never a selection input; GT for scoring only',
           'split_by_stuck': split_metrics(a.root, ['T0', 'T1b_eta050', 'T1ac_d05a6']),
           'T0_lost_windows_seed0': lost_windows(a.root),
           'T0_dock_start_phase': start_phase(a.root),
           'boundary_row_disparity_T0_seed0': disparity(a.root)}
    a.output.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1)[:6000])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
