"""Yaw-direction analysis, step 2: how much of the loaded-pair yaw error can a controller-side mean model predict?

Offline; reads yaw_direction_dataset.json (built from recorded raw by yaw_direction_dataset.py). No physics run.

Response  e = (GT yaw change - registered loaded-plant prediction) / window   [rad/s], per case and robot. This is the
rate at which the registered dead-reckoning yaw drifts from the truth; it is what ``carry_dr_model`` models as a
random per-leg bias with std 0.00233 rad/s (cell-balanced RMS on the cal cells).

Model ladder (all fitted by least squares, evaluated leave-one-placement-out = leave one CELL NAME out, so that the
same offset design in the other setup variant (cal vs base) is held out with it):
  M0  no correction                        : the registered model, e itself.
  M1  command-only mean correction         : per (leg class, robot) intercept. Known to the controller (its own commands,
                                             its role). Predicts the pair-plant yaw coupling error.
  M2  M1 + own-image offsets, pair         : M1 + linear terms in the staged grip offsets of BOTH robots, reduced to the
                                             pair modes (uniform/skew shift along, lateral, yaw). The offsets are the
                                             align residuals; a controller can only know them as measured by its own
                                             image (noise added at test time, sensitivity shown). Needs the partner's
                                             measured offsets (pair channel).
  M2o M1 + own offsets only                : as M2 but without the partner's offsets (no pair-channel dependency).
  L1  LEAK: M1 + the true beam yaw rate of this very case (GT, not observable) - shows how much of the error is the
      common (beam) mode; excluded from the candidates.
  L2  LEAK: per-cell fixed effect (GT placement identity) - in-sample upper bound, excluded from the candidates.
Every variance is reported as the RMS over cells of the per-cell RMS of e (each cell counts once, as in
refit_carry_dr_cal.py). Only the LOPO numbers are honest predictions; "in-sample" is printed for scale.
"""
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROWS = json.load(open(HERE/'yaw_direction_dataset.json'))
AXIAL_LEGS, LAT_LEGS = (0, 1, 2, 6, 7), (3, 4, 5)
GATE_RAD = math.radians(3.)
LIVE_S = {0: 18.5, 1: 24.4, 2: 23.3, 3: 20.75, 4: 20.75, 5: 20.75, 6: 21.15, 7: 21.15}   # nominal passing legs (dataset)
SIGMA0 = (0.0104, 0.0129)      # cal PF yaw std at leg entry (min/max of the L0-L2 entries seen in cal-2)
B_CURRENT = 0.00233            # rad/s, registered v6e bias std (cell-balanced RMS on the three cal cells)
SIG_MEAS = {'x': .004, 'y': .003, 'yaw': .008}   # assumed own-image offset measurement noise (yaw: v6d-align hue-mask rms 8 mrad; x,y: assumption)


def leg_class(leg):
    return 'lat' if leg in LAT_LEGS else 'ax'


def features(off1, off2):
    """Pair-mode features from the staged own-frame offsets (along, lateral, yaw) of r1 and r2.

    r1 faces +x and r2 faces -x, so an own-frame 'same' offset is a skew in the world and 'opp' a uniform shift."""
    x1, y1, w1 = off1
    x2, y2, w2 = off2
    return np.array([(x1 - x2)/2, (x1 + x2)/2,        # u_x uniform along shift, s_x spacing change (world)
                     (y1 - y2)/2, (y1 + y2)/2,        # u_y uniform lateral shift, s_y skew
                     (w1 + w2)/2, (w1 - w2)/2])       # w_u uniform yaw, w_s counter yaw


FEAT_NAMES = ['u_x', 's_x', 'u_y', 's_y', 'w_u', 'w_s']


def aggregate():
    """(variant, cell, leg, robot) -> mean over duplicate cases (PF seeds / diagnostic reruns share one physics)."""
    g = defaultdict(list)
    for r in ROWS:
        g[(r['variant'], r['cell'], r['leg'], r['robot'])].append(r)
    out = []
    for (var, cell, leg, rob), rs in g.items():
        o = rs[0]['offsets']
        out.append({'variant': var, 'cell': cell, 'leg': leg, 'robot': rob, 'cls': leg_class(leg),
                    'e': float(np.mean([(x['gt_dyaw'] - x['model_dyaw'])/x['T_s'] for x in rs])),
                    'beam': float(np.mean([x['gt_dbeam']/x['T_s'] for x in rs])),
                    'own': np.array(o[rob], float), 'off1': np.array(o['r1'], float), 'off2': np.array(o['r2'], float),
                    'n': len(rs)})
    return out


def design(rec, kind):
    role = 1. if rec['robot'] == 'r2' else 0.
    base = [1. - role, role]                       # per-robot intercept
    if kind == 'M1':
        return np.array(base)
    if kind == 'M2':
        f = features(rec['off1'], rec['off2'])
        return np.concatenate([base, (1. - role)*f, role*f])
    if kind == 'M2o':
        f = rec['own']
        return np.concatenate([base, (1. - role)*f, role*f])
    raise KeyError(kind)


def fit_predict(train, test, kind, *, test_noise=None, rng=None, ridge=1e-9):
    """Per leg class least squares (min-norm); returns predictions for ``test``."""
    pred = np.zeros(len(test))
    for cls in ('ax', 'lat'):
        tr = [r for r in train if r['cls'] == cls]
        ti = [i for i, r in enumerate(test) if r['cls'] == cls]
        if not tr or not ti:
            continue
        X = np.array([design(r, kind) for r in tr])
        y = np.array([r['e'] for r in tr])
        # scale columns so that offsets in mm / mrad and intercepts are comparable
        s = np.maximum(np.abs(X).max(0), 1e-12)
        beta = np.linalg.lstsq(np.vstack([X/s, np.sqrt(ridge)*np.eye(X.shape[1])]), np.concatenate([y, np.zeros(X.shape[1])]),
                               rcond=None)[0]/s
        for i in ti:
            r = test[i]
            if test_noise is not None and kind in ('M2', 'M2o'):
                r = dict(r)
                r['own'] = r['own'] + rng.normal(size=3)*test_noise
                r['off1'] = r['off1'] + rng.normal(size=3)*test_noise
                r['off2'] = r['off2'] + rng.normal(size=3)*test_noise
            pred[i] = design(r, kind)@beta
    return pred


def cell_rms(recs, resid):
    per = defaultdict(list)
    for r, v in zip(recs, resid):
        per[r['cell']].append(v)
    rms = {c: float(np.sqrt(np.mean(np.square(v)))) for c, v in per.items()}
    return float(np.sqrt(np.mean([v**2 for v in rms.values()]))), rms


def lopo(recs, kind, *, noise=None, draws=1, seed=0):
    rng = np.random.default_rng(seed)
    cells = sorted({r['cell'] for r in recs})
    resid_all = []
    for d in range(draws):
        resid = np.zeros(len(recs))
        for c in cells:
            tr = [r for r in recs if r['cell'] != c]
            ti = [i for i, r in enumerate(recs) if r['cell'] == c]
            te = [recs[i] for i in ti]
            p = fit_predict(tr, te, kind, test_noise=noise, rng=rng)
            for j, i in enumerate(ti):
                resid[i] = recs[i]['e'] - p[j]
        resid_all.append(resid)
    return np.mean(resid_all, 0) if draws == 1 else resid_all


def gate_time(b, sigma0):
    """Live (moving) time [s] at which sqrt(sigma0^2 + (b t)^2) reaches the 3 degree hold gate."""
    if b <= 0:
        return math.inf
    return math.sqrt(max(GATE_RAD**2 - sigma0**2, 0.))/b


def main():
    recs = aggregate()
    print('records (variant, cell, leg, robot) after averaging duplicate physics: %d, cells: %d' % (len(recs), len({r["cell"] for r in recs})))
    cells = sorted({r['cell'] for r in recs})
    print('cells:', cells)
    out = {}

    # ---- M0 and its two reference cell sets
    e = np.array([r['e'] for r in recs])
    m0, per0 = cell_rms(recs, e)
    cal3 = [r for r in recs if r['variant'] == 'cal']
    m0_cal = cell_rms(cal3, [r['e'] for r in cal3])[0]
    print('\nM0 (registered model, no correction): all-cell balanced RMS %.5f rad/s; the three cal cells only %.5f (v6e refit 0.00233)' % (m0, m0_cal))
    out['M0'] = {'all_cells': m0, 'cal_cells': m0_cal, 'per_cell': per0}

    results = {}
    for kind in ('M1', 'M2', 'M2o'):
        r = lopo(recs, kind)
        results[kind] = r
    # noise sensitivity for M2 / M2o
    noise_rows = {}
    for kind in ('M2', 'M2o'):
        for mult in (0., 1., 2.):
            nz = np.array([SIG_MEAS['x'], SIG_MEAS['y'], SIG_MEAS['yaw']])*mult
            if mult == 0:
                res = lopo(recs, kind)
                rms = cell_rms(recs, res)[0]
            else:
                draws = lopo(recs, kind, noise=nz, draws=200, seed=3)
                rms = float(np.mean([cell_rms(recs, d)[0] for d in draws]))
            noise_rows[(kind, mult)] = rms
    # leaks
    beam = np.array([r['beam'] for r in recs])
    # L1: subtract the case's true beam yaw rate from e, then per (class, robot) mean (LOPO)
    l1 = []
    for c in cells:
        for i, r in enumerate(recs):
            if r['cell'] != c:
                continue
            tr = [q for q in recs if q['cell'] != c and q['cls'] == r['cls'] and q['robot'] == r['robot']]
            l1.append((i, r['e'] - r['beam'] - np.mean([q['e'] - q['beam'] for q in tr])))
    res_l1 = np.zeros(len(recs))
    for i, v in l1:
        res_l1[i] = v
    # L2: per-cell fixed effect in-sample: residual = e - mean over that cell's records for (class, robot)
    res_l2 = np.zeros(len(recs))
    for i, r in enumerate(recs):
        same = [q['e'] for q in recs if q['cell'] == r['cell'] and q['variant'] == r['variant'] and q['cls'] == r['cls'] and q['robot'] == r['robot']]
        res_l2[i] = r['e'] - np.mean(same)

    print('\nLOPO (leave one cell name out) balanced RMS of the residual rate, rad/s [mrad/s]:')
    rows = [('M0 registered (no correction)', e), ('M1 command-only mean correction', results['M1']),
            ('M2 M1 + measured pair offsets (noise-free)', results['M2']), ('M2o M1 + own offsets only (noise-free)', results['M2o']),
            ('L1 LEAK beam yaw rate observed', res_l1), ('L2 LEAK per-cell fixed effect (in-sample)', res_l2)]
    table = []
    for name, res in rows:
        bal, per = cell_rms(recs, res)
        # worst single case-robot
        table.append((name, bal, float(np.max(np.abs(res))), per))
        print('  %-46s %.5f [%.2f]   max |e| %.2f mrad/s' % (name, bal, bal*1e3, np.max(np.abs(res))*1e3))
    print('  with assumed own-image measurement noise on the offsets (x %.0f mm, y %.0f mm, yaw %.0f mrad; x2 = double):' %
          (SIG_MEAS['x']*1e3, SIG_MEAS['y']*1e3, SIG_MEAS['yaw']*1e3))
    for (kind, mult), v in noise_rows.items():
        print('    %-4s noise x%.0f  balanced LOPO RMS %.5f [%.2f]' % (kind, mult, v, v*1e3))

    # per cell breakdown
    print('\nper-cell RMS of e [mrad/s]: cell | M0 | M1 | M2 | M2o | L1')
    per_tab = {}
    for c in cells:
        vals = []
        for res in (e, results['M1'], results['M2'], results['M2o'], res_l1):
            vals.append(cell_rms(recs, res)[1][c]*1e3)
        per_tab[c] = vals
        print('  %-14s %s' % (c, ' '.join('%6.2f' % v for v in vals)))

    # per (leg, robot) intercept-only prediction (M1) - the model's yaw coupling correction
    print('\nM1 intercepts fitted on all cells (mrad/s): class robot -> mean e')
    for cls in ('ax', 'lat'):
        for rob in ('r1', 'r2'):
            v = [r['e'] for r in recs if r['cls'] == cls and r['robot'] == rob]
            vn = [r['e'] for r in recs if r['cls'] == cls and r['robot'] == rob and r['cell'] == 'nominal']
            print('  %-3s %-2s all-cells mean %+.2f  nominal-only mean %+.2f' % (cls, rob, np.mean(v)*1e3, np.mean(vn)*1e3))

    # ---- time to the 3 degree gate
    print('\nTime to the 3 deg hold gate, sigma(t)=sqrt(sigma0^2+(b*t)^2) (validated on cal-2 PF traces: L0 end sigma 0.048 at 20 s with b=0.00233):')
    print('  b [rad/s]  source | live time to gate (sigma0 0.0104 / 0.0129) | legs of live time L0 18.5, L1 24.4, L2 23.3, L3-5 20.75, L6-7 21.15 that pass')
    gate_tab = []
    for name, b in [('registered v6e refit (M0, cal 3 cells)', B_CURRENT),
                    ('M0 on all %d cells' % len(cells), m0),
                    ('M1 command-only (LOPO)', cell_rms(recs, results['M1'])[0]),
                    ('M2o own offsets, noise x1', noise_rows[('M2o', 1.)]),
                    ('M2 pair offsets, noise x1', noise_rows[('M2', 1.)]),
                    ('M2 pair offsets, noise x2', noise_rows[('M2', 2.)]),
                    ('M2 pair offsets, noise-free', cell_rms(recs, results['M2'])[0]),
                    ('L1 leak (beam yaw observed)', cell_rms(recs, res_l1)[0])]:
        t0, t1 = gate_time(b, SIGMA0[0]), gate_time(b, SIGMA0[1])
        passing = [k for k, lt in LIVE_S.items() if lt <= t1]
        passing_opt = [k for k, lt in LIVE_S.items() if lt <= t0]
        gate_tab.append((name, b, t0, t1, passing))
        print('  %.5f  %-38s | %5.1f / %5.1f s | legs %s (optimistic sigma0: %s)' % (b, name, t0, t1, passing, passing_opt))
    total = sum(LIVE_S.values())
    print('  whole route live time L0..L7 = %.1f s; a constant bias b tolerated for the WHOLE route without any yaw observation: <= %.5f rad/s (%.2f mrad/s)' %
          (total, math.sqrt(GATE_RAD**2 - SIGMA0[0]**2)/total, math.sqrt(GATE_RAD**2 - SIGMA0[0]**2)/total*1e3))
    # 2-sigma honesty: what fraction of case-robot residuals stay within 2*b_assumed*live
    print('\nHonesty check of the LOPO-M2 bias std: fraction of case-robots whose |yaw error at leg end| <= 2 sigma_end with sigma_end from b=that RMS')
    for name, res in (('M0', e), ('M1', results['M1']), ('M2 noise-free', results['M2'])):
        b = cell_rms(recs, res)[0]
        cov = np.mean([abs(v)*LIVE_S[r['leg']] <= 2*math.sqrt(SIGMA0[0]**2 + (b*LIVE_S[r['leg']])**2) for r, v in zip(recs, res)])
        print('  %-14s b=%.5f  coverage %.1f %%' % (name, b, cov*100))

    json.dump({'M0': out['M0'], 'lopo_balanced_rms_rad_s': {n: b for n, b, _, _ in table},
               'noise_rows': {f'{k[0]}_x{int(k[1])}': v for k, v in noise_rows.items()},
               'per_cell_mrad_s': per_tab,
               'gate_table': [{'name': n, 'b_rad_s': b, 'gate_s_sigma0_0.0104': t0, 'gate_s_sigma0_0.0129': t1, 'legs_pass': p}
                              for n, b, t0, t1, p in gate_tab]}, open(HERE/'yaw_direction_models.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
