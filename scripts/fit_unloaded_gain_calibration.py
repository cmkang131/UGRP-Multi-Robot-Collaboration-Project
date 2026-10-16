#!/usr/bin/env python3
"""Offline fit / held-out evaluation of the v101 unloaded gain and lag calibration.

Never imports a simulator, renderer or controller. Ground truth (``eval_only/r1/pose.jsonl``) is read ONLY here, as an
offline calibration product (same nature as the registered r4/r5 measured noise); it never reaches a command schedule.

Stages (each writes a new directory; nothing is overwritten):
  fit       fit-role runs only -> fit.json (frozen model forms, per-block diagnostics, noise/scale/rest rules)
  evaluate  frozen fit.json + held-out runs -> heldout.json (form selection on heldA3/heldM1, acceptance on heldP1/P2)
  product   fit.json + heldout.json -> new calibration file(s) filling the ten unloaded ``params.motion`` fields

The model is the particle filter's own predictor (harness/owncam_localizer.py ``predict_to``): first-order velocity
lag per axis while a command is active, one shared stop lag when every axis is commanded zero, 0.05 s steps,
position integrated from the updated velocity, optional ``deadband`` ramp. Rules: PREREGISTRATION.md.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import least_squares, nnls

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import final_environment_gain_calibration_v101 as env   # noqa: E402  (static plan only)

DT = .05
YAW_WEIGHT_M = .35                  # metres per radian: yaw error counted at the conservative robot radius
AXES = env.AXES
FORMS = ('linear_diag', 'deadband_diag', 'linear_full')
HORIZONS_S = (.5, 1., 2.)
COVERAGE_HORIZONS_S = (1., 2., 4.)

# Comparators (registered values as they are; never re-fitted).
DEV_FILL = {'gain': [1.15, .94, 1.40], 'tau_axis_s': [.12, .12, .12], 'tau_stop_s': .12}
R4R5 = {'gain': [1.2371430923959086, .8509603197221365, 1.0725221565695355],
        'tau_axis_s': [.7977909566698789, .7877102182037926, .16770868665607128],
        'tau_stop_s': .08897855686817813}      # forward stop lag; per-axis stop lags are never averaged
R4R5_SOURCE = ('experiments/2026-10-03-critb-rotation/calibration_candidate_r5_yaw.json',
               '978727fcacc5e368efe2a0fdf6d9d8dc3756573c41e896e06ba11d78cf86fb97')

# Acceptance thresholds (PREREGISTRATION.md section 5), written before any collection.
NOISE_ABS_FLOOR = .002           # m/s and rad/s: a measured law is never allowed to reach zero (dither floor, MRPT / Gustafsson)
POSE_RESOLUTION_M = 1e-6
ACCEPT = {'leg_end_over_path': .06, 'leg_max_pos_err_m': .12, 'leg_rms_ratio_vs_dev': .5,
          'sel_rms_ratio_vs_dev': .6, 'sel_rms_ratio_vs_r4r5': .8, 'coverage_2sigma': .90,
          'deadband_vs_linear': .9, 'full_vs_best_diag': .75, 'rest_noise_rms_m': .001, 'scale_on_std': .01}


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    return sha_bytes(Path(path).read_bytes())


def write_new(path, obj):
    with Path(path).open('x') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, allow_nan=False, sort_keys=True)
        f.write('\n')


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def git_clean_sha():
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT, text=True)
    return sha, not dirty.strip()


# ----------------------------------------------------------------------------------------------- data
def load_run(raw, run_id, plan):
    run = env.run_row(plan, run_id)
    folder = Path(raw) / run_id / run_id        # runner layout: <raw>/<run>/<run>/{result.json, eval_only, robots}
    result = json.loads((folder / 'result.json').read_text())
    if result.get('status') != 'COLLECTED_UNQUALIFIED' or not result.get('protocol_complete'):
        raise ValueError(f'{run_id}: acquisition incomplete: {result.get("status")}')
    poses = rows(folder / 'eval_only/r1/pose.jsonl')
    n = round(run['sim_cap_s'] / DT)
    if len(poses) != n + 1:
        raise ValueError(f'{run_id}: expected {n + 1} pose samples, found {len(poses)}')
    t = np.array([p['t'] for p in poses])
    if np.max(np.abs(np.diff(t) - DT)) > 1e-6:
        raise ValueError(f'{run_id}: pose clock is not 0.05 s')
    rot = np.array([p['base_rotation'] for p in poses])
    xy = np.array([p['base_position_m'][:2] for p in poses])
    yaw = np.unwrap(np.arctan2(rot[:, 1, 0], rot[:, 0, 0]))
    table = env.command_table(run, plan)
    commands = [c for c in rows(folder / 'robots/r1/commands.jsonl') if c['kind'] == 'mecanum']
    got = np.array([[c['forward'], c['left'], c['turn']] for c in commands])
    if got.shape != table.shape or np.max(np.abs(got - table)) > 1e-9:
        raise ValueError(f'{run_id}: issued commands differ from the registered table')
    return {'id': run_id, 'role': run['role'], 'run': run, 'pose': np.column_stack((xy, yaw)),
            'U': np.repeat(table, round(plan['control_period_s'] / DT), axis=0),
            'result_sha256': sha_file(folder / 'result.json'),
            'pose_sha256': sha_file(folder / 'eval_only/r1/pose.jsonl'),
            'commands_sha256': sha_file(folder / 'robots/r1/commands.jsonl')}


def make_windows(run, plan):
    """Blocks that start from rest: a step/mixed segment plus its coast; a replay leg plus its coast."""
    out, t, segs, i = [], plan['initial_hold_s'], run['segments'], 0
    while i < len(segs):
        s = segs[i]
        if s['phase'] in ('step', 'mixed') and i + 1 < len(segs) and segs[i + 1]['phase'] == 'coast':
            d = s['duration_s'] + segs[i + 1]['duration_s']
            peak = [max(abs(s['start'][k]), abs(s['end'][k])) for k in range(3)]
            out.append({'kind': s['phase'], 'axis': s['axis'], 'a': round(t / DT), 'b': round((t + d) / DT),
                        'step_end': round((t + s['duration_s']) / DT), 'level': max(peak),
                        'sign': float(np.sign(sum(s['start']))) if s['phase'] == 'step' else 0.})
            t += d
            i += 2
        elif s['phase'] == 'replay':
            j, d = i, 0.
            while j < len(segs) and segs[j]['phase'] in ('replay', 'coast'):
                d += segs[j]['duration_s']
                j += 1
            out.append({'kind': 'replay', 'axis': 'replay', 'a': round(t / DT), 'b': round((t + d) / DT),
                        'step_end': round((t + d) / DT), 'level': 0., 'sign': 0.})
            t += d
            i = j
        else:
            t += s['duration_s']
            i += 1
    return out


# ----------------------------------------------------------------------------------------------- model
def unpack(form, p):
    p = np.asarray(p, float)
    if form == 'linear_diag':
        return np.diag(p[0:3]), p[3:6], p[6], None
    if form == 'deadband_diag':
        return np.diag(p[0:3]), p[3:6], p[6], (p[7:10], p[10:13])
    if form == 'linear_full':
        return p[0:9].reshape(3, 3), p[9:12], p[12], None
    raise ValueError(form)


def predict(U, form, p, a, b):
    """Predictor of harness/owncam_localizer.py predict_to, deterministic part (scale 1), relative to sample ``a``."""
    gain, tau_axis, tau_stop, db = unpack(form, p)
    alpha_drive = 1. - np.exp(-DT / np.maximum(tau_axis, 1e-6))
    alpha_stop = 1. - math.exp(-DT / max(tau_stop, 1e-6))
    vel = np.zeros(3)
    x = y = yaw = 0.
    out = np.zeros((b - a + 1, 3))
    for k in range(a, b):
        u = U[k]
        if db is not None and np.any(u):
            c0, u1 = db
            u = u * np.where(u1 > c0, np.clip((np.abs(u) - c0) / np.maximum(u1 - c0, 1e-9), 0., 1.), 1.)
        active = bool(np.any(u))
        vel = vel + (alpha_drive if active else alpha_stop) * (gain @ u - vel)
        c, s = math.cos(yaw), math.sin(yaw)
        x += (c * vel[0] - s * vel[1]) * DT
        y += (s * vel[0] + c * vel[1]) * DT
        yaw += vel[2] * DT
        out[k - a + 1] = (x, y, yaw)
    return out


def predict_velocity(U, form, p, a, b):
    """Predicted body velocity per sample (same recursion), for the noise law."""
    gain, tau_axis, tau_stop, db = unpack(form, p)
    alpha_drive = 1. - np.exp(-DT / np.maximum(tau_axis, 1e-6))
    alpha_stop = 1. - math.exp(-DT / max(tau_stop, 1e-6))
    vel = np.zeros(3)
    out = np.zeros((b - a + 1, 3))
    for k in range(a, b):
        u = U[k]
        if db is not None and np.any(u):
            c0, u1 = db
            u = u * np.where(u1 > c0, np.clip((np.abs(u) - c0) / np.maximum(u1 - c0, 1e-9), 0., 1.), 1.)
        vel = vel + (alpha_drive if np.any(u) else alpha_stop) * (gain @ u - vel)
        out[k - a + 1] = vel
    return out


def measured(pose, a, b):
    d = pose[a:b + 1] - pose[a]
    c, s = math.cos(pose[a, 2]), math.sin(pose[a, 2])
    return np.column_stack((c * d[:, 0] + s * d[:, 1], -s * d[:, 0] + c * d[:, 1], d[:, 2]))


def residual(run, w, form, p):
    r = predict(run['U'], form, p, w['a'], w['b']) - measured(run['pose'], w['a'], w['b'])
    r[:, 2] *= YAW_WEIGHT_M
    return r


def comparator_params(spec):
    return np.array([*spec['gain'], *spec['tau_axis_s'], spec['tau_stop_s']])


# ----------------------------------------------------------------------------------------------- weights
def usage_weights(inputs, fit_windows):
    """Window weight = (0.8 * energy share of the approach's commands at that level + 0.2 / levels) / windows at the level.

    The shrinkage keeps levels the approach rarely uses identifiable (deadband shape) without letting them dominate.
    Weights are rescaled so that their mean over the fit windows is 1.
    """
    shares = inputs['usage']
    counts = {}
    for run_id, w in fit_windows:
        if w['kind'] == 'step':
            counts[(w['axis'], round(w['level'], 6))] = counts.get((w['axis'], round(w['level'], 6)), 0) + 1
    weights = {}
    for axis in AXES:
        levels = shares[axis]['levels']
        for level, share in zip(levels, shares[axis]['energy_share']):
            n = counts.get((axis, round(level, 6)), 0)
            if n:
                weights[(axis, round(level, 6))] = (.8 * share + .2 / len(levels)) / n
    total = sum(weights[(w['axis'], round(w['level'], 6))] for _, w in fit_windows if w['kind'] == 'step')
    k = len([1 for _, w in fit_windows if w['kind'] == 'step'])
    return {key: value * k / total for key, value in weights.items()}


# ----------------------------------------------------------------------------------------------- fitting
BOUNDS = {'gain': (.05, 4.), 'tau': (.03, 3.), 'tau_stop': (.01, .5)}


def start_points(form, ref):
    g = np.array(ref)
    if form == 'linear_diag':
        return [np.array([*g, t, t, t * .3, .08]) for t in (.2, .8, 1.5)]
    if form == 'deadband_diag':
        return [np.array([*g, t, t, t * .3, .08, .004, .004, .004, .03, .03, .03]) for t in (.2, .8, 1.5)]
    full = np.diag(g).ravel()
    return [np.array([*full, t, t, t * .3, .08]) for t in (.2, .8, 1.5)]


def bounds_for(form):
    g_lo, g_hi = BOUNDS['gain']
    t_lo, t_hi = BOUNDS['tau']
    s_lo, s_hi = BOUNDS['tau_stop']
    if form == 'linear_diag':
        return ([g_lo] * 3 + [t_lo] * 3 + [s_lo], [g_hi] * 3 + [t_hi] * 3 + [s_hi])
    if form == 'deadband_diag':
        return ([g_lo] * 3 + [t_lo] * 3 + [s_lo] + [0.] * 3 + [.012] * 3,
                [g_hi] * 3 + [t_hi] * 3 + [s_hi] + [.015] * 3 + [.2] * 3)
    return ([-g_hi] * 9 + [t_lo] * 3 + [s_lo], [g_hi] * 9 + [t_hi] * 3 + [s_hi])


def batch_predict(Ub, form, p):
    """Same recursion as ``predict`` for W equal-length windows at once. Ub: (W, K, 3) -> (W, K + 1, 3)."""
    gain, tau_axis, tau_stop, db = unpack(form, p)
    alpha_drive = 1. - np.exp(-DT / np.maximum(tau_axis, 1e-6))
    alpha_stop = 1. - math.exp(-DT / max(tau_stop, 1e-6))
    W, K, _ = Ub.shape
    vel = np.zeros((W, 3))
    x, y, yaw = np.zeros(W), np.zeros(W), np.zeros(W)
    out = np.zeros((W, K + 1, 3))
    for k in range(K):
        u = Ub[:, k, :]
        if db is not None:
            c0, u1 = db
            ramp = np.where(u1 > c0, np.clip((np.abs(u) - c0) / np.maximum(u1 - c0, 1e-9), 0., 1.), 1.)
            u = np.where(np.any(u != 0, axis=1)[:, None], u * ramp, u)
        active = np.any(u != 0, axis=1)[:, None]
        alpha = np.where(active, alpha_drive[None, :], alpha_stop)
        vel = vel + alpha * (u @ gain.T - vel)
        c, s_ = np.cos(yaw), np.sin(yaw)
        x = x + (c * vel[:, 0] - s_ * vel[:, 1]) * DT
        y = y + (s_ * vel[:, 0] + c * vel[:, 1]) * DT
        yaw = yaw + vel[:, 2] * DT
        out[:, k + 1, 0], out[:, k + 1, 1], out[:, k + 1, 2] = x, y, yaw
    return out


def fit_form(form, items, weights, ref_gain):
    """items: list of (run, window) of equal length. Weighted trajectory least squares, multi-start."""
    lo, hi = bounds_for(form)
    lengths = {w['b'] - w['a'] for _, w in items}
    if len(lengths) != 1:
        raise ValueError('fit windows must have equal length')
    Ub = np.stack([run['U'][w['a']:w['b']] for run, w in items])
    meas = np.stack([measured(run['pose'], w['a'], w['b']) for run, w in items])
    scale = np.array([math.sqrt(weights.get((w['axis'], round(w['level'], 6)), 1.)) for _, w in items])
    yaw_w = np.array([1., 1., YAW_WEIGHT_M])

    def fun(p):
        r = (batch_predict(Ub, form, p) - meas) * yaw_w
        return (r * scale[:, None, None]).ravel()

    best = None
    for x0 in start_points(form, ref_gain):
        x0 = np.clip(x0, np.array(lo) + 1e-6, np.array(hi) - 1e-6)
        sol = least_squares(fun, x0, bounds=(lo, hi), xtol=1e-10, ftol=1e-10, gtol=1e-10, max_nfev=400)
        if best is None or sol.cost < best.cost:
            best = sol
    p = best.x
    boundary = [i for i in range(len(p)) if abs(p[i] - lo[i]) < 1e-6 * max(1, abs(lo[i])) + 1e-9
                or abs(p[i] - hi[i]) < 1e-6 * max(1, abs(hi[i])) + 1e-9]
    jac = best.jac
    rank = int(np.linalg.matrix_rank(jac, tol=1e-9 * np.linalg.norm(jac)))
    rmse = math.sqrt(2 * best.cost / max(len(best.fun), 1))
    return {'form': form, 'params': [float(v) for v in p], 'cost': float(best.cost), 'rmse_weighted': rmse,
            'success': bool(best.success), 'status': int(best.status), 'nfev': int(best.nfev), 'rank': rank,
            'n_params': len(p), 'boundary_params': boundary}


def unpacked_json(form, p):
    gain, tau_axis, tau_stop, db = unpack(form, p)
    out = {'gain': [[float(v) for v in row] for row in gain], 'tau_axis_s': [float(v) for v in tau_axis],
           'tau_stop_s': float(tau_stop)}
    if db is not None:
        out['deadband'] = {'c0': [float(v) for v in db[0]], 'u1': [float(v) for v in db[1]]}
    return out


# ----------------------------------------------------------------------------------------------- diagnostics
def steady_velocity(run, w):
    """Measured mean body velocity of the axis over the last 1.5 s of the step (model-free)."""
    k = round(1.5 / DT)
    a, e = max(w['step_end'] - k, w['a']), w['step_end']
    pose = run['pose']
    c, s = np.cos(pose[a:e, 2]), np.sin(pose[a:e, 2])
    d = np.diff(pose[a:e + 1], axis=0) / DT
    body = np.column_stack((c * d[:, 0] + s * d[:, 1], -s * d[:, 0] + c * d[:, 1], d[:, 2]))
    return [float(v) for v in body.mean(axis=0)]


def block_table(runs_windows):
    table = []
    for run, w in runs_windows:
        if w['kind'] != 'step':
            continue
        i = AXES.index(w['axis'])
        v = steady_velocity(run, w)
        u = w['sign'] * w['level']
        table.append({'run': run['id'], 'axis': w['axis'], 'level': w['level'], 'sign': w['sign'],
                      'v_ss_own_axis': v[i], 'v_ss_over_u': v[i] / u, 'v_ss_cross': [v[j] for j in range(3) if j != i]})
    return table


def direct_gain(table, inputs):
    """Usage-weighted least-squares slope of measured steady speed vs command, per axis (model-free cross-check)."""
    out = {}
    for axis in AXES:
        share = dict(zip(inputs['usage'][axis]['levels'], inputs['usage'][axis]['energy_share']))
        num = den = 0.
        for row in table:
            if row['axis'] != axis:
                continue
            w = share.get(row['level'], 0.)
            u = row['sign'] * row['level']
            num += w * u * row['v_ss_own_axis']
            den += w * u * u
        out[axis] = num / den if den else None
    return out


def replicate_spread(table):
    """Relative std of steady speed between replicate blocks (same axis, level, sign; different run/start/yaw)."""
    pairs = {}
    for row in table:
        pairs.setdefault((row['axis'], round(row['level'], 6), row['sign']), []).append(row['v_ss_own_axis'])
    rel = []
    for values in pairs.values():
        if len(values) >= 2:
            m = np.mean(np.abs(values))
            if m > 1e-9:
                rel.append((np.std(values, ddof=1) / m) ** 2)
    return float(math.sqrt(np.mean(rel))) if rel else None, len(rel)


def end_metrics(run, w, form, p):
    pred = predict(run['U'], form, p, w['a'], w['b'])
    meas = measured(run['pose'], w['a'], w['b'])
    err = pred - meas
    pos = np.linalg.norm(err[:, :2], axis=1)
    path = float(np.sum(np.linalg.norm(np.diff(meas[:, :2], axis=0), axis=1)))
    e_end = float(math.sqrt(err[-1, 0] ** 2 + err[-1, 1] ** 2 + (YAW_WEIGHT_M * err[-1, 2]) ** 2))
    return {'run': run['id'], 'kind': w['kind'], 'axis': w['axis'], 'level': w['level'], 'sign': w['sign'],
            'end_err_m': e_end, 'end_pos_err_m': float(pos[-1]), 'max_pos_err_m': float(pos.max()),
            'rms_pos_err_m': float(math.sqrt(np.mean(pos ** 2))), 'path_len_m': path,
            'end_over_path': float(pos[-1] / path) if path > 1e-6 else None,
            'end_yaw_err_rad': float(err[-1, 2])}


def rms(values):
    return float(math.sqrt(np.mean(np.square(values)))) if len(values) else None


# ----------------------------------------------------------------------------------------------- noise law
def noise_groups(items, form, p):
    """(axis, kind, horizon) -> list of (vbar, residual) over sub-windows of settled drive / idle / rest.

    residual = predicted minus measured displacement increment of that axis over the horizon, in the window-start
    frame (m, or rad for turn). 'driven': the axis is the commanded axis and settled (>= 3 lags into the step);
    'idle': another axis is commanded and settled; 'rest': command zero for >= 5 stop lags.
    """
    groups = {}
    tau_axis, tau_stop = unpack(form, p)[1], unpack(form, p)[2]
    for run, w in items:
        a, b = w['a'], w['b']
        vel = predict_velocity(run['U'], form, p, a, b)
        res = predict(run['U'], form, p, a, b) - measured(run['pose'], a, b)
        drive_end, rest_start = w['step_end'] - a, w['step_end'] - a + math.ceil(5 * tau_stop / DT)
        for axis_i, axis in enumerate(AXES):
            for H in HORIZONS_S:
                n = round(H / DT)
                for j in range(0, b - a - n + 1):
                    if j + n <= drive_end:
                        settle = math.ceil(3 * (tau_axis[axis_i] if w['axis'] == axis else float(np.max(tau_axis))) / DT)
                        if j < settle:
                            continue
                        kind = 'driven' if w['axis'] == axis else 'idle'
                    elif j >= rest_start:
                        kind = 'rest'
                    else:
                        continue
                    vbar = float(np.mean(np.abs(vel[j:j + n + 1, axis_i])))
                    groups.setdefault((axis, kind, H), []).append((vbar, float(res[j + n, axis_i] - res[j, axis_i])))
    return groups


def fit_noise(groups):
    """Per axis: s = rel * vbar + abs, with s the white velocity-noise std implied by the residual RMS per horizon."""
    out = {'noise_rel': [], 'noise_abs': [], 'detail': {}}
    for axis in AXES:
        xs, ys, ws = [], [], []
        for (ax, kind, H), values in groups.items():
            if ax != axis or len(values) < 5:
                continue
            v = np.array(values)
            s = math.sqrt(np.mean(v[:, 1] ** 2)) / math.sqrt(DT * H)
            xs.append(float(np.mean(v[:, 0])))
            ys.append(s)
            ws.append(len(values))
            out['detail'][f'{axis}/{kind}/H{H}'] = {'n': len(values), 'vbar': xs[-1], 'implied_std': s}
        if not xs:
            out['noise_rel'].append(0.)
            out['noise_abs'].append(NOISE_ABS_FLOOR)
            continue
        w = np.sqrt(np.array(ws, float))
        A = np.column_stack((xs, np.ones(len(xs)))) * w[:, None]
        sol, _ = nnls(A, np.array(ys) * w)
        out['noise_rel'].append(float(sol[0]))
        out['noise_abs'].append(float(max(sol[1], NOISE_ABS_FLOOR)))
    return out


def coverage(items, form, p, noise):
    """Fraction of sub-window displacement residuals inside 2 sigma of the PF noise at that horizon."""
    inside = total = 0
    per = {}
    rel, ab = np.array(noise['noise_rel']), np.array(noise['noise_abs'])
    for run, w in items:
        a, b = w['a'], w['b']
        vel = predict_velocity(run['U'], form, p, a, b)
        res = predict(run['U'], form, p, a, b) - measured(run['pose'], a, b)
        for H in COVERAGE_HORIZONS_S:
            n = round(H / DT)
            for j in range(0, b - a - n + 1):
                for i in range(3):
                    d = res[j + n, i] - res[j, i]
                    vbar = float(np.mean(np.abs(vel[j:j + n + 1, i])))
                    sigma = (rel[i] * vbar + ab[i]) * math.sqrt(DT * H)
                    hit = abs(d) <= max(2 * sigma, POSE_RESOLUTION_M)
                    inside += hit
                    total += 1
                    key = f'H{H}'
                    c = per.setdefault(key, [0, 0])
                    c[0] += hit
                    c[1] += 1
    return {'overall': inside / total if total else None, 'per_horizon': {k: v[0] / v[1] for k, v in per.items()}}


def rest_rms(items, form, p, window_s=1.):
    """RMS model-free displacement in rest windows (command zero for >= 5 stop lags), metres over ``window_s``."""
    n = round(window_s / DT)
    values = []
    for run, w in items:
        tau_stop = unpack(form, p)[2]
        j0 = w['step_end'] + math.ceil(5 * tau_stop / DT)
        meas = measured(run['pose'], w['a'], w['b'])
        for j in range(j0 - w['a'], w['b'] - w['a'] - n + 1):
            d = meas[j + n, :2] - meas[j, :2]
            values.append(float(np.linalg.norm(d)))
    return rms(values), len(values)


# ----------------------------------------------------------------------------------------------- stages
def read_plan_inputs():
    plan = env.protocol()
    inputs = json.loads((ROOT / env.INPUTS).read_text())
    return plan, inputs


def stage_fit(args):
    plan, inputs = read_plan_inputs()
    sha, clean = git_clean_sha()
    if not clean:
        raise ValueError('fit requires a clean committed tree (script and plan are part of the record)')
    out = Path(args.output)
    if not out.is_absolute():
        raise ValueError('output must be absolute')
    out.mkdir(parents=True, exist_ok=False)
    fit_ids = [r['id'] for r in plan['runs'] if r['role'] == 'fit']
    runs = [load_run(args.raw, rid, plan) for rid in fit_ids]
    if any(r['role'] != 'fit' for r in runs):
        raise ValueError('fit stage reads fit-role runs only')
    items = [(r, w) for r in runs for w in make_windows(r['run'], plan)]
    weights = usage_weights(inputs, [(r['id'], w) for r, w in items])
    table = block_table(items)
    direct = direct_gain(table, inputs)
    ref_gain = [abs(direct[a]) if direct[a] else 1. for a in AXES]
    fits = {form: fit_form(form, items, weights, ref_gain) for form in FORMS}
    for form in FORMS:
        fits[form].update(unpacked_json(form, fits[form]['params']))
    spread, n_pairs = replicate_spread(table)
    # Noise law, rest and scale rules use the linear_diag mean model (the registered baseline form).
    p_lin = fits['linear_diag']['params']
    noise = fit_noise(noise_groups(items, 'linear_diag', p_lin))
    rest, n_rest = rest_rms(items, 'linear_diag', p_lin)
    record = {'schema': 'ugrp.unloaded_gain_calibration_fit.v101', 'stage': 'fit', 'source_sha': sha,
              'script_sha256': sha_file(__file__), 'plan_sha256': sha_file(ROOT / env.CONFIG),
              'inputs_sha256': sha_file(ROOT / env.INPUTS), 'environment': {'python': platform.python_version(),
                                                                          'numpy': np.__version__, 'scipy': scipy.__version__},
              'fit_runs': [{k: r[k] for k in ('id', 'result_sha256', 'pose_sha256', 'commands_sha256')} for r in runs],
              'n_windows': len(items), 'weights': {f'{a}/{lv}': w for (a, lv), w in sorted(weights.items())},
              'forms': fits, 'direct_usage_weighted_gain': direct, 'blocks': table,
              'replicate_spread_rel': spread, 'replicate_pairs': n_pairs,
              'scale_std_rule': {'scale_std': spread if spread is not None else 0.,
                                 'use_scale': bool(spread is not None and spread > ACCEPT['scale_on_std']),
                                 'scale_walk': 0.},
              'rest': {'rms_displacement_1s_m': rest, 'n_windows': n_rest,
                       'rest_noise': bool(rest is not None and rest >= ACCEPT['rest_noise_rms_m'])},
              'noise_measured': noise,
              'comparators': {'dev_fill': DEV_FILL, 'r4r5': dict(R4R5, source=R4R5_SOURCE)}}
    write_new(out / 'fit.json', record)
    (out / 'fit.json.sha256').write_text(sha_file(out / 'fit.json') + '\n')
    print(json.dumps({'fit': str(out / 'fit.json'), 'sha256': sha_file(out / 'fit.json'),
                      'linear_diag': {k: fits['linear_diag'][k] for k in ('gain', 'tau_axis_s', 'tau_stop_s', 'rmse_weighted',
                                                                         'boundary_params', 'rank')},
                      'direct_gain': direct}, indent=1))


def stage_evaluate(args):
    plan, inputs = read_plan_inputs()
    fit_path = Path(args.fit)
    if sha_file(fit_path) != (fit_path.parent / 'fit.json.sha256').read_text().strip():
        raise ValueError('fit.json hash mismatch')
    fit = json.loads(fit_path.read_text())
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    held = {r['id']: load_run(args.raw, r['id'], plan) for r in plan['runs'] if r['role'] == 'heldout'}
    sel_runs = [held[i] for i in ('heldA3', 'heldM1')]
    leg_runs = [held[i] for i in ('heldP1', 'heldP2')]
    sel_items = [(r, w) for r in sel_runs for w in make_windows(r['run'], plan)]
    leg_items = [(r, w) for r in leg_runs for w in make_windows(r['run'], plan)]
    candidates = {f: {'form': f, 'params': fit['forms'][f]['params']} for f in FORMS}
    candidates['dev_fill'] = {'form': 'linear_diag', 'params': list(comparator_params(DEV_FILL))}
    candidates['r4r5'] = {'form': 'linear_diag', 'params': list(comparator_params(R4R5))}
    table = {}
    for name, c in candidates.items():
        sel = [end_metrics(r, w, c['form'], c['params']) for r, w in sel_items]
        leg = [end_metrics(r, w, c['form'], c['params']) for r, w in leg_items]
        table[name] = {'selection_windows': sel, 'leg_windows': leg,
                       'sel_rms_end_err_m': rms([m['end_err_m'] for m in sel]),
                       'leg_rms_pos_err_m': rms([m['rms_pos_err_m'] for m in leg])}
    # Form selection on heldA3/heldM1 only; legs stay untouched by the selection.
    lin = table['linear_diag']['sel_rms_end_err_m']
    chosen, why = 'linear_diag', 'baseline form'
    if table['deadband_diag']['sel_rms_end_err_m'] <= ACCEPT['deadband_vs_linear'] * lin:
        chosen, why = 'deadband_diag', 'deadband improves selection RMS by >= 10%'
    best_diag = table[chosen]['sel_rms_end_err_m']
    if table['linear_full']['sel_rms_end_err_m'] <= ACCEPT['full_vs_best_diag'] * best_diag:
        chosen, why = 'linear_full', 'cross-axis gains improve selection RMS by >= 25% over the best diagonal form'
    c = candidates[chosen]
    legs = table[chosen]['leg_windows']
    checks = {
        'legs_end_over_path_ok': all(m['end_over_path'] is not None and abs(m['end_over_path']) <= ACCEPT['leg_end_over_path'] for m in legs),
        'legs_max_pos_err_ok': all(m['max_pos_err_m'] <= ACCEPT['leg_max_pos_err_m'] for m in legs),
        'legs_vs_dev_ok': table[chosen]['leg_rms_pos_err_m'] <= ACCEPT['leg_rms_ratio_vs_dev'] * table['dev_fill']['leg_rms_pos_err_m'],
        'sel_vs_dev_ok': table[chosen]['sel_rms_end_err_m'] <= ACCEPT['sel_rms_ratio_vs_dev'] * table['dev_fill']['sel_rms_end_err_m'],
        'sel_vs_r4r5_ok': table[chosen]['sel_rms_end_err_m'] <= ACCEPT['sel_rms_ratio_vs_r4r5'] * table['r4r5']['sel_rms_end_err_m']}
    noise = fit['noise_measured']
    cover = coverage(sel_items, 'linear_diag', fit['forms']['linear_diag']['params'], noise)
    checks['noise_measured_coverage_ok'] = bool(cover['overall'] is not None and cover['overall'] >= ACCEPT['coverage_2sigma'])
    mean_ok = all(v for k, v in checks.items() if k != 'noise_measured_coverage_ok')
    record = {'schema': 'ugrp.unloaded_gain_calibration_heldout.v101', 'stage': 'evaluate',
              'fit_sha256': sha_file(fit_path), 'script_sha256': sha_file(__file__),
              'heldout_runs': [{k: r[k] for k in ('id', 'result_sha256', 'pose_sha256', 'commands_sha256')} for r in held.values()],
              'chosen_form': chosen, 'chosen_reason': why, 'candidates': table, 'checks': checks,
              'noise_measured_coverage': cover,
              'status': 'VALIDATED_DEV' if mean_ok else 'FAILED_HELDOUT',
              'note': 'status concerns the mean model (gain, lag); noise_measured_coverage_ok gates only the measured-noise variant C2'}
    write_new(out / 'heldout.json', record)
    (out / 'heldout.json.sha256').write_text(sha_file(out / 'heldout.json') + '\n')
    print(json.dumps({'status': record['status'], 'chosen': chosen, 'why': why, 'checks': checks,
                      'sel_rms': {k: v['sel_rms_end_err_m'] for k, v in table.items()},
                      'leg_rms': {k: v['leg_rms_pos_err_m'] for k, v in table.items()},
                      'coverage': cover}, indent=1))


def stage_product(args):
    fit_path, held_path = Path(args.fit), Path(args.heldout)
    for p in (fit_path, held_path):
        if sha_file(p) != (p.parent / (p.name + '.sha256')).read_text().strip():
            raise ValueError(f'{p.name} hash mismatch')
    fit, held = json.loads(fit_path.read_text()), json.loads(held_path.read_text())
    if held['status'] != 'VALIDATED_DEV':
        raise ValueError('held-out acceptance failed; no registered product is written')
    if held['fit_sha256'] != sha_file(fit_path):
        raise ValueError('heldout.json does not belong to this fit.json')
    base = Path(args.base)
    if sha_file(base) != args.base_sha256:
        raise ValueError('base calibration hash mismatch')
    form = held['chosen_form']
    mean = unpacked_json(form, fit['forms'][form]['params'])
    r5 = json.loads((ROOT / R4R5_SOURCE[0]).read_text())
    if sha_file(ROOT / R4R5_SOURCE[0]) != R4R5_SOURCE[1]:
        raise ValueError('registered r4/r5 candidate changed')
    ax = r5['candidate_axes']
    registered_noise = {'noise_rel': ax['forward']['consumer_fields']['noise_rel'],
                        'noise_abs': [ax['forward']['consumer_fields']['noise_abs'][0],
                                      ax['left']['consumer_fields']['noise_abs'][1],
                                      ax['rotate']['consumer_fields']['noise_abs'][2]]}
    scale = fit['scale_std_rule']
    sha, clean = git_clean_sha()
    if not clean:
        raise ValueError('product requires a clean committed tree')
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)

    def motion(noise, label):
        value = {'gain': mean['gain'], 'tau_s': mean['tau_axis_s'][0], 'tau_axis_s': mean['tau_axis_s'],
                 'tau_stop_s': mean['tau_stop_s'], 'noise_rel': noise['noise_rel'], 'noise_abs': noise['noise_abs'],
                 'scale_std': scale['scale_std'], 'scale_walk': scale['scale_walk'], 'use_scale': scale['use_scale'],
                 'rest_noise': fit['rest']['rest_noise']}
        if 'deadband' in mean:
            value['deadband'] = mean['deadband']
        return value

    products = {}
    variants = {'C': ('registered r4/r5 measured noise (diff C)', registered_noise),
                'C2': ('noise measured in this calibration (variant C2)', fit['noise_measured'])}
    for key, (label, noise) in variants.items():
        cal = json.loads(base.read_text())
        cal['params']['motion'] = motion(noise, label)
        fields = ['gain', 'tau_s', 'tau_axis_s', 'tau_stop_s', 'noise_rel', 'noise_abs', 'scale_std', 'scale_walk',
                  'use_scale', 'rest_noise']
        cal['missing'] = []
        for f in fields:
            cal['field_provenance'][f'params.motion.{f}'] = (
                'registered_r4_r5_measured_noise' if key == 'C' and f in ('noise_rel', 'noise_abs')
                else 'measured_unloaded_gain_calibration_v101')
        if 'deadband' in mean:
            cal['field_provenance']['params.motion.deadband'] = 'measured_unloaded_gain_calibration_v101'
        cal['source_sha'] = sha
        cal['unloaded_gain_calibration'] = {
            'bundle_id': env.BUNDLE_ID, 'variant': key, 'noise_source': label, 'form': form,
            'fit_sha256': sha_file(fit_path), 'heldout_sha256': sha_file(held_path),
            'heldout_status': held['status'], 'registered_noise_source': {'path': R4R5_SOURCE[0], 'sha256': R4R5_SOURCE[1]},
            'qualification': 'DEV_PILOT unloaded profile measured at the approach command amplitudes; NOT MEASURED_SIM, '
                             'not a confirmation sample; unloaded, floor_light_v1, masterpi_v3 standard reset arm pose'}
        cal['parent_calibration'] = {'path': str(base), 'sha256': args.base_sha256}
        manifest = {'schema': 'ugrp.v92_dev_pilot_inputs.v1', 'execution_source_sha': sha, 'working_tree_dirty': False,
                    'script_sha256': sha_file(__file__), 'purpose': f'unloaded gain calibration v101 variant {key}',
                    'fit_sha256': sha_file(fit_path), 'heldout_sha256': sha_file(held_path)}
        folder = out / key
        folder.mkdir()
        write_new(folder / 'input_manifest_dev.json', manifest)
        cal['dev_manifest_sha256'] = sha_file(folder / 'input_manifest_dev.json')
        write_new(folder / 'calibration_dev_pilot_unloaded_v101.json', cal)
        products[key] = sha_file(folder / 'calibration_dev_pilot_unloaded_v101.json')
    write_new(out / 'products.json', {'products': products, 'form': form, 'source_sha': sha})
    print(json.dumps({'products': products, 'form': form}, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='stage', required=True)
    f = sub.add_parser('fit')
    f.add_argument('--raw', required=True, type=Path)
    f.add_argument('--output', required=True, type=Path)
    e = sub.add_parser('evaluate')
    e.add_argument('--raw', required=True, type=Path)
    e.add_argument('--fit', required=True, type=Path)
    e.add_argument('--output', required=True, type=Path)
    q = sub.add_parser('product')
    q.add_argument('--fit', required=True, type=Path)
    q.add_argument('--heldout', required=True, type=Path)
    q.add_argument('--base', required=True, type=Path)
    q.add_argument('--base-sha256', required=True)
    q.add_argument('--output', required=True, type=Path)
    args = p.parse_args(argv)
    {'fit': stage_fit, 'evaluate': stage_evaluate, 'product': stage_product}[args.stage](args)


if __name__ == '__main__':
    main()
