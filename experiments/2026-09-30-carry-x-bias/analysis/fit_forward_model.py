"""Fit the loaded forward-motion correction on the FIT set only; score it on every hold-out set.

Model family (all terms are things a controller has: its own issued commands and a fixed calibration):
  M0  registered loaded plant            gain_fwd = 1.4004, tau = 0.8 s
  M1  one forward-gain multiplier kappa  (tau fixed)
  M2  kappa and lag tau jointly
  M3  kappa per robot                    (r1, r2)
  M4  kappa per robot and per leg-0      (first leg after the teacher staging)
Score: endpoint error (GT travel minus model travel over [t_carry, t_end + 1.5 s], body forward axis) and trajectory RMS.
"""
import sys, json, pickle, collections
sys.path.insert(0, '.')
from xb_common import *
import xb_replay as R

PM = R.base_params()['motion_loaded']
GAIN = np.array(PM['gain'], float)
END_EXTRA = 1.5

def axial(w):
    dt = STEP
    uf = w['u'][:, 0].sum()*dt; ul = w['u'][:, 1].sum()*dt
    return abs(uf) > 0.1 and abs(ul) < 0.15

def end_index(w):
    return int(round((w['t_end'] + END_EXTRA - w['t_carry'])/STEP))

def model_pos(w, tau=TAU):
    return mean_model_u(w['u'], GAIN, tau=tau)[:, 0]

def endpoint(w, kappa, tau=TAU):
    i = min(end_index(w), len(w['gt_fwd'])-1)
    m = model_pos(w, tau)
    return w['gt_fwd'][i], kappa*m[i], i

def fit_kappa(ws, tau=TAU):
    """Least squares through the origin on endpoints (weights: model travel^2, i.e. long legs count more)."""
    num = den = 0.
    for w in ws:
        g, m, i = endpoint(w, 1.0, tau)
        num += g*m; den += m*m
    return num/den

def fit_kappa_tau(ws, taus=np.arange(0.6, 1.4001, 0.05)):
    best = None
    for tau in taus:
        num = den = 0.
        for w in ws:
            m = model_pos(w, tau)
            n = min(len(m), len(w['gt_fwd']))
            num += float(m[:n] @ w['gt_fwd'][:n]); den += float(m[:n] @ m[:n])
        k = num/den
        rss = 0.; cnt = 0
        for w in ws:
            m = model_pos(w, tau); n = min(len(m), len(w['gt_fwd']))
            rss += float(np.sum((k*m[:n] - w['gt_fwd'][:n])**2)); cnt += n
        r = math.sqrt(rss/cnt)
        if best is None or r < best[2]:
            best = (float(tau), float(k), r)
    return best

def score(ws, kappa_of, tau_of):
    """kappa_of(w), tau_of(w) -> per-window parameters. Returns endpoint bias/rms (mm) and trajectory rms (mm)."""
    e = []; rel = []; rss = 0.; cnt = 0
    for w in ws:
        k, tau = kappa_of(w), tau_of(w)
        g, m, i = endpoint(w, k, tau)
        sgn = 1. if m >= 0 else -1.
        e.append(sgn*(g - m)); rel.append((g-m)/g if abs(g) > 1e-3 else 0.)   # + = GT travelled farther than the model
        mp = model_pos(w, tau)*k; n = min(len(mp), len(w['gt_fwd']))
        rss += float(np.sum((mp[:n] - w['gt_fwd'][:n])**2)); cnt += n
    e = np.array(e)
    return dict(n=len(ws), end_bias_mm=1000*float(e.mean()), end_rms_mm=1000*float(np.sqrt((e**2).mean())),
                end_max_mm=1000*float(np.abs(e).max()), traj_rms_mm=1000*math.sqrt(rss/max(cnt, 1)), rel_bias_pct=100*float(np.mean(rel)))

def main(pkl, out_json):
    W = pickle.load(open(pkl, 'rb'))
    W = [w for w in W if axial(w)]
    F = [w for w in W if w['set'].startswith('F_')]
    sets = sorted({w['set'] for w in W})
    print('axial windows', len(W), 'fit', len(F))
    res = {'fit_windows': len(F), 'fit_cases': len({(w['raw'], w['case']) for w in F})}
    # ---- fits
    k1 = fit_kappa(F)
    tau2, k2, r2 = fit_kappa_tau(F)
    k3 = {r: fit_kappa([w for w in F if w['robot'] == r]) for r in ROBOTS}
    F_not0 = [w for w in F if w['leg'] != 0]
    k4 = {(r, l0): fit_kappa([w for w in F if w['robot'] == r and (w['leg'] == 0) == l0]) for r in ROBOTS for l0 in (True, False)}
    res['fit'] = dict(M1_kappa=k1, M2_tau=tau2, M2_kappa=k2, M2_traj_rms_mm=1000*r2,
                      M3_kappa={r: k3[r] for r in ROBOTS}, M4_kappa={f'{r}_{"L0" if l0 else "later"}': v for (r, l0), v in k4.items()},
                      gain_fwd_M1=float(GAIN[0, 0]*k1), gain_fwd_M2=float(GAIN[0, 0]*k2))
    print(json.dumps(res['fit'], indent=1))
    models = {
        'M0': (lambda w: 1.0, lambda w: TAU),
        'M1': (lambda w: k1, lambda w: TAU),
        'M2': (lambda w: k2, lambda w: tau2),
        'M3': (lambda w: k3[w['robot']], lambda w: TAU),
        'M4': (lambda w: k4[(w['robot'], w['leg'] == 0)], lambda w: TAU),
    }
    res['score'] = {}
    print('%-14s %-3s %5s  end_bias  end_rms  end_max  traj_rms  rel_bias%%' % ('set', 'mod', 'n'))
    for s in sets + ['ALL_HOLDOUT']:
        ws = [w for w in W if (w['set'] == s if s != 'ALL_HOLDOUT' else w['set'].startswith('H_'))]
        res['score'][s] = {}
        for name, (kf, tf) in models.items():
            sc = score(ws, kf, tf)
            res['score'][s][name] = sc
            print('%-14s %-3s %5d  %+7.1f  %7.1f  %7.1f  %8.1f  %+6.2f' % (s, name, sc['n'], sc['end_bias_mm'], sc['end_rms_mm'], sc['end_max_mm'], sc['traj_rms_mm'], sc['rel_bias_pct']))
    # ---- leave-one-case-out inside the fit set (both robots of a case left out)
    cases = sorted({(w['raw'], w['case']) for w in F})
    loco = []
    for cs in cases:
        tr = [w for w in F if (w['raw'], w['case']) != cs]; te = [w for w in F if (w['raw'], w['case']) == cs]
        k = fit_kappa(tr)
        loco.append(score(te, lambda w: k, lambda w: TAU)['end_rms_mm'])
    res['loco_M1_end_rms_mm'] = dict(mean=float(np.mean(loco)), max=float(np.max(loco)), n=len(loco))
    print('LOCO M1 endpoint rms mm: mean %.2f max %.2f (n=%d)' % (np.mean(loco), np.max(loco), len(loco)))
    # ---- per (set, robot, leg) kappa table for the README
    tab = collections.defaultdict(list)
    for w in W:
        g, m, i = endpoint(w, 1.0)
        tab[(w['set'], w['robot'], w['leg'])].append(g/m)
    res['kappa_table'] = {f'{s}|{r}|L{l}': dict(n=len(v), mean=float(np.mean(v)), sd=float(np.std(v))) for (s, r, l), v in sorted(tab.items(), key=str)}
    json.dump(res, open(out_json, 'w'), indent=1)
    return res

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
