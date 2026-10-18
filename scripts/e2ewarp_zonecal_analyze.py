#!/usr/bin/env python3
"""Fit the GPU-render appearance profile from the zone calibration capture.

Inputs (allowed): the capture's own RGB frames, the FK camera model from the
issued arm command, the static-map zone rectangle, and **eval-only** labels
(actual camera pose + zone rectangle masks) used only to score thresholds.
No simulator, no model, no control.  The capture is labelled "GPU appearance
calibration, not research result" and is never pooled with research results.

Outputs: a JSON with the label distributions, the threshold grid search, the
chosen profile, and before/after detection counts on
* the capture frames (zone-B positives and pickup-zone negatives), and
* the recorded R4 own frames (all floor negatives; the R4 smoke never reached
  the east room), which is the frame set where the CPU profile produced
  180/183 floor false positives.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ZONE_B_RECT = (4.30, 4.90, -2.80, -1.40)


def load_path_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_replay_helpers():
    replay = load_path_module(
        'e2ewarp_visdet_replay', ROOT / 'scripts' / 'e2ewarp_visdet_replay.py')
    det = load_path_module(
        'own_rgb_zone_visdet', ROOT / 'harness' / 'own_rgb_zone_visdet.py')
    return replay, det


def rays_cam_frame():
    replay, _ = load_replay_helpers()
    return replay.fisheye_rays_camera_frame()


def camera_model_from_capture(det, frame_record, rays_cam):
    """Camera model in the robot base frame from the issued-command FK pose."""
    fk = frame_record['fk_camera']
    rot = np.asarray(fk['rotation'], float).reshape(3, 3)
    trans = np.asarray(fk['translation_m'], float)
    yaw = float(frame_record['base_pose_eval_only'][2])
    rz = np.array([[math.cos(yaw), -math.sin(yaw), 0.0],
                   [math.sin(yaw), math.cos(yaw), 0.0],
                   [0.0, 0.0, 1.0]])
    rot_world = rz @ rot
    return det.CameraModel(kind='rays', width=640, height=480,
                           rays=np.einsum('hwj,ij->hwi', rays_cam,
                                          rot_world).astype(np.float32),
                           translation_m=tuple((rz @ trans).tolist()))


def zone_b_mask_from_eval_pose(frame_record, rays_cam):
    """Eval-only label: pixels whose floor ray lands inside the zone-B rect."""
    cam = frame_record['actual_camera_pose_eval_only']
    xpos = np.asarray(cam['xpos'], float)
    xmat = np.asarray(cam['xmat'], float).reshape(3, 3)
    # MuJoCo camera frame (x right, y up, z back) -> ray directions.
    rays_mj = np.stack([rays_cam[..., 0], -rays_cam[..., 1],
                        -rays_cam[..., 2]], axis=-1)
    rw = rays_mj @ xmat.T
    denom = rw[..., 2]
    scale = np.divide(-xpos[2], denom,
                      out=np.full_like(denom, np.inf),
                      where=np.abs(denom) > 1e-9)
    px = xpos[0] + scale * rw[..., 0]
    py = xpos[1] + scale * rw[..., 1]
    ok = (scale > 0) & np.isfinite(scale)
    x0, x1, y0, y1 = ZONE_B_RECT
    return ok & (px >= x0) & (px <= x1) & (py >= y0) & (py <= y1)


def capture_frames(det, capture_dir, rays_cam):
    frames = json.loads((capture_dir / 'frames.json').read_text())
    out = []
    for rec in frames:
        rgb = cv2.cvtColor(cv2.imread(str(capture_dir / 'rgb' / rec['frame'])),
                           cv2.COLOR_BGR2RGB)
        label = zone_b_mask_from_eval_pose(rec, rays_cam)
        zone_px = int(label.sum())
        # Label by what is actually visible (the aim target is not the label):
        out.append(dict(name='capture:' + rec['frame'],
                        kind='zone_B' if zone_px >= 500 else
                             ('pickup_zone' if rec['kind'] == 'pickup_zone'
                              else 'other'),
                        zone_px=zone_px, rgb=rgb,
                        camera=camera_model_from_capture(det, rec, rays_cam),
                        source='capture'))
    return out


def r4_frames(det, replay, raw: Path, rays_cam, max_frames=None):
    commands = replay.load_commands(raw)
    module = det
    import harness.visual_arm  # noqa: F401
    fk = load_path_module('servo_camera_fk',
                          ROOT / 'harness' / 'servo_camera_fk.py')
    models = {}
    out = []
    paths = sorted(raw.glob('world-*/review-rgb/*.jpg'))
    if max_frames:
        paths = paths[:int(max_frames)]
    for path in paths:
        world = int(path.parents[1].name.split('-')[1])
        mt = __import__('re').match(r'(?P<robot>r[123])-(?P<tick>\d{6})\.jpg',
                                    path.name)
        if not mt:
            continue
        robot, tick = mt.group('robot'), int(mt.group('tick'))
        pwm = commands.get((world, robot, round(tick / 10.0, 3)))
        if pwm is None:
            continue
        key = (world, robot, pwm['1'], pwm['3'], pwm['4'], pwm['5'], pwm['6'])
        if key not in models:
            models[key], _ = replay.camera_model_for(module, pwm, rays_cam, fk)
        if models[key] is None:
            continue
        rgb = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        out.append(dict(name='r4:' + path.name, kind='floor_negative', zone_px=0,
                        rgb=rgb, camera=models[key], source='r4'))
    return out


def evaluate(det, frames, profile, override=None, appearance='cpu_v1'):
    accepted = 0
    by_kind = Counter()
    reasons = Counter()
    for f in frames:
        d = det.detect(f['rgb'], f['camera'], enabled=True,
                       appearance=appearance, override=override)
        ok = d.status == 'observed'
        accepted += int(ok)
        by_kind[(f['kind'], ok)] += 1
        reasons[f"{f['kind']}:{d.status}:{d.reason}"] += 1
    return dict(accepted=accepted, n=len(frames),
                by_kind={f'{k[0]}|accepted={k[1]}': v
                         for k, v in sorted(by_kind.items())},
                reasons=dict(reasons))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--capture', type=Path, required=True)
    ap.add_argument('--r4-raw', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--r4-max-frames', type=int, default=None)
    a = ap.parse_args()
    replay, det = load_replay_helpers()
    rays_cam = rays_cam_frame()
    caps = capture_frames(det, a.capture, rays_cam)
    r4 = r4_frames(det, replay, a.r4_raw, rays_cam, a.r4_max_frames)
    positives = [f for f in caps if f['kind'] == 'zone_B']
    neg_capture = [f for f in caps if f['kind'] == 'pickup_zone']
    before = dict(
        capture_positives=evaluate(det, positives, 'cpu_v1'),
        capture_pickup_negatives=evaluate(det, neg_capture, 'cpu_v1'),
        r4_floor_negatives=evaluate(det, r4, 'cpu_v1'))
    grid = []
    best = None
    for hlo in (106, 108, 110):
        for hhi in (114, 116, 118, 120):
            if hhi <= hlo:
                continue
            for smin in (100, 140, 170):
                for vmax in (95, 110, 125, 160, 255):
                    override = dict(hue=(hlo, hhi), s_min=smin, v_min=30,
                                    v_max=vmax, max_extent_m=1.75)
                    pos = evaluate(det, positives, None, override=override)
                    neg = evaluate(det, neg_capture, None, override=override)
                    r4ev = evaluate(det, r4, None, override=override)
                    fp = neg['accepted'] + r4ev['accepted']
                    score = pos['accepted'] - 5 * fp
                    row = dict(hue=(hlo, hhi), s_min=smin, v_max=vmax,
                               positives_accepted=pos['accepted'],
                               pickup_fp=neg['accepted'],
                               r4_fp=r4ev['accepted'], score=score)
                    grid.append(row)
                    if best is None or score > best['score']:
                        best = row
    chosen = dict(hue=tuple(best['hue']), s_min=best['s_min'], v_min=30,
                  v_max=best['v_max'], max_extent_m=1.75)
    after = dict(
        capture_positives=evaluate(det, positives, None,
                                   override=chosen),
        capture_pickup_negatives=evaluate(det, neg_capture, None,
                                          override=chosen),
        r4_floor_negatives=evaluate(det, r4, None, override=chosen))
    report = dict(
        schema='ugrp.e2ewarp.zonecal_appearance.v1',
        label='GPU appearance calibration, not research result',
        not_pooled_with=['R1..R4 e2ewarp attempts', 'visgoal gates',
                         'any research result'],
        capture_dir=str(a.capture),
        capture_frames_sha256={f['frame']: f.get('image_sha256') for f in
                               json.loads((a.capture / 'frames.json').read_text())},
        r4_raw=str(a.r4_raw),
        labels=dict(zone_B_positives=len(positives),
                    pickup_negatives=len(neg_capture),
                    r4_floor_negatives=len(r4),
                    label_rule='eval-only floor-ray mask inside the static-map '
                               'zone-B rectangle; >=500 px = zone_B visible'),
        distributions=dict(
            capture_zone_B=[dict(frame=f['name'], zone_px=f['zone_px'])
                            for f in positives][:12],
        ),
        grid_top=sorted(grid, key=lambda r: -r['score'])[:8],
        chosen_profile=chosen,
        before_after=dict(before=before, after=after),
        scope=('appearance-threshold fitting on the approved GPU calibration '
               'capture only; the capture and this fit are not research '
               'results and are not pooled. Detector remains default off; '
               'arrival judgement is still the navigation adapter decision.'),
        dependency_wait=['ACT', 'loaded FK', 'mapbuild8 map correction',
                         'release relocalization'],
    )
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(dict(chosen=chosen,
                          positives=dict(
                              before=before['capture_positives']['accepted'],
                              after=after['capture_positives']['accepted'],
                              n=len(positives)),
                          pickup_fp=dict(
                              before=before['capture_pickup_negatives']['accepted'],
                              after=after['capture_pickup_negatives']['accepted'],
                              n=len(neg_capture)),
                          r4_fp=dict(before=before['r4_floor_negatives']['accepted'],
                                     after=after['r4_floor_negatives']['accepted'],
                                     n=len(r4))), indent=2))


if __name__ == '__main__':
    main()
