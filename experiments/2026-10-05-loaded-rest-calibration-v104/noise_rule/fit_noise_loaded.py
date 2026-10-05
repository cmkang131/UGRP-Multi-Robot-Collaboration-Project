#!/usr/bin/env python3
"""Loaded-motion process-noise measurement rule (params.motion_loaded.noise_abs / noise_rel, forward + left).

Offline, read-only: imports the #378 fit module from the calib-loaded-gain worktree (no edits, no bytecode), reads the v102 raw
truth (eval_only/trajectory.jsonl) ONLY as a calibration target (same use as #376/#378).  No simulator, no controller.

Rule = #376 `fit_noise` moment matching, applied to the loaded v102 FIT split (roles fit, fit_duration):
  residual  = truth body-frame displacement increment over an H-window  -  calibrated-mean-model increment (simulate()),
              body frame at the window start (per axis: forward, left; turn = truth yaw increment, idle only).
  groups    = (axis, kind, H), kind in {driven, idle}; settled drive only (>= 3 lags into the step); rest windows excluded
              because params.motion_loaded.rest_noise=false means the PF injects no noise at rest.
  implied s = RMS(residual) / sqrt(DT*H)      [PF: white per-step velocity noise std s, position += v*dt  =>  sd(pos,H) = s*sqrt(DT*H)]
  fit       = NNLS  s ~ rel*vbar + abs  (weights sqrt(n)), vbar = mean |MODEL velocity| over the window (the PF uses |self.vel|),
  floor     = abs >= NOISE_ABS_FLOOR = .002  (the #376 floor, unchanged).
Cross-check: exact Gaussian ML of the same model on the same windows (composite likelihood; windows overlap).
"""
import sys, json, math, hashlib
sys.dont_write_bytecode = True
import numpy as np
from scipy.optimize import nnls, minimize

WT = '/Users/changmin/projects/ugrp-wt/calib-unloaded-gain'
sys.path.insert(0, WT)
from scripts import fit_loaded_gain_calibration as F      # read-only import
RAW = '/Users/changmin/projects/ugrp/outputs/calib-loaded-gain-v102-274a6206-20261005T0306Z'
BASE = '/Users/changmin/projects/ugrp-wt/pair-carry-highpose/experiments/2026-10-05-loaded-rest-calibration-v104/products/calibration_dev_pilot_loaded_v102_rest_v104.json'
BASE_SHA = 'a04371f614bd7f6f7583ef4f4121abce1c337fd5652899dbfe0fe6df1703f926'
OUT = '/Users/changmin/projects/ugrp/outputs/v98-loaded-noise-rule-20261005'
DT = .05
HORIZONS_S = (.5, 1., 2.)             # #376 fit horizons
COVERAGE_HORIZONS_S = (1., 2., 4.)    # #376 coverage horizons
NOISE_ABS_FLOOR = .002                # #376 (scripts/fit_unloaded_gain_calibration.py l.52), unchanged
POSE_RESOLUTION_M = 1e-6
ACCEPT_COVERAGE_2SIGMA = .90          # #376 ACCEPT['coverage_2sigma']
MIN_GROUP_N = 5
AXES = ('forward', 'left')
plan = F.env.protocol()
I0 = round(F.env.PREP_END_S / DT)


def sha_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


cal = json.load(open(BASE))
assert sha_file(BASE) == BASE_SHA
ML = cal['params']['motion_loaded']
AXP = {'forward': {'g': ML['gain'][0][0], 'tau': ML['tau_axis_s'][0], 'shape': {'u0': ML['deadband']['u0'][0]}},
       'left': {'g': ML['gain'][1][1], 'tau': ML['tau_axis_s'][1], 'shape': {'u0': ML['deadband']['u0'][1]}}}
TAU_STOP = ML['tau_stop_s']
CUR_ABS, CUR_REL = np.array(ML['noise_abs']), np.array(ML['noise_rel'])


def traj(rid):
    rows = [json.loads(l) for l in open(f'{RAW}/{rid}/{rid}/eval_only/trajectory.jsonl')]
    return np.array([r['qpos'] for r in rows])


def pose(q, k):
    o = 17 * k
    return np.column_stack((q[:, o], q[:, o + 1], [F.qyaw(*q[i, o + 3:o + 7]) for i in range(len(q))]))


def sim_xv(run):
    """F.simulate() positions plus the model velocity at every grid point (v[k] = (x[k]-x[k-1])/DT; v[0] = 0)."""
    x = F.simulate(run, 'A', AXP[run['axis']], TAU_STOP)
    v = np.concatenate(([0.], np.diff(x) / DT))
    return x, v


def wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def load_all():
    out = []
    for rid in ('latA', 'latB', 'fwdA', 'fwdB'):
        q = traj(rid)
        run = F.env.run_row(plan, rid)
        x, v = sim_xv(run)
        assert np.allclose(x, F.simulate(run, 'A', AXP[run['axis']], TAU_STOP))
        P = [pose(q, 0), pose(q, 1)]
        for k in (0, 1):
            out.append({'rid': rid, 'k': k, 'run': run, 'P': P[k], 'x': x, 'v': v, 'sg': 1. if k == 0 else -1.})
    return out


def block_arrays(R, w):
    """Window arrays on the 0.05 s grid j = 0..b-a: truth world pose, model along-axis displacement/velocity."""
    a, b = I0 + w['a'], I0 + w['b']
    ia = 0 if R['run']['axis'] == 'forward' else 1
    return {'P': R['P'][a:b + 1], 'mx': R['sg'] * (R['x'][w['a']:w['b'] + 1] - R['x'][w['a']]),
            'mv': np.abs(R['v'][w['a']:w['b'] + 1]), 'axis_i': ia}


def sub_residuals(B, j, n, frame='sub'):
    """Residual (truth - model) increment over [j, j+n] in the body frame at j (frame='sub') or at window start (frame='block'),
    for forward, left, turn (turn: truth yaw increment; the calibrated mean model has no yaw response)."""
    P, ia = B['P'], B['axis_i']
    j = np.asarray(j)
    y = P[j if frame == 'sub' else 0, 2]
    c, s = np.cos(y), np.sin(y)
    d = P[j + n, :2] - P[j, :2]
    body = np.column_stack((c * d[:, 0] + s * d[:, 1], -s * d[:, 0] + c * d[:, 1]))
    m = np.zeros_like(body)
    m[:, ia] = B['mx'][j + n] - B['mx'][j]
    e = body - m
    return e[:, 0], e[:, 1], wrap(P[j + n, 2] - P[j, 2])


def noise_groups(items, frame='sub', by_level=False):
    """(axis, kind, H) -> arrays [vbar, residual] (mirrors #376 noise_groups; 'rest' dropped, see module doc)."""
    groups = {}
    tau_max = max(AXP[a]['tau'] for a in AXES)
    for R, w in items:
        B = block_arrays(R, w)
        nrow = len(B['P'])
        drive_end = w['b_step'] - w['a']
        for H in HORIZONS_S + tuple(h for h in COVERAGE_HORIZONS_S if h not in HORIZONS_S):
            n = round(H / DT)
            j = np.arange(0, nrow - n)
            ef, el, et = sub_residuals(B, j, n, frame)
            vb_axis = np.array([B['mv'][jj:jj + n + 1].mean() for jj in j])
            for axis_i, (axis, e) in enumerate((('forward', ef), ('left', el), ('turn', et))):
                commanded = (axis == R['run']['axis'])
                settle = math.ceil(3 * (AXP[axis]['tau'] if commanded else tau_max) / DT)
                ok = (j + n <= drive_end) & (j >= settle)
                if not ok.any():
                    continue
                kind = 'driven' if commanded else 'idle'
                vb = vb_axis if commanded else np.zeros_like(vb_axis)
                key = (axis, kind, H)
                rows = np.column_stack((vb[ok], e[ok]))
                if by_level:
                    key = key + (round(abs(w['value']), 4),)
                groups.setdefault(key, []).append(rows)
    return {k: np.vstack(v) for k, v in groups.items()}


def fit_moment(groups, axis, horizons=HORIZONS_S):
    xs, ys, ws, detail = [], [], [], {}
    for (ax, kind, H), v in sorted(groups.items()):
        if ax != axis or H not in horizons or len(v) < MIN_GROUP_N:
            continue
        s = math.sqrt(np.mean(v[:, 1] ** 2)) / math.sqrt(DT * H)
        xs.append(float(np.mean(v[:, 0]))); ys.append(s); ws.append(len(v))
        detail[f'{kind}/H{H}'] = {'n': len(v), 'vbar': xs[-1], 'implied_std': s}
    w = np.sqrt(np.array(ws, float))
    A = np.column_stack((xs, np.ones(len(xs)))) * w[:, None]
    sol, _ = nnls(A, np.array(ys) * w)
    return {'rel': float(sol[0]), 'abs_raw': float(sol[1]), 'abs': float(max(sol[1], NOISE_ABS_FLOOR)),
            'floor_binding': bool(sol[1] < NOISE_ABS_FLOOR), 'detail': detail}


def fit_ml(groups, axis, floor=None, horizons=HORIZONS_S):
    """Exact Gaussian ML (sliding windows -> composite likelihood): r ~ N(0, (rel*vbar+abs)^2 DT H)."""
    V, R_, HH = [], [], []
    for (ax, kind, H), v in groups.items():
        if ax == axis and H in horizons:
            V.append(v[:, 0]); R_.append(v[:, 1]); HH.append(np.full(len(v), H))
    V, R_, HH = np.concatenate(V), np.concatenate(R_), np.concatenate(HH)
    lo = 1e-6 if floor is None else floor

    def nll(p):
        ab, rel = p[0] * 1e-3, p[1]
        s2 = (rel * V + ab) ** 2 * DT * HH
        return float(np.sum(0.5 * np.log(s2) + 0.5 * R_ ** 2 / s2))
    best = None
    for p0 in ((2., .05), (1., .3), (5., 0.), (.5, .01)):
        r = minimize(nll, np.array(p0), method='L-BFGS-B', bounds=[(lo * 1e3, 100.), (0., 3.)])
        if best is None or r.fun < best.fun:
            best = r
    return {'abs': float(best.x[0] * 1e-3), 'rel': float(best.x[1]), 'nll': float(best.fun), 'n': int(len(V)),
            'floor_applied': floor}


def coverage_subwindows(items, noise, frame='sub'):
    """#376 coverage(): fraction of sub-window residuals inside 2 sigma, sigma = (rel*vbar+abs) sqrt(DT*H); all phases, both axes."""
    rel, ab = np.array(noise['rel']), np.array(noise['abs'])
    inside = {H: [0, 0] for H in COVERAGE_HORIZONS_S}
    for R, w in items:
        B = block_arrays(R, w)
        nrow = len(B['P'])
        for H in COVERAGE_HORIZONS_S:
            n = round(H / DT)
            j = np.arange(0, nrow - n)
            es = sub_residuals(B, j, n, frame)
            vb_model = np.array([B['mv'][jj:jj + n + 1].mean() for jj in j])
            for i in range(2):
                vb = vb_model if i == B['axis_i'] else np.zeros_like(vb_model)
                sig = (rel[i] * vb + ab[i]) * math.sqrt(DT * H)
                hit = np.abs(es[i]) <= np.maximum(2 * sig, POSE_RESOLUTION_M)
                inside[H][0] += int(hit.sum()); inside[H][1] += int(len(hit))
    tot = sum(v[0] for v in inside.values()); n = sum(v[1] for v in inside.values())
    return {'overall': tot / n, 'per_horizon': {f'H{H}': v[0] / v[1] for H, v in inside.items()}, 'n': n}


def pf_discrete_sigma(R, w, noise, upto):
    """Analytic sd (m) of the PF displacement from block start to step `upto` (grid index rel. window start), per axis,
    exact PF discrete propagation: Var = DT^2 * sum_k moving_k (rel|v_k| + abs)^2, moving = commanded (+1 lease step) or |v|>=1e-3.
    xy-noise only (excludes the rotation spread from turn noise)."""
    nstep = round(w['duration_s'] / DT)
    v = R['v'][w['a'] + 1:w['a'] + upto + 1]
    k = np.arange(1, len(v) + 1)
    moving = (k <= nstep + 1) | (np.abs(v) >= 1e-3)
    out = []
    for i, axis in enumerate(AXES):
        va = np.abs(v) if axis == R['run']['axis'] else np.zeros_like(v)
        out.append(math.sqrt(DT ** 2 * float(np.sum(moving * (noise['rel'][i] * va + noise['abs'][i]) ** 2))))
    return out


def coverage_endpoints(items, noise):
    """Residual at step end and block end (block start -> checkpoint) vs 2 * PF discrete sigma, per axis."""
    rows = []
    for R, w in items:
        B = block_arrays(R, w)
        for name, upto in (('step_end', w['b_step'] - w['a']), ('block_end', w['b'] - w['a'])):
            es = sub_residuals(B, np.array([0]), upto, 'block')
            sig = pf_discrete_sigma(R, w, noise, upto)
            for i, axis in enumerate(AXES):
                rows.append({'run': R['rid'], 'robot': f"r{R['k'] + 1}", 'role': w['role'], 'value': w['value'], 'checkpoint': name,
                             'axis': axis, 'resid_mm': 1e3 * float(es[i][0]), 'sigma_mm': 1e3 * sig[i],
                             'z': float(es[i][0] / sig[i]) if sig[i] > 0 else None})
    out = {}
    for ck in ('step_end', 'block_end'):
        z = np.array([r['z'] for r in rows if r['checkpoint'] == ck])
        out[ck] = {'n': int(len(z)), 'frac_inside_2sigma': float(np.mean(np.abs(z) <= 2)), 'rms_z': float(np.sqrt(np.mean(z ** 2))),
                   'max_abs_z': float(np.abs(z).max())}
    return out, rows


def main():
    all_runs = load_all()
    fit_items = [(R, w) for R in all_runs for w in F.windows(R['run']) if w['role'] in F.FIT_ROLES]
    held_items = [(R, w) for R in all_runs for w in F.windows(R['run']) if w['role'] in F.HELD_ROLES]
    res = {'schema': 'ugrp.loaded_noise_rule.v105', 'base': BASE, 'base_sha256': BASE_SHA, 'raw': RAW, 'dt': DT,
           'horizons_fit_s': HORIZONS_S, 'horizons_coverage_s': COVERAGE_HORIZONS_S, 'noise_abs_floor': NOISE_ABS_FLOOR,
           'n_fit_blocks_per_robot': len(fit_items) // 2, 'n_held_blocks_per_robot': len(held_items) // 2,
           'current': {'abs': CUR_ABS.tolist(), 'rel': CUR_REL.tolist()}}
    groups = noise_groups(fit_items)
    fits = {}
    for axis in AXES:
        ms = fit_moment(groups, axis)
        fits[axis] = {'moment': ms, 'ml_floorless': fit_ml(groups, axis), 'ml_floor': fit_ml(groups, axis, NOISE_ABS_FLOOR)}
    # sensitivities (reported, not used): block-start frame; per-robot split; horizons 1,2,4
    gblk = noise_groups(fit_items, frame='block')
    sens = {'block_frame': {a: fit_moment(gblk, a) for a in AXES},
            'horizons_1_2_4': {a: fit_moment(groups, a, COVERAGE_HORIZONS_S) for a in AXES},
            'r1_only': {a: fit_moment(noise_groups([x for x in fit_items if x[0]['k'] == 0]), a) for a in AXES},
            'r2_only': {a: fit_moment(noise_groups([x for x in fit_items if x[0]['k'] == 1]), a) for a in AXES}}
    # per-level implied std (diagnostic): shows where rel comes from
    glev = noise_groups(fit_items, by_level=True)
    lvl = {}
    for (axis, kind, H, level), v in sorted(glev.items()):
        if H == 1. and len(v) >= MIN_GROUP_N and axis in AXES:
            lvl[f'{axis}/{kind}/u={level}'] = {'n': len(v), 'vbar': float(v[:, 0].mean()),
                                              'implied_std': math.sqrt(np.mean(v[:, 1] ** 2) / (DT * H)),
                                              'mean_resid_mm': 1e3 * float(v[:, 1].mean())}
    # yaw (idle only): diagnostic for the turn axis, NOT used in the proposed file
    yaw = fit_moment(groups, 'turn')
    res.update(fit=fits, sensitivity=sens, per_level_H1=lvl, yaw_idle_diagnostic={'abs_raw': yaw['abs_raw'], 'abs': yaw['abs'],
               'rel_fit_not_identified': yaw['rel'], 'detail': yaw['detail'], 'parent_abs': CUR_ABS[2], 'parent_rel': CUR_REL[2]})
    prop = {'abs': [fits['forward']['moment']['abs'], fits['left']['moment']['abs'], float(CUR_ABS[2])],
            'rel': [fits['forward']['moment']['rel'], fits['left']['moment']['rel'], float(CUR_REL[2])]}
    res['proposed'] = prop
    cov = {}
    for label, nz in (('current', {'abs': CUR_ABS.tolist(), 'rel': CUR_REL.tolist()}), ('fitted', prop)):
        ep_fit, _ = coverage_endpoints(fit_items, nz)
        ep_held, rows_held = coverage_endpoints(held_items, nz)
        cov[label] = {'subwindow_fit_split': coverage_subwindows(fit_items, nz), 'subwindow_heldout': coverage_subwindows(held_items, nz),
                      'endpoints_fit_split': ep_fit, 'endpoints_heldout': ep_held,
                      'accept_overall_2sigma': ACCEPT_COVERAGE_2SIGMA}
        cov[label]['accept_heldout_subwindow'] = bool((cov[label]['subwindow_heldout']['overall'] or 0) >= ACCEPT_COVERAGE_2SIGMA)
        if label == 'fitted':
            res['endpoint_rows_heldout_fitted'] = rows_held
    res['coverage'] = cov
    # in-sample residual size at fit-block endpoints (diagnostic of how small the mean-model residual is)
    r_end = []
    for R, w in fit_items + held_items:
        B = block_arrays(R, w)
        es = sub_residuals(B, np.array([0]), w['b'] - w['a'], 'block')
        r_end.append((w['role'] in F.FIT_ROLES, 1e3 * float(es[0][0]), 1e3 * float(es[1][0])))
    r_end = np.array(r_end)
    res['block_end_resid_mm_rms'] = {'fit': float(np.sqrt(np.mean(r_end[r_end[:, 0] == 1][:, 1:] ** 2))),
                                     'heldout': float(np.sqrt(np.mean(r_end[r_end[:, 0] == 0][:, 1:] ** 2)))}
    path = f'{OUT}/fit_noise_loaded_result.json'
    json.dump(res, open(path, 'w'), indent=1, sort_keys=True, default=float)
    print(json.dumps({'proposed': prop, 'current': res['current'], 'floor_binding': {a: fits[a]['moment']['floor_binding'] for a in AXES},
                      'abs_raw': {a: fits[a]['moment']['abs_raw'] for a in AXES}, 'ml_floorless': {a: fits[a]['ml_floorless'] for a in AXES},
                      'ml_floor': {a: fits[a]['ml_floor'] for a in AXES},
                      'coverage': {k: {kk: vv for kk, vv in v.items() if kk in ('subwindow_fit_split', 'subwindow_heldout', 'endpoints_heldout', 'endpoints_fit_split')} for k, v in cov.items()},
                      'yaw_idle': res['yaw_idle_diagnostic']['abs_raw'], 'block_end_resid_mm_rms': res['block_end_resid_mm_rms']}, indent=1, default=float))


if __name__ == '__main__':
    main()
