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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(argv)
    _forbid_physics()
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
