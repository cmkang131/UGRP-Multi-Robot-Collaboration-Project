"""Diagnostic: expected ground-truth wall rows vs what the detector accepted.

Read-only. No writes into the episode. Ground truth is used here only to *look at* the
comparison; nothing it returns feeds the detector.
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


def bearing_to_row(cm, cols, bearing, rng):
    """Row of the floor point at (range from nadir, bearing) in the nearest column."""
    best, best_err = None, 1e9
    for j, u in enumerate(cols):
        r0, b0 = hfw.column_range_bearing(cm, j, 0.)
        r1, b1 = hfw.column_range_bearing(cm, j, 1.)
        d = b1 - b0
        if abs(d) < 1e-12:
            continue
        s = (bearing - b0)/d
        if s < 0:
            continue
        r_here = r0 + s*(r1 - r0)
        err = abs(r_here - rng)
        if err < best_err:
            best_err, best = err, (u, j, s)
    if best is None:
        return None
    u, j, s = best
    row = cm.rows(np.asarray([s]), np.asarray([0.]))
    return int(u), int(j), float(np.asarray(row).ravel()[0]), best_err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--episode', required=True)
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--frame', type=int, default=1, help='index into frames.jsonl')
    ap.add_argument('--cols', default='0,24', help='column-index range to print')
    ap.add_argument('--load-rule', choices=('s3', 'gripper'), default='s3',
                    help='own load state: s3 = the earlier servo[3] >= 900 (default), gripper = commanded gripper closed')
    args = ap.parse_args()
    rp.set_load_rule(args.load_rule)
    j_lo, j_hi = (int(x) for x in args.cols.split(','))

    ep = Path(args.episode)
    static_map = json.loads((ep/'inputs'/'static_map.json').read_text())
    rects = rp.wall_rects(static_map)
    traj = [json.loads(l) for l in (ep/'eval_only'/'trajectory.jsonl').read_text().splitlines() if l.strip()]
    qa, _ = rp.free_joint_qaddr(ep/'scene.xml', f'{args.robot}__base_free')
    frames, _ = rp.resolve_frames(ep, args.robot)
    t_of_frame = [float(r['sim_time']) for r in frames]
    poses = [(float(x['qpos'][qa]), float(x['qpos'][qa + 1]), rp.yaw_from_quat(x['qpos'][qa + 3:qa + 7]))
             for x in traj]

    row = frames[args.frame]
    t = float(row['sim_time'])
    i = min(max(int(np.searchsorted(t_of_frame, t)), 0), len(poses) - 1)
    px, py, yaw = poses[i]
    servo = {int(k): int(v) for k, v in row['commanded_servo'].items()}
    bgr = cv2.imread(str(ep/row['path']), cv2.IMREAD_COLOR)
    und = mp.undistort(bgr)
    loaded = rp.loaded_for(servo, legacy_str_key=True)
    b0 = mp.elevation_bias(rp.SEED_BIAS['loaded' if loaded else 'unloaded'], servo)
    cols = mp.column_positions(rp.FROZEN_DETECTOR['columns'], rp.FROZEN_DETECTOR['strip_half_px'])
    cm = mp.column_model(servo, b0, cols)
    cols = np.asarray(cm.columns, int)

    print(f'frame {args.frame}  t={t:.2f}  image={row["path"]}')
    print(f'pose x={px:.3f} y={py:.3f} yaw={math.degrees(yaw):.1f} deg  loaded={loaded} servo={servo}')
    print(f'bias={b0:+.5f} rad   camera origin xyz={np.round(cm.origin, 4).tolist()}')
    print(f'camera height above floor = {cm.origin[2]:.4f} m')
    print()

    print('--- ground truth walls: nearest visible point per wall ---')
    for cx, cy, hx, hy, h in rects:
        # sample the footprint perimeter, keep points facing the robot
        pts = []
        for sx in np.linspace(-hx, hx, 41):
            for sy in (-hy, hy):
                pts.append((cx + sx, cy + sy))
        for sy in np.linspace(-hy, hy, 41):
            for sx in (-hx, hx):
                pts.append((cx + sx, cy + sy))
        best = None
        for (wx, wy) in pts:
            dx, dy = wx - px, wy - py
            rng = math.hypot(dx, dy)
            brg = math.atan2(dy, dx)
            # camera looks along +yaw; keep roughly in front
            if abs((brg - yaw + math.pi) % (2*math.pi) - math.pi) > 1.1:
                continue
            # also require the surface normal to face the robot
            if best is None or rng < best[0]:
                best = (rng, brg, wx, wy)
        if best is None:
            continue
        rng, brg, wx, wy = best
        got = bearing_to_row(cm, cols, brg, rng)
        txt = f'wall c=({cx},{cy}) h={h}  nearest pt=({wx:.2f},{wy:.2f}) rng={rng:.2f} brg={math.degrees(brg):+.1f}'
        if got:
            u, j, rowv, err = got
            txt += f'  -> col u={u} row={rowv:.1f} (fit err {err:.2f} m)'
            txt += f'  t_of_row={float(np.ravel(cm.t_of_row(np.asarray([rowv])))[j]):.3f}'
        print(txt)
    print()

    self_top = rp.self_top_for(und, cm, servo)
    scan = hfw.detect(und, cm, self_top=self_top)
    occ = self_top < hfw.HEIGHT
    span = f'self_top rows {int(self_top[occ].min())}..{int(self_top[occ].max())}' if occ.any() else 'no occluded column'
    print(f'--- height-free detector, columns {j_lo}..{j_hi - 1} ---')
    print(f'self-mask ON (self_mask, undistorted frame, own commanded s3={servo.get(3, 0)}): '
          f'{int(occ.sum())}/{len(self_top)} columns occluded, {span}')
    print(f'{"j":>3} {"col":>4} {"vb":>6} {"vt":>6} {"h":>6} {"t":>6} {"r":>6} {"bear":>7} {"c":>6} {"std":>5}')
    for j in range(j_lo, min(j_hi, len(cols))):
        for k in range(int(hfw.PARAMS['candidates'])):
            vb = scan['vb'][j, k]
            if not np.isfinite(vb):
                continue
            t_here = float(cm.t_of_row(np.asarray([vb]))[j])
            r, b = hfw.column_range_bearing(cm, j, t_here)
            vt, h = scan['vt'][j, k], scan['h'][j, k]
            print(f'{j:>3} {cols[j]:>4} {vb:>6.1f} {vt:>6.1f} {h:>6.3f} {t_here:>6.2f} {r:>6.2f} '
                  f'{math.degrees(b):>7.1f} {scan["c"][j, k]:>6.1f} {scan["s"][j, k]:>5.2f}')
    print()
    segs = hfw.link_segments(scan)
    print(f'--- {len(segs)} segments ---')
    for s in segs:
        wx = px + s['range_first_m']*math.cos(s['bearing_first_rad'])
        wy = py + s['range_first_m']*math.sin(s['bearing_first_rad'])
        print(f'cols {s["col_first"]}..{s["col_last"]} ({s["n_columns"]})  r {s["range_first_m"]:.2f}->{s["range_last_m"]:.2f}'
              f'  brg {math.degrees(s["bearing_first_rad"]):+.1f}->{math.degrees(s["bearing_last_rad"]):+.1f}'
              f'  world=({wx:.2f},{wy:.2f})  h={s["height_m"]}'
              f'  wall_dist={rp.dist_to_walls((wx, wy), rects):.2f} m')


if __name__ == '__main__':
    main()