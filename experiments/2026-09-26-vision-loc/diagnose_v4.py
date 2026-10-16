#!/usr/bin/env python3
"""Offline DEV-ONLY teacher-target diagnostics and motion fitting for VIS4.

GT is read here, never by vision_motion / the student replay. Test episodes are
rejected before opening any episode files. No rendering or network inference.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path

import numpy as np

import vision_loc as vl
import vision_loc_io as vio
from vision_motion import lag_integral

HERE = Path(__file__).resolve().parent
PLAN = HERE/'dev_plan_v4.json'
OUT = HERE.parents[1]/'outputs'/'vision-loc-v4'


def require_dev(episodes):
    if not episodes or len(set(episodes)) != len(episodes) or any(vio.split_of(e) != 'dev' for e in episodes):
        raise ValueError('VIS4 fitting/selection accepts unique dev episodes only')


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(data, f, indent=1, allow_nan=False)
        f.write('\n')


def own_states(commands, profiles, times):
    """Only issued commands determine load/profile, even in the fitting script."""
    load = vl.mp.load_m1_localizer().LoadState()
    ci = pi = 0
    profile, last_change, previous = None, -1e9, (False, None)
    states, ages = [], []
    for t in times:
        while ci < len(commands) and commands[ci]['t'] < t - 1e-9:
            load.command(commands[ci])
            ci += 1
        while pi < len(profiles) and profiles[pi][0] < t - 1e-9:
            profile = profiles[pi][1]
            pi += 1
        state = (bool(load.loaded), profile)
        if state != previous:
            last_change, previous = t, state
        states.append(state)
        ages.append(t - last_change)
    return states, np.asarray(ages)


def command_response(times, commands, gain, tau, stop_tau, delay):
    """Exact body integral of lagged issued commands at arbitrary timestamps.

    Independent offline fit calculation. Expiries split segments, superseded
    expiry events are cancelled. No finite-difference velocity target shift.
    """
    events = [(0., np.zeros(3))]
    expiry = math.inf
    for row in commands:
        if row['kind'] in ('initial_servo_command', 'arm', 'look'):
            continue
        t = float(row['t']) + delay
        if expiry < t - 1e-9:
            events.append((expiry, np.zeros(3)))
        if row['kind'] in ('drive', 'mecanum'):
            u = np.array([row['forward'], row.get('left', 0.) if row['kind'] == 'mecanum' else 0., row['turn']])
            expiry = t + float(row['duration_s'])
        else:
            u, expiry = np.zeros(3), math.inf
        events.append((t, u))
    if expiry < times[-1]:
        events.append((expiry, np.zeros(3)))
    events.append((max(times[-1] + 1., events[-1][0] + 1.), np.zeros(3)))
    out = np.zeros((len(times), 3))
    v, integral = np.zeros(3), np.zeros(3)
    for (start, u), (end, _) in zip(events, events[1:]):
        if end < start:
            raise ValueError('commands must be chronological')
        target = np.asarray(gain) @ u
        lag = tau if np.any(u) else stop_tau
        lo, hi = np.searchsorted(times, [start, end])
        if hi > lo:
            _, part = lag_integral(v, target, (times[lo:hi] - start)[:, None], lag)
            out[lo:hi] = integral + part
        v, distance = lag_integral(v, target, end - start, lag)
        integral += distance
    return np.diff(out, axis=0)/np.diff(times)[:, None]


def targets(ep):
    require_dev([ep])
    folder = vio.RENDER_ROOT/ep
    data = vl.student_inputs(folder)
    gt = vl.read_jsonl(folder/'eval_only'/'gt_trajectory.jsonl')
    t = np.array([r['t'] for r in gt])
    p = np.array([[r[k] for k in ('x', 'y', 'yaw')] for r in gt])
    d = np.diff(p, axis=0)
    d[:, 2] = np.arctan2(np.sin(d[:, 2]), np.cos(d[:, 2]))
    yaw = p[:-1, 2] + d[:, 2]/2
    c, s = np.cos(yaw), np.sin(yaw)
    body = np.column_stack([c*d[:, 0] + s*d[:, 1], -s*d[:, 0] + c*d[:, 1], d[:, 2]])/np.diff(t)[:, None]
    states, age = own_states(data['commands'], data['profile_events'], .5*(t[1:] + t[:-1]))
    return {'episode': ep, 't': t, 'body': body, 'commands': data['commands'], 'states': states, 'age': age}


def robust_scale(x, y, w, delta):
    scale = 1.
    for _ in range(12):
        residual = scale*x - y
        weight = w*np.minimum(1., delta/np.maximum(np.abs(residual), 1e-12))
        scale = float(np.clip(np.sum(weight*x*y)/max(np.sum(weight*x*x), 1e-12), .5, 1.5))
    r = np.abs(scale*x-y)
    loss = np.where(r <= delta, .5*r*r, delta*(r - .5*delta))
    return scale, float(np.sum(w*loss)/np.sum(w))


def fit(plan, output):
    require_dev(plan['fit_episodes'] + plan['validation_episodes'])
    rows = [targets(ep) for ep in plan['fit_episodes']]
    base, _ = vl.mp.load_m1_calibration()
    params = copy.deepcopy(base['params'])
    report, delays = {}, {}
    for loaded, key in ((False, 'motion'), (True, 'motion_loaded')):
        state = 'loaded' if loaded else 'unloaded'
        original = params[key]
        candidates = []
        for delay in plan['fit_rule']['delay_grid_s']:
            for tau in plan['fit_rule']['tau_grid_s']:
                xs, ys, ws, counts = [], [], [], {}
                for row in rows:
                    pred = command_response(row['t'], row['commands'], original['gain'], tau,
                                            original.get('tau_stop_s', tau), delay)
                    moving = (np.linalg.norm(row['body'][:, :2], axis=1) > .005) | (np.abs(row['body'][:, 2]) > .02)
                    mask = np.array([s == (loaded, None) for s in row['states']]) & (row['age'] > 1.5) & moving
                    n = int(mask.sum())
                    counts[row['episode']] = n
                    if n:
                        xs.append(pred[mask]); ys.append(row['body'][mask]); ws.append(np.full(n, 1./n))
                x, y, w = np.concatenate(xs), np.concatenate(ys), np.concatenate(ws)
                scales, losses, excitation = [], [], []
                for axis, delta in enumerate((.03, .03, .10)):
                    active = np.abs(x[:, axis]) > (.003 if axis < 2 else .01)
                    n = int(active.sum())
                    excitation.append(n)
                    if n < 100:
                        scale, loss = 1., 0.  # unidentifiable axis retained, not a fitted success
                    else:
                        scale, loss = robust_scale(x[active, axis], y[active, axis], w[active], delta)
                    scales.append(scale); losses.append(loss/(delta*delta))
                candidates.append({'delay_s': delay, 'tau_s': tau, 'scale': scales, 'loss': sum(losses),
                                   'axis_loss': losses, 'excited_intervals': excitation, 'episode_intervals': counts})
        best = min(candidates, key=lambda c: (c['loss'], c['delay_s'], c['tau_s']))
        params[key]['gain'] = (np.array(original['gain'])*np.array(best['scale'])[:, None]).tolist()
        params[key]['tau_s'] = best['tau_s']
        delays[state] = best['delay_s']
        report[state] = {'selected': best, 'grid': candidates}
    fitted = {'schema': 'ugrp.vision_loc.motion_dev.v4', 'params': params, 'motion_v4': {'exact': True, 'delay_s': delays},
              'plan_sha256': vio.sha_file(PLAN), 'fit_episodes': plan['fit_episodes'], 'fit': report,
              'source_files_sha256': {str(vio.RENDER_ROOT/e/p): vio.sha_file(vio.RENDER_ROOT/e/p)
                                      for e in plan['fit_episodes'] for p in ('inputs/commands.jsonl',
                                           'inputs/motion_profile.jsonl', 'eval_only/gt_trajectory.jsonl')}}
    save(output, fitted)
    print(json.dumps({k: v['selected'] for k, v in report.items()}), flush=True)


def error_summary(rows):
    if not rows:
        return {'n': 0}
    a = np.asarray(rows)
    return {'n': len(a), 'dx_mean_m': float(a[:, 0].mean()), 'dy_mean_m': float(a[:, 1].mean()),
            'forward_mean_m': float(a[:, 3].mean()), 'pos_p90_m': float(np.percentile(np.linalg.norm(a[:, :2], axis=1), 90)),
            'dx_abs_p90_m': float(np.percentile(np.abs(a[:, 0]), 90)),
            'lat_abs_p99_m': float(np.percentile(np.abs(a[:, 1]), 99)),
            'yaw_p90_deg': float(np.percentile(np.abs(a[:, 2]), 90)),
            'lost_frames': int((np.linalg.norm(a[:, :2], axis=1) > .30).sum())}


def diagnose(plan, output):
    eps = plan['fit_episodes'] + plan['validation_episodes']
    require_dev(eps)
    report = {'plan_sha256': vio.sha_file(PLAN), 'loadavg': os.getloadavg(), 'episodes': {}, 'pooled': {}, 'sources': {}}
    pooled = {}
    for ep in eps:
        folder = vio.RENDER_ROOT/ep
        data = vl.student_inputs(folder)
        frames = data['frames']
        ev = {r['frame']: r for r in vl.read_jsonl(folder/'eval_only'/'frames_eval.jsonl')}
        labels = {r['frame_id']: r for r in vl.read_jsonl(folder/'eval_only'/'labels.jsonl')}
        alignment = {'frames': len(frames), 'frame_eval_time_mismatch': 0, 'frame_label_time_mismatch': 0,
                     'label_rgb_hash_mismatch': 0, 'servo_before_frame_mismatch': 0, 'servo_at_frame_mismatch': 0,
                     'max_label_gt_position_delta_m': 0.}
        def servo_audit(inclusive):
            servo, ci, mismatch = {}, 0, 0
            for row in frames:
                while ci < len(data['commands']) and (data['commands'][ci]['t'] <= row['t'] + 1e-9 if inclusive
                                                     else data['commands'][ci]['t'] < row['t'] - 1e-9):
                    c = data['commands'][ci]; ci += 1
                    if c['kind'] == 'initial_servo_command': servo = dict(c['pulses'])
                    elif c['kind'] == 'arm': servo[str(c['servo_id'])] = c['pulse']
                    elif c['kind'] == 'look': servo['6'] = c['pan_pulse']
                mismatch += servo != row['commanded_servo']
            return mismatch
        alignment['servo_before_frame_mismatch'] = servo_audit(False)
        alignment['servo_at_frame_mismatch'] = servo_audit(True)
        for row in frames:
            lab, gt = labels[row['frame_id']], ev[row['frame']]
            alignment['frame_eval_time_mismatch'] += abs(row['t'] - gt['t']) > 1e-4
            alignment['frame_label_time_mismatch'] += abs(row['t'] - lab['sim_time']) > 1e-4
            alignment['label_rgb_hash_mismatch'] += row['sha256'] != lab['frame_sha256']
            alignment['max_label_gt_position_delta_m'] = max(alignment['max_label_gt_position_delta_m'],
                float(np.linalg.norm(np.array(lab['base_gt'][:2]) - gt['gt'][:2])))
        per = {'alignment': alignment, 'filters': {}}
        for kind, sub in (('vision', 'dev-grid'), ('oracle', 'dev-oracle')):
            path = vio.PRIMARY_OUT/'r3'/sub/'a1_open'/f'{ep}.estimates.jsonl'
            report['sources'][str(path)] = vio.sha_file(path)
            errors = {}
            for r in vl.read_jsonl(path):
                if not r.get(kind): continue
                gt = ev[r['frame']]['gt']; est = r[kind]['xyyaw']
                dx, dy = est[0]-gt[0], est[1]-gt[1]
                yaw = math.degrees(math.atan2(math.sin(est[2]-gt[2]), math.cos(est[2]-gt[2])))
                val = (dx, dy, yaw, math.cos(gt[2])*dx + math.sin(gt[2])*dy)
                groups = ['all', 'loaded' if r['loaded'] else 'unloaded', 'phase_'+str(r['phase'])]
                if abs(gt[0]-2.2) < .6 and -.45 < gt[1] < .55:
                    groups += ['door', 'door_loaded' if r['loaded'] else 'door_unloaded']
                for group in groups:
                    errors.setdefault(group, []).append(val)
                    pooled.setdefault(kind, {}).setdefault(group, []).append(val)
            per['filters'][kind] = {g: error_summary(v) for g, v in errors.items()}
        row = targets(ep)
        b = row['body']; moving = (np.linalg.norm(b[:, :2], axis=1) > .005) | (np.abs(b[:, 2]) > .02)
        per['motion_intervals'] = {'total': len(b), 'stationary': int((~moving).sum()),
                                   'loaded': sum(s[0] for s in row['states']),
                                   'fine': sum(s[1] is not None for s in row['states'])}
        report['episodes'][ep] = per
        print(ep, alignment, per['filters']['vision'].get('door_loaded'), flush=True)
    report['pooled'] = {k: {g: error_summary(v) for g, v in groups.items()} for k, groups in pooled.items()}
    save(output, report)


def likelihood(plan, output):
    eps = plan['fit_episodes'] + plan['validation_episodes']
    require_dev(eps)
    cfg = vio.load_json(HERE/'selected_config_v3.json')
    cal = vio.load_json(HERE/'calibration_train.json')
    geometry = vl.mp.MapGeometry(vio.load_map(), include_posts=False)
    offsets = np.linspace(-.10, .10, 21)
    rows = []
    for ep in eps:
        data = vl.student_inputs(vio.RENDER_ROOT/ep)
        ev = {r['frame']: r for r in vl.read_jsonl(vio.RENDER_ROOT/ep/'eval_only'/'frames_eval.jsonl')}
        states, _ = own_states(data['commands'], data['profile_events'], [r['t'] for r in data['frames']])
        caches = {}
        for kind, sub in (('vision', 'obs-w6'), ('oracle', 'oracle-w6')):
            caches[kind], _ = vio.load_obs(vio.PRIMARY_OUT/'r3'/sub/f'{ep}.obs.npz', kind=kind, episode=ep,
                obs_params=vio.config_obs_params(cfg), checkpoint_sha256=plan['fixed']['segmentation_sha256'],
                infer_size=cfg['infer_size'])
        ci, last_arm = 0, -1e9
        for k, frame in enumerate(data['frames']):
            t = frame['t']
            while ci < len(data['commands']) and data['commands'][ci]['t'] < t - 1e-9:
                cmd = data['commands'][ci]; ci += 1
                if cmd['kind'] in ('arm', 'look', 'initial_servo_command'): last_arm = cmd['t']
            gt = np.array(ev[frame['frame']]['gt'])
            if k % 10 or not states[k][0] or abs(gt[0]-2.2) >= .6 or not -.45 < gt[1] < .55 or t-last_arm < .2-1e-9:
                continue
            pose = {int(a): int(b) for a, b in frame['commanded_servo'].items()}
            b, dz = vl.sag(cal['sag'], True, pose)
            pan = vl.pan_yaw(cal.get('pan_base_yaw', {}), True, pose)
            for kind, obs_map in caches.items():
                obs = obs_map[frame['frame']]
                px = np.tile(gt, (len(offsets), 1)); px[:, 0] += offsets; px[:, 2] -= pan
                cm = vl.column_model(pose, b, dz, obs.columns, pan)
                vb, vt = vl.expected_rows(geometry, px, cm)
                ll = vl.column_loglik(vb, vt, obs, cfg['measurement'])
                # Report tied plateau, not an artificial leftmost argmax.
                maxima = offsets[ll >= ll.max()-1e-7]
                rows.append({'episode': ep, 'frame': frame['frame'], 'kind': kind, 't': t,
                             'argmax_mid_m': float(np.mean(maxima)), 'argmax_lo_m': float(maxima.min()),
                             'argmax_hi_m': float(maxima.max()), 'll_plus3_minus_minus3': float(ll[13]-ll[7]),
                             'll_range': float(np.ptp(ll)), 'loglik': ll.tolist()})
    summary = {}
    for kind in ('vision', 'oracle'):
        subset = [r for r in rows if r['kind'] == kind]
        peaks = np.array([r['argmax_mid_m'] for r in subset])
        summary[kind] = {'n': len(subset), 'peak_mean_m': float(peaks.mean()),
                         'peak_abs_p90_m': float(np.percentile(np.abs(peaks), 90)),
                         'mean_ll_plus3_minus_minus3': float(np.mean([r['ll_plus3_minus_minus3'] for r in subset])),
                         'at_grid_edge': sum(r['argmax_lo_m'] <= -.1 or r['argmax_hi_m'] >= .1 for r in subset)}
    save(output, {'plan_sha256': vio.sha_file(PLAN), 'offsets_m': offsets.tolist(), 'summary': summary, 'rows': rows,
                  'scope': 'GT-centred one-dimensional diagnostic, not an identifiable 3D estimate or student input'})
    print(json.dumps(summary), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['diagnose', 'fit', 'likelihood'])
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    plan = json.loads(PLAN.read_text())
    {'diagnose': diagnose, 'fit': fit, 'likelihood': likelihood}[args.action](plan, args.output)


if __name__ == '__main__':
    main()
