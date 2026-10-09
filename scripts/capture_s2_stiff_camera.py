"""Finite free-chassis stationary RGB calibration; dry plan by default."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from harness import s2_extrinsic_targets as target
from harness.s2_stiff_camera_calibration import OPTION, fit


def poses():
    rows = [p for state, p in target.poses() if state == 'unloaded']
    rows += [p for _, p in target.capture_poses('real_carry_v1')]
    return list({target.key(p): p for p in rows}.values())


def capture(out, sha, servo_stiffness):
    import mujoco
    from PIL import Image
    from sim.s2_realism import make_scene
    from sim.s2_realism_camera_binding import bound_world
    from sim.s2_extrinsic_capture import board_xml
    from sim.s2_servo_stiffness import transform_xml, parameters
    from sim.s2_eval_camera_trace import camera_row
    from sim.camera_robot_port import CameraRobotPort
    from sim.masterpi_drive_friction_v7 import PROFILE
    from scripts.run_final_environment_checks import write
    out.mkdir(parents=True, exist_ok=False)
    c = target.contract
    setup_bundle = c.bundle(sha, seed=1047, **c.NEW_OPTIONS)
    scene = make_scene(setup_bundle, 0)
    original = scene.transform
    scene.transform = lambda xml: board_xml(original(xml))
    robot_transform = scene.robot_transform
    scene.robot_transform = lambda xml, **kw: transform_xml(robot_transform(xml, **kw), servo_stiffness=servo_stiffness)
    scene.config['setup_only']['spawns']['r3'] = [*target.FIXTURE, 0.]
    world = None; rows = []; audits = []; errors = []; fitted = {}; start = time.monotonic()
    try:
        world = bound_world(scene, drive_profile=PROFILE, idle_robot_contacts='freeze_v1',
                            seed=0, width=640, height=480, render=True,
                            warehouse_layout=scene.engine_layout, warehouse_cargo_ids=None)
        scene.setup(world)
        robot = world.robot('r3')
        port = CameraRobotPort(world, 'r3', allow_reverse=True, allow_mecanum=True)
        dt = world.model.opt.timestep
        write(out/'setup-design.json', dict(source_sha=sha, task_run=False,
              servo_stiffness=servo_stiffness, idle_robot_contacts='freeze_v1',
              stiffness_parameters=parameters(), poses=poses(), chassis_clamp=False,
              load='empty; no repeated loaded jig', known_target_geometry=True,
              fit_inputs='RGB corners and surveyed board geometry only'))
        (out/'scene.xml').write_text(world.scene_xml)
        for pose in poses():
            now = float(world.data.time)
            for sid, pulse in {1:2000, **pose}.items():
                cmd = dict(kind='look', pan_pulse=pulse) if sid == 6 else dict(kind='arm', servo_id=sid, pulse=pulse)
                port.apply(cmd, now)
            # Match S2's public port interpolation; no direct qpos or base clamp.
            for _ in range(round(6./dt)):
                if world.data.time > 180.: raise RuntimeError('CALIBRATION_SIM_CAP')
                port.tick(float(world.data.time)); world._physics_step_for(robot)
            per_pose = []
            for board in target.boards(pose):
                axes = np.asarray(board['rotation'])
                mid = int(world.model.body('cal_board').mocapid[0])
                world.data.mocap_pos[mid] = np.asarray(board['origin_m']) + np.r_[target.FIXTURE[:2], 0.]
                quat = np.zeros(4); mujoco.mju_mat2Quat(quat, axes.ravel())
                world.data.mocap_quat[mid] = quat
                s = board['square_m']
                world.model.geom('cal_border').size[:2] = [5.5*s, 4*s]
                for y in range(6):
                    for x in range(9):
                        g = world.model.geom(f'cal_{x}_{y}')
                        g.pos[:2] = [(x-4)*s, (y-2.5)*s]; g.size[:2] = s/2
                mujoco.mj_forward(world.model, world.data)
                rgb = world.render_rgb(robot_id='r3', camera='robot_cam')
                name = target.key(pose)+'-'+str(board['index'])+'.png'
                Image.fromarray(rgb).save(out/name)
                row = dict(**board, pose_key=target.key(pose), servo=pose, path=name,
                           sha256=hashlib.sha256((out/name).read_bytes()).hexdigest(),
                           sim_time=float(world.data.time))
                try: row.update(corners_px=target.detect(rgb).tolist(), status='detected')
                except ValueError as exc: row['status'] = str(exc)
                rows.append(row); per_pose.append(row)
                # Write-only evaluation sidecar, never passed to fit().
                audits.append(dict(pose_key=target.key(pose), path=name,
                                   camera=camera_row(world,'r3',float(world.data.time))))
                write(out/'observations.json', rows); write(out/'eval_only.json', audits)
            try:
                if any(r['status'] != 'detected' for r in per_pose):
                    raise ValueError('TARGET_MISSING')
                fitted[target.key(pose)] = fit(per_pose)
            except ValueError as exc:
                errors.append(dict(pose_key=target.key(pose), error=str(exc)))
            print(target.key(pose), 'fit' if target.key(pose) in fitted else errors[-1]['error'], flush=True)
        table = dict(schema='ugrp.s2.stiff_target.v1', option=OPTION, source_sha=sha,
                     servo_stiffness=servo_stiffness, complete=not errors,
                     fit_uses_gt=False, poses=fitted, errors=errors, loaded_measured=False,
                     camera_mount_fov_changed=False, method='fixed K/D surveyed planar targets solvePnP+LM',
                     source_sha256=hashlib.sha256((out/'observations.json').read_bytes()).hexdigest())
        write(out/'calibration.json', table)
        write(out/'result.json', dict(status='PASS' if not errors else 'FAIL', errors=errors,
              calibrated=len(fitted), required=len(poses()), source_sha=sha,
              sim_s=float(world.data.time), wall_s=time.monotonic()-start, model_calls=0,
              options=dict(servo_stiffness=servo_stiffness, idle_robot_contacts='freeze_v1'),
              scope='stationary calibration, not task transport'))
    finally:
        if world is not None: world.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--expected-source-sha', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--servo-stiffness', choices=('off','real_v1'), default='off')
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(dict(execution_started=False, poses=len(poses()),
                              servo_stiffness=args.servo_stiffness, sim_cap_s=180)))
        return
    from scripts.run_final_environment_checks import check_source
    from scripts.agent_lock import status, DEFAULT_ROOT
    check_source(args.expected_source_sha)
    lock = status(DEFAULT_ROOT)
    if not lock or not lock['pid_alive'] or lock['owner']!='codex' or lock['branch']!='codex/s2-realism':
        raise ValueError('owned calibration lock required')
    if args.output is None or not args.output.is_absolute(): raise ValueError('absolute new output required')
    capture(args.output, args.expected_source_sha, args.servo_stiffness)


if __name__ == '__main__': main()
