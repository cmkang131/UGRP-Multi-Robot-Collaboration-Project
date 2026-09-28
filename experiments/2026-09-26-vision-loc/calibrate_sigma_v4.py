#!/usr/bin/env python3
"""DEV-only cached-estimate calibration. Evaluation truth never enters the head.

Run --diagnose to audit legacy records, then the finite frozen plan with --compare.
Neither operation renders or calls a perception model. Old full covariance was
not recorded: all legacy NEES/NLL/coverage here explicitly assume isotropic XY.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import diagnose_v4 as d
import vision_loc as vl
import vision_loc_io as vio
import vision_sigma as vs

HERE = Path(__file__).resolve().parent
PLAN = HERE / 'sigma_plan_v4.json'
VISW = Path('/Users/changmin/projects/ugrp/outputs/vision-worker-closed-loop-20260927/vl3-dev-s942')
RUNTIME = ('vision_sigma.py', 'vision_pf_v4.py', 'vision_loc.py', 'vision_loc_cli_v4.py',
           'vision_motion.py', 'vision_loc_io.py', 'diagnose_v4.py',
           '../2026-09-26-markerless-probe/markerless_probe.py',
           'calibrate_sigma_v4.py', 'sigma_plan_v4.json', 'selected_config_v3.json')


def read(path, sources):
    sources[str(path)] = vio.sha_file(path)
    return vl.read_jsonl(path)


def command_features(frames, commands, settle_s):
    """Replay issued commands only; same-time frame precedes commands."""
    load = vl.mp.load_m1_localizer().LoadState()
    j, last_arm = 0, -1e9
    values = []
    for f in frames:
        t = float(f['t'])
        while j < len(commands) and commands[j]['t'] < t - 1e-9:
            row = commands[j]
            load.command(row)
            if row['kind'] in ('initial_servo_command', 'look', 'arm'):
                last_arm = float(row['t'])
            j += 1
        pose = {int(k): int(v) for k, v in f['commanded_servo'].items()}
        if pose != load.servo:
            raise ValueError(f"own commanded-servo mismatch frame={f['frame']}")
        values.append((bool(load.loaded), t - last_arm >= settle_s - 1e-9))
    return values


def sequence(name, kind, rows, gt, own, *, visw=False):
    records, last_scan = [], None
    for f, (loaded, settled) in zip(rows, own, strict=True):
        e = f['report'] if visw else f[kind]
        if not e or (visw and not e['initialized']):
            raise ValueError('missing estimate; cannot drop failed frames')
        g = gt[f['frame']]
        if abs(float(f['t']) - float(g['t'])) > 1e-7:
            raise ValueError('frame/evaluation timestamp mismatch')
        if visw:
            if (e['load_state'] == 'loaded') != loaded or abs(e['t_est'] - f['t']) > 1e-7:
                raise ValueError('VISW own report alignment mismatch')
            observed = e.get('last_valid_obs')
            last_scan = None if observed is None else observed['t']
        else:
            if bool(f['loaded']) != loaded or bool(f['settled']) != settled:
                raise ValueError('baseline command-state mismatch')
            if e['measured']:
                last_scan = f['t']
        xy = np.asarray(e['xyyaw'], float)
        err = xy - np.asarray(g['gt'], float)
        err[2] = math.atan2(math.sin(err[2]), math.cos(err[2]))
        records.append([f['frame'], f['t'], np.nan if last_scan is None else last_scan,
                        vs.STATES.index(vs.state_key(loaded, settled)), e['std_xy_m']**2,
                        float(err[:2] @ err[:2]), abs(err[2]), e['std_yaw_rad'], *xy, *g['gt']])
    a = np.array(records, float)
    if not len(a) or not np.isfinite(a[:, 3:]).all() or np.any(np.diff(a[:, 1]) < 0):
        raise ValueError('invalid or empty sequence')
    return {'name': name, 'kind': kind, 'a': a,
            'point_sha256': hashlib.sha256(a[:, 8:11].tobytes()).hexdigest()}


def load_data(plan):
    fit, val = plan['fit_teacher_episodes'], plan['validation_teacher_episodes']
    d.require_dev(fit + val)
    if set(fit) & set(val) or plan['fit_closed_loop'] != ['VISW-vl3-dev-s942-r2']:
        raise ValueError('invalid dev cohort')
    sources, data = {}, []
    cfg = vio.load_json(HERE/'selected_config_v3.json')
    settle = cfg.get('measurement', {}).get('settle_s', vl.DEFAULT_MEASUREMENT['settle_s'])
    for ep in fit + val:
        original = vio.RENDER_ROOT/ep
        frames = read(original/'inputs/frames.jsonl', sources)
        commands = read(original/'inputs/commands.jsonl', sources)
        own = command_features(frames, commands, settle)
        gt = {r['frame']: r for r in read(original/'eval_only/frames_eval.jsonl', sources)}
        rows = read(d.OUT/'comparison/b0'/f'{ep}.estimates.jsonl', sources)
        if [(f['frame'], f['t']) for f in frames] != [(f['frame'], f['t']) for f in rows]:
            raise ValueError('baseline input-frame mismatch')
        for kind in ('vision', 'oracle'):
            s = sequence(ep, kind, rows, gt, own)
            s['cohort'] = 'fit_teacher' if ep in fit else 'validation'
            data.append(s)
    frames = read(VISW/'robots/r2/inputs/frames.jsonl', sources)
    commands = read(VISW/'robots/r2/inputs/commands.jsonl', sources)
    own = command_features(frames, commands, settle)
    gt = {r['frame']: r for r in read(VISW/'eval_only/frames_eval.jsonl', sources) if r['robot_id'] == 'r2'}
    s = sequence('VISW-vl3-dev-s942-r2', 'vision', frames, gt, own, visw=True)
    s['cohort'] = 'fit_VISW'; data.append(s)
    for name in ('result.json', 'manifest.json', 'robots/r2/executor/events.jsonl'):
        sources[str(VISW/name)] = vio.sha_file(VISW/name)
    return data, sources


def variance_series(s, config):
    if not config.get('enabled'):
        return s['a'][:, 4].copy()
    head, values = vs.VarianceCalibrator(config), []
    for r in s['a']:
        key = vs.STATES[int(r[3])]
        values.append(head.step(float(r[4]), float(r[1]), None if np.isnan(r[2]) else float(r[2]),
                                key.startswith('loaded_'), key.endswith('_settled')))
    return np.asarray(values)


def metrics(a, variance):
    if not len(a):
        return {'n': 0}
    v = np.maximum(variance, vs.VAR_FLOOR)
    z = a[:, 5] / v
    out = {'n': len(a), 'nll_iso': float(np.mean(np.log(math.pi*v) + z)),
           'nees_iso_mean': float(np.mean(2*z)), 'nees_iso_p90': float(np.quantile(2*z, .9)),
           'over_3sigma_fraction': float(np.mean(z > 9.)),
           'sigma_p50_m': float(np.median(np.sqrt(v))), 'sigma_p90_m': float(np.quantile(np.sqrt(v), .9)),
           'error_p50_m': float(np.median(np.sqrt(a[:, 5]))), 'error_p90_m': float(np.quantile(np.sqrt(a[:, 5]), .9)),
           'yaw_error_p90_deg': float(np.rad2deg(np.quantile(a[:, 6], .9))),
           'yaw_sigma_p90_deg': float(np.rad2deg(np.quantile(a[:, 7], .9)))}
    for p in (.5, .9, .95, .99):
        out[f'coverage{int(100*p)}'] = float(np.mean(z <= -math.log(1-p)))
    return out


def summaries(data, variances):
    out = {'sequences': {}, 'cohorts': {}}
    for s, v in zip(data, variances, strict=True):
        a = s['a']; age = a[:, 1] - np.nan_to_num(a[:, 2], nan=0.)
        stale = (a[1:, 2] == a[:-1, 2]) | (np.isnan(a[1:, 2]) & np.isnan(a[:-1, 2]))
        details = {'all': metrics(a, v), 'states': {}, 'age': {},
                   'stale_intervals': int(stale.sum()),
                   'stale_variance_decreases': int(np.sum(stale & (np.diff(v) < -1e-12))),
                   'max_scan_age_s': float(age.max()), 'point_sha256': s['point_sha256']}
        for i, key in enumerate(vs.STATES):
            mask = a[:, 3] == i; details['states'][key] = metrics(a[mask], v[mask])
        for key, mask in [('fresh', age <= .25), ('age_025_1', (age > .25) & (age <= 1)), ('age_gt1', age > 1)]:
            details['age'][key] = metrics(a[mask], v[mask])
        if s['cohort'] == 'fit_VISW':
            for key, lo, hi in [('grasp_90_150', 90, 150), ('near_A_430_462', 430, 462)]:
                mask = (a[:, 1] >= lo) & (a[:, 1] <= hi)
                details[key] = metrics(a[mask], v[mask])
                details[key]['xy_sigma_above_loaded_007'] = int(np.sum(np.sqrt(v[mask]) > .07))
                details[key]['yaw_sigma_above_loaded_3deg'] = int(np.sum(a[mask, 7] > math.radians(3)))
        out['sequences'][s['name']+'/'+s['kind']] = details
    for cohort in ('fit_teacher', 'fit_VISW', 'validation', 'all_dev'):
        for kind in ('vision', 'oracle'):
            chosen = [(s, v) for s, v in zip(data, variances, strict=True)
                      if s['kind'] == kind and (cohort == 'all_dev' or s['cohort'] == cohort)]
            if not chosen: continue
            result = metrics(np.concatenate([s['a'] for s, _ in chosen]), np.concatenate([v for _, v in chosen]))
            result['episode_balanced_nll_iso'] = float(np.mean([metrics(s['a'], v)['nll_iso'] for s, v in chosen]))
            result['episodes'] = len(chosen)
            out['cohorts'][cohort+'/'+kind] = result
    return out


def fit(data, plan):
    training = [s for s in data if s['kind'] == 'vision' and s['cohort'].startswith('fit_')]
    a = np.concatenate([s['a'] for s in training])
    w = np.concatenate([np.full(len(s['a']), 1./len(s['a'])/len(training)) for s in training])
    raw, error = np.maximum(a[:, 4], vs.VAR_FLOOR), a[:, 5]
    scale = float(np.clip(np.sum(w * error / raw), .0625, 4096.))
    global_state = dict(a=scale, b_m2=0., q_m2_s=0.)
    u1 = {'enabled': True, 'stale_envelope': False, 'states': {k: dict(global_state) for k in vs.STATES}}
    u2 = {'enabled': True, 'stale_envelope': True, 'states': {}}
    fit_details = {'fit_names': [s['name'] for s in training], 'state_fit': {}}
    rule = plan['fit_rule']
    for i, key in enumerate(vs.STATES):
        mask = a[:, 3] == i
        if mask.sum() < 100:
            result = dict(global_state)
            loss = None
        else:
            choices = []
            for mult, b_std in itertools.product(rule['a_grid'], rule['b_std_grid_m']):
                v = mult*raw[mask] + b_std**2
                loss = float(np.sum(w[mask]*(np.log(math.pi*v) + error[mask]/v))/np.sum(w[mask]))
                choices.append((loss, mult, b_std**2))
            loss, mult, bias = min(choices)
            result = dict(a=mult, b_m2=bias, q_m2_s=0.)
        u2['states'][key] = result
        fit_details['state_fit'][key] = {'frames': int(mask.sum()), 'stage1_nll_iso': loss, **result}
    best = None
    for qs in itertools.product(rule['q_trace_grid_m2_per_s'], repeat=len(vs.STATES)):
        for key, q in zip(vs.STATES, qs, strict=True): u2['states'][key]['q_m2_s'] = q
        loss = float(np.mean([metrics(s['a'], variance_series(s, u2))['nll_iso'] for s in training]))
        candidate = (loss, qs)
        if best is None or candidate < best: best = candidate
    for key, q in zip(vs.STATES, best[1], strict=True): u2['states'][key]['q_m2_s'] = q
    fit_details['stage2_nll_iso'] = best[0]
    return {'u0': {'enabled': False}, 'u1': u1, 'u2': u2}, fit_details


def select(results):
    base = results['u0']; checks, eligible = {}, []
    for name in ('u1', 'u2'):
        result = results[name]; b = base['cohorts']['validation/vision']; c = result['cohorts']['validation/vision']
        reasons = []
        if c['episode_balanced_nll_iso'] > b['episode_balanced_nll_iso'] - .05 + 1e-12: reasons.append('NLL_not_improved_005')
        if not .90 <= c['coverage95'] <= .99: reasons.append('coverage95_outside_090_099')
        if c['over_3sigma_fraction'] > .01: reasons.append('over_3sigma_above_001')
        for key, value in result['sequences'].items():
            if value['point_sha256'] != base['sequences'][key]['point_sha256']: reasons.append('point_changed')
            if key in ('vl3-dev-s945/vision', 'vl3-dev-s946/vision', 'vl3-dev-s947/vision'):
                if value['all']['nll_iso'] > base['sequences'][key]['all']['nll_iso'] + .1:
                    reasons.append(key+':NLL_regressed_010')
        if (result['cohorts']['validation/oracle']['episode_balanced_nll_iso'] >
                base['cohorts']['validation/oracle']['episode_balanced_nll_iso'] + .1):
            reasons.append('oracle_NLL_regressed_010')
        checks[name] = {'eligible': not reasons, 'reasons': reasons}
        if not reasons: eligible.append(name)
    chosen = min(eligible, key=lambda n: (results[n]['cohorts']['validation/vision']['episode_balanced_nll_iso'], n)) if eligible else 'u0'
    return {'selected': chosen, 'checks': checks, 'motion_promotion': 'NO_GO_UNCHANGED',
            'new_test_enabled': False, 'scope': 'cached DEV covariance reports only; no closed-loop behavior claim'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--diagnose', action='store_true'); mode.add_argument('--compare', action='store_true')
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    output = args.output or d.OUT/('sigma' if args.compare else 'sigma_diagnosis')
    output.mkdir(parents=True, exist_ok=False)
    plan = vio.load_json(PLAN)
    source_hashes = {str(HERE/f): vio.sha_file(HERE/f) for f in RUNTIME}
    d.save(output/'source_freeze.json', {'source_sha256': source_hashes, 'loadavg_start': os.getloadavg(),
                                       'plan_sha256': vio.sha_file(PLAN), 'git_commit_created': False,
                                       'started_utc': datetime.now(timezone.utc).isoformat(),
                                       'python': platform.python_version(), 'numpy': np.__version__,
                                       'OMP_NUM_THREADS': os.environ.get('OMP_NUM_THREADS')})
    data, inputs = load_data(plan)
    d.save(output/'input_hashes.json', inputs)
    if args.compare:
        configs, details = fit(data, plan)
        d.save(output/'fit.json', details)
    else:
        configs = {'u0': {'enabled': False}}
    results = {}
    for name, config in configs.items():
        values = [variance_series(s, config) for s in data]
        results[name] = summaries(data, values)
        d.save(output/f'{name}.json', {'sigma_v4': config})
        np.savez_compressed(output/f'{name}_variance.npz', **{s['name']+'_'+s['kind']: v for s, v in zip(data, values, strict=True)})
    d.save(output/'metrics.json', results)
    if args.compare:
        decision = select(results); d.save(output/'selection.json', decision); print(json.dumps(decision), flush=True)
    mismatches = [p for p, h in {**inputs, **source_hashes}.items() if vio.sha_file(Path(p)) != h]
    d.save(output/'verification.json', {'input_files': len(inputs), 'runtime_files': len(source_hashes),
         'mismatches': mismatches, 'sequences': len(data), 'vision_frames': sum(len(s['a']) for s in data if s['kind'] == 'vision'),
         'oracle_frames': sum(len(s['a']) for s in data if s['kind'] == 'oracle'), 'new_model_calls': 0,
         'new_physics_runs': 0, 'full_covariance_available_in_legacy_data': False,
         'covariance_rounding_scope': 'Shadow uses rounded legacy sigma squared; future online uses full recorded covariance trace.',
         'point_estimates_unchanged': True, 'loadavg_end': os.getloadavg()})
    if mismatches: raise ValueError(f'input/runtime changed: {mismatches}')
    print(output, flush=True)


if __name__ == '__main__':
    main()
