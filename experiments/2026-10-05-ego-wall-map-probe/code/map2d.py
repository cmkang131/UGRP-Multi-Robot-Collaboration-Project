"""2D top-down render of the height-free wall detector against the static-map ground truth.

Refs #216. **Physical simulation runs: 0.** Reads recorded own-camera frames only and
never writes into a recorded episode directory. Outputs go to ``--out`` / ``--png``,
which must live under the primary checkout's ``outputs/``.

Two deliverables:

  a JSON dump  one record per frame: robot pose, ground-truth wall footprints, the
               detector's linked segments in world coordinates, and the per-column
               ground-truth contacts (slab intersection from ``cm.q0[j]``).
  a PNG        one top-down figure: robot at its pose, grey ground-truth footprints,
               coloured detector segments, contact dots, camera FOV wedge, 1 m grid,
               scale bar, legend.

--------------------------------------------------------------------------
GROUND TRUTH IS DRAWING-ONLY.  ``height_free_wall.detect`` and ``link_segments``
receive exactly three things -- the own undistorted image, the own commanded servo
(through ``markerless_probe.column_model``) and the own load state.  The map walls
(``static_map.json``) and the robot pose (``eval_only/trajectory.jsonl``) are read
only in the ``# GROUND TRUTH`` blocks below, for drawing and for the distance
statistics.  They never reach a detector argument, a detector threshold or
``height_free_wall.PARAMS``.  The two detector call sites are marked
``# DETECTOR: ground truth free`` and the two ground-truth call sites
``# GROUND TRUTH: drawing + statistics only``.

--------------------------------------------------------------------------
THREE GEOMETRY POINTS the raw ``coverage.ray_rect`` convention gets wrong or leaves
implicit.  A top-down map in world coordinates is wrong without them, so this module
handles all three itself and uses ``score_harness`` only as a cross-check:

  1. Frame of reference.  ``cm`` (columns, floor trace, camera nadir) lives in the
     robot BASE frame; the wall rectangles in ``static_map.json`` live in the MAP
     frame.  The robot is not at the map origin, so the trace is lifted to map
     coordinates by the recorded pose before it is intersected.  Without this the
     ground-truth contacts would be plotted next to the robot instead of on the walls.
  2. Parametrisation.  ``coverage.ray_rect`` starts its ray at ``cm.origin`` (the
     camera nadir in xy).  A column's floor trace, however, is the LINE
     ``cm.q0[j] + t*cm.d[j]``, and ``cm.d`` is the direction of that line, NOT the
     direction of a camera ray through ``cm.q0``: ``ColumnModel.__post_init__`` takes
     ``q0`` from the BOTTOM image row and ``q1`` from a far row and sets
     ``d = normalize(q1 - q0)``, so the line does not pass through the camera.
     Tracing from ``cm.origin`` along ``cm.d[j]`` therefore follows a line PARALLEL to
     the true trace but laterally displaced.

     That displacement has two parts.  The ALONG-ray part is
     ``dot(q0 - origin, d)`` -- median 0.10 m, max 0.33 m on this episode -- and that
     is what ``score_harness`` subtracts.  The PERPENDICULAR part,
     ``|cross(q0 - origin, d)|``, it does not correct.  Both are measured per frame and
     reported under ``gt_crosscheck_vs_score_harness``.  The residual is small, but it
     flips grazing hits at wall corners: on frame 20 column 20 the two conventions
     disagree about whether the ray meets the door-post wall at all.

     This module therefore solves the slab intersection ITSELF, with the ray origin at
     the world position of ``cm.q0[j]`` and direction ``rot(yaw) @ cm.d[j]``
     (:func:`ray_slab`, :func:`gt_columns`).  The ray is then on the line ``cm.rows``
     actually parametrises and ``height_free_wall.detect`` actually uses, with no
     correction step and no residual lateral error.  The returned ``t`` is directly
     comparable with the detector's ``scan['vb']`` and ``scan['r']``.

  3. Per-column rows.  The image row is evaluated with a FULL ARRAY of per-column ``t``
     values, ``cm.rows(t_array, 0.)``, and then indexed by column.  ``cm.rows`` is
     vectorised over columns and BROADCASTS a scalar ``t`` across all of them, so
     ``cm.rows(float(scalar), 0.)`` returns column 0's geometry for every column and
     ``float(np.ravel(cm.rows(...))[0])`` silently yields column 0's row 96 times.
     Passing the length-96 array makes ``alpha[j] + t[j]*beta[j]`` pair up correctly.

  SCOPE.  Corrections 1-3 matter for ``gt_contacts`` and for the image-row comparison.
  They do NOT affect the ``dist_to_walls`` alignment statistics in
  :func:`alignment_stats`, which compare a DETECTED world point against the wall
  rectangles -- both already in the world frame.  Those numbers are reported as
  measured, with no ground-truth correction applied to the detector side.

--------------------------------------------------------------------------
POSE LOOKUP.  The frame -> pose mapping is a known hazard: the recorded trajectory
carries its time under the key ``t`` while ``frames.jsonl`` uses ``sim_time``, so a
naive ``traj_row['sim_time']`` raises.  The mapping is done exactly the way
``diag_rows.py`` does it -- build the pose list from ``trajectory.jsonl`` in file
order, then index it with ``searchsorted`` over the FRAME time array.  ``verify_pose``
independently checks the two files are the same length and elementwise time-equal and
reports the result under ``pose_lookup`` in the JSON.
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
# HERE first: markerless_probe inserts its own ROOT at position 0 on import, and a
# colliding module name would then shadow height_free_wall / wall_probe / coverage.
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-26-markerless-probe'))
sys.path.insert(0, str(ROOT))

import markerless_probe as mp          # noqa: E402
import coverage as cov                 # noqa: E402
import height_free_wall as hfw         # noqa: E402
import wall_probe as rp                # noqa: E402
import score_harness as sh             # noqa: E402  (world_trace + ground_truth)

MAX_RANGE_M = cov.MAX_RANGE_M          # 6.0 m, from coverage.py
MIN_VISIBLE_COLS = 8

# The ground-truth convention, recorded in the output so the reader never has to guess.
GT_CONVENTION = ('per-column ray from the world position of cm.q0[j] along rot(yaw) @ cm.d[j], '
                 'slab-intersected with the static-map wall rectangles. cm.d is the direction of '
                 'the column floor-TRACE line q0 + t*d, not of a camera ray, so the ray is '
                 'started on that line rather than at cm.origin and no dot(q0-origin,d) '
                 'correction is applied. t is then in the parametrisation cm.rows and '
                 'height_free_wall.detect share. The image row is cm.rows(t_array, 0.) with a '
                 'full per-column array (a scalar would broadcast column 0 geometry to all 96 '
                 'columns). Compared every frame against score_harness.ground_truth; see '
                 'gt_crosscheck_vs_score_harness for the size of the disagreement.')

# Curated frame set: every frame contains at least 8 ground-truth wall contacts in
# image, the set spans all four commanded shoulder (servo 3) bands present in the
# visible subset and both load states, and it deliberately includes frames where the
# detector returned nothing (4, 340, 816) next to the frame where it returned the
# most (20, eight segments).  Chosen from a full 1848-frame scan with
# coverage.ray_rect; the failures are in on purpose.
DEFAULT_FRAMES = [4, 20, 105, 169, 170, 219, 244, 340, 816]

DEFAULT_HIT_M = 0.15       # "on the wall" threshold for the alignment statistics
DEFAULT_WARN_M = 0.50      # beyond this a segment endpoint is drawn as a failure


# ----------------------------------------------------------------------- episode load
def load_episode(ep_dir: Path, robot: str):
    """Everything the render needs, loaded once. Ground truth is resolved here."""
    static_map = json.loads((ep_dir/'inputs'/'static_map.json').read_text())
    rects = rp.wall_rects(static_map)                                   # GROUND TRUTH
    frames, frames_rel = rp.resolve_frames(ep_dir, robot)
    traj = [json.loads(l) for l in (ep_dir/'eval_only'/'trajectory.jsonl').read_text().splitlines()
            if l.strip()]
    qa, _ = rp.free_joint_qaddr(ep_dir/'scene.xml', f'{robot}__base_free')
    poses = [(float(r['qpos'][qa]), float(r['qpos'][qa + 1]),
              rp.yaw_from_quat(r['qpos'][qa + 3:qa + 7])) for r in traj]  # GROUND TRUTH
    cols = mp.column_positions(rp.FROZEN_DETECTOR['columns'],
                               rp.FROZEN_DETECTOR['strip_half_px'])
    t_of_frame = [float(r['sim_time']) for r in frames]

    def pose_at(t: float):
        """diag_rows.py's convention: index the pose list with the frame time array."""
        i = min(max(int(np.searchsorted(t_of_frame, t)), 0), len(poses) - 1)
        return poses[i], i

    return {'ep': ep_dir, 'robot': robot, 'static_map': static_map, 'rects': rects,
            'frames': frames, 'frames_rel': str(frames_rel), 'poses': poses, 'cols': cols,
            'pose_at': pose_at, 't_of_frame': t_of_frame, 'traj_t': [float(r['t']) for r in traj]}


def verify_pose(ctx) -> dict:
    """Independent check of the frame -> trajectory-pose alignment.  Reported, not assumed."""
    t_frame = np.asarray(ctx['t_of_frame'], float)
    t_traj = np.asarray(ctx['traj_t'], float)
    same_len = t_frame.size == t_traj.size
    equal = bool(same_len and np.allclose(t_frame, t_traj, atol=0, rtol=0))
    idx = np.clip(np.searchsorted(t_frame, t_frame), 0, max(len(ctx['poses']) - 1, 0))
    identity = bool(same_len and np.array_equal(idx, np.arange(t_frame.size)))
    max_dt = float(np.max(np.abs(t_frame - t_traj))) if same_len else None
    return {
        'convention': "diag_rows.py: pose list built from trajectory.jsonl in file order, "
                      "indexed by searchsorted over the frames.jsonl time array",
        'n_frames': int(t_frame.size), 'n_trajectory_rows': int(t_traj.size),
        'same_length': same_len,
        'frame_time_equals_trajectory_time_elementwise': equal,
        'searchsorted_is_identity_index': identity,
        'max_abs_time_difference_s': max_dt,
        'aligned': bool(same_len and equal and identity),
        'note': ('trajectory.jsonl stores its time under the key "t", frames.jsonl under '
                 '"sim_time"; the two arrays are compared here rather than assumed'),
    }


# ------------------------------------------------- ground truth (drawing + statistics)
def rot2d(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s], [s, c]])


def ray_slab(origin2, dir2, rects, max_t):
    """Distance from ``origin2`` along ``dir2`` to the nearest axis-aligned rect, else None.

    Same slab test as ``coverage.ray_rect``, but with the ray origin supplied by the
    caller instead of hard-wired to ``cm.origin``.  That is the whole point: a column's
    floor trace starts at ``cm.q0[j]``, not at the camera nadir, so the caller passes
    the bottom-row floor point and no ``dot(q0-origin, d)`` correction is needed.
    """
    o = np.asarray(origin2, float)
    d = np.asarray(dir2, float)
    best = None
    for cx, cy, hx, hy, _h in rects:
        lo, hi, ok = -math.inf, math.inf, True
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


def gt_columns(cm, cols, rects, pose, max_range_m=MAX_RANGE_M):
    """Per-column ground-truth wall contact. **Scoring/drawing only, never the detector.**

    Convention (see the module docstring):
      * ray origin  = world position of ``cm.q0[j]``, direction ``rot(yaw) @ cm.d[j]``
      * ``t`` is in the ``q0 + t*d`` parametrisation that ``cm.rows`` and
        ``height_free_wall.detect`` share
      * the row is ``cm.rows(t_array, 0.)`` -- a full per-column array, never a scalar

    Returns dict(t, hit, visible, row, world (C,2), range_m, bearing_rad).
    """
    px, py, yaw = pose
    rot, t = rot2d(yaw), np.full(len(cols), np.nan)
    q0_w = cm.q0 @ rot.T + np.array([px, py])
    d_w = cm.d @ rot.T
    for j in range(len(cols)):
        v = ray_slab(q0_w[j], d_w[j], rects, max_range_m)
        if v is not None:
            t[j] = v
    hit = np.isfinite(t)
    # per-column row: t is a length-C array so alpha[j] pairs with t[j]. A scalar here
    # would broadcast column 0's geometry across all 96 columns.
    row = cm.rows(np.where(hit, t, np.nan), 0.)
    visible = hit & np.isfinite(row) & (row >= 0) & (row <= mp.HEIGHT - 1)
    world = q0_w + np.where(hit, t, np.nan)[:, None]*d_w
    cam_w = rot @ cm.origin[:2] + np.array([px, py])
    rel = world - cam_w
    return {'t': t, 'hit': hit, 'visible': visible, 'row': row, 'world': world,
            'range_m': np.hypot(rel[:, 0], rel[:, 1]),
            'bearing_rad': np.arctan2(rel[:, 1], rel[:, 0])}


def gt_crosscheck(cm, cols, rects, pose, gt):
    """Compare this module's ground truth against score_harness.ground_truth, and
    quantify WHY they differ.

    ``cm.d`` is the direction of the column's floor-TRACE line on the ground plane,
    NOT the direction of a camera ray through ``cm.q0``.  ``ColumnModel.__post_init__``
    builds ``q0`` from the bottom image row and ``q1`` from a far row and sets
    ``d = normalize(q1 - q0)``, so the line ``q0 + t*d`` does not pass through the
    camera.  ``coverage.ray_rect`` therefore traces ``cm.origin + t*cm.d[j]``: a line
    PARALLEL to the true trace but laterally displaced.  ``score_harness`` subtracts
    ``dot(q0-origin, d)``, which removes only the ALONG-ray component and leaves the
    perpendicular one unfixed.

    :func:`gt_columns` starts the ray at ``cm.q0[j]``, i.e. on the line ``cm.rows``
    actually parametrises and that ``height_free_wall.detect`` uses, so it is the
    correct convention here.  This function measures the size of the disagreement
    instead of asserting there is none, because the offsets are small but they flip
    grazing hits at wall corners.
    """
    vis, row, rng, hit = sh.ground_truth(cm, rects, sh.world_trace(cm, pose), MAX_RANGE_M, exact=False)  # legacy construction: this function measures its disagreement with it
    v = cm.q0 - cm.origin[:2]                      # offset from the camera nadir to q0
    along = (v*cm.d).sum(1)                        # what score_harness corrects
    lateral = v[:, 0]*cm.d[:, 1] - v[:, 1]*cm.d[:, 0]   # what it leaves in place
    both = gt['hit'] & hit & np.isfinite(gt['row']) & np.isfinite(row)
    return {'convention': 'gt_columns (ray from cm.q0[j]) is used; this block is diagnostic',
            'note': ('cm.d is the floor-trace line direction, not a camera ray, so '
                     'coverage.ray_rect and score_harness trace a laterally displaced '
                     'parallel line; score_harness corrects only the along-ray part'),
            'lateral_offset_m_median': round(float(np.median(np.abs(lateral))), 5),
            'lateral_offset_m_max': round(float(np.max(np.abs(lateral))), 5),
            'along_ray_offset_m_median': round(float(np.median(np.abs(along))), 5),
            'same_hit_set_as_score_harness': bool(np.array_equal(gt['hit'], hit)),
            'same_visible_set_as_score_harness': bool(np.array_equal(gt['visible'], vis)),
            'n_hit_disagreements': int((gt['hit'] != hit).sum()),
            'n_visible_disagreements': int((gt['visible'] != vis).sum()),
            'max_row_difference_px': (round(float(np.max(np.abs(gt['row'][both] - row[both]))), 4)
                                      if both.any() else None),
            'median_row_difference_px': (round(float(np.median(np.abs(gt['row'][both] - row[both]))), 4)
                                         if both.any() else None)}


# ------------------------------------------------------------------ per-frame building
def frame_record(ctx, idx: int) -> dict:
    """One frame: detector output in world coordinates plus its ground truth."""
    ep, row = ctx['ep'], ctx['frames'][idx]
    t = float(row['sim_time'])
    servo = {int(k): int(v) for k, v in row['commanded_servo'].items()}
    # own load state = own commanded gripper pulse (closed ~1500). The old `servo[3] >= 900` is an arm
    # pose, true for the open-gripper search pose, and applied the carry elevation bias to unloaded frames.
    loaded = rp.is_loaded(servo)
    b0 = mp.elevation_bias(rp.SEED_BIAS['loaded' if loaded else 'unloaded'], servo)

    # ---- ground truth (drawing + statistics only) ---------------------------------------
    rects = ctx['rects']
    pose, pose_i = ctx['pose_at'](t)                                    # GROUND TRUTH
    px, py, yaw = pose
    gt_cm = mp.column_model(servo, b0, ctx['cols'])
    gt = gt_columns(gt_cm, ctx['cols'], rects, pose)                    # GROUND TRUTH
    xcheck = gt_crosscheck(gt_cm, ctx['cols'], rects, pose, gt)        # GROUND TRUTH

    # ---- detection (no ground truth below this line) ------------------------------------
    bgr = cv2.imread(str(ep/row['path']), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(f'cannot read frame image: {ep/row["path"]}')
    und = mp.undistort(bgr)
    cm = mp.column_model(servo, b0, ctx['cols'])                       # DETECTOR: own servo only
    self_top = rp.self_top_for(und, cm, servo)                         # DETECTOR: own image+load
    scan = hfw.detect(und, cm, self_top=self_top)                      # DETECTOR: image+cm+mask
    segs = hfw.link_segments(scan)                                     # DETECTOR: no arguments
    # ---- end of detection ----------------------------------------------------------------

    cos_y, sin_y = math.cos(yaw), math.sin(yaw)
    rot = np.array([[cos_y, -sin_y], [sin_y, cos_y]])

    def to_world(p_base):
        return rot @ np.asarray(p_base, float) + np.array([px, py])

    # ground-truth contacts, per column, from the slab intersection at cm.q0[j]
    contacts = []
    for j in range(len(ctx['cols'])):
        if not gt['hit'][j]:
            continue                                                   # no wall on this ray
        w = gt['world'][j]
        contacts.append({'col': int(j),
                         'world_x': round(float(w[0]), 4), 'world_y': round(float(w[1]), 4),
                         'range_m': round(float(gt['range_m'][j]), 4),
                         'bearing_rad': round(float(gt['bearing_rad'][j]), 4),
                         'row_px': (round(float(gt['row'][j]), 2)
                                    if np.isfinite(gt['row'][j]) else None),
                         'visible': bool(gt['visible'][j])})

    ego = []
    for s in segs:
        first = to_world([px + s['range_first_m']*math.cos(s['bearing_first_rad']),
                          py + s['range_first_m']*math.sin(s['bearing_first_rad'])])
        last = to_world([px + s['range_last_m']*math.cos(s['bearing_last_rad']),
                         py + s['range_last_m']*math.sin(s['bearing_last_rad'])])
        d_first = rp.dist_to_walls((float(first[0]), float(first[1])), rects)  # GROUND TRUTH
        d_last = rp.dist_to_walls((float(last[0]), float(last[1])), rects)     # GROUND TRUTH
        ego.append({
            'range_m': round(float(s['range_first_m']), 4),
            'bearing_rad': round(float(s['bearing_first_rad']), 4),
            'world_x': round(float(first[0]), 4), 'world_y': round(float(first[1]), 4),
            'height_m': (None if s['height_m'] is None else round(float(s['height_m']), 4)),
            'col_first': int(s['col_first']), 'col_last': int(s['col_last']),
            'n_columns': int(s['n_columns']), 'contrast_med': round(float(s['contrast_med']), 2),
            # second endpoint of the same segment, so the drawn line is fully described
            'range_last_m': round(float(s['range_last_m']), 4),
            'bearing_last_rad': round(float(s['bearing_last_rad']), 4),
            'world_x_last': round(float(last[0]), 4), 'world_y_last': round(float(last[1]), 4),
            'wall_dist_first_m': round(float(d_first), 4), 'wall_dist_last_m': round(float(d_last), 4),
            'wall_dist_min_m': round(float(min(d_first, d_last)), 4),
        })

    # camera FOV, world-frame bearings of the outermost detector columns
    brgs = []
    for j in (0, len(ctx['cols']) - 1):
        _r, b = hfw.column_range_bearing(cm, j, 1.0)
        brgs.append(b + yaw)
    cam_w = to_world(cm.origin[:2])

    # ---- per-column detector vs ground truth, on columns that are both (scoring only) ---
    det = np.isfinite(scan['vb'][:, 0])
    found = gt['visible'] & det
    cmp = {'n_columns_compared': int(found.sum()),
           'note': 'detector scan["vb"]/scan["r"] minus the ground-truth contact row/range, '
                   'on columns where a ground-truth wall is visible AND the detector fired; '
                   'positive row error = the detector places the contact LOWER in the image, '
                   'i.e. CLOSER to the robot'}
    if found.any():
        row_err = scan['vb'][:, 0][found] - gt['row'][found]
        rng_err = scan['r'][:, 0][found] - gt['range_m'][found]
        cmp.update({'row_error_med_px': round(float(np.median(row_err)), 3),
                    'row_error_abs_med_px': round(float(np.median(np.abs(row_err))), 3),
                    'range_error_med_m': round(float(np.median(rng_err)), 3),
                    'range_error_abs_med_m': round(float(np.median(np.abs(rng_err))), 3)})

    return {
        'frame': int(idx),
        'frame_id': int(row.get('frame_id', idx)),
        'sim_time': round(t, 4),
        'robot': {'x': round(px, 4), 'y': round(py, 4), 'yaw_rad': round(yaw, 5),
                  'loaded': bool(loaded), 'cam_z': round(float(cm.origin[2]), 4),
                  'cam_x': round(float(cam_w[0]), 4), 'cam_y': round(float(cam_w[1]), 4),
                  'servo_3': int(servo.get(3, 0)), 'pose_row': int(pose_i)},
        'walls_gt': [{'cx': c, 'cy': y, 'hx': hx, 'hy': hy, 'height_m': h}
                     for (c, y, hx, hy, h) in rects],
        'ego_walls': ego,
        'gt_contacts': contacts,
        'camera_fov': {'bearing_min_rad': round(float(min(brgs)), 5),
                       'bearing_max_rad': round(float(max(brgs)), 5),
                       'max_range_m': MAX_RANGE_M},
        'gt_convention': GT_CONVENTION,
        'gt_crosscheck_vs_score_harness': xcheck,
        'detector_vs_gt': cmp,
        'counts': {'n_columns': int(len(ctx['cols'])),
                   'n_contacts_total': int(gt['visible'].sum()),
                   'n_contacts_all_hits': int(len(contacts)),
                   'n_detector_columns': int(det.sum()),
                   'n_segments': int(len(ego)),
                   'n_visible_segments': int(sum(1 for e in ego
                                                 if e['wall_dist_min_m'] <= DEFAULT_HIT_M))},
    }


def visible_columns_only(ctx, idx: int) -> int:
    """Number of ground-truth wall contacts that land inside the image (frame label)."""
    row = ctx['frames'][idx]
    servo = {int(k): int(v) for k, v in row['commanded_servo'].items()}
    loaded = rp.is_loaded(servo)
    gt_cm = mp.column_model(servo, mp.elevation_bias(
        rp.SEED_BIAS['loaded' if loaded else 'unloaded'], servo), ctx['cols'])
    gt = gt_columns(gt_cm, ctx['cols'], ctx['rects'],                # GROUND TRUTH
                    ctx['pose_at'](float(row['sim_time']))[0])
    return int(gt['visible'].sum())


# ------------------------------------------------------------------- cv2 map rendering
class View:
    """World (metres) -> canvas pixels, equal aspect, north = +y up."""

    def __init__(self, bounds, box, pad_px):
        x0, y0, x1, y1 = bounds
        bx0, by0, bx1, by1 = box
        bw, bh = max(bx1 - bx0 - 2*pad_px, 1), max(by1 - by0 - 2*pad_px, 1)
        cx, cy = .5*(x0 + x1), .5*(y0 + y1)
        self.scale = min(bw/max(x1 - x0, 1e-6), bh/max(y1 - y0, 1e-6))   # equal aspect
        self.cx, self.cy = cx, cy
        self.ox = .5*(bx0 + bx1) - self.scale*cx
        self.oy = .5*(by0 + by1) + self.scale*cy

    def p(self, x, y):
        return (int(round(self.ox + self.scale*x)), int(round(self.oy - self.scale*y)))


def _text(img, s, org, scale=.55, color=(30, 30, 30), thick=1, font=cv2.FONT_HERSHEY_SIMPLEX):
    cv2.putText(img, s, org, font, scale, color, thick, cv2.LINE_AA)


def _ray_box_interval(o, d, c, e):
    """Parameter interval of the ray ``o + s*d`` inside the axis-aligned box [c-e, c+e]."""
    lo, hi = -math.inf, math.inf
    for k in range(2):
        if abs(d[k]) < 1e-12:
            if abs(o[k] - c[k]) > e[k]:
                return None
            continue
        t1, t2 = (c[k] - e[k] - o[k])/d[k], (c[k] + e[k] - o[k])/d[k]
        lo, hi = max(lo, min(t1, t2)), min(hi, max(t1, t2))
        if lo > hi:
            return None
    return lo, hi


def _rect_hatch(img, v, rect, spacing_m=.28, color=(150, 156, 168)):
    """Diagonal hatching clipped to one wall footprint."""
    cx, cy, hx, hy, _h = rect
    d = np.array([1., 1.])/math.sqrt(2.)
    lo_x, hi_x = cx - hx, cx + hx
    k0 = int(math.floor((lo_x + lo_x + 2*(cy - hy))/(2*spacing_m))) - 2
    for k in range(k0, k0 + int((4*(hx + hy))/(2*spacing_m)) + 6):
        o = np.array([lo_x + k*spacing_m, lo_x + 2*cy - 2*hy - k*spacing_m])
        iv = _ray_box_interval(o, d, (cx, cy), (hx, hy))
        if iv is None:
            continue
        a, b = v.p(*(o + iv[0]*d)), v.p(*(o + iv[1]*d))
        cv2.line(img, a, b, color, 1, cv2.LINE_AA)


def _seg_colour(d, hit_m=DEFAULT_HIT_M, warn_m=DEFAULT_WARN_M):
    if d <= hit_m:
        return (70, 170, 60)        # green   -- on the wall
    if d <= warn_m:
        return (40, 170, 235)       # amber   -- off by up to warn_m
    return (55, 55, 220)            # red     -- off by more


def render_png(rec: dict, path: Path, hit_m=DEFAULT_HIT_M, warn_m=DEFAULT_WARN_M):
    """One top-down figure.  matplotlib is not installed in .venv-sim, so this draws with
    cv2 and sets the axes by hand: equal aspect, metres, north = +y, 1 m grid, scale bar."""
    W, H = 1780, 1180
    img = np.full((H, W, 3), 252, np.uint8)
    panel = (58, 104, 1232, 1128)
    legend = (1266, 104, 1748, 1128)
    cv2.rectangle(img, (panel[0], panel[1]), (panel[2], panel[3]), (255, 255, 255), -1)
    cv2.rectangle(img, (panel[0], panel[1]), (panel[2], panel[3]), (170, 174, 182), 2)
    cv2.rectangle(img, (legend[0], legend[1]), (legend[2], legend[3]), (255, 255, 255), -1)
    cv2.rectangle(img, (legend[0], legend[1]), (legend[2], legend[3]), (170, 174, 182), 2)

    walls = rec['walls_gt']
    ego = rec['ego_walls']
    contacts = rec['gt_contacts']
    rob = rec['robot']
    fov = rec['camera_fov']
    cam = (rob['cam_x'], rob['cam_y'])

    # ---- extent: robot, FOV wedge corners, wall footprints, detector points -----------
    xs = [rob['x'] - 1.2, rob['x'] + 1.2, cam[0]]
    ys = [rob['y'] - 1.2, rob['y'] + 1.2, cam[1]]
    for b in (fov['bearing_min_rad'], fov['bearing_max_rad']):
        xs.append(cam[0] + fov['max_range_m']*math.cos(b))
        ys.append(cam[1] + fov['max_range_m']*math.sin(b))
    for w in walls:
        xs += [w['cx'] - w['hx'], w['cx'] + w['hx']]
        ys += [w['cy'] - w['hy'], w['cy'] + w['hy']]
    for e in ego:
        xs += [e['world_x'], e['world_x_last']]
        ys += [e['world_y'], e['world_y_last']]
    x0, x1 = min(xs) - .4, max(xs) + .4
    y0, y1 = min(ys) - .4, max(ys) + .4
    side = max(x1 - x0, y1 - y0) + 1e-6
    x0, x1 = .5*(x0 + x1) - side/2, .5*(x0 + x1) + side/2
    y0, y1 = .5*(y0 + y1) - side/2, .5*(y0 + y1) + side/2
    v = View((x0, y0, x1, y1), panel, pad_px=64)
    m2px = v.scale

    # ---- 1 m grid -------------------------------------------------------------------------
    gx = math.ceil(x0)
    while gx <= x1:
        a, b = v.p(gx, y0), v.p(gx, y1)
        cv2.line(img, a, b, (232, 235, 240) if gx else (196, 202, 212), 1, cv2.LINE_AA)
        gx += 1
    gy = math.ceil(y0)
    while gy <= y1:
        a, b = v.p(x0, gy), v.p(x1, gy)
        cv2.line(img, a, b, (232, 235, 240) if gy else (196, 202, 212), 1, cv2.LINE_AA)
        gy += 1

    # ---- camera FOV wedge to max_range_m --------------------------------------------------
    poly = np.array([v.p(*cam),
                     v.p(cam[0] + fov['max_range_m']*math.cos(fov['bearing_min_rad']),
                         cam[1] + fov['max_range_m']*math.sin(fov['bearing_min_rad'])),
                     v.p(cam[0] + fov['max_range_m']*math.cos(fov['bearing_max_rad']),
                         cam[1] + fov['max_range_m']*math.sin(fov['bearing_max_rad']))], np.int32)
    ov = img[panel[1]:panel[3], panel[0]:panel[2]].copy()
    lay = ov.copy()
    cv2.fillPoly(lay, [poly - np.array([panel[0], panel[1]])], (238, 248, 255))
    cv2.addWeighted(lay, .75, ov, .25, 0, ov)
    cv2.polylines(ov, [poly - np.array([panel[0], panel[1]])], True, (176, 214, 240), 2, cv2.LINE_AA)
    img[panel[1]:panel[3], panel[0]:panel[2]] = ov

    # ---- ground-truth wall footprints: filled + hatched + labelled -------------------------
    for w in walls:
        a = v.p(w['cx'] - w['hx'], w['cy'] - w['hy'])
        b = v.p(w['cx'] + w['hx'], w['cy'] + w['hy'])
        cv2.rectangle(img, a, b, (206, 211, 219), -1)
        _rect_hatch(img, v, (w['cx'], w['cy'], w['hx'], w['hy'], w['height_m']))
        cv2.rectangle(img, a, b, (86, 92, 104), 2)
        label = 'h=%.2f m' % w['height_m']
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, .46, 1)
        lx, ly = int((a[0] + b[0])/2 - tw/2), int((a[1] + b[1])/2 + th/2)
        cv2.rectangle(img, (lx - 4, ly - th - 5), (lx + tw + 4, ly + 5), (255, 255, 255), -1)
        _text(img, label, (lx, ly), .46, (60, 64, 74), 1)

    # ---- ground-truth contact points ---------------------------------------------------------
    for c in contacts:
        if not c['visible']:
            continue
        q = v.p(c['world_x'], c['world_y'])
        cv2.circle(img, q, 5, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(img, q, 4, (150, 60, 120), -1, cv2.LINE_AA)

    # ---- detector segments, thick, coloured by distance to the nearest GT wall -------------
    for e in ego:
        a, b = v.p(e['world_x'], e['world_y']), v.p(e['world_x_last'], e['world_y_last'])
        col = _seg_colour(e['wall_dist_min_m'], hit_m, warn_m)
        cv2.line(img, a, b, (255, 255, 255), 9, cv2.LINE_AA)
        cv2.line(img, a, b, col, 6, cv2.LINE_AA)
        for q, dd in ((a, e['wall_dist_first_m']), (b, e['wall_dist_last_m'])):
            cv2.circle(img, q, 6, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(img, q, 5, _seg_colour(dd, hit_m, warn_m), -1, cv2.LINE_AA)

    # ---- robot: triangle at the pose, heading line, camera nadir ---------------------------
    fwd = np.array([math.cos(rob['yaw_rad']), math.sin(rob['yaw_rad'])])
    lat = np.array([-fwd[1], fwd[0]])
    base = np.array([rob['x'], rob['y']])
    tri = [v.p(*(base + fwd*.26)), v.p(*(base - fwd*.20 + lat*.16)), v.p(*(base - fwd*.20 - lat*.16))]
    cv2.fillPoly(img, [np.array(tri, np.int32)], (40, 60, 130))
    cv2.polylines(img, [np.array(tri, np.int32)], True, (255, 255, 255), 2, cv2.LINE_AA)
    hp = v.p(*(base + fwd*.85))
    cv2.line(img, v.p(*base), hp, (40, 60, 130), 3, cv2.LINE_AA)
    q = v.p(*base)
    cv2.circle(img, q, 4, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(img, q, 3, (40, 60, 130), -1, cv2.LINE_AA)
    _text(img, 'robot r1  (%.2f, %.2f)' % (rob['x'], rob['y']),
          (q[0] + 14, q[1] + 22), .5, (40, 60, 130), 1)
    qc = v.p(*cam)
    cv2.drawMarker(img, qc, (200, 90, 40), cv2.MARKER_CROSS, 16, 2, cv2.LINE_AA)
    _text(img, 'cam z=%.3f m' % rob['cam_z'], (qc[0] - 96, qc[1] + 30), .44, (200, 90, 40), 1)

    # ---- ticks, scale bar, north arrow -------------------------------------------------------
    for gx in range(math.ceil(x0), int(x1) + 1):
        q = v.p(gx, y0)
        cv2.line(img, (q[0], q[1] - 5), (q[0], q[1] + 5), (120, 126, 136), 1, cv2.LINE_AA)
        _text(img, '%g' % gx, (q[0] - 9, q[1] + 21), .44, (110, 116, 126), 1)
    for gy in range(math.ceil(y0), int(y1) + 1):
        q = v.p(x0, gy)
        cv2.line(img, (q[0] - 5, q[1]), (q[0] + 5, q[1]), (120, 126, 136), 1, cv2.LINE_AA)
        _text(img, '%g' % gy, (q[0] - 40, q[1] + 5), .44, (110, 116, 126), 1)
    _text(img, 'x (m)', (v.p(x1, y0)[0] - 34, v.p(x1, y0)[1] + 44), .5, (90, 96, 106), 1)
    _text(img, 'y (m)', (v.p(x0, y1)[0] - 42, v.p(x0, y1)[1] - 12), .5, (90, 96, 106), 1)

    sb = 1.0
    bx, by = panel[0] + 26, panel[3] - 34
    L = int(round(sb*m2px))
    cv2.line(img, (bx, by), (bx + L, by), (40, 40, 40), 4, cv2.LINE_AA)
    for i in range(3):
        px_ = bx + int(L*i/2)
        cv2.line(img, (px_, by - 7), (px_, by + 7), (40, 40, 40), 3, cv2.LINE_AA)
    _text(img, '0', (bx - 5, by - 12), .45, (40, 40, 40), 1)
    _text(img, '1 m', (bx + L - 12, by - 12), .45, (40, 40, 40), 1)

    nx, ny = v.p(x1 - .55, y1 - .30)
    cv2.arrowedLine(img, (nx, ny + 34), (nx, ny), (70, 70, 70), 2, cv2.LINE_AA, tipLength=.35)
    _text(img, 'N', (nx - 5, ny - 8), .5, (70, 70, 70), 1)

    # ---- title -------------------------------------------------------------------------------
    _text(img, 'Ego wall map  -  frame %d  -  sim_time %.2f s' % (rec['frame'], rec['sim_time']),
          (58, 52), .95, (24, 24, 24), 2)
    sub = ('robot (%.2f, %.2f)  yaw %+.1f deg  %s  servo3=%d  cam_z=%.3f m  |  '
           '%d GT contacts in view  %d detector columns  %d segments'
           % (rob['x'], rob['y'], math.degrees(rob['yaw_rad']),
              'loaded' if rob['loaded'] else 'unloaded', rob['servo_3'], rob['cam_z'],
              rec['counts']['n_contacts_total'], rec['counts']['n_detector_columns'],
              rec['counts']['n_segments']))
    _text(img, sub, (58, 82), .52, (78, 84, 94), 1)

    # ---- legend ------------------------------------------------------------------------------
    y = legend[1] + 34
    _text(img, 'LEGEND', (legend[0] + 18, y), .6, (24, 24, 24), 2)
    y += 20

    def head(s):
        nonlocal y
        y += 22
        _text(img, s, (legend[0] + 18, y), .5, (110, 116, 126), 1)
        y += 12

    def row(sample, s):
        """sample = (line_colour, line_thickness, dot_colour, dot_radius); thickness 0 = dot only."""
        nonlocal y
        if sample[1] > 0:
            cv2.line(img, (legend[0] + 20, y), (legend[0] + 68, y), sample[0],
                     sample[1], cv2.LINE_AA)
        if sample[2] is not None:
            cv2.circle(img, (legend[0] + 44, y), sample[3], (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(img, (legend[0] + 44, y), max(sample[3] - 1, 1), sample[2], -1, cv2.LINE_AA)
        _text(img, s, (legend[0] + 80, y + 5), .45, (40, 40, 40), 1)
        y += 26

    head('GROUND TRUTH  (static_map.json + trajectory.jsonl)')
    a = v.p(walls[0]['cx'] - walls[0]['hx'], walls[0]['cy'] - walls[0]['hy'])
    b = v.p(walls[0]['cx'] + walls[0]['hx'], walls[0]['cy'] + walls[0]['hy'])
    cv2.rectangle(img, (legend[0] + 20, y - 10), (legend[0] + 68, y + 8), (206, 211, 219), -1)
    cv2.rectangle(img, (legend[0] + 20, y - 10), (legend[0] + 68, y + 8), (86, 92, 104), 2)
    _text(img, 'wall footprint (h labelled)', (legend[0] + 80, y + 5), .45, (40, 40, 40), 1)
    y += 26
    row(((150, 60, 120), 0, (150, 60, 120), 4), 'GT contact (ground truth)')
    poly2 = np.array([[legend[0] + 20, y + 9], [legend[0] + 44, y - 9], [legend[0] + 68, y + 9]],
                     np.int32)
    lay2 = img.copy()
    cv2.fillPoly(lay2, [poly2], (238, 248, 255))
    cv2.addWeighted(lay2, .75, img, .25, 0, img)
    cv2.polylines(img, [poly2], True, (176, 214, 240), 2, cv2.LINE_AA)
    _text(img, 'camera FOV wedge (6 m)', (legend[0] + 80, y + 5), .45, (40, 40, 40), 1)
    y += 26
    cv2.drawMarker(img, (legend[0] + 44, y), (200, 90, 40), cv2.MARKER_CROSS, 14, 2, cv2.LINE_AA)
    _text(img, 'camera nadir', (legend[0] + 80, y + 5), .45, (40, 40, 40), 1)
    y += 26

    head('DETECTOR  (height_free_wall, own image + own servo only)')
    for probe, s in ((0., '<= %.2f m  on the wall' % hit_m),
                     ((hit_m + warn_m)/2, '<= %.2f m  offset' % warn_m),
                     (warn_m + 1., '> %.2f m  offset' % warn_m)):
        c = _seg_colour(probe, hit_m, warn_m)
        row((c, 6, c, 4), s)
    row(((40, 60, 130), 3, None, 0), 'robot + heading')
    y += 10

    head('DISTANCE TO NEAREST GT WALL (segment endpoints)')
    ds = [e['wall_dist_min_m'] for e in ego]
    if ds:
        _text(img, 'n segments          %d' % len(ego), (legend[0] + 20, y), .46, (40, 40, 40), 1)
        y += 22
        _text(img, 'median              %.3f m' % float(np.median(ds)),
              (legend[0] + 20, y), .46, (40, 40, 40), 1)
        y += 22
        _text(img, 'max                 %.3f m' % float(np.max(ds)),
              (legend[0] + 20, y), .46, (40, 40, 40), 1)
        y += 22
        _text(img, 'within %.2f m        %d / %d' % (hit_m, sum(1 for d in ds if d <= hit_m), len(ds)),
              (legend[0] + 20, y), .46, (40, 40, 40), 1)
    else:
        _text(img, 'no segments on this frame', (legend[0] + 20, y), .46, (90, 96, 106), 1)

    y += 34
    _text(img, 'ground truth is used for drawing and', (legend[0] + 18, y), .42, (130, 136, 146), 1)
    _text(img, 'these statistics only - it never reaches', (legend[0] + 18, y + 18), .42, (130, 136, 146), 1)
    _text(img, 'height_free_wall.detect.', (legend[0] + 18, y + 36), .42, (130, 136, 146), 1)

    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), img):
        raise IOError(f'cv2.imwrite failed: {path}')
    return path


# ---------------------------------------------------------------------------- statistics
def alignment_stats(records: list, hit_m=DEFAULT_HIT_M):
    """Segment-endpoint distance to the nearest ground-truth wall, over every frame."""
    per_seg, per_end, per_frame = [], [], []
    for rec in records:
        d = []
        for e in rec['ego_walls']:
            per_seg.append(e['wall_dist_min_m'])
            per_end += [e['wall_dist_first_m'], e['wall_dist_last_m']]
            d.append(e['wall_dist_min_m'])
        if d:
            per_frame.append(float(np.median(d)))
    if not per_seg:
        return {'n_segments': 0, 'n_endpoints': 0, 'n_frames_with_segments': 0}
    ps, pe, pf = map(np.asarray, (per_seg, per_end, per_frame))
    return {
        'note': 'wall_probe.dist_to_walls from each detector segment endpoint to the nearest '
                'ground-truth wall footprint; 0 means the endpoint lies on a wall',
        'n_segments': int(ps.size), 'n_endpoints': int(pe.size),
        'n_frames_with_segments': int(pf.size),
        'segment_median_m': round(float(np.median(ps)), 4),
        'segment_max_m': round(float(np.max(ps)), 4),
        'endpoint_median_m': round(float(np.median(pe)), 4),
        'endpoint_p90_m': round(float(np.percentile(pe, 90)), 4),
        'endpoint_max_m': round(float(np.max(pe)), 4),
        'per_frame_median_of_medians_m': round(float(np.median(pf)), 4),
        'endpoints_within_%.2fm' % hit_m: int((pe <= hit_m).sum()),
        'endpoint_share_within_%.2fm' % hit_m: round(float((pe <= hit_m).mean()), 4),
    }


def aggregate_row_range(records: list) -> dict:
    """Median signed row / range error of the detector against ground truth.

    A systematic offset in these numbers is the thing the top-down map is for: the
    segments are drawn where the detector says they are, and if they sit consistently
    short of the grey rectangles the numbers here say by how much.
    """
    rows, rngs, n = [], [], 0
    for rec in records:
        c = rec['detector_vs_gt']
        n += c['n_columns_compared']
        for key, bucket in (('row_error_med_px', rows), ('range_error_med_m', rngs)):
            if c.get(key) is not None:
                bucket.append(c[key])
    if not rows:
        return {'n_columns_compared': n, 'note': 'no column had both a visible GT wall and a detection'}
    return {'n_columns_compared': n,
            'note': 'median per frame, over columns where a GT wall is visible and the detector '
                    'fired. Positive = detector places the contact closer to the robot.',
            'row_error_med_px_of_frame_medians': round(float(np.median(rows)), 3),
            'row_error_median_of_all_frames_same_sign': bool(
                all(r > 0 for r in rows) or all(r < 0 for r in rows)),
            'range_error_med_m_of_frame_medians': round(float(np.median(rngs)), 3),
            'range_error_median_of_all_frames_same_sign': bool(
                all(r > 0 for r in rngs) or all(r < 0 for r in rngs)),
            'n_frames_with_comparison': len(rows)}


# --------------------------------------------------------------------------------- main
def parse_frames(spec: str, ctx, every: int):
    if spec.strip().lower() == 'all':
        return [i for i in range(0, len(ctx['frames']), max(1, every))
                if visible_columns_only(ctx, i) >= MIN_VISIBLE_COLS]
    return [int(x) for x in spec.split(',') if x.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--episode', required=True)
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--frames', default=','.join(str(i) for i in DEFAULT_FRAMES),
                    help='comma-separated frame indices, or "all" for every wall-visible frame')
    ap.add_argument('--out', required=True, help='JSON path')
    ap.add_argument('--png', default=None, help='optional PNG path (one top-down figure)')
    ap.add_argument('--png-frame', type=int, default=None,
                    help='frame to draw; default is the requested frame with the most segments')
    ap.add_argument('--all-every', type=int, default=1, help='stride for --frames all')
    ap.add_argument('--hit-m', type=float, default=DEFAULT_HIT_M)
    ap.add_argument('--warn-m', type=float, default=DEFAULT_WARN_M)
    args = ap.parse_args()

    ctx = load_episode(Path(args.episode), args.robot)
    chosen = parse_frames(args.frames, ctx, args.all_every)
    for i in chosen:
        if not 0 <= i < len(ctx['frames']):
            raise IndexError(f'frame {i} out of range (0..{len(ctx["frames"]) - 1})')
    print(f'frames to dump: {len(chosen)}  ({chosen[:12]}{" ..." if len(chosen) > 12 else ""})')

    records = [frame_record(ctx, i) for i in chosen]

    png_frame = args.png_frame
    if args.png and png_frame is None:
        scored = [r for r in records if r['counts']['n_segments'] > 0]
        pool = scored or records
        png_frame = max(pool, key=lambda r: (r['counts']['n_segments'], -r['frame']))['frame']

    payload = {
        'episode': str(ctx['ep']), 'robot': args.robot,
        'frames_jsonl': ctx['frames_rel'], 'map_id': ctx['static_map'].get('map_id'),
        'max_range_m': MAX_RANGE_M, 'min_visible_cols': MIN_VISIBLE_COLS,
        'chosen_frames': [int(r['frame']) for r in records],
        'frame_selection': ('curated set' if args.frames.strip().lower() != 'all' else
                            f'all wall-visible frames (stride {max(1, args.all_every)})'),
        'pose_lookup': verify_pose(ctx),
        'frozen_detector_params': rp.FROZEN_DETECTOR,
        'seed_bias_rad': rp.SEED_BIAS,
        'gt_use': ('drawing and the distance statistics only. height_free_wall.detect and '
                   'link_segments receive the own undistorted image, the own commanded servo '
                   'and the own load state, nothing else.'),
        'gt_geometry': GT_CONVENTION,
        'gt_convention': GT_CONVENTION,
        'alignment': alignment_stats(records, args.hit_m),
        'detector_vs_gt': aggregate_row_range(records),
        'png_frame': png_frame,
        'frames': records,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(f'wrote {out}  ({out.stat().st_size/1024:.1f} KiB)')

    if args.png:
        rec = next(r for r in records if r['frame'] == png_frame)
        render_png(rec, Path(args.png), args.hit_m, args.warn_m)
        print(f'wrote {args.png}  (frame {png_frame}, {rec["counts"]["n_segments"]} segments)')

    al = payload['alignment']
    if al['n_segments']:
        print('\n--- detector vs ground truth ---')
        print('  pose lookup aligned           : %s' % payload['pose_lookup']['aligned'])
        print('  segments / endpoints          : %d / %d'
              % (al['n_segments'], al['n_endpoints']))
        print('  distance to nearest GT wall   : median %.3f m, p90 %.3f m, max %.3f m'
              % (al['endpoint_median_m'], al['endpoint_p90_m'], al['endpoint_max_m']))
        print('  endpoints within %.2f m        : %d / %d (%.1f%%)'
              % (args.hit_m, al['endpoints_within_%.2fm' % args.hit_m], al['n_endpoints'],
                 100*al['endpoint_share_within_%.2fm' % args.hit_m]))
        dv = payload['detector_vs_gt']
        if dv.get('n_frames_with_comparison'):
            print('  per-column row error            : median %+.2f px (same sign every frame: %s)'
                  % (dv['row_error_med_px_of_frame_medians'], dv['row_error_median_of_all_frames_same_sign']))
            print('  per-column range error          : median %+.3f m  (same sign every frame: %s)'
                  % (dv['range_error_med_m_of_frame_medians'], dv['range_error_median_of_all_frames_same_sign']))
        xc = records[0]['gt_crosscheck_vs_score_harness']
        print('  gt convention (ray from cm.q0)  : lateral offset median %.4f m / max %.4f m; '
              'hit-set disagreements vs score_harness %d, visible %d; median row diff %.2f px'
              % (xc['lateral_offset_m_median'], xc['lateral_offset_m_max'],
                 xc['n_hit_disagreements'], xc['n_visible_disagreements'],
                 xc['median_row_difference_px'] or 0.))
    print('\nper-frame:')
    print('  %-6s %-7s %-6s %-8s %-6s %-5s %-6s %-8s %-8s'
          % ('frame', 't', 's3', 'loaded', 'gtcol', 'det', 'segs', 'med_d_m', 'max_d_m'))
    for r in records:
        d = [e['wall_dist_min_m'] for e in r['ego_walls']] or [float('nan')]
        print('  %-6d %-7.2f %-6d %-8s %-6d %-5d %-6d %-8.3f %-8.3f'
              % (r['frame'], r['sim_time'], r['robot']['servo_3'], r['robot']['loaded'],
                 r['counts']['n_contacts_total'], r['counts']['n_detector_columns'],
                 r['counts']['n_segments'], float(np.median(d)), float(np.max(d))))


if __name__ == '__main__':
    main()
