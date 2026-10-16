"""Summarise records.jsonl of run_counterfactual.py: NEES / +-2 sigma coverage / gate exposure per data set and variant."""
import sys, json, math, collections
import numpy as np

GATE_XY = 0.07
GATE_YAW_REG = math.radians(3.0)
GATE_YAW_K1G = math.radians(5.0)

def chi2_band(n, dof=3, z=1.96):
    v = dof*n
    f = lambda zz: v*(1 - 2/(9*v) + zz*math.sqrt(2/(9*v)))**3/n
    return f(-z), f(z)

def wilson(k, n, z=1.96):
    if n == 0: return (float('nan'), float('nan'))
    p = k/n; d = 1 + z*z/n; c = (p + z*z/(2*n))/d
    h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return max(0, c-h), min(1, c+h)

def stats(samples, gate_key=None):
    """samples: list of dict(e, sd, nees, sxy) + optional max_sxy / max_syaw."""
    e = np.array([s['e'] for s in samples]); sd = np.array([s['sd'] for s in samples]); nees = np.array([s['nees'] for s in samples])
    z = e/sd
    n = len(samples)
    lo, hi = chi2_band(n)
    cov = (np.abs(z) < 2).mean(0)
    return dict(n=n, nees_mean=float(nees.mean()), nees_median=float(np.median(nees)), band=[lo, hi],
                nees_in_band=bool(lo <= nees.mean() <= hi), cov_x=float(cov[0]), cov_y=float(cov[1]), cov_yaw=float(cov[2]),
                cov_x_ci=list(wilson(int((np.abs(z[:, 0]) < 2).sum()), n)),
                ex_mean_mm=float(1000*e[:, 0].mean()), ex_abs_mm=float(1000*np.abs(e[:, 0]).mean()), ex_rms_mm=float(1000*math.sqrt((e[:, 0]**2).mean())),
                zx_abs=float(np.abs(z[:, 0]).mean()), sx_mm=float(1000*sd[:, 0].mean()), sy_mm=float(1000*sd[:, 1].mean()),
                sxy_mm=float(1000*np.mean([s['sxy'] for s in samples])), syaw_deg=float(math.degrees(sd[:, 2].mean())))

def main(rec_path, out_json, out_txt):
    recs = [json.loads(l) for l in open(rec_path)]
    G = collections.defaultdict(list)
    for r in recs:
        if r['kind'] == 'chain':
            for lvl in ('L0', 'L1start', 'L1'):
                mx = {'L0': r['max_sxy_L0'], 'L1start': 0., 'L1': r['max_sxy_L1']}[lvl]
                my = {'L0': r['max_syaw_L0'], 'L1start': 0., 'L1': r['max_syaw_L1']}[lvl]
                s = dict(r[lvl]); s['max_sxy'] = mx; s['max_syaw'] = my
                G[(f"chain:{r['label']}:{r['fix_mode']}", lvl, r['variant'])].append(s)
        else:
            s = dict(r['end']); s['max_sxy'] = r['max_sxy']; s['max_syaw'] = r['max_syaw']
            G[(f"leg:{r['label']}", 'end', r['variant'])].append(s)
    # pooled hold-out leg sets (everything but the fit-set leg L0 of hR2)
    for (g, lvl, v), ss in list(G.items()):
        if g.startswith('leg:') and g != 'leg:hR2_L0':
            G[('leg:ALL_HOLDOUT', lvl, v)] += ss
    out = {}
    lines = []
    for (g, lvl, v), ss in sorted(G.items()):
        st = stats(ss)
        st['gate_xy_hits'] = int(sum(s['max_sxy'] > GATE_XY for s in ss)); st['gate_yaw3_hits'] = int(sum(s['max_syaw'] > GATE_YAW_REG for s in ss))
        st['gate_yaw5_hits'] = int(sum(s['max_syaw'] > GATE_YAW_K1G for s in ss))
        st['max_sxy_mm_mean'] = float(1000*np.mean([s['max_sxy'] for s in ss])); st['max_sxy_mm_max'] = float(1000*np.max([s['max_sxy'] for s in ss]))
        out[f'{g}|{lvl}|{v}'] = st
    json.dump(out, open(out_json, 'w'), indent=1)
    return out

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
