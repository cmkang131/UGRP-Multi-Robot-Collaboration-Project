"""Separate the cause of the systematic wall-contact row bias (offline, no physics).

Refs #216. **Physical simulation runs: 0** (``mj_forward`` / ``mj_ray`` on recorded qpos only,
no ``mj_step``). Reads the recorded episode read-only, writes under ``--output``.

``score_harness.py`` (legacy scoring) reported the detector's contact row +15.3 px below ground
truth and its range 0.46 m short. Three suspects:

  (a) the detector picks a row below the true floor/wall boundary
  (b) the camera the detector assumes (FK of the commanded pulses + fixed elevation bias)
      differs from the camera MuJoCo actually rendered from
  (c) the scoring geometry is wrong (frame origin, trace construction)

Reference that needs no camera model, no pose and no detector: a **segmentation render** of the
recorded state through the same ``<robot>__robot_cam``. The lowest wall pixel of each detector
column strip is the true floor/wall boundary row of the (ideal pinhole == undistorted) image.
The true range comes from an ``mj_ray`` through that pixel.

Per visible frame and detector column this script reports, against that reference:

  det_row          the detector's ``vb`` on the undistorted recorded JPEG (arm (a))
  gt_row[V0..V4]   ground-truth row under five scoring constructions (arms (b), (c)):
                     V0 legacy: model camera with the legacy load rule ``servo[3] >= 900``
                     V1 + load state from the own gripper command
                     V2 + chassis -> arm-base-axis frame offset in the map transform
                     V3 + exact column floor trace (instead of nadir ray minus along-ray offset)
                     V4 true rendered camera + exact trace (what ``score_harness`` now uses)
  gt_range[V0..V4] the matching ground-truth ranges, against ``mj_ray``

and, per frame, the true camera pose against the model camera pose from the commanded servo.

GROUND TRUTH IS SCORING/DIAGNOSIS ONLY. Nothing computed here reaches a detector input.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import cv2
import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-26-markerless-probe'))
sys.path.insert(0, str(HERE))

import markerless_probe as mp  # noqa: E402
import height_free_wall as hfw  # noqa: E402
import wall_probe as wp  # noqa: E402
import score_harness as sh  # noqa: E402
import true_camera as tc  # noqa: E402

HIDDEN_GEOM_GROUPS = (4, 5)
WALL_PREFIX = 'zone_wall_'
VARIANTS = ('V0', 'V1', 'V2', 'V3', 'V4')


def seg_boundary_rows(seg_ids, cols, half, wall_ids):
    """Lowest wall pixel row of every detector strip (all strip columns wall at that row)."""
    wall = np.isin(seg_ids, list(wall_ids))
    out = np.full(len(cols), np.nan)
    for j, c in enumerate(cols):
        rows = np.flatnonzero(wall[:, max(c - half, 0):c + half + 1].all(axis=1))
        if rows.size:
            out[j] = rows.max()
    return out


def mj_wall_range(model, data, cam_xpos, axes_w, cols, rows, wall_ids):
    """Horizontal distance from the camera nadir to the wall face hit by the pixel ray (u, v)."""
    geomgroup = np.array([1, 1, 1, 1, 0, 0], np.uint8)
    out = np.full(len(cols), np.nan)
    gid = np.zeros(1, np.int32)
    for j, (u, v) in enumerate(zip(cols, rows)):
        if not np.isfinite(v):
            continue
        d_cam = mp.K_INV @ np.array([float(u), float(v), 1.])
        d_w = axes_w @ d_cam
        d_w /= np.linalg.norm(d_w)
        dist = mujoco.mj_ray(model, data, cam_xpos, d_w, geomgroup, 1, -1, gid)
        if dist >= 0 and int(gid[0]) in wall_ids:
            hit = cam_xpos + dist*d_w
            out[j] = math.hypot(hit[0] - cam_xpos[0], hit[1] - cam_xpos[1])
    return out


def _q(a):
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    return {'n': int(a.size), 'median': float(np.median(a)), 'p10': float(np.percentile(a, 10)),
            'p90': float(np.percentile(a, 90))} if a.size else {'n': 0}


def summarize(col_rows, pose_rows):
    """Medians (p10, p90) over columns / frames. Row differences are in pixels, ranges in metres.

    ``*_minus_seg`` are against the segmentation-render boundary (the reference). A detector row is
    ``vb`` (first row below the wall); the reference edge is the lowest wall pixel + 0.5.
    """
    g = lambda k: np.array([r[k] for r in col_rows], float)
    seg, mj = g('seg_row'), g('mj_range')
    out = {'columns': len(col_rows), 'frames': len(pose_rows), 'row_px_minus_seg_render': {}, 'range_m_minus_mj_ray': {}}
    for k in ('det_row_old', 'det_row_new'):
        d = g(k) - seg
        out['row_px_minus_seg_render'][k] = _q(d)
        out['row_px_minus_seg_render'][k + '_within_1px_share'] = float(np.mean(np.abs(d[np.isfinite(d)]) <= 1.))
    for v in VARIANTS:
        out['row_px_minus_seg_render']['gt_row_' + v] = _q(g('gt_row_' + v) - seg)
        out['range_m_minus_mj_ray']['gt_range_' + v] = _q(g('gt_range_' + v) - mj)
    out['range_m_minus_mj_ray']['det_range_old'] = _q(g('det_range_old') - mj)
    out['range_m_minus_mj_ray']['det_range_new'] = _q(g('det_range_new') - mj)
    h = lambda k: np.array([r[k] for r in pose_rows], float)
    out['camera'] = {
        'elev_true_deg': _q(h('elev_true_deg')),
        'detector_legacy_minus_true_deg': _q(h('elev_detector_legacy_deg') - h('elev_true_deg')),
        'detector_fixed_minus_true_deg': _q(h('elev_detector_fixed_deg') - h('elev_true_deg')),
        'fk_nobias_minus_true_deg': _q(h('elev_fk_nobias_deg') - h('elev_true_deg')),
        'z_model_minus_true_m': _q(h('z_model') - h('z_true')),
        'x_true_minus_model_m': _q(h('x_true_minus_model')),
        'y_true_minus_model_m': _q(h('y_true_minus_model')),
        'frames_loaded_legacy_rule': int(h('loaded_legacy_rule').sum()),
        'frames_loaded_gripper_rule': int(h('loaded_gripper_rule').sum()),
        'bias_legacy_deg': _q(h('bias_legacy_deg')), 'bias_fixed_deg': _q(h('bias_fixed_deg')),
    }
    return out


def run(args):
    ep = Path(args.episode)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    static_map = json.loads((ep/'inputs'/'static_map.json').read_text())
    rects = wp.wall_rects(static_map)
    frames, _ = wp.resolve_frames(ep, args.robot)
    cam = tc.TrueCamera(ep, args.robot)
    model, data = cam.model, cam.data
    wall_ids = {i for i in range(model.ngeom)
                if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) or '').startswith(WALL_PREFIX)}
    renderer = mujoco.Renderer(model, height=mp.HEIGHT, width=mp.WIDTH)
    opt = mujoco.MjvOption()
    opt.geomgroup[:] = 1
    for g in HIDDEN_GEOM_GROUPS:
        opt.geomgroup[g] = 0

    cols = mp.column_positions(wp.FROZEN_DETECTOR['columns'], wp.FROZEN_DETECTOR['strip_half_px'])
    half = int(wp.FROZEN_DETECTOR['strip_half_px'])
    max_range = args.max_range_m
    det_params = json.loads(args.detector_params) if args.detector_params else None

    per = list(csv.DictReader(open(args.per_frame)))
    sel = [r for r in per if r['visible_frame'] == 'True']
    if args.limit:
        sel = sel[::max(1, len(sel)//args.limit)][:args.limit]

    pose_rows, col_rows = [], []
    for r in sel:
        idx = int(r['frame_index']) - 1
        servo = {int(k): int(v) for k, v in frames[idx]['commanded_servo'].items()}
        loaded_old = servo.get(3, 0) >= 900
        loaded_new = wp.is_loaded(servo)
        bias_old = wp.SEED_BIAS['loaded' if loaded_old else 'unloaded']
        bias_new = wp.SEED_BIAS['loaded' if loaded_new else 'unloaded']

        # ---- true render geometry (reference) -------------------------------------------------
        o_true, ax_true, pose = cam.at(idx)
        axes_w_true = np.asarray(data.cam_xmat[cam.cam_id]).reshape(3, 3)
        axes_w = np.stack([axes_w_true[:, 0], -axes_w_true[:, 1], -axes_w_true[:, 2]], axis=1)
        cam_xpos = data.cam_xpos[cam.cam_id].copy()
        renderer.enable_segmentation_rendering()
        renderer.update_scene(data, camera=cam.cam_id, scene_option=opt)
        seg = renderer.render().copy()
        renderer.disable_segmentation_rendering()
        seg_row = seg_boundary_rows(seg[..., 0], cols, half, wall_ids)
        seg_edge = seg_row + 0.5                      # boundary between the last wall pixel and the next
        mj_rng = mj_wall_range(model, data, cam_xpos, axes_w, cols, seg_row, wall_ids)

        # ---- the detector's camera model ----------------------------------------------------------
        o_nom, r_nom = mp.camera_in_base(servo)
        el_true = tc.elevation_deg(ax_true)
        el_nom = tc.elevation_deg(np.asarray(r_nom, float))
        rot_new = np.asarray(r_nom, float) @ mp.bias_rotation(bias_new).T
        el_det_new = tc.elevation_deg(rot_new)
        rot_old = np.asarray(r_nom, float) @ mp.bias_rotation(bias_old).T
        el_det_old = tc.elevation_deg(rot_old)

        # ---- ground truth under the five constructions --------------------------------------------
        cm_old = mp.column_model(servo, bias_old, cols)
        cm_new = mp.column_model(servo, bias_new, cols)
        cm_true, pose_true = cam.column_model(idx, cols)
        x, y, yaw = pose
        a = cam.arm_base_x_m
        pose_arm = (x + a*math.cos(yaw), y + a*math.sin(yaw), yaw)
        gt = {}
        gt['V0'] = sh.ground_truth(cm_old, rects, sh.world_trace(cm_old, pose), max_range, exact=False)
        gt['V1'] = sh.ground_truth(cm_new, rects, sh.world_trace(cm_new, pose), max_range, exact=False)
        gt['V2'] = sh.ground_truth(cm_new, rects, sh.world_trace(cm_new, pose_arm), max_range, exact=False)
        gt['V3'] = sh.ground_truth(cm_new, rects, sh.world_trace(cm_new, pose_arm), max_range, exact=True)
        gt['V4'] = sh.ground_truth(cm_true, rects, sh.world_trace(cm_true, pose_true), max_range, exact=True)

        # ---- detector on the recorded image, both load rules ------------------------------------------
        bgr = cv2.imread(str(ep/frames[idx]['path']), cv2.IMREAD_COLOR)
        und = mp.undistort(bgr)
        full = np.full(len(cols), hfw.HEIGHT, int)
        det_old = hfw.detect(und, cm_old, params=det_params, self_top=full, loaded=loaded_old)
        det_new = hfw.detect(und, cm_new, params=det_params, self_top=full, loaded=loaded_new)

        for j in range(len(cols)):
            if not np.isfinite(seg_row[j]):
                continue
            rec = {'frame_index': int(r['frame_index']), 'col': int(cols[j]), 's1': servo.get(1, 0),
                   's3': servo.get(3, 0), 'seg_row': float(seg_edge[j]), 'mj_range': float(mj_rng[j]),
                   'det_row_old': float(det_old['vb'][j, 0]), 'det_range_old': float(det_old['r'][j, 0]),
                   'det_row_new': float(det_new['vb'][j, 0]), 'det_range_new': float(det_new['r'][j, 0])}
            for v in VARIANTS:
                vis, row, rng, _ = gt[v]
                rec[f'gt_row_{v}'] = float(row[j]) if vis[j] else float('nan')
                rec[f'gt_range_{v}'] = float(rng[j]) if vis[j] else float('nan')
            col_rows.append(rec)

        pose_rows.append({
            'frame_index': int(r['frame_index']), 's1': servo.get(1, 0), 's3': servo.get(3, 0),
            'loaded_legacy_rule': int(loaded_old), 'loaded_gripper_rule': int(loaded_new),
            'z_true': float(o_true[2]), 'z_model': float(o_nom[2]),
            'x_true_minus_model': float(o_true[0] - o_nom[0]), 'y_true_minus_model': float(o_true[1] - o_nom[1]),
            'elev_true_deg': el_true, 'elev_fk_nobias_deg': el_nom,
            'elev_detector_legacy_deg': el_det_old, 'elev_detector_fixed_deg': el_det_new,
            'bias_legacy_deg': math.degrees(bias_old), 'bias_fixed_deg': math.degrees(bias_new)})

    renderer.close()
    with open(out/'pose_compare.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(pose_rows[0].keys()))
        w.writeheader(); w.writerows(pose_rows)
    with open(out/'column_rows.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(col_rows[0].keys()))
        w.writeheader(); w.writerows(col_rows)
    (out/'meta.json').write_text(json.dumps({
        'episode': str(ep), 'robot': args.robot, 'frames': len(pose_rows), 'columns': len(col_rows),
        'arm_base_x_m': cam.arm_base_x_m, 'per_frame_source': str(args.per_frame),
        'detector_params_override': det_params, 'seg_edge': 'lowest wall pixel row + 0.5', 'mj_range': 'mj_ray through (column, lowest wall pixel row)',
    }, indent=2))
    summary = summarize(col_rows, pose_rows)
    (out/'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print(f'{len(pose_rows)} frames, {len(col_rows)} columns -> {out}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--episode', required=True)
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--per-frame', required=True, help='per_frame.csv of a score_harness run (visible-frame list)')
    ap.add_argument('--output', required=True)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--max-range-m', type=float, default=6.)
    ap.add_argument('--detector-params', default='', help='JSON overrides of height_free_wall.PARAMS')
    run(ap.parse_args())
