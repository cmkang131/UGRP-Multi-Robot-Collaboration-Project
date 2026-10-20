"""Carry-pose candidates and render-test measures for the E2E NAV_CARRY hold rule.

CPU-only derivation (no simulator):

* (a) ``act_lift_end``: the ACT C2c-HO4 issued PWM at the grasp done tick
  (``summary.json`` ``issued_done_times.grasp`` matched to
  ``actor-actions.jsonl``), medoid over all worlds that issued a grasp done.
* (b) ``teacher_hold_max_pitch``: among teacher dataset rows of the grasp skill
  with the gripper closed (PWM1 <= 1600) and a stable holding phase, the
  distinct PWM vector with the highest tool pitch
  (``harness.visual_arm_v3.tool_pose(...).pitch_deg``); ties -> most rows.
* (c) ``carry_look_v1``: gripper (1), elbow (4) and yaw (6) from (a); only
  shoulder (5) and wrist (3) move, to the grid pose whose SDK camera
  (``camera_extrinsics``) is closest to the SEARCH camera (see carry_look_v1).
* reference ``search_grip_ref`` (= ``gripper_hold_arm_search_v1``): SEARCH with
  the gripper PWM of (a).  Not a candidate of the verdict; rendered so the
  fallback's occlusion is known.

Servo map: 1 gripper, 3 wrist, 4 elbow, 5 shoulder, 6 yaw
(``scripts/warp_act_backend.py:274``).  Render-side measures and the
pre-registered verdict live here so they are unit-tested on CPU.
"""
from __future__ import annotations

import glob
import hashlib
import json
import math
from pathlib import Path

SCHEMA = 'ugrp.e2e_min.carry_pose.v1'
SERVOS = (1, 3, 4, 5, 6)
CANDIDATES = ('act_lift_end', 'teacher_hold_max_pitch', 'carry_look_v1')
REFERENCE = 'search_grip_ref'
GRIPPER_CLOSED_MAX = 1600
HOLD_PHASES = ('hold', 'lift_settle', 'lookback', 'lookback_pose', 'lookback_settle',
               'verify_lift')
#: Render positions on each nav lane (m), and the verdict position.
RENDER_X = (1.5, 2.0, 2.8, 3.5)
VERDICT_X = 2.8
MIN_COMPONENT_PX = 600
MAX_OCCLUSION = 0.30
#: Sum of |dRGB| over 3 channels above which a pixel counts as changed by the
#: cube (JPEG q82 noise between two renders of the same state is below this).
OCCLUSION_DIFF = 40


def _key(pwm):
    return tuple(int(pwm[str(s)] if str(s) in pwm else pwm[s]) for s in SERVOS)


def _pwm(key):
    return {str(s): int(v) for s, v in zip(SERVOS, key)}


def search_pwm():
    from harness.active_camera import SEARCH
    return {str(k): int(v) for k, v in SEARCH.items()}


def camera_pose(pwm):
    """SDK camera origin (base frame, m) and optical-axis pitch below horizontal."""
    from harness.visual_arm_v3 import camera_extrinsics, tool_pose
    pose = {s: int(pwm[str(s)]) for s in SERVOS}
    origin, axes = camera_extrinsics(pose)
    optical = [float(v) for v in axes[2]]
    return dict(origin_m=[round(float(v), 4) for v in origin],
                pitch_down_deg=round(math.degrees(math.asin(max(-1.0, min(1.0, -optical[2])))), 2),
                tool_pitch_deg=round(float(tool_pose(pose).pitch_deg), 2))


def grasp_done_pwms(run_root):
    """Issued PWM at each world's grasp done tick in C2c-HO4 runs (raw files)."""
    rows = []
    pattern = str(Path(run_root) / 'C2c-ho4-rep*' / 'R8-diag' / 'group-*' / 'evaluation' / 'actor-actions.jsonl')
    for path in sorted(glob.glob(pattern)):
        folder = Path(path).parent
        plans = json.loads((folder / 'initial-plans.json').read_text())['episodes']
        scores = {r['seed']: r for r in json.loads((folder / 'summary.json').read_text())['student_scores']}
        actions = [json.loads(line) for line in Path(path).read_text().splitlines() if line]
        for i, plan in enumerate(plans):
            done = ((scores.get(plan['seed']) or {}).get('issued_done_times') or {}).get('grasp')
            if done is None:
                continue
            match = [a['actions'][i]['command'] for a in actions
                     if abs(float(a['actions'][i]['command']['t']) - float(done)) < 0.051]
            if not match:
                raise ValueError(f'grasp done tick missing in {path} world {i}')
            rows.append(dict(run=str(folder.relative_to(Path(run_root))), seed=plan['seed'],
                             t=round(float(done), 2), pwm=_pwm(_key(match[0]['pwm']))))
    return rows


def medoid(pwms):
    """Real PWM vector closest (L1) to the per-servo median; deterministic."""
    if not pwms:
        raise ValueError('no PWM rows')
    keys = [_key(p) for p in pwms]
    median = []
    for j in range(len(SERVOS)):
        values = sorted(k[j] for k in keys)
        median.append(values[len(values) // 2])
    best = min(range(len(keys)), key=lambda i: (sum(abs(a - b) for a, b in zip(keys[i], median)), i))
    return _pwm(keys[best]), _pwm(tuple(median))


def teacher_hold_max_pitch(dataset_rows):
    """(b) from teacher dataset rows ({'skill','teacher_phase','issued_pwm'})."""
    from harness.visual_arm_v3 import tool_pose
    counts, phases = {}, {}
    for row in dataset_rows:
        pwm = row['issued_pwm']
        if row.get('skill') != 'grasp' or int(pwm['1']) > GRIPPER_CLOSED_MAX:
            continue
        if row.get('teacher_phase') not in HOLD_PHASES:
            continue
        key = _key(pwm)
        counts[key] = counts.get(key, 0) + 1
        phases.setdefault(key, set()).add(row['teacher_phase'])
    if not counts:
        raise ValueError('no closed-gripper teacher hold rows')
    ranked = sorted(counts, key=lambda k: (-round(tool_pose(dict(zip(SERVOS, k))).pitch_deg, 6),
                                           -counts[k], k))
    best = ranked[0]
    return _pwm(best), dict(rows=counts[best], phases=sorted(phases[best]),
                            distinct_hold_vectors=len(counts))


LOOK_PWM_RANGE = (550, 2450)
LOOK_TOOL_PITCH_DEG = (-90.0, 0.0)


def carry_look_v1(lift_pwm, *, step=10):
    """(c): gripper/elbow/yaw of (a); shoulder (5) and wrist (3) only are moved.

    Grid search (``step`` PWM, inside LOOK_PWM_RANGE away from the 500/2500
    clamps) for the SDK camera pose closest to the SEARCH camera:
    cost = |d pitch_deg| + 100 * (|d z_m| + |d x_m|), subject to the tool
    pitch staying in LOOK_TOOL_PITCH_DEG (gripper not raised above horizontal
    or inverted, so the held cube is not tipped out).  Ties: least PWM change
    from (a).
    """
    target = camera_pose(search_pwm())
    lo, hi = LOOK_PWM_RANGE
    best = None
    for shoulder in range(lo, hi + 1, step):
        for wrist in range(lo, hi + 1, step):
            pwm = dict(lift_pwm, **{'5': shoulder, '3': wrist})
            cam = camera_pose(pwm)
            if not LOOK_TOOL_PITCH_DEG[0] <= cam['tool_pitch_deg'] <= LOOK_TOOL_PITCH_DEG[1]:
                continue
            cost = (abs(cam['pitch_down_deg'] - target['pitch_down_deg'])
                    + 100.0 * (abs(cam['origin_m'][2] - target['origin_m'][2])
                               + abs(cam['origin_m'][0] - target['origin_m'][0])))
            moved = abs(shoulder - int(lift_pwm['5'])) + abs(wrist - int(lift_pwm['3']))
            key = (round(cost, 6), moved, shoulder, wrist)
            if best is None or key < best[0]:
                best = (key, pwm)
    if best is None:
        raise ValueError('no carry_look_v1 pose satisfies the tool-pitch constraint')
    return {str(k): int(v) for k, v in best[1].items()}


def build_candidates(run_root, dataset_path):
    run_root, dataset_path = Path(run_root), Path(dataset_path)
    done_rows = grasp_done_pwms(run_root)
    lift, median = medoid([r['pwm'] for r in done_rows])
    rows = [json.loads(line) for line in dataset_path.read_text().splitlines() if line]
    teacher, teacher_meta = teacher_hold_max_pitch(rows)
    look = carry_look_v1(lift)
    search = search_pwm()
    reference = dict(search, **{'1': lift['1']})
    poses = {'act_lift_end': lift, 'teacher_hold_max_pitch': teacher, 'carry_look_v1': look,
             REFERENCE: reference}
    return dict(
        schema=SCHEMA, servo_map='1 gripper, 3 wrist, 4 elbow, 5 shoulder, 6 yaw',
        candidates=list(CANDIDATES), reference=REFERENCE,
        poses=poses, camera={k: camera_pose(v) for k, v in poses.items()},
        search=dict(pwm=search, camera=camera_pose(search)),
        provenance=dict(
            act_lift_end=dict(source='C2c-HO4 actor-actions.jsonl at summary issued_done_times.grasp',
                              run_root=str(run_root), worlds=len(done_rows),
                              per_servo_median=median, rows=done_rows),
            teacher_hold_max_pitch=dict(source=str(dataset_path),
                                        dataset_sha256=hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
                                        hold_phases=list(HOLD_PHASES), **teacher_meta),
            carry_look_v1=dict(rule='gripper/elbow/yaw of act_lift_end; shoulder+wrist grid '
                               'search toward the SEARCH camera pose',
                               pwm_range=list(LOOK_PWM_RANGE),
                               tool_pitch_deg=list(LOOK_TOOL_PITCH_DEG), step=10),
            search_grip_ref='SEARCH arm + act_lift_end gripper (gripper_hold_arm_search_v1)'),
    )


# -- render-side measures (CPU, numpy) ------------------------------------
def occlusion_fraction(rgb_on, rgb_off, threshold=OCCLUSION_DIFF):
    """Frame fraction whose RGB changed when the held cube is present."""
    import numpy as np
    a = np.asarray(rgb_on, dtype=np.int32)
    b = np.asarray(rgb_off, dtype=np.int32)
    if a.shape != b.shape:
        raise ValueError('frame shape mismatch')
    return float((np.abs(a - b).sum(axis=-1) > threshold).mean())


def mask_loss(mask_off, mask_on):
    """Fraction of zone-band pixels (cube absent) that are lost with the cube."""
    import numpy as np
    off = np.asarray(mask_off, dtype=bool)
    on = np.asarray(mask_on, dtype=bool)
    total = int(off.sum())
    return None if total == 0 else float((off & ~on).sum() / total)


def verdict(rows, *, x=VERDICT_X, min_px=MIN_COMPONENT_PX, max_occ=MAX_OCCLUSION):
    """Pre-registered decision.

    ``rows``: dicts with pose, robot, x, largest_component_px (cube present) and
    occlusion_fraction.  A candidate passes iff at ``x`` BOTH robots have a
    v230 component >= ``min_px`` and occlusion < ``max_occ``.  The first
    passing candidate in CANDIDATES order (least arm motion after grasp first)
    is adopted; none -> ``gripper_hold_arm_search_v1``.  Missing rows fail.
    """
    per = {}
    for pose in CANDIDATES:
        cells = {r['robot']: r for r in rows
                 if r['pose'] == pose and abs(float(r['x']) - x) < 1e-6}
        checks = {}
        for robot in ('r1', 'r2'):
            cell = cells.get(robot)
            checks[robot] = bool(cell is not None
                                 and int(cell['largest_component_px']) >= min_px
                                 and float(cell['occlusion_fraction']) < max_occ)
        per[pose] = dict(passed=all(checks.values()), robots=checks)
    adopted = next((p for p in CANDIDATES if per[p]['passed']), None)
    return dict(x=x, min_component_px=min_px, max_occlusion=max_occ, candidates=per,
                adopted=adopted or 'gripper_hold_arm_search_v1',
                fallback=adopted is None,
                note=('fallback requires a separate drop-risk test' if adopted is None
                      else 'adopted pose still needs a nav ground-projection refit'))


def band_mask(rgb):
    """v230 zone-B band mask (same thresholds as GPU_CALIB_V230)."""
    import numpy as np
    from harness.e2ewarp_selfnav import GPU_CALIB_V230, hue_degrees_to_opencv, rgb_to_hsv
    h_deg, s, v = rgb_to_hsv(np.asarray(rgb, dtype=np.uint8))
    h = hue_degrees_to_opencv(h_deg)
    band = GPU_CALIB_V230
    return ((h >= band['hue_cv'][0]) & (h <= band['hue_cv'][1]) & (s >= band['sat_min'])
            & (v >= band['val'][0]) & (v <= band['val'][1]))


def measure_frame(rgb):
    """Largest v230 component, its last bbox row (inclusive) and detector output."""
    import numpy as np
    from harness.e2ewarp_selfnav import (BEARING_POSITIVE_LEFT, GpuCalibZoneDetector,
                                         largest_component)
    mask = band_mask(rgb)
    comp = largest_component(mask)
    detections = GpuCalibZoneDetector(profile='gpu_calib_v230',
                                      bearing_convention=BEARING_POSITIVE_LEFT)(np.asarray(rgb, dtype=np.uint8))
    return dict(mask=mask,
                largest_component_px=0 if comp is None else int(comp['area']),
                bbox_bottom_row=None if comp is None else int(comp['bottom']) - 1,
                detections_v230=len(detections))
