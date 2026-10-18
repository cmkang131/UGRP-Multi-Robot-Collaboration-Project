#!/usr/bin/env python3
"""Replay recorded GPU E2E own frames through the pure-RGB zone detector.

No simulator, no engine, no new execution: this reads the raw run's recorded
2 Hz ``review-rgb`` own frames and the issued command rows, builds the camera
model from the **issued servo commands** (owner FK ``servo_fk_v1``) plus the
fixed measured fisheye calibration, and runs
``harness/own_rgb_zone_visdet.py`` on each frame.  It verifies only that the
detector runs on real MJWarp-GPU-rendered frames and which own-RGB evidence
categories it reports; it does not claim navigation or mission success.

Allowed inputs: own RGB frames, own issued commands, fixed camera calibration
and FK geometry (all recorded/static).  Never read: TOP camera, simulator or
GT pose, contacts, measured joints, teacher phases/outcomes.

Usage:
``python3 scripts/e2ewarp_visdet_replay.py --raw <raw dir> --output <json>``
where ``<raw dir>`` contains ``world-*/review-rgb/*.jpg`` and ``commands.json``.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CALIBRATION = ROOT / 'sim' / 'masterpi_camera_profile.py'
FRAME_RE = r'(?P<robot>r[123])-(?P<tick>\d{6})\.jpg'


def load_path_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_calibration():
    cal = load_path_module('masterpi_camera_profile', CALIBRATION)
    return (np.asarray(cal.scaled_camera_matrix(640, 480), float),
            np.asarray(cal.CAMERA_FISHEYE_D, float).reshape(4, 1))


def fisheye_rays_camera_frame():
    """Raw fisheye pixel -> OpenCV camera-frame ray (x right, y down, z fwd)."""
    k, d = load_calibration()
    ys, xs = np.indices((480, 640), dtype=np.float64)
    raw = np.stack((xs, ys), axis=-1).reshape(-1, 1, 2)
    ideal = cv2.fisheye.undistortPoints(raw, k, d).reshape(480, 640, 2)
    rays = np.concatenate([ideal, np.ones((480, 640, 1))], axis=-1)
    return rays / np.linalg.norm(rays, axis=-1, keepdims=True)


def camera_model_for(module, pwm, rays_cam, fk_module):
    """CameraModel from issued servo commands (FK) + fixed fisheye rays."""
    pose, reason = fk_module.transform_from_commands(
        {int(k): int(v) for k, v in pwm.items()}, camera_pose='servo_fk_v1')
    if pose is None:
        return None, reason
    translation, rotation = pose
    rays = np.einsum('hwj,ij->hwi', rays_cam, rotation)  # camera -> floor frame
    return module.CameraModel(kind='rays', width=640, height=480,
                              rays=rays.astype(np.float32),
                              translation_m=tuple(float(v) for v in translation)), reason


def load_commands(raw: Path):
    rows = json.loads((raw / 'commands.json').read_text())
    out = {}
    for row in rows:
        key = (int(row['world']), str(row['robot']), round(float(row['t']), 3))
        out[key] = row['pwm']
    return out


def replay(raw: Path, *, enabled=True, worlds=None, robots=('r1', 'r2', 'r3'),
           max_frames=None, max_extent_m='default'):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    module = load_path_module(
        'own_rgb_zone_visdet', ROOT / 'harness' / 'own_rgb_zone_visdet.py')
    import harness.visual_arm  # noqa: F401  (constants used by the FK module)
    fk = load_path_module('servo_camera_fk',
                          ROOT / 'harness' / 'servo_camera_fk.py')
    rays_cam = fisheye_rays_camera_frame()
    commands = load_commands(raw)
    results, reasons = [], Counter()
    models = {}
    frame_glob = sorted(raw.glob('world-*/review-rgb/*.jpg'))
    if max_frames:
        frame_glob = frame_glob[:int(max_frames)]
    for path in frame_glob:
        world = int(path.parents[1].name.split('-')[1])
        import re
        mt = re.match(FRAME_RE, path.name)
        if not mt:
            continue
        robot, tick = mt.group('robot'), int(mt.group('tick'))
        if worlds is not None and world not in worlds:
            continue
        if robot not in robots:
            continue
        pwm = commands.get((world, robot, round(tick / 10.0, 3)))
        rgb = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        if pwm is None:
            results.append(dict(world=world, robot=robot, tick=tick,
                                status='unknown', reason='command_row_missing',
                                pixels=0, nearest_range_m=None,
                                extent_m=None, bottom_norm=None,
                                paint_reaches_bottom_band=False))
            reasons['command_row_missing'] += 1
            continue
        bucket = (world, robot, tick // 100)
        if bucket not in models:
            models[bucket], reason = camera_model_for(module, pwm, rays_cam, fk)
            if models[bucket] is None:
                results.append(dict(world=world, robot=robot, tick=tick,
                                    status='unknown', reason=reason,
                                    pixels=0, nearest_range_m=None,
                                    extent_m=None, bottom_norm=None,
                                    paint_reaches_bottom_band=False))
                reasons[reason] += 1
                continue
        kwargs = {} if max_extent_m == 'default' else dict(max_extent_m=max_extent_m)
        det = module.detect(rgb, models[bucket], enabled=enabled, **kwargs)
        row = dict(world=world, robot=robot, tick=tick, status=det.status,
                   reason=det.reason,
                   pixels=det.pixels,
                   nearest_range_m=det.nearest_range_m,
                   extent_m=det.extent_m,
                   bottom_norm=det.bottom_norm,
                   paint_reaches_bottom_band=det.paint_reaches_bottom_band)
        results.append(row)
        reasons[f'{det.status}:{det.reason}'] += 1
    observed = [r for r in results if r['status'] == 'observed']
    nearest = [r['nearest_range_m'] for r in observed
               if r['nearest_range_m'] is not None]
    report = dict(
        schema='ugrp.e2ewarp.visdet_replay.v1',
        raw=str(raw.resolve()),
        analysis_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        frames=len(results),
        observed_n=len(observed),
        arrival_evidence_n=sum(bool(r.get('paint_reaches_bottom_band'))
                               for r in results),
        reason_distribution=dict(reasons),
        nearest_range_m=(dict(min=min(nearest), median=statistics.median(nearest),
                              max=max(nearest)) if nearest else None),
        frames_by_world_robot={f'{k[0]}-{k[1]}': v for k, v in
                               Counter((r['world'], r['robot'])
                                       for r in results).items()},
        camera_model='servo_fk_v1 (issued command rows) + measured raw-fisheye '
                     'undistort table; floor plane z=0 in the FK floor frame',
        inputs=['world-*/review-rgb/*.jpg', 'commands.json',
                'harness/servo_camera_fk.py', 'harness/data/servo_camera_v3_chain.json',
                'sim/masterpi_camera_profile.py (fixed calibration)'],
        not_read=['TOP camera', 'simulator/GT pose', 'contacts',
                  'measured joints', 'teacher/outcomes', 'llm choices'],
        scope=('detector replay on recorded GPU E2E own frames only; no new '
               'execution, no navigation/mission success claim. FK is the '
               'issued-command nominal pose, so metric range/extent on replay '
               'frames are approximate; the colour component/status evidence '
               'does not depend on the pose.'),
        dependency_wait=['selected ACT student', 'loaded FK',
                         'mapbuild8 map correction', 'release relocalization'],
    )
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--worlds', default=None,
                   help='comma-separated world ids (default all)')
    p.add_argument('--robots', default='r1,r2,r3')
    p.add_argument('--max-frames', type=int, default=None)
    p.add_argument('--no-extent-cap', action='store_true',
                   help='diagnostic only: disable the zone-size extent cap')
    a = p.parse_args()
    worlds = None if a.worlds is None else {int(v) for v in a.worlds.split(',')}
    report = replay(a.raw, worlds=worlds, robots=tuple(a.robots.split(',')),
                    max_frames=a.max_frames,
                    max_extent_m=None if a.no_extent_cap else 'default')
    report['extent_cap'] = 'off' if a.no_extent_cap else 'module-default'
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    (a.output.parent / (a.output.stem + '.sha256.json')).write_text(json.dumps(
        {a.output.name: hashlib.sha256(a.output.read_bytes()).hexdigest()},
        indent=2) + '\n')
    print(json.dumps({k: report[k] for k in
                      ('frames', 'observed_n', 'arrival_evidence_n',
                       'nearest_range_m', 'reason_distribution')},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
