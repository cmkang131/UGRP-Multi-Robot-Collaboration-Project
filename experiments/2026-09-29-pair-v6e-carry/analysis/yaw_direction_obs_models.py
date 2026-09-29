"""Yaw-direction analysis, step 3: use the robot-to-beam relative yaw that the own wrist RGB already shows.

Offline. Input: beam_edge_all_cases.json (200 case-robots from recorded frames + eval-only GT, see beam_edge_all_cases.py).
Physical picture (measured, see beam_edge_all_cases): each robot's yaw = beam yaw + relative yaw d_r; d_r is visible as the
slope change of the beam band's lower edge in the robot's own RGB (slope change = 0.96 x relative yaw change, corr 0.994).
The beam yaw itself (common mode) is NOT visible (no structure in the carried view).

Estimators of the robot yaw change over the window (all rates = change / window):
  E0  registered: m_self                                (dead reckoning of the own commands; the v6e PF mean)
  E1  pair-mean model: (m_self + m_partner)/2           (rigid pair: beam yaw = mean of the two plant predictions; the
                                                          partner's prediction is a function of the static plan, no message)
  E2  E1 + d_hat                                        (d_hat = own-image edge slope change, ratio 1.0 - physically 1:1)
  E3  E2 - LOPO regression of the remaining beam-yaw error on the staged pair offsets (as measured, noise added)
  L   LEAK: E2 with the GT beam yaw substituted for the common mode (only measurement error left)
Residual rate rho = (GT robot yaw change - estimate)/window. Balanced RMS: mean over cells of per-cell RMS (each cell once).
"""
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
D = json.load(open(HERE/'beam_edge_all_cases.json'))
GATE = math.radians(3.)
SIGMA0 = (0.0104, 0.0129)
LIVE = {0: 18.5, 1: 24.4, 2: 23.3, 3: 20.75, 4: 20.75, 5: 20.75, 6: 21.15, 7: 21.15}
NOISE = {'x': .004, 'y': .003, 'yaw': .008}


def feats(o1, o2):
    x1, y1, w1 = o1
    x2, y2, w2 = o2
    return np.array([(x1 - x2)/2, (x1 + x2)/2, (y1 - y2)/2, (y1 + y2)/2, (w1 + w2)/2, (w1 - w2)/2])   # u_x s_x u_y s_y w_u w_s


def prep():
    rows = []
    for q in D:
        T = q['t_b'] - q['t_a']
        if T < 8.:
            continue
        g, ms, mp, gb = q['g_dyaw']/T, q['m_self']/T, q['m_partner']/T, q['g_dbeam']/T
        dh = q['d_slope']/T
        rows.append({**q, 'T': T, 'g': g, 'ms': ms, 'mp': mp, 'gb': gb, 'dh': dh, 'cls': 'lat' if q['leg'] in (3, 4, 5) else 'ax',
                     'e0': g - ms, 'e1': g - (ms + mp)/2, 'e2': g - ((ms + mp)/2 + dh), 'gt_dev': (q['d_relyaw'])/T,
                     'f': feats(q['offsets']['r1'], q['offsets']['r2'])})
    return rows


def bal(rows, key_or_vals):
    vals = key_or_vals if not isinstance(key_or_vals, str) else [r[key_or_vals] for r in rows]
    per = defaultdict(list)
    for r, v in zip(rows, vals):
        per[r['cell']].append(v)
    p = {c: float(np.sqrt(np.mean(np.square(v)))) for c, v in per.items()}
    return float(np.sqrt(np.mean([v**2 for v in p.values()]))), p


def e3_lopo(rows, noise_mult, draws=200, seed=1):
    """Predict e2 (= beam yaw error of the pair-mean model, the part the image cannot see) from measured pair offsets."""
    rng = np.random.default_rng(seed)
    cells = sorted({r['cell'] for r in rows})
    nz = np.array([NOISE['x'], NOISE['y'], NOISE['yaw']])*noise_mult
    outs = []
    for _ in range(draws if noise_mult > 0 else 1):
        rho = np.zeros(len(rows))
        for c in cells:
            tr = [r for r in rows if r['cell'] != c]
            te = [(i, r) for i, r in enumerate(rows) if r['cell'] == c]
            pred = {}
            for cls in ('ax', 'lat'):
                t = [r for r in tr if r['cls'] == cls]
                # role does not matter for the beam-yaw error of the pair mean (e2 is symmetric): pool r1/r2
                X = np.array([np.r_[1., r['f']] for r in t]); y = np.array([r['e2'] for r in t])
                s = np.maximum(np.abs(X).max(0), 1e-12)
                beta = np.linalg.lstsq(X/s, y, rcond=None)[0]/s
                for i, r in te:
                    if r['cls'] != cls:
                        continue
                    o1 = np.array(r['offsets']['r1'], float) + (rng.normal(size=3)*nz if noise_mult > 0 else 0)
                    o2 = np.array(r['offsets']['r2'], float) + (rng.normal(size=3)*nz if noise_mult > 0 else 0)
                    pred[i] = float(np.r_[1., feats(o1, o2)]@beta)
            for i, r in te:
                rho[i] = r['e2'] - pred[i]
        outs.append(rho)
    return outs


def gate_t(b, s0):
    return math.sqrt(GATE**2 - s0**2)/b if b > 0 else math.inf



def route_cumulative(rows):
    """Yaw error accumulated over legs L0..L7 for the three cal cells (all eight legs exist there), per robot, [deg]."""
    print('\nWhole-route (L0..L7, window-time weighted) accumulated GT-vs-estimate yaw error of the three cal cells [deg] (r1 / r2)')
    for cell in ('nominal', 'yaw+/same', 'lat-/opp'):
        line = []
        for key in ('e0', 'e1', 'e2'):
            tot = {}
            for rob in ('r1', 'r2'):
                rs = [r for r in rows if r['variant'] == 'cal' and r['cell'] == cell and r['robot'] == rob]
                legs = {r['leg'] for r in rs}
                if legs != set(range(8)):
                    tot[rob] = float('nan'); continue
                tot[rob] = math.degrees(sum(np.mean([q[key] for q in rs if q['leg'] == L])*np.mean([q['T'] for q in rs if q['leg'] == L]) for L in range(8)))
            line.append('%s %+.1f / %+.1f' % (key, tot['r1'], tot['r2']))
        print('  %-10s %s' % (cell, ' | '.join(line)))

def coefficients(rows):
    """Full-data fit of e2 (beam-yaw error of the pair-mean model, common mode) on the pair-mode offsets, per leg class."""
    print('\nFull-data fit (all 11 cells; NOT a held-out result): common-mode yaw rate error e2 [mrad/s] per unit pair-mode offset')
    print('  (u = uniform in the world frame, s = skew; along/lateral in mm, yaw in 10 mrad; r1 faces +x, r2 faces -x)')
    names = ['const', 'u_x', 's_x', 'u_y', 's_y', 'w_u', 'w_s']
    unit = [1., 1e-3, 1e-3, 1e-3, 1e-3, .01, .01]
    for cls in ('ax', 'lat'):
        t = [r for r in rows if r['cls'] == cls]
        X = np.array([np.r_[1., r['f']] for r in t]); y = np.array([r['e2'] for r in t])
        s_ = np.maximum(np.abs(X).max(0), 1e-12)
        beta = np.linalg.lstsq(X/s_, y, rcond=None)[0]/s_
        print('  %-3s ' % cls + ', '.join('%s %+.3f' % (n, b*u*1e3) for n, b, u in zip(names, beta, unit)) + '   (u_x has no data: along +/- cells with opp sign did not stage)')

def main():
    rows = prep()
    print('case-robots (s911 only, window >= 8 s): %d, cells %d' % (len(rows), len({r['cell'] for r in rows})))
    # validity of d_hat: residual after replacing GT dev
    resid_dev = [r['dh'] - r['gt_dev'] for r in rows]
    print('d_hat (slope) vs GT relative yaw rate: RMS difference %.3f mrad/s (window mean %.1f s)' % (1e3*np.sqrt(np.mean(np.square(resid_dev))), np.mean([r['T'] for r in rows])))
    out = {}
    tab = []
    for name, key in [('E0 registered (own commands only)', 'e0'), ('E1 pair-mean model', 'e1'), ('E2 pair-mean + image relative yaw', 'e2')]:
        b, per = bal(rows, key)
        tab.append((name, b)); out[name] = {'balanced_rms_rad_s': b, 'per_cell_mrad_s': {k: v*1e3 for k, v in per.items()}}
        print('  %-40s balanced RMS %.5f [%.2f mrad/s]  max |rho| %.2f mrad/s' % (name, b, b*1e3, 1e3*max(abs(r[key]) for r in rows)))
    # E3 (offset regression on the leftover beam-yaw error)
    for mult in (0., 1., 2.):
        outs = e3_lopo(rows, mult)
        b = float(np.mean([bal(rows, o)[0] for o in outs]))
        name = 'E3 E2 - offsets regression (noise x%.0f)' % mult
        tab.append((name, b)); out[name] = {'balanced_rms_rad_s': b}
        print('  %-40s balanced RMS %.5f [%.2f mrad/s]' % (name, b, b*1e3))
    # leak
    leak = [r['g'] - (r['gb'] + r['dh']) for r in rows]
    b, _ = bal(rows, leak)
    tab.append(('L LEAK: GT beam yaw + image relative yaw', b)); out['L'] = {'balanced_rms_rad_s': b}
    print('  %-40s balanced RMS %.5f [%.2f mrad/s]' % ('L LEAK GT beam yaw + image relative yaw', b, b*1e3))
    # what the common mode alone is
    bb, per_b = bal(rows, [r['gb'] - (r['ms'] + r['mp'])/2 for r in rows])
    print('  common-mode (beam yaw rate minus pair-mean model): balanced RMS %.5f' % bb)

    print('\nper-cell RMS [mrad/s]: cell | E0 | E1 | E2 | (E3 noise x1 below)')
    e3 = e3_lopo(rows, 1.)
    b3, p3 = bal(rows, np.mean(e3, 0))
    for c in sorted(out['E0 registered (own commands only)']['per_cell_mrad_s']):
        print('  %-14s %6.2f %6.2f %6.2f %6.2f' % (c, out['E0 registered (own commands only)']['per_cell_mrad_s'][c], out['E1 pair-mean model']['per_cell_mrad_s'][c],
                                                  out['E2 pair-mean + image relative yaw']['per_cell_mrad_s'][c], p3[c]*1e3))
    print('\nGate time (sigma(t)=sqrt(s0^2+(b t)^2) vs 3 deg) and legs passing (live L0 18.5 L1 24.4 L2 23.3 L3-5 20.75 L6-7 21.15):')
    for name, b in tab:
        t0, t1 = gate_t(b, SIGMA0[0]), gate_t(b, SIGMA0[1])
        legs = [k for k, v in LIVE.items() if v <= t1]
        print('  b=%.5f %-42s gate %6.1f / %6.1f s  legs %s  whole-route(170.8 s) sigma %.1f deg' %
              (b, name, t0, t1, legs if len(legs) < 8 else 'all', math.degrees(math.hypot(SIGMA0[0], b*170.8))))
    route_cumulative(rows)
    coefficients(rows)
    print('\n2-sigma coverage of the leg-end yaw error with sigma_end = sqrt(0.0104^2 + (b*live)^2), b = the balanced RMS of that estimator (should be >= 90 %)')
    draws = e3_lopo(rows, 1.)
    for name, key in (('E0', 'e0'), ('E1', 'e1'), ('E2', 'e2'), ('E3 (noise x1, mean over 200 draws)', None)):
        covs, bs = [], []
        for v in ([[r[key] for r in rows]] if key else draws):
            b = bal(rows, list(v))[0]
            bs.append(b)
            covs.append(np.mean([abs(x)*r['T'] <= 2*math.sqrt(SIGMA0[0]**2 + (b*LIVE[r['leg']])**2) for r, x in zip(rows, v)]))
        print('  %-36s b=%.5f coverage %.1f %%' % (name, np.mean(bs), 100*np.mean(covs)))
    ratios = sorted(((q['d_slope']/q['d_relyaw'], q['cell'], q['leg'], q['robot'], q['variant']) for q in D if abs(q['d_relyaw']) > math.radians(0.5)))
    print('\nlowest slope/relyaw ratios (|rel yaw change| > 0.5 deg):', [(round(a, 2), c, l, r) for a, c, l, r, v in ratios[:5]])
    json.dump({'summary': out, 'gate': [{'name': n, 'b': b, 'gate_s': [gate_t(b, s) for s in SIGMA0]} for n, b in tab]},
              open(HERE/'yaw_direction_obs_models.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
