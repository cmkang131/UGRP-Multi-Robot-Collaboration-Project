#!/usr/bin/env python3
"""hR result by leg (L0-L6) + PF honesty + door-guard margin numbers for failures. Usage: hR_analysis.py <ghR raw> [<ghRL7 raw>]
GT is the analysis target only. Guard requirement is the documented PairSweepGuard margin
(BASE 0.02 + residual 0.015 + 2 sigma_xy + 2 sigma_yaw * 0.18 lever), an approximation of the guard actually used."""
import json, math, re, sys, collections
from pathlib import Path
import numpy as np
DOOR_LO, DOOR_HI = -0.20, 0.30
HALF_W = 0.10          # chassis half width used only to express the lateral clearance (approximate)


def wrap(a):
    return (a + math.pi)%(2*math.pi) - math.pi


def case_dir(root, cid):
    return root/'cases'/cid.replace('@', '_').replace(':', '_').replace('/', '_')


def analyse(root):
    rows = [json.loads(l) for l in open(root/'cases.jsonl')]
    bylg = collections.defaultdict(list)
    for r in rows:
        m = re.search(r':L(\d)', r['case_id'])
        bylg[int(m.group(1)) if m else 0].append(r)
    staged = [r for r in rows if r.get('entry_sim_s') is not None]
    print(f'== {root.name}: {sum(r["passed"] for r in rows)}/{len(rows)} passed; staged (IK envelope excluded) {sum(r["passed"] for r in staged)}/{len(staged)}')
    print('leg  pass  causes')
    for k in sorted(bylg):
        rs = bylg[k]
        c = collections.Counter(r['cause'] + (':' + r['cause_sub'] if r.get('cause_sub') else '') for r in rs if not r['passed'])
        print(f' L{k}  {sum(r["passed"] for r in rs)}/{len(rs)}  {dict(c)}')
    end, allz = [], []
    print('failures: id | fail t | robot | PF sigma_xy sigma_yaw(deg) | GT y | PF y | door clearance GT (m) | door clearance by PF y (m) | guard need (m) | reading')
    for r in rows:
        if r.get('entry_sim_s') is None:      # staging infeasible (STAGING_IK_ENVELOPE): no stage run, excluded from the staged denominator
            continue
        d = case_dir(root, r['case_id'])
        tr = [json.loads(x) for x in open(d/'eval_only/trace.jsonl')]
        tex = max(r['exit_sim_s'].values()) if r.get('exit_sim_s') else tr[-1]['t']
        pf = [x for x in tr if 'pf' in x and r['entry_sim_s'] <= x['t'] <= tex + 1e-6]
        for rid in ('r1', 'r2'):
            sm = []
            for x in pf:
                p = x['pf'][rid]
                if not p.get('initialized'):
                    continue
                g = x['robots'][rid]
                e = np.array([g[0] - p['x'], g[1] - p['y'], wrap(g[2] - p['yaw'])])
                C = np.array(p['cov'])
                sm.append((float(e@np.linalg.solve(C, e)), np.abs(e)/np.sqrt(np.diag(C))))
            if sm:
                end.append(sm[-1])
        if not r['passed']:
            x = pf[-1]; ff = r.get('first_failure') or {}
            rid = ff.get('robot_id', 'r2')
            p = x['pf'][rid]; g = x['robots'][rid]
            sxy, syaw = p['std_xy_m'], p['std_yaw_rad']
            need = .02 + .015 + 2*sxy + 2*syaw*.18
            clear = min(g[1] - DOOR_LO, DOOR_HI - g[1]) - HALF_W if 1.6 < g[0] < 2.9 else float('nan')
            pclear = min(p['y'] - DOOR_LO, DOOR_HI - p['y']) - HALF_W if 1.6 < g[0] < 2.9 else float('nan')
            reading = ('sigma gate' if r['cause'] == 'SELF_POSE_UNCERTAIN' else
                       'true tight (GT clearance < need)' if clear < need else
                       'PF bias false alarm (GT clearance >= need, PF-based < need)' if pclear < need else 'marginal')
            print(' ', r['case_id'].split(':', 2)[2], '| %.1f' % ff.get('sim_s', float('nan')), '|', rid, '| %.3f %.2f' % (sxy, math.degrees(syaw)),
                  '| %.3f %.3f' % (g[1], p['y']), '| %.3f | %.3f | %.3f' % (clear, pclear, need), '|', r['cause'], '|', reading)
    if end:
        n = np.array([e[0] for e in end]); z = np.array([e[1] for e in end])
        print('PF honesty at last sample per case-robot: n=%d meanNEES=%.2f median=%.2f cov2σ x/y/yaw=%s' % (len(n), n.mean(), np.median(n), (z <= 2).mean(0).round(3)))


if __name__ == '__main__':
    for a in sys.argv[1:]:
        analyse(Path(a))
