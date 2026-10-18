#!/usr/bin/env python3
"""Offline floor vs zone-B colour separability measurement (no GPU, no control).

Purpose: prereg the own-RGB zone detector thresholds in **OpenCV HSV units**
(H 0-180, S/V 0-255) before any further physical nav-gate run.  This script
reads only recorded frames plus eval-only pose labels; it never starts a
simulator, never issues a command, and is not a research result.

Inputs
------
``--zonecal-dir``: the frozen GPU appearance capture
``experiments/2026-10-17-e2ewarp/r4-selfmap-recount/zonecal-gpu`` (branch
``dsh/e2ewarp-components-v1``, commit ``b894d8cb1``).  30 zone-B frames with
eval-only ``actual_camera_pose``; the script verifies every JPEG against the
capture's ``SHA256SUMS.json``.  Labels are the eval-only floor-ray mask inside
the static-map zone-B rectangle: they score thresholds and are never a
controller input.

``--nav-frame``: recorded nav-gate own frames (the first physical gate).  The
blue pickup-region floor is measured in fixed ROIs and a real floor frame is
run through the detector as a negative test.

Output: one JSON artifact with per-channel percentiles, pixel overlap, and the
largest-component detection rate per candidate band.  No thresholds are chosen
here; the prereg in ``experiments/2026-10-18-nav-gate-1/CALIBRATION_PREREG.md``
records the verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.e2ewarp_selfnav import (GPU_CALIB_V1, GpuCalibZoneDetector,  # noqa: E402
                                     hue_degrees_to_opencv, largest_component,
                                     rgb_to_hsv)

ZONE_RECT = (4.30, 4.90, -2.80, -1.40)  # static-map zone B, eval-only label
# Fixed ROIs (rows, cols) over the recorded nav-gate frame.  The blue pickup
# region floor fills the lower half; the white rectangle only delimits the
# sample and never feeds the detector.
NAV_ROIS = {
    'floor_pickup_blue': ((150, 330), (100, 500)),
    'floor_pickup_blue_low': ((330, 380), (150, 480)),
}
CANDIDATE_BANDS = (
    dict(name='gpu_calib_v1', hue_cv=(110.0, 114.0), sat_min=100.0, val=(30.0, 110.0)),
    dict(name='wide_109_115', hue_cv=(109.0, 115.0), sat_min=100.0, val=(30.0, 110.0)),
    dict(name='wide_108_116', hue_cv=(108.0, 116.0), sat_min=100.0, val=(30.0, 110.0)),
    dict(name='tight_sat_140', hue_cv=(110.0, 114.0), sat_min=140.0, val=(30.0, 110.0)),
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def percentiles(values):
    a = np.asarray(values, dtype=np.float64)
    if not a.size:
        return {}
    p = np.percentile(a, [5, 50, 95])
    return dict(n=int(a.size), p5=round(float(p[0]), 2), p50=round(float(p[1]), 2),
                p95=round(float(p[2]), 2), min=round(float(a.min()), 2),
                max=round(float(a.max()), 2))


def camera_rays():
    """Raw fisheye pixel -> OpenCV camera-frame unit ray (fixed camera model)."""
    from sim import masterpi_camera_profile as profile
    k = np.asarray(profile.scaled_camera_matrix(640, 480), float)
    d = np.asarray(profile.CAMERA_FISHEYE_D, float).reshape(4, 1)
    ys, xs = np.indices((480, 640), dtype=np.float64)
    raw = np.stack((xs, ys), axis=-1).reshape(-1, 1, 2)
    ideal = cv2.fisheye.undistortPoints(raw, k, d).reshape(480, 640, 2)
    rays = np.concatenate([ideal, np.ones((480, 640, 1))], axis=-1)
    return rays / np.linalg.norm(rays, axis=-1, keepdims=True)


def zone_label(record, rays):
    """Eval-only label: pixels whose floor ray lands inside the zone-B rect."""
    cam = record['actual_camera_pose_eval_only']
    xpos = np.asarray(cam['xpos'], float)
    xmat = np.asarray(cam['xmat'], float).reshape(3, 3)
    rays_mj = np.stack([rays[..., 0], -rays[..., 1], -rays[..., 2]], axis=-1)
    rw = rays_mj @ xmat.T
    denom = rw[..., 2]
    scale = np.divide(-xpos[2], denom, out=np.full_like(denom, np.inf),
                      where=np.abs(denom) > 1e-9)
    px = xpos[0] + scale * rw[..., 0]
    py = xpos[1] + scale * rw[..., 1]
    x0, x1, y0, y1 = ZONE_RECT
    return ((scale > 0) & np.isfinite(scale)
            & (px >= x0) & (px <= x1) & (py >= y0) & (py <= y1))


def verify_capture(capture_dir, records):
    """Verify every JPEG against the capture's own SHA256SUMS list."""
    path = capture_dir / 'SHA256SUMS.json'
    if not path.is_file():
        raise SystemExit('CAPTURE_SHA_MANIFEST_MISSING:' + str(path))
    manifest = {}
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) == 2:
            manifest[parts[1]] = parts[0]
    checked = []
    for rec in records:
        rel = 'rgb/' + rec['frame']
        spec = capture_dir / rel
        digest = sha256(spec)
        if manifest.get(rel) != digest:
            raise SystemExit('CAPTURE_SHA_MISMATCH_OR_UNVERIFIED:' + rel)
        checked.append(dict(frame=rec['frame'], sha256=digest, verified=True))
    return checked, sha256(path)


def band_mask(hsv, band):
    lo, hi = band['hue_cv']
    vlo, vhi = band['val']
    return ((hsv[..., 0] >= lo) & (hsv[..., 0] <= hi)
            & (hsv[..., 1] >= band['sat_min'])
            & (hsv[..., 2] >= vlo) & (hsv[..., 2] <= vhi))


def in_band(h, s, v, band):
    lo, hi = band['hue_cv']
    vlo, vhi = band['val']
    return ((h >= lo) & (h <= hi) & (s >= band['sat_min'])
            & (v >= vlo) & (v <= vhi))


def capture_measure(capture_dir, records, rays):
    zone_h, zone_s, zone_v = [], [], []
    per_frame, labels = [], []
    for rec in records:
        if rec['kind'] != 'zone_B':
            continue
        bgr = cv2.imread(str(capture_dir / 'rgb' / rec['frame']))
        if bgr is None:
            raise SystemExit('CAPTURE_FRAME_UNREADABLE:' + rec['frame'])
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)  # OpenCV H 0-180, S/V 0-255
        label = zone_label(rec, rays) & (hsv[..., 2] >= 15)  # drop unrendered black
        h, s, v = hsv[..., 0][label], hsv[..., 1][label], hsv[..., 2][label]
        if h.size < 500:
            raise SystemExit('ZONE_LABEL_TOO_SMALL:' + rec['frame'])
        zone_h.append(h); zone_s.append(s); zone_v.append(v)
        per_frame.append(dict(frame=rec['frame'], distance_m=round(float(rec['distance_m']), 3),
                              zone_px=int(h.size),
                              h_cv=percentiles(h), s=percentiles(s), v=percentiles(v)))
        labels.append((rec, hsv, label))
    return zone_h, zone_s, zone_v, per_frame, labels


def floor_measure(nav_paths):
    per_frame, pools = [], {'h': [], 's': [], 'v': []}
    for path in nav_paths:
        bgr = cv2.imread(str(path))
        if bgr is None:
            raise SystemExit('NAV_FRAME_UNREADABLE:' + str(path))
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        rows = {}
        for name, ((r0, r1), (c0, c1)) in NAV_ROIS.items():
            h, s, v = hsv[r0:r1, c0:c1, 0].ravel(), hsv[r0:r1, c0:c1, 1].ravel(), hsv[r0:r1, c0:c1, 2].ravel()
            rows[name] = dict(roi=[r0, r1, c0, c1], n=int(h.size),
                              h_cv=percentiles(h), s=percentiles(s), v=percentiles(v))
            if name == 'floor_pickup_blue':
                pools['h'].append(h); pools['s'].append(s); pools['v'].append(v)
        per_frame.append(dict(path=str(path), sha256=sha256(path), rois=rows))
    return per_frame, pools


def component_geometry(hsv, band):
    """Largest-component geometry in frame fractions (the arrival-guard inputs)."""
    comp = largest_component(band_mask(hsv, band))
    if comp is None:
        return None
    h, w = hsv.shape[:2]
    width, height = comp['right'] - comp['left'], comp['bottom'] - comp['top']
    return dict(area_px=comp['area'], bbox=[comp['left'], comp['top'],
                                            comp['right'], comp['bottom']],
                bottom_norm=round(comp['bottom'] / h, 4),
                width_norm=round(width / w, 4), height_norm=round(height / h, 4),
                area_norm=round(comp['area'] / (h * w), 4),
                solidity=round(comp['area'] / (width * height), 4),
                spans_center_x=bool(comp['left'] <= w // 2 < comp['right']),
                touches_top=bool(comp['top'] <= 0))


def detection_counts(labels, nav_paths, band):
    det = GpuCalibZoneDetector(min_pixels=GPU_CALIB_V1['min_pixels'])
    zone_detected, zone_min = 0, None
    for rec, hsv, label in labels:
        mask = band_mask(hsv, band)
        comp = largest_component(mask)
        area = 0 if comp is None else comp['area']
        zone_detected += int(area >= GPU_CALIB_V1['min_pixels'])
        zone_min = area if zone_min is None else min(zone_min, area)
    floor_rows = []
    for path in nav_paths:
        bgr = cv2.imread(str(path))
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        mask = band_mask(hsv, band)
        comp = largest_component(mask)
        floor_rows.append(dict(path=str(path), total_pixels=int(mask.sum()),
                               largest_component_px=0 if comp is None else comp['area'],
                               detected=bool(comp and comp['area'] >= GPU_CALIB_V1['min_pixels']),
                               detector_result=det(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))))
    return dict(band=dict(name=band['name'], hue_cv=list(band['hue_cv']),
                          sat_min=band['sat_min'], val=list(band['val'])),
                zone_frames_detected=zone_detected, zone_frames_n=len(labels),
                zone_min_component_px=zone_min,
                floor_frames=floor_rows,
                floor_frames_detected=sum(row['detected'] for row in floor_rows))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zonecal-dir', type=Path, required=True)
    parser.add_argument('--nav-frame', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)

    frames_json = args.zonecal_dir / 'frames.json'
    records = json.loads(frames_json.read_text())
    checked, sums_sha = verify_capture(args.zonecal_dir, records)
    rays = camera_rays()
    zone_h, zone_s, zone_v, per_frame, labels = capture_measure(args.zonecal_dir, records, rays)
    floor_frames, floor_pool = floor_measure(args.nav_frame)

    h_all = np.concatenate(zone_h); s_all = np.concatenate(zone_s); v_all = np.concatenate(zone_v)
    profile = dict(hue_cv=list(GPU_CALIB_V1['hue_cv']), sat_min=GPU_CALIB_V1['sat_min'],
                   val=list(GPU_CALIB_V1['val']), min_pixels=GPU_CALIB_V1['min_pixels'],
                   units=GPU_CALIB_V1['units'])
    band = dict(CANDIDATE_BANDS[0])
    zone_in_band = in_band(h_all, s_all, v_all, band)
    floor_h = np.concatenate(floor_pool['h']); floor_s = np.concatenate(floor_pool['s'])
    floor_v = np.concatenate(floor_pool['v'])
    floor_in_band = in_band(floor_h, floor_s, floor_v, band)
    result = dict(
        schema='ugrp.e2ewarp.nav_detector_calibration.v1',
        label='offline colour separability measurement; not a research result',
        not_pooled_with=['R1..R4 e2ewarp attempts', 'visgoal gates', 'any research result'],
        units='OpenCV HSV: H 0-180, S/V 0-255; degrees = opencv_h * 2',
        profile=profile,
        inputs=dict(
            zonecal=dict(dir=str(args.zonecal_dir),
                         frames_json_sha256=sha256(frames_json),
                         sha256sums_sha256=sums_sha,
                         frames=checked,
                         zone_b_frames=len(labels)),
            nav_frames=[dict(path=str(p), sha256=sha256(p)) for p in args.nav_frame]),
        zone_b=dict(pooled=dict(h_cv=percentiles(h_all), s=percentiles(s_all), v=percentiles(v_all)),
                    per_frame=per_frame),
        floor_pickup_blue=dict(pooled=dict(h_cv=percentiles(floor_h), s=percentiles(floor_s),
                                           v=percentiles(floor_v)),
                               per_frame=floor_frames),
        pixel_overlap=dict(
            zone_b_in_band_fraction=round(float(zone_in_band.mean()), 4),
            floor_in_band_fraction=round(float(floor_in_band.mean()), 4),
            note='pixel fractions are pooling-weighted; detection is per-frame largest component'),
        candidates=[detection_counts(labels, args.nav_frame, b)
                    for b in CANDIDATE_BANDS],
        component_geometry=dict(
            band='gpu_calib_v1',
            zone_b=[dict(frame=rec['frame'], distance_m=round(float(rec['distance_m']), 3),
                         **(component_geometry(hsv, CANDIDATE_BANDS[0]) or {}))
                    for rec, hsv, _ in labels],
            floor=[dict(path=str(path), current_band=component_geometry(hsv, CANDIDATE_BANDS[0]),
                        widened_108_116=component_geometry(hsv, CANDIDATE_BANDS[2]))
                   for path, hsv in
                   ((path, cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2HSV))
                    for path in args.nav_frame)]),
        limits=['zone-B labels use the zonecal capture (R4 scene, camera aimed with servo 6=1000); '
                'the nav gate holds SEARCH servo 6=1500, so geometry (bottom_norm) does not transfer',
                'floor samples are the two spawn frames of the first physical nav-gate run; '
                'no zone-B frame from the nav-gate scene exists yet'],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps(dict(
        zone_b_frames=len(labels),
        zone_b=result['zone_b']['pooled'],
        floor_pickup_blue=result['floor_pickup_blue']['pooled'],
        overlap=result['pixel_overlap'],
        candidates=[dict(band=c['band']['name'],
                         zone=f"{c['zone_frames_detected']}/{c['zone_frames_n']}",
                         floor=f"{c['floor_frames_detected']}/{len(c['floor_frames'])}",
                         floor_largest=[row['largest_component_px'] for row in c['floor_frames']])
                    for c in result['candidates']],
        output=str(args.output)), indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
