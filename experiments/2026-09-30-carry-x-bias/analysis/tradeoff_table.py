"""Honesty-vs-gate tradeoff of the candidate motion models at the L1 end (chained cases) and at the leg end (single-leg hold-out).

Reads the per-sample records of run_counterfactual.py (kept in the scratchpad / outputs, not in the repo) and writes
results/tradeoff_table.{json,txt}.
"""
import sys, json, math, collections
import numpy as np
sys.path.insert(0, '.')
from aggregate_counterfactual import chi2_band, wilson

GATE_XY = 0.07
ORDER = ['V0', 'V0_s1.5', 'V0_s2.0', 'V0_s3.0', 'V0_s4.0', 'V0_w0.03', 'V0_w0.05', 'V0_w0.08',
         'V1', 'V1_s0.0', 'V1_s0.25', 'V1_s0.5', 'V1_s0.75', 'V1_s1.5', 'V1_s2.0', 'V1_w0.03', 'V1_w0.05', 'V1_w0.08', 'V2']
DESC = {'V0': 'registered (gain 1.4004, tau 0.8)', 'V1': 'gain x0.9483', 'V2': 'gain x0.9607 + tau 1.0 s'}

def collect(recs, kind, labels, fix_mode='fuse'):
    g = collections.defaultdict(list)
    for r in recs:
        if r['kind'] != kind: continue
        if kind == 'chain':
            if r['label'] not in labels or r['fix_mode'] != fix_mode: continue
            g[r['variant']].append(dict(**r['L1'], max_sxy=r['max_sxy_L1'], max_sxy_all=max(r['max_sxy_L0'], r['max_sxy_L1']), max_syaw=max(r['max_syaw_L0'], r['max_syaw_L1'])))
        else:
            if r['label'] not in labels: continue
            g[r['variant']].append(dict(**r['end'], max_sxy=r['max_sxy'], max_sxy_all=r['max_sxy'], max_syaw=r['max_syaw']))
    return g

def row(ss):
    e = np.array([s['e'] for s in ss]); sd = np.array([s['sd'] for s in ss]); nees = np.array([s['nees'] for s in ss]); n = len(ss)
    z = e/sd; lo, hi = chi2_band(n)
    cov = (np.abs(z) < 2).mean(0)
    k = int((np.abs(z[:, 0]) < 2).sum()); w = wilson(k, n)
    z2 = (z**2).mean(0)
    return dict(z2_x=float(z2[0]), z2_y=float(z2[1]), z2_yaw=float(z2[2]), n=n, nees=float(nees.mean()), band=[lo, hi], cov_x=float(cov[0]), cov_x_ci=[w[0], w[1]], cov_y=float(cov[1]), cov_yaw=float(cov[2]),
                ex_mm=float(1000*e[:, 0].mean()), abs_ex_mm=float(1000*np.abs(e[:, 0]).mean()), sx_mm=float(1000*sd[:, 0].mean()),
                sxy_mm=float(1000*np.mean([s['sxy'] for s in ss])), peak_sxy_mm=float(1000*np.mean([s['max_sxy_all'] for s in ss])),
                gate_hits=int(sum(s['max_sxy_all'] > GATE_XY for s in ss)))

def main(rec_path, out_json, out_txt):
    recs = [json.loads(l) for l in open(rec_path)]
    tables = {
        'chain L1 end, k1g+p2 seeds 911+912 (n = 40 case-robots; fix transferred by linear-Gaussian rule)': collect(recs, 'chain', {'chain911', 'chain912'}, 'fuse'),
        'chain L1 end, same, regrasp fix kept as recorded (r1 upper bound; unphysical for r2)': collect(recs, 'chain', {'chain911', 'chain912'}, 'replace'),
        'single-leg hold-out leg end (all hold-out sets, n = 328 robot-legs)': collect(recs, 'leg', {r['label'] for r in recs if r['kind'] == 'leg' and r['label'] != 'hR2_L0'}),
    }
    res = {}
    lines = []
    for title, g in tables.items():
        lines.append('\n## ' + title)
        lines.append('variant | NEES mean [chi2 95% band] | mean z^2 x/y/yaw (honest = 1) | cov x (Wilson) | cov y/yaw | e_x mean / mean|e_x| mm | sigma_x / sigma_xy mm | peak sigma_xy over the legs mm | gate(0.07 m) hits')
        res[title] = {}
        for v in ORDER:
            if v not in g: continue
            r = row(g[v]); res[title][v] = r
            lines.append(f"{v} | {r['nees']:.2f} [{r['band'][0]:.2f}, {r['band'][1]:.2f}] | {r['z2_x']:.2f}/{r['z2_y']:.2f}/{r['z2_yaw']:.2f} | {r['cov_x']*100:.0f}% ({r['cov_x_ci'][0]*100:.0f}-{r['cov_x_ci'][1]*100:.0f}) | {r['cov_y']*100:.0f}/{r['cov_yaw']*100:.0f}% | {r['ex_mm']:+.1f} / {r['abs_ex_mm']:.1f} | {r['sx_mm']:.1f} / {r['sxy_mm']:.1f} | {r['peak_sxy_mm']:.1f} | {r['gate_hits']}/{r['n']}")
    open(out_txt, 'w').write('\n'.join(lines) + '\n')
    json.dump(res, open(out_json, 'w'), indent=1)
    print('\n'.join(lines))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
