"""Fixed saved own RGB + actual issued commands; NOT a simulation, no model call.

Compares, on the SAME saved-image windows as scripts/replay_e2e_stall.py:
  off            issued-command pulse odometry
  pulse_gate     rgb_pulse_gate_v1 (binary stationarity gate, zero increment)
  vo_fused       rgb_vo_v1 (ground VO + command Kalman fusion, chi-square replace)
  vo_replace     diagnostic column: every measured VO increment replaces command
  vo_fused_p95   diagnostic sensitivity: chi-square p=.95 (7.815) gate; chosen
                 after seeing this data, so NOT an adoptable result
All estimators consume only own RGB, own issued commands/servo and fixed camera
calibration. Ground truth is read only AFTER every prediction exists, for scoring.
RBPF maps, navigation and recovery are not replayed (command estimator only).
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import cv2
import numpy as np
from harness.e2e_stall_odometry import Detector, PULSE_GATE
from harness.e2e_rgb_vo import VOFusion, between
from harness.self_pulse_rotation import RotationPulseOdometry
from harness.active_camera import SEARCH

ESTIMATORS = ('off', 'pulse_gate', 'vo_fused', 'vo_replace', 'vo_fused_p95')
UNCHANGED_M = .001
UNCHANGED_RAD = math.radians(.1)


def rows(path):
    path = Path(path)
    data = path.read_bytes() if path.exists() else subprocess.check_output(['zstd', '-dc', str(path)+'.zst'])
    return [json.loads(x) for x in data.splitlines() if x]


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def predict(raw, images, rid):
    frames = rows(raw/f'robots/{rid}/frames.jsonl');own = rows(raw/f'robots/{rid}/ownmap.jsonl')
    origin = frames[0]['sim_time']
    every = [{**r, 't': round(r['t']-origin, 8)} for r in rows(raw/f'robots/{rid}/commands.jsonl') if r['t'] >= origin-1e-6]
    commands = [r for r in every if r['kind'] in ('mecanum', 'drive', 'hold', 'stop')]
    servo_changes = [r for r in every if r['kind'] in ('arm', 'look', 'initial_servo_command')]
    drivers = {k: RotationPulseOdometry() for k in ESTIMATORS}
    for d in drivers.values():
        d.command(dict(t=0., kind='initial_servo_command', pulses=SEARCH))
    detector = Detector(drivers['off'], PULSE_GATE)
    fusion = {k: VOFusion(drivers['off'], mode, chi2_gate=gate95) for k, mode, gate95 in
              (('vo_fused', 'fused', None), ('vo_replace', 'replace', None), ('vo_fused_p95', 'fused', 7.815))}
    gate = False
    drivers['pulse_gate'].motion_filter = lambda delta, variance: (np.zeros(3) if gate else delta, variance)
    active = {k: False for k in fusion}
    for key in fusion:
        drivers[key].motion_filter = (lambda k: lambda delta, variance:
                                      fusion[k].motion_filter(delta, variance) if active[k] else (delta, variance))(key)
    cursor = 0;servo_cursor = 0;out = [];max_match = 0.;flows = [];vo_rows = {k: [] for k in fusion}

    def issue(cmd):
        detector.command(cmd)
        for f in fusion.values():
            f.command(cmd)
        for d in drivers.values():
            d.command(cmd)
    for frame, prior in zip(frames, own):
        t = round(frame['sim_time']-origin, 8)
        while cursor < len(commands) and commands[cursor]['t'] < t-1e-8:
            issue(commands[cursor]);cursor += 1
        while servo_cursor < len(servo_changes) and servo_changes[servo_cursor]['t'] <= t+1e-8:
            for f in fusion.values():  # own issued arm/look commands (camera settle only)
                f.servo_since = max(f.servo_since, servo_changes[servo_cursor]['t'])
            servo_cursor += 1
        path = images/frame['path'];has = path.exists();gate = False;flow = None;vo = {}
        if has:
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != frame['sha256']:
                raise ValueError('IMAGE_HASH_MISMATCH '+str(path))
            rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
            servo = {int(k): int(v) for k, v in frame['commanded_servo'].items()}
            flow = detector.observe(t=t, frame_id=frame['frame_id'], rgb=rgb, servo=SEARCH, sha256=frame['sha256'])
            gate = detector.suppressed;flows.append(flow)
            for k, f in fusion.items():
                vo[k] = f.observe(t=t, frame_id=frame['frame_id'], rgb=rgb, servo=servo, sha256=frame['sha256'])
                vo_rows[k].append(vo[k])
        else:
            # Same as replay_e2e_stall: missing image resets the gate history.
            detector.frames.clear();detector.stationary_since = None;detector.streak = 0
            detector.nominal.advance(t);detector.last_nominal = np.asarray(detector.nominal.pose)
            for f in fusion.values():
                f.nominal.advance(t);f.steps = []  # no pair across a missing image (gap check also applies)
        for k, d in drivers.items():
            if k in fusion:
                active[k] = True
                try:
                    d.advance(t)
                finally:
                    active[k] = False;fusion[k].finish_interval()
            else:
                d.advance(t)
        gate = False
        max_match = max(max_match, float(np.max(abs(np.asarray(drivers['off'].pose)-prior['pose_continuity']['control_pose']))))
        out.append(dict(t=t, absolute_t=frame['sim_time'], has_image=has, frame_id=frame['frame_id'],
                        sha256=frame['sha256'] if has else None,
                        **{k: list(d.pose) for k, d in drivers.items()},
                        flow_status=(flow or {}).get('status'), gated=bool((flow or {}).get('stationary')),
                        vo={k: {x: v.get(x) for x in ('status', 'fusion', 'nis', 'inliers', 'cells', 'delta', 'fused_delta',
                                                      'command_delta', 'fusion_applied')} for k, v in vo.items()}))
        while cursor < len(commands) and commands[cursor]['t'] <= t+1e-8:
            issue(commands[cursor]);cursor += 1
    return out, origin, dict(max_off_reproduction_error=max_match, pulse_flow_counts=dict(Counter(f['status'] for f in flows)),
                             vo_status_counts={k: dict(Counter(r['status'] for r in v)) for k, v in vo_rows.items()},
                             vo_counts={k: dict(f.counts) for k, f in fusion.items()})


def score(raw, rid, predictions, origin):
    """Evaluation only, after all predictions: own-start truth frame."""
    truth = rows(raw/f'eval_only/{rid}/trajectory.jsonl')
    by_t = {round(r['t']-origin, 8): r for r in truth};ts = sorted(by_t)
    first = by_t[0.];yaw0 = first['robot_yaw_rad'];c, s = math.cos(yaw0), math.sin(yaw0)

    def own(r):
        dx, dy = np.asarray(r['robot_xyz_m'][:2])-first['robot_xyz_m'][:2]
        return np.array([c*dx+s*dy, -s*dx+c*dy, wrap(r['robot_yaw_rad']-yaw0)])
    for p in predictions:
        p['truth'] = own(by_t[p['t']]).tolist()
    intervals = [];windows = [];current = []
    for a, b in zip(predictions, predictions[1:]):
        if not (a['has_image'] and b['has_image']):
            continue
        issued = between(a['off'], b['off'])
        seg = [x for x in ts if a['t']-1e-9 <= x <= b['t']+1e-9]
        path = sum(math.dist(by_t[x]['robot_xyz_m'][:2], by_t[y]['robot_xyz_m'][:2]) for x, y in zip(seg, seg[1:]))
        truth_inc = between(a['truth'], b['truth'])
        issued_xy = math.hypot(issued[0], issued[1])
        if abs(issued[2]) >= .02:
            kind = 'rotation'
        elif issued_xy >= .005:
            kind = 'stalled' if path < .2*issued_xy else ('moving' if path >= .8*issued_xy else 'partial_slip')
        else:
            kind = 'no_command_motion'
        item = dict(t0=a['t'], t1=b['t'], kind=kind, issued=issued.tolist(), truth_increment=truth_inc.tolist(), truth_path_m=path)
        for k in ESTIMATORS:
            inc = between(a[k], b[k])
            item[k+'_xy_err_m'] = math.hypot(inc[0]-truth_inc[0], inc[1]-truth_inc[1])
            item[k+'_yaw_err_rad'] = abs(wrap(inc[2]-truth_inc[2]))
        intervals.append(item)
    for r in predictions+[dict(has_image=False)]:
        if r['has_image']:
            current.append(r);continue
        if not current:
            continue
        s0, s1 = current[0], current[-1]
        w = dict(start_s=s0['t'], end_s=s1['t'], frames=len(current), gated=sum(x['gated'] for x in current))
        tr = np.asarray(s1['truth'])-s0['truth']
        for k in ESTIMATORS:
            est = np.asarray(s1[k])-s0[k]
            # Same xy definition as replay_e2e_stall (own-frame difference) + heading.
            w[k+'_xy_err_m'] = float(math.hypot(est[0]-tr[0], est[1]-tr[1]))
            w[k+'_yaw_err_rad'] = abs(wrap(est[2]-tr[2]))
            # Body frame of each window start: excludes heading error accumulated before the window.
            eb, tb = between(s0[k], s1[k]), between(s0['truth'], s1['truth'])
            w[k+'_body_xy_err_m'] = float(math.hypot(eb[0]-tb[0], eb[1]-tb[1]))
        kinds = Counter(i['kind'] for i in intervals if s0['t']-1e-9 <= i['t0'] and i['t1'] <= s1['t']+1e-9)
        w['interval_kinds'] = dict(kinds)
        w['label'] = ('stalled' if kinds['stalled'] else 'partial_slip' if kinds['partial_slip'] else
                      'rotation' if kinds['rotation'] else 'moving' if kinds['moving'] else 'no_command_motion')
        windows.append(w);current = []
    glob = {k: dict(max_m=max(math.dist(p[k][:2], p['truth'][:2]) for p in predictions),
                    final_m=math.dist(predictions[-1][k][:2], predictions[-1]['truth'][:2]),
                    final_yaw_err_rad=abs(wrap(predictions[-1][k][2]-predictions[-1]['truth'][2]))) for k in ESTIMATORS}
    return intervals, windows, glob


def compare(items, key, base, unchanged):
    out = dict(improved=0, worse=0, unchanged=0, max_worsening=0., worse_items=[])
    for x in items:
        d = x[key]-x[base]
        if abs(d) <= unchanged:
            out['unchanged'] += 1
        elif d < 0:
            out['improved'] += 1
        else:
            out['worse'] += 1;out['max_worsening'] = max(out['max_worsening'], d)
            out['worse_items'].append({k: x[k] for k in x if k in ('run', 'robot', 'start_s', 'end_s', 't0', 't1', 'label', 'kind')} | {'delta': d})
    return out


def aggregate(intervals, windows):
    by_kind = {}
    for kind in sorted({i['kind'] for i in intervals}):
        part = [i for i in intervals if i['kind'] == kind]
        by_kind[kind] = dict(n=len(part), N=len(intervals),
            **{k: dict(sum_xy_err_m=sum(i[k+'_xy_err_m'] for i in part),
                       median_xy_err_mm=1000*statistics.median(i[k+'_xy_err_m'] for i in part),
                       sum_yaw_err_deg=math.degrees(sum(i[k+'_yaw_err_rad'] for i in part)),
                       median_yaw_err_deg=math.degrees(statistics.median(i[k+'_yaw_err_rad'] for i in part)))
               for k in ESTIMATORS},
            **{f'{k}_vs_off_{axis}': compare(part, f'{k}_{axis}_err_{unit}', f'off_{axis}_err_{unit}', tol) | {'worse_items': None}
               for k in ESTIMATORS[1:] for axis, unit, tol in (('xy', 'm', UNCHANGED_M), ('yaw', 'rad', UNCHANGED_RAD))})
    win = dict(N=len(windows), by_label=dict(Counter(w['label'] for w in windows)),
        mean_xy_err_m={k: statistics.mean(w[k+'_xy_err_m'] for w in windows) for k in ESTIMATORS},
        mean_yaw_err_deg={k: math.degrees(statistics.mean(w[k+'_yaw_err_rad'] for w in windows)) for k in ESTIMATORS},
        mean_body_xy_err_m={k: statistics.mean(w[k+'_body_xy_err_m'] for w in windows) for k in ESTIMATORS})
    for k in ESTIMATORS[1:]:
        win[k+'_vs_off_xy'] = compare(windows, k+'_xy_err_m', 'off_xy_err_m', UNCHANGED_M)
        win[k+'_vs_off_yaw'] = compare(windows, k+'_yaw_err_rad', 'off_yaw_err_rad', UNCHANGED_RAD)
        win[k+'_vs_off_body_xy'] = compare(windows, k+'_body_xy_err_m', 'off_body_xy_err_m', UNCHANGED_M)
    win['vo_fused_vs_pulse_gate_xy'] = compare(windows, 'vo_fused_xy_err_m', 'pulse_gate_xy_err_m', UNCHANGED_M)
    win['by_label_detail'] = {}
    for label in sorted({w['label'] for w in windows}):
        part = [w for w in windows if w['label'] == label]
        win['by_label_detail'][label] = dict(n=len(part),
            mean_xy_err_m={k: statistics.mean(w[k+'_xy_err_m'] for w in part) for k in ESTIMATORS},
            mean_yaw_err_deg={k: math.degrees(statistics.mean(w[k+'_yaw_err_rad'] for w in part)) for k in ESTIMATORS},
            mean_body_xy_err_m={k: statistics.mean(w[k+'_body_xy_err_m'] for w in part) for k in ESTIMATORS})
    return dict(intervals_by_kind=by_kind, windows=win)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', action='append', required=True, help='name=RAW_DIR:IMAGE_ROOT')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args();cv2.setNumThreads(1)
    all_intervals = [];all_windows = [];per_run = {};detail = []
    for spec in a.run:
        name, paths = spec.split('=', 1);raw, images = (Path(x) for x in paths.split(':'))
        for rid in ('r1', 'r2'):
            preds, origin, meta = predict(raw, images, rid)
            intervals, windows, glob = score(raw, rid, preds, origin)
            for x in intervals+windows:
                x.update(run=name, robot=rid)
            all_intervals += intervals;all_windows += windows
            per_run[f'{name}:{rid}'] = dict(**meta, saved_images=sum(x['has_image'] for x in preds), frames=len(preds),
                                            windows=windows, global_error_all_frames=glob)
            detail += [dict(run=name, robot=rid, **x) for x in preds if x['has_image']]
    result = dict(schema='ugrp.e2e_vo_replay.v1', simulation=False, model_calls=0,
                  scope='fixed saved own RGB + actual issued commands; command estimator only; not held-out',
                  estimators=list(ESTIMATORS), aggregate=aggregate(all_intervals, all_windows), per_run=per_run)
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output/'summary.json').write_text(json.dumps(result, indent=1)+'\n')
    for name, obj in (('intervals.json.zst', all_intervals), ('predictions.json.zst', detail)):
        data = (json.dumps(obj)+'\n').encode();path = a.output/name
        subprocess.run(['zstd', '-q', '-19', '-o', str(path)], input=data, check=True)
        assert subprocess.check_output(['zstd', '-dc', str(path)]) == data
    print(json.dumps(result['aggregate'], indent=1))


if __name__ == '__main__':
    main()
