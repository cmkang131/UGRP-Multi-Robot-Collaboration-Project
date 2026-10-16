"""평가 전용: v3 시작 자세 접촉·카메라 가림. mj_forward만 사용한다."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import mujoco
import numpy as np

from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2
from sim.multi_masterpi_production import build_multi_robot_xml
from sim.zone_masterpi_v3_scene import MAP_IDS
from sim.zone_own_scene_provider import own_scene
from sim.zone_cargo_contact import apply as apply_cargo_profile

START_PWM = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}
JOINT_NAMES = {'yaw': 'arm_yaw', 'shoulder': 'shoulder', 'elbow': 'elbow', 'wrist': 'wrist_pitch'}


def set_static_pwm(model, data, rid, pwm):
    targets = MasterPiDynamicsV2.pulse_to_joint_targets(
        SimpleNamespace(physical_params={'servo6_center_pwm': 1500}), pwm)
    for key, value in targets.items():
        names = ('left_gripper_close', 'right_gripper_close') if key == 'gripper' else (JOINT_NAMES[key],)
        for name in names:
            joint = model.joint(rid + '__' + name)
            if model.jnt_limited[joint.id]:
                value = float(np.clip(value, *model.jnt_range[joint.id]))
            data.qpos[model.jnt_qposadr[joint.id]] = value


def compile_start(name, *, seed=700):
    scene = own_scene({'map': name, 'seed': seed, 'goal': {'A': {'cyan': 1}}, 'team_cargo': []},
                      'cargo_noslip_v1')
    environment = scene.transform(build_multi_robot_xml(None, navigation_camera=True))
    xml = scene.robot_transform(apply_cargo_profile(environment, 'cargo_noslip_v1'))
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    for rid, pose in scene.config['setup_only']['spawns'].items():
        body = model.body(rid + '__robot')
        q = model.jnt_qposadr[model.body_jntadr[body.id]]
        data.qpos[q:q + 7] = [*pose[:3], math.cos(pose[3]/2), 0., 0., math.sin(pose[3]/2)]
        set_static_pwm(model, data, rid, START_PWM)
    for obj in scene.config['setup_only']['objects'].values():
        q = model.jnt_qposadr[model.joint(obj['joint_name']).id]
        data.qpos[q:q + 7] = [*obj['position_m'], 1., 0., 0., 0.]
    data.eq_active[:] = 0
    mujoco.mj_forward(model, data)
    return scene, model, data, xml


def camera_occlusion(model, data, camera, *, columns=17, rows=13):
    """Finite pinhole-ray sample; report self hits, not a visibility guarantee.

Use the same group 4/5 exclusions as the production own-camera renderer.
No images/depth/contacts from this diagnostic are passed to a controller.
"""
    cid = model.camera(camera).id
    origin = data.cam_xpos[cid]
    rotation = data.cam_xmat[cid].reshape(3, 3)
    scale = math.tan(math.radians(float(model.cam_fovy[cid])) / 2)
    groups = np.ones(6, dtype=np.uint8)
    groups[4:6] = 0
    prefix = camera.split('__')[0] + '__'
    hits = {}
    self_hits = 0
    for y in np.linspace(-1, 1, rows):
        for x in np.linspace(-1, 1, columns):
            direction = rotation @ np.array([x * scale * 640/480, y * scale, -1.])
            direction /= np.linalg.norm(direction)
            gid = np.array([-1], dtype=np.int32)
            distance = mujoco.mj_ray(model, data, origin, direction, groups, True, -1, gid)
            if distance >= 0 and gid[0] >= 0:
                name = model.geom(int(gid[0])).name
                if name.startswith(prefix):
                    self_hits += 1
                    hits[name] = hits.get(name, 0) + 1
    return {'rays': rows*columns, 'self_hits': self_hits, 'self_fraction': self_hits/(rows*columns),
            'self_geoms': hits, 'geomgroup': groups.tolist(),
            'scope': 'raw_pinhole_sample_not_fisheye_render_or_task_visibility'}


def audit(name, *, seed=700):
    scene, model, data, xml = compile_start(name, seed=seed)
    contacts = []
    for i in range(data.ncon):
        contact = data.contact[i]
        names = [model.geom(int(g)).name for g in (contact.geom1, contact.geom2)]
        robots = [n.split('__')[0] if '__' in n else None for n in names]
        if any(robots) and float(contact.dist) < -1e-8:
            kind = 'self' if robots[0] is not None and robots[0] == robots[1] else (
                'peer' if all(robots) else 'environment')
            contacts.append({'kind': kind, 'geoms': names, 'penetration_m': -float(contact.dist)})
    cameras = {rid + '__' + cam: camera_occlusion(model, data, rid + '__' + cam)
               for rid in ('r1', 'r2', 'r3') for cam in ('nav_cam', 'robot_cam')}
    return {'schema': 'ugrp.masterpi_v3_static_audit.v1', 'scene': name, 'seed': seed,
            'robot_model': scene.config['robot_model'], 'mujoco': mujoco.__version__,
            'contact_profile': 'cargo_noslip_v1', 'noslip_iterations': int(model.opt.noslip_iterations),
            'runtime_engine_layout': scene.engine_layout,
            'nav_cam_scope_ko': 'standard host에는 nav_cam이 없음. 같은 builder의 navigation_camera=True로 추가한 고정 카메라 진단.',
            'scene_xml_sha256': hashlib.sha256(xml.encode()).hexdigest(),
            'start_pwm': START_PWM, 'setup_only_spawns': scene.config['setup_only']['spawns'],
            'contacts': contacts, 'cameras': cameras, 'mj_step_calls': 0, 'sim_time_s': float(data.time),
            'active_welds': int(np.count_nonzero(data.eq_active)), 'model_calls': 0,
            'verdict_ko': '정적 진단만 수행. 파지·주행·운반·실물 성공 판정 없음.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('기존 감사 기록을 덮어쓰지 않습니다')
    args.output.write_text(json.dumps([audit(name) for name in MAP_IDS], ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
