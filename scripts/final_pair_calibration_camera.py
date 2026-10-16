"""r1 extrinsics and v6-family RGB edge/yaw definitions on v88 saved data."""
from __future__ import annotations

from collections import defaultdict
import io

import numpy as np
from PIL import Image

from harness.own_beam_edge import BeamEdgeTracker
from harness.vision_pose_source_final import camera_key
from harness.zone_final_pair_camera import floor_camera, rigid
from harness.zone_final_pair_vision import required_camera_poses
from scripts.fit_final_environment_unloaded import camera_summary, wrap
from scripts.final_pair_calibration_motion import increments


def fit_cameras(collections, gate):
    models, pans, evidence, missing = {}, {}, {}, {}
    wanted = required_camera_poses()
    for state in ('unloaded', 'loaded'):
        records, pan_groups = defaultdict(list), defaultdict(list)
        for data, valid in collections.get(state, []):
            for rid, robot in data['robots'].items():
                group_id, previous_arm, moving_before = 0, None, True
                for f, label in zip(robot['frames'], robot['labels']):
                    i = round((f['sim_time']-robot['t'][0])/.05)
                    arm = tuple(f['commanded_servo'][str(j)] for j in (3, 4, 5))
                    # No movement/pan-regression contamination from drive drift.
                    lo = max(0, i-round(gate['settled_s']/.05))
                    still_drive = not np.any(robot['u'][lo:i])
                    if arm != previous_arm or not still_drive or moving_before:
                        group_id += 1
                    previous_arm, moving_before = arm, not still_drive
                    if not still_drive or f['_still_s'] < gate['settled_s']-1e-7 or not np.all(valid[lo:i+1]):
                        continue
                    # These already are actual-chassis labels. r1's optical
                    # conversion was performed by measurement_label at capture.
                    floor_camera(label)
                    key = camera_key({int(k): v for k, v in f['commanded_servo'].items()})
                    records[key].append(label)
                    rb = np.asarray(label['base_rotation'])
                    yaw = float(np.arctan2(rb[1, 0], rb[0, 0]))
                    group = (str(data['folder']), rid, group_id, arm)
                    pan_groups[group].append((int(f['commanded_servo']['6']), yaw))
        models[state], evidence[state] = {}, {}
        for key, labels in sorted(records.items()):
            origin = camera_summary([rigid(label) for label in labels])
            floor = camera_summary([rigid(label['chassis_to_floor']) for label in labels])
            accepted = (len(labels) >= gate['minimum_frames_per_pose'] and all(
                rec['origin_residual_max_m'] <= gate['origin_max_residual_m'] and
                rec['rotation_residual_max_deg'] <= gate['rotation_max_residual_deg'] for rec in (origin, floor)))
            evidence[state][key] = {'accepted': accepted, 'optical': origin, 'floor': floor}
            if accepted:
                record = {**origin, 'frame': 'optical_to_actual_chassis', 'chassis_to_floor': floor}
                floor_camera(record)
                models[state][key] = record
        for servo in wanted[state]:
            key = camera_key(servo)
            if key not in models[state]:
                missing[f'camera_models.{state}.{key}'] = ('settled transform rejected by residual/count gate'
                    if key in records else 'no measured stationary settled pose'+(' with lifted bilateral grip' if state == 'loaded' else ''))
        xs, ys = [], []
        for group in pan_groups.values():
            reference = [yaw for pan, yaw in group if pan == 1500]
            if not reference:
                continue
            # Circular relative yaw, including the opposite-facing r2.
            angle = float(np.median(np.unwrap(reference)))
            for pan, yaw in group:
                if pan != 1500:
                    xs.append(pan-1500)
                    ys.append(float(wrap(yaw-angle)))
        x, y = np.asarray(xs), np.asarray(ys)
        if min(np.sum(x > 0), np.sum(x < 0)) < 5:
            missing[f'pan_base_yaw.{state}'] = 'insufficient both-sign stationary pan samples with same-arm center reference'
            continue
        k = float(x @ y/(x @ x))
        residual = float(np.degrees(np.percentile(np.abs(y-k*x), 95)))
        evidence[state]['pan'] = {'accepted': residual <= gate['pan_residual_p95_deg_max'],
                                 'n': len(x), 'rad_per_pwm': k, 'residual_p95_deg': residual}
        if residual <= gate['pan_residual_p95_deg_max']:
            pans[state] = k
        else:
            missing[f'pan_base_yaw.{state}'] = 'pan yaw residual exceeds frozen gate'
    return models, pans, evidence, missing


def mirrored(u):
    """fit_carry_pair_yaw.mirrored: flip translations only for zero turn."""
    out = u.copy()
    mask = (out[:, 2] == 0) & np.any(out[:, :2] != 0, axis=1)
    out[mask, :2] *= -1
    return out


def pair_rows(data, profile, valid, inputs, gate):
    rows, unavailable = [], []
    trace = data['beam_trace']
    beam_rotation = np.asarray([r['beam_rotation'] for r in trace]).reshape(-1, 3, 3)
    beam_yaw = np.unwrap(np.arctan2(beam_rotation[:, 1, 0], beam_rotation[:, 0, 0]))
    for rid, robot in data['robots'].items():
        own = np.r_[0., np.cumsum(increments(robot, profile)[:, 2])]
        partner = np.r_[0., np.cumsum(increments({**robot, 'u': mirrored(robot['u'])}, profile)[:, 2])]
        relative = wrap(robot['pose'][:, 2]-beam_yaw)
        relative = np.unwrap(np.where(np.abs(relative) < np.pi/2, relative, wrap(relative-np.pi)))
        for axis, splits in data['segments'].items():
            for split, spans in splits.items():
                for index, (a, z) in enumerate(spans):
                    if (z-a)*.05 < gate['minimum_window_s'] or not np.all(valid[a:z+1]):
                        unavailable.append({'robot': rid, 'axis': axis, 'split': split, 'block': index, 'reason': 'not continuously lifted for full block'})
                        continue
                    tracker = BeamEdgeTracker(1.)
                    t0, t1 = robot['t'][[a, z]]
                    for frame in robot['frames']:
                        if t0 <= frame['sim_time'] <= t1:
                            image = Image.open(io.BytesIO(inputs.read(data['folder']/frame['path']))).convert('RGB')
                            servo = {int(k): int(v) for k, v in frame['commanded_servo'].items()}
                            tracker.observe(frame['sim_time'], np.asarray(image), servo, servo.get(1, 2000) < 1700)
                    if (tracker.ref_t is None or tracker.eff_t is None or tracker.eff_t <= tracker.ref_t
                            or not tracker.available(t1)):
                        unavailable.append({'robot': rid, 'axis': axis, 'split': split, 'block': index, 'reason': 'edge not observable/available at endpoint', 'stats': tracker.stats})
                        continue
                    rel = float(np.interp(tracker.eff_t, robot['t'], relative)-np.interp(tracker.ref_t, robot['t'], relative))
                    magnitude = float(np.max(np.abs(robot['u'][a:z])))
                    rows.append({'robot': rid, 'cell': f'{axis}/{magnitude}', 'split': split, 'T': t1-t0,
                        'g': float(wrap(robot['pose'][z, 2]-robot['pose'][a, 2])),
                        'ms': float(own[z]-own[a]), 'mp': float(partner[z]-partner[a]),
                        'd_slope_total': tracker.total_rad, 'd_rel_gt': rel, 'stats': dict(tracker.stats)})
    return rows, unavailable


def balanced(rows, estimate):
    """Exact v6e cell-balanced RMS residual rate (fit_carry_pair_yaw)."""
    cells = defaultdict(list)
    for row in rows:
        cells[row['cell']].append((row['g']-estimate(row))/row['T'])
    if not cells:
        raise ValueError('no pair model windows')
    return float(np.sqrt(np.mean([np.mean(np.square(v)) for v in cells.values()])))


def fit_pair(rows, gate):
    training = [r for r in rows if r['split'] == 'steps']
    validation = [r for r in rows if r['split'] == 'prbs']
    if len(training) < gate['minimum_fit_windows'] or not validation:
        raise ValueError('pair_model: insufficient lifted edge step/PRBS windows')
    slope = np.array([r['d_slope_total'] for r in training])
    yaw = np.array([r['d_rel_gt'] for r in training])
    if float(yaw @ yaw) <= gate['relative_yaw_energy_min_rad2']:
        raise ValueError('pair_model.slope_to_yaw_ratio: relative yaw is unexcited')
    ratio = float(slope @ yaw/(yaw @ yaw))
    if not 0 < ratio < 3:
        raise ValueError('pair_model.slope_to_yaw_ratio outside tracker bounds')
    estimates = {'': lambda r: r['ms'], 'pm': lambda r: (r['ms']+r['mp'])/2,
        'edge': lambda r: r['ms']+r['d_slope_total']/ratio,
        'pm+edge': lambda r: (r['ms']+r['mp'])/2+r['d_slope_total']/ratio}
    biases = {key: balanced(training, estimate) for key, estimate in estimates.items()}
    validation_rate = {key: [abs((r['g']-estimate(r))/r['T']) for r in validation] for key, estimate in estimates.items()}
    ratio_error = float(np.percentile([abs(r['d_slope_total']/ratio-r['d_rel_gt']) for r in validation], 95))
    accepted = ratio_error <= .02 and all(max(validation_rate[k]) <= 2*biases[k]+1e-12 for k in estimates)
    return {'slope_to_yaw_ratio': ratio, 'b_rad_s': biases}, {
        'accepted': accepted, 'fit_windows': len(training), 'validation_windows': len(validation),
        'ratio_validation_p95_rad': ratio_error, 'validation_rate_rad_s': validation_rate,
        'rows': rows, 'method': 'v6e through-origin slope and cell-balanced residual-rate RMS; steps fit, PRBS validate'}
