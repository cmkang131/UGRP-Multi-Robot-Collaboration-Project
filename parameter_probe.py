#!/usr/bin/env python3
"""Parameter sensitivity probe for height-free wall detection.

Tests parameter variations on the curated frame set (4, 20, 105, 169, 170, 219,
244, 340, 816) drawn from outputs/ego-wall-map-probe/map2d/frames.json.

Parameter sets:
  - base:       min_contrast_below=6,  max_band_std=3   (current)
  - sensitive:  min_contrast_below=4,  max_band_std=4
  - very_sens:  min_contrast_below=3,  max_band_std=5

For each set it runs the detector on every frame (passing params through
height_free_wall.detect / link_segments and passing self_top explicitly so the
carried-object mask stays fixed), recomputes segment-to-wall-alignment, and
reports:
  - number of frames that went from zero to >=1 detected segment (zero-frame recovery)
  - per-frame n_detector_columns, n_segments, n_visible_segments
  - mean recall proxy: n_visible_segments / n_gt_walls (GT walls per frame)
  - precision proxy: n_visible_segments / n_segments

Also evaluates whether the range-error correction (applied in
analyze_wall_detection.render_analysis_visualization) improves the alignment
numbers: it recomputes metrics with detected segments radially scaled by
1 + correction where correction = -range_error_med_m of the frame.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path('/Users/changmin/projects/ugrp')
PROBE_CODE = ROOT / 'projects/ugrp-wt/ego-wall-map/experiments/2026-10-05-ego-wall-map-probe/code'
sys.path.insert(0, str(PROBE_CODE))
sys.path.insert(0, str(ROOT / 'projects/ugrp/experiments/2026-09-26-markerless-probe'))

import cv2
import markerless_probe as mp
import height_free_wall as hfw
import wall_probe as rp

DATA = Path('/Users/changmin/projects/ugrp/outputs/ego-wall-map-probe/map2d/frames.json')
EP_DIR = Path('/Users/changmin/projects/ugrp/outputs/v98-dev-align_to_carry-a3415342-s911-wtA/zone_wide_door_geometry_v3')

PARAM_SETS = [
    ('base',       dict(min_contrast_below=6,  max_band_std=3)),
    ('sensitive',  dict(min_contrast_below=4,  max_band_std=4)),
    ('very_sens',  dict(min_contrast_below=3,  max_band_std=5)),
]

FRAME_SET = [4, 20, 105, 169, 170, 219, 244, 340, 816]


def score_segments(segs, rects, hit_m=0.30):
    """Align detected wall segments to GT footprints; return recall/precision proxies."""
    if not rects:
        return 0.0, 0.0, 0
    n_hits_gt = 0
    for w in rects:
        cx, cy, hx, hy = w['cx'], w['cy'], w['hx'], w['hy']
        for s in segs:
            if (min(abs(s['world_x'] - cx), abs(s['world_x_last'] - cx)) <= hx
                    and min(abs(s['world_y'] - cy), abs(s['world_y_last'] - cy)) <= hy):
                n_hits_gt += 1
                break
    recall = n_hits_gt / len(rects)
    vis = sum(1 for s in segs if s['wall_dist_min_m'] <= hit_m)
    prec = vis / len(segs) if segs else 0.0
    return recall, prec, vis


def load_frame(idx):
    """Return (undistorted_image, cm, servo, loaded) for a frame record."""
    row = ctx['frames'][idx]
    t = float(row['sim_time'])
    pose = ctx['pose_at'](t)[0]
    px, py, yaw = pose
    servo = {int(k): int(v) for k, v in row['commanded_servo'].items()}
    loaded = bool(servo.get(3, 0) >= 900)
    b0 = mp.elevation_bias(rp.SEED_BIAS['loaded' if loaded else 'unloaded'], servo)
    bgr = cv2.imread(str(EP_DIR / row['path']), cv2.IMREAD_COLOR)
    und = mp.undistort(bgr)
    cm = mp.column_model(servo, b0, ctx['cols'])
    return und, cm, loaded


def run_frame(idx, params):
    """Run detector on a frame with the given parameter override."""
    und, cm, loaded = load_frame(idx)
    self_top = rp.self_top_for(und, cm, {int(k): int(v) for k, v in
                                          ctx['frames'][idx]['commanded_servo'].items()})
    scan = hfw.detect(und, cm, params=params, self_top=self_top, loaded=loaded)
    segs = hfw.link_segments(scan, params=params)
    segs_w = []
    for s in segs:
        first = ctx['rot'] @ np.asarray([px + s['range_first_m'] * math.cos(s['bearing_first_rad']),
                                         py + s['range_first_m'] * math.sin(s['bearing_first_rad'])]) + ctx['pose']
        last = ctx['rot'] @ np.asarray([px + s['range_last_m'] * math.cos(s['bearing_last_rad']),
                                        py + s['range_last_m'] * math.sin(s['bearing_last_rad'])]) + ctx['pose']
        d_first = rp.dist_to_walls((float(first[0]), float(first[1])), rects)
        d_last = rp.dist_to_walls((float(last[0]), float(last[1])), rects)
        segs_w.append(dict(
            world_x=float(first[0]), world_x_last=float(last[0]),
            world_y=float(first[1]), world_y_last=float(last[1]),
            range_first_m=float(s['range_first_m']),
            wall_dist_min_m=min(d_first, d_last)))
    det_cols = int(np.isfinite(scan['vb'][:, 0]).sum())
    return det_cols, len(segs), segs_w


def scale_segments_range(segs_w, correction, px, py):
    """Apply the detector-vs-GT range correction (scale detected points radially about camera)."""
    if correction is None or not math.isfinite(correction):
        return segs_w
    out = []
    for s in segs_w:
        s = dict(s)
        for key in ('world_x', 'world_x_last'):
            r0 = math.hypot(s[key] - px, s[key] - py)
            if r0 > 0:
                scale = (r0 + correction) / r0
                s[key] = px + (s[key] - px) * scale
        out.append(s)
    return out


def main():
    global ctx, rects, px, py, rot, pose, yaw

    data = json.loads(DATA.read_text())
    frames = data['frames']
    ctx = dict(frames=frames, pose_at=lambda t: (np.array([0.0, 0.0, 0.0]), 0))
    # Build real pose lookup from trajectory.jsonl.
    traj = [json.loads(l) for l in (EP_DIR / 'eval_only' / 'trajectory.jsonl').read_text().splitlines() if l.strip()]
    from xml.etree import ElementTree as ET
    scene = ET.parse(EP_DIR / 'scene.xml').getroot()
    world = scene.find('worldbody')
    nq = nv = 0
    qa = None
    for node in world.iter():
        if node.tag not in ('joint', 'freejoint'):
            continue
        kind = node.get('type', 'free' if node.tag == 'freejoint' else 'hinge')
        if node.get('name') == 'r1__base_free' and kind == 'free':
            qa = (nq, nv)
        nq += {'free': 7, 'ball': 4}.get(kind, 1)
        nv += {'free': 6, 'ball': 3}.get(kind, 1)

    def yaw_from_quat(quat):
        w, x, y, z = quat
        return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))

    t_of = [float(r['sim_time']) for r in frames]
    poses = [(float(t['qpos'][qa[0]]), float(t['qpos'][qa[0] + 1]), yaw_from_quat(t['qpos'][qa[3]:qa + 7]))
             for t in traj]

    def pose_at(t):
        i = int(np.searchsorted(t_of, t))
        i = min(max(i, 0), len(poses) - 1)
        return np.array(poses[i]), i

    ctx['pose_at'] = pose_at
    ctx['cols'] = mp.column_positions(96, 2)

    with open(EP_DIR / 'inputs' / 'static_map.json') as f:
        static = json.load(f)
    rects = []
    for o in static['obstacles']:
        if o.get('kind') != 'wall':
            continue
        cx, cy = o['center_m']
        hx, hy = o['half_extents_m']
        rects.append({'cx': float(cx), 'cy': float(cy), 'hx': float(hx), 'hy': float(hy), 'height_m': 0.4})

    results = []

    for name, p in PARAM_SETS:
        per_frame = []
        zero_to_some = 0
        zero_frames = set()
        for idx in FRAME_SET:
            fr = frames[idx]
            if fr['counts']['n_segments'] == 0:
                zero_frames.add(idx)
        baseline_seg = {idx: frames[idx]['counts']['n_segments'] for idx in FRAME_SET}
        baseline_det = {idx: frames[idx]['counts']['n_detector_columns'] for idx in FRAME_SET}
        baseline_vis = {idx: frames[idx]['counts']['n_visible_segments'] for idx in FRAME_SET}

        for idx in FRAME_SET:
            und, cm, loaded = load_frame(idx)
            servo = ctx['frames'][idx]['commanded_servo']
            self_top = rp.self_top_for(und, cm, {int(k): int(v) for k, v in servo.items()})
            scan = hfw.detect(und, cm, params=p, self_top=self_top, loaded=loaded)
            segs = hfw.link_segments(scan, params=p)
            det_cols = int(np.isfinite(scan['vb'][:, 0]).sum())
            # world coords
            t = float(ctx['frames'][idx]['sim_time'])
            px, py, yaw = pose_at(t)
            cos_y, sin_y = math.cos(yaw), math.sin(yaw)
            rot = np.array([[cos_y, -sin_y], [sin_y, cos_y]])
            pts = []
            for s in segs:
                a = rot @ np.asarray([px + s['range_first_m'] * math.cos(s['bearing_first_rad']),
                                      py + s['range_first_m'] * math.sin(s['bearing_first_rad'])]) + np.array([px, py])
                b = rot @ np.asarray([px + s['range_last_m'] * math.cos(s['bearing_last_rad']),
                                      py + s['range_last_m'] * math.sin(s['bearing_last_rad'])]) + np.array([px, py])
                pts.append((float(a[0]), float(b[0]), float(a[1]), float(b[1])))
            recall, prec, nvis = score_segments(pts, rects)
            dv = fr.get('detector_vs_gt', {})
            correction = None
            rc = dv.get('range_error_med_m')
            if rc is not None and math.isfinite(rc):
                correction = -float(rc)
            if correction:
                pts = scale_segments_range(pts, correction, px, py)
                recall_corr, prec_corr, nvis_corr = score_segments(pts, rects)
            else:
                recall_corr = prec_corr = nvis_corr = None
            per_frame.append({
                'frame': idx,
                'detector_columns': det_cols,
                'n_segments': len(segs),
                'n_visible_segments': nvis,
                'recall': recall,
                'precision': prec,
                'recall_corr': recall_corr,
                'precision_corr': prec_corr,
            })
        results.append({'set': name, 'params': p, 'per_frame': per_frame,
                        'zero_frames': sorted(zero_frames),
                        'baseline_seg': baseline_seg, 'baseline_det': baseline_det,
                        'baseline_vis': baseline_vis})

    print("\n" + "=" * 100)
    print("PARAMETER PROBE RESULTS  (frames: " + ", ".join(str(f) for f in FRAME_SET) + ")")
    print("=" * 100)

    for r in results:
        name, p = r['set'], r['params']
        print(f"\n--- Parameter set: {name:12s} min_contrast_below={p['min_contrast_below']}, "
              f"max_band_std={p['max_band_std']} ---")
        print(f"{'frame':>5} {'cols':>6} {'seg':>5} {'base_seg':>9} {'vis':>5} {'recall':>7} "
              f"{'recall_corr':>11} {'prec':>7} {'prec_corr':>11}")
        zero_recovered = 0
        for pf in r['per_frame']:
            f = pf['frame']
            zero_to = ('**ZERO->!' if (r['baseline_seg'][f] == 0 and pf['n_segments'] > 0) else '')
            if r['baseline_seg'][f] == 0 and pf['n_segments'] > 0:
                zero_recovered += 1
            line = f"{f:>5} {pf['detector_columns']:>6} {pf['n_segments']:>5} {r['baseline_seg'][f]:>9} " \
                   f"{pf['n_visible_segments']:>5} {pf['recall']:>7.2f} {pf['recall_corr']:>11.2f} " \
                   f"{pf['precision']:>7.2f} {pf['precision_corr']:>11.2f}{zero_to}"
            if r['baseline_seg'][f] == 0 or zero_recovered:
                print(line)

        mean_recall = np.mean([pf['recall'] for pf in r['per_frame']])
        mean_recall_corr = np.mean([pf['recall_corr'] for pf in r['per_frame'] if pf['recall_corr'] is not None])
        print(f"\nMean recall (GT walls covered): base={np.mean([r['baseline_vis'][i]/max(1,len(rects)) for i in FRAME_SET]):.3f}, "
              f"set={mean_recall:.3f}, with_range_corr={mean_recall_corr:.3f}")
        print(f"Zero-detection frames recovered to >=1 segment: {zero_recovered}/{len(r['zero_frames'])} "
              f"(frames {r['zero_frames']})")

    print("\n" + "=" * 100)
    print("RECOMMENDATION")
    print("=" * 100)
    # Pick best overall by mean recall (with correction), tie-break by precision.
    best = None
    best_score = None
    for r in results:
        mean_corr = np.mean([pf['recall_corr'] for pf in r['per_frame'] if pf['recall_corr'] is not None])
        mean_prec = np.mean([pf['precision_corr'] for pf in r['per_frame'] if pf['precision_corr'] is not None])
        zero_rec = sum(1 for pf in r['per_frame']
                       if r['baseline_seg'][pf['frame']] == 0 and pf['n_segments'] > 0)
        score = (mean_corr, mean_prec, zero_rec)
        if best_score is None or score > best_score:
            best_score = score
            best = r
    print(f"Best overall parameter set: {best['set']} "
          f"(min_contrast_below={best['params']['min_contrast_below']}, "
          f"max_band_std={best['params']['max_band_std']})")
    print(f"  Mean recall with range correction: {best_score[0]:.3f}")
    print(f"  Mean precision with range correction: {best_score[1]:.3f}")
    print(f"  Zero-frame recovery: {best_score[2]}")


if __name__ == '__main__':
    main()
