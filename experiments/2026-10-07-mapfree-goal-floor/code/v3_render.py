"""Finite static RGB/segmentation dataset. No physics stepping or forward dynamics.

The saved scene is never edited. Only predefined base/arm setup qpos varies.
Camera calibration, geometry, materials, lighting, height and FOV stay unchanged.
All simulator truth is written under eval_only, separate from actor inputs.
"""
import argparse
import itertools
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import cv2
import numpy as np

from replay import ROOT, dump, sha
from harness.self_odom_grid import CommandOdometry, transform
from harness.visual_arm import PULSE_PER_DEGREE, SERVO_DEVIATION
from scripts import agent_lock
from sim.masterpi_camera_profile import raw_fisheye_remap


def planned_views(config, arm):
    """Known issued-command construction, also replayed by the actor separately."""
    odom = CommandOdometry()
    commands = [{'t': 0., 'kind': 'initial_servo_command', 'pulses': config['arm_poses'][arm]}]
    odom.command(commands[0])
    views = []
    for i, t in enumerate(config['view_times_s']):
        if i:
            command = {'t': config['view_times_s'][i-1], 'kind': 'mecanum', 'forward': config['translation_command']['forward'], 'left': config['translation_command']['left'],
                       'turn': config['translation_command']['turn'], 'duration_s': config['translation_command']['duration_s']}
            odom.command(command)
            commands.append(command)
        views.append({'t': t, 'own_pose': odom.advance(t)})
    return commands, views


def groups(config):
    return list(itertools.product(config['targets'], config['distances_m'], config['lateral_offsets_m'],
                                  config['arm_poses'], config['occlusion']))


def servo_targets(pose):
    p = {int(k): v for k, v in pose.items()}
    n = lambda i: p[i]-SERVO_DEVIATION.get(i, 0)
    closure = max(0., min(1., (2000-p[1])/500))*.016
    return {'arm_yaw': math.radians((p[6]-1500)/PULSE_PER_DEGREE),
            'shoulder': math.radians(90-(n(5)-1500)/PULSE_PER_DEGREE),
            'elbow': math.radians(-(n(4)-1500)/PULSE_PER_DEGREE),
            'wrist_pitch': math.radians((n(3)-1500)/PULSE_PER_DEGREE),
            'left_gripper_close': closure, 'right_gripper_close': closure}


def simulation_processes():
    """Read-only second gate; never stop another owner's process."""
    lines = subprocess.check_output(['ps', '-axo', 'pid,comm,args'], text=True).splitlines()[1:]
    markers = ('mjpython', 'mujoco_worker', 'run_zone_', 'run_s2_', 'run_solo_', 'run_cohort_',
               'launch_v117', 'launch_v121', 'sim_cli.py', 'run_simulation.py')
    return [line for line in lines if int(line.split()[0]) != os.getpid() and
            any(s in line for s in markers) and not ('ps -axo' in line or '/bin/zsh -c' in line)]


def render(config_path, output):
    config = json.loads(config_path.read_text())
    if sha(config['scene']) != config['scene_sha256']:
        raise ValueError('REGISTERED_SCENE_CHANGED')
    if agent_lock.status(agent_lock.DEFAULT_ROOT) is not None:
        raise RuntimeError('LOCK_NOT_NULL')
    active = simulation_processes()
    if active:
        raise RuntimeError('SIMULATION_ALREADY_RUNNING: '+repr(active))
    output.mkdir(parents=True, exist_ok=False)
    lock = agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner='codex', branch='claude/mapfree-goal-floor',
                             purpose='B render testset', pid=os.getpid(), expected_minutes=config['render_limit_minutes'])
    started = time.monotonic()
    receipt = {'lock': lock, 'physics_steps': 0, 'forward_dynamics_calls': 0, 'frames': 0, 'status': 'running'}
    renderer = None
    previous_signals = {}
    def interrupted(signum, frame):
        raise RuntimeError(f'RENDER_INTERRUPTED_{signum}')
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous_signals[sig] = signal.signal(sig, interrupted)
        import mujoco
        def forbidden(*args, **kwargs):
            raise AssertionError('PHYSICS_FORBIDDEN_IN_STATIC_RENDER')
        mujoco.mj_step = mujoco.mj_step1 = mujoco.mj_step2 = mujoco.mj_forward = forbidden
        model = mujoco.MjModel.from_xml_path(config['scene'])
        data = mujoco.MjData(model)
        renderer = mujoco.Renderer(model, height=480, width=640)
        option = mujoco.MjvOption()
        option.geomgroup[4:6] = 0
        camera = model.camera(config['camera']).id
        optical = np.diag([1., -1., -1.])
        remap = raw_fisheye_remap(640, 480)
        # These are derived from the scene, never substituted from actor FK.
        calibration = {'pos': model.cam_pos[camera].tolist(), 'quat': model.cam_quat[camera].tolist(),
                       'intrinsic': model.cam_intrinsic[camera].tolist(), 'resolution': model.cam_resolution[camera].tolist(),
                       'sensorsize': model.cam_sensorsize[camera].tolist()}
        dump(output/'camera_manifest.json', calibration)
        xml = ET.parse(config['scene']).getroot()
        centers = {target: np.fromstring(xml.find(f'.//geom[@name="zone_{target}"]').get('pos'), sep=' ')[:2]
                   for target in config['targets']}
        names = [model.geom(i).name for i in range(model.ngeom)]
        b_ids = [i for i, name in enumerate(names) if name == 'zone_zone_B' or name.startswith('zone_slot_B')]
        dump(output/'geometry_ids.json', names)
        actor_rows, gt_rows = [], []
        for gi, (target, distance, lateral, arm, occlusion) in enumerate(groups(config)):
            split = 'development' if lateral < 0 else 'confirmation'
            center = centers[target]
            base = center + [-distance, lateral]
            yaw = math.atan2(-lateral, distance)
            commands, views = planned_views(config, arm)
            group = f'g{gi:03d}'
            for vi, view in enumerate(views):
                if time.monotonic()-started > config['render_limit_minutes']*60:
                    raise RuntimeError('RENDER_TIME_LIMIT')
                data.qpos[:] = model.qpos0
                data.qvel[:] = 0.
                def place(robot, xy, heading):
                    address = model.jnt_qposadr[model.joint(f'{robot}__base_free').id]
                    data.qpos[address:address+7] = [*xy, .0325, math.cos(heading/2), 0., 0., math.sin(heading/2)]
                own_pose = np.array(view['own_pose'])
                xy = transform([own_pose[:2]], [*base, yaw])[0]
                place('r3', xy, yaw+own_pose[2])
                if occlusion in ('r1_in_front', 'r1_side'):
                    place('r1', center+[-.15, .30 if occlusion == 'r1_side' else 0.], math.pi)
                for robot in ('r1', 'r2', 'r3'):
                    pose = config['arm_poses'][arm if robot == 'r3' else 'search']
                    for joint, value in servo_targets(pose).items():
                        jid = model.joint(f'{robot}__{joint}').id
                        low, high = model.jnt_range[jid]
                        data.qpos[model.jnt_qposadr[jid]] = np.clip(value, low, high) if model.jnt_limited[jid] else value
                before = data.qpos.copy()
                mujoco.mj_kinematics(model, data)
                mujoco.mj_camlight(model, data)
                renderer.update_scene(data, camera=config['camera'], scene_option=option)
                rgb = renderer.render().copy()
                rgb = cv2.remap(rgb, *remap, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
                renderer.enable_segmentation_rendering()
                segmentation = renderer.render().copy()
                renderer.disable_segmentation_rendering()
                ids = cv2.remap((segmentation[..., 0]+1).astype(np.uint16), *remap, cv2.INTER_NEAREST,
                                borderMode=cv2.BORDER_CONSTANT).astype(np.int32)-1
                # ID rendering identifies the front geometric footprint of the
                # translucent paint, plus its white B slots; alpha is unchanged.
                bmask = np.isin(ids, b_ids).astype(np.uint8)*255
                sample_id = f'{group}-v{vi}'
                directory = output/split
                (directory/'rgb').mkdir(parents=True, exist_ok=True)
                (directory/'eval_only').mkdir(exist_ok=True)
                rgb_path = directory/f'rgb/{sample_id}.jpg'
                mask_path = directory/f'eval_only/{sample_id}-B.png'
                ids_path = directory/f'eval_only/{sample_id}-ids.png'
                for path, image, params in ((rgb_path, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 95]),
                                            (mask_path, bmask, []), (ids_path, (ids+1).astype(np.uint16), [])):
                    if not cv2.imwrite(str(path), image, params):
                        raise OSError('RENDER_WRITE_FAILED')
                actor_rows.append({'id': sample_id, 'group': group, 'split': split, 't': view['t'], 'robot_id': 'r3',
                                   'rgb_path': str(rgb_path.resolve()), 'rgb_sha256': sha(rgb_path),
                                   'commanded_servo': config['arm_poses'][arm], 'camera_profile': 'camera_v3',
                                   'commands': [c for c in commands if c['t'] < view['t']]})
                gt_rows.append({'id': sample_id, 'group': group, 'split': split, 'target': target, 'distance': distance,
                                'lateral': lateral, 'arm': arm, 'occlusion': occlusion,
                                'B_mask_path': str(mask_path.resolve()), 'B_sha256': sha(mask_path),
                                'ids_path': str(ids_path.resolve()), 'ids_sha256': sha(ids_path),
                                'B_pixels': int(np.count_nonzero(bmask)),
                                'camera_xyz': data.cam_xpos[camera].tolist(),
                                'camera_rotation': (data.cam_xmat[camera].reshape(3, 3)@optical).tolist(),
                                'base_pose': [*xy, yaw+own_pose[2]]})
                assert data.time == 0. and np.array_equal(before, data.qpos)
                receipt['frames'] += 1
            if gi % 8 == 7:
                print(f'static RGB frames saved: {receipt["frames"]}/{config["frames"]}', flush=True)
        for split in ('development', 'confirmation'):
            for name, values in [('inputs.jsonl', actor_rows), ('eval_only/truth.jsonl', gt_rows)]:
                (output/split/name).write_text(''.join(json.dumps(v)+'\n' for v in values if v['split'] == split))
        files = [p for p in output.rglob('*') if p.is_file()]
        if receipt['frames'] != config['frames']:
            raise ValueError('REGISTERED_FRAME_COUNT_MISMATCH')
        size = sum(p.stat().st_size for p in files)
        if size > config['data_limit_mib']*1024**2:
            raise RuntimeError('RENDER_DISK_BUDGET_EXCEEDED')
        receipt.update(status='complete', bytes=size, mujoco_version=mujoco.__version__, source_sha=subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), registration_sha256=sha(config_path),
            source_sha256=sha(Path(__file__)), data_time=0., scene_sha256=sha(config['scene']),
            artifacts={str(p.relative_to(output)): sha(p) for p in files})
    except BaseException as error:
        receipt.update(status='HOST_ERROR', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        try:
            if renderer is not None:
                renderer.close()
        finally:
            agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex')
            receipt['lock_released'] = agent_lock.status(agent_lock.DEFAULT_ROOT) is None
            dump(output/'render_receipt.json', receipt)
            for sig, handler in previous_signals.items():
                signal.signal(sig, handler)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--registration', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    render(args.registration, args.output)
