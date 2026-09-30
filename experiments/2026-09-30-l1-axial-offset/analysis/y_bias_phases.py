#!/usr/bin/env python3
"""Where does the y bias of the loaded PF (estimate - ground truth, -8 ... +15 mm between cohorts) come from, phase by phase and robot?

The number quoted in experiments/2026-09-30-b-v6h-gain is the mean signed PF y error of both robots at the leg end. Ground truth is EVAL ONLY.
Sections:
  A  tie-out with the exploratory README (signed PF error at the leg end per cohort, both robots pooled)
  B  PF error along the chain by phase (pair mean = the number of A; robot difference = the mirrored part)
  C  what moves the PF y error inside a forward window: integral of v*sin(PF yaw error) plus the PF cross-coupling term
  D  the open-loop alignment pulse (6 s, unloaded TURN_GAIN): commanded vs achieved rotation, and what the PF credits
  E  ground truth: the beam drifts exactly by travel * tan(heading) (no forward->lateral coupling in the plant)
Usage: y_bias_phases.py --table <leg_table.json>
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

CROSS_COUPLING = 0.0054        # calibration_loop_v2.json params.motion_loaded.gain[1][0] (forward command -> lateral velocity)
LABELS = ('cA', 'cB', 'rA', 'rB', 'sA', 'sB')


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def get(r, rid, t):
    best = None
    for p in r['pf_err']:
        if p['t'] <= t + 1e-6 and rid in p:
            best = p
    return best[rid] if best else None


def usable(rows):
    for r in rows:
        if r['label'] in LABELS and len(r['legs']) == 2 and all(L.get('cmd') for L in r['legs']):
            yield r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--table', required=True)
    a = ap.parse_args()
    rows = list(usable(json.load(open(a.table))['rows']))
    out = []
    P = out.append

    P('== A. mean signed PF error (estimate - truth) at the leg end, both robots pooled (ties out with the exploratory README)')
    P('  cohort  leg   n    x [mm]   y [mm]   yaw [deg]')
    for lab in LABELS:
        for k in (0, 1):
            e = []
            for r in rows:
                if r['label'] != lab:
                    continue
                for rid in ('r1', 'r2'):
                    g = get(r, rid, r['legs'][k]['end_sim_s'])
                    if g:
                        e.append(g[:3])
            e = np.array(e)
            P(f'  {lab:5s}   L{k}  {len(e):3d}  {1000 * e[:, 0].mean():+7.1f}  {1000 * e[:, 1].mean():+7.1f}  {math.degrees(e[:, 2].mean()):+7.2f}')

    P('\n== B. PF y error [mm] and yaw error [deg] by phase and robot (mean over cases; r1 = -x end of the beam facing +x, r2 = +x end facing -x)')
    phases = [('prior seed (1.3 s)', lambda r: 1.31), ('start L0 (6.1 s)', lambda r: r['legs'][0]['r1']['start']['t']),
              ('L0 fwd start (after align)', lambda r: r['legs'][0]['cmd']['t0']), ('L0 fwd end', lambda r: r['legs'][0]['cmd']['t1']),
              ('L1 start (after handover)', lambda r: r['legs'][1]['r1']['start']['t']), ('L1 fwd start', lambda r: r['legs'][1]['cmd']['t0']),
              ('L1 fwd end', lambda r: r['legs'][1]['cmd']['t1'])]
    keep = {}
    for grp, labs in (('no gain fix (A: cA rA sA)', ('cA', 'rA', 'sA')), ('gain fix (B: cB rB sB)', ('cB', 'rB', 'sB'))):
        P(f'  -- {grp}')
        P('  phase                         ey r1   ey r2   pair mean   (r2-r1)/2 |  eyaw r1  eyaw r2 | ex r1  ex r2')
        prev = None
        for name, tf in phases:
            v = collections.defaultdict(list)
            for r in rows:
                if r['label'] not in labs:
                    continue
                for rid in ('r1', 'r2'):
                    g = get(r, rid, tf(r))
                    if g:
                        v[rid].append(g[:3])
            if not v['r1']:
                continue
            m = {rid: np.array(v[rid]).mean(0) for rid in ('r1', 'r2')}
            pm_ = 1000 * (m['r1'][1] + m['r2'][1]) / 2
            keep[(grp, name)] = pm_
            step = '' if prev is None else f'   step {pm_ - prev:+6.1f}'
            P(f'  {name:29s} {1000 * m["r1"][1]:+6.1f}  {1000 * m["r2"][1]:+6.1f}   {pm_:+7.1f}    {1000 * (m["r2"][1] - m["r1"][1]) / 2:+7.1f}   | {math.degrees(m["r1"][2]):+6.2f}  {math.degrees(m["r2"][2]):+6.2f}  |'
              f' {1000 * m["r1"][0]:+6.1f} {1000 * m["r2"][0]:+6.1f}{step}')
            prev = pm_

    P('\n== B2. pair-mean PF y error [mm] step by step, per cohort (why the cohort means differ: -8 ... +15 mm)')
    P('  cohort   n   placement yaw [deg]   PF yaw err after align [deg]  | start   align   L0 travel   handover   L1 travel  = L1 end')
    for lab in LABELS:
        rr = [r for r in rows if r['label'] == lab]
        pts = [lambda r: r['legs'][0]['r1']['start']['t'], lambda r: r['legs'][0]['cmd']['t0'], lambda r: r['legs'][0]['cmd']['t1'],
               lambda r: r['legs'][1]['cmd']['t0'], lambda r: r['legs'][1]['cmd']['t1']]
        vals = []
        yawe = []
        for r in rr:
            row_ = []
            for f in pts:
                e = [get(r, rid, f(r)) for rid in ('r1', 'r2')]
                row_.append(1000 * (e[0][1] + e[1][1]) / 2)
            vals.append(row_)
            e = [get(r, rid, pts[1](r)) for rid in ('r1', 'r2')]
            yawe.append(math.degrees((e[0][2] + e[1][2]) / 2))
        v = np.array(vals).mean(0)
        P(f'  {lab:5s}   {len(rr):3d}   {np.mean([math.degrees(r["beam_place"][2]) for r in rr]):+6.2f}              {np.mean(yawe):+6.2f}                     | '
          f'{v[0]:+6.1f}  {v[1] - v[0]:+6.1f}  {v[2] - v[1]:+8.1f}   {v[3] - v[2]:+8.1f}   {v[4] - v[3]:+8.1f}  = {v[4]:+6.1f}')

    P('\n== C. inside a forward window: PF y error change = integral of v*sin(PF yaw error) + cross-coupling term')
    P('  cross-coupling: the calibrated plant has gain[1][0] = 0.0054 (forward command -> lateral speed). With the sign flip of r2 it moves the PF')
    P('  of BOTH robots to world +y by 0.0054 * 0.03818 * (T - tau) = 2.2 mm (L0, 11.8 s) and 3.6 mm (L1, 18.4 s).')
    P('  cohorts  leg  robot  obs dEy   sum v*sin(eyaw)   residual (mean, sd)   predicted coupling   corr(obs, sum)')
    for grp, labs in (('A', ('cA', 'rA', 'sA')), ('B', ('cB', 'rB', 'sB'))):
        for k in (0, 1):
            for rid in ('r1', 'r2'):
                obs, pred = [], []
                for r in rows:
                    if r['label'] not in labs:
                        continue
                    L = r['legs'][k]
                    t0, t1 = L['cmd']['t0'], L['cmd']['t1']
                    w = [p for p in r['pf_err'] if t0 <= p['t'] <= t1 and rid in p]
                    if len(w) < 3:
                        continue
                    t = np.array([p['t'] for p in w])
                    ey = np.array([p[rid][1] for p in w])
                    eyaw = np.array([p[rid][2] for p in w])
                    obs.append(1000 * (ey[-1] - ey[0]))
                    pred.append(1000 * np.trapezoid(L['plant']['v_ss'] * np.sin(eyaw), t))
                obs, pred = np.array(obs), np.array(pred)
                T = 11.8 if k == 0 else 18.4
                coup = 1000 * CROSS_COUPLING * pm.CMD * (T - pm.PLANT['tau'])
                P(f'  {grp:5s}    L{k}   {rid}   {obs.mean():+6.1f}   {pred.mean():+9.1f}         {np.mean(obs - pred):+5.1f}, {np.std(obs - pred):.1f}          {coup:+5.1f}           {np.corrcoef(obs, pred)[0, 1]:.3f}')

    P('\n== D. the open-loop alignment pulse (run_m2_pair.door_schedule: turn = e_yaw / 6 s / TURN_GAIN, TURN_GAIN = 1.4885 = UNLOADED gain)')
    X, Y, dE = [], [], []
    for r in rows:
        L0 = r['legs'][0]
        cm, gr, dp = [], [], []
        for rid, target in (('r1', 0.), ('r2', math.pi)):
            st = L0[rid]['start']
            cm.append(wrap(target - st['own'][2]))
            gr.append(wrap(L0['gt']['robot_yaw_t0'][rid] - st['gt_robots'][rid][2]))
            e0, e1 = get(r, rid, st['t']), get(r, rid, L0['cmd']['t0'])
            dp.append(wrap(e1[2] - e0[2]))
        X.append(np.mean(cm))
        Y.append(np.mean(gr))
        dE.append(np.mean(dp))
    X, Y, dE = map(np.array, (X, Y, dE))
    b, a0 = np.polyfit(X, Y, 1)
    P(f'  achieved GT rotation = {b:.3f} * commanded {math.degrees(a0):+.2f} deg   (pair mean, n={len(X)}, corr {np.corrcoef(X, Y)[0, 1]:.2f}, residual sd {math.degrees(np.std(Y - a0 - b * X)):.2f} deg)')
    b2, a2 = np.polyfit(Y, dE, 1)
    P(f'  change of the PF yaw error over the pulse = {b2:+.3f} * GT rotation {math.degrees(a2):+.2f} deg (corr {np.corrcoef(Y, dE)[0, 1]:.2f}):'
      f' the PF credits only {1 + b2:.2f} of the true rotation')
    P('  => after the pulse the truth is left with ~0.4 of the intended correction PLUS the estimate error of the yaw the pulse was computed from;')
    P('     that heading residual times the 1.4 m of chained travel is the ground-truth cross-track of the L1 end (see predict_pass.py).')

    P('\n== E. ground truth: beam y drift over a forward window against travel * tan(robot heading)   (L0 window contains the settling of the align pulse)')
    for k in (0, 1):
        d = np.array([[1000 * r['legs'][k]['drift']['dy_beam'], 1000 * r['legs'][k]['drift']['dy_pred_from_robot_heading']['r1'],
                       1000 * r['legs'][k]['drift']['dy_pred_from_robot_heading']['r2']] for r in rows])
        P(f'  L{k}: GT dy mean {d[:, 0].mean():+.2f} mm ; from r1 heading {d[:, 1].mean():+.2f} ; from r2 heading {d[:, 2].mean():+.2f} ; '
          f'residual to r1: mean {np.mean(d[:, 0] - d[:, 1]):+.2f} sd {np.std(d[:, 0] - d[:, 1]):.2f} mm')
    P('  L1 residual is 0.1 mm: the true plant has NO forward->lateral coupling, so the +3.6 mm of C is a PF-model bias, not motion.')

    txt = '\n'.join(out) + '\n'
    print(txt)


if __name__ == '__main__':
    main()
