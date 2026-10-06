"""Wall faces as the ego map records them, scored against the true walls (step 0 and stage C). Refs #216.

**Physical simulation runs: 0.** Replays a recorded episode: own undistorted frames -> ``height_free_wall`` ->
``ego_wall_map`` records (chassis frame). The ground truth (``static_map.json`` walls, the recorded chassis pose, the
true rendered camera) is read only in this file's scoring branches and never reaches the detector or the recorder; the
two call sites that build detector inputs are marked ``# DETECTOR: ground truth free``.

What is scored is the map content, not the per-column contacts ``score_harness.py`` scores: for each wall face the
chord between its two recorded end points (chassis frame at ``t_sim``) is carried to the map frame with the TRUE pose and
compared with the wall footprints.

  segment correct   median over 9 chord samples of the distance to the nearest wall footprint boundary <= ``--tol-m``
                    (default 0.15 m; 0.10 and 0.25 also reported)
  position error    that median distance, over correct segments (m); orientation error against the nearest map axis
                    (the walls are axis aligned), segments >= 0.3 m long
  GT face           a run of >= ``min_run_columns`` adjacent ground-truth-visible columns hitting one wall; it is FOUND
                    when >= 50 % of its columns lie inside the column span of a correct segment
  false segment     any segment that is not correct; reported separately for frames in which no wall is visible
  by range          the same, in range bands of the segment's mean range from the chassis origin
  map coverage      of the wall boundary cells (0.1 m) that the true camera sees in some frame, the share within ``tol-m``
                    of a correct recorded segment

``--gate none`` scores every frame (step 0: the detector as it is). ``--gate settle`` records only settled observations
(``ego_wall_map.SETTLE_S``) and writes the map to ``--output/ego_map.jsonl`` (stage C).

Options passed through to the detector, all default off: ``--load-rule``, ``--detector-params``, ``--sag-comp``.
"""
from __future__ import annotations

import argparse
import csv
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
import coverage as cov  # noqa: E402
import ego_wall_map as ewm  # noqa: E402
import height_free_wall as hfw  # noqa: E402
import score_harness as sh  # noqa: E402
import true_camera as tc  # noqa: E402
import wall_probe as wp  # noqa: E402

TOLS_M = (0.10, 0.15, 0.25)
CELL_M = 0.10
MIN_LEN_FOR_ANGLE_M = 0.30
RANGE_BANDS_M = ((0, 2), (2, 3), (3, 4), (4, 99))    # a row error of dr px moves the range by about R^2/h * dr/FY: it grows as R^2


def sdf_rects(pts, rects):
    """|signed distance| of points (n, 2) to the boundary of each axis-aligned rect (cx, cy, hx, hy, h): (n, m)."""
    r = np.asarray(rects, float)
    q = np.abs(pts[:, None, :] - r[None, :, :2]) - r[None, :, 2:4]
    outside = np.hypot(np.maximum(q[..., 0], 0), np.maximum(q[..., 1], 0))
    inside = np.minimum(np.maximum(q[..., 0], q[..., 1]), 0)
    return np.abs(outside + inside)


def chord_world(rec_seg, pose, n=9):
    """(n, 2) map-frame samples of the chord between the two recorded end points, from the true chassis pose."""
    r1, t1, r2, t2, _ = rec_seg
    p1, p2 = np.array([r1*math.cos(t1), r1*math.sin(t1)]), np.array([r2*math.cos(t2), r2*math.sin(t2)])
    s = np.linspace(0., 1., n)[:, None]
    pts = p1 + (p2 - p1)*s
    px, py, yaw = pose
    c, sn = math.cos(yaw), math.sin(yaw)
    return pts @ np.array([[c, sn], [-sn, c]]) + np.array([px, py]), float(np.linalg.norm(p2 - p1)), p2 - p1


def axis_error_deg(vec, yaw):
    a = math.degrees(math.atan2(vec[1], vec[0]) + yaw) % 90.
    return min(a, 90. - a)


def point_segment_dist(cells, a, b):
    ab = b - a
    den = float(ab @ ab)
    t = np.zeros(len(cells)) if den < 1e-12 else np.clip(((cells - a) @ ab)/den, 0., 1.)
    return np.hypot(*(cells - (a + t[:, None]*ab)).T)


def gt_columns(gt_cm, trace, rects, max_range_m):
    """(visible, row, rect id per column, map-frame contact points (n, 2)). Scoring only."""
    vis, row, _rng, _hit = sh.ground_truth(gt_cm, rects, trace, max_range_m, exact=True)
    n = len(gt_cm.columns)
    rid = np.full(n, -1)
    pts = np.full((n, 2), np.nan)
    for j in np.flatnonzero(vis):
        ts = [sh.first_hit_t(trace.q0[j], trace.d[j], [r]) for r in rects]
        ts = [np.inf if v is None else v for v in ts]
        k = int(np.argmin(ts))
        rid[j] = k
        pts[j] = trace.q0[j] + ts[k]*trace.d[j]
    return vis, row, rid, pts


def gt_faces(vis, rid, min_run):
    """[(first_col, last_col, rect id)]: runs of adjacent visible columns on one wall, >= ``min_run`` long."""
    out, j, n = [], 0, len(vis)
    while j < n:
        if not vis[j]:
            j += 1
            continue
        k = j
        while k + 1 < n and vis[k + 1] and rid[k + 1] == rid[j]:
            k += 1
        if k - j + 1 >= min_run:
            out.append((j, k, int(rid[j])))
        j = k + 1
    return out


def height_by_pose(seg_rows):
    """Per commanded wrist pulse s3: faces, faces with a measured height, and that height's median / p10 / p90 (m).

    The walls of the recorded scene are 0.40 m. Heights come from the run top found in the frame: where the wall top is out
    of the frame (``top_edge_px`` on) or the run is cut at a door edge, it is missing or wrong.
    """
    out = {}
    for s3 in sorted({r['s3'] for r in seg_rows if r['s3'] is not None}):
        rows = [r for r in seg_rows if r['s3'] == s3]
        h = [r['height_m'] for r in rows if r['height_m'] is not None]
        out[str(s3)] = {'faces': len(rows), 'with_height': len(h),
                        'height_median_p10_p90': [round(float(np.median(h)), 3), round(float(np.percentile(h, 10)), 3),
                                                  round(float(np.percentile(h, 90)), 3)] if h else None}
    return out


def run(args):
    ep_dir, out_dir = Path(args.episode), Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    static_map = json.loads((ep_dir/'inputs'/'static_map.json').read_text())
    rects = wp.wall_rects(static_map)                                  # ground truth, scoring only
    frames, frames_rel = wp.resolve_frames(ep_dir, args.robot)
    truecam = tc.TrueCamera(ep_dir, args.robot)
    cols = mp.column_positions(wp.FROZEN_DETECTOR['columns'], wp.FROZEN_DETECTOR['strip_half_px'])
    det_params = json.loads(args.detector_params) if args.detector_params else {}
    min_run = int({**hfw.PARAMS, **det_params}['min_run_columns'])
    emap = ewm.EgoWallMap(enabled=True, settle_s=ewm.SETTLE_S if args.gate == 'settle' else None)
    step = max(1, int(args.every))

    seg_rows, frame_rows, gt_cell_all, gt_cell_settled, correct_chords = [], [], {}, {}, []
    for idx, row in enumerate(frames):
        t = float(row['sim_time'])
        servo = {int(k): int(v) for k, v in row['commanded_servo'].items()}
        loaded = wp.loaded_for(servo, args.load_rule)
        emap.update_command(t, servo)                                  # every tick, not only the scored ones
        if idx % step:
            continue
        bgr = cv2.imread(str(ep_dir/row['path']), cv2.IMREAD_COLOR)
        if bgr is None:
            continue
        held = wp.is_loaded(servo)                                     # own gripper command: the settle class and the record's 'load'
        settled = emap.settled(t, held)

        # ---- ground truth (scoring only) ----------------------------------------------------
        gt_cm, pose = truecam.column_model(idx, cols)
        trace = sh.world_trace(gt_cm, pose)
        vis, _grow, rid, pts = gt_columns(gt_cm, trace, rects, args.max_range_m)
        visible_frame = bool(vis.sum() >= args.min_visible_cols)
        faces = gt_faces(vis, rid, min_run) if visible_frame else []
        for j in np.flatnonzero(vis):
            key = (int(rid[j]), int(math.floor(pts[j, 0]/CELL_M)), int(math.floor(pts[j, 1]/CELL_M)))
            gt_cell_all[key] = pts[j]
            if settled:
                gt_cell_settled[key] = pts[j]

        # ---- detection and record (no ground truth below this line) ----------------------------
        segs, rec = [], None
        if settled:
            und = mp.undistort(bgr)
            cm = mp.column_model(servo, wp.detector_bias(servo, loaded, args.sag_comp), cols)   # DETECTOR: ground truth free
            self_top = sh.mask_on_top(und, cm, loaded)
            scan = hfw.detect(und, cm, params=det_params, self_top=self_top, loaded=loaded)      # DETECTOR: ground truth free
            segs = hfw.link_segments(scan, det_params)
            rec = emap.observe(t, servo, held, cm.origin[:2], segs, int(row.get('frame_id', idx)))

        # ---- scoring only ----------------------------------------------------------------------
        covered = np.zeros(len(cols), bool)
        n_correct = 0
        for k, s in enumerate(segs):
            rs = rec['seg'][k]
            chord, length, vec = chord_world(rs, pose)
            d = sdf_rects(chord, rects)
            near = d.min(0)
            nearest = int(np.argmin(near))
            d_med = float(np.median(d[:, nearest]))
            correct = d_med <= args.tol_m
            ang = axis_error_deg(vec, pose[2]) if length >= MIN_LEN_FOR_ANGLE_M else None
            if correct:
                n_correct += 1
                covered[s['col_first']:s['col_last'] + 1] = True
                correct_chords.append((chord[0], chord[-1]))
            seg_rows.append({'frame_index': int(row.get('frame_id', idx)), 't': round(t, 3), 'loaded': bool(held), 's3': servo.get(3),
                             'visible_frame': visible_frame, 'n_columns': s['n_columns'], 'length_m': round(length, 3),
                             'd_med_m': round(d_med, 4), 'd_max_m': round(float(d[:, nearest].max()), 4),
                             'nearest_wall': nearest, 'axis_err_deg': None if ang is None else round(ang, 2),
                             'correct': bool(correct), 'correct_010': d_med <= 0.10, 'correct_025': d_med <= 0.25,
                             'height_m': s['height_m'], 'range_m': round((rs[0] + rs[2])/2, 3)})
        found = [bool(covered[a:b + 1].mean() >= 0.5) for a, b, _ in faces]
        frame_rows.append({'frame_index': int(row.get('frame_id', idx)), 't': round(t, 3), 'loaded': bool(held),
                           'settled': settled, 'visible_frame': visible_frame, 'gt_faces': len(faces),
                           'gt_faces_found': int(sum(found)), 'segments': len(segs), 'segments_correct': n_correct})

    # ---- aggregate ------------------------------------------------------------------------------
    def share(a, b):
        return round(a/b, 4) if b else None

    def seg_stats(rows):
        c = [r for r in rows if r['correct']]
        return {'segments': len(rows), 'correct': len(c), 'correct_share': share(len(c), len(rows)),
                'correct_share_tol_0.10': share(sum(r['correct_010'] for r in rows), len(rows)),
                'correct_share_tol_0.25': share(sum(r['correct_025'] for r in rows), len(rows)),
                'position_error_m_median_p90': [round(float(np.median([r['d_med_m'] for r in c])), 4),
                                                round(float(np.percentile([r['d_med_m'] for r in c], 90)), 4)] if c else None,
                'axis_error_deg_median_p90': ([round(float(np.median(a)), 2), round(float(np.percentile(a, 90)), 2)]
                                              if (a := [r['axis_err_deg'] for r in c if r['axis_err_deg'] is not None]) else None),
                'wrong_d_med_m_median': round(float(np.median([r['d_med_m'] for r in rows if not r['correct']])), 3)
                if any(not r['correct'] for r in rows) else None}

    vis_f = [r for r in frame_rows if r['visible_frame']]
    inv_f = [r for r in frame_rows if not r['visible_frame']]
    seg_vis = [r for r in seg_rows if r['visible_frame']]
    seg_inv = [r for r in seg_rows if not r['visible_frame']]
    cells_all = np.array(list(gt_cell_all.values())).reshape(-1, 2)
    cells_set = np.array(list(gt_cell_settled.values())).reshape(-1, 2)

    def coverage(cells):
        if not len(cells):
            return None
        hit = np.zeros(len(cells), bool)
        for a, b in correct_chords:
            hit |= point_segment_dist(cells, a, b) <= args.tol_m
        return share(int(hit.sum()), len(cells))

    gt_faces_all = sum(r['gt_faces'] for r in frame_rows)
    gt_faces_set = sum(r['gt_faces'] for r in frame_rows if r['settled'])
    summary = {
        'episode': str(ep_dir), 'robot': args.robot, 'frames_jsonl': str(frames_rel), 'step': step,
        'options': {'load_rule': args.load_rule, 'detector_params': det_params, 'sag_comp': bool(args.sag_comp),
                    'gate': args.gate, 'settle_s': ewm.SETTLE_S if args.gate == 'settle' else None,
                    'ego_map_origin': 'chassis', 'arm_axis_offset_m': ewm.ARM_AXIS_OFFSET_M},
        'tol_m': args.tol_m, 'frames_scored': len(frame_rows), 'visible_frames': len(vis_f),
        'settled_frames': sum(r['settled'] for r in frame_rows),
        'settled_visible_frames': sum(r['settled'] for r in vis_f),
        'segments_visible_frames': seg_stats(seg_vis),
        'segments_visible_frames_by_range_m': {
            f'{lo:g}-{hi:g}': seg_stats([r for r in seg_vis if lo <= r['range_m'] < hi])
            for lo, hi in RANGE_BANDS_M},
        'segments_visible_frames_by_load': {name: seg_stats([r for r in seg_vis if r['loaded'] == flag])
                                            for name, flag in (('unloaded', False), ('loaded', True))},
        'height_m_by_arm_pose_s3': height_by_pose(seg_rows),
        'false_on_invisible_frames': {'frames': len(inv_f), 'settled_frames': sum(r['settled'] for r in inv_f),
                                      'segments': len(seg_inv),
                                      'frames_with_any_segment': sum(1 for r in inv_f if r['segments']),
                                      'segments_per_settled_frame': share(len(seg_inv), sum(r['settled'] for r in inv_f))},
        'gt_faces': {'all_visible_frames': gt_faces_all, 'in_settled_frames': gt_faces_set,
                     'found': sum(r['gt_faces_found'] for r in frame_rows),
                     'found_share_of_settled': share(sum(r['gt_faces_found'] for r in frame_rows), gt_faces_set),
                     'found_share_of_all': share(sum(r['gt_faces_found'] for r in frame_rows), gt_faces_all),
                     'visible_frames_with_a_face_found': sum(1 for r in vis_f if r['gt_faces_found']),
                     'visible_settled_frames_with_gt_face': sum(1 for r in vis_f if r['settled'] and r['gt_faces'])},
        'map_coverage': {'cell_m': CELL_M, 'cells_seen_in_any_frame': len(cells_all),
                         'cells_seen_in_settled_frames': len(cells_set),
                         'covered_share_of_seen_in_any_frame': coverage(cells_all),
                         'covered_share_of_seen_in_settled_frames': coverage(cells_set)},
        'records': len(emap.records),
        'gt_use': 'scoring only: walls, chassis pose and the rendered camera are read after detection and never reach it',
    }
    (out_dir/'summary.json').write_text(json.dumps(summary, indent=2))
    for name, rows in (('segments.csv', seg_rows), ('frames.csv', frame_rows)):
        if rows:
            with open(out_dir/name, 'w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
    if args.gate == 'settle':
        emap.save(out_dir/'ego_map.jsonl')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--episode', required=True)
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--output', required=True)
    ap.add_argument('--every', type=int, default=2)
    ap.add_argument('--gate', choices=('none', 'settle'), default='none',
                    help='none: score every frame (step 0). settle: record only settled observations (stage C)')
    ap.add_argument('--tol-m', type=float, default=0.15)
    ap.add_argument('--min-visible-cols', type=int, default=8)
    ap.add_argument('--max-range-m', type=float, default=cov.MAX_RANGE_M)
    ap.add_argument('--load-rule', choices=wp.LOAD_RULES, default=wp.LOAD_RULE_DEFAULT)
    ap.add_argument('--detector-params', default='')
    ap.add_argument('--sag-comp', action='store_true')
    run(ap.parse_args())
