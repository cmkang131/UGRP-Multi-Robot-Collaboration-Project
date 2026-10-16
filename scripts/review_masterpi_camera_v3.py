"""Finite diagnostic on an archived standard Scene; no S2/controller/model call.

v3 user-observation candidate; one unchanged v2 fixture close/lift sequence.
Normal contact, no weld; archived real images are evaluated separately. Fixed commands never
read evaluation state. Capture actual qpos for matched camera comparisons.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.review_masterpi_camera import PRIMARY, JOINT_NAMES, lock_command, rows, sha, write
from sim import masterpi_camera_review_v1 as v1
from sim import masterpi_camera_review_v2 as v2
from sim import masterpi_camera_review_v3 as v3
from sim import masterpi_camera_profile as old

VARIANTS = ('baseline', 'drawing_v1', 'sdk_sample_v2', 'user_v3')


def targets(pose):
    from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2
    return MasterPiDynamicsV2.pulse_to_joint_targets(
        SimpleNamespace(physical_params={'servo6_center_pwm': 1500}), pose)


def set_pose(model, data, rid, pose, *, initialize=False):
    for key, value in targets(pose).items():
        names = [('left_gripper_close', 'servo_gripper_left'),
                 ('right_gripper_close', 'servo_gripper_right')] if key == 'gripper' else [
                     (JOINT_NAMES[key], 'servo_arm_yaw' if key == 'yaw' else 'servo_'+key)]
        for joint, actuator in names:
            jid = model.joint(rid+'__'+joint).id
            lo, hi = model.jnt_range[jid]
            if not lo <= value <= hi:
                raise ValueError('command outside joint range: '+joint)
            data.ctrl[model.actuator(rid+'__'+actuator).id] = value
            if initialize:
                data.qpos[model.jnt_qposadr[jid]] = value


def camera(model, variant):
    cid = model.camera('r3__robot_cam').id
    model.cam_pos[cid] = old.CAMERA_LOCAL_POS_M if variant == 'baseline' else v1.POSITION_M
    model.cam_quat[cid] = (old.CAMERA_LOCAL_QUAT_WXYZ if variant in ('baseline', 'position_only')
                           else v3.QUAT_WXYZ if variant == 'user_v3' else v1.QUAT_WXYZ)
    model.cam_resolution[cid] = [640, 480]
    model.cam_sensorsize[cid] = [640, 480]
    model.cam_intrinsic[cid] = (v2.pixel_intrinsic() if variant == 'sdk_sample_v2'
                                else old.mujoco_pixel_intrinsic(640, 480))
    return cid


def metrics(rgb, valid):
    import cv2
    import numpy as np
    from harness.zone_color_boxes import _mask, OWN_ZONE_CYAN_HSV
    mask = _mask(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV), OWN_ZONE_CYAN_HSV).astype(bool)
    return {'cyan_pixels': int(mask.sum()), 'full_pixels': int(mask.size),
            'valid_pixels': int(valid.sum()), 'full_fraction': float(mask.mean()),
            'valid_fraction': float((mask & valid).sum()/valid.sum())}


def geometry(model, data, cid, cargo):
    import numpy as np
    body = data.body('r3__gripper')
    obj = data.body(cargo['body_name'])
    rot = body.xmat.reshape(3, 3)
    local = rot.T @ (obj.xpos-body.xpos)
    axes = data.cam_xmat[cid].reshape(3, 3)
    corners = np.array(list(itertools.product((-1, 1), repeat=3))) * cargo['half_extents_m']
    world = corners @ obj.xmat.reshape(3, 3).T + obj.xpos
    # OpenCV: right, down, forward, unlike MuJoCo's right, up, backward.
    optical = (world-data.cam_xpos[cid]) @ axes * [1, -1, -1]
    angles = np.degrees(np.arctan2(optical[:, 1], optical[:, 2]))
    return {'cargo_centre_gripper_m': local.tolist(),
            'cargo_corners_optical_m': optical.tolist(),
            'corner_down_angles_deg': [float(angles.min()), float(angles.max())],
            'camera_world_m': data.cam_xpos[cid].tolist(),
            'optical_pitch_world_deg': math.degrees(math.asin(-axes[2, 2])),
            'cargo_world_m': obj.xpos.tolist(),
            'cargo_rotation_world': obj.xmat.tolist()}


def capture(model, data, renderer, option, out, label, phase, cargo):
    import cv2
    import mujoco
    import numpy as np
    result = []
    for variant in VARIANTS:
        cid = camera(model, variant)
        mujoco.mj_forward(model, data)
        renderer.update_scene(data, camera=cid, scene_option=option)
        rgb = renderer.render().copy()
        if variant == 'sdk_sample_v2':
            valid = v2.valid_mask()
            rgb[~valid] = 0
        else:
            x, y = old.raw_fisheye_remap(640, 480)
            valid = (x >= 0) & (x <= 639) & (y >= 0) & (y <= 479)
            rgb = cv2.remap(rgb, x, y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        path = out/f'{label}-{variant}.png'
        cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        result.append({'phase': phase, 't': float(data.time), 'variant': variant,
                       'image': path.name, 'sha256': sha(path), **metrics(rgb, valid),
                       **geometry(model, data, cid, cargo),
                       'qpos_sha256': hashlib.sha256(data.qpos.tobytes()).hexdigest()})
    return result


def plan():
    from harness.zone_final_pair_vision import grasp_postures
    from harness.zone_pair_highpose import HIGH, VIA_110, VIA_130
    hover, descent = grasp_postures()
    # Established v106 intermediates/times, shortened HIGH hold is explicitly a
    # diagnostic, not an accepted carry. Official lift timing is 1.5 s.
    return [('close', {**descent[-1], 1: 1500}, .5, 1.5),
            ('hover', {**hover, 1: 1500}, 1.2, 2.8),
            ('via110', {**VIA_110, 1: 1500}, 1.2, 2.8),
            ('via130', {**VIA_130, 1: 1500}, 1.2, 2.8),
            ('HIGH', {**HIGH, 1: 1500}, 1.2, 1.),
            ('official_lift', {**v2.OFFICIAL_LIFT_PWM, 1: 1500}, 1.5, 1.5)]


def run_locked(source, out):
    import mujoco
    import numpy as np
    from harness.zone_pair_highpose import HIGH
    from harness.zone_final_pair_vision import grasp_postures
    from harness.visual_arm_v3 import tool_pose
    start = time.monotonic()
    setup = json.loads((source/'eval_only/setup.json').read_text())
    cargo = next(iter(setup['objects'].values()))
    xml = v3.transform_xml((source/'scene.xml').read_text(), profile_id=v3.PROFILE_ID)
    (out/'scene.xml').write_text(xml)
    model = mujoco.MjModel.from_xml_string(xml)
    if model.neq:
        # The source may contain disabled equalities; no active weld is allowed.
        assert not np.any(model.eq_active0), 'active artificial fixation forbidden'
    data = mujoco.MjData(model)
    for rid, spawn in setup['spawns'].items():
        adr = model.jnt_qposadr[model.joint(rid+'__base_free').id]
        data.qpos[adr:adr+3] = spawn[:3]
        data.qpos[adr+3:adr+7] = [math.cos(spawn[3]/2), 0, 0, math.sin(spawn[3]/2)]
        set_pose(model, data, rid, {**HIGH, 1: 2000}, initialize=True)
    baseadr = model.jnt_qposadr[model.joint('r3__base_free').id]
    objadr = model.jnt_qposadr[model.joint(cargo['joint_name']).id]
    initial_qpos, initial_ctrl = data.qpos.copy(), data.ctrl.copy()
    option = mujoco.MjvOption(); option.geomgroup[:] = 1; option.geomgroup[4:6] = 0
    renderer = mujoco.Renderer(model, height=480, width=640)
    result, trace = [], []
    steps = 0
    try:
        # Reconstruct exactly the three earlier STATIC samples, then rotate the
        # same rigid held cargo with the official lift to isolate arm orientation.
        trajectory = rows(source/'eval_only/trajectory.jsonl')
        for t in (105., 180., 270.):
            sample = min(trajectory, key=lambda r: abs(r['t']-t))
            data.qpos[:] = initial_qpos; data.ctrl[:] = initial_ctrl
            data.qpos[baseadr:baseadr+3] = sample['robot_xyz_m']
            yaw = sample['robot_yaw_rad']
            data.qpos[baseadr+3:baseadr+7] = [math.cos(yaw/2), 0, 0, math.sin(yaw/2)]
            set_pose(model, data, 'r3', {**HIGH, 1: 1500}, initialize=True)
            data.qpos[objadr:objadr+3] = sample['cyan_xyz_m']
            mujoco.mju_mat2Quat(data.qpos[objadr+3:objadr+7], np.array(sample['cyan_rotation']))
            mujoco.mj_forward(model, data)
            body = data.body('r3__gripper')
            local = body.xmat.reshape(3, 3).T @ (data.body(cargo['body_name']).xpos-body.xpos)
            relrot = body.xmat.reshape(3, 3).T @ data.body(cargo['body_name']).xmat.reshape(3, 3)
            result += capture(model, data, renderer, option, out, f'static-{int(t)}', 'static_HIGH', cargo)
            set_pose(model, data, 'r3', {**v2.OFFICIAL_LIFT_PWM, 1: 1500}, initialize=True)
            mujoco.mj_forward(model, data)
            body = data.body('r3__gripper'); rot = body.xmat.reshape(3, 3)
            data.qpos[objadr:objadr+3] = body.xpos+rot@local
            mujoco.mju_mat2Quat(data.qpos[objadr+3:objadr+7], (rot@relrot).ravel())
            result += capture(model, data, renderer, option, out, f'static-lift-{int(t)}',
                              'static_official_lift_rigid_cargo', cargo)
        # Single open-loop contact experiment. Only SETUP uses fixture coordinates.
        mujoco.mj_resetData(model, data)
        data.qpos[:] = initial_qpos; data.ctrl[:] = initial_ctrl
        floor = {**grasp_postures()[1][-1], 1: 2000}
        set_pose(model, data, 'r3', floor, initialize=True)
        grip = tool_pose(floor)
        data.qpos[objadr:objadr+3] = [setup['spawns']['r3'][0]+grip.x_m,
                                     setup['spawns']['r3'][1], cargo['half_extents_m'][2]]
        data.qpos[objadr+3:objadr+7] = [1, 0, 0, 0]
        mujoco.mj_forward(model, data)
        write(out/'fixture.json', {'setup': setup, 'initial_qpos': data.qpos.tolist(),
            'initial_ctrl': data.ctrl.tolist(), 'initial_floor_pwm': floor, 'plan': plan(),
            'scope': 'fixed arm-only fixture, zero chassis command; not S2 or stock picking demonstration',
            'physics': 'archived standard Scene unchanged except camera visuals/mount; mj_step without production drive callbacks'})
        pose = floor
        with (out/'evaluation.jsonl').open('x') as stream:
            for phase, target, duration, hold in plan():
                begin = data.time
                count = round((duration+hold)/model.opt.timestep)
                every = round(.2/model.opt.timestep)
                for i in range(count):
                    f = min(1., (i+1)*model.opt.timestep/duration)
                    issued = {k: round(pose[k]+f*(target[k]-pose[k])) for k in target}
                    set_pose(model, data, 'r3', issued)
                    mujoco.mj_step(model, data); steps += 1
                    if i % every == 0 or i == count-1:
                        if time.monotonic()-start > 45:
                            raise TimeoutError('45 s finite diagnostic budget; no retry/tuning')
                        mujoco.mj_forward(model, data)
                        ev = {'t': float(data.time), 'phase': phase, 'issued_pwm': issued,
                              'qpos': data.qpos.tolist(), 'qvel': data.qvel.tolist(),
                              'cargo_world_m': data.body(cargo['body_name']).xpos.tolist()}
                        stream.write(json.dumps(ev)+'\n'); stream.flush()
                        trace.append(ev)
                        result += capture(model, data, renderer, option, out,
                                          f'dynamic-{len(trace):04}', phase, cargo)
                pose = target
        write(out/'summary.json', {'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'],
            cwd=ROOT, text=True).strip(), 'source_scene_sha256': sha(source/'scene.xml'),
            'profile': v3.record(), 'scope': 'diagnostic fixed commands, no S2 or physical hardware',
            'results': result, 'mj_step_calls': steps, 'sim_s': float(data.time),
            'wall_s': time.monotonic()-start, 'model_calls': 0, 'hardware_calls': 0,
            'chassis_commands': 0, 'arm_stages': len(plan()), 'weld': False,
            'mujoco': mujoco.__version__, 'loadavg': os.getloadavg(),
            'final_cargo_world_m': data.body(cargo['body_name']).xpos.tolist()})
    finally:
        renderer.close()
        if not (out/'summary.json').exists():
            write(out/'partial-results.json', {'results': result, 'mj_step_calls': steps,
                                               'sim_s': float(data.time), 'complete': False})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if not a.output.is_absolute() or not a.output.resolve().is_relative_to(PRIMARY/'outputs'):
        p.error('raw must be an absolute primary outputs path')
    # No wait, no steal, even when owner is another Codex.
    if lock_command('status') is not None:
        raise RuntimeError('shared lock occupied; no simulation attempted')
    a.output.mkdir(parents=True, exist_ok=False)
    identity = lock_command('acquire', '--owner', 'codex', '--branch', 'codex/robot-camera-review',
        '--purpose', 'camera v3 static pairs + one finite contact lift; no S2',
        '--pid', str(os.getpid()), '--expected-minutes', '1')
    write(a.output/'lock-acquire.json', identity)
    try:
        run_locked(a.source, a.output)
    except Exception as e:
        write(a.output/'error.json', {'type': type(e).__name__, 'error': str(e)})
        raise
    finally:
        held = lock_command('status')
        if held and held['pid'] == os.getpid() and held['branch'] == identity['branch']:
            write(a.output/'lock-release.json', lock_command('release', '--owner', 'codex'))
        else:
            raise RuntimeError('lock ownership changed; refusing release')


if __name__ == '__main__':
    main()
