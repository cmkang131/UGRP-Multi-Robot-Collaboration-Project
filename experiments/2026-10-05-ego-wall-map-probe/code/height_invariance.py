"""Does a wall detector survive having NO wall height? (probe, 2026-10-05)

Refs #216. **Physical simulation runs: 0.** Re-renders recorded frames at three
wall heights with ``replay_render`` (mj_forward only) and runs the height-free
detector on each. If wall height is truly an OUTPUT, the reported contact row
and range must not move when the rendered wall height changes under it.

    step 1  coverage gate  -- pick frames whose floor ray actually meets a wall
                              base inside the image (``coverage.ray_rect``)
    step 2  main table     -- contact row / range / h / h_lb per true height
    step 3  frozen contrast-- ``markerless_probe.detect_boundaries`` at 0.40 m
    step 4  height output  -- measured h and h_lb against the true height

GROUND TRUTH SEPARATION.  ``gt_contact_rows`` is computed from the static map and
is used ONLY to score. It is never passed to ``height_free_wall.detect`` and never
reaches it: :func:`run_frame` builds the detector's inputs (undistorted RGB, the
commanded servo, the fixed calibration) and calls ``detect`` on those alone. The
detector sees exactly what the robot would see.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE.parents[2] / 'experiments/2026-09-26-markerless-probe'))

import height_free_wall as hfw        # noqa: E402
import markerless_probe as mp         # noqa: E402
import replay_render as rr            # noqa: E402
import wall_probe as rp               # noqa: E402
from coverage import MAX_RANGE_M, ray_rect   # noqa: E402

OUT_ROOT = rr.DEFAULT_OUTPUTS_ROOT / 'height_invariance'
HEIGHTS = (0.10, 0.40, 0.50)


def camera_model(servo, bias_mode):
    """The frozen VIS3 column model for one frame. Robot-side inputs only."""
    loaded = rp.is_loaded(servo)
    key = 'auto' if bias_mode == 'auto' else bias_mode
    b0 = mp.elevation_bias(rp.SEED_BIAS[key if key != 'auto'
                                    else ('loaded' if loaded else 'unloaded')], servo)
    return mp.column_model(servo, b0, COLS), b0, loaded


COLS = None    # set in main(); the module-level cache key is the column tuple


def gt_contact_rows(cm, rects):
    """SCORING ONLY. Per column: (trace distance, GT contact row, GT range).

    Where the column's floor ray meets a wall footprint and the contact lands
    inside the image. Never passed to the detector.
    """
    t_hit = np.full(len(cm.columns), np.nan)
    row = np.full(len(cm.columns), np.nan)
    rng = np.full(len(cm.columns), np.nan)
    for j in range(len(cm.columns)):
        t = ray_rect(cm, j, rects, MAX_RANGE_M)
        if t is None:
            continue
        r = float(np.ravel(cm.rows(np.asarray([t]), np.asarray([0.])))[0])
        if np.isfinite(r) and 0 <= r <= mp.HEIGHT - 1:
            t_hit[j] = t
            row[j] = r
            rng[j] = hfw.column_range_bearing(cm, j, t)[0]
    return t_hit, row, rng


def gt_wall_top_rows(cm, rects, t_hit, height):
    """SCORING ONLY. Row of the top edge of a wall of ``height``, per column.

    Used to name WHICH edge a detection locked onto -- not to detect anything.
    """
    out = np.full(len(cm.columns), np.nan)
    for j in range(len(cm.columns)):
        if not np.isfinite(t_hit[j]):
            continue
        v = float(np.ravel(cm.rows_at(np.asarray([t_hit[j]]), height))[0])
        if np.isfinite(v) and 0 <= v <= mp.HEIGHT - 1:
            out[j] = v
    return out


def coverage_gate(ep, robot, stride, min_cols):
    """Frames whose own camera sees a wall base in the image, and how many columns."""
    rects = rp.wall_rects(json.loads((ep / 'inputs' / 'static_map.json').read_text()))
    frames, _ = rp.resolve_frames(ep, robot)
    out = []
    for idx in range(0, len(frames), max(1, stride)):
        servo = {int(k): int(v) for k, v in frames[idx]['commanded_servo'].items()}
        cm, _, _ = camera_model(servo, 'auto')
        _, row, _ = gt_contact_rows(cm, rects)
        n = int(np.isfinite(row).sum())
        if n >= min_cols:
            out.append({'i': idx, 't': round(float(frames[idx]['sim_time']), 2),
                        's3': int(servo.get(3, 0)), 'n_cols': n})
    return out


def select_frames(cands, want):
    """Spread the selection across commanded shoulder poses, best frame per pose.

    One frame per distinct servo-3 keeps the arm pose from being confounded with
    wall height; within a pose the frame with the most visible contact columns
    carries the most signal.
    """
    best = {}
    for c in cands:
        if c['s3'] not in best or c['n_cols'] > best[c['s3']]['n_cols']:
            best[c['s3']] = c
    picked = sorted(best.values(), key=lambda c: c['i'])
    return picked[:want] if want else picked


def render(models, rends, step, camera, height, fisheye):
    """Render one recorded state at one wall height. mj_forward only; no physics."""
    m = models[height]
    d = mujoco.MjData(m)
    d.qpos[:] = np.asarray(step['qpos'], float)
    d.qvel[:] = np.asarray(step['qvel'], float)
    d.time = float(step['t'])
    mujoco.mj_forward(m, d)          # no mj_step: see replay_render.WHY_NO_STEP
    return rr.render_robot_cam(*rends[height], m, d, camera, fisheye)


def run_frame(ep, idx, models, rends, fisheye, camera, rects, bias_mode, out_dir, robot):
    """One frame at every height: detector outputs, ground truth, frozen detector.

    Returns a per-frame dict. Ground truth enters only the ``gt_*`` keys.
    """
    traj, frames, _, ep = rr.load_episode(ep, robot)
    row = frames[idx]
    step = traj[idx]
    servo = {int(k): int(v) for k, v in row['commanded_servo'].items()}
    cm, bias, loaded = camera_model(servo, bias_mode)

    t_hit, gt_row, gt_rng = gt_contact_rows(cm, rects)          # scoring only
    rec = {'frame': idx, 't': round(float(row['sim_time']), 2), 's3': int(servo.get(3, 0)),
           'loaded': loaded, 'bias_rad': round(bias, 5),
           'gt_cols': int(np.isfinite(gt_row).sum()), 'by_height': {}}

    for height in sorted(models):
        rgb = render(models, rends, step, camera, height, fisheye)
        path = out_dir / f'{robot}_{idx:05d}_h{height:.3f}.jpg'
        path.write_bytes(rr.encode_jpeg(rgb, 82))          # never into the repo
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
        und = mp.undistort(bgr)

        # The detector's own inputs and nothing else: RGB, own servo, calibration.
        # self_top=None makes it compute its own carried-object mask; we compute
        # the same mask once so the frozen detector gets an identical one and the
        # comparison isolates the height prior.
        self_top = hfw.self_top_mask(und, cm, loaded=loaded)
        scan = hfw.detect(und, cm, self_top=self_top)       # <-- NO ground truth
        frozen = mp.detect_boundaries(und, cm, rp.FROZEN_DETECTOR, self_top)

        vb = scan['vb'][:, 0]
        gt_top = gt_wall_top_rows(cm, rects, t_hit, height)  # scoring only
        matched = np.isfinite(vb) & np.isfinite(gt_row)
        entry = {
            'true_h': height,
            'n_det': int(np.isfinite(vb).sum()),
            'frozen_det': int(frozen.detected.sum()),
            'vb_med': None, 'r_med': None, 'h_med': None, 'h_lb_med': None,
            'err_contact_med': None, 'err_walltop_med': None, 'r_err_med': None,
            'vb': None, 'r': None, 'h': None, 'h_lb': None,
        }
        if np.isfinite(vb).any():
            entry['vb_med'] = round(float(np.nanmedian(vb)), 1)
            entry['r_med'] = round(float(np.nanmedian(scan['r'][:, 0])), 3)
            entry['vb'] = np.round(vb, 1).tolist()
            entry['r'] = np.round(scan['r'][:, 0], 3).tolist()
            entry['h'] = np.round(scan['h'][:, 0], 3).tolist()
            entry['h_lb'] = np.round(scan['h_lb'][:, 0], 3).tolist()
            hv = scan['h'][:, 0][np.isfinite(scan['h'][:, 0])]
            lb = scan['h_lb'][:, 0][np.isfinite(scan['h_lb'][:, 0])]
            entry['h_med'] = round(float(np.median(hv)), 3) if hv.size else None
            entry['h_lb_med'] = round(float(np.median(lb)), 3) if lb.size else None
        if matched.any():
            entry['err_contact_med'] = round(float(np.nanmedian(np.abs(vb - gt_row)[matched])), 1)
            entry['r_err_med'] = round(float(np.nanmedian(
                np.abs(scan['r'][:, 0] - gt_rng)[matched])), 3)
            mt = matched & np.isfinite(gt_top)
            if mt.any():
                entry['err_walltop_med'] = round(
                    float(np.nanmedian(np.abs(vb - gt_top)[mt])), 1)
        rec['by_height'][f'{height:.2f}'] = entry
    rec['gt_row'] = np.round(gt_row, 1).tolist()
    rec['gt_range'] = np.round(gt_rng, 3).tolist()
    return rec


def spread(per_frame, key, lo, hi):
    """Headline: per-column spread of ``key`` across the three true heights.

    Only columns the detector reports at EVERY height are compared, so the
    number is a real disagreement and not a detection-count difference.
    """
    d = []
    for rec in per_frame:
        raw = [rec['by_height'][f'{h:.2f}'][key] for h in (lo, 0.40, hi)]
        if any(v is None for v in raw):      # frame detected nothing at some height
            continue
        arrs = [np.asarray(v, float) for v in raw]
        ok = np.logical_and.reduce([np.isfinite(a) for a in arrs])
        if ok.any():
            d.extend((np.ptp(np.stack([a[ok] for a in arrs]), axis=0)).tolist())
    return np.asarray(d, float)


def main():
    global COLS
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--episode', required=True)
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--frames', default=None,
                    help='comma-separated frame indices, or "auto" to run the coverage gate')
    ap.add_argument('--heights', default=','.join(f'{h:.2f}' for h in HEIGHTS))
    ap.add_argument('--bias', default='auto', choices=('auto', 'loaded', 'unloaded'),
                    help='which SEED_BIAS table builds the camera model')
    ap.add_argument('--stride', type=int, default=8, help='coverage gate stride')
    ap.add_argument('--min-cols', type=int, default=8, help='min visible contact columns')
    ap.add_argument('--n-frames', type=int, default=0, help='0 = one per distinct servo-3')
    ap.add_argument('--out', default=str(OUT_ROOT))
    args = ap.parse_args()

    ep = Path(args.episode).expanduser().resolve()
    out_dir = rr.check_output_dir(args.out, False)
    img_dir = out_dir / args.robot
    img_dir.mkdir(parents=True, exist_ok=True)
    heights = tuple(float(x) for x in args.heights.split(','))
    COLS = mp.column_positions(rp.FROZEN_DETECTOR['columns'], rp.FROZEN_DETECTOR['strip_half_px'])

    rects = rp.wall_rects(json.loads((ep / 'inputs' / 'static_map.json').read_text()))

    # --- step 1: the gate -----------------------------------------------------
    if args.frames == 'auto':
        cands = coverage_gate(ep, args.robot, args.stride, args.min_cols)
        picked = select_frames(cands, args.n_frames)
        idxs = [c['i'] for c in picked]
    else:
        idxs = [int(x) for x in args.frames.split(',')]
        picked = []
    print(f'episode {ep}\nrobot {args.robot}  bias={args.bias}  heights={heights}')
    print(f'selected {len(idxs)} frames: {idxs}')
    if picked:
        print(f'{"frame":>6} {"t":>7} {"s3":>5} {"visible contact cols":>21}')
        for c in picked:
            print(f'{c["i"]:>6} {c["t"]:>7} {c["s3"]:>5} {c["n_cols"]:>21}')
    print()

    traj, _, _, ep = rr.load_episode(ep, args.robot)
    fisheye = rr.raw_fisheye_remap(mp.WIDTH, mp.HEIGHT)
    camera = f'{args.robot}__robot_cam'
    models = {h: mujoco.MjModel.from_xml_string(rr.scene_with_wall_height(
        ep / 'scene.xml', ep / 'inputs' / 'static_map.json', h)) for h in heights}
    rends = {h: rr.make_renderer(m, mp.WIDTH, mp.HEIGHT) for h, m in models.items()}

    per_frame = [run_frame(ep, i, models, rends, fisheye, camera, rects,
                           args.bias, img_dir, args.robot) for i in idxs]
    for r in rends.values():
        r[0].close()

    # --- step 2: the main table ----------------------------------------------
    hdr = f'{"frame":>5} {"h":>5} {"n":>4} {"vb":>7} {"GTrow":>7} {"r":>6} {"GTr":>6} ' \
          f'{"h_med":>6} {"h_lb":>6} {"frozen":>6}'
    print('=== step 2: main table (vb/r = median over detected columns) ===')
    print(hdr)
    for rec in per_frame:
        gtv = [v for v in rec['gt_row'] if v is not None]
        gtr = [v for v in rec['gt_range'] if v is not None]
        for h in heights:
            e = rec['by_height'][f'{h:.2f}']
            f = lambda x, w, p=1: (f'{x:>{w}.{p}f}' if x is not None else ' ' * w)
            print(f'{rec["frame"]:>5} {h:>5.2f} {e["n_det"]:>4} {f(e["vb_med"], 7)} '
                  f'{f(round(float(np.median(gtv)), 1) if gtv else None, 7)} '
                  f'{f(e["r_med"], 6, 3)} {f(round(float(np.median(gtr)), 3) if gtr else None, 6, 3)} '
                  f'{f(e["h_med"], 6, 3)} {f(e["h_lb_med"], 6, 3)} {e["frozen_det"]:>6}')
    print()

    # --- headline -------------------------------------------------------------
    vb_sp = spread(per_frame, 'vb', heights[0], heights[-1])
    r_sp = spread(per_frame, 'r', heights[0], heights[-1])
    print('=== HEADLINE: per-column spread across the three true heights ===')
    for name, a, unit in (('contact row', vb_sp, 'px'), ('range', r_sp, 'm')):
        if a.size:
            print(f'{name:>12}: median {np.median(a):.3f} {unit}   max {a.max():.3f} {unit}   '
                  f'(n={a.size} columns detected at every height; p90 {np.percentile(a, 90):.3f})')
        else:
            print(f'{name:>12}: no column detected at every height')
    print('  (target: 0-2 px for the contact row; the requirement was 0-2)')
    print()

    # --- step 3: frozen contrast ---------------------------------------------
    print('=== step 3: frozen 0.40 m detector vs height-free ===')
    print(f'{"true h":>7} {"frozen contacts":>16} {"height-free contacts":>22} '
          f'{"frozen frames>0":>16} {"free frames>0":>14}')
    for h in heights:
        fz = sum(rec['by_height'][f'{h:.2f}']['frozen_det'] for rec in per_frame)
        fr = sum(rec['by_height'][f'{h:.2f}']['n_det'] for rec in per_frame)
        nfz = sum(rec['by_height'][f'{h:.2f}']['frozen_det'] > 0 for rec in per_frame)
        nfr = sum(rec['by_height'][f'{h:.2f}']['n_det'] > 0 for rec in per_frame)
        print(f'{h:>7.2f} {fz:>16} {fr:>22} {nfz:>16} {nfr:>14}')
    print()

    # --- step 4: height as an output -----------------------------------------
    print('=== step 4: measured height as an OUTPUT ===')
    print(f'{"true h":>7} {"median h":>9} {"median h_lb":>12} {"n h":>5} {"n h_lb":>7}')
    for h in heights:
        hv = [rec['by_height'][f'{h:.2f}']['h_med'] for rec in per_frame
              if rec['by_height'][f'{h:.2f}']['h_med'] is not None]
        lb = [rec['by_height'][f'{h:.2f}']['h_lb_med'] for rec in per_frame
              if rec['by_height'][f'{h:.2f}']['h_lb_med'] is not None]
        print(f'{h:>7.2f} {(f"{np.median(hv):>9.3f}" if hv else "        -")} '
              f'{(f"{np.median(lb):>12.3f}" if lb else "           -")} '
              f'{len(hv):>5} {len(lb):>7}')
    print()

    print('=== absolute accuracy vs ground truth (calibration debt is NOT a spread) ===')
    print(f'{"true h":>7} {"median |vb-GTcontact|":>22} {"median |r-GTrange|":>18} '
          f'{"median |vb-GTwallTOP|":>20}')
    for h in heights:
        e = [rec['by_height'][f'{h:.2f}'] for rec in per_frame]
        ec = [x['err_contact_med'] for x in e if x['err_contact_med'] is not None]
        er = [x['r_err_med'] for x in e if x['r_err_med'] is not None]
        et = [x['err_walltop_med'] for x in e if x['err_walltop_med'] is not None]
        print(f'{h:>7.2f} {(f"{np.median(ec):>22.1f}" if ec else "                      -")} '
              f'{(f"{np.median(er):>18.3f}" if er else "                  -")} '
              f'{(f"{np.median(et):>20.1f}" if et else "                    -")}')
    print()

    summary = {'episode': str(ep), 'robot': args.robot, 'bias': args.bias,
               'frames': idxs, 'heights': list(heights),
               'contact_row_spread_px': {'median': float(np.median(vb_sp)) if vb_sp.size else None,
                                         'max': float(vb_sp.max()) if vb_sp.size else None},
               'range_spread_m': {'median': float(np.median(r_sp)) if r_sp.size else None,
                                  'max': float(r_sp.max()) if r_sp.size else None},
               'per_frame': per_frame,
               'gt_use': 'scoring only; detect() receives RGB + own servo + calibration'}
    (out_dir / f'summary_{args.robot}_{args.bias}.json').write_text(json.dumps(summary, indent=1))
    print(f'wrote {out_dir / f"summary_{args.robot}_{args.bias}.json"}')
    print(f'images {img_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())