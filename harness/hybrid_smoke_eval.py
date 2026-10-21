"""EVAL-ONLY measurements for the hybrid code-carry smoke (never an input to the code or a teacher).

Written per code tick into ``raw/hybrid-drive.jsonl`` under ``eval_only`` by the runner
(``scripts/run_grasp_act_teacher.py`` hybrid_smoke). They answer two open risks of
experiments/2026-10-21-pairact-p2/HYBRID_RUN.md §8 from the smoke itself:

  * loaded-pose camera projection: the nav zone point is projected with the gate mount
    ``GATE_GROUND_PROJECTION`` (height 0.300 m, pitch 19 deg down, x offset 0.0255 m). With the beam
    lifted the arm-mounted camera may sit elsewhere. ``camera_mount`` reads the GT camera pose,
    ``projection_check`` re-projects the same detection pixel with the measured mount and reports the
    floor-point difference.
  * beam / partner occlusion of zone B: ``zone_occlusion`` casts GT rays from the navigator camera to
    a grid on the zone B floor and counts points inside the field of view that the beam (capsule
    between the GT beam ends) or the partner robot (vertical cylinder) blocks.

Geometry only; the caller passes GT arrays. Beam radius and partner cylinder size are recorded with
every row because they are approximations [확인 필요: beam cross-section and chassis height of the
scene XML].
"""
from __future__ import annotations

import math

SCHEMA = 'ugrp.pairact.hybrid_smoke_eval.v1'
BEAM_RADIUS_M = .03          # [확인 필요] capsule approximation of the beam cross-section
PARTNER_RADIUS_M = .17       # pair_carry_teacher_warp.ROBOT_RADIUS_M (planning disc)
PARTNER_HEIGHT_M = .30       # [확인 필요] chassis + lifted arm height
GRID = 5                     # zone floor samples per axis


def _mat(xmat):
    m = [float(v) for v in xmat]
    if len(m) != 9:
        raise ValueError('3x3 camera rotation (row major) required')
    return [m[0:3], m[3:6], m[6:9]]


def _col(m, j):
    return (m[0][j], m[1][j], m[2][j])


def camera_mount(cam_xpos, cam_xmat, base_pose, floor_z=0.):
    """GT camera mount relative to the robot base (MuJoCo camera: looks along -z, up = +y)."""
    m = _mat(cam_xmat)
    fwd = tuple(-v for v in _col(m, 2))
    pitch_down = math.degrees(math.asin(max(-1., min(1., -fwd[2]))))
    yaw_cam = math.atan2(fwd[1], fwd[0])
    c, s = math.cos(base_pose[2]), math.sin(base_pose[2])
    dx, dy = cam_xpos[0] - base_pose[0], cam_xpos[1] - base_pose[1]
    return {'height_m': float(cam_xpos[2]) - floor_z, 'pitch_down_deg': pitch_down,
            'x_offset_m': c*dx + s*dy, 'y_offset_m': -s*dx + c*dy,
            'yaw_rel_deg': math.degrees(math.atan2(math.sin(yaw_cam - base_pose[2]), math.cos(yaw_cam - base_pose[2])))}


def projection_check(bbox, mount, ground_point_robot, gate):
    """Same detection pixel as NavZoneSensor (bottom row, centre column), gate mount vs measured mount."""
    left, top, right, bottom = bbox
    u, v = (left + right - 1)/2., bottom - 1
    measured = dict(gate, camera_height_m=mount['height_m'], pitch_down_deg=mount['pitch_down_deg'],
                    camera_x_offset_m=mount['x_offset_m'])
    a, b = ground_point_robot(u, v, gate), ground_point_robot(u, v, measured)
    out = {'pixel': [u, v], 'gate_point': list(a) if a else None, 'measured_point': list(b) if b else None,
           'height_delta_m': mount['height_m'] - float(gate['camera_height_m']),
           'pitch_delta_deg': mount['pitch_down_deg'] - float(gate['pitch_down_deg']),
           'lateral_offset_m': mount['y_offset_m'], 'yaw_rel_deg': mount['yaw_rel_deg']}
    if a and b:
        out['error_m'] = math.hypot(a[0] - b[0], a[1] - b[1])
        out['range_gate_m'], out['range_measured_m'] = math.hypot(*a), math.hypot(*b)
    return out


def _seg_ray_distance(p, q, a, b):
    """Minimum distance between segment p->q (ray to the floor point) and segment a-b (beam axis)."""
    d1 = [q[i] - p[i] for i in range(3)]; d2 = [b[i] - a[i] for i in range(3)]; r = [p[i] - a[i] for i in range(3)]
    A = sum(x*x for x in d1); E = sum(x*x for x in d2); F = sum(d2[i]*r[i] for i in range(3))
    C = sum(d1[i]*r[i] for i in range(3)); B = sum(d1[i]*d2[i] for i in range(3))
    den = A*E - B*B
    s = max(0., min(1., (B*F - C*E)/den)) if den > 1e-12 else 0.
    t = max(0., min(1., (B*s + F)/E)) if E > 1e-12 else 0.
    s = max(0., min(1., (B*t - C)/A)) if A > 1e-12 else 0.
    c1 = [p[i] + d1[i]*s for i in range(3)]; c2 = [a[i] + d2[i]*t for i in range(3)]
    return math.dist(c1, c2), s


def _ray_hits_cylinder(p, q, centre, radius, height):
    """Does segment p->q pass through the vertical cylinder (floor..height) around centre (x, y)?"""
    dx, dy = q[0] - p[0], q[1] - p[1]
    fx, fy = p[0] - centre[0], p[1] - centre[1]
    a = dx*dx + dy*dy; b = 2*(fx*dx + fy*dy); c = fx*fx + fy*fy - radius*radius
    if a < 1e-12:
        return c <= 0
    disc = b*b - 4*a*c
    if disc < 0:
        return False
    for s in ((-b - math.sqrt(disc))/(2*a), (-b + math.sqrt(disc))/(2*a)):
        if 0. <= s < .999:
            z = p[2] + (q[2] - p[2])*s
            if 0. <= z <= height:
                return True
    return c <= 0 and p[2] <= height


def zone_occlusion(cam_xpos, cam_xmat, zone, beam_ends, partner_xy, *, hfov_deg=120., vfov_deg=None,
                   beam_radius=BEAM_RADIUS_M, partner_radius=PARTNER_RADIUS_M, partner_height=PARTNER_HEIGHT_M,
                   grid=GRID, width=640, height=480):
    """Zone B floor grid seen from the GT camera: in FOV, blocked by the beam, blocked by the partner."""
    m = _mat(cam_xmat)
    right, up, back = _col(m, 0), _col(m, 1), _col(m, 2)
    if vfov_deg is None:
        vfov_deg = math.degrees(2*math.atan(math.tan(math.radians(hfov_deg)/2)*height/width))
    th, tv = math.tan(math.radians(hfov_deg)/2), math.tan(math.radians(vfov_deg)/2)
    a, b = beam_ends
    n = in_fov = beam_blk = partner_blk = visible = 0
    for i in range(grid):
        for j in range(grid):
            x = zone['cx'] - zone['hx'] + (i + .5)*2*zone['hx']/grid
            y = zone['cy'] - zone['hy'] + (j + .5)*2*zone['hy']/grid
            pt = (x, y, 0.)
            v = [pt[k] - cam_xpos[k] for k in range(3)]
            zc = -sum(v[k]*back[k] for k in range(3))
            n += 1
            if zc <= 1e-6:
                continue
            xc, yc = sum(v[k]*right[k] for k in range(3))/zc, sum(v[k]*up[k] for k in range(3))/zc
            if abs(xc) > th or abs(yc) > tv:
                continue
            in_fov += 1
            dist, _s = _seg_ray_distance(cam_xpos, pt, a, b)
            hit_beam = dist < beam_radius
            hit_partner = partner_xy is not None and _ray_hits_cylinder(cam_xpos, pt, partner_xy, partner_radius,
                                                                         partner_height)
            beam_blk += hit_beam; partner_blk += hit_partner
            visible += not (hit_beam or hit_partner)
    return {'schema': SCHEMA, 'grid_points': n, 'in_fov': in_fov, 'blocked_by_beam': beam_blk,
            'blocked_by_partner': partner_blk, 'visible': visible,
            'visible_frac_of_fov': visible/in_fov if in_fov else None,
            'model': {'beam_radius_m': beam_radius, 'partner_radius_m': partner_radius,
                      'partner_height_m': partner_height, 'hfov_deg': hfov_deg, 'vfov_deg': vfov_deg}}


def tick_row(t, run, commands, truth, *, camera=None, zone=None, ground_point_robot=None, gate=None,
             hfov_deg=120.):
    """One hybrid-drive.jsonl row: the code's applied commands (fit input) + eval-only GT measurements."""
    leader, follower = run.leader, run.follower
    row = {'t': t, 'segment': run.segment(), 'planner_phase': run.planner.phase if run.planner else None,
           'commands': {r: {'wheels': list(c['wheels']), 'duration_s': list(c['duration_s'])} for r, c in commands.items()},
           'zone_seen': run.last_zone is not None,
           'zone_point': list(run.last_zone['point']) if run.last_zone else None}
    ev = {'gt_beam_pose': list(truth['beam']['pose']), 'gt_robot_pose': {r: list(truth['robots'][r]['pose'])
                                                                         for r in commands}}
    if camera is not None:
        pos, xmat = camera
        mount = camera_mount(pos, xmat, truth['robots'][leader]['pose'])
        ev['camera_mount'] = mount
        if run.last_zone is not None and ground_point_robot is not None and gate is not None:
            bbox = run.last_zone['detection'].get('bbox')
            if bbox is not None:
                ev['projection'] = projection_check(bbox, mount, ground_point_robot, gate)
        ends = (truth['beam'].get('ends') or {})
        if zone is not None and len(ends) == 2:
            e = [tuple(v) for v in ends.values()]
            ev['occlusion'] = zone_occlusion(pos, xmat, zone, e, truth['robots'][follower]['pose'][:2],
                                             hfov_deg=hfov_deg)
    row['eval_only'] = ev
    return row
