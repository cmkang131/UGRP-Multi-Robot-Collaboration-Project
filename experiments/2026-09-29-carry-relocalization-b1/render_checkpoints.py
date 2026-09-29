"""Static-frame renders of the checkpoint look sweeps in the tag-free final environment (NO physics step).

What runs (sim env, `.venv-sim-worker-mac`):
  * scene: `sim.zone_geometry_scene.GeometryCargoZoneScene` on map `zone_wide_door_geometry_v2`
    (walls_v3 = 0.40 m walls, ZERO AprilTags, no landmark block), robot model v2, contact profile
    `cargo_noslip_v1`; optional render profile (`default` = none, `floor_light_v1`).
  * no controller, no `mj_step`. The scene builder settles ~1.3 SIM s once at construction (same as every other
    world); afterwards only `mj_forward` is called, and the world time is asserted unchanged.
  * per checkpoint the long beam is put on the floor at the route point and r1/r2 stand at the recorded stations
    (beam x -/+ 0.425 m, yaw 0 / pi). r3 stays at its dock. Poses are written into qpos (`set_base_pose_for_test`).
  * per look variant (`p20` = harness.owncam_drive.LOOK_P20 as used by run_m2_pair `_queue_grasp`; `search` =
    SEARCH_POSE) and per pan of `PREGRASP_PANS_V2` the arm is set to the commanded pulses (forward kinematics) and
    then to its STATIC GRAVITY EQUILIBRIUM (Newton solve of qfrc_actuator + qfrc_passive - qfrc_bias = 0 on the four
    arm dofs, velocities zero, no time advance). This reproduces the servo droop that physics settling gives; the
    result is compared with the TRAIN calibration table (`sag_check`).
  * the RGB is `world.render_jpeg` (same fisheye JPEG the harness gets). Segmentation labels (eval-only oracle
    diagnostic) come from the same segmentation-render path as the teacher renders.

Inputs never reach a controller here. Truth poses and labels are written to `eval_only`-named fields/files.

usage: python render_checkpoints.py <out_dir> [--profile default|floor_light_v1] [--checkpoints 0 1 ...] [--no-labels]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments' / '2026-09-26-vision-loc'))

import cv2  # noqa: E402
import mujoco  # noqa: E402
import numpy as np  # noqa: E402

MAP_ID = 'zone_wide_door_geometry_v2'
# Route of the 8-leg carry (beam centre, world m): recorded route of the stage-probe carry cases, as used by the
# PR #276 candidate-point prediction (experiments/2026-09-29-relocalization-audit/cand_points.py).
ROUTE = [[1.0, 0.05], [1.55, 0.05], [2.4, 0.05], [3.2, 0.05], [3.2, -0.6666666666666666], [3.2, -1.3833333333333333],
         [3.2, -2.1], [3.9, -2.1], [4.6, -2.1]]
LABELS = ['start'] + [f'after_L{k}' for k in range(8)]
STATION_M = 0.425                                   # r1 at beam x - 0.425 (yaw 0), r2 at beam x + 0.425 (yaw pi)
STATIONS = {'r1': (-STATION_M, 0.0), 'r2': (STATION_M, math.pi)}
OPEN = 2000
LOOKS = {'p20': {3: 1072, 4: 2400, 5: 1482},          # harness.owncam_drive.LOOK_P20 (run_m2_pair _queue_grasp look)
         'search': {3: 740, 4: 2320, 5: 1320}}         # harness.owncam_drive.SEARCH_POSE arm (unloaded look)
PANS = (1500, 1230, 970, 700, 1770, 2030, 2300)        # unique pans of run_m2_pair.PREGRASP_PANS_V2 (8th frame repeats 1500)
CLASSES = {'floor': 0, 'wall': 1, 'self': 2, 'object': 3, 'background': 4}


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build_world(profile: str):
    from sim.multi_masterpi_production import MultiMasterPiProductionV2
    from sim.zone_cargo_contact import CARGO_PROFILES, apply as apply_cargo_profile
    from sim.zone_geometry_scene import GeometryCargoZoneScene
    from sim.zone_masterpi_v3_scene import scene_robot_model
    from sim.zone_own_scene_provider import own_scene
    spec = {'map': MAP_ID, 'seed': 911, 'goal': {'B': {'cyan': 1}}, 'contact_profile': 'cargo_noslip_v1',
            'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': [ROUTE[0][0], ROUTE[0][1], 0.0]}]}
    scene0 = GeometryCargoZoneScene.from_spec(spec, 'local_contact_fine')
    scene0.config['setup_only']['objects'] = {}
    scene = own_scene(spec, spec['contact_profile'], scene0)
    if scene_robot_model(scene) != 'masterpi_v2':
        raise SystemExit('expected robot model masterpi_v2')
    if profile != 'default':
        from sim import render_profile as rp
        rp.install(scene, profile)
    xf = ((lambda xml: apply_cargo_profile(scene.transform(xml), spec['contact_profile']))
          if spec['contact_profile'] in CARGO_PROFILES else scene.transform)
    world = MultiMasterPiProductionV2(seed=911, width=640, height=480, render=True, warehouse_layout=scene.engine_layout,
                                      warehouse_cargo_ids=None, xml_transform=xf)
    scene.setup(world)
    return world, scene


def place_beam(world, scene, x, y, yaw=0.0):
    m, d = world.model, world.data
    bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, scene.cargo[0].body)
    adr = int(m.jnt_qposadr[int(m.body_jntadr[bid])])
    d.qpos[adr:adr + 2] = [x, y]
    d.qpos[adr + 3:adr + 7] = [math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
    d.qvel[:] = 0
    mujoco.mj_forward(m, d)


def place_robot(world, rid, x, y, yaw):
    r = world.robot(rid)
    r.set_base_pose_for_test((x, y, float(r.base_xyz()[2])), yaw)


def arm_equilibrium(world, rid, iters=40):
    """Static equilibrium of the four arm joints under gravity (no time advance). Returns the max residual torque."""
    m, d, r = world.model, world.data, world.robot(rid)
    jids = [r.arm_joint[n] for n in ('yaw', 'shoulder', 'elbow', 'wrist')]
    qa = [int(m.jnt_qposadr[j]) for j in jids]
    da = [int(m.jnt_dofadr[j]) for j in jids]
    d.qvel[:] = 0

    def resid():
        mujoco.mj_forward(m, d)
        return np.array([d.qfrc_actuator[k] + d.qfrc_passive[k] - d.qfrc_bias[k] for k in da])
    for _ in range(iters):
        f = resid()
        jac = np.zeros((4, 4))
        for c, a in enumerate(qa):
            d.qpos[a] += 1e-5
            jac[:, c] = (resid() - f) / 1e-5
            d.qpos[a] -= 1e-5
        dq = np.linalg.solve(jac, -f)
        for c, a in enumerate(qa):
            d.qpos[a] += dq[c]
        if np.abs(dq).max() < 1e-9:
            break
    return float(np.abs(resid()).max())


def set_look(world, rid, servo):
    r = world.robot(rid)
    r.set_servo_pulses(servo, forward_only=True)
    res = arm_equilibrium(world, rid)
    mujoco.mj_forward(world.model, world.data)
    return res


def camera_truth(world, rid):
    """Eval-only: true camera pose in the base frame and its (elevation bias, height offset) against the commanded FK."""
    r = world.robot(rid)
    cam = world.data.camera(r._n('robot_cam'))
    xyz, rpy = r.base_xyz(), r.base_rpy()
    return {'base_gt': [round(float(xyz[0]), 5), round(float(xyz[1]), 5), round(float(rpy[2]), 6)],
            'cam_pos_m': [round(float(v), 6) for v in cam.xpos], 'cam_xmat': [round(float(v), 7) for v in cam.xmat]}


def sag_of(truth, servo):
    import vision_loc as vl
    x, y, yaw = truth['base_gt']
    c, s = math.cos(yaw), math.sin(yaw)
    rz = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    r_w = np.asarray(truth['cam_xmat'], float).reshape(3, 3) @ np.diag([1., -1., -1.])
    p_b = rz.T @ (np.asarray(truth['cam_pos_m'], float) - np.array([x, y, 0.]))
    b, dz, az = vl.elevation_and_dz(rz.T @ r_w, p_b, servo)
    return float(b), float(dz), float(az)


def make_label_renderer(world):
    """Teacher-style segmentation labels (ideal pinhole, before the fisheye remap) of one robot's camera."""
    m = world.model
    table_by_rid = {}

    def class_table(rid):
        table = np.full(m.ngeom, CLASSES['object'], np.uint8)
        for g in range(m.ngeom):
            n = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ''
            if n == 'floor' or (n.startswith('zone_') and not n.startswith('zone_wall_')):
                table[g] = CLASSES['floor']
            elif n.startswith('zone_wall_'):
                table[g] = CLASSES['wall']
            elif n.startswith(rid + '__'):
                table[g] = CLASSES['self']
        return table

    def render(rid):
        robot = world.robot(rid)
        if rid not in table_by_rid:
            table_by_rid[rid] = class_table(rid)

        def fn():
            with world.physics_lock, world.render_lock:
                robot._sync_real_camera_mount()
                r = world.renderer
                r.enable_segmentation_rendering()
                try:
                    r.update_scene(world.data, camera=robot._n('robot_cam'), scene_option=robot._robot_sensor_scene_option)
                    seg = r.render().copy()
                finally:
                    r.disable_segmentation_rendering()
            return seg
        seg = fn() if threading.get_ident() == world._render_thread_id else world._render_executor.submit(fn).result(timeout=30.)
        objid, objtype = seg[..., 0], seg[..., 1]
        label = np.full(objid.shape, CLASSES['background'], np.uint8)
        geom = (objtype == int(mujoco.mjtObj.mjOBJ_GEOM)) & (objid >= 0)
        label[geom] = table_by_rid[rid][objid[geom]]
        label[(objid >= 0) & ~geom] = CLASSES['object']
        return label
    return render


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('out_dir')
    ap.add_argument('--profile', default='default', choices=('default', 'floor_light_v1'))
    ap.add_argument('--checkpoints', type=int, nargs='*', default=list(range(len(ROUTE))))
    ap.add_argument('--looks', nargs='*', default=list(LOOKS))
    ap.add_argument('--no-labels', action='store_true')
    a = ap.parse_args(argv)
    out = Path(a.out_dir)
    (out / 'frames').mkdir(parents=True, exist_ok=True)
    if not a.no_labels:
        (out / 'eval_only' / 'labels').mkdir(parents=True, exist_ok=True)
    world, scene = build_world(a.profile)
    t_after_build = float(world.data.time)
    label_render = None if a.no_labels else make_label_renderer(world)
    rows, sag_rows = [], []
    for k in a.checkpoints:
        bx, by = ROUTE[k]
        place_beam(world, scene, bx, by)
        for rid, (dx, yaw) in STATIONS.items():
            place_robot(world, rid, bx + dx, by, yaw)
        for look in a.looks:
            arm = LOOKS[look]
            for rid in ('r1', 'r2'):
                partner = 'r2' if rid == 'r1' else 'r1'
                set_look(world, partner, {**arm, 1: OPEN, 6: 1500})      # partner stands with the same look posture, pan centre
                for pan in PANS:
                    servo = {**arm, 1: OPEN, 6: pan}
                    resid = set_look(world, rid, servo)
                    jpeg = bytes(world.render_jpeg(robot_id=rid, camera='robot_cam'))
                    name = f'cp{k}_{rid}_{look}_{pan}'
                    (out / 'frames' / f'{name}.jpg').write_bytes(jpeg)
                    truth = camera_truth(world, rid)
                    bias, dz, az = sag_of(truth, servo)
                    row = {'name': name, 'checkpoint': k, 'label': LABELS[k], 'robot': rid, 'look': look, 'pan': pan,
                           'file': f'frames/{name}.jpg', 'sha256': sha_bytes(jpeg), 'servo': {str(s): int(v) for s, v in servo.items()},
                           'beam_xy': [bx, by], 'eval_only': {**truth, 'sag_bias_rad': round(bias, 5), 'sag_dz_m': round(dz, 5),
                                                              'azimuth_err_rad': round(az, 6), 'arm_equilibrium_resid_nm': resid}}
                    if label_render is not None:
                        lab = label_render(rid)
                        ok, png = cv2.imencode('.png', lab)
                        (out / 'eval_only' / 'labels' / f'{name}.png').write_bytes(png.tobytes())
                        row['eval_only']['label'] = f'eval_only/labels/{name}.png'
                        row['eval_only']['label_sha256'] = sha_bytes(png.tobytes())
                    rows.append(row)
                    sag_rows.append((look, bias, dz))
    assert float(world.data.time) == t_after_build, 'physics advanced while rendering'
    sag = {}
    for look in a.looks:
        b = np.array([s[1] for s in sag_rows if s[0] == look])
        z = np.array([s[2] for s in sag_rows if s[0] == look])
        sag[look] = {'n': int(len(b)), 'bias_rad_median': round(float(np.median(b)), 5), 'bias_rad_min_max': [round(float(b.min()), 5), round(float(b.max()), 5)],
                     'dz_m_median': round(float(np.median(z)), 5)}
    manifest = {'schema': 'ugrp.carry_relocalization_b1.render.v1', 'map_id': MAP_ID, 'render_profile': a.profile,
                'robot_model': 'masterpi_v2', 'world_time_s_after_build': t_after_build, 'world_time_s_after_renders': float(world.data.time),
                'note': 'mj_forward only after the scene was built; arm set to commanded FK then to its static gravity equilibrium',
                'route': ROUTE, 'labels': LABELS, 'station_m': STATION_M, 'looks': {k: v for k, v in LOOKS.items() if k in a.looks},
                'pans': list(PANS), 'sag_check': sag, 'rows': rows}
    (out / 'render_manifest.json').write_text(json.dumps(manifest, indent=1))
    print(len(rows), 'frames ->', out, json.dumps(sag))
    world.close()


if __name__ == '__main__':
    main()
