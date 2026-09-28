#!/usr/bin/env python3
"""Carry height vs the own ultrasonic cone: kinematics-only analysis (#221, #246, PR #248).

No physics step, no simulation run, no model call: ``mj_step*`` are replaced by a
failing stub before anything is built. The pair-carry scene (``zone_wide_door_tags_v2``
+ ``long_beam``) is built from XML, robots/arm joints/beam are placed kinematically
and only ``mj_forward``, ``mj_multiRay``/``mj_ray`` and ``mj_geomDistance`` run.

Per commanded lift height: calibrated IK (harness.visual_arm), SIM joint-range and
grip-site check, sonar first echo WITH the held load (and an own-arm diagnostic),
beam clearance to both robots (grippers excluded), static tip-over margins with the
half-load share, and a pinhole proxy of the held-bar mask in the wrist camera.

Usage: ``OMP_NUM_THREADS=2 .venv-sim/bin/python scripts/analyze_ultrasonic_carry_height.py --out <json>``
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mujoco  # noqa: E402
import numpy as np  # noqa: E402


def _forbid_physics() -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError('kinematics-only analysis: physics stepping is forbidden')
    for name in ('mj_step', 'mj_step1', 'mj_step2'):
        setattr(mujoco, name, forbidden)


from harness import ultrasonic_carry as uc  # noqa: E402
from harness import visual_arm as va  # noqa: E402
from harness.ultrasonic_model import DEFAULT_SPEC  # noqa: E402

BEAM_CENTER = (1.0, -1.2)
LOAD_SHARE_KG = .300 / 2          # long_beam 0.300 kg, symmetric two-end carry
FRONT_CONTACT_X_M = .06           # wheel axle x = wheelbase / 2 (sim.masterpi_geometry)
SIDE_CONTACT_Y_M = .0655          # track / 2
CAM_W, CAM_H = 640, 480


def build_scene():
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.zone_cargo import instances
    from sim.zone_tagged_cargo_scene import TaggedCargoZoneScene
    beam = {'item_id': 'beam', 'kind': 'long_beam', 'pose': [*BEAM_CENTER, 0.]}
    scene = TaggedCargoZoneScene.from_tagged_cargo('zone_wide_door_tags_v2', 11, cargo=[beam],
                                                   goal={'A': {'cyan': 1}}, contact_profile='local_contact_fine')
    xml = scene.transform(build_multi_robot_xml(None))
    model = mujoco.MjModel.from_xml_string(xml)
    return model, mujoco.MjData(model), instances([beam])[0], hashlib.sha256(xml.encode()).hexdigest()


def _free(model, data, joint, x, y, z, yaw):
    j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint)
    q = model.jnt_qposadr[j]
    data.qpos[q:q + 7] = [x, y, z, math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]


def joint_targets(pulses: dict) -> dict:
    """Same map as sim.masterpi_dynamics_v2.pulse_to_joint_targets (servo6 centre 1500)."""
    nom = lambda s: float(pulses[s] - va.SERVO_DEVIATION[s])
    return {'arm_yaw': math.radians((pulses.get(6, 1500) - 1500) / va.PULSE_PER_DEGREE),
            'shoulder': math.radians(90. - (nom(5) - 1500.) / va.PULSE_PER_DEGREE),
            'elbow': math.radians(-(nom(4) - 1500.) / va.PULSE_PER_DEGREE),
            'wrist_pitch': math.radians((nom(3) - 1500.) / va.PULSE_PER_DEGREE)}


def set_arm(model, data, rid, pulses) -> dict:
    out = {}
    for name, value in joint_targets(pulses).items():
        j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f'{rid}__{name}')
        lo, hi = (float(v) for v in model.jnt_range[j])
        out[name] = {'target_rad': round(value, 4), 'range_rad': [round(lo, 3), round(hi, 3)],
                     'within_range': bool(lo - 1e-9 <= value <= hi + 1e-9)}
        data.qpos[model.jnt_qposadr[j]] = min(hi, max(lo, value))
    return out


def place(model, data, beam, pulses, bar_bottom_m):
    r = uc.GRASP_RADIUS_M
    grip_x = uc.BEAM_LENGTH_M / 2 - uc.GRIP_FROM_END_M
    cx, cy = BEAM_CENTER
    _free(model, data, 'r1__base_free', cx - grip_x - r, cy, .0325, 0.)
    _free(model, data, 'r2__base_free', cx + grip_x + r, cy, .0325, math.pi)
    _free(model, data, 'r3__base_free', 4.8, .9, .0325, 0.)
    ranges = {rid: set_arm(model, data, rid, pulses) for rid in ('r1', 'r2')}
    _free(model, data, beam.joint, cx, cy, bar_bottom_m, 0.)
    mujoco.mj_forward(model, data)
    return ranges


def _subtree(model, root):
    return [b for b in range(model.nbody) if int(model.body_rootid[b]) == root]


def _descends(model, body, ancestor):
    while body > 0:
        if body == ancestor:
            return True
        body = int(model.body_parentid[body])
    return False


def clearance(model, data, beam, rid) -> dict:
    """Min distance between the bar and a robot's geoms, the own/partner gripper subtree excluded."""
    root = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f'{rid}__robot')
    gripper = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f'{rid}__gripper')
    bodies = {b for b in _subtree(model, root) if not _descends(model, b, gripper)}
    bar = [g for g in range(model.ngeom) if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g) or '')
           .startswith(beam.body + '__')]
    best, pair = 1., None
    fromto = np.zeros(6)
    for g in range(model.ngeom):
        if int(model.geom_bodyid[g]) not in bodies:
            continue
        for b in bar:
            d = mujoco.mj_geomDistance(model, data, b, g, .2, fromto)
            if d < best:
                best, pair = d, mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g)
    return {'min_distance_m': round(best, 4), 'nearest_geom': pair}


def tip_margins(model, data, rid, grip_world) -> dict:
    root = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f'{rid}__robot')
    base = data.xpos[root].copy()
    R = data.xmat[root].reshape(3, 3)
    m_r = float(model.body_subtreemass[root])
    com_r = R.T @ (data.subtree_com[root] - base)          # robot frame, origin at axle height
    grip = R.T @ (np.asarray(grip_world) - base)
    masses = [(m_r, com_r), (LOAD_SHARE_KG, grip)]
    axle_z = float(base[2])
    h = lambda p: p[2] + axle_z                             # height above the floor
    m_tot = sum(m for m, _ in masses)
    com = sum(m * p for m, p in masses) / m_tot
    fwd = sum(m * (FRONT_CONTACT_X_M - p[0]) for m, p in masses)
    lat = sum(m * (SIDE_CONTACT_Y_M - abs(p[1])) for m, p in masses)
    mh = sum(m * h(p) for m, p in masses)
    return {'robot_mass_kg': round(m_r, 3), 'load_share_kg': LOAD_SHARE_KG,
            'com_x_m': round(float(com[0]), 4), 'com_height_m': round(float(h(com)), 4),
            'static_forward_restoring_ratio': round(float(m_r * (FRONT_CONTACT_X_M - com_r[0])
                                                          / (LOAD_SHARE_KG * (grip[0] - FRONT_CONTACT_X_M))), 2),
            'tip_accel_forward_mps2': round(float(9.81 * fwd / mh), 2),
            'tip_accel_lateral_mps2': round(float(9.81 * lat / mh), 2)}


def camera_bar_mask(pulses, bar_bottom_m):
    """Pinhole proxy of the bar in the wrist camera (robot frame, bar level along +x)."""
    import cv2
    from sim.masterpi_camera_profile import CAMERA_CX_PX, CAMERA_CY_PX, CAMERA_FX_PX, CAMERA_FY_PX
    origin, axes = va.camera_extrinsics(pulses)
    o, A = np.asarray(origin), np.asarray(axes)             # rows: image-right, image-down, forward
    x0 = uc.GRASP_RADIUS_M - uc.GRIP_FROM_END_M
    xs = np.linspace(x0, x0 + uc.BEAM_LENGTH_M, 121)
    mask = np.zeros((CAM_H, CAM_W), np.uint8)
    for (ya, za), (yb, zb) in (((-.02, bar_bottom_m + .032), (.02, bar_bottom_m + .032)),      # top face
                               ((-.02, bar_bottom_m), (-.02, bar_bottom_m + .032)),            # side faces
                               ((.02, bar_bottom_m), (.02, bar_bottom_m + .032))):
        for i in range(len(xs) - 1):
            quad = [(xs[i], ya, za), (xs[i + 1], ya, za), (xs[i + 1], yb, zb), (xs[i], yb, zb)]
            cam = [(A @ (np.asarray(p) - o)) for p in quad]
            if min(c[2] for c in cam) <= .01:
                continue
            px = np.array([[CAMERA_CX_PX + CAMERA_FX_PX * c[0] / c[2], CAMERA_CY_PX + CAMERA_FY_PX * c[1] / c[2]]
                           for c in cam], np.float64)
            if np.abs(px).max() > 1e5:
                continue
            cv2.fillConvexPoly(mask, np.round(px).astype(np.int32), 1)
    return mask.astype(bool), {'camera_height_m': round(float(o[2]), 4),
                               'optical_axis_elevation_deg': round(math.degrees(math.asin(float(A[2][2]))), 2)}


def iou(a, b) -> float:
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 1.


def evaluate_height(model, data, beam, tool_z, *, grasp_mask) -> dict:
    from sim.ultrasonic_range import MujocoUltrasonic
    row = {'commanded_tool_z_m': tool_z}
    try:
        lift = uc.lift_ik(tool_z)
    except ValueError as exc:
        row.update(ik_feasible=False, ik_error=str(exc))
        return row
    bottom = uc.expected_bar_bottom(lift['tool_z_m'])
    row.update(ik_feasible=True, pulses=lift['pulses'], fk_tool_z_m=round(lift['tool_z_m'], 4),
               pitch_deg=round(lift['pitch_deg'], 2), pitch_change_from_grasp_deg=round(lift['pitch_change_from_grasp_deg'], 2),
               expected_bar_bottom_m=round(bottom, 4))
    ranges = place(model, data, beam, lift['pulses'], bottom)
    row['sim_joint_ranges_ok'] = all(v['within_range'] for r in ranges.values() for v in r.values())
    row['sim_joint_targets_r1'] = ranges['r1']
    site = data.site(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, 'r1__grip_site'))
    base = data.xpos[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'r1__robot')]
    row['sim_grip_site_m'] = {'forward': round(float(site.xpos[0] - base[0]), 4), 'z': round(float(site.xpos[2]), 4)}
    exact = replace(DEFAULT_SPEC, dropout_prob=0., outlier_prob=0., noise_sigma0_m=0., noise_rel=0.)
    sonar = MujocoUltrasonic(model, data, 'r1', seed=0, spec=exact)
    _, diag = sonar.measure_diagnostic(0.)
    own = sonar.cast(include_own=True)
    from harness.ultrasonic_model import first_echo_index
    i = first_echo_index(own['dist'], sonar.alpha, own['beta'], exact)
    row['sonar'] = {'first_echo_m': None if diag['true_first_echo_m'] is None else round(diag['true_first_echo_m'], 4),
                    'echo_geom': diag['echo_geom'],
                    'sees_own_load': bool(diag['echo_geom'] and diag['echo_geom'].startswith(beam.body)),
                    'with_own_arm_first_echo_m': None if i is None else round(float(own['dist'][i]), 4),
                    'with_own_arm_echo_geom': None if i is None else mujoco.mj_id2name(
                        model, mujoco.mjtObj.mjOBJ_GEOM, int(own['geom'][i]))}
    row['bar_clearance'] = {rid: clearance(model, data, beam, rid) for rid in ('r1', 'r2')}
    row['tip_over_r1'] = tip_margins(model, data, 'r1', site.xpos.copy())
    mask, cam = camera_bar_mask(lift['pulses'], bottom)
    lower = slice(int(CAM_H * .4), CAM_H)
    row['wrist_camera_proxy'] = {**cam, 'bar_pixels': int(mask.sum()),
                                 'iou_vs_grasp_view': round(iou(mask, grasp_mask), 3),
                                 'iou_vs_grasp_view_lower60': round(iou(mask[lower], grasp_mask[lower]), 3)}
    return row


def analyse() -> dict:
    model, data, beam, xml_sha = build_scene()
    grasp = uc.grasp_pose()
    grasp_mask, grasp_cam = camera_bar_mask(grasp, 0.)
    margins = uc.CarryMargins()
    req = {c: {h: uc.required_heights(c, margins=margins, half_angle_deg=h) for h in (15., 7.5)}
           for c in ('near_face', 'whole_beam')}
    rec = uc.recommended_carry_tool_z()
    heights = sorted({uc.M2_LIFT_TOOL_Z_M, rec, rec + .01, round(req['whole_beam'][7.5]['tool_z_min_m'], 3),
                      round(req['whole_beam'][15.]['tool_z_min_m'], 3)})
    table = []
    for crit in ('near_face', 'whole_beam'):
        for half in (15., 7.5):
            for mz in (.044, .054, .064):
                for mx in (.068, .078, .088):
                    spec = replace(DEFAULT_SPEC, mount_z_floor_m=mz, mount_x_m=mx)
                    r = uc.required_heights(crit, spec, margins, half_angle_deg=half)
                    table.append({'criterion': crit, 'half_angle_deg': half, 'mount_z_m': mz, 'mount_x_m': mx,
                                  'bar_bottom_min_m': round(r['bar_bottom_min_m'], 4),
                                  'tool_z_min_m': round(r['tool_z_min_m'], 4)})
    tilt_sens = {f'{t}deg': round(uc.required_heights('whole_beam', margins=replace(margins, beam_pitch_deg=t))
                                  ['tool_z_min_m'], 4) for t in (uc.M2_TILT_P95_DEG, uc.M2_TILT_MAX_DEG)}
    return {'schema': 'ugrp.ultrasonic_carry_height_analysis.v1', 'scene_xml_sha256': xml_sha,
            'spec': asdict(DEFAULT_SPEC), 'margins': asdict(margins),
            'geometry': {'grasp_radius_m': uc.GRASP_RADIUS_M, 'grip_from_end_m': uc.GRIP_FROM_END_M,
                         'beam_length_m': uc.BEAM_LENGTH_M, 'grip_above_bottom_m': uc.GRIP_ABOVE_BOTTOM_M,
                         'm2_lift_tool_z_m': uc.M2_LIFT_TOOL_Z_M, 'm2_beam_body_z_m': uc.M2_BEAM_BODY_Z_M},
            'required': {c: {str(h): {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}
                             for h, r in by.items()} for c, by in req.items()},
            'whole_beam_tool_z_vs_tilt': tilt_sens,
            'mount_table': table,
            'ik_max_tool_z_calibrated': uc.max_tool_z(),
            'ik_max_tool_z_any_pitch_le_0': uc.max_tool_z(pitch_range_deg=(-90, 0)),
            'grasp_pose': {'pulses': grasp, 'camera': grasp_cam, 'bar_pixels': int(grasp_mask.sum())},
            'recommended_tool_z_m': rec,
            'heights': [evaluate_height(model, data, beam, h, grasp_mask=grasp_mask) for h in heights]}


# --- solo carry --------------------------------------------------------------------------------

SOLO_BODIES = {'box': ('cargo_box_00', .008), 'can': ('cargo_can', .024), 'tile': ('cargo_tile', .007)}
SOLO_POSE = (1.6, -2.5, 0.)          # facing wall_divider_1 (face x 2.175) in the pickup room


def build_solo_scene():
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.zone_tagged_cargo_scene import TaggedCargoZoneScene
    items = [{'item_id': 'can', 'kind': 'can', 'pose': [4.6, -2.9, 0.]},
             {'item_id': 'tile', 'kind': 'tile', 'pose': [4.4, -2.9, 0.]}]
    scene = TaggedCargoZoneScene.from_tagged_cargo('zone_wide_door_tags_v2', 11, cargo=items,
                                                   goal={'A': {'cyan': 1}}, contact_profile='local_contact_fine')
    xml = scene.transform(build_multi_robot_xml(None))
    model = mujoco.MjModel.from_xml_string(xml)
    return scene, model, mujoco.MjData(model), hashlib.sha256(xml.encode()).hexdigest()


def _park_all(model, data):
    _free(model, data, 'r2__base_free', 4.8, .9, .0325, 0.)
    _free(model, data, 'r3__base_free', 4.8, .45, .0325, 0.)
    for i, (body, _) in enumerate(SOLO_BODIES.values()):
        _free(model, data, body + '_free', 4.2 + .2 * i, -2.95, .02, 0.)


def place_solo(model, data, kind, pulses, tilt_deg, sag_m):
    """r1 at SOLO_POSE with the arm pose; the item rigidly at the grip site, tilted, sagged."""
    _park_all(model, data)
    x, y, yaw = SOLO_POSE
    _free(model, data, 'r1__base_free', x, y, .0325, yaw)
    set_arm(model, data, 'r1', pulses)
    mujoco.mj_forward(model, data)
    site = data.site(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, 'r1__grip_site')).xpos.copy()
    body, grip_z = SOLO_BODIES[kind]
    t = math.radians(tilt_deg)
    # rotation about +y by -tilt: forward edge up; quaternion (w, 0, sin(-t/2), 0)
    rot = np.array([[math.cos(t), 0., -math.sin(t)], [0., 1., 0.], [math.sin(t), 0., math.cos(t)]])
    origin = site - rot @ np.array([0., 0., grip_z]) - np.array([0., 0., sag_m])
    j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, body + '_free')
    q = model.jnt_qposadr[j]
    data.qpos[q:q + 7] = [*origin, math.cos(-t / 2), 0., math.sin(-t / 2), 0.]
    mujoco.mj_forward(model, data)
    return site


def floor_band(pulses):
    """Pinhole floor distances seen by the image's bottom and top rows at the centre column."""
    from sim.masterpi_camera_profile import CAMERA_CY_PX, CAMERA_FY_PX
    origin, axes = va.camera_extrinsics(pulses)
    o, A = np.asarray(origin), np.asarray(axes)
    out = {}
    for name, v in (('bottom_row', CAM_H - 1), ('top_row', 0)):
        d = A[2] + A[1] * (v - CAMERA_CY_PX) / CAMERA_FY_PX
        out[name] = round(float(o[0] + d[0] * (-o[2] / d[2])), 3) if d[2] < -1e-6 else None
    return {'camera_height_m': round(float(o[2]), 4),
            'optical_axis_elevation_deg': round(math.degrees(math.asin(float(A[2][2]))), 2),
            'floor_visible_from_m': out['bottom_row'], 'floor_visible_to_m': out['top_row']}


def lowering_path(item, from_pulses, grasp_pitch, n=16):
    """Put-down as the existing skill does it: a servo move (joint-linear) from the carry pose to the
    0.095 m hover at the grasp pitch, then the straight 16-step descent to the grasp height.
    Reports IK feasibility and the lowest item point (rigid hold, no sag) before the final step."""
    hover = va.solve_grip_ik(uc.GRASP_RADIUS_M, 0., .095, grasp_pitch)
    joints = sorted(set(from_pulses) & set(hover) - {1})
    lowest_transition, ik_ok = 1., True
    for s in np.linspace(0., 1., n):
        pose = {k: from_pulses[k] + s * (hover[k] - from_pulses[k]) for k in joints}
        p = va.tool_pose(pose)
        pts = uc.item_points(item, p.x_m, p.z_m, p.pitch_deg - grasp_pitch)
        lowest_transition = min(lowest_transition, float(pts[:, 2].min()))
    lowest_descent = 1.
    for h in np.linspace(.095, item.grip_above_bottom_m, n)[:-1]:
        try:
            p = va.tool_pose(va.solve_grip_ik(uc.GRASP_RADIUS_M, 0., float(h), grasp_pitch))
        except ValueError:
            ik_ok = False
            continue
        lowest_descent = min(lowest_descent, float(uc.item_points(item, p.x_m, p.z_m, p.pitch_deg - grasp_pitch)[:, 2].min()))
    return {'transition_to_hover_lowest_item_point_m': round(lowest_transition, 4),
            'descent_ik_feasible': ik_ok, 'descent_lowest_item_point_m': round(lowest_descent, 4),
            'transition_max_joint_change_pulses': int(max(abs(hover[k] - from_pulses[k]) for k in joints))}


def evaluate_solo(scene, model, data, kind, label, pulses, grasp_pitch):
    from harness.ultrasonic_map import expected_range
    from harness.ultrasonic_model import first_echo_index
    from sim.ultrasonic_range import MujocoUltrasonic
    item = uc.SOLO_ITEMS[kind]
    tp = va.tool_pose(pulses)
    rigid = tp.pitch_deg - grasp_pitch
    exact = replace(DEFAULT_SPEC, dropout_prob=0., outlier_prob=0., noise_sigma0_m=0., noise_rel=0.)
    expected = expected_range(scene.config['static_map'], SOLO_POSE, exact).range_m
    row = {'posture': label, 'pulses': pulses, 'tool_x_m': round(tp.x_m, 4), 'tool_z_m': round(tp.z_m, 4),
           'pitch_deg': round(tp.pitch_deg, 2), 'pitch_change_from_grasp_deg': round(rigid, 2),
           'analytic': uc.solo_posture_margins(item, pulses, grasp_pitch,
                                               extra_tilts_deg=(uc.CARRY_P30_RECORDED_TILT_DEG,) if label == 'carry_p30' else ()),
           'map_expected_m': round(expected, 4), 'cases': {}}
    row['sim_joint_ranges_ok'] = None
    for case, tilt in (('level', 0.), ('rigid', rigid)):
        _park_all(model, data)
        ranges = set_arm(model, data, 'r1', pulses)
        row['sim_joint_ranges_ok'] = all(v['within_range'] for v in ranges.values())
        site = place_solo(model, data, kind, pulses, tilt, uc.SoloMargins().load_sag_m)
        sonar = MujocoUltrasonic(model, data, 'r1', seed=0, spec=exact)
        own = sonar.cast(include_own=True)
        i = first_echo_index(own['dist'], sonar.alpha, own['beta'], exact)
        name = lambda g: mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(g))
        body = SOLO_BODIES[kind][0]
        hit = sorted({name(g) for g in own['geom'] if g >= 0})
        row['cases'][case] = {
            'tilt_deg': round(tilt, 2), 'grip_site_z_m': round(float(site[2]), 4),
            'first_echo_with_own_arm_m': None if i is None else round(float(own['dist'][i]), 4),
            'echo_geom': None if i is None else name(own['geom'][i]),
            'matches_map': i is not None and abs(float(own['dist'][i]) - expected) < .005,
            'own_arm_geoms_in_cone': [h for h in hit if h.startswith('r1__')],
            'item_in_cone': any(h.startswith(body) for h in hit)}
    _park_all(model, data)
    set_arm(model, data, 'r1', pulses)
    place_solo(model, data, kind, pulses, rigid, uc.SoloMargins().load_sag_m)
    site = data.site(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, 'r1__grip_site')).xpos.copy()
    tip = tip_margins(model, data, 'r1', site)
    # replace the half-beam load by this item's mass
    row['tip_over_r1'] = _tip_with_load(model, data, site, item.mass_kg)
    row['wrist_camera'] = floor_band(pulses)
    row['put_down'] = lowering_path(item, pulses, grasp_pitch)
    return row


def _tip_with_load(model, data, grip_world, load_kg):
    global LOAD_SHARE_KG
    saved, LOAD_SHARE_KG = LOAD_SHARE_KG, load_kg
    try:
        return tip_margins(model, data, 'r1', grip_world)
    finally:
        LOAD_SHARE_KG = saved


def analyse_solo() -> dict:
    scene, model, data, xml_sha = build_solo_scene()
    rows = {}
    for kind, item in uc.SOLO_ITEMS.items():
        grasp = va.solve_grip_ik(uc.GRASP_RADIUS_M, 0., item.grip_above_bottom_m, -90)
        g_pitch = va.tool_pose(grasp).pitch_deg
        rec = uc.recommended_solo_tool_z(kind)
        rec75 = uc.recommended_solo_tool_z(kind, half_angle_deg=7.5)
        postures = [('hover_0.095', uc.solo_lift(item, .095)['pulses']),
                    (f'straight_{rec:.3f}', uc.solo_lift(item, rec)['pulses']),
                    ('carry_p30', dict(uc.CARRY_P30))]
        rows[kind] = {'item': asdict(item), 'grasp_pulses': grasp, 'grasp_pitch_deg': round(g_pitch, 2),
                      'grasp_camera': floor_band(grasp),
                      'recommended_straight_lift_tool_z_m': {'15': rec, '7.5': rec75},
                      'postures': [evaluate_solo(scene, model, data, kind, label, pose, g_pitch)
                                   for label, pose in postures]}
        tp = va.tool_pose(uc.CARRY_P30)
        front = max(float(uc.item_points(item, tp.x_m, tp.z_m, t)[:, 0].max()) for t in (0., tp.pitch_deg - g_pitch))
        ext = max(0., front - DEFAULT_SPEC.mount_x_m)
        rows[kind]['carry_p30_forward_rule'] = {
            'item_front_beyond_sensor_m': round(ext, 4),
            'stop_distance_m': round(uc.solo_stop_distance(ext), 4),
            'slow_distance_m': round(uc.solo_stop_distance(ext, reaction_s=1.0), 4)}
    return {'schema': 'ugrp.ultrasonic_solo_carry_analysis.v1', 'scene_xml_sha256': xml_sha,
            'robot_pose': SOLO_POSE, 'margins': asdict(uc.SoloMargins()), 'spec': asdict(DEFAULT_SPEC),
            'kinds': rows}


# --- pair carry: side grasp (9/9 ㄱ자) vs straight (M2/v5/v6) ------------------------------------
# Same grasp on the beam (arm along the beam axis, jaws across it); only the body heading and the
# arm yaw differ. Side: body perpendicular to the beam, arm yaw -/+90 deg (PWM 500/2500, as
# scripts/probe_dual_grasp_sync.py --side-grasp, commit 9bb41317).

SIDE_BEAM_CENTER = (1.0, -1.2)
DOOR_1 = {'center': (2.2, .05), 'width_m': .5}      # zone_wide_door_tags_v2 passages[door_1], axis x
YAW_PWM = {'straight': {'r1': 1500, 'r2': 1500}, 'side': {'r1': 500, 'r2': 2500}}
HEADING = {'straight': {'r1': 0., 'r2': math.pi}, 'side': {'r1': math.pi / 2, 'r2': math.pi / 2}}


def build_pair_scene():
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.zone_cargo import instances
    from sim.zone_tagged_cargo_scene import TaggedCargoZoneScene
    beam = {'item_id': 'beam', 'kind': 'long_beam', 'pose': [*SIDE_BEAM_CENTER, 0.]}
    scene = TaggedCargoZoneScene.from_tagged_cargo('zone_wide_door_tags_v2', 11, cargo=[beam],
                                                   goal={'A': {'cyan': 1}}, contact_profile='local_contact_fine')
    xml = scene.transform(build_multi_robot_xml(None))
    model = mujoco.MjModel.from_xml_string(xml)
    return scene, model, mujoco.MjData(model), instances([beam])[0], hashlib.sha256(xml.encode()).hexdigest()


def _site(model, data, rid, name='grip_site'):
    return data.site(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, f'{rid}__{name}')).xpos.copy()


def place_formation(model, data, beam, mode, center, lift):
    """Beam level along world x at ``center``; each robot placed so its SIM grip site is on its grip point."""
    grip_x = uc.BEAM_LENGTH_M / 2 - uc.GRIP_FROM_END_M
    bottom = uc.expected_bar_bottom(lift['tool_z_m'])
    _free(model, data, 'r3__base_free', 4.8, .9, .0325, 0.)
    ranges = {}
    for rid, sign in (('r1', -1.), ('r2', 1.)):
        pulses = {**lift['pulses'], 6: YAW_PWM[mode][rid]}
        yaw = HEADING[mode][rid]
        _free(model, data, f'{rid}__base_free', 0., 0., .0325, yaw)
        ranges[rid] = set_arm(model, data, rid, pulses)
    mujoco.mj_forward(model, data)
    for rid, sign in (('r1', -1.), ('r2', 1.)):
        off = _site(model, data, rid)[:2]
        target = np.array([center[0] + sign * grip_x, center[1]])
        x, y = target - off
        _free(model, data, f'{rid}__base_free', float(x), float(y), .0325, HEADING[mode][rid])
    _free(model, data, beam.joint, center[0], center[1], bottom, 0.)
    mujoco.mj_forward(model, data)
    err = {rid: round(float(np.linalg.norm(_site(model, data, rid)[:2]
                                           - [center[0] + s * grip_x, center[1]])), 4)
           for rid, s in (('r1', -1.), ('r2', 1.))}
    return ranges, err, bottom


def _robot_geoms(model, rid):
    root = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f'{rid}__robot')
    return [g for g in range(model.ngeom) if int(model.body_rootid[model.geom_bodyid[g]]) == root
            and int(model.geom_group[g]) <= 2 and float(model.geom_rgba[g][3]) > 0]


def footprint(model, data, beam) -> dict:
    """World AABB of both robots (visible/collision geoms, groups 0-2) and the beam."""
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    geoms = _robot_geoms(model, 'r1') + _robot_geoms(model, 'r2') + [
        g for g in range(model.ngeom) if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g) or '').startswith(beam.body + '__')]
    for g in geoms:
        c, h = model.geom_aabb[g][:3], model.geom_aabb[g][3:]
        R = data.geom_xmat[g].reshape(3, 3)
        ext = np.abs(R) @ h
        w = data.geom_xpos[g] + R @ c
        lo, hi = np.minimum(lo, w - ext), np.maximum(hi, w + ext)
    return {'along_beam_m': round(float(hi[0] - lo[0]), 4), 'across_beam_m': round(float(hi[1] - lo[1]), 4)}


def sonar_view(scene, model, data, rid, beam) -> dict:
    from harness.ultrasonic_map import expected_range
    from harness.ultrasonic_model import first_echo_index
    from sim.ultrasonic_range import MujocoUltrasonic
    exact = replace(DEFAULT_SPEC, dropout_prob=0., outlier_prob=0., noise_sigma0_m=0., noise_rel=0.)
    sonar = MujocoUltrasonic(model, data, rid, seed=0, spec=exact)
    own = sonar.cast(include_own=True)
    i = first_echo_index(own['dist'], sonar.alpha, own['beta'], exact)
    name = lambda g: mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(g)) or ''
    hit = sorted({name(g) for g in own['geom'] if g >= 0})
    root = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f'{rid}__robot')
    base = data.xpos[root]
    heading = math.atan2(float(data.xmat[root][3]), float(data.xmat[root][0]))
    exp = expected_range(scene.config['static_map'], (float(base[0]), float(base[1]), heading), exact).range_m
    first = None if i is None else round(float(own['dist'][i]), 4)
    geom = None if i is None else name(own['geom'][i])
    partner = 'r2__' if rid == 'r1' else 'r1__'
    return {'heading_deg': round(math.degrees(heading), 1), 'first_echo_m': first, 'echo_geom': geom,
            'map_expected_m': None if exp is None else round(exp, 4),
            'matches_map': bool(first is not None and exp is not None and abs(first - exp) < .01),
            'own_geoms_in_cone': [h for h in hit if h.startswith(rid + '__')],
            'load_in_cone': any(h.startswith(beam.body) for h in hit),
            'partner_in_cone': any(h.startswith(partner) for h in hit)}


def static_ratios(model, data, rid, grip_world) -> dict:
    """Restoring / overturning moment about the edge the load hangs over (inf: load inside the support)."""
    root = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f'{rid}__robot')
    R = data.xmat[root].reshape(3, 3)
    com = R.T @ (data.subtree_com[root] - data.xpos[root])
    grip = R.T @ (np.asarray(grip_world) - data.xpos[root])
    m = float(model.body_subtreemass[root])
    out = {}
    for name, axis, edge in (('forward', 0, FRONT_CONTACT_X_M), ('lateral', 1, SIDE_CONTACT_Y_M)):
        over = LOAD_SHARE_KG * (abs(grip[axis]) - edge)
        out[f'static_{name}_restoring_ratio_signed'] = (round(float(m * (edge - abs(com[axis])) / over), 2)
                                                         if over > 1e-9 else None)
    return out


def camera_bar_mask_yawed(pulses, bar_bottom_m, bar_yaw_rad):
    """camera_bar_mask with the bar along the arm direction ``bar_yaw_rad`` (robot frame)."""
    import cv2
    from sim.masterpi_camera_profile import CAMERA_CX_PX, CAMERA_CY_PX, CAMERA_FX_PX, CAMERA_FY_PX
    origin, axes = va.camera_extrinsics(pulses)
    o, A = np.asarray(origin), np.asarray(axes)
    c, s_ = math.cos(bar_yaw_rad), math.sin(bar_yaw_rad)
    rot = lambda p: (c * p[0] - s_ * p[1], s_ * p[0] + c * p[1], p[2])
    x0 = uc.GRASP_RADIUS_M - uc.GRIP_FROM_END_M
    xs = np.linspace(x0, x0 + uc.BEAM_LENGTH_M, 121)
    mask = np.zeros((CAM_H, CAM_W), np.uint8)
    for (ya, za), (yb, zb) in (((-.02, bar_bottom_m + .032), (.02, bar_bottom_m + .032)),
                               ((-.02, bar_bottom_m), (-.02, bar_bottom_m + .032)),
                               ((.02, bar_bottom_m), (.02, bar_bottom_m + .032))):
        for i in range(len(xs) - 1):
            quad = [rot(p) for p in ((xs[i], ya, za), (xs[i + 1], ya, za), (xs[i + 1], yb, zb), (xs[i], yb, zb))]
            cam = [(A @ (np.asarray(p) - o)) for p in quad]
            if min(q[2] for q in cam) <= .01:
                continue
            px = np.array([[CAMERA_CX_PX + CAMERA_FX_PX * q[0] / q[2], CAMERA_CY_PX + CAMERA_FY_PX * q[1] / q[2]]
                           for q in cam], np.float64)
            cv2.fillConvexPoly(mask, np.round(px).astype(np.int32), 1)
    return mask.astype(bool)


def analyse_side(tool_z: float | None = None) -> dict:
    scene, model, data, beam, xml_sha = build_pair_scene()
    tool_z = uc.recommended_carry_tool_z() if tool_z is None else tool_z
    lift = uc.lift_ik(tool_z)
    arm_base = {}
    modes = {}
    masks = {}
    for mode in ('straight', 'side'):
        ranges, err, bottom = place_formation(model, data, beam, mode, SIDE_BEAM_CENTER, lift)
        row = {'yaw_pwm': YAW_PWM[mode], 'heading_deg': {r: round(math.degrees(h), 1) for r, h in HEADING[mode].items()},
               'sim_joint_ranges_ok': all(v['within_range'] for r in ranges.values() for v in r.values()),
               'arm_yaw_rad': {r: ranges[r]['arm_yaw']['target_rad'] for r in ranges},
               'grip_site_error_m': err, 'footprint': footprint(model, data, beam),
               'sonar_open_floor': {r: sonar_view(scene, model, data, r, beam) for r in ('r1', 'r2')},
               'bar_clearance': {r: clearance(model, data, beam, r) for r in ('r1', 'r2')},
               'tip_over': {r: {**{k: v for k, v in tip_margins(model, data, r, _site(model, data, r)).items()
                                   if k != 'static_forward_restoring_ratio'},   # assumes a forward load
                                **static_ratios(model, data, r, _site(model, data, r))} for r in ('r1', 'r2')}}
        root = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'r1__robot')
        ab = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'r1__arm_yaw_link') if mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, 'r1__arm_yaw_link') >= 0 else None
        j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, 'r1__arm_yaw')
        anchor = data.xanchor[j] - data.xpos[root]
        R = data.xmat[root].reshape(3, 3)
        arm_base = {'yaw_axis_offset_from_chassis_origin_m': [round(float(v), 4) for v in (R.T @ anchor)[:2]]}
        # doorway: side mode strafes along the beam through door_1; straight mode drives along it
        door = {}
        grip_x = uc.BEAM_LENGTH_M / 2 - uc.GRIP_FROM_END_M
        reach = grip_x + uc.GRASP_RADIUS_M
        for who, cx in (('r2_in_door', DOOR_1['center'][0] - reach), ('r1_in_door', DOOR_1['center'][0] + reach)):
            place_formation(model, data, beam, mode, (cx, DOOR_1['center'][1]), lift)
            door[who] = {r: sonar_view(scene, model, data, r, beam) for r in ('r1', 'r2')}
        fp = row['footprint']
        row['door_crossing_axial'] = {'sonar': door, 'width_across_m': fp['across_beam_m'],
                                      'clearance_per_side_0.5m': round((.5 - fp['across_beam_m']) / 2, 4),
                                      'clearance_per_side_1.0m': round((1. - fp['across_beam_m']) / 2, 4)}
        pulses = {**lift['pulses'], 6: YAW_PWM[mode]['r1']}
        yaw = (YAW_PWM[mode]['r1'] - 1500) / va.PULSE_PER_DEGREE
        try:
            masks[mode] = camera_bar_mask_yawed(pulses, bottom, math.radians(yaw))
            row['wrist_camera_bar_pixels_r1'] = int(masks[mode].sum())
        except Exception as exc:                       # extrinsics outside the calibrated pan sector
            row['wrist_camera_error'] = repr(exc)
        modes[mode] = row
    if len(masks) == 2:
        modes['side']['wrist_camera_iou_vs_straight'] = round(iou(masks['side'], masks['straight']), 3)
    act = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, 'r1__servo_arm_yaw')
    j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, 'r1__arm_yaw')
    fr = float(model.actuator_forcerange[act][1])
    r = uc.GRASP_RADIUS_M
    torque = {
        'gravity_about_vertical_yaw_axis_Nm': 0.0,
        'note': 'the arm lies along the beam in both modes, so the yaw servo load is mode-independent: '
                'forces across the beam (lateral leg, formation error across the beam) load yaw; '
                'forces along the beam (axial leg) load the arm along its length',
        'lever_m': r, 'sim_forcerange_Nm': fr, 'sim_joint_range_rad': [float(v) for v in model.jnt_range[j]],
        'sim_force_at_grip_limit_N': round(fr / r, 2),
        'real_servo_assumed': 'LD-1501MG (standard-servo family per docs/decision_log.md; 17 kg·cm vendor listing, voltage unconfirmed)',
        'real_stall_Nm_assumed': round(17 * 9.81 / 100, 3),
        'real_force_at_grip_stall_N': round(17 * 9.81 / 100 / r, 2),
        'half_beam_inertia_torque_at_1mps2_Nm': round(LOAD_SHARE_KG * 1. * r, 4),
        'one_robot_traction_torque_mu0.5_Nm': round(.5 * 1.1 * 9.81 * r, 3)}
    return {'schema': 'ugrp.ultrasonic_side_grasp_analysis.v1', 'scene_xml_sha256': xml_sha,
            'tool_z_m': tool_z, 'lift_pulses': lift['pulses'], 'pitch_deg': round(lift['pitch_deg'], 2),
            'expected_bar_bottom_m': round(uc.expected_bar_bottom(lift['tool_z_m']), 4),
            'arm_yaw_axis': arm_base, 'yaw_servo_load': torque,
            'calibrated_pan_sector_pwm': [va.CALIBRATED_PAN_MIN, va.CALIBRATED_PAN_MAX],
            'axial_leg_leader_facing': {
                'needed_arm_yaw_deg': 180., 'joint_limit_deg': round(math.degrees(float(model.jnt_range[j][1])), 1),
                'best_heading_off_travel_deg': round(180. - math.degrees(float(model.jnt_range[j][1])), 1),
                'cone_half_angle_deg': DEFAULT_SPEC.half_angle_deg},
            'modes': modes}


# --- v2 vs v3 (PR #249 drawing layout) geometry ------------------------------------------------

def _solo_block(geom, spec):
    out = {}
    for kind, item in uc.SOLO_ITEMS.items():
        try:
            g = uc.solo_lift(item, .095)['grasp_pitch_deg']
        except ValueError as exc:
            out[kind] = {'grasp_or_hover_ik': repr(exc)}
            continue
        row = {}
        for half in (15., 7.5):
            try:
                row[f'straight_min_tool_z_{half:g}'] = uc.recommended_solo_tool_z(
                    kind, spec, half_angle_deg=half, arm_axis_x_m=geom.arm_axis_x_m)
            except ValueError as exc:
                row[f'straight_min_tool_z_{half:g}'] = repr(exc)
        hover = uc.solo_posture_margins(item, uc.solo_lift(item, .095)['pulses'], g, spec, arm_axis_x_m=geom.arm_axis_x_m)
        p30 = uc.solo_posture_margins(item, uc.CARRY_P30, g, spec, arm_axis_x_m=geom.arm_axis_x_m,
                                      extra_tilts_deg=(uc.CARRY_P30_RECORDED_TILT_DEG,))
        row['hover_0.095_min_margin_m'] = min(c['margin_m'] for c in hover['cases'].values())
        row['carry_p30'] = {'tool_x_m': p30['tool_x_m'], 'tool_z_m': p30['tool_z_m'], 'pitch_deg': p30['pitch_deg'],
                            'clear': p30['clear'], 'min_margin_m': min(c['margin_m'] for c in p30['cases'].values()),
                            'item_front_beyond_sensor_m': p30['item_front_beyond_sensor_m'],
                            'stop_distance_m': round(uc.solo_stop_distance(p30['item_front_beyond_sensor_m']), 4)}
        out[kind] = row
    return out


def _pair_block(geom, spec):
    req = {c: {f'{h:g}': round(uc.required_heights(c, spec, half_angle_deg=h, arm_axis_x_m=geom.arm_axis_x_m)
                               ['tool_z_min_m'], 4) for h in (15., 7.5)} for c in ('near_face', 'whole_beam')}
    near = uc.required_heights('near_face', spec, arm_axis_x_m=geom.arm_axis_x_m)['near_face_from_sensor_m']
    out = {'near_face_from_sensor_m': round(near, 4), 'required_tool_z_m': req,
           'max_tool_z_calibrated': uc.max_tool_z(), 'max_tool_z_any_pitch_le_0': uc.max_tool_z(pitch_range_deg=(-90, 0))}
    try:
        rec = uc.recommended_carry_tool_z(spec, arm_axis_x_m=geom.arm_axis_x_m)
        lift = uc.lift_ik(rec)
        out.update(recommended_tool_z_m=rec, pitch_deg=round(lift['pitch_deg'], 2),
                   pitch_change_from_grasp_deg=round(lift['pitch_change_from_grasp_deg'], 2))
    except ValueError as exc:
        out['recommended_tool_z_m'] = repr(exc)
    return out


def own_arm_cone_angles(model, data, pulses, geom, n=5) -> dict:
    """Smallest off-axis angle of any own arm/gripper point (AABB grid, conservative) seen from the sensor.

    The SIM arm chain (v2) is posed kinematically; for another geometry the arm points are shifted by
    its arm-axis offset and compared with its sensor mount. Points behind the sensor plane are ignored.
    """
    _free(model, data, 'r1__base_free', 3.0, -2.6, .0325, 0.)
    set_arm(model, data, 'r1', pulses)
    mujoco.mj_forward(model, data)
    root = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'r1__robot')
    arm_root = int(model.jnt_bodyid[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, 'r1__arm_yaw')])
    R, base = data.xmat[root].reshape(3, 3), data.xpos[root]
    sensor = np.array([geom.mount_x_m, 0., geom.mount_z_m])
    grid = np.array([(a, b, c) for a in np.linspace(-1, 1, n) for b in np.linspace(-1, 1, n) for c in np.linspace(-1, 1, n)])
    best = (180., None)
    for g in _robot_geoms(model, 'r1'):
        if not _descends(model, int(model.geom_bodyid[g]), arm_root):
            continue
        c, h = model.geom_aabb[g][:3], model.geom_aabb[g][3:]
        Rg = data.geom_xmat[g].reshape(3, 3)
        pts = (data.geom_xpos[g] + (grid * h + c) @ Rg.T - base) @ R           # robot frame (origin at axle height)
        pts[:, 2] += float(base[2])                                           # floor frame
        pts[:, 0] += geom.arm_axis_x_m
        d = pts - sensor
        ahead = d[:, 0] > 1e-4
        if not ahead.any():
            continue
        ang = np.degrees(np.arctan2(np.hypot(d[ahead, 1], d[ahead, 2]), d[ahead, 0]))
        k = int(np.argmin(ang))
        if ang[k] < best[0]:
            best = (float(ang[k]), mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g))
    return {'min_off_axis_deg': round(best[0], 2), 'geom': best[1],
            'in_15deg_cone': best[0] < DEFAULT_SPEC.half_angle_deg}


def min_tool_z(radius_m: float = uc.GRASP_RADIUS_M, pitch_range_deg=uc.IK_PITCH_RANGE_DEG, step_m: float = .001):
    """Lowest grip z the controller IK solves at this radius (safe PWM), current link lengths."""
    for i in range(0, 400):
        z = i * step_m
        for pitch in range(int(pitch_range_deg[0]), int(pitch_range_deg[1]) + 1):
            if va._ik_at_pitch(radius_m * 100., z * 100. - va.ROBOT_BASE_FLOOR_HEIGHT_CM, float(pitch)) is not None:
                return {'tool_z_m': round(z, 4), 'pitch_deg': pitch}
    return {'tool_z_m': None, 'pitch_deg': None}


def analyse_geometries() -> dict:
    _, model, data, _, _ = build_pair_scene()
    _free(model, data, 'r2__base_free', 4.8, .45, .0325, 0.)
    out = {'schema': 'ugrp.ultrasonic_geometry_compare.v1',
           'note': 'v3 = draft PR #249 drawing layout (not measured); analytic only (no v3 MuJoCo model in this branch). '
                   'Own-arm cone check poses the v2 SIM arm chain and shifts it by the v3 arm-axis offset.',
           'geometries': {}}
    for name, geom in uc.GEOMETRIES.items():
        spec = geom.spec()
        pair_z = uc.recommended_carry_tool_z(spec, arm_axis_x_m=geom.arm_axis_x_m)
        lift = uc.lift_ik(pair_z)['pulses']
        arm_cone = {'pair_straight_lift': own_arm_cone_angles(model, data, lift, geom),
                    'pair_side_lift_yaw-90': own_arm_cone_angles(model, data, {**lift, 6: 500}, geom),
                    'solo_carry_p30': own_arm_cone_angles(model, data, dict(uc.CARRY_P30), geom)}
        for kind in uc.SOLO_ITEMS:
            z = uc.recommended_solo_tool_z(kind, spec, arm_axis_x_m=geom.arm_axis_x_m)
            arm_cone[f'solo_straight_{kind}_{z:g}'] = own_arm_cone_angles(
                model, data, uc.solo_lift(uc.SOLO_ITEMS[kind], z)['pulses'], geom)
        out['geometries'][name] = {
            'geometry': asdict(geom), 'pair_straight': _pair_block(geom, spec), 'solo': _solo_block(geom, spec),
            'own_arm_in_cone': arm_cone,
            'pair_side': {'beam_front_x_m': round(geom.arm_axis_x_m + .02, 4), 'sensor_x_m': geom.mount_x_m,
                          'beam_behind_sensor_plane_by_m': round(geom.mount_x_m - geom.arm_axis_x_m - .02, 4),
                          'robot_centre_offset_from_beam_axis_m': geom.arm_axis_x_m,
                          'turn_90_about_centre_grip_shift_m': round(uc.turn_in_place_grip_shift_m(90., geom), 4),
                          'straight_formation_length_change_m': round(2 * geom.arm_axis_x_m, 4)}}
    sens = {}
    v3 = uc.GEOMETRY_V3
    for label, l2, gr in (('sdk_6.5_10.0', None, None), ('upper_5.77', uc.DRAWING_LINK2_CM, None),
                          ('gripper_9.4', None, uc.DRAWING_GRIPPER_CM),
                          ('both', uc.DRAWING_LINK2_CM, uc.DRAWING_GRIPPER_CM)):
        with uc.arm_links(l2, gr):
            row = {'link2_cm': va.LINK_2_CM, 'gripper_cm': va.GRIPPER_LINK_CM,
                   'min_tool_z_calibrated_m': min_tool_z(),
                   'max_tool_z_calibrated': uc.max_tool_z(),
                   'max_tool_z_any_pitch_le_0': uc.max_tool_z(pitch_range_deg=(-90, 0))}
            try:
                g = uc.grasp_pose()
                row['grasp_pitch_deg'] = round(va.tool_pose(g).pitch_deg, 2)
            except ValueError as exc:
                row['grasp_pitch_deg'] = repr(exc)
            row['v3_pair'] = _pair_block(v3, v3.spec())
            row['v3_solo'] = _solo_block(v3, v3.spec())
        sens[label] = row
    out['v3_link_sensitivity'] = sens
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--solo-out', type=Path, default=None, help='also write the solo-carry analysis here')
    p.add_argument('--side-out', type=Path, default=None, help='also write the side-grasp pair analysis here')
    p.add_argument('--geometry-out', type=Path, default=None, help='also write the v2/v3 geometry comparison here')
    a = p.parse_args(argv)
    _forbid_physics()
    if a.solo_out is not None:
        solo = analyse_solo()
        a.solo_out.parent.mkdir(parents=True, exist_ok=True)
        a.solo_out.write_text(json.dumps(solo, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
    if a.geometry_out is not None:
        geo = analyse_geometries()
        a.geometry_out.parent.mkdir(parents=True, exist_ok=True)
        a.geometry_out.write_text(json.dumps(geo, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
    if a.side_out is not None:
        side = analyse_side()
        a.side_out.parent.mkdir(parents=True, exist_ok=True)
        a.side_out.write_text(json.dumps(side, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
    result = analyse()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
    print(json.dumps({'recommended_tool_z_m': result['recommended_tool_z_m'],
                      'heights': [{k: h.get(k) for k in ('commanded_tool_z_m', 'ik_feasible', 'pitch_deg',
                                                         'expected_bar_bottom_m', 'sonar')} for h in result['heights']]},
                     indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
