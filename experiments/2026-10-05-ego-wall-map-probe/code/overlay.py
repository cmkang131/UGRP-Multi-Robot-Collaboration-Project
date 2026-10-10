"""Render one undistorted frame with detector rows and ground-truth contact rows drawn.

Diagnostic visualisation only. Ground truth is drawn for inspection; it is not fed
back into the detector.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-26-markerless-probe'))
sys.path.insert(0, str(HERE))

import markerless_probe as mp  # noqa: E402
import height_free_wall as hfw  # noqa: E402
import wall_probe as rp  # noqa: E402
from coverage import ray_rect, MAX_RANGE_M  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--episode', required=True)
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--frame', type=int, default=1)
    ap.add_argument('--out', required=True)
    ap.add_argument('--scale', type=float, default=1.0)
    ap.add_argument('--load-rule', choices=('s3', 'gripper'), default='s3',
                    help='own load state: s3 = the earlier servo[3] >= 900 (default), gripper = commanded gripper closed')
    args = ap.parse_args()
    rp.set_load_rule(args.load_rule)

    ep = Path(args.episode)
    static_map = json.loads((ep/'inputs'/'static_map.json').read_text())
    rects = rp.wall_rects(static_map)
    frames, _ = rp.resolve_frames(ep, args.robot)
    cols = mp.column_positions(rp.FROZEN_DETECTOR['columns'], rp.FROZEN_DETECTOR['strip_half_px'])
    row = frames[args.frame]
    servo = {int(k): int(v) for k, v in row['commanded_servo'].items()}
    bgr = cv2.imread(str(ep/row['path']), cv2.IMREAD_COLOR)
    und = mp.undistort(bgr)
    loaded = rp.loaded_for(servo, legacy_str_key=True)
    b0 = mp.elevation_bias(rp.SEED_BIAS['loaded' if loaded else 'unloaded'], servo)
    cm = mp.column_model(servo, b0, cols)

    vis = und.copy()
    # self-mask ON: carried beam/crate rows are excluded from detection (own image +
    # own commanded load state only).
    self_top = rp.self_top_for(und, cm, servo)
    scan = hfw.detect(und, cm, self_top=self_top)
    for j in range(len(cols)):
        for k in range(int(hfw.PARAMS['candidates'])):
            vb = scan['vb'][j, k]
            if not np.isfinite(vb):
                continue
            colour = (0, 0, 255) if k == 0 else ((0, 165, 255) if k == 1 else (255, 200, 0))
            cv2.line(vis, (int(cols[j]), int(vb)), (int(cols[j]) + 1, int(vb)), colour, 1, cv2.LINE_AA)
            vt = scan['vt'][j, k]
            if np.isfinite(vt):
                cv2.line(vis, (int(cols[j]), int(vt)), (int(cols[j]) + 1, int(vt)), (0, 255, 255), 1, cv2.LINE_AA)

    # ground-truth wall contact rows, in green, drawn per column
    for j in range(len(cols)):
        t_hit = ray_rect(cm, j, rects, MAX_RANGE_M)
        if t_hit is None:
            continue
        rv = float(np.ravel(cm.rows(np.asarray([t_hit]), np.asarray([0.])))[0])
        if np.isfinite(rv) and 0 <= rv <= mp.HEIGHT - 1:
            cv2.line(vis, (int(cols[j]), int(rv)), (int(cols[j]) + 1, int(rv)), (0, 255, 0), 2, cv2.LINE_AA)

    if args.scale != 1.0:
        vis = cv2.resize(vis, None, fx=args.scale, fy=args.scale, interpolation=cv2.INTER_AREA)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), vis)
    occ = self_top < hfw.HEIGHT
    print(f'wrote {out}  ({vis.shape[1]}x{vis.shape[0]})  green=gt contact row, red/orange/yellow=detected vb, cyan=measured vt')
    print(f'self-mask ON (self_mask, undistorted frame, own commanded s3={servo.get(3, 0)}): '
          f'{int(occ.sum())}/{len(self_top)} columns occluded')


if __name__ == '__main__':
    main()