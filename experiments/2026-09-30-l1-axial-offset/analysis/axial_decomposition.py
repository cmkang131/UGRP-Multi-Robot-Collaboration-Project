#!/usr/bin/env python3
"""Where does the L1 end error come from? Exact decomposition of the along-track error of the chained L0 -> L1 carry.

Reads the leg table written by ``extract_legs.py`` (ground truth is eval only). Prints, per cohort and per order-sheet value:
  * the measured plant (v_ss, lag, delay) and how it differs from the numbers the controller plans with,
  * the exact identity   along_L1 = dx + [F(T0) - d0] + [F(T1) - coast - 0.85]   (dx = beam x - sheet x),
  * the fit  L1 end error = a + b * dx  of the exploratory notes, and why b is 1.09 instead of 1.0,
  * the model residual against the recorded along errors.
Usage: axial_decomposition.py --table <leg_table.json>
"""
import argparse
import collections
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plant_model as pm  # noqa: E402

COHORT_GROUPS = {'no gain fix (A)': ('cA', 'rA', 'sA'), 'gain fix (B)': ('cB', 'rB', 'sB')}


def chain_rows(rows, labels=None):
    for r in rows:
        if labels and r['label'] not in labels:
            continue
        if len(r['legs']) < 2 or not all(L.get('cmd') for L in r['legs']):
            continue
        yield r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--table', required=True)
    a = ap.parse_args()
    rows = json.load(open(a.table))['rows']
    out = []
    P = out.append

    # 1. plant
    P('== 1. measured loaded-carry plant (fit of the GT beam x(t) around every forward command window, rms < 0.25 mm)')
    for k in (0, 1):
        for key in ('v_ss', 'tau', 'tau_stop', 'delay'):
            v = np.array([r['legs'][k]['plant'][key] for r in chain_rows(rows)])
            P(f'  L{k} {key:9s} n={len(v):3d} mean {v.mean():.5f} sd {v.std():.5f} min {v.min():.5f} max {v.max():.5f}')
    P(f'  steady gain (v_ss / forward command {pm.CMD:.7f}) = {pm.PLANT["v_ss"] / pm.CMD:.4f}')
    P(f'  gain the open-loop plan implies (SPEED*0.772/CMD)      = {pm.SPEED * pm.ODOM_AXIAL / pm.CMD:.4f}')
    P(f'  gain of the registered PF plant / after kappa          = {pm.PF_GAIN:.4f} / {pm.PF_GAIN * pm.KAPPA:.4f}   (lag {pm.PF_TAU} s, stop {pm.PF_TAU_STOP} s)')
    P(f'  measured lag / stop lag                                = {pm.PLANT["tau"]:.3f} s / {pm.PLANT["tau_stop"]:.4f} s')

    # 2. tick rule + timed stopping
    P('\n== 2. stopping rule: timed. Commanded window T_cmd against the plan T = d / (0.06 * 0.772)')
    c = collections.Counter()
    for r in chain_rows(rows):
        sx = r['sheet'][0]
        c[(sx, round(pm.T_registered(pm.ROUTE_X[1] - sx), 3), round(r['legs'][0]['cmd']['T_s'], 1),
           round(pm.T_registered(0.85), 3), round(r['legs'][1]['cmd']['T_s'], 1))] += 1
    for k, n in sorted(c.items()):
        P(f'  sheet x {k[0]:.1f}: L0 T_plan {k[1]:.3f} -> T_cmd {k[2]:.1f} ; L1 T_plan {k[3]:.3f} -> T_cmd {k[4]:.1f}   ({n} cases)')
    P('  T_cmd depends only on the order sheet (same value for every placement, PF seed, prior, gain fix): the leg is not closed on any estimate.')

    # 3. exact identity
    P('\n== 3. exact decomposition of the L1 along error (mm; identity checked to < 3 mm)')
    P('  cohort  sheet_x  n   dx_lift   L0_excess(F-d0)  coast   L1_excess(F-c-.85)  along_L1(obs)  along_L1(model)  resid')
    resid0, resid1 = [], []
    groups = collections.defaultdict(list)
    for r in chain_rows(rows, {'cA', 'cB', 'rA', 'rB', 'sA', 'sB'}):
        L0, L1 = r['legs']
        sx = r['sheet'][0]
        dx = r['beam_place'][0] - sx
        T0, T1 = L0['cmd']['T_s'], L1['cmd']['T_s']
        e0, e1 = pm.along_errors(dx, T0, T1, sx)
        resid0.append(1000 * (L0['along_error_m'] - e0))
        resid1.append(1000 * (L1['along_error_m'] - e1))
        d0 = pm.ROUTE_X[1] - sx
        groups[(r['label'], sx)].append((1000 * dx, 1000 * (pm.F(T0) - d0), pm.COAST_MM, 1000 * (pm.F(T1) - 0.85) - pm.COAST_MM,
                                         1000 * L1['along_error_m'], 1000 * e1))
    for (lab, sx), g in sorted(groups.items()):
        g = np.array(g)
        P(f'  {lab:5s}   {sx:.1f}     {len(g):2d}  {g[:, 0].mean():+7.1f}  {g[:, 1].mean():+9.1f}         {g[:, 2].mean():+5.1f}   {g[:, 3].mean():+9.1f}          '
          f'{g[:, 4].mean():+7.1f}        {g[:, 5].mean():+7.1f}      {g[:, 4].mean() - g[:, 5].mean():+.2f}')
    r0, r1 = np.array(resid0), np.array(resid1)
    P(f'  model residual against recorded along error: L0 mean {r0.mean():+.2f} sd {r0.std():.2f} max|.| {abs(r0).max():.2f} mm ; '
      f'L1 mean {r1.mean():+.2f} sd {r1.std():.2f} max|.| {abs(r1).max():.2f} mm  (n={len(r0)})')

    # 4. the dx fit of the exploratory notes
    P('\n== 4. regression of the L1 END error (the pass gate, 100 mm) on dx = beam x - rounded sheet x')
    for lab in ('sA', 'sB', 'rA', 'rB'):
        xs, ys, al, sh = [], [], [], []
        for r in chain_rows(rows, {lab}):
            L1 = r['legs'][1]
            xs.append(1000 * (r['beam_place'][0] - r['sheet'][0]))
            ys.append(1000 * L1['end_error_m'])
            al.append(1000 * L1['along_error_m'])
            sh.append(r['sheet'][0])
        xs, ys, al, sh = map(np.array, (xs, ys, al, sh))
        b, a0 = np.polyfit(xs, ys, 1)
        b2, a2 = np.polyfit(xs, al, 1)
        s = f'  {lab}: end_error = {a0:5.1f} + {b:.2f}*dx (corr {np.corrcoef(xs, ys)[0, 1]:.2f}); along = {a2:5.1f} + {b2:.2f}*dx (corr {np.corrcoef(xs, al)[0, 1]:.2f})'
        w = sh == 1.0
        if w.sum() > 3 and (~w).sum() > 1 and xs[w].std() > 15:
            bw, aw = np.polyfit(xs[w], al[w], 1)
            s += f' ; inside sheet 1.0 only: along = {aw:5.1f} + {bw:.2f}*dx'
        P(s)
    P('  The slope is above 1 because dx and the L0 excess move together: a beam at x < 0.95 rounds to sheet 0.9, which makes L0 longer (0.65 m)')
    P('  and therefore adds a larger timed-plan excess exactly where dx is already large and positive.')

    # 5. excess as a function of leg length (registered plan) and after candidate fixes
    P('\n== 5. axial travel excess of one leg as a function of its length (measured plant, tick phase averaged)')
    P('  d [m]   registered plan   PF-lag plan (1.4004, not fixed)   PF-lag plan (kappa 0.9483)   exact plant')
    for d in (0.45, 0.55, 0.65, 0.85):
        ex = [1000 * (pm.F(pm.T_registered(d)) - d),
              1000 * (pm.F(pm.T_lag(d, pm.PF_GAIN)) - d),
              1000 * (pm.F(pm.T_lag(d, pm.PF_GAIN * pm.KAPPA)) - d),
              1000 * (pm.F(pm.T_lag(d, pm.GAIN_TRUE, pm.PLANT['tau'], pm.PLANT['tau_stop'])) - d)]
        P(f'  {d:4.2f}   {ex[0]:+8.1f} mm      {ex[1]:+8.1f} mm                    {ex[2]:+8.1f} mm               {ex[3]:+6.1f} mm')
    txt = '\n'.join(out) + '\n'
    print(txt)
    return txt


if __name__ == '__main__':
    main()
