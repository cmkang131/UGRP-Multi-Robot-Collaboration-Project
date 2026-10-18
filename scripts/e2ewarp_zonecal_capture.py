#!/usr/bin/env python3
"""GPU zone-B appearance calibration capture (NOT a research result).

Renders the recorded e2ewarp R4 scene with the MJWarp native renderer from
experimenter-configured poses that show the zone-B floor paint, using the same
camera, remap and JPEG settings as the recorded own frames. No LLM, no control,
no physics stepping, no policy. Map/zone geometry and the actual camera pose are
used only to configure the poses and to write eval-only labels; the capture is
labelled "GPU appearance calibration, not research result" and is never pooled
with any experiment result.
"""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import cv2
import mujoco
import mujoco_warp as mjw
import warp as wp

ZONE_RECT = (4.30, 4.90, -2.80, -1.40)
ZONE_CENTER = (4.60, -2.10)
DOOR = (2.20, 0.05)
# Issued R4 unloaded SEARCH arm command (same as the recorded own frames).
PWM = {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1000}
BASE_Z = 0.0325
RES = (640, 480)
JPEG_QUALITY = 82


def quat_yaw(yaw):
    return [math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)]


def rot2(u, ang):
    c, s = math.cos(ang), math.sin(ang)
    return (c * u[0] - s * u[1], s * u[0] + c * u[1])


def zone_poses():
    """Experimenter-configured poses; camera aimed at the label target by FK.

    Base positions were chosen from the zone-B static-map rectangle with the
    same SEARCH arm command as the recorded own frames.  The aim target is an
    eval-only label; the detector never receives it.
    """
    ZONE_A = (4.60, 0.40)
    PICKUP = (0.70, -0.85)
    specs = [
        ('zoneB_d0.45_a0', 'zone_B', (4.265, -1.800), ZONE_CENTER),
        ('zoneB_d0.60_a0', 'zone_B', (4.153, -1.701), ZONE_CENTER),
        ('zoneB_d0.60_am40', 'zone_B', (4.620, -1.500), ZONE_CENTER),
        ('zoneB_d0.60_ap40', 'zone_B', (4.010, -2.190), ZONE_CENTER),
        ('zoneB_d0.90_a0', 'zone_B', (3.930, -1.500), ZONE_CENTER),
        ('zoneB_d0.90_ap40', 'zone_B', (3.710, -2.230), ZONE_CENTER),
        ('zoneB_d1.20_am25', 'zone_B', (3.710, -1.300), ZONE_CENTER),
        ('zoneB_d1.60_a0', 'zone_B', (3.410, -1.030), ZONE_CENTER),
        ('zoneB_d2.10_ap25', 'zone_B', (2.730, -1.150), ZONE_CENTER),
        ('zoneB_d3.00_a0', 'zone_B', (2.360, -0.130), ZONE_CENTER),
        ('neg_pickup_blue', 'pickup_zone', (-0.200, 0.600), PICKUP),
        ('neg_zoneA_orange', 'zone_A', (4.600, 1.500), ZONE_A),
    ]
    poses = []
    for name, kind, xy, aim in specs:
        poses.append(dict(id=name, kind=kind, base_xy=list(xy),
                          aim_xy=list(aim)))
    return poses


def base_yaw(model, xy, aim, joint_targets):
    """Yaw so the wrist camera (FK) points at ``aim``; experimenter setup only."""
    x, y = float(xy[0]), float(xy[1])
    yaw = 0.0
    for _ in range(10):
        qpos = build_qpos(model, (x, y, yaw), joint_targets)
        data = mujoco.MjData(model)
        data.qpos[:] = qpos
        mujoco.mj_forward(model, data)
        cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA,
                                   'r1__robot_cam')
        cam_xpos = np.array(data.cam_xpos[cam_id])
        cam_xmat = np.array(data.cam_xmat[cam_id]).reshape(3, 3)
        fwd = -cam_xmat[:, 2]  # MuJoCo camera looks along -z
        cam_yaw = math.atan2(fwd[1], fwd[0])
        want = math.atan2(float(aim[1]) - cam_xpos[1],
                          float(aim[0]) - cam_xpos[0])
        yaw += want - cam_yaw
    return yaw


def load_fk(pwm):
    sys.path.insert(0, '/home/ugrp/ugrp-sim/src/e2ewarp-r4-src')
    import harness.servo_camera_fk as fk
    pose, reason = fk.transform_from_commands(pwm, camera_pose='servo_fk_v1')
    if pose is None:
        raise SystemExit('FK unavailable: ' + reason)
    translation, rotation = pose
    return {int(k): int(v) for k, v in pwm.items()}, reason, rotation, translation


def build_qpos(model, base, joint_targets):
    qpos = np.array(model.qpos0, dtype=float)
    qpos[0:3] = [base[0], base[1], BASE_Z]
    qpos[3:7] = quat_yaw(base[2])
    # Fixed servo->joint mapping of the v3 chain: 3 arm_yaw, 4 shoulder,
    # 5 elbow, 6 wrist_pitch (from harness/servo_camera_fk.py).
    for servo, joint in ((3, 'r1__arm_yaw'), (4, 'r1__shoulder'),
                         (5, 'r1__elbow'), (6, 'r1__wrist_pitch')):
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint)
        if jid < 0:
            raise SystemExit('missing joint ' + joint)
        qpos[int(model.jnt_qposadr[jid])] = joint_targets[servo]
    for other, xy in (('r2', (-1.2, 0.6)), ('r3', (-1.2, -0.6))):
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT,
                                other + '__base_free')
        adr = int(model.jnt_qposadr[jid])
        qpos[adr:adr + 3] = [xy[0], xy[1], BASE_Z]
        qpos[adr + 3:adr + 7] = [1., 0., 0., 0.]
    return qpos


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--scene', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--source-root', type=Path,
                    default=Path('/home/ugrp/ugrp-sim/src/e2ewarp-r4-src'))
    ap.add_argument('--nworld-chunk', type=int, default=33)
    a = ap.parse_args()
    sys.path.insert(0, str(a.source_root))
    from sim.masterpi_camera_profile import (raw_fisheye_remap,
                                             scaled_camera_matrix,
                                             CAMERA_FISHEYE_D)
    pwm, fk_reason, fk_rot, fk_trans = load_fk(PWM)
    model = mujoco.MjModel.from_xml_path(str(a.scene))
    data = mujoco.MjData(model)
    poses = zone_poses()
    jt = {3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0}
    import harness.servo_camera_fk as fkmod2
    _, joints0 = fkmod2.commanded_joints(pwm)
    for servo, ang in joints0.items():
        jt[int(servo)] = float(ang)
    for pose in poses:
        pose['yaw'] = base_yaw(model, pose['base_xy'], pose['aim_xy'], jt)
    frames = []
    for pose in poses:
        for k, dyaw in enumerate((0.0, 0.008, -0.008)):
            row = dict(pose)
            row['frame'] = k
            row['sim_s'] = 0.5 * k
            row['base'] = [row['base_xy'][0], row['base_xy'][1],
                           row['yaw'] + dyaw]
            frames.append(row)
    wp.init()
    wp.set_device('cuda:0')
    wm = mjw.put_model(model)
    wd = mjw.put_data(model, data, nworld=len(frames), nconmax=64, njmax=512)
    qpos_np = np.zeros((len(frames), model.nq), dtype=float)
    joint_targets = {3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0}
    import harness.servo_camera_fk as fkmod
    _, joints = fkmod.commanded_joints(pwm)
    for servo, ang in joints.items():
        joint_targets[int(servo)] = float(ang)
    for i, row in enumerate(frames):
        qpos_np[i] = build_qpos(model, row['base'], joint_targets)
    wp.copy(wd.qpos, wp.array(qpos_np, dtype=float))
    rc = mjw.create_render_context(
        model, nworld=len(frames), cam_res=RES, render_rgb=True,
        render_depth=False, render_seg=False, use_textures=True,
        use_shadows=True, enabled_geom_groups=[0, 1, 2, 3],
        cam_active=['r1__robot_cam'])
    device_rgb = wp.zeros((len(frames), RES[1], RES[0]), dtype=wp.vec3)
    mx, my = raw_fisheye_remap(*RES)
    t0 = time.perf_counter()
    mjw.kinematics(wm, wd)
    mjw.camlight(wm, wd)
    mjw.refit_bvh(wm, wd, rc)
    mjw.render(wm, wd, rc)
    wp.synchronize()
    mjw.get_rgb(rc, 0, device_rgb)
    wp.synchronize()
    render_s = time.perf_counter() - t0
    images = np.clip(device_rgb.numpy() * 255, 0, 255).astype(np.uint8)
    cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA,
                               'r1__robot_cam')
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / 'rgb').mkdir(exist_ok=True)
    records = []
    for i, row in enumerate(frames):
        rgb = cv2.remap(images[i], mx, my, cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_CONSTANT)
        name = f"{row['id']}-f{row['frame']}-r1.jpg"
        path = a.out / 'rgb' / name
        cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                    [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        data.qpos[:] = qpos_np[i]
        mujoco.mj_forward(model, data)
        cam_xpos = np.array(data.cam_xpos[cam_id], dtype=float)
        cam_xmat = np.array(data.cam_xmat[cam_id], dtype=float)
        records.append(dict(
            frame=name, pose_id=row['id'], kind=row['kind'],
            frame_in_pose=row['frame'], sim_s=row['sim_s'],
            label='GPU appearance calibration, not research result',
            base_pose_eval_only=[float(v) for v in row['base']],
            aim_xy_eval_only=list(row['aim_xy']),
            distance_m=(math.hypot(row['aim_xy'][0] - row['base_xy'][0],
                                   row['aim_xy'][1] - row['base_xy'][1])),
            zone_rect_static_map=list(ZONE_RECT),
            zone_center_static_map=list(ZONE_CENTER),
            issued_arm_pwm={k: int(v) for k, v in pwm.items()},
            fk_camera=dict(reason=fk_reason,
                           translation_m=[float(v) for v in fk_trans],
                           rotation=[float(v) for v in np.asarray(fk_rot).reshape(-1)]),
            actual_camera_pose_eval_only=dict(xpos=[float(v) for v in cam_xpos],
                                              xmat=[float(v) for v in cam_xmat.reshape(-1)]),
            image_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            image_bytes=path.stat().st_size))
    sha_scene = hashlib.sha256(a.scene.read_bytes()).hexdigest()
    remap_sha = hashlib.sha256(mx.tobytes() + my.tobytes()).hexdigest()
    conditions = dict(
        schema='ugrp.e2ewarp.zonecal_capture.v1',
        label='GPU appearance calibration, not research result',
        not_pooled_with=['crossroom conditions', 'R1..R4 e2ewarp attempts',
                         'visgoal gates', 'any research result'],
        scene=a.scene.name, scene_sha256=sha_scene,
        source_sha='718777118be41991156b047faff78621969101bb',
        renderer=dict(backend='mujoco_warp native render',
                      cam_active=['r1__robot_cam'], cam_res=list(RES),
                      use_textures=True, use_shadows=True,
                      enabled_geom_groups=[0, 1, 2, 3],
                      remap='sim.masterpi_camera_profile.raw_fisheye_remap',
                      remap_sha256=remap_sha, jpeg_quality=JPEG_QUALITY,
                      render_wall_s=round(render_s, 4)),
        physics='no stepping, no control, no LLM; static qpos render only',
        camera='own r1 wrist camera, SEARCH arm command PWM ' + json.dumps(PWM),
        poses=[dict(id=p['id'], kind=p['kind'], base_xy=p['base_xy'],
                    aim_xy=p['aim_xy'], yaw_rad=round(p['yaw'], 5))
               for p in poses], frames_per_pose=3,
        capture_hz='2 Hz (0.5 SIM s labelled spacing; static pose)',
        n_frames=len(records),
        eval_only_notes=['base_pose_eval_only', 'actual_camera_pose_eval_only',
                         'distance_m', 'angle_deg'],
        allowed_inputs_for_calibration=['own RGB frames (this capture)',
                                        'issued arm PWM / servo FK',
                                        'static map zone rectangle'],
        sha256={r['frame']: r['image_sha256'] for r in records})
    (a.out / 'conditions.json').write_text(
        json.dumps(conditions, indent=2, ensure_ascii=False) + '\n')
    (a.out / 'frames.json').write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + '\n')
    lines = []
    for p in sorted(a.out.rglob('*')):
        if p.is_file() and p.name != 'SHA256SUMS.json':
            lines.append(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' +
                         str(p.relative_to(a.out)))
    (a.out / 'SHA256SUMS.json').write_text('\n'.join(lines) + '\n')
    (a.out / 'README.md').write_text(
        '# GPU zone-B appearance calibration capture\n\n'
        '**GPU appearance calibration, not research result.** No LLM, no control,\n'
        'no physics stepping; experimenter-configured static poses of the\n'
        'recorded R4 scene rendered with the MJWarp native renderer, same camera\n'
        'and raw-fisheye remap/JPEG settings as the recorded own frames. Zone\n'
        f'rectangle {ZONE_RECT} and pose/label fields are eval-only. Not pooled\n'
        'with any research result.\n')
    print(json.dumps(dict(frames=len(records), scenes_sha=sha_scene,
                          remap_sha=remap_sha, render_wall_s=round(render_s, 4),
                          out=str(a.out), pose_ids=[p['id'] for p in poses]),
                     indent=2))


if __name__ == '__main__':
    main()
