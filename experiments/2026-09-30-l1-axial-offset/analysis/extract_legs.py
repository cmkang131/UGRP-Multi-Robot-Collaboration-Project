#!/usr/bin/env python3
"""Offline extraction of the chain L0/L1 carry legs from existing raw (NO new physics).

For every chain case (stage probe ``--stage chain --chain-stop-leg 1``) of the listed raw directories this writes one JSON row with
everything the L1-axial-offset diagnosis needs: the placement and the order sheet, the planned legs, the commanded forward windows
(from ``commands.json``), the ground-truth beam / robot trace at the key times (from ``eval_only/trace.jsonl``, EVAL ONLY, never a
controller input), the fitted first-order-lag plant of every forward leg and the PF estimates at the leg boundaries.

Usage: extract_legs.py [--out results/leg_table.json]
Raw stays in /Users/changmin/projects/ugrp/outputs (read only).
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

RAW = Path('/Users/changmin/projects/ugrp/outputs')
COHORTS = {          # label -> (raw dir, note)
    'cA': ('b-v6h-gain-69c2a99a-cA', 'fixed base sheet, k1g+p2f'),
    'cB': ('b-v6h-gain-69c2a99a-cB', 'fixed base sheet, k1g+p2f+gain'),
    'rA': ('b-v6h-gain-64abed88-rA', 'recorded hR2 starts, k1g+p2f'),
    'rB': ('b-v6h-gain-64abed88-rB', 'recorded hR2 starts, k1g+p2f+gain'),
    'sA': ('b-v6h-gain-b95d2016-sA', 'sheet = beam rounded, k1g+p2f'),
    'sB': ('b-v6h-gain-b95d2016-sB', 'sheet = beam rounded, k1g+p2f+gain'),
    'cC': ('b-v6h-gain-69c2a99a-cC', 'fixed base sheet, k1+p2f+gain'),
    'cD': ('b-v6h-gain-69c2a99a-cD', 'fixed base sheet, k2+p2f+gain'),
    'cF': ('b-v6h-gain-69c2a99a-cF', 'fixed base sheet, k2+p2f'),
    'eK1g': ('door-relax-envelope-fdd35cee-chK1g', 'recorded hR2 starts, k1g (PR #283)'),
    'eK1gP2': ('door-relax-envelope-77fde5f6-chK1gP2', 'recorded hR2 starts, k1g+p2 (PR #283)'),
    'eK1gP1': ('door-relax-envelope-fdd35cee-chK1gP1', 'recorded hR2 starts, k1g+p1 (PR #283)'),
    'eBase': ('door-relax-envelope-fdd35cee-chBase', 'recorded hR2 starts, registered b-v6g'),
}
FWD_MIN = 0.03           # |forward command| of a carry leg is SPEED/FORWARD_GAIN = 0.0382


def case_dir(root, cid):
    return root / 'cases' / cid.replace('@', '_').replace(':', '_').replace('/', '_')


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def forward_runs(cmds):
    """Contiguous constant-forward runs of the mecanum commands: [(t_first, t_last, forward)]."""
    runs, cur = [], None
    for c in cmds:
        if c.get('kind') != 'mecanum':
            continue
        fw = c.get('forward', 0.)
        pure = abs(fw) > FWD_MIN and abs(c.get('left', 0.)) < 1e-9 and abs(c.get('turn', 0.)) < 1e-9
        if pure and cur is not None and abs(fw - cur[2]) < 1e-9 and c['t'] - cur[1] < 0.25:
            cur[1] = c['t']
        elif pure:
            cur = [c['t'], c['t'], fw]
            runs.append(cur)
        else:
            cur = None
    return runs


def lag_x(t, t0, T, v, tau, tau_s, delay):
    """Displacement of a first-order-lag drive (command from t0 for T, then zero) with an actuation delay."""
    x = np.zeros_like(t, dtype=float)
    ta = t0 + delay
    m1 = (t >= ta) & (t <= ta + T)
    s = t[m1] - ta
    x[m1] = v * (s - tau * (1 - np.exp(-s / tau)))
    vT = v * (1 - math.exp(-T / tau))
    xT = v * (T - tau * (1 - math.exp(-T / tau)))
    m2 = t > ta + T
    s = t[m2] - (ta + T)
    x[m2] = xT + vT * tau_s * (1 - np.exp(-s / tau_s))
    return x


def fit_plant(t, x, t0, T):
    m = (t >= t0 - 0.3) & (t <= t0 + T + 4.0)
    tt, xx = t[m], x[m] - x[m][0]

    def res(p):
        return lag_x(tt, t0, T, p[0], p[1], p[2], p[3]) - xx
    sol = least_squares(res, [0.05, 0.8, 0.1, 0.0], bounds=([0.01, 0.05, 0.005, -0.3], [0.2, 3.0, 1.0, 0.5]))
    return {'v_ss': float(sol.x[0]), 'tau': float(sol.x[1]), 'tau_stop': float(sol.x[2]), 'delay': float(sol.x[3]),
            'rms_mm': float(1000 * math.sqrt(np.mean(sol.fun ** 2)))}


def at(tr_t, arr, t):
    i = int(np.searchsorted(tr_t, t))
    i = min(max(i, 0), len(tr_t) - 1)
    return arr[i]


def own_gt(entry):
    if not entry:
        return None
    o, g = entry.get('own'), entry.get('gt')
    if not o or not g:
        return None
    return {'t': entry['sim_s'], 'own': o['xyyaw'], 'own_std_xy': o.get('std_xy_m'), 'own_std_yaw': o.get('std_yaw_rad'), 'gt_robots': g['robots'],
            'gt_beam': g['beam_xyz'], 'gt_beam_yaw': g['beam_yaw']}


def one_case(root, row, label):
    d = case_dir(root, row['case_id'])
    if not (d / 'result.json').exists() or not (d / 'eval_only/trace.jsonl').exists():
        return None
    case = json.load(open(d / 'case.json'))
    res = json.load(open(d / 'result.json'))
    cmds = json.load(open(d / 'commands.json'))
    tr = [json.loads(x) for x in open(d / 'eval_only/trace.jsonl')]
    t = np.array([r['t'] for r in tr])
    bx = np.array([r['beam_xyz'][0] for r in tr])
    by = np.array([r['beam_xyz'][1] for r in tr])
    byaw = np.array([r['beam_yaw'] for r in tr])
    rob = {rid: np.array([r['robots'][rid] for r in tr]) for rid in ('r1', 'r2')}
    legs = ((res.get('row') or {}).get('chain') or {}).get('legs') or []
    raw = res.get('chain_raw') or {}
    sheet = case['coarse_order_sheet']['beam_xyyaw']
    out = {'label': label, 'case_id': row['case_id'], 'cell': row['cell'], 'seed': row['seed'], 'policy': case.get('policy_id'),
           'door_relax': case.get('door_relax'), 'gain_fix': case.get('carry_gain_fix'), 'progress': case.get('progress_relax'),
           'beam_place': case['beam_xyyaw'], 'sheet': sheet, 'prior_r1': case['prior']['r1']['mean_xyyaw'], 'prior_r2': case['prior']['r2']['mean_xyyaw'],
           'passed': bool(res['evaluation']['passed']), 'category': res['evaluation']['category'], 'legs': []}
    runs = {rid: forward_runs(cmds[rid]) for rid in ('r1', 'r2')}
    out['n_fwd_runs'] = {rid: len(runs[rid]) for rid in runs}
    out['gt_after_lift'] = {'beam': res['teacher']['gt_after_lift']['beam_xyz'], 'beam_yaw': res['teacher']['gt_after_lift']['beam_yaw'],
                            'robots': res['teacher']['gt_after_lift']['robots']}
    out['prior_seeded'] = {rid: res['prior_seeded'][rid]['estimate'] for rid in ('r1', 'r2')}
    for k, leg in enumerate(legs[:2]):
        if not leg.get('recorded'):
            out['legs'].append({'leg': k, 'recorded': False})
            continue
        L = {'leg': k, 'recorded': True, 'planned_m': leg['planned_length_m'], 'end_error_m': leg['end_error_m'], 'along_error_m': leg['along_error_m'],
             'cross_track_m': leg['cross_track_m'], 'travel_m': leg['travel_m'], 'yaw_drift_deg': leg['yaw_drift_deg'],
             'start_sim_s': leg['start_sim_s'], 'end_sim_s': leg['end_sim_s']}
        for rid in ('r1', 'r2'):
            L[rid] = {'start': own_gt(raw[rid]['leg_start'].get(str(k))), 'end': own_gt(raw[rid]['leg_end'].get(str(k)))}
        # commanded forward window of this leg (one long run inside [start, end] per robot)
        inleg = {}
        for rid in ('r1', 'r2'):
            cand = [r for r in runs[rid] if r[0] >= leg['start_sim_s'] - 1e-6 and r[1] <= leg['end_sim_s'] + 0.3]
            inleg[rid] = max(cand, key=lambda r: r[1] - r[0]) if cand else None
        if inleg['r1'] and inleg['r2']:
            t0, t1 = inleg['r1'][0], inleg['r1'][1] + 0.1
            T = t1 - t0
            L['cmd'] = {'t0': t0, 't1': t1, 'T_s': T, 'forward_r1': inleg['r1'][2], 'forward_r2': inleg['r2'][2],
                        'same_window': abs(inleg['r1'][0] - inleg['r2'][0]) < 1e-6 and abs(inleg['r1'][1] - inleg['r2'][1]) < 1e-6}
            L['plant'] = fit_plant(t, bx, t0, T)
            sel = lambda tq, arr: float(at(t, arr, tq))
            w = (t >= t0) & (t <= t1 + 3.0)
            dxw = np.diff(bx[w])
            drift = {rid: float(np.sum(dxw * np.tan(wrap(rob[rid][w][:-1, 2] - (math.pi if rid == 'r2' else 0.))))) for rid in rob}
            L['drift'] = {'dy_beam': float(by[w][-1] - by[w][0]), 'dy_pred_from_robot_heading': drift}
            L['gt'] = {'x_at_t0': sel(t0, bx), 'x_at_t1': sel(t1, bx), 'x_rest': sel(t1 + 3.0, bx),
                       'y_at_t0': sel(t0, by), 'y_at_t1': sel(t1, by), 'y_rest': sel(t1 + 3.0, by),
                       'yaw_at_t0': sel(t0, byaw), 'yaw_rest': sel(t1 + 3.0, byaw),
                       'robot_yaw_t0': {rid: float(at(t, rob[rid][:, 2], t0)) for rid in rob},
                       'robot_yaw_rest': {rid: float(at(t, rob[rid][:, 2], t1 + 3.0)) for rid in rob},
                       'robot_x_t0': {rid: float(at(t, rob[rid][:, 0], t0)) for rid in rob},
                       'robot_y_t0': {rid: float(at(t, rob[rid][:, 1], t0)) for rid in rob},
                       'robot_x_rest': {rid: float(at(t, rob[rid][:, 0], t1 + 3.0)) for rid in rob},
                       'robot_y_rest': {rid: float(at(t, rob[rid][:, 1], t1 + 3.0)) for rid in rob}}
        out['legs'].append(L)
    # PF rows (estimate vs GT robot pose) for the phase analysis of the y / yaw bias
    pf = []
    for r in tr:
        if 'pf' in r:
            row_ = {'t': r['t'], 'state': (r.get('states') or {}).get('r1')}
            for rid in ('r1', 'r2'):
                p = r['pf'].get(rid)
                if p and p.get('initialized'):
                    g = r['robots'][rid]
                    row_[rid] = [p['x'] - g[0], p['y'] - g[1], wrap(p['yaw'] - g[2]), p['std_xy_m'], p['std_yaw_rad']]
            pf.append(row_)
    out['pf_err'] = pf
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True, help='full table (about 20 MB with the PF traces): keep it OUTSIDE the repository')
    ap.add_argument('--manifest', help='write the raw-directory manifest (dir, cases, sha256 of cases.jsonl) here')
    ap.add_argument('--csv', help='write the slim per-case table here (committed)')
    ap.add_argument('--labels', nargs='*')
    a = ap.parse_args()
    table, manifest = [], {}
    for label, (dname, note) in COHORTS.items():
        if a.labels and label not in a.labels:
            continue
        root = RAW / dname
        rows = [json.loads(l) for l in open(root / 'cases.jsonl')]
        n = 0
        for row in rows:
            r = one_case(root, row, label)
            if r is not None:
                table.append(r)
                n += 1
        manifest[label] = {'dir': dname, 'note': note, 'cases': n, 'cases_jsonl_sha256': sha256(root / 'cases.jsonl'),
                           'cases_jsonl_bytes': (root / 'cases.jsonl').stat().st_size}
        print(label, dname, n)
    Path(a.out).write_text(json.dumps({'manifest': manifest, 'rows': table}, default=float))
    print('wrote', a.out, len(table))
    if a.manifest:
        Path(a.manifest).write_text(json.dumps(manifest, indent=1) + '\n')
    if a.csv:
        write_csv(a.csv, table)


def write_csv(path, table):
    import csv
    cols = ['label', 'cell', 'seed', 'policy', 'gain_fix', 'sheet_x', 'place_x', 'place_y', 'place_yaw_deg', 'dx_mm', 'end_ok_L0_L1',
            'T0_cmd_s', 'T1_cmd_s', 'L0_travel_mm', 'L1_travel_mm', 'L0_along_mm', 'L1_along_mm', 'L0_cross_mm', 'L1_cross_mm', 'L0_end_mm', 'L1_end_mm',
            'L1_y_signed_mm', 'v_ss_mm_s', 'tau_s', 'tau_stop_s']
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in table:
            if len(r['legs']) < 2 or not all(L.get('recorded') for L in r['legs']):
                continue
            L0, L1 = r['legs']
            ys = max([L1[k]['end'] for k in ('r1', 'r2') if L1[k]['end']], key=lambda s: s['t'])['gt_beam'][1] - 0.05
            w.writerow([r['label'], r['cell'], r['seed'], r['policy'], r['gain_fix'], r['sheet'][0], r['beam_place'][0], r['beam_place'][1],
                        round(math.degrees(r['beam_place'][2]), 3), round(1000 * (r['beam_place'][0] - r['sheet'][0]), 2), int(L0['end_error_m'] <= 0.1 and L1['end_error_m'] <= 0.1),
                        L0.get('cmd', {}).get('T_s'), L1.get('cmd', {}).get('T_s'), round(1000 * L0['travel_m'], 2), round(1000 * L1['travel_m'], 2),
                        round(1000 * L0['along_error_m'], 2), round(1000 * L1['along_error_m'], 2), round(1000 * L0['cross_track_m'], 2),
                        round(1000 * L1['cross_track_m'], 2), round(1000 * L0['end_error_m'], 2), round(1000 * L1['end_error_m'], 2), round(1000 * ys, 2),
                        round(1000 * L1['plant']['v_ss'], 3) if L1.get('plant') else '', round(L1['plant']['tau'], 4) if L1.get('plant') else '',
                        round(L1['plant']['tau_stop'], 4) if L1.get('plant') else ''])


if __name__ == '__main__':
    main()
