"""Saved RGB and issued-command replay. No physics, renderer, provider or GT input.

Scoring reads the previously archived evaluation-only truth increments AFTER
every prediction has been produced. Missing map registration is measured as
availability failure, not advertised as a wall-mask/odometry improvement.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess

import cv2
import numpy as np

from harness.active_camera import SEARCH
from harness.e2e_rgb_vo import VOFusion, between, image_mask
from harness.e2e_vo_floor_mask import wall_boxes, registered_map_pose, geometric_mask, rays, MAP_OPTIONS
from harness.self_pulse_rotation import RotationPulseOdometry
from scripts.audit_e2e_usstall import CASES
from scripts.replay_e2e_vo import rows, wrap

CONFIGS = {
    'off': dict(vo_floor_mask='off'),
    'homography_v1': dict(vo_floor_mask='homography_v1'),
    'map_v1': dict(vo_floor_mask='map_v1'),
    'geom_v1': dict(vo_floor_mask='geom_v1'),
    'homography_turn_off': dict(vo_floor_mask='homography_v1', rotation_policy='no_ransac_v1'),
    'homography_turn_command': dict(vo_floor_mask='homography_v1', rotation_policy='command_v1'),
}
OPTIONS = tuple(CONFIGS)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def predict(raw_root, image_root, ledger_root):
    output = []; hashes = {}; cases = []
    for run, rid in CASES:
        raw = raw_root/run/'raw'; base = raw/'robots'/rid
        frames = rows(base/'frames.jsonl'); origin = frames[0]['sim_time']
        ledger_path = ledger_root/run/'raw/robots'/rid/'ownmap.jsonl.zst'
        ledger = rows(ledger_path)
        own_rows = {r['frame_id']: r for r in ledger}
        if len(own_rows) != len(ledger):
            raise ValueError('DUPLICATE_CONTROLLER_FRAME')
        hashes[str(ledger_path)] = sha(ledger_path)
        map_path = raw/'inputs/static_map.json'
        static_map = json.loads(map_path.read_text()); map_sha = sha(map_path)
        hashes[str(map_path)] = map_sha; boxes = wall_boxes(static_map)
        registration = Counter(); pose_frames = []; closure = []; clock_offsets = []
        camera_origins = []; wall_support = []; sizes = Counter()
        commands = [{**r, 't': round(r['t']-origin, 8)} for r in rows(base/'commands.jsonl') if r['t'] >= origin-1e-6]
        for name in ('frames.jsonl.zst', 'commands.jsonl'):
            path = base/name; hashes[str(path)] = sha(path)
        if list(raw.glob('robots/*/inputs/range.jsonl*')):
            raise ValueError('NEW_RANGE_EVIDENCE_REQUIRES_REPLAY_ADAPTER')
        drivers = {}; fusions = {}; active = {}
        for option in OPTIONS:
            d = RotationPulseOdometry(); d.command(dict(t=0., kind='initial_servo_command', pulses=SEARCH))
            drivers[option] = d
            fusions[option] = VOFusion(d, fallback='ultrasonic', static_walls=boxes, **CONFIGS[option])
            active[option] = False
            d.motion_filter = (lambda k: lambda delta, q: fusions[k].motion_filter(delta, q) if active[k] else (delta, q))(option)
        cursor = 0; count = 0; statuses = {k: Counter() for k in OPTIONS}; last = None
        for frame in frames:
            t = round(frame['sim_time']-origin, 8)
            while cursor < len(commands) and commands[cursor]['t'] < t-1e-8:
                cmd = commands[cursor]; cursor += 1
                for k in OPTIONS:
                    fusions[k].command(cmd); drivers[k].command(cmd)
            path = image_root/run/'raw'/frame['path']; measurements = {}
            if path.exists():
                data = path.read_bytes(); digest = hashlib.sha256(data).hexdigest()
                if digest != frame['sha256']:
                    raise ValueError('IMAGE_HASH_MISMATCH')
                hashes[str(path)] = digest
                rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
                servo = {int(k): v for k, v in frame['commanded_servo'].items()}
                own_row = own_rows.get(frame['frame_id'])
                pose, reason = registered_map_pose(frame, own_row, robot_id=rid, origin=origin,
                    static_map_sha256=map_sha, map_frame=static_map['frame'])
                registration[reason] += 1
                if own_row is not None:
                    pose_frames.append(frame['frame_id']); clock_offsets.append(frame['sim_time']-own_row['t'])
                    from harness.e2e_rgb_vo import compose
                    pc = own_row['pose_continuity']
                    residual = between(compose(pc['map_to_odom'], pc['odom_pose']), pc['map_pose'])
                    closure.append(float(np.max(np.abs(residual))))
                camera_origins.append(rays(tuple(sorted(servo.items())))[0].tolist())
                sizes[str(rgb.shape)] += 1
                gm = geometric_mask(servo, boxes, pose)
                if gm is not None:
                    wall_support.append(int(np.count_nonzero(image_mask(rgb, servo) & gm)))
                for k in OPTIONS:
                    r = fusions[k].observe(t=t, frame_id=frame['frame_id'], rgb=rgb, servo=servo, sha256=digest,
                                          estimated_map_pose=pose)
                    measurements[k] = r; statuses[k][r['status']] += 1
                count += 1; last = (rgb, servo, frame['frame_id'])
            else:
                for f in fusions.values():
                    f.skip(t)
            for k, d in drivers.items():
                active[k] = True
                try:
                    d.advance(t)
                finally:
                    active[k] = False; fusions[k].finish_interval()
            if measurements:
                output.append(dict(run=run, robot=rid, t=t, frame_id=frame['frame_id'], sha256=digest,
                    poses={k: list(d.pose) for k, d in drivers.items()}, measurements=measurements,
                    registration=dict(status=reason, estimated_map_pose=pose,
                        own_pose=None if own_row is None else own_row['pose_own_m'])))
        rgb, servo, frame_id = last
        support = image_mask(rgb, servo) > 0
        roi = np.zeros((480, 640), bool); roi[110:170, 200:540] = True
        cases.append(dict(run=run, robot=rid, frames=count, statuses={k: dict(v) for k, v in statuses.items()},
            registration=dict(counts=dict(registration), controller_rows=len(ledger), matched_frames=pose_frames,
                last_ledger_frame=max(own_rows), first_ledger_pose=ledger[0]['pose_own_m'],
                clock_offset_s=[min(clock_offsets), max(clock_offsets)],
                own_map_to_odom_closure_max=max(closure), static_map_frame=static_map['frame'],
                static_map_sha256=map_sha, static_wall_boxes=len(boxes),
                map_extent_m=[static_map['bounds_m'][1]-static_map['bounds_m'][0], static_map['bounds_m'][3]-static_map['bounds_m'][2]],
                camera_extrinsics_n=len(camera_origins), camera_origin_m=camera_origins[0], image_shapes=dict(sizes),
                projected_frames=len(wall_support)),
            wall_roi=dict(frame_id=frame_id, xyxy=[200, 110, 540, 170],
                annotation='PR450 manually inspected wall ROI; partial label, not all wall pixels',
                roi_pixels=int(roi.sum()), admitted=int((support & roi).sum()), mask_pixels=int(support.sum()),
                admitted_roi_fraction=float((support & roi).sum()/roi.sum()),
                lower_bound_contamination=float((support & roi).sum()/support.sum()),
                homography_v1='same pixel mask as off; only point matches filtered',
                geom_v1=None if gm is None else int(np.count_nonzero(support & roi & (gm > 0))),
                geom_status=reason)))
    return output, cases, hashes


def score(predictions, evaluation_root):
    # This function is the ONLY evaluation reader. No truth flows into predict().
    old = json.loads(subprocess.check_output(['zstd', '-dc', str(evaluation_root/'predictions.json.zst')]))
    intervals = json.loads(subprocess.check_output(['zstd', '-dc', str(evaluation_root/'intervals.json.zst')]))
    previous = {(r['run']+'-r2', r['robot'], r['t']): r for r in old}
    truth = {(r['run']+'-r2', r['robot'], r['t0'], r['t1']): r for r in intervals}
    scored = []; windows = []; reproduction = []
    for run, rid in CASES:
        part = [p for p in predictions if (p['run'], p['robot']) == (run, rid)]
        for p in part:
            before = previous[(run, rid, p['t'])]
            if before['sha256'] != p['sha256']:
                raise ValueError('EVALUATION_IMAGE_MISMATCH')
            reproduction.append(float(np.max(np.abs(np.array(p['poses']['off'])-before['vo2']))))
        for a, b in zip(part, part[1:]):
            label = truth[(run, rid, a['t'], b['t'])]
            expected = label['truth_increment']
            metrics = {}
            for k in OPTIONS:
                inc = between(a['poses'][k], b['poses'][k])
                available = (k not in MAP_OPTIONS or all(p['registration']['status'] == 'registered' for p in (a, b)))
                metrics[k] = dict(xy_mm=1000*math.dist(inc[:2], expected[:2]),
                    yaw_deg=math.degrees(abs(wrap(inc[2]-expected[2]))),
                    tracks=b['measurements'][k].get('tracks', 0),
                    inliers=b['measurements'][k].get('inliers', 0),
                    measured=b['measurements'][k]['status'] == 'measured', available=available)
                if not available:
                    metrics[k]['unregistered_fallback_only'] = {f: metrics[k][f] for f in ('xy_mm', 'yaw_deg')}
                    metrics[k].update(xy_mm=None, yaw_deg=None)
            scored.append(dict(run=run, robot=rid, t0=a['t'], t1=b['t'], kind=label['kind'], metrics=metrics))
        a, b = part[0], part[-1]
        ta = previous[(run, rid, a['t'])]['truth']; tb = previous[(run, rid, b['t'])]['truth']
        delta = np.asarray(tb)-ta
        windows.append(dict(run=run, robot=rid, metrics={k: (None if k in MAP_OPTIONS and
            any(p['registration']['status'] != 'registered' for p in part) else dict(
            xy_mm=1000*float(np.linalg.norm((np.asarray(b['poses'][k])-a['poses'][k]-delta)[:2])),
            yaw_deg=math.degrees(abs(wrap(b['poses'][k][2]-a['poses'][k][2]-delta[2]))))) for k in OPTIONS}))
    kinds = {}
    for kind in ('moving', 'stalled', 'rotation', 'partial_slip', 'no_command_motion'):
        part = [r for r in scored if r['kind'] == kind]
        metrics = {}
        for k in OPTIONS:
            valid = [x for x in part if x['metrics'][k]['available']]
            metrics[k] = dict(n=len(valid), N=len(part),
                sum_xy_mm=sum(x['metrics'][k]['xy_mm'] for x in valid) if valid else None,
                sum_yaw_deg=sum(x['metrics'][k]['yaw_deg'] for x in valid) if valid else None,
                measured=sum(x['metrics'][k]['measured'] for x in valid),
                tracks=sum(x['metrics'][k]['tracks'] for x in valid),
                xy_improved=sum(x['metrics'][k]['xy_mm'] < x['metrics']['off']['xy_mm']-1. for x in valid),
                xy_worse=sum(x['metrics'][k]['xy_mm'] > x['metrics']['off']['xy_mm']+1. for x in valid))
        kinds[kind] = dict(n=len(part), N=len(scored), metrics=metrics)
    return dict(intervals_by_kind=kinds, windows=windows, N_windows=len(windows),
        max_baseline_reproduction_abs=max(reproduction),
        geom_interpretation='Null for missing map registration; fallback-only numbers stay in the separate per-pair diagnostic'), scored


def main():
    p = argparse.ArgumentParser(); p.add_argument('--raw-root', type=Path, required=True)
    p.add_argument('--image-root', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--ledger-root', type=Path, required=True)
    p.add_argument('--evaluation-root', type=Path, default=Path('experiments/2026-10-12-e2e-vo/replay-e2e14-crash'))
    a = p.parse_args(); cv2.setNumThreads(1)
    predictions, cases, hashes = predict(a.raw_root, a.image_root, a.ledger_root)
    a.output.mkdir(parents=True, exist_ok=False)
    def compressed(name, obj):
        data = (json.dumps(obj, allow_nan=False)+'\n').encode()
        path = a.output/name
        subprocess.run(['zstd', '-q', '-o', str(path)], input=data, check=True)
        assert subprocess.check_output(['zstd', '-dc', str(path)]) == data
    # Persist predictions before evaluation data is ever loaded.
    compressed('predictions.json.zst', predictions)
    metrics, scored = score(predictions, a.evaluation_root)
    compressed('evaluation.json.zst', scored)
    for name in ('predictions.json.zst', 'intervals.json.zst', 'input-hashes.tsv'):
        path = a.evaluation_root/name; hashes[str(path)] = sha(path)
    result = dict(schema='ugrp.e2e_vomask_replay.v2', source_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        simulation=False, model_calls=0, options=OPTIONS, frames=len(predictions), cases=cases, metrics=metrics,
        map_registration=dict(n=sum(p['registration']['status'] == 'registered' for p in predictions), N=len(predictions),
            counts=dict(Counter(p['registration']['status'] for p in predictions)),
            reason='Stored own-SLAM map_to_odom does not anchor the authored world map; no spawn/GT/identity or last-frame extrapolation'),
        ranges_available=0, scope='fixed commands; DEV, observed data; no closed-loop or full v206 sonar validation')
    (a.output/'replay.json').write_text(json.dumps(result, indent=1)+'\n')
    (a.output/'input-hashes.json').write_text(json.dumps(hashes, indent=1)+'\n')
    print(json.dumps(dict(frames=len(predictions), map_registration=result['map_registration'], metrics=metrics['intervals_by_kind']), indent=1))


if __name__ == '__main__':
    main()
