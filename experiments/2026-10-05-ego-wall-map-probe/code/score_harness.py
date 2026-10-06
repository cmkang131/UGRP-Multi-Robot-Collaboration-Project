"""Visibility-split scoring harness for the height-free wall-contact detector.

Refs #216. **Physical simulation runs: 0.** Reads recorded own-camera frames only and
never writes into a recorded episode directory. Outputs go to ``--output``.

Why this exists: ``wall_probe.py`` reduces everything to one ``endpoint_hit_share`` over
all frames. That number is meaningless because most frames point the wrist camera away
from every wall, so a correct detector *must* return nothing there and a trigger-happy
one scores just as well on the frames where a wall genuinely fills the view. This
harness labels every frame with ground-truth wall visibility first, then reports:

  recall           only over columns that are provably wall-visible
  row / range err  only over detected contacts on those same columns
  false positives  only over frames where nothing is visible -- never merged with recall
  height           the inverted ``scan['h']`` and segment ``height_m`` distributions

Both carried-object variants (``mask_off`` / ``mask_on``) are scored separately and
never averaged together. On this episode they turn out to be identical, because
``height_free_wall.detect`` already gates on the horizon row and no frame in the
visible subset has the beam entering the column strip; that is a property of this
episode, not a property of the harness.

GROUND TRUTH IS SCORING-ONLY. ``height_free_wall.detect`` and ``link_segments`` receive
exactly three things -- the own undistorted image, the own commanded servo (through
``markerless_probe.column_model``) and the own load state. The map walls
(``static_map.json``) and the robot pose (``eval_only/trajectory.jsonl``) are read only
below, in :func:`ground_truth` and the scoring branches, and never reach a detector
argument, a detector threshold or ``height_free_wall.PARAMS``. Keep it that way: the two
detector call sites are marked ``# DETECTOR: ground truth free``.

Two geometry corrections this harness applies to the ground truth, both of which
``coverage.py``'s labelling misses. Both are documented at their definitions below and
quantified in the ``gt_geometry`` block of the summary JSON.

  1. ``coverage.ray_rect`` traces from ``cm.origin`` (the camera nadir) while
     ``cm.rows`` parametrises from ``cm.q0`` (the bottom-row floor point). The two
     differ by the along-ray offset ``dot(q0 - origin, d)`` -- a median 0.10 m, up to
     0.33 m on this episode -- so the raw trace distance cannot be fed to ``cm.rows``
     as-is.
  2. ``cm`` is in the robot base frame but the wall rectangles are in map/world
     coordinates. The robot is *not* at the map origin, so the trace has to be
     transformed by the recorded pose before it is intersected with the map. Pass
     ``--no-pose-correct`` to reproduce the uncorrected convention.

Ground-truth camera (``--gt-camera``). The two corrections above still left the ground truth
built from the detector's own camera model (FK of the commanded pulses + fixed bias), so any
error in that model moved ground truth and detector together and showed up as a row bias that
belongs to neither. ``true`` (default) builds the ground-truth floor trace from the camera MuJoCo
rendered from (``true_camera.TrueCamera``: recorded ``qpos`` -> ``mj_forward``, no stepping).
``model`` reproduces the previous scoring (``harness-full/``). ``diag_bias.py`` checks the
``true`` rows against a segmentation render, which needs no camera model at all.

OPTIONS. Every behaviour change of #405 is an explicit switch and its default is the behaviour before #405:
``--load-rule s3|gripper`` (default ``s3``: ``servo[3] >= 900``, an arm pose that marks the open-gripper search
pose (s3 = 1072) as loaded; ``gripper``: the own commanded gripper pulse closed, ``wall_probe.is_loaded``),
``--detector-params '{"floor_patch_max_m": 0.81}'`` (floor-patch rule, off by default). ``--gt-camera true|model``
is scoring only and is the one exception: ``true`` (default) is the corrected ground truth, ``model`` the earlier one.
The earlier ``wall_probe.py`` read the load state with the string key ``'3'`` on an int-keyed dict (never loaded);
``s3`` here reads the int key, as the earlier scorer did. Of the 1848 frames of the v98 dev episode ``s3`` marks 669
as loaded, the own gripper command is closed on 571.
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
# The code directory must come FIRST: importing markerless_probe below inserts its own
# ROOT at position 0, and a colliding module name would then shadow height_free_wall /
# wall_probe / coverage.
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-26-markerless-probe'))
sys.path.insert(0, str(HERE))

import markerless_probe as mp  # noqa: E402
import coverage as cov  # noqa: E402
import height_free_wall as hfw  # noqa: E402
import wall_probe as wp  # noqa: E402
import true_camera as tc  # noqa: E402

VARIANTS = ('mask_off', 'mask_on')

# Height statistics read ``scan['h']`` only. ``scan['h_lb']`` is a lower bound for a
# surface whose top leaves the frame; mixing it into the median would bias the height
# distribution downward, so the true wall height is not recoverable from those columns.


class WorldTrace:
    """Duck-typed ``ColumnModel`` carrying only what the ground-truth trace reads.

    ``ray_rect`` (legacy) touches ``cm.origin[:2]`` and ``cm.d[j]``; the exact trace below
    additionally reads ``cm.q0``, so it is carried too.
    """

    __slots__ = ('origin', 'd', 'q0')

    def __init__(self, origin, d, q0=None):
        self.origin = origin
        self.d = d
        self.q0 = q0


def world_trace(cm, pose):
    """Map-frame floor trace of ``cm``. ``pose=None`` keeps the uncorrected convention."""
    if pose is None:
        return cm
    px, py, yaw = pose
    c, s = math.cos(yaw), math.sin(yaw)
    rot = np.array([[c, -s], [s, c]])
    origin = np.concatenate([rot @ cm.origin[:2] + np.array([px, py]), [cm.origin[2]]])
    return WorldTrace(origin, cm.d @ rot.T, cm.q0 @ rot.T + np.array([px, py]))


def first_hit_t(p0, d, rects):
    """Smallest t >= 0 where the line ``p0 + t*d`` enters a wall footprint, else None."""
    best = None
    for cx, cy, hx, hy, _h in rects:
        lo, hi, ok = -math.inf, math.inf, True
        for k, (c, e) in enumerate(((cx, hx), (cy, hy))):
            if abs(d[k]) < 1e-12:
                if abs(p0[k] - c) > e:
                    ok = False
                    break
                continue
            t1, t2 = (c - e - p0[k])/d[k], (c + e - p0[k])/d[k]
            lo, hi = max(lo, min(t1, t2)), min(hi, max(t1, t2))
            if lo > hi:
                ok = False
                break
        if ok and lo >= 0 and (best is None or lo < best):
            best = lo
    return best


def ground_truth(cm, rects, trace, max_range_m, exact=True):
    """Per-column ground-truth wall contact. **Scoring only, never reaches the detector.**

    Returns ``(visible, row, range_m, hit)``, each length ``n_columns``. ``visible`` is
    the frame's label: the column's floor trace meets a wall footprint within
    ``max_range_m`` of the camera nadir and that contact projects to a row inside the image.

    ``exact=True`` intersects the column's own floor trace ``q0 + t*d`` (the line ``cm.rows``
    parametrises) with the wall footprints, so the hit ``t`` is the one ``cm.rows`` expects.
    ``exact=False`` is the legacy construction: cast from the camera nadir along ``d`` and
    subtract the along-ray offset ``dot(q0 - origin, d)``. That line is parallel to the column's
    trace but not on it (the column plane is tilted by the camera pitch), so for off-centre
    columns it hits the wall at a slightly different point.
    """
    n_c = len(cm.columns)
    if exact:
        t_row = np.full(n_c, np.nan)
        for j in range(n_c):
            v = first_hit_t(trace.q0[j], trace.d[j], rects)
            if v is not None:
                t_row[j] = v
        hit = np.isfinite(t_row)
        p = cm.floor_point(np.where(hit, t_row, np.nan))
        rng = np.hypot(p[..., 0] - cm.origin[0], p[..., 1] - cm.origin[1])
        hit &= rng <= max_range_m
        t_row = np.where(hit, t_row, np.nan)
    else:
        t_ray = np.array([np.nan if (v := cov.ray_rect(trace, j, rects, max_range_m)) is None else v
                          for j in range(n_c)])
        hit = np.isfinite(t_ray)
        # Correction 1: ray_rect measures from cm.origin, cm.rows measures from cm.q0.
        along = ((cm.q0 - cm.origin[:2]) * cm.d).sum(1)
        t_row = np.where(hit, t_ray - along, np.nan)
    row = cm.rows(t_row, 0.)
    inside = hit & np.isfinite(row) & (row >= 0) & (row <= hfw.HEIGHT - 1)
    p = cm.floor_point(np.where(inside, t_row, np.nan))
    rng = np.hypot(p[..., 0] - cm.origin[0], p[..., 1] - cm.origin[1])
    return inside, np.where(inside, row, np.nan), np.where(inside, rng, np.nan), hit


def pct(values, q):
    """Percentile of a 1-D array, or None when empty (JSON has no NaN)."""
    a = np.asarray(values, float)
    a = a[np.isfinite(a)]
    return round(float(np.percentile(a, q)), 3) if a.size else None


def describe(values, unit=''):
    """n / median / p10 / p90 of a sample, in the given unit."""
    a = np.asarray(values, float)
    a = a[np.isfinite(a)]
    if not a.size:
        return {'n': 0, f'median{unit}': None, f'p10{unit}': None, f'p90{unit}': None}
    return {'n': int(a.size), f'median{unit}': round(float(np.median(a)), 3),
            f'p10{unit}': round(float(np.percentile(a, 10)), 3),
            f'p90{unit}': round(float(np.percentile(a, 90)), 3)}


def mask_on_top(und, cm, loaded):
    """Per-column carried-object occlusion ceiling, delegated to the detector.

    Uses ``height_free_wall.self_top_mask`` rather than re-deriving it here: that
    module owns the self-occlusion policy (``self_mask``), and duplicating it would
    silently drift from the detector under measurement. Own image + own load state.
    """
    return hfw.self_top_mask(und, cm, loaded=loaded)


def run(args):
    ep_dir = Path(args.episode)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    static_map = json.loads((ep_dir/'inputs'/'static_map.json').read_text())
    rects = wp.wall_rects(static_map)                       # ground truth, scoring only
    frames, frames_rel = wp.resolve_frames(ep_dir, args.robot)
    t_of_frame = np.array([float(r['sim_time']) for r in frames])

    truecam = tc.TrueCamera(ep_dir, args.robot) if args.gt_camera == 'true' else None
    poses = None
    if truecam is None and not args.no_pose_correct:
        traj = [json.loads(l) for l in (ep_dir/'eval_only'/'trajectory.jsonl').read_text().splitlines()
                if l.strip()]
        qa, _ = wp.free_joint_qaddr(ep_dir/'scene.xml', f'{args.robot}__base_free')
        poses = [(float(t['qpos'][qa]), float(t['qpos'][qa + 1]),
                  wp.yaw_from_quat(t['qpos'][qa + 3:qa + 7])) for t in traj]

    def pose_at(t):
        i = min(max(int(np.searchsorted(t_of_frame, t)), 0), len(poses) - 1)
        return poses[i]

    cols = mp.column_positions(wp.FROZEN_DETECTOR['columns'], wp.FROZEN_DETECTOR['strip_half_px'])
    det_params = json.loads(args.detector_params) if args.detector_params else {}
    step = max(1, int(args.every))

    rows_out, segments_out = [], []
    col_dump = {}
    frame_ids = []
    n_frames = n_visible = 0
    for idx in range(0, len(frames), step):
        row = frames[idx]
        t = float(row['sim_time'])
        servo = {int(k): int(v) for k, v in row['commanded_servo'].items()}
        bgr = cv2.imread(str(ep_dir/row['path']), cv2.IMREAD_COLOR)
        if bgr is None:
            continue

        # NOTE: servo keys are ints. wall_probe.py reads them with the string key '3', so
        # its `loaded` flag is False on every frame (669 of 1848 here are actually loaded).
        # Read them as ints; this only selects the elevation-bias entry and which carried-
        # object mask applies, both own-signal derived.
        loaded = wp.loaded_for(servo, args.load_rule)

        # ---- ground truth (scoring only) -------------------------------------------------
        if truecam is not None:
            gt_cm, gt_pose = truecam.column_model(idx, cols)
            gt_trace = world_trace(gt_cm, gt_pose)
        else:
            gt_cm_bias = mp.elevation_bias(
                wp.SEED_BIAS['loaded' if loaded else 'unloaded'], servo)
            gt_cm = mp.column_model(servo, gt_cm_bias, cols)
            gt_trace = world_trace(gt_cm, pose_at(t) if poses else None)
        vis, gt_row, gt_range, hit = ground_truth(gt_cm, rects, gt_trace, args.max_range_m,
                                                  exact=args.gt_camera == 'true')
        visible_frame = bool(vis.sum() >= args.min_visible_cols)
        # a contact needs ``band_px`` rows of surface above it to be testable at all
        testable = vis & (gt_row >= hfw.PARAMS['band_px'])
        testable_frame = bool(testable.sum() >= args.min_visible_cols)

        # ---- detection (no ground truth below this line) ----------------------------------
        und = mp.undistort(bgr)
        cm = mp.column_model(servo, mp.elevation_bias(
            wp.SEED_BIAS['loaded' if loaded else 'unloaded'], servo), cols)   # DETECTOR: own servo only

        rec = {'frame_index': int(row.get('frame_id', idx)), 't': round(t, 3), 'loaded': bool(loaded),
               's3': int(servo.get(3, 0)), 'wall_hit_cols': int(hit.sum()),
               'visible_cols': int(vis.sum()), 'visible_frame': visible_frame,
               'testable_cols': int(testable.sum()), 'testable_frame': testable_frame,
               'gt_row_med': pct(gt_row[vis], 50)}

        for tag in VARIANTS:
            if tag == 'mask_off':
                self_top = np.full(len(cols), hfw.HEIGHT, int)
            else:
                self_top = mask_on_top(und, cm, loaded)
            scan = hfw.detect(und, cm, params=det_params, self_top=self_top, loaded=loaded)  # DETECTOR: image+cm+mask
            segs = hfw.link_segments(scan, det_params)      # DETECTOR: no ground truth

            # ---- scoring only -------------------------------------------------------------
            det = np.isfinite(scan['vb'][:, 0])
            found = vis & det
            rec[f'{tag}_contacts'] = int(det.sum())
            rec[f'{tag}_segments'] = len(segs)
            rec[f'{tag}_contacts_on_visible'] = int(found.sum())
            rec[f'{tag}_recall'] = round(float(found.sum()/max(vis.sum(), 1)), 4)
            correct = found & (np.abs(scan['vb'][:, 0] - gt_row) <= args.row_tol_px)
            rec[f'{tag}_correct_on_visible'] = int(correct.sum())
            rec[f'{tag}_correct_recall'] = round(float(correct.sum()/max(vis.sum(), 1)), 4)
            found_t = testable & det
            rec[f'{tag}_contacts_on_testable'] = int(found_t.sum())
            rec[f'{tag}_recall_testable'] = round(float(found_t.sum()/max(testable.sum(), 1)), 4)
            row_err = scan['vb'][:, 0][found] - gt_row[found]
            rec[f'{tag}_row_err_med_px'] = pct(row_err, 50)
            rec[f'{tag}_row_err_abs_med_px'] = pct(np.abs(row_err), 50)
            rng_err = scan['r'][:, 0][found] - gt_range[found]
            rec[f'{tag}_range_err_abs_med_m'] = pct(np.abs(rng_err), 50)
            rec[f'{tag}_range_err_med_m'] = pct(rng_err, 50)
            h = scan['h'][np.isfinite(scan['h'])]
            rec[f'{tag}_height_med_m'] = pct(h, 50)
            sh = [s['height_m'] for s in segs if s['height_m'] is not None]
            rec[f'{tag}_seg_height_med_m'] = pct(sh, 50)
            col_dump.setdefault(tag, []).append(np.stack([
                scan['vb'][:, 0], scan['r'][:, 0], gt_row, gt_range]))
            for s in segs:
                segments_out.append({'tag': tag, 'frame_index': int(row.get('frame_id', idx)),
                                     't': round(t, 3), **s})

        rows_out.append(rec)
        frame_ids.append(rec['frame_index'])
        n_frames += 1
        n_visible += int(visible_frame)
        if n_frames % 200 == 0:
            print(f'{n_frames} frames ({n_visible} visible)', flush=True)

    fields = list(rows_out[0].keys()) if rows_out else []
    with open(out_dir/'per_frame.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_out)
    with open(out_dir/'segments.jsonl', 'w') as f:
        for s in segments_out:
            f.write(json.dumps(s) + '\n')
    # per-column arrays, (frames, 4, columns): det row, det range, gt row, gt range
    np.savez_compressed(out_dir/'columns.npz', frame_index=np.array(frame_ids),
                        columns=cols, **{tag: np.stack(v) for tag, v in col_dump.items()})

    # ---- aggregate ----------------------------------------------------------------------
    vis_frames = [r for r in rows_out if r['visible_frame']]
    testable_frames = [r for r in rows_out if r['testable_frame']]
    inv_frames = [r for r in rows_out if not r['visible_frame']]

    def present(rows, key):
        return [r[key] for r in rows if r.get(key) is not None]

    summary_variants = {}
    for tag in VARIANTS:
        recalls = present(vis_frames, f'{tag}_recall')
        row_errs = present(vis_frames, f'{tag}_row_err_med_px')
        row_abs = present(vis_frames, f'{tag}_row_err_abs_med_px')
        rng_abs = present(vis_frames, f'{tag}_range_err_abs_med_m')
        n_det_vis = sum(r[f'{tag}_contacts_on_visible'] for r in vis_frames)
        n_gt_vis = sum(r['visible_cols'] for r in vis_frames)
        inv_hits = sum(1 for r in inv_frames if r[f'{tag}_contacts'])
        inv_segs = sum(1 for r in inv_frames if r[f'{tag}_segments'])
        hs = present(rows_out, f'{tag}_height_med_m')
        sh = [s['height_m'] for s in segments_out if s['tag'] == tag and s['height_m'] is not None]
        summary_variants[tag] = {
            'recall': {
                'note': 'detected contacts / ground-truth-visible columns, visible frames only',
                'gt_visible_columns': n_gt_vis,
                'detected_on_visible_columns': n_det_vis,
                'column_recall': round(n_det_vis/max(n_gt_vis, 1), 4),
                'per_frame_recall_median': pct(recalls, 50),
                'per_frame_recall_p10': pct(recalls, 10),
                'visible_frames': len(vis_frames),
                'visible_frames_with_zero_recall': sum(1 for v in recalls if v == 0),
            },
            'correctness': {
                'note': (f'a contact on a visible column is CORRECT when |detected row - ground-truth row| '
                         f'<= {args.row_tol_px} px (the detector window_px); per-frame medians hide wrong ones'),
                'row_tol_px': args.row_tol_px,
                'detected_on_visible_columns': n_det_vis,
                'correct_on_visible_columns': sum(r[f'{tag}_correct_on_visible'] for r in vis_frames),
                'precision_on_visible_columns': round(sum(r[f'{tag}_correct_on_visible'] for r in vis_frames)
                                                      / max(n_det_vis, 1), 4),
                'correct_column_recall': round(sum(r[f'{tag}_correct_on_visible'] for r in vis_frames)
                                               / max(n_gt_vis, 1), 4),
                'visible_frames_with_zero_correct': sum(
                    1 for r in vis_frames if r[f'{tag}_correct_on_visible'] == 0),
            },
            'recall_testable': {
                'note': ('same, restricted to contacts with >= band_px rows of surface above them '
                         '(gt row >= band_px), the least the detector needs to test a contact'),
                'gt_testable_columns': sum(r['testable_cols'] for r in testable_frames),
                'detected_on_testable_columns': sum(r[f'{tag}_contacts_on_testable'] for r in testable_frames),
                'column_recall': round(sum(r[f'{tag}_contacts_on_testable'] for r in testable_frames)
                                       / max(sum(r['testable_cols'] for r in testable_frames), 1), 4),
                'testable_frames': len(testable_frames),
                'testable_frames_with_zero_recall': sum(
                    1 for r in testable_frames if r[f'{tag}_contacts_on_testable'] == 0),
            },
            'row_error_px': {
                **describe(row_errs, ''),
                'note': 'detected vb minus ground-truth contact row, median per visible frame',
                'abs_per_frame_median_px': pct(row_abs, 50),
            },
            'range_error_m': {
                **describe(rng_abs, ''),
                'note': '|scan r - ground-truth range| on visible columns, median per visible frame',
            },
            'false_positives_invisible_frames': {
                'note': 'invisible frames ONLY. Never combined with recall.',
                'frames': len(inv_frames),
                'contacts': sum(r[f'{tag}_contacts'] for r in inv_frames),
                'segments': sum(r[f'{tag}_segments'] for r in inv_frames),
                'contacts_per_frame': round(sum(r[f'{tag}_contacts'] for r in inv_frames)
                                            / max(len(inv_frames), 1), 3),
                'segments_per_frame': round(sum(r[f'{tag}_segments'] for r in inv_frames)
                                            / max(len(inv_frames), 1), 3),
                'frames_with_any_contact': inv_hits,
                'frames_with_any_contact_share': round(inv_hits/max(len(inv_frames), 1), 4),
                'frames_with_any_segment': inv_segs,
                'frames_with_any_segment_share': round(inv_segs/max(len(inv_frames), 1), 4),
            },
            'height': {
                'gt_wall_height_m': sorted({r[4] for r in rects}),
                'scan_h_m': describe(hs, '_m'),
                'scan_h_note': 'per-frame median of scan["h"] over finite contacts',
                'segment_height_m': describe(sh, '_m'),
            },
        }

    summary = {
        'episode': str(ep_dir), 'robot': args.robot, 'step': step,
        'frames_jsonl': str(frames_rel), 'map_id': static_map.get('map_id'),
        'frames_scored': n_frames, 'visible_frames': n_visible,
        'invisible_frames': n_frames - n_visible,
        'visible_frame_share': round(n_visible/max(n_frames, 1), 4),
        'testable_frames': len(testable_frames),
        'gt_camera': args.gt_camera, 'load_rule': args.load_rule,
        'min_visible_cols': args.min_visible_cols,
        'max_range_m': args.max_range_m,
        'visible_cols_total': sum(r['visible_cols'] for r in rows_out),
        'variants': summary_variants,
        'gt_geometry': {
            'pose_corrected': not args.no_pose_correct,
            'parametrisation_corrected': True,
            'note': ('ground truth is transformed into the map frame and reparametrised from '
                     'cm.q0 before cm.rows; coverage.py does neither, see score_harness docstring'),
        },
        'frozen_detector_params': wp.FROZEN_DETECTOR,
        'seed_bias_rad': wp.SEED_BIAS,
        'height_free_params': hfw.recorded_params(det_params),
        'detector_params_override': det_params,
        'gt_use': ('scoring only. Detector inputs are own undistorted RGB, own commanded servo, '
                   'fixed camera calibration and own load state.'),
    }
    (out_dir/'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--episode', required=True)
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--output', required=True)
    ap.add_argument('--every', type=int, default=2)
    ap.add_argument('--min-visible-cols', type=int, default=8)
    ap.add_argument('--max-range-m', type=float, default=cov.MAX_RANGE_M)
    ap.add_argument('--gt-camera', choices=('true', 'model'), default='true',
                    help='ground-truth camera: the rendered MuJoCo camera, or the detector FK model (legacy)')
    ap.add_argument('--load-rule', choices=wp.LOAD_RULES, default=wp.LOAD_RULE_DEFAULT,
                    help='own load state: s3 = servo[3] >= 900 (default, the earlier rule), gripper = commanded gripper closed')
    ap.add_argument('--detector-params', default='',
                    help='JSON overrides of height_free_wall.PARAMS, e.g. {"clamp_horizon": true}')
    ap.add_argument('--row-tol-px', type=float, default=3.,
                    help='a contact is correct when within this many rows of ground truth')
    ap.add_argument('--no-pose-correct', action='store_true',
                    help='skip the base-frame to map-frame transform (reproduces coverage.py)')
    run(ap.parse_args())