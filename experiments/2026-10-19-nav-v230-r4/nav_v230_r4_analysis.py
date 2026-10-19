#!/usr/bin/env python3
"""Eval-only recount for the nav v230-r4 runs (no success claim).

Reads one ``run_e2e_warp --mode nav`` run directory (pair or the r4 solo
diagnostic) plus its admission directory, and re-derives every number the r4
report needs, from raw rows only:

- source/pin equality (admission queue, run queue, RUN_META, result);
- per-robot detection ticks, largest component, first detection, forward cap use,
  ``drive_reason`` distribution, arming/claim/``NO_CLAIM``;
- the r3-unchanged claim: ``d_proj`` at the claim, path, the armed bearing ``u``,
  the component-centre bearing and the r4 slot offset;
- eval-only GT: claim/final inside the authored zone rectangle, west-edge margin,
  armed->claim GT displacement vs odometry, GT yaw next to the odometry yaw;
- the r4 contact ledger (MJWarp contact buffer) plus the minimum base-centre
  distance and minimum base collision-box separation from raw qpos;
- the r4 step ③ drift decomposition: commanded yaw (wheel differential x
  calibration) vs odometry yaw vs GT yaw, forward gain (slip), yaw gain, sign
  agreement, lateral drift, and coasting after the wheels are held.

The script writes one JSON report and never writes into the run directory, so the
raw ``sha256.json`` stays the run's own.  It never re-enters the run and never
claims physical, E2E or acceptance success.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

SCHEMA = 'ugrp.e2ewarp.nav_v230_r4_analysis.v1'
TICK_HZ = 10.0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    return json.loads(path.read_text())


def inside(xy, center, half):
    return bool(abs(float(xy[0]) - float(center[0])) <= float(half[0])
                and abs(float(xy[1]) - float(center[1])) <= float(half[1]))


def wrap_deg(angle):
    return (float(angle) + 180.0) % 360.0 - 180.0


def component_px(landmark):
    bbox = (landmark or {}).get('bbox')
    if not bbox or len(bbox) != 4:
        return 0
    left, top, right, bottom = (int(v) for v in bbox)
    return max(0, right - left) * max(0, bottom - top)


def zone_b_largest(row):
    memory = (row.get('own_navigation') or {}).get('self_centric_memory') or []
    hits = [m for m in memory if str(m.get('kind')) == 'zone_B']
    return max(hits, key=component_px) if hits else None


def fresh_zone_b(row):
    sim_s = float(row.get('sim_s') or 0.0)
    memory = (row.get('own_navigation') or {}).get('self_centric_memory') or []
    hits = [m for m in memory if str(m.get('kind')) == 'zone_B'
            and abs(float(m.get('last_seen_s') or -1.0) - sim_s) < 1e-6]
    return max(hits, key=component_px) if hits else None


def first_index(rows, predicate):
    return next((i for i, row in enumerate(rows) if predicate(row)), None)


def gt_pose(qpos, adr):
    """World-frame base xy + yaw (deg) from the free-joint qpos row (eval only)."""
    pose = np.asarray(qpos, dtype=float)
    x, y = float(pose[adr]), float(pose[adr + 1])
    qw, qx, qy, qz = (float(v) for v in pose[adr + 3:adr + 7])
    yaw = math.degrees(math.atan2(2.0 * (qw * qz + qx * qy),
                                  1.0 - 2.0 * (qy * qy + qz * qz)))
    return x, y, wrap_deg(yaw)


def track(run, robot, qpos):
    geometry = json.loads((Path(run) / 'world-00' / 'eval-geometry.json').read_text())
    if robot not in geometry['robot_qpos_adr']:
        raise ValueError('robot missing from eval geometry: ' + robot)
    adr = int(geometry['robot_qpos_adr'][robot])
    poses = [gt_pose(qpos[i, 0], adr) for i in range(qpos.shape[0])]
    xy = np.asarray([[p[0], p[1]] for p in poses], dtype=float)
    yaw = np.asarray([p[2] for p in poses], dtype=float)
    return geometry, adr, xy, yaw


def command_kinematics(commands, robot, constants):
    """Per-tick own-command forward/yaw from the raw command rows (calibrated)."""
    rows = sorted([c for c in commands if str(c.get('robot')) == robot],
                  key=lambda c: float(c.get('t') or 0.0))
    forward = float(constants['forward_m_per_pct_s'])
    yaw = float(constants['yaw_deg_per_pct_s'])
    out = []
    for row in rows:
        wheels = [float(w) for w in (row.get('wheels') or [0.0] * 4)]
        durations = [float(d) for d in (row.get('duration_s') or [0.0] * 4)]
        # The issued rows carry normalized duty in [-1, 1]; the calibration is
        # per *percent*-second (OwnCommandOdometry.wheels_percent), so convert.
        percent = [w * 100.0 for w in wheels]
        f = sum(w * dt for w, dt in zip(percent, durations)) / 4.0
        t = ((percent[1] * durations[1] + percent[3] * durations[3])
             - (percent[0] * durations[0] + percent[2] * durations[2])) / 4.0
        out.append(dict(t=float(row.get('t') or 0.0), forward_m=f * forward,
                        yaw_deg=t * yaw, moving=any(abs(w) > 0.0 for w in wheels)))
    return out


def _segments(own, commands, armed_i, claim_i):
    """Tick index ranges for the drift decomposition (inclusive start, exclusive end)."""
    n = min(len(own), len(commands))
    segments = {}
    end = claim_i if claim_i is not None else n
    segments['pre_armed'] = (0, armed_i if armed_i is not None else n)
    if armed_i is not None:
        segments['armed_to_claim'] = (armed_i, end)
    if claim_i is not None:
        segments['post_claim'] = (claim_i, n)
    return {k: v for k, v in segments.items() if v[1] > v[0]}


def _segment_stats(start, end, own, commands, xy, yaw_gt):
    """Commanded vs odometry vs GT motion over one tick range (diagnostic only).

    ``commands`` are calibrated per-tick rows (``command_kinematics``): the
    adapter's own wheel pulses converted with the injected percent-second
    calibration, i.e. the *commanded* yaw/forward in physical units.  The
    odometry is the adapter's own integration of the same rows; GT is the raw
    eval-only qpos.  Differences therefore decompose into (a) command->odometry
    (relay/differential realisation) and (b) odometry->GT (slip, contact).
    """
    n = min(end, len(own), len(commands))
    if n - start < 2:
        return None
    odom_pose = [own[i].get('odom_pose') for i in range(start, n)]
    cmd = commands[start:n]
    gt_steps, odom_steps, gt_yaw_steps = [], [], []
    for i in range(start + 1, n):
        gt_steps.append(xy[i] - xy[i - 1])
        gt_yaw_steps.append(wrap_deg(yaw_gt[i] - yaw_gt[i - 1]))
        prev, cur = own[i - 1].get('odom_pose'), own[i].get('odom_pose')
        odom_steps.append(None if prev is None or cur is None else
                          (float(cur[0]) - float(prev[0]), float(cur[1]) - float(prev[1]),
                           wrap_deg(float(cur[2]) - float(prev[2]))))
    keep = [i for i, o in enumerate(odom_steps) if o is not None]
    if len(keep) < 2:
        return None
    gt = np.asarray([gt_steps[i] for i in keep], dtype=float)
    od = np.asarray([[odom_steps[i][0], odom_steps[i][1]] for i in keep], dtype=float)
    gt_yaw_step = np.asarray([gt_yaw_steps[i] for i in keep], dtype=float)
    cmd_yaw = np.asarray([cmd[i + 1]['yaw_deg'] for i in keep], dtype=float)
    cmd_fwd = np.asarray([cmd[i + 1]['forward_m'] for i in keep], dtype=float)
    headings = np.radians(np.asarray([float((odom_pose[i + 1] or [0.0, 0.0, 0.0])[2])
                                      for i in keep]))
    gt_norm = float(np.linalg.norm(gt, axis=1).sum())
    od_norm = float(np.linalg.norm(od, axis=1).sum())
    forward_proj = float((gt[:, 0] * np.cos(headings) + gt[:, 1] * np.sin(headings)).sum())
    lateral = float((-gt[:, 0] * np.sin(headings) + gt[:, 1] * np.cos(headings)).sum())
    turning = np.abs(cmd_yaw) > 0.05
    turn_n = int(turning.sum())
    sign_match = int(np.sum(np.sign(cmd_yaw[turning]) == np.sign(gt_yaw_step[turning])))
    gains = (gt_yaw_step[turning] / cmd_yaw[turning]) if turn_n else np.asarray([])
    cw = cmd_yaw[turning]
    gw = gt_yaw_step[turning]
    forward_ratios = [(float(np.linalg.norm(gt[i])) / float(np.linalg.norm(od[i])), i)
                      for i in keep if float(np.linalg.norm(od[i])) > 1e-9]
    fwd_ratio = (float(np.mean([r for r, _ in forward_ratios])) if forward_ratios else None)
    return dict(
        ticks=int(len(keep)),
        sim_s=round(len(keep) / TICK_HZ, 3),
        command_forward_m=round(float(cmd_fwd.sum()), 4),
        command_yaw_deg=round(float(cmd_yaw.sum()), 3),
        odom_yaw_deg=round(float(sum(odom_steps[i][2] for i in keep)), 3),
        gt_yaw_deg=round(float(gt_yaw_step.sum()), 3),
        gt_path_m=round(gt_norm, 4),
        odom_path_m=round(od_norm, 4),
        gt_over_odom_path=(round(gt_norm / od_norm, 4) if od_norm > 0 else None),
        gt_forward_projection_m=round(forward_proj, 4),
        gt_lateral_m=round(lateral, 4),
        gt_forward_over_odom=(round(forward_proj / od_norm, 4) if od_norm > 0 else None),
        step_forward_gain=(None if fwd_ratio is None else round(fwd_ratio, 4)),
        yaw_gain_gt_over_odom=(round(float(gt_yaw_step.sum() / sum(odom_steps[i][2] for i in keep)), 4)
                               if abs(sum(odom_steps[i][2] for i in keep)) > 1e-9 else None),
        turning_ticks=turn_n,
        turning_yaw_gain_gt_over_command=(round(float(np.mean(gains)), 4) if turn_n else None),
        turning_yaw_gain_median=(round(float(np.median(gains)), 4) if turn_n else None),
        turn_sign_agreement=(round(sign_match / turn_n, 4) if turn_n else None),
        turn_sign_agreement_n=dict(match=sign_match, ticks=turn_n),
        gt_yaw_per_tick_left_cmd_deg=(round(float(gw[cw > 0].mean()), 4) if np.any(cw > 0) else None),
        gt_yaw_per_tick_right_cmd_deg=(round(float(gw[cw < 0].mean()), 4) if np.any(cw < 0) else None),
        command_yaw_per_tick_left_deg=(round(float(cw[cw > 0].mean()), 4) if np.any(cw > 0) else None),
        command_yaw_per_tick_right_deg=(round(float(cw[cw < 0].mean()), 4) if np.any(cw < 0) else None),
        zero_command_gt_yaw_drift_deg=round(float(gt_yaw_step[~turning].sum()), 3)
        if np.any(~turning) else None,
        zero_command_ticks=int((~turning).sum()),
        gt_vs_odom_heading_error_deg=round(float(np.degrees(np.arctan2(gt[:, 1], gt[:, 0])).mean()
                                                - np.degrees(np.arctan2(od[:, 1], od[:, 0])).mean()), 3)
        if gt_norm > 0 else None,
        diagnostic_only=True,
        note='world-frame GT is read for this table only; never a controller input',
    )


def timeline(own, commands, xy, yaw_gt, *, bin_s=1.0):
    """Per-bin (default 1 s) commanded/odometry/GT summary for the drift diagnosis."""
    step = max(1, int(round(bin_s * TICK_HZ)))
    out = []
    for start in range(0, min(len(own), len(commands), xy.shape[0]), step):
        end = min(start + step, len(own), len(commands), xy.shape[0])
        if end - start < 2:
            continue
        odom = own[end - 1].get('odom_pose')
        gt_step = float(np.linalg.norm(np.diff(xy[start:end], axis=0), axis=1).sum())
        odom_step = 0.0
        for i in range(start + 1, end):
            prev, cur = own[i - 1].get('odom_pose'), own[i].get('odom_pose')
            if prev is not None and cur is not None:
                odom_step += math.hypot(float(cur[0]) - float(prev[0]),
                                        float(cur[1]) - float(prev[1]))
        cmd_yaw = sum(commands[i]['yaw_deg'] for i in range(start + 1, end))
        gt_yaw_step = wrap_deg(float(yaw_gt[end - 1]) - float(yaw_gt[start]))
        out.append(dict(
            sim_s=round(start / TICK_HZ, 3),
            gt_xy=[round(float(v), 4) for v in xy[end - 1]],
            gt_yaw_deg=round(float(yaw_gt[end - 1]), 3),
            odom_yaw_deg=(None if odom is None else round(float(odom[2]), 3)),
            yaw_error_deg=(None if odom is None else round(
                wrap_deg(float(yaw_gt[end - 1]) - float(odom[2])), 3)),
            cmd_yaw_deg=round(float(cmd_yaw), 3),
            gt_yaw_step_deg=round(float(gt_yaw_step), 3),
            gt_step_m=round(gt_step, 4),
            odom_step_m=round(odom_step, 4),
            step_ratio=(round(gt_step / odom_step, 4) if odom_step > 1e-9 else None),
        ))
    return out


def yaw_error_summary(own, yaw_gt, *, threshold_deg=10.0, persist_ticks=10):
    """GT-vs-odometry yaw error: onset of a persistent divergence and its size.

    A persistent divergence is the signature of an external yaw torque (contact)
    rather than of a calibration gain: the odometry yaw keeps integrating the
    issued pulses while the measured yaw leaves it.
    """
    series = []
    for i, o in enumerate(own):
        pose = o.get('odom_pose')
        series.append(None if pose is None else wrap_deg(float(yaw_gt[i]) - float(pose[2])))
    onset = None
    for i, value in enumerate(series):
        if value is None or abs(value) < threshold_deg:
            continue
        window = series[i:i + persist_ticks]
        if len(window) == persist_ticks and all(v is not None and abs(v) >= threshold_deg
                                                for v in window):
            onset = i
            break
    defined = [(i, v) for i, v in enumerate(series) if v is not None]
    peak_i, peak_v = (max(defined, key=lambda item: abs(item[1])) if defined else (None, None))
    return dict(
        threshold_deg=threshold_deg, persist_ticks=persist_ticks,
        onset_index=onset, onset_s=(round(onset / TICK_HZ, 3) if onset is not None else None),
        onset_error_deg=(None if onset is None else round(series[onset], 3)),
        peak_abs_error_deg=(None if peak_v is None else round(abs(peak_v), 3)),
        peak_error_deg=(None if peak_v is None else round(peak_v, 3)),
        peak_s=(None if peak_i is None else round(peak_i / TICK_HZ, 3)),
        final_error_deg=(None if not defined else round(defined[-1][1], 3)),
        diagnostic_only=True,
    )


def coasting(own, commands, xy, yaw_gt):
    """GT motion in ticks whose issued wheels were all held (no command)."""
    moving = [c['moving'] for c in commands]
    rows = []
    for i in range(1, min(len(moving), xy.shape[0])):
        if not moving[i] and not moving[i - 1]:
            step = xy[i] - xy[i - 1]
            if float(np.linalg.norm(step)) > 1e-9:
                rows.append(dict(index=i, sim_s=round(i / TICK_HZ, 3),
                                 dx_m=round(float(step[0]), 4), dy_m=round(float(step[1]), 4),
                                 norm_m=round(float(np.linalg.norm(step)), 4),
                                 gt_yaw_deg=round(float(yaw_gt[i]), 3)))
    return dict(ticks=len(rows), total_m=round(sum(r['norm_m'] for r in rows), 4),
                rows=rows, diagnostic_only=True)


def _rect_corners(center, yaw_deg, half_x, half_y):
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    out = []
    for dx, dy in ((-half_x, -half_y), (half_x, -half_y), (half_x, half_y), (-half_x, half_y)):
        out.append((center[0] + dx * c - dy * s, center[1] + dx * s + dy * c))
    return out


def _point_segment(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0.0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    qx, qy = ax + t * dx, ay + t * dy
    return math.hypot(px - qx, py - qy)


def _segments_cross(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    return o1 * o2 <= 0.0 and o3 * o4 <= 0.0


def polygon_distance(poly_a, poly_b):
    """Minimum distance between two convex CCW polygons (0 when they overlap)."""
    for i in range(len(poly_a)):
        a, b = poly_a[i], poly_a[(i + 1) % len(poly_a)]
        for j in range(len(poly_b)):
            c, d = poly_b[j], poly_b[(j + 1) % len(poly_b)]
            if _segments_cross(a, b, c, d):
                return 0.0
    best = float('inf')
    for p in poly_a:
        for j in range(len(poly_b)):
            best = min(best, _point_segment(p, poly_b[j], poly_b[(j + 1) % len(poly_b)]))
    for p in poly_b:
        for i in range(len(poly_a)):
            best = min(best, _point_segment(p, poly_a[i], poly_a[(i + 1) % len(poly_a)]))
    return best


def contact_summary(run, robots, geometry, tracks, ledger):
    """GT base distance / base-box separation and the raw MJWarp contact ledger."""
    out = dict(schema='ugrp.e2ewarp.nav_r4_contact_summary.v1', eval_only=True,
               robots=list(robots), pair=(len(robots) == 2), ledger=ledger)
    if len(robots) != 2:
        out.update(available=False, reason='solo diagnostic: no peer in the scene')
        return out
    r1, r2 = robots
    xy1, yaw1 = tracks[r1]
    xy2, yaw2 = tracks[r2]
    n = min(len(xy1), len(xy2))
    centers = [float(np.linalg.norm(xy1[i] - xy2[i])) for i in range(n)]
    imin = int(np.argmin(centers)) if centers else None
    boxes = (ledger or {}).get('base_boxes') or {}
    separations = []
    for i in range(n):
        a, b = boxes.get(r1), boxes.get(r2)
        if not a or not b:
            break
        pa = _rect_corners((float(xy1[i][0]) + a['local_pos'][0], float(xy1[i][1]) + a['local_pos'][1]),
                           float(yaw1[i]), float(a['size'][0]), float(a['size'][1]))
        pb = _rect_corners((float(xy2[i][0]) + b['local_pos'][0], float(xy2[i][1]) + b['local_pos'][1]),
                           float(yaw2[i]), float(b['size'][0]), float(b['size'][1]))
        separations.append(polygon_distance(pa, pb))
    smin = int(np.argmin(separations)) if separations else None
    out.update(available=True,
               min_center_distance_m=round(min(centers), 4) if centers else None,
               min_center_distance_s=(round(imin / TICK_HZ, 3) if imin is not None else None),
               min_base_box_separation_m=(round(float(min(separations)), 4) if separations else None),
               min_base_box_separation_s=(round(smin / TICK_HZ, 3) if smin is not None else None),
               center_distance_below_0_181_n=(sum(1 for v in centers if v < 0.181) if centers else None),
               contact_ticks=((ledger or {}).get('contact_ticks')),
               contact_pairs_total=((ledger or {}).get('contact_pairs_total')),
               first_contact_s=((ledger or {}).get('first_contact_s')),
               last_contact_s=((ledger or {}).get('last_contact_s')),
               contacts_available=((ledger or {}).get('contacts_available')),
               note='MJWarp contact buffer (evaluation-only) + GT box geometry; never a controller input')
    return out


def robot_report(run, rows, robot, qpos, destination, constants, commands):
    rows = sorted(rows, key=lambda r: float(r['sim_s']))
    geometry, adr, xy, yaw_gt = track(run, robot, qpos)
    sim = [float(r['sim_s']) for r in rows]
    own = [r.get('own_navigation') or {} for r in rows]
    detected = [z is not None for z in (zone_b_largest(r) for r in rows)]
    fresh = [z is not None for z in (fresh_zone_b(r) for r in rows)]
    components = [component_px(zone_b_largest(r)) for r in rows]
    first_detection = next((i for i, hit in enumerate(detected) if hit), None)
    first_fresh = next((i for i, hit in enumerate(fresh) if hit), None)
    first_fresh_mem = fresh_zone_b(rows[first_fresh]) if first_fresh is not None else None
    armed_i = first_index(own, lambda o: bool(o.get('arrival_armed')))
    claim_i = first_index(own, lambda o: bool(o.get('destination_arrived')))
    no_claim_i = first_index(own, lambda o: bool(o.get('arrival_no_claim')))
    arrival_modes = sorted({str(o.get('arrival_mode')) for o in own})
    slot = sorted({str(o.get('slot')) for o in own if o.get('slot') is not None})
    reasons = {}
    for o in own:
        key = str(o.get('drive_reason'))
        reasons[key] = reasons.get(key, 0) + 1
    own_commands = [c for c in commands if str(c.get('robot')) == robot]
    moving = sum(1 for c in own_commands
                 if any(abs(float(w)) > 0.0 for w in (c.get('wheels') or [])))
    cmd_kin = command_kinematics(commands, robot, constants)

    def pose_at(i):
        return own[i].get('odom_pose')

    def gt_at(i):
        return xy[min(i, len(xy) - 1)]

    armed = None
    if armed_i is not None:
        mem = fresh_zone_b(rows[armed_i]) or zone_b_largest(rows[armed_i]) or {}
        armed = dict(index=armed_i, sim_s=sim[armed_i],
                     gt_xy=[round(float(v), 4) for v in xy[armed_i]],
                     gt_yaw_deg=round(float(yaw_gt[armed_i]), 3),
                     odom_pose=pose_at(armed_i),
                     odom_yaw_deg=(None if pose_at(armed_i) is None else pose_at(armed_i)[2]),
                     u_deg=own[armed_i].get('arrival_u_deg'),
                     bearing_armed_deg=own[armed_i].get('arrival_bearing_armed_deg'),
                     heading_error_deg=own[armed_i].get('arrival_heading_error_deg'),
                     slot_offset_deg=mem.get('slot_bearing_offset_deg'),
                     bottom_norm=mem.get('bottom_norm'), height_norm=mem.get('height_norm'),
                     component_px=component_px(mem),
                     detection_fresh=bool(fresh_zone_b(rows[armed_i]) is not None),
                     forward_used_m=own[armed_i].get('forward_used_m'),
                     drive_reason=own[armed_i].get('drive_reason'))
    claim = None
    if claim_i is not None:
        claim = dict(index=claim_i, sim_s=sim[claim_i],
                     gt_xy=[round(float(v), 4) for v in xy[claim_i]],
                     gt_yaw_deg=round(float(yaw_gt[claim_i]), 3),
                     inside_gt=inside(xy[claim_i], destination['center_m'],
                                      destination['half_extents_m']),
                     odom_pose=pose_at(claim_i),
                     projection_m=own[claim_i].get('arrival_projection_m'),
                     path_m=own[claim_i].get('arrival_path_m'),
                     heading_error_deg=own[claim_i].get('arrival_heading_error_deg'),
                     drive_reason=own[claim_i].get('drive_reason'))
    no_claim = None
    if no_claim_i is not None:
        no_claim = dict(index=no_claim_i, sim_s=sim[no_claim_i],
                        gt_xy=[round(float(v), 4) for v in xy[no_claim_i]],
                        projection_m=own[no_claim_i].get('arrival_projection_m'),
                        path_m=own[no_claim_i].get('arrival_path_m'),
                        drive_reason=own[no_claim_i].get('drive_reason'))
    displacement = None
    if (armed is not None and claim is not None and claim['index'] > armed['index']
            and armed['odom_pose'] is not None and claim['odom_pose'] is not None):
        start, end = armed['index'], claim['index']
        gt_path = float(np.linalg.norm(np.diff(xy[start:end + 1], axis=0), axis=1).sum())
        odom0, odom1 = armed['odom_pose'], claim['odom_pose']
        odom_dx = float(odom1[0]) - float(odom0[0])
        odom_dy = float(odom1[1]) - float(odom0[1])
        u = math.radians(float(armed['u_deg'] or 0.0))
        gt_dx = float(xy[end][0]) - float(xy[start][0])
        gt_dy = float(xy[end][1]) - float(xy[start][1])
        displacement = dict(
            ticks=end - start, sim_s=round(sim[end] - sim[start], 3),
            gt_dx_m=round(gt_dx, 4), gt_dy_m=round(gt_dy, 4),
            gt_norm_m=round(math.hypot(gt_dx, gt_dy), 4), gt_path_m=round(gt_path, 4),
            gt_dot_u_m=round(gt_dx * math.cos(u) + gt_dy * math.sin(u), 4),
            gt_heading_deg=round(math.degrees(math.atan2(gt_dy, gt_dx)), 3)
            if math.hypot(gt_dx, gt_dy) > 0 else None,
            odom_dx_m=round(odom_dx, 4), odom_dy_m=round(odom_dy, 4),
            odom_norm_m=round(math.hypot(odom_dx, odom_dy), 4),
            odom_projection_m=claim['projection_m'], odom_path_m=claim['path_m'],
            odom_over_gt_path=round(float(claim['path_m'] or 0.0) / gt_path, 3) if gt_path > 0 else None,
            odom_yaw_error_to_gt_deg=round(wrap_deg(float(odom1[2]) - float(yaw_gt[end])), 3),
            diagnostic_only=True,
            note='world-frame GT next to the self-odometry displacement; never a controller input')
    final_xy = xy[-1]
    west_edge = float(destination['center_m'][0]) - float(destination['half_extents_m'][0])
    post_claim = None
    if claim_i is not None:
        gt_claim = xy[claim_i]
        post_claim = dict(ticks=len(xy) - 1 - claim_i,
                          dx_m=round(float(final_xy[0]) - float(gt_claim[0]), 4),
                          dy_m=round(float(final_xy[1]) - float(gt_claim[1]), 4),
                          norm_m=round(float(np.linalg.norm(final_xy - gt_claim)), 4),
                          diagnostic_only=True)
    drift = dict(
        segments={name: _segment_stats(start, end, own, cmd_kin, xy, yaw_gt)
                  for name, (start, end) in _segments(own, cmd_kin, armed_i, claim_i).items()},
        coasting=coasting(own, cmd_kin, xy, yaw_gt),
        yaw_gt_series_summary=dict(
            final_deg=round(float(yaw_gt[-1]), 3),
            min_deg=round(float(yaw_gt.min()), 3),
            max_deg=round(float(yaw_gt.max()), 3)),
    )
    return dict(
        robot=robot,
        sim_s_span=[round(sim[0], 3), round(sim[-1], 3)] if sim else None,
        localization_rows=len(rows),
        detection_n=sum(detected), fresh_detection_n=sum(fresh),
        max_component_px=max(components) if components else 0,
        first_detection=({} if first_detection is None else
                         dict(index=first_detection, sim_s=sim[first_detection],
                              pixels=component_px(zone_b_largest(rows[first_detection])))),
        first_fresh_detection=({} if first_fresh is None else
                               dict(index=first_fresh, sim_s=sim[first_fresh],
                                    bottom_norm=(first_fresh_mem or {}).get('bottom_norm'),
                                    height_norm=(first_fresh_mem or {}).get('height_norm'),
                                    pixels=component_px(first_fresh_mem))),
        drive_reason=reasons,
        command_rows=len(own_commands), moving_command_rows=moving,
        forward_used_m=max([float(o.get('forward_used_m') or 0.0) for o in own], default=0.0),
        forward_steps=max([int(o.get('forward_steps') or 0) for o in own], default=0),
        search_steps=max([int(o.get('search_steps') or 0) for o in own], default=0),
        arrival_modes=arrival_modes, slots=slot,
        armed=armed, claim=claim, no_claim=no_claim,
        armed_to_claim=displacement,
        final_gt_xy=[round(float(v), 4) for v in final_xy],
        final_gt_yaw_deg=round(float(yaw_gt[-1]), 3),
        final_inside_gt=inside(final_xy, destination['center_m'], destination['half_extents_m']),
        gt_path_m=round(float(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum()), 4),
        x_margin_to_west_edge_final_m=round(float(final_xy[0]) - west_edge, 4),
        x_margin_to_west_edge_claim_m=(None if claim is None else
                                       round(float(claim['gt_xy'][0]) - west_edge, 4)),
        post_claim_gt_drift=post_claim,
        drift=drift,
        yaw_error_summary=yaw_error_summary(own, yaw_gt),
        timeline_1s=timeline(own, cmd_kin, xy, yaw_gt),
        gt_yaw_vs_odom_yaw_series=[
            dict(sim_s=round(sim[i], 3),
                 gt_yaw_deg=round(float(yaw_gt[i]), 3),
                 odom_yaw_deg=(None if pose_at(i) is None else pose_at(i)[2]),
                 error_deg=(None if pose_at(i) is None else
                            round(wrap_deg(float(yaw_gt[i]) - float(pose_at(i)[2])), 3)))
            for i in range(len(own))],
    )


def recount(run_dir, admission_dir, expected_sha):
    run = Path(run_dir).resolve()
    admission = Path(admission_dir).resolve()
    result = load_json(run / 'result.json') or {}
    run_queue = load_json(run / 'queue.json') or {}
    adm_queue = load_json(admission / 'queue.json') or {}
    meta = load_json(run / 'RUN_META.json') or {}
    stack = load_json(admission / 'stack-check.json') or {}
    runtime = load_json(run / 'runtime-applied.json') or {}
    events = load_json(run / 'nav-events.json') or {}
    ledger = load_json(run / 'contact-ledger.json')
    rows_all = load_json(run / 'localization.json') or []
    commands = load_json(run / 'commands.json') or []
    state = np.load(run / 'evaluation-state.npz')
    qpos = np.asarray(state['qpos'])
    if qpos.ndim != 3:
        raise ValueError('evaluation-state qpos must be [ticks, worlds, nq]')
    geometry = json.loads((run / 'world-00' / 'eval-geometry.json').read_text())
    destination = geometry['destination']
    robots = tuple(run_queue.get('robots') or geometry['robot_qpos_adr'])
    constants = ((run_queue.get('nav_calibration') or {}).get('constants')
                 or (adm_queue.get('nav_calibration') or {}).get('constants') or {})
    per_robot = {}
    tracks = {}
    for robot in robots:
        rows = [r for r in rows_all if str(r.get('robot')) == robot]
        per_robot[robot] = robot_report(run, rows, robot, qpos, destination, constants, commands)
        _g, _adr, xy, yaw = track(run, robot, qpos)
        tracks[robot] = (xy, yaw)
    claim_n = sum(1 for r in robots if per_robot[r]['claim'] is not None)
    # Acceptance table (r3-compatible): GT arrival is the *final* pose; a claim
    # whose robot is finally outside the zone is the mismatch/FP.  The claim-time
    # outside count is reported separately as a diagnostic (r3 did the same).
    final_arrival_n = sum(1 for r in robots if per_robot[r]['final_inside_gt'])
    mismatch_n = sum(1 for r in robots if per_robot[r]['claim'] is not None
                     and not per_robot[r]['final_inside_gt'])
    outside_claim_n = sum(1 for r in robots if per_robot[r]['claim'] is not None
                          and not per_robot[r]['claim']['inside_gt'])
    no_claim_n = sum(1 for r in robots if per_robot[r]['no_claim'] is not None)
    boundary_keys = ('held_world_reads', 'top_camera_control', 'static_map_input',
                     'gpu_noslip_iterations', 'cpu_physics_steps')
    boundaries = {
        'result_input_audit': ((result.get('input_audit') or {})),
        'runtime_applied': {k: runtime.get(k) for k in boundary_keys},
        'queue_static_map_input': run_queue.get('nav_static_map_input'),
        'nav_cargo_spawned': run_queue.get('nav_cargo_spawned'),
    }
    boundary_violations = []
    audit = result.get('input_audit') or {}
    if int(audit.get('held_world_reads') or 0) != 0:
        boundary_violations.append('held_world_reads')
    if audit.get('top_camera_control') is not False:
        boundary_violations.append('top_camera_control')
    if runtime.get('static_map_input') not in (False, None):
        boundary_violations.append('static_map_input')
    if int(runtime.get('gpu_noslip_iterations') or 0) != 0:
        boundary_violations.append('gpu_noslip_iterations')
    if int(runtime.get('cpu_physics_steps') or 0) != 0:
        boundary_violations.append('cpu_physics_steps')
    if int(runtime.get('cpu_render_calls') or 0) != 0:
        boundary_violations.append('cpu_render_calls')
    queue_markers = {k: v for k, v in run_queue.items() if k.startswith('nav_')}
    return dict(
        schema=SCHEMA, eval_only=True, no_pooling=True, research_result=False,
        success_claim='not_available', run=str(run), admission=str(admission),
        expected_source_sha=expected_sha,
        source=dict(
            run_queue_source_sha=run_queue.get('source_sha'),
            admission_queue_source_sha=adm_queue.get('source_sha'),
            run_meta_sha=meta.get('sha'),
            result_source_sha=result.get('source_sha'),
            admission_equals_run_queue=(adm_queue == run_queue),
        ),
        status=result.get('status'), sim_s=result.get('sim_s'), wall_s=result.get('wall_s'),
        mode=run_queue.get('mode'), robots=list(robots),
        nav_solo_robot=run_queue.get('nav_solo_robot'),
        localization_rows=len(rows_all),
        commands_rows=len(commands),
        moving_wheel_rows=sum(1 for c in commands
                              if any(abs(float(w)) > 0.0 for w in (c.get('wheels') or []))),
        robots_report=per_robot,
        arrival_claim_n=claim_n, arrival_gt_n=final_arrival_n,
        claim_mismatch_n=mismatch_n, claims_outside_gt_at_claim_time_n=outside_claim_n,
        no_claim_n=no_claim_n, final_gt_arrival_n=final_arrival_n,
        nav_events=events,
        queue_markers=queue_markers,
        stack_check=dict(ok=stack.get('ok'), rows=len(stack.get('rows') or []),
                         blocked=sum(1 for r in (stack.get('rows') or [])
                                     if r.get('status') not in ('current', 'approved_deviation'))),
        boundaries=boundaries, boundary_violations=boundary_violations,
        contacts=contact_summary(run, robots, geometry, tracks, ledger),
        calibration=dict(sha256=(run_queue.get('nav_calibration') or {}).get('sha256'),
                         source_sha=(run_queue.get('nav_calibration') or {}).get('source_sha'),
                         constants=constants),
        eval_geometry=dict(destination=destination, spawns=geometry.get('spawns')),
        model_calls=result.get('model_calls'), decisions=result.get('decisions'),
        scope='nav-only; no evaluator; claim/arrival unverified by the runner',
    )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--admission', type=Path, required=True)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--out', type=Path)
    a = p.parse_args(argv)
    report = recount(a.run, a.admission, a.expected_source_sha)
    if a.out:
        a.out.write_text(json.dumps(report, ensure_ascii=False, indent=1, allow_nan=False) + '\n')
    print(json.dumps(dict(run=report['run'], status=report['status'],
                          arrival_gt_n=report['arrival_gt_n'], claim_n=report['arrival_claim_n'],
                          mismatch_n=report['claim_mismatch_n'],
                          no_claim_n=report['no_claim_n'],
                          min_center_distance_m=report['contacts'].get('min_center_distance_m'),
                          contact_ticks=report['contacts'].get('contact_ticks')),
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
