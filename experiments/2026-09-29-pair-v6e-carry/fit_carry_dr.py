"""Dev-only, horizon-matched dead-reckoning error fit for the LOADED plant (v6e flag 1 input).

Input: cohort-1 dev box-carry episodes (outputs/owncam-loop-20260925/dev-a1..a4/dev-box-s31..33),
student-phase 'drive' segments (the robot carries the box). Ground truth is read offline as a
calibration reference. NOT read: the 33 pair-carry stage cells, any test or cohort-2 episode.

Mean model = the shipped loaded plant (calibration_loop_v2.json 'motion_loaded': gain, tau_s,
tau_stop_s), the same equations as ``OwnCamLocalizer.predict_to``. For every window [t0, t0+T]
inside a drive segment (T = 0.5 ... 4 s, every 0.2 s, overlapping) the error is

    e = GT displacement - model displacement    (in the window-start body frame; yaw: rad)

and its variance is regressed on the two terms a dead-reckoning error model can have
(Woodman 2007 eq. 4-5 for the white part; Borenstein & Feng 1996 for the systematic part):

    var(e_yaw) = a_w * T   + b_w * T**2         white rate noise + constant rate bias
    var(e_i)   = a_i * T   + s_i**2 * d_i**2    white velocity noise + relative scale error
                                                (d_i = model displacement along axis i)

Nonnegative least squares on e**2 (two parameters, closed form). A leave-one-episode-out (LOEO)
check gives the spread of the fitted values. The white terms map to the PF's per-step velocity
noise as  noise_abs = sqrt(a / STEP_S)  (one step adds std noise_abs * STEP_S).

Also printed: lag-1 autocorrelation of the yaw-rate residual (white noise would be ~0; the
shipped loop-v1 fit treated finite-difference GT residuals as white rate noise).
"""
import argparse
import glob
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEV = Path('/Users/changmin/projects/ugrp/outputs/owncam-loop-20260925')
CAL = json.load(open(ROOT / 'experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json'))
MP = CAL['params']['motion_loaded']
STEP = .05
HORIZONS = (.5, 1., 1.5, 2., 3., 4.)


def model_velocity(cmds, tg, gain, tau, tau_stop):
    """Mean-model body velocity on the GT grid (same update as OwnCamLocalizer.predict_to)."""
    vel = np.zeros(3)
    out = np.zeros((len(tg), 3))
    cmd, exp, k = np.zeros(3), -1., 0
    cmds = [c for c in cmds if c['kind'] in ('mecanum', 'drive', 'hold', 'stop')]
    for i, t in enumerate(tg):
        while k < len(cmds) and cmds[k]['t'] <= t + 1e-9:
            c = cmds[k]
            k += 1
            if c['kind'] == 'mecanum':
                cmd, exp = np.array([c['forward'], c['left'], c['turn']]), c['t'] + c['duration_s']
            elif c['kind'] == 'drive':
                cmd, exp = np.array([c['forward'], 0., c['turn']]), c['t'] + c['duration_s']
            else:
                cmd, exp = np.zeros(3), -1.
        u = cmd if t < exp - 1e-9 else np.zeros(3)
        tau_now = tau_stop if not np.any(u) else tau
        vel = vel + (1 - math.exp(-STEP / tau_now)) * (gain @ u - vel)
        out[i] = vel
    return out


def integrate(vel, yaw0=0.):
    """Pose (x, y, yaw) on the grid from body velocities; index i = state after step i."""
    n = len(vel)
    pose = np.zeros((n, 3))
    x = y = 0.
    th = yaw0
    for i in range(n):
        x += (math.cos(th) * vel[i, 0] - math.sin(th) * vel[i, 1]) * STEP
        y += (math.sin(th) * vel[i, 0] + math.cos(th) * vel[i, 1]) * STEP
        th += vel[i, 2] * STEP
        pose[i] = (x, y, th)
    return pose


def body_disp(p0, p1):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    c, s = math.cos(p0[2]), math.sin(p0[2])
    return np.array([c * dx + s * dy, -s * dx + c * dy])


def episodes():
    gain = np.asarray(MP['gain'], float)
    for d in sorted(glob.glob(str(DEV / 'dev-a*/dev-box-s3*'))):
        d = Path(d)
        cmds = [json.loads(line) for line in open(d / 'inputs/commands.jsonl')]
        gt = [json.loads(line) for line in open(d / 'eval_only/gt_trajectory.jsonl')]
        ev = [e for e in map(json.loads, open(d / 'eval_only/frames_eval.jsonl')) if e['phase'] == 'student']
        segs, cur = [], []
        for e in ev + [{'student_state': 'end', 't': 0.}]:
            if e['student_state'] == 'drive':
                cur.append(e['t'])
            else:
                if len(cur) > 5:
                    segs.append((cur[0], cur[-1]))
                cur = []
        yield (d.parent.name + '/' + d.name, cmds, gain, np.array([g['t'] for g in gt]),
               np.array([g['x'] for g in gt]), np.array([g['y'] for g in gt]),
               np.unwrap(np.array([g['yaw'] for g in gt])), segs)


def windows():
    """One row per window: episode, T, GT-minus-model error [x, y, yaw], model displacement [x, y]."""
    rows, rate_res = [], []
    for name, cmds, gain, t, x, y, yaw, segs in episodes():
        for (s0, s1) in segs:
            i0, i1 = np.searchsorted(t, s0 - 1e-6), np.searchsorted(t, s1 + 1e-6)
            tg = t[i0:i1 + 1]
            if len(tg) < 12:
                continue
            # the mean model starts at rest at the first drive frame (segments follow a stationary look phase)
            vm = model_velocity(cmds, tg, gain, MP['tau_s'], MP['tau_stop_s'])
            pm = integrate(vm, yaw[i0])
            pg = np.stack([x[i0:i1 + 1], y[i0:i1 + 1], yaw[i0:i1 + 1]], 1)
            rate_res.append(np.diff(pg[:, 2]) / STEP - 0.5 * (vm[1:, 2] + vm[:-1, 2]))
            for T in HORIZONS:
                k = int(round(T / STEP))
                for j in range(0, len(tg) - k, 4):
                    dg, dm = body_disp(pg[j], pg[j + k]), body_disp(pm[j], pm[j + k])
                    rows.append((name, T, dg[0] - dm[0], dg[1] - dm[1],
                                 (pg[j + k, 2] - pg[j, 2]) - (pm[j + k, 2] - pm[j, 2]), dm[0], dm[1]))
    return rows, rate_res


def nnls2(f1, f2, y):
    """min ||y - a f1 - b f2|| with a, b >= 0 (closed form for two columns)."""
    A = np.stack([f1, f2], 1)
    best = None
    for cols in ((0, 1), (0,), (1,)):
        sol, *_ = np.linalg.lstsq(A[:, cols], y, rcond=None)
        if np.all(sol >= 0):
            full = np.zeros(2)
            full[list(cols)] = sol
            r = float(np.sum((y - A @ full) ** 2))
            if best is None or r < best[1]:
                best = (full, r)
    return best[0] if best else np.zeros(2)


def fit(rows):
    T = np.array([r[1] for r in rows])
    e = np.array([[r[2], r[3], r[4]] for r in rows])
    d = np.array([[r[5], r[6]] for r in rows])
    out = {}
    a, b = nnls2(T, T ** 2, e[:, 2] ** 2)
    out['yaw'] = {'white_a': a, 'bias_var_b': b, 'white_rate_std_rad_s': math.sqrt(a / STEP),
                  'bias_rate_std_rad_s': math.sqrt(b)}
    for i, ax in enumerate(('x', 'y')):
        a, s2 = nnls2(T, d[:, i] ** 2, e[:, i] ** 2)
        out[ax] = {'white_a': a, 'scale_var_s2': s2, 'white_vel_std_m_s': math.sqrt(a / STEP),
                   'scale_std': math.sqrt(s2)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path)
    args = ap.parse_args()
    rows, rate_res = windows()
    eps = sorted({r[0] for r in rows})
    print(f'episodes {len(eps)}, windows {len(rows)}')
    print('T[s]    n  rms_x[m]  rms_y[m]  rms_yaw[rad]  PF-sigma_yaw(shipped)  rms_yaw/PF')
    per_T = {}
    for T in HORIZONS:
        sel = [r for r in rows if r[1] == T]
        if len(sel) < 8:
            continue
        rx, ry, rz = (float(np.sqrt(np.mean([r[i] ** 2 for r in sel]))) for i in (2, 3, 4))
        pf = MP['noise_abs'][2] * math.sqrt(STEP * T)
        per_T[str(T)] = {'n': len(sel), 'rms_x': rx, 'rms_y': ry, 'rms_yaw': rz, 'pf_sigma_yaw': pf}
        print(f'{T:4.1f} {len(sel):5d}  {rx:8.4f}  {ry:8.4f}  {rz:11.5f}  {pf:14.4f}  {rz / pf:14.3f}')
    full = fit(rows)
    loeo = {}
    for ep in eps:
        f = fit([r for r in rows if r[0] != ep])
        for ax, vals in f.items():
            for k, v in vals.items():
                loeo.setdefault(ax, {}).setdefault(k, []).append(v)
    print('\nfull-fit  (leave-one-episode-out min..max in brackets)')
    for ax, vals in full.items():
        for k, v in vals.items():
            lo, hi = min(loeo[ax][k]), max(loeo[ax][k])
            print(f'  {ax:3s} {k:24s} {v:.6f}   [{lo:.6f} .. {hi:.6f}]')
    ac = float(np.mean([np.corrcoef(s[:-1], s[1:])[0, 1] for s in rate_res if len(s) > 8]))
    rr = np.concatenate(rate_res)
    print(f'\nyaw-rate residual rms {np.sqrt(np.mean(rr ** 2)):.5f} rad/s, lag-1 autocorr {ac:.3f}; '
          f'shipped noise_abs[2] {MP["noise_abs"][2]}, noise_rel {MP["noise_rel"]}, scale_std {MP["scale_std"]}, '
          f'scale_walk {MP["scale_walk"]}')
    if args.out:
        args.out.write_text(json.dumps({
            'source': 'outputs/owncam-loop-20260925/dev-a1..a4/dev-box-s31..33 (student drive segments)',
            'mean_model': {k: MP[k] for k in ('gain', 'tau_s', 'tau_stop_s')},
            'episodes': eps, 'windows': len(rows), 'per_horizon': per_T, 'fit': full,
            'loeo_range': {ax: {k: [min(v), max(v)] for k, v in d.items()} for ax, d in loeo.items()},
            'yaw_rate_residual_rms': float(np.sqrt(np.mean(rr ** 2))), 'yaw_rate_residual_lag1_autocorr': ac,
            'shipped_loaded': {k: MP[k] for k in ('noise_rel', 'noise_abs', 'scale_std', 'scale_walk')}},
            indent=1))


if __name__ == '__main__':
    main()
