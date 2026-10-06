"""Which recorded frames actually contain a wall contact in view?

Read-only scan of one episode. Ground truth is used only to *label* frames here; the
detector never sees it. Answers: at which commanded arm poses does the own wrist camera
see a floor-wall contact at all, so the probe is scored on frames that can contain one.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-26-markerless-probe'))
sys.path.insert(0, str(HERE))

import markerless_probe as mp  # noqa: E402
import wall_probe as rp  # noqa: E402

MAX_RANGE_M = 6.


def ray_rect(cm, j, rects, max_t):
    """Trace distance where column ``j``'s floor ray meets any wall, else None.

    Axis-aligned rectangle: solve for the slab crossings along the ray and keep the
    smallest positive distance that lies inside the footprint.
    """
    o = cm.origin[:2]
    d = cm.d[j]
    best = None
    for cx, cy, hx, hy, _h in rects:
        lo, hi = -math.inf, math.inf
        ok = True
        for k, (c, e) in enumerate(((cx, hx), (cy, hy))):
            if abs(d[k]) < 1e-12:
                if abs(o[k] - c) > e:
                    ok = False
                    break
                continue
            t1, t2 = (c - e - o[k])/d[k], (c + e - o[k])/d[k]
            lo, hi = max(lo, min(t1, t2)), min(hi, max(t1, t2))
            if lo > hi:
                ok = False
                break
        if ok and lo >= 0 and (best is None or lo < best):
            best = lo
    return best if best is not None and best <= max_t else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--episode', required=True)
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--every', type=int, default=1)
    args = ap.parse_args()

    ep = Path(args.episode)
    static_map = json.loads((ep/'inputs'/'static_map.json').read_text())
    rects = rp.wall_rects(static_map)
    frames, _ = rp.resolve_frames(ep, args.robot)
    cols = mp.column_positions(rp.FROZEN_DETECTOR['columns'], rp.FROZEN_DETECTOR['strip_half_px'])

    by_s3 = defaultdict(lambda: {'n': 0, 'cols_in_view': [], 'rows': []})
    rows_out = []
    for idx in range(0, len(frames), max(1, args.every)):
        row = frames[idx]
        servo = {int(k): int(v) for k, v in row['commanded_servo'].items()}
        s3 = servo.get(3, 0)
        b0 = mp.elevation_bias(rp.SEED_BIAS['loaded' if rp.is_loaded(servo) else 'unloaded'], servo)
        cm = mp.column_model(servo, b0, cols)

        in_view, contact_rows, contacts = 0, [], 0
        for j in range(len(cols)):
            t_hit = ray_rect(cm, j, rects, MAX_RANGE_M)
            if t_hit is None:
                continue
            contacts += 1
            rv = float(np.ravel(cm.rows(np.asarray([t_hit]), np.asarray([0.])))[0])
            if np.isfinite(rv) and 0 <= rv <= mp.HEIGHT - 1:
                in_view += 1
                contact_rows.append(rv)
        rec = {'i': idx, 't': round(float(row['sim_time']), 2), 's3': s3,
               'cam_z': round(float(cm.origin[2]), 4), 'cam_x': round(float(cm.origin[0]), 3),
               'columns_hitting_wall': contacts, 'columns_contact_in_image': in_view}
        rows_out.append(rec)
        e = by_s3[s3]
        e['n'] += 1
        e['cols_in_view'].append(in_view)
        e['rows'].extend(contact_rows)

    print(f'{"s3":>6} {"frames":>7} {"mean_cols_wall":>14} {"mean_cols_in_img":>17} {"row p10":>8} {"row p50":>8} {"row p90":>8}')
    for s3 in sorted(by_s3):
        e = by_s3[s3]
        r = np.asarray(e['rows'], float)
        rs = f'{np.percentile(r, 10):>8.0f} {np.percentile(r, 50):>8.0f} {np.percentile(r, 90):>8.0f}' \
            if r.size else f'{"-":>8} {"-":>8} {"-":>8}'
        print(f'{s3:>6} {e["n"]:>7} {"-":>14} {np.mean(e["cols_in_view"]):>17.2f} {rs}')

    good = [r for r in rows_out if r['columns_contact_in_image'] >= 8]
    print()
    print(f'frames scanned: {len(rows_out)}   frames with >=8 contact columns visible: {len(good)}')
    if good:
        print(f'  t range {good[0]["t"]:.1f}..{good[-1]["t"]:.1f} s   s3 values: {sorted({r["s3"] for r in good})}')
        print(f'  mean visible contact columns: {np.mean([r["columns_contact_in_image"] for r in good]):.1f}')
    else:
        print('  none: the own wrist camera never sees a wall base in this episode')
    cam_z = sorted({r['cam_z'] for r in rows_out})
    print(f'camera heights present: {cam_z[:5]} ... ({len(cam_z)} distinct)')


if __name__ == '__main__':
    main()