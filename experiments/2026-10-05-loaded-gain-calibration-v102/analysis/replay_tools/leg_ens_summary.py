#!/usr/bin/env python3
"""Ensemble summary of the fcc5215f replay (PREREGISTRATION section 8). Evaluation only: truth scores, never drives.

cfg  rec  = #363 HEAD 14ba8b5e as is, recorded calibration (aba4ac58 = v101 unloaded C + the old DEV loaded model). fcc5215f itself was recorded with this
            calibration, so for the loaded legs (a) "as recorded" and (b) "C only" are the same configuration.
cfg  v102 = HEAD + the v102 patch (affine dead zone) + the v102 loaded calibration (ce447ada).
mode meas   = full replay (own frames update the PF); nomeas = every frame rejected (pure dead reckoning of the same PF).
Per leg and robot, over PF seeds {0,101,...,104}:
  d_err     lateral/axial displacement error over the leg, est - truth (mm, est heading frame at leg start)          [registered: ~52 mm recorded bias]
  e_abs     absolute error along the commanded axis at the leg end (mm, truth body frame)
  D_vel     model-only displacement = integral of the PF mean body velocity (heading-independent), ratio to truth
  nees2     (est - truth)' C^-1 (est - truth) at the leg end, chi2(2) median 1.386
usage: leg_ens_summary.py [--json OUT]
"""
import glob
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_pf import load_truth, load_replay  # noqa: E402
from leg_summary import legs_of, leg_row  # noqa: E402

D = os.environ.get('REPLAY_DIR', '/Users/changmin/projects/ugrp/outputs/pf-loadedgain-v102-20261005/replay7194')   # the replay set to summarize (summary files go to its parent)
RAW = '/Users/changmin/projects/ugrp/outputs/v98-dev-probe-align_to_carry-fcc5215f/zone_wide_door_geometry_v3'
SEEDS = (0, 101, 102, 103, 104)
CFGS = ('rec', 'v102')
MODES = ('nomeas', 'meas')


def collect():
    out = {}
    for rid in ('r1', 'r2'):
        tr = load_truth(RAW, rid)
        legs = legs_of(RAW, rid)
        for cfg in CFGS:
            for mode in MODES:
                for s in SEEDS:
                    p = f'{D}/{cfg}_{rid}_s{s}_{mode}.jsonl'
                    if not os.path.exists(p) or not any('"kind": "final"' in l for l in open(p)):
                        continue
                    frames = [f for f in load_replay(p)[0] if f['initialized']]
                    for k, leg in enumerate(legs):
                        row = leg_row(RAW, rid, leg, frames, tr)
                        out.setdefault((cfg, mode, rid, k), []).append((s, row, leg))
    return out


def med(xs):
    return float(np.median(xs)) if len(xs) else float('nan')


def main():
    res = collect()
    summ = {}
    print('rows: cfg/mode robot leg(axis,u,t0) n_seeds | median d_err_mm  e_abs_mm  ratio_est  ratio_vel(D_vel/truth)  nees2')
    for key in sorted(res):
        cfg, mode, rid, k = key
        rows = res[key]
        r0 = rows[0][1]
        d = [r['d_err'] * 1000 for _, r, _ in rows]
        e = [r['ey_end_body'] * 1000 if r['axis'] == 'left' else float('nan') for _, r, _ in rows]
        rv = [r['ratio_vel'] for _, r, _ in rows]
        re_ = [r['ratio'] for _, r, _ in rows]
        nees = [r['nees2'] for _, r, _ in rows]
        summ[f'{cfg}/{mode}/{rid}/{k}'] = {'axis': r0['axis'], 'u': r0['u'], 't0': r0['t0'], 'n': len(rows), 'd_err_mm': med(d),
                                           'e_abs_left_mm': med(e), 'ratio_est': med(re_), 'ratio_vel': med(rv), 'nees2': med(nees),
                                           'd_err_mm_all': d}
        print(f"{cfg:5s}{mode:7s}{rid} {r0['axis']:7s}{r0['u']:+.4f} t0={r0['t0']:6.1f} n={len(rows)} | {med(d):8.1f} {med(e):8.1f}  {med(re_):7.4f}  {med(rv):7.4f}  {med(nees):6.2f}")
    # registered criterion: the two lateral legs of both robots, median over seeds and legs of |d_err| (nomeas = pure dead reckoning; meas = full replay);
    # forward legs and the whole-run windows are reported by window_summary.py
    crit = {}
    for mode in MODES:
        print(f'\nregistered criterion ({mode}; legs with |u|>0.04 of r1 and r2 (the 0.0208 align leg is excluded); median over seeds and legs of |est - truth| displacement error over the leg):')
        for axis in ('left', 'forward'):
            for cfg in CFGS:
                vals = [abs(x) for (c, m, rid, k), rows in res.items() if c == cfg and m == mode and rows[0][1]['axis'] == axis and abs(rows[0][1]['u']) > .04
                        for x in [r['d_err'] * 1000 for _, r, _ in rows]]
                crit[f'{cfg}/{mode}/{axis}'] = med(vals)
                print(f'  {axis:7s} {cfg:5s}: median |d_err| = {crit[f"{cfg}/{mode}/{axis}"]:.1f} mm over {len(vals)} (seed, leg, robot) values')
    json.dump({'per_leg': summ, 'criterion_median_abs_derr_mm': crit}, open(os.path.join(D, f'../leg_ens_summary_{os.path.basename(D)}.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
