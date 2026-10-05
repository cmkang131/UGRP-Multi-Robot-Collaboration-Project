"""Offline v87 unloaded calibration; NumPy/file IO only, no student factory.

Reuse the v2 stop-fit window/least-squares method and M1 fine-fit tau grid,
with the existing VIS4 exact lag integral at the recorded sample timestamps.
GT is an offline teacher target. This product cannot qualify P03.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = '04eb11c6a001f2a7d2ab916765d59b3661c06efe'
CONTRACT = 'configs/calibration/zone_final_v3_floor_light_contract.json'
PLAN = 'configs/final_environment_measurement_v1.json'
V2 = 'experiments/2026-09-26-zone-owncam-loop-v2/fit_stop_dynamics.py'
FINE = 'experiments/2026-09-26-zone-m1-owncam/fit_fine_motion.py'
INTEGRAL = 'experiments/2026-09-26-vision-loc/vision_motion.py'
CAMERA_METHOD = 'experiments/2026-09-26-vision-loc/vision_loc_cli.py'
OLD_MOTION = 'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json'
OLD_CAMERA = 'experiments/2026-09-26-vision-loc/calibration_train.json'
AXES = ('forward', 'lateral', 'rotate')
TAU_GRID = np.round(np.arange(.05, 3.01, .01), 2)
STOP_GRID = np.array([.03, .05, .08, .12, .2, .3, .44, 1.])
SENSITIVITY_TAUS = (3., 5., 10., 30., 100.)
# Exploratory terminal-window summary, after the legacy 0.3 s filter showed
# large pan transients. Both filters' results are retained, not a new gate.
CAMERA_SETTLED_S = 1.0
MISSING = 'loaded collection not yet run'


def read(path):
    return json.loads(Path(path).read_text())


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def load_integral():
    spec = importlib.util.spec_from_file_location('v87_offline_lag', ROOT / INTEGRAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.lag_integral


lag_integral = load_integral()


def wrap(value):
    return np.arctan2(np.sin(value), np.cos(value))


def spread(values):
    a = np.asarray(values, float)
    return {'min': np.min(a, axis=0).tolist(), 'max': np.max(a, axis=0).tolist(),
            'range': np.ptp(a, axis=0).tolist(), 'std_ddof1': np.std(a, axis=0, ddof=1).tolist()}


def response(t, duration, tau, stop_tau):
    """Unit-speed displacement: exact first-order drive then stop coast.

    Same ODE as v2 fit_stop_dynamics; use the existing lag_integral helper
    instead of shifting the first sample by v2's 0.01 s integration bin.
    Four contiguous 0.25 s renewals are one uninterrupted 1 s command.
    """
    t = np.asarray(t, float)
    vel, distance = lag_integral(0., 1., np.minimum(t, duration), tau)
    end_v, end_d = lag_integral(0., 1., duration, tau)
    _, coast = lag_integral(end_v, 0., np.maximum(t - duration, 0.), stop_tau)
    return np.where(t <= duration, distance, end_d + coast)


def blocks(commands):
    out = []
    for row in commands:
        if row['kind'] != 'mecanum':
            continue
        u = np.array([row['forward'], row['left'], row['turn']], float)
        if np.count_nonzero(u) != 1 or row['duration_s'] <= 0:
            raise ValueError('expected single-axis issued commands')
        start, end = row['t'], row['t'] + row['duration_s']
        if out and abs(out[-1]['end'] - start) < 1e-7 and np.array_equal(out[-1]['u'], u):
            out[-1]['end'] = end
            out[-1]['command_count'] += 1
        else:
            out.append({'start': start, 'end': end, 'u': u, 'command_count': 1})
    if len(out) != 6 or any(b['command_count'] != 4 for b in out):
        raise ValueError('expected six contiguous 4-command motion blocks')
    return out


def trajectory(labels):
    t = np.array([r['t'] for r in labels])
    p = np.array([r['base_position_m'] for r in labels])
    r = np.array([r['base_rotation'] for r in labels])
    yaw = np.unwrap(np.arctan2(r[:, 1, 0], r[:, 0, 0]))
    return t, p, yaw


def motion_windows(commands, labels):
    t, p, yaw = trajectory(labels)
    result = []
    for b in blocks(commands):
        # Equal four-second windows: active 1 s plus 3 s of observed stop.
        sel = (t >= b['start'] - 1e-7) & (t <= b['start'] + 4. + 1e-7)
        ix = np.flatnonzero(sel)
        if len(ix) != 21 or abs(t[ix[0]] - b['start']) > 1e-7:
            raise ValueError('missing motion window samples')
        delta = p[ix] - p[ix[0]]
        c, s = math.cos(yaw[ix[0]]), math.sin(yaw[ix[0]])
        body = np.column_stack([c * delta[:, 0] + s * delta[:, 1],
                                -s * delta[:, 0] + c * delta[:, 1], wrap(yaw[ix] - yaw[ix[0]])])
        axis = int(np.flatnonzero(b['u'])[0])
        result.append({**b, 'axis': axis, 'times': t[ix] - t[ix[0]], 'body': body,
                       'duration': b['end'] - b['start']})
    return result


def fit_axis(windows, axis):
    ws = [w for w in windows if w['axis'] == axis]
    y = np.concatenate([w['body'][:, axis] for w in ws])
    candidates = []
    for tau in TAU_GRID:
        for stop_tau in STOP_GRID:
            x = np.concatenate([w['u'][axis] * response(w['times'], w['duration'], tau, stop_tau) for w in ws])
            # v2 least squares, unrestricted signed gain: no clamp to old values.
            gain = float(x @ y / (x @ x))
            residual = gain * x - y
            rms = float(np.sqrt(np.mean(residual ** 2)))
            candidates.append((rms, float(tau), float(stop_tau), gain))
    rms, tau, stop_tau, gain = min(candidates)
    null_rms = float(np.sqrt(np.mean(y ** 2)))
    # Sensitivity band is descriptive, not a confidence interval or gate.
    near = [c for c in candidates if c[0] <= rms * 1.05 + 1e-15]
    sensitivity = []
    for td in SENSITIVITY_TAUS:
        options = []
        for ts in STOP_GRID:
            x = np.concatenate([w['u'][axis] * response(w['times'], w['duration'], td, ts) for w in ws])
            g = float(x @ y / (x @ x))
            options.append((float(np.sqrt(np.mean((g * x - y) ** 2))), float(ts), g))
        error, ts, g = min(options)
        sensitivity.append({'tau_s': td, 'tau_stop_s': ts, 'gain': g, 'rms': error})
    unidentified = null_rms < 1e-10 or gain <= 0 or rms >= null_rms or any(c['rms'] < rms for c in sensitivity)
    observed = []
    for w in ws:
        stop_i = int(np.argmin(abs(w['times'] - w['duration'])))
        predicted = gain * w['u'][axis] * response(w['times'], w['duration'], tau, stop_tau)
        observed.append({'start_t': w['start'], 'command_count': w['command_count'],
                         'command_integral': float(w['u'][axis] * w['duration']),
                         'observed_at_expiry': float(w['body'][stop_i, axis]),
                         'observed_after_stop': float(w['body'][-1, axis]),
                         'stop_drift': float(w['body'][-1, axis] - w['body'][stop_i, axis]),
                         'cross_axis_end_body_m_m_rad': w['body'][-1].tolist(),
                         'times_s': w['times'].tolist(), 'observed': w['body'][:, axis].tolist(),
                         'predicted': predicted.tolist(),
                         'residual_pred_minus_observed': (predicted - w['body'][:, axis]).tolist()})
    return {'gain': gain, 'tau_s': tau, 'tau_stop_s': stop_tau, 'rms': rms, 'zero_model_rms': null_rms,
            'relative_rms': rms / null_rms if null_rms else None,
            'degenerate': null_rms < 1e-10 or gain <= 0 or rms >= null_rms,
            'gain_lag_identified': not unidentified,
            'fit_status': 'GAIN_LAG_UNIDENTIFIED' if unidentified else 'EXPLORATORY_GRID_FIT',
            'extended_tau_sensitivity_not_selected': sensitivity,
            'tau_on_grid_boundary': tau in (TAU_GRID[0], TAU_GRID[-1]),
            'stop_tau_on_grid_boundary': stop_tau in (STOP_GRID[0], STOP_GRID[-1]),
            'within_5pct_min_rms': {'tau_s': [min(c[1] for c in near), max(c[1] for c in near)],
                                  'tau_stop_s': [min(c[2] for c in near), max(c[2] for c in near)],
                                  'gain': [min(c[3] for c in near), max(c[3] for c in near)]},
            'units': 'rad' if axis == 2 else 'm', 'windows': observed}


def camera_in_chassis(label):
    """VIS3 MuJoCo->optical convention, using full recorded chassis rotation.

    Origin is relative to the actual 3-D chassis body origin (not ground z=0).
    No v2 FK/sag is used or extrapolated to unvisited poses.
    """
    rb, rc = np.asarray(label['base_rotation']), np.asarray(label['camera_rotation'])
    for r in (rb, rc):
        if r.shape != (3, 3) or not np.isfinite(r).all() or not np.allclose(r.T @ r, np.eye(3), atol=1e-8) or not np.isclose(np.linalg.det(r), 1., atol=1e-8):
            raise ValueError('invalid recorded camera/base rotation')
    origin = rb.T @ (np.asarray(label['camera_position_m']) - np.asarray(label['base_position_m']))
    return origin, rb.T @ rc @ np.diag([1., -1., -1.])


def camera_summary(records):
    origins = np.array([r[0] for r in records])
    rotations = np.array([r[1] for r in records])
    center = np.median(origins, axis=0)
    # Preserve an actual proper rotation: nearest recorded matrix to the
    # coordinatewise median, rather than an invalid elementwise median matrix.
    med = np.median(rotations, axis=0)
    rotation = rotations[np.argmin(np.sum((rotations - med) ** 2, axis=(1, 2)))]
    angles = np.arccos(np.clip((np.trace(rotations @ rotation.T, axis1=1, axis2=2) - 1) / 2, -1, 1))
    residual_m = np.linalg.norm(origins - center, axis=1)
    return {'origin_m': center.tolist(), 'rotation': rotation.tolist(), 'n': len(records),
            'origin_residual_rms_m': float(np.sqrt(np.mean(residual_m ** 2))),
            'origin_residual_max_m': float(residual_m.max()),
            'rotation_residual_p95_deg': float(np.degrees(np.percentile(angles, 95))),
            'rotation_residual_max_deg': float(np.degrees(angles.max()))}


def camera_fit(frames, labels, plan, settled_s):
    start = frames[0]['t']
    visits, by_key, pan_segments = [], {}, []
    for event in (e for e in plan['events'] if e['t'] < 72.):
        ts = start + event['t']
        selected = [(f, l) for f, l in zip(frames, labels)
                    if f['t'] >= ts + settled_s - 1e-7 and f['t'] <= ts + 3. + 1e-7]
        if not selected:
            raise ValueError('no settled camera frames')
        servos = {str(a['servo_id']): a['pulse'] for a in event['actions'] if a['kind'] == 'arm'}
        servos['6'] = next(a['pan_pulse'] for a in event['actions'] if a['kind'] == 'look')
        key = ','.join(str(servos[str(i)]) for i in (3, 4, 5, 6))
        records, yaw = [], []
        for f, label in selected:
            if any(f['commanded_servo'][k] != v for k, v in servos.items()):
                raise ValueError('camera visit pose/issued commands mismatch')
            records.append(camera_in_chassis(label))
            yaw.append(math.atan2(label['base_rotation'][1][0], label['base_rotation'][0][0]))
        by_key.setdefault(key, []).extend(records)
        visits.append({'phase': event['phase'], 'start_s': event['t'], 'servo_key': key,
                       'first_frame_id': selected[0][0]['frame_id'], 'last_frame_id': selected[-1][0]['frame_id'],
                       **camera_summary(records)})
        pan_segments.append({'phase': event['phase'], 'pan': servos['6'], 'yaw': yaw})
    # VIS3 same-arm hold segment reference: median of pan=1500; regression
    # through origin on pan-1500. Keep each arm's result as well as pooled.
    pan, xs, ys = {}, [], []
    for phase in dict.fromkeys(v['phase'] for v in pan_segments):
        segments = [s for s in pan_segments if s['phase'] == phase]
        reference = float(np.median([y for s in segments if s['pan'] == 1500 for y in s['yaw']]))
        x = np.array([s['pan'] - 1500. for s in segments if s['pan'] != 1500 for y in s['yaw']])
        y = wrap(np.array([y for s in segments if s['pan'] != 1500 for y in s['yaw']]) - reference)
        k = float(x @ y / (x @ x))
        pan[phase] = {'rad_per_pwm': k, 'n': len(x),
                      'residual_abs_p95_deg': float(np.degrees(np.percentile(abs(y - k * x), 95)))}
        xs.extend(x); ys.extend(y)
    x, y = np.array(xs), np.array(ys)
    k = float(x @ y / (x @ x))
    return {key: camera_summary(records) for key, records in by_key.items()}, {
        'rad_per_pwm': k, 'n': len(x), 'per_pose': pan,
        'residual_abs_p95_deg': float(np.degrees(np.percentile(abs(y - k * x), 95)))}, visits


def verify_streams(folder, rid, protocol):
    commands = rows(folder / f'robots/{rid}/commands.jsonl')
    frames = rows(folder / f'robots/{rid}/frames.jsonl')
    labels = rows(folder / f'eval_only/{rid}/camera_labels.jsonl')
    if len(frames) != 601 or len(labels) != 601 or commands[0]['kind'] != 'initial_servo_command':
        raise ValueError('incomplete recorded stream')
    start = frames[0]['t']
    expected = [{'t': start + e['t'], **a} for e in protocol['events'] for a in e['actions']] if rid == protocol['robot_id'] else []
    if len(commands) != len(expected) + 1:
        raise ValueError('issued command count mismatch')
    for actual, want in zip(commands[1:], expected):
        if abs(actual['t'] - want['t']) > 1e-7 or {k: v for k, v in actual.items() if k != 't'} != {k: v for k, v in want.items() if k != 't'}:
            raise ValueError('issued command differs from fixed protocol')
    servo, ci = dict(commands[0]['pulses']), 1
    for i, (f, label) in enumerate(zip(frames, labels)):
        if (f['frame_id'] != i or label['frame_id'] != i or abs(f['t'] - label['t']) > 1e-7
                or abs(f['t'] - start - .2 * i) > 1e-7 or label['load_state'] != 'unloaded'):
            raise ValueError('frame/teacher timing or state mismatch')
        while ci < len(commands) and commands[ci]['t'] < f['t'] - 1e-7:
            row = commands[ci]
            if row['kind'] == 'arm':
                servo[str(row['servo_id'])] = row['pulse']
            elif row['kind'] == 'look':
                servo['6'] = row['pan_pulse']
            ci += 1
        if servo != f['commanded_servo']:
            raise ValueError('frame servo differs from command replay')
        path = folder / f['path']
        if not path.resolve().is_relative_to(folder.resolve()) or sha(path) != f['sha256']:
            raise ValueError('RGB path/hash mismatch')
        # PNG header only; no image decoding, rendering or model calls.
        data = path.read_bytes()
        if data[:8] != b'\x89PNG\r\n\x1a\n' or int.from_bytes(data[16:20], 'big') != 640 or int.from_bytes(data[20:24], 'big') != 480:
            raise ValueError('unexpected RGB dimensions')
    return commands, frames, labels


def run(raw, output):
    raw, output = Path(raw).resolve(), Path(output).resolve()
    if output.is_relative_to(raw) or raw.is_relative_to(output):
        raise ValueError('output and read-only collection must be disjoint')
    if output.exists():
        raise FileExistsError(output)
    # Hash every collection file, including unused evidence. No extraction/copy.
    files = [('raw', p.relative_to(raw).as_posix(), p) for p in sorted(raw.rglob('*')) if p.is_file()]
    methods = [CONTRACT, PLAN, V2, FINE, INTEGRAL, CAMERA_METHOD, OLD_MOTION, OLD_CAMERA,
               'PHYSICS_HANDOFF.md', 'scripts/fit_final_environment_unloaded.py',
               'sim/final_environment_checks.py', 'scripts/run_final_environment_checks.py']
    files += [('repo', rel, ROOT / rel) for rel in methods]
    snapshot = [(scope, rel, sha(path), path.stat().st_size, path) for scope, rel, path in files]
    plan, result = read(raw / 'plan.json'), read(raw / 'result.json')
    contract, protocol = read(ROOT / CONTRACT), read(ROOT / PLAN)
    if (plan['expected_source_sha'] != SOURCE_SHA or plan['check'] != 'calibration'
            or plan['execution_bundle_id'] != 'zone-final-environment-v87'
            or plan['render_profile'] != 'floor_light_v1' or result['status'] != 'COLLECTED_UNQUALIFIED'
            or result['denominator'] != 3 or result['unattempted'] or not result['source_unchanged']):
        raise ValueError('collection provenance/completion mismatch')
    per_map, camera_maps, all_visits = {}, {}, {}
    old_motion, old_camera = read(ROOT / OLD_MOTION), read(ROOT / OLD_CAMERA)
    for mid, map_hash in contract['maps'].items():
        folder = raw / mid
        bundle, static, applied = (read(folder / p) for p in ('bundle.json', 'inputs/static_map.json', 'eval_only/applied.json'))
        if (digest(bundle) != plan['bundles'][mid] or bundle['calibration_contract'] != contract
                or digest(static) != map_hash or applied['static_map_sha256'] != map_hash
                or bundle['robot_model'] != 'masterpi_v3' or bundle['render_profile'] != 'floor_light_v1'
                or bundle['source_sha256'][PLAN] != sha(ROOT / PLAN)):
            raise ValueError('map/contract/source mismatch')
        stationary = {}
        for rid in ('r1', 'r2', 'r3'):
            c, f, labels = verify_streams(folder, rid, protocol)
            t, p, yaw = trajectory(labels)
            stationary[rid] = {'max_xy_from_start_m': float(np.linalg.norm(p[:, :2] - p[0, :2], axis=1).max()),
                               'max_yaw_from_start_rad': float(abs(yaw - yaw[0]).max()),
                               'net_xy_m': (p[-1, :2] - p[0, :2]).tolist(),
                               'sampled_xy_path_m': float(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1).sum())}
            if rid == 'r1':
                windows = motion_windows(c, labels)
                motion = {name: fit_axis(windows, i) for i, name in enumerate(AXES)}
                camera, pan, visits = camera_fit(f, labels, protocol, CAMERA_SETTLED_S)
                legacy_camera, legacy_pan, _ = camera_fit(f, labels, protocol, old_camera['settled_s'])
        per_map[mid] = {'motion': motion, 'pan': pan, 'robot_motion_audit': stationary,
                       'legacy_settle_diagnostic': {'settled_s': old_camera['settled_s'],
                           'camera_models': legacy_camera, 'pan': legacy_pan}}
        camera_maps[mid], all_visits[mid] = camera, visits
    if any(set(v) != set(camera_maps[next(iter(camera_maps))]) for v in camera_maps.values()):
        raise ValueError('inconsistent visited camera poses')
    camera_models = {}
    for key in camera_maps[next(iter(camera_maps))]:
        records = [(m[key]['origin_m'], m[key]['rotation']) for m in camera_maps.values()]
        camera_models[key] = {**camera_summary(records),
                              'n_maps': len(records),
                              'n_frames': sum(m[key]['n'] for m in camera_maps.values()),
                              'origin_per_map_spread_m': spread([r[0] for r in records])}
    motion_spread, axes = {}, {}
    for axis in AXES:
        values = [m['motion'][axis] for m in per_map.values()]
        axes[axis] = {key: float(np.median([v[key] for v in values])) for key in ('gain', 'tau_s', 'tau_stop_s', 'rms')}
        axes[axis]['stop_drift_abs_mean'] = float(np.mean([abs(w['stop_drift']) for v in values for w in v['windows']]))
        axes[axis]['degenerate'] = any(v['degenerate'] for v in values)
        axes[axis]['gain_lag_identified'] = all(v['gain_lag_identified'] for v in values)
        motion_spread[axis] = {key: spread([v[key] for v in values]) for key in ('gain', 'tau_s', 'tau_stop_s', 'rms')}
        motion_spread[axis]['stop_drift_abs_mean'] = spread([
            np.mean([abs(w['stop_drift']) for w in v['windows']]) for v in values])
    pan_values = [m['pan']['rad_per_pwm'] for m in per_map.values()]
    manifest = 'scope\tpath\tsha256\tbytes\n' + ''.join(f'{s}\t{rel}\t{h}\t{size}\n' for s, rel, h, size, _ in snapshot)
    manifest_hash = hashlib.sha256(manifest.encode()).hexdigest()
    product = {'schema': 'ugrp.final_environment_measured_calibration.v1', 'status': 'PARTIAL_UNLOADED_SIM',
               'contract_sha256': sha(ROOT / CONTRACT), 'maps': contract['maps'], 'robot_model': 'masterpi_v3',
               'render_profile': 'floor_light_v1', 'source_sha': SOURCE_SHA,
               'measurement_manifest_sha256': manifest_hash,
               'qualification': 'offline exploratory fit only; no student factory, no P03 admission',
               'params': {'motion': {'gain': [[(axes[a]['gain'] if axes[a]['gain_lag_identified'] else None)
                                               if i == j else 0. for j in range(3)] for i, a in enumerate(AXES)],
                                     'tau_axis_s': [axes[a]['tau_s'] if axes[a]['gain_lag_identified'] else None for a in AXES],
                                     'tau_stop_axis_s': [None, None, None],
                                     'diagnostic_grid_minima': axes,
                                     'unidentified_reason': 'Forward/lateral gain and lag trade off; extended tau probes improve residuals. Stop lag candidates are shorter than the 0.2 s sampling interval.',
                                     'stop_drift_abs_mean_m_m_rad': [axes[a]['stop_drift_abs_mean'] for a in AXES]},
                          'motion_loaded': None, 'motion_profiles': {'fine': None}},
               'pan_base_yaw': {'unloaded': float(np.median(pan_values)), 'loaded': None},
               'camera_models': {'unloaded': camera_models, 'loaded': None},
               'missing_reasons': {k: MISSING for k in ('params.motion_loaded', 'params.motion_profiles.fine',
                                                       'pan_base_yaw.loaded', 'camera_models.loaded')},
               'uncertainty': {'kind': 'spread across 3 maps, not independent trials or a confidence interval',
                               'motion': motion_spread, 'pan_rad_per_pwm': spread(pan_values)},
               'frame_convention': 'origin at actual 3-D chassis body; rotation maps optical x-right/y-down/z-forward to chassis',
               'camera_sampling': {'settled_s': CAMERA_SETTLED_S, 'legacy_settled_s': old_camera['settled_s'],
                                   'selection': 'exploratory post-hoc terminal window; legacy residuals retained in report', 'visits_per_map': 24,
                                   'unique_poses': len(camera_models), 'note': '8 visits per arm, pan 1500 repeated; 7 unique pans'},
               'limitations': ['Only r1 driven, single seed and amplitude, 0.2 s labels; no held-out validation.',
                               'Four adjacent 0.25 s renewals form 1 s drive; gain and lag are not steady-state measurements.',
                               'Stop tau below 0.2 s is poorly resolved; report boundary fits without forcing acceptance.',
                               'Unidentified forward/lateral gain and lag and unresolved stop lag remain null; diagnostic candidates are not adopted parameters.',
                               'Cross-axis drift retained in report, not claimed zero by the diagonal fit.',
                               'Actual chassis origin is above the ground; future ground-plane consumers must handle the frame explicitly.']}
    report = {'schema': 'ugrp.final_environment_unloaded_fit_report.v1', 'source_sha': SOURCE_SHA,
              'raw_root': str(raw), 'measurement_manifest_sha256': manifest_hash, 'axes': axes,
              'methods': {'motion_window_lstsq': V2, 'tau_grid': FINE, 'exact_integral': INTEGRAL,
                          'camera_optical_convention_and_pan_regression': CAMERA_METHOD,
                          'drive_tau_grid_s': TAU_GRID.tolist(), 'stop_tau_grid_s': STOP_GRID.tolist(),
                          'camera_rotation_summary': 'nearest measured rotation to elementwise median; no FK'},
              'per_map': per_map, 'camera_per_map': camera_maps, 'camera_visits': all_visits,
              'comparison_v2': {'motion': old_motion['params']['motion'], 'pan_base_yaw': old_camera['pan_base_yaw'],
                                'camera_sag': old_camera['sag'], 'note': 'comparison only; no v2 parameters inherited'},
              'input_file_count': len(snapshot), 'raw_file_count': sum(s == 'raw' for s, *_ in snapshot)}
    # Refuse a concurrently changed collection or method before writing anything.
    for _, rel, expected, size, path in snapshot:
        if path.stat().st_size != size or sha(path) != expected:
            raise ValueError(f'input changed during fitting: {rel}')
    output.mkdir(parents=True)
    (output / 'input_manifest.tsv').write_text(manifest)
    write(output / 'calibration_partial.json', product)
    write(output / 'fit_report.json', report)
    print(json.dumps({'output': str(output), 'status': product['status'], 'axes': axes,
                      'pan_rad_per_pwm': product['pan_base_yaw']['unloaded'], 'input_files': len(snapshot)}, indent=2))
    return product, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new output directory, disjoint from read-only raw')
    args = parser.parse_args()
    run(args.raw, args.output)


if __name__ == '__main__':
    main()
