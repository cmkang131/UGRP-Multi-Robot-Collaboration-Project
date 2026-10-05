#!/usr/bin/env python3
"""Held-out fix-free NEES of the base PF predictor (read-only import of the #363 pair-carry-highpose worktree) with the
a04371f6 loaded calibration: current noise vs fitted noise (+ labelled diagnostics).  Same procedure as
outputs/v98-loaded-rest-noise-20261005/nees_heldout.py (own commands only, truth only scores; blocks.json from the same
held-out segments), with ONE stated change: block-start particle spread 1e-5 m instead of 1 mm (1 mm is not negligible against
a ~2 mm sigma).  Modes: `unit` (PF vs analytic std), `nees`."""
import sys, json, math, os, hashlib, copy
sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
import numpy as np
from scipy.stats import chi2
PF_WT = '/Users/changmin/projects/ugrp-wt/pair-carry-highpose'
sys.path.insert(0, PF_WT)
from harness import owncam_localizer as oc
from harness import zone_pair_highpose_contract as zc
OUT = '/Users/changmin/projects/ugrp/outputs/v98-loaded-noise-rule-20261005'
BASE = '/Users/changmin/projects/ugrp-wt/pair-carry-highpose/experiments/2026-10-05-loaded-rest-calibration-v104/products/calibration_dev_pilot_loaded_v102_rest_v104.json'
BLOCKS = '/Users/changmin/projects/ugrp/outputs/v98-loaded-rest-noise-20261005/blocks.json'
DT = .05
INIT_STD = 1e-5
cal = json.load(open(BASE))
static_map = dict(zc.resolve('zone_wide_two_doors_final_v3')[0]); static_map.setdefault('landmarks', {'tags': []})


def affine(u, u0):
    return np.sign(u) * np.maximum(np.abs(u) - u0, 0.)


class PF(oc.OwnCamLocalizer):
    """#378 PF subclass: affine dead zone on the issued command (zone_pair_deadband), then the stock predictor."""
    def predict_to(self, t):
        db = self.params['motion_loaded']['deadband']
        issued = self.cmd
        self.cmd = affine(issued, np.asarray(db['u0'], float))
        try:
            return super().predict_to(t)
        finally:
            self.cmd = issued


def build(seed, noise, n, init_std=INIT_STD, yaw_zero=False):
    params = json.loads(json.dumps(oc.DEFAULT_PARAMS))
    params['particles'] = n
    params['motion'] = cal['params']['motion']
    ml = json.loads(json.dumps(cal['params']['motion_loaded']))
    ml['noise_abs'], ml['noise_rel'] = list(noise['abs']), list(noise['rel'])
    if yaw_zero:
        ml['noise_abs'][2] = 0.; ml['yaw_bias_std_rad_s'] = 0.
    params['motion_loaded'] = ml
    pf = PF(static_map, params, seed=seed)
    pf._init_std = init_std
    return pf


def start(pf, pose0):
    pf.px = np.tile(pose0, (pf.n, 1)) + pf.rng.normal(size=(pf.n, 3)) * np.array([pf._init_std] * 3)
    pf.scale = np.ones((pf.n, 3)); pf.logw = np.zeros(pf.n)
    pf.load.loaded = True; pf.initialized = True; pf.t = 0.; pf.vel = np.zeros(3)
    pf._init_plant_state()
    pf.logw = pf._map_logprior(pf.px)


def run_block(pf, pose0, segs, sign, axis):
    start(pf, pose0)
    out = {}; t = 0.
    for name, (u, dur) in segs:
        for k in range(int(round(dur / .1))):
            cmd = np.zeros(3); cmd[0 if axis == 'forward' else 1] = sign * u
            pf.command({'kind': 'mecanum', 't': round(t + .1 * k, 6), 'forward': cmd[0], 'left': cmd[1], 'turn': 0., 'duration_s': .15})
        t += dur
        pf.predict_to(t)
        out[name] = (t, pf.estimate())
    return out


def nees(est, truth_xy):
    e = np.array(truth_xy) - np.array([est['x'], est['y']])
    C = np.array(est['cov'])[:2, :2]
    return float(e @ np.linalg.solve(C, e)), e, C


def unit_check():
    """PF predictor vs the analytic discrete sd (units check): constant forward / left command, 20000 particles, zero init spread,
    sd of particle positions along the commanded body axis (yaw 0) at 1,2,4,7 s; analytic = DT*sqrt(sum (rel|v_k|+abs)^2) with the PF's own v_k."""
    prop = json.load(open(f'{OUT}/fit_noise_loaded_result.json'))['proposed']
    res = {}
    for label, noise in (('fitted', prop), ('current', {'abs': cal['params']['motion_loaded']['noise_abs'], 'rel': cal['params']['motion_loaded']['noise_rel']})):
        for axis, ai in (('forward', 0), ('left', 1)):
            pf = build(7, noise, 20000, init_std=0.)
            start(pf, np.array([3.3, -.65, 0.]))
            u = np.zeros(3); u[ai] = .05
            ss = 0.; rows = {}
            for k in range(1, 141):                       # 7 s in 0.05 s steps; command refreshed every 0.1 s, lease .15
                t = k * DT
                if k % 2 == 1:
                    pf.command({'kind': 'mecanum', 't': round(t - DT, 6), 'forward': u[0], 'left': u[1], 'turn': 0., 'duration_s': .15})
                pf.predict_to(t)
                ss += (noise['rel'][ai] * abs(pf.vel[ai]) + noise['abs'][ai]) ** 2
                if k in (20, 40, 80, 140):
                    px = pf.px
                    rows[f't={t:g}s'] = {'pf_sd_along_mm': 1e3 * float(np.std(px[:, ai])), 'analytic_sd_along_mm': 1e3 * DT * math.sqrt(ss),
                                          'pf_sd_cross_mm': 1e3 * float(np.std(px[:, 1 - ai]))}
            res[f'{label}/{axis}'] = rows
    json.dump(res, open(f'{OUT}/unit_check_result.json', 'w'), indent=1, sort_keys=True)
    print(json.dumps(res, indent=1))


CONDS = {}


def main_nees(n_particles=4000, seeds=5):
    fit = json.load(open(f'{OUT}/fit_noise_loaded_result.json'))
    ml = cal['params']['motion_loaded']
    cur = {'abs': ml['noise_abs'], 'rel': ml['noise_rel']}
    prop = fit['proposed']
    yaw_meas = fit['yaw_idle_diagnostic']['abs']
    conds = {'current': (cur, {}), 'proposed': (prop, {}),
             'proposed_init1mm': (prop, {'init_std': 1e-3}),
             'diag_yaw0': (prop, {'yaw_zero': True}),
             'diag_yawmeas': ({'abs': prop['abs'][:2] + [yaw_meas], 'rel': prop['rel']}, {})}
    blocks = json.load(open(BLOCKS))
    rows = []
    for b in blocks:
        plan_segs = [('step_end', (b['u'], b['step_s'])), ('block_end', (0., b['coast_s']))]
        if b['end_hold_s']:
            plan_segs.append(('end_hold', (0., b['end_hold_s'])))
        for k in (0, 1):
            sign = 1. if k == 0 else -1.
            T = np.array(b['truth_r%d' % (k + 1)])
            for cond, (noise, kw) in conds.items():
                for seed in range(seeds):
                    pf = build(1000 + seed, noise, n_particles, **kw)
                    res = run_block(pf, T[0], plan_segs, sign, b['axis'])
                    for name, (tc, est) in res.items():
                        nv, e, C = nees(est, T[round(tc / DT), :2])
                        rows.append(dict(run=b['run'], role=b['role'], axis=b['axis'], u=b['u'], robot=f'r{k+1}', cond=cond, seed=seed,
                                         checkpoint=name, nees=nv, err_mm=1000 * float(np.linalg.norm(e)),
                                         std_xy_mm=1000 * math.sqrt(max(C[0, 0] + C[1, 1], 0.)),
                                         sd_major_mm=1000 * math.sqrt(max(np.linalg.eigvalsh(C)[1], 0.)),
                                         sd_minor_mm=1000 * math.sqrt(max(np.linalg.eigvalsh(C)[0], 0.))))
    json.dump(rows, open(f'{OUT}/nees_rows.json', 'w'))
    summarize(rows, list(conds))


def summarize(rows, conds):
    lo2, hi2, up = chi2.ppf(.025, 2), chi2.ppf(.975, 2), chi2.ppf(.95, 2)
    summ = {'chi2_2': {'lo2.5': lo2, 'hi97.5': hi2, 'up95': up}, 'table': {}, 'bar_shalom': {}}
    for ck in ('step_end', 'block_end', 'end_hold'):
        for cond in conds:
            sel = [r for r in rows if r['checkpoint'] == ck and r['cond'] == cond]
            v = np.array([r['nees'] for r in sel])
            summ['table'][f'{ck}/{cond}'] = {'n': len(v), 'mean_nees': float(v.mean()), 'median_nees': float(np.median(v)),
                'frac_in_2sided95': float(np.mean((v >= lo2) & (v <= hi2))), 'frac_le_95': float(np.mean(v <= up)),
                'frac_below_2.5': float(np.mean(v < lo2)), 'frac_above_97.5': float(np.mean(v > hi2)),
                'std_xy_mm': float(np.mean([r['std_xy_mm'] for r in sel])), 'sd_major_mm': float(np.mean([r['sd_major_mm'] for r in sel])),
                'sd_minor_mm': float(np.mean([r['sd_minor_mm'] for r in sel])), 'err_mm': float(np.mean([r['err_mm'] for r in sel]))}
            # Bar-Shalom averaged NEES: truth realisations = blocks (per robot); seeds averaged first (PF sampling only)
            for robot in ('r1', 'r2'):
                per_block = {}
                for r in sel:
                    if r['robot'] == robot:
                        per_block.setdefault((r['run'], r['role'], r['u']), []).append(r['nees'])
                vals = np.array([np.mean(x) for x in per_block.values()])
                N = len(vals)
                lo, hi = chi2.ppf(.025, 2 * N) / N, chi2.ppf(.975, 2 * N) / N
                summ['bar_shalom'][f'{ck}/{cond}/{robot}'] = {'N_blocks': N, 'avg_nees': float(vals.mean()), 'interval95': [float(lo), float(hi)],
                    'inside': bool(lo <= vals.mean() <= hi), 'below': bool(vals.mean() < lo), 'above': bool(vals.mean() > hi)}
    for split_name, key in (('role', 'role'), ('axis', 'axis')):
        for cond in ('current', 'proposed'):
            for ck in ('step_end', 'block_end'):
                for val in sorted({r[key] for r in rows}):
                    sel = [r['nees'] for r in rows if r['cond'] == cond and r['checkpoint'] == ck and r[key] == val]
                    summ['table'][f'{ck}/{cond}/{key}={val}'] = {'n': len(sel), 'mean_nees': float(np.mean(sel)), 'frac_in_2sided95': float(np.mean([(x >= lo2) and (x <= hi2) for x in sel])),
                                                                'frac_above_97.5': float(np.mean([x > hi2 for x in sel]))}
    json.dump(summ, open(f'{OUT}/nees_summary.json', 'w'), indent=1, sort_keys=True)
    for k, v in summ['table'].items():
        if '=' not in k:
            print(f"{k:28s} n={v['n']:4d} mean={v['mean_nees']:9.4f} med={v['median_nees']:8.4f} in95={v['frac_in_2sided95']:.3f} le95={v['frac_le_95']:.3f} "
                  f"below={v['frac_below_2.5']:.3f} above={v['frac_above_97.5']:.3f} sd_xy={v['std_xy_mm']:.2f} maj={v['sd_major_mm']:.2f} min={v['sd_minor_mm']:.2f} err={v['err_mm']:.2f}")
    for k, v in summ['bar_shalom'].items():
        print(k, v)


if __name__ == '__main__':
    {'unit': unit_check, 'nees': main_nees}[sys.argv[1]]()
