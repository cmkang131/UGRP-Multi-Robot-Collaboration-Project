"""GCP3 MJWarp own-RGB visual-search probe; default-off skill.

Controller inputs: own raw fisheye RGB, issued wheel/servo commands, and
egocentric memory.  Ground-truth pose is written only to eval-only artifacts
and to the final arrival verdict.  The scene/model builder and static labels are
setup/evaluation only.  See experiments/2026-10-17-visgoal/README.md.
"""
import argparse
from collections import deque
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
HZ = 10.
DT = 1. / HZ


def dump(p, v):
    Path(p).write_text(json.dumps(v, indent=2, allow_nan=False) + '\n')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def vendor_root():
    return ROOT / 'experiments/2026-10-17-visgoal/vendor'


def register_vendor():
    """Register byte-vendored reuse under its original module names."""
    # The vendored modules import harness/sim at load time, before the
    # renderer/legacy paths are installed by prefixed_paths.  Keep the clone
    # root importable so a plain ``python scripts/visgoal_probe.py`` works.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    v = vendor_root()
    load_module('sim.grasp_act_solo_lookback', v / 'grasp_act_solo_lookback.py')
    load_module('sim.destination_visual_acquire', v / 'destination_visual_acquire.py')
    load_module('harness.scene_colour_boundary', v / 'scene_colour_boundary.py')
    load_module('harness.rovio_feature_statistics', v / 'rovio_feature_statistics.py')
    load_module('harness.egomem_object_association', v / 'egomem_object_association.py')
    load_module('harness.egocentric_landmark_memory', v / 'egocentric_landmark_memory.py')
    load_module('harness.mapbuild_command_prior', v / 'mapbuild_command_prior.py')
    load_module('sim.solo_carry_obstacles', v / 'solo_carry_obstacles.py')


def duty(drive):
    f, l, t = drive
    desired = [f - l - t, f + l + t, f + l - t, f - l + t]
    scale = max(.35, max(map(abs, desired)))
    duration = [DT * abs(v) / scale for v in desired]
    return [0. if dd < .001 else math.copysign(.35, v) for v, dd in zip(desired, duration)], \
           [0. if dd < .001 else dd for dd in duration]


def command_delta(command):
    a, b, c, d = [w * min(dt, t) for w, dt, t in zip(command['wheels'],
                                                   command['duration_s'],
                                                   [DT] * 4)]
    gain = .0325 * 150 * 2 * math.pi / 60
    return [gain * (a + b + c + d) / 4, gain * (-a + b + c - d) / 4,
            gain * (-a + b - c + d) / (4 * .1255)]


@contextmanager
def prefixed_paths(renderer, legacy):
    sys.path[:0] = [str(ROOT), str(ROOT / 'scripts'), str(renderer),
                    str(renderer / 'scripts'), str(legacy), str(legacy / 'scripts')]
    import sim, harness, scripts
    sim.__path__[:0] = [str(renderer / 'sim'), str(legacy / 'sim')]
    harness.__path__.extend([str(legacy / 'harness'), str(renderer / 'harness')])
    scripts.__path__.append(str(renderer / 'scripts'))
    old = os.getcwd()
    os.chdir(renderer)
    try:
        yield
    finally:
        os.chdir(old)


def make_model(renderer, legacy, plan):
    with prefixed_paths(renderer, legacy):
        import mujoco
        import numpy as np
        import cv2
        from types import SimpleNamespace
        from sim.multi_masterpi_production import build_multi_robot_xml
        from sim.masterpi_dynamics_v2 import load_fitted_hardware
        from sim.masterpi_model_v3 import v3_hardware
        from sim.masterpi_drive_friction_v7 import transform_xml, DriveParameters
        from sim.masterpi_camera_profile import mujoco_pixel_intrinsic
        from sim import masterpi_camera_review_v3 as camera
        from sim.zone_cargo_contact import apply as cargo_contact
        from scripts import probe_scene_tex2 as st
        from harness.active_camera import SEARCH
        cv2.setNumThreads(1)
        vendor = vendor_root()
        scene_factory = load_module('visgoal_scene', vendor / 'warp_act_scene.py')
        native = load_module('visgoal_native', vendor / 'warp_native_contact.py')
        if sha(vendor / 'warp_native_contact.py') != \
                'a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a':
            raise ValueError('NATIVE_OWNER_BYTES_REQUIRED')
        plan = {**plan, 'scenario_id': 's1_normal_mixed_v7',
                'end_color_scene': 'grasp_act_teal_blue_v1'}
        scene = scene_factory.make_scene(plan)
        hardware, _ = load_fitted_hardware()
        xml = cargo_contact(scene.transform(build_multi_robot_xml(hardware)), 'cargo_noslip_v1')
        xml = scene.robot_transform(xml, hardware=hardware, calibrated_keys=hardware)
        xml = native.apply(transform_xml(xml, DriveParameters(), 'mesh', 'off'),
                           'warp_native_contact_v1')
        m = mujoco.MjModel.from_xml_string(xml)
        for rid in ('r1', 'r2', 'r3'):
            cid = m.camera(rid + '__robot_cam').id
            m.cam_pos[cid] = camera.POSITION_M
            m.cam_quat[cid] = camera.QUAT_WXYZ
            m.cam_resolution[cid] = (640, 480)
            m.cam_sensorsize[cid] = (640, 480)
            m.cam_intrinsic[cid] = mujoco_pixel_intrinsic(640, 480)
        hardware = v3_hardware(hardware)
        hardware.setdefault('servo6_center_pwm', 1500.)
        return m, hardware, xml, scene


def reset_episode(m, hardware, plan, st, SEARCH, mujoco):
    import numpy as np
    d = mujoco.MjData(m)
    mujoco.mj_resetData(m, d)
    for rid, spawn in plan['spawns'].items():
        st._free_pose(m, d, rid + '__robot', spawn[:3], spawn[3])
        st.set_arm(m, d, rid, SEARCH, hardware)
    mujoco.mj_forward(m, d)
    return d


def overlap_check(m, d, mujoco, check, option):
    floor = {m.geom(i).name for i in range(m.ngeom)
             if int(m.geom_type[i]) == int(mujoco.mjtGeom.mjGEOM_PLANE)
             and any(word in m.geom(i).name.lower() for word in ('floor', 'ground'))}
    cargo = {m.body(i).name for i in range(1, m.nbody)
             if int(m.body_jntnum[i])
             and int(m.jnt_type[int(m.body_jntadr[i])]) == int(mujoco.mjtJoint.mjJNT_FREE)
             and not m.body(i).name.startswith(('r1__', 'r2__', 'r3__'))}
    wall = {m.geom(i).name for i in range(m.ngeom) if 'wall' in m.geom(i).name.lower()}
    return check(m, d, floor_geoms=floor, cargo_bodies=cargo, wall_geoms=wall,
                 option=option)


def json_safe(obj):
    import numpy as np
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()
                if k not in ('labels', 'mask')}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    return obj


def run(a):
    if not a.enabled:
        raise ValueError('EXPLICIT_ENABLED_REQUIRED')
    if not platform.node().startswith('ugrp-act-l4-gcp3'):
        raise ValueError('EXPLICIT_GCP3_ONLY')
    lease = Path('/home/ugrp/ugrp-sim/leases') / (a.lease_name + '.json')
    if not lease.is_file():
        raise ValueError('OWN_LEASE_REQUIRED')
    q = json.loads(a.queue.read_text())
    import subprocess
    if subprocess.call(['git', '-C', str(ROOT), 'cat-file', '-e',
                         q['source_sha'] + '^{commit}'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
        raise ValueError('PINNED_SOURCE_REQUIRED')
    if not a.preflight and not Path(q['rejection_table']).is_file():
        raise ValueError('PRIOR_FUNNEL_REQUIRED')
    for name, expected in q.get('input_sha256', {}).items():
        if sha(ROOT / name) != expected:
            raise ValueError('PINNED_INPUT_CHANGED:' + name)
    if a.output.exists():
        raise ValueError('OUTPUT_MUST_NOT_EXIST')
    a.output.mkdir(parents=True)
    (a.output / 'own-rgb').mkdir()
    dump(a.output / 'queue.json', q)
    register_vendor()
    setups = json.loads(a.setups.read_text())['episodes']
    if a.episodes:
        keep = {int(x) for x in a.episodes.split(',')}
        setups = [e for i, e in enumerate(setups) if i in keep]
    if a.preflight:
        # A preflight must cover both sides of the perception decision: one
        # west start (no destination colour) and one east start where the zone
        # is inside the initial FOV.  Filter by --episodes first; truncating
        # before the filter previously tested two west starts only.
        a.sim_cap = min(a.sim_cap, 60.)
        if not a.episodes:
            east = [e for e in setups
                    if e.get('split') == 'east_zone_possible_visibility']
            setups = [setups[0]] + ([east[5]] if len(east) > 5 else east[:1])
    with prefixed_paths(a.renderer, a.legacy):
        import numpy as np
        import cv2
        import mujoco
        import mujoco_warp as mjw
        import warp as wp
        from types import SimpleNamespace
        from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2
        from sim.masterpi_camera_profile import raw_fisheye_remap
        from scripts.warp5_render import Renderer
        from scripts.simalt_physics_compare import unused_efm
        from scripts import probe_scene_tex2 as st
        core = load_module('visgoal_warp_act_core', vendor_root() / 'warp_act_core.py')
        control_tape, runtime_sleep_policy = core.control_tape, core.runtime_sleep_policy
        from harness.active_camera import SEARCH
        from harness.rbpf_rejection import motion_variance
        from harness.mapbuild_command_prior import CommandPrior, OPTION as PRIOR
        from harness.egocentric_landmark_memory import LandmarkMemory, MemoryOptions, OPTION as MEMORY
        from sim.visual_goal_search import (VisualGoalSearch, OPTION as SKILL,
                                            detect_paint, wall_points, component_clear,
                                            signed_turn_wheels)
        from sim.destination_visual_acquire import floor_patch
        from sim.solo_carry_obstacles import detections as obstacle_detections
        from harness.scene_colour_boundary import surface_masks
        cv2.setNumThreads(1)
        if a.implementation != 'legacy_v1':
            raise ValueError('VISGOAL_LEGACY_MEMORY_ONLY')
        plan0 = {**setups[0], 'scenario_id': 's1_normal_mixed_v7',
                 'end_color_scene': 'grasp_act_teal_blue_v1'}
        m, hardware, xml, scene = make_model(a.renderer, a.legacy, plan0)
        if int(m.opt.noslip_iterations) != 0:
            raise ValueError('NOSLIP0_REQUIRED')
        en = mujoco.mjtSleepPolicy
        m.tree_sleep_policy[:] = runtime_sleep_policy(
            m.tree_sleep_policy.copy(), auto=int(en.mjSLEEP_AUTO),
            auto_never=int(en.mjSLEEP_AUTO_NEVER), auto_allowed=int(en.mjSLEEP_AUTO_ALLOWED),
            never=int(en.mjSLEEP_NEVER), allowed=int(en.mjSLEEP_ALLOWED))
        dump(a.output / 'scene.json', scene.manifest)
        dump(a.output / 'stack.json', {'stack_values': q['stack_values'], 'flow': q['flow'],
                                       'source_sha': q['source_sha']})
        (a.output / 'scene.xml').write_text(xml)
        calibration = json.loads((vendor_root() / 'walls_floor_contrast_v5_indigo110_s80-calibration.json').read_text())
        command_calibration = json.loads((vendor_root() / 'own-command-calibration-r2.json').read_text())
        own_prior = CommandPrior(command_calibration, option=PRIOR)
        from sim.spawn_overlap_check import check, OPTION as OVERLAP
        hue_band = (104, 120)  # PAINT_HUE['B']: appearance only, no zone position.
        summaries = []
        for episode_index, plan in enumerate(setups):
            plan = {**plan, 'scenario_id': 's1_normal_mixed_v7',
                    'end_color_scene': 'grasp_act_teal_blue_v1'}
            out = a.output / 'episodes' / f'e{episode_index:02d}'
            out.mkdir(parents=True)
            (out / 'frames').mkdir()
            d = reset_episode(m, hardware, plan, st, SEARCH, mujoco)
            admission = overlap_check(m, d, mujoco, check, OVERLAP)
            dump(out / 'admission.json', admission)
            if not admission['accepted']:
                summaries.append(dict(episode=episode_index, status='START_REJECTED',
                                      admission=admission))
                dump(out / 'episode.json', summaries[-1])
                continue
            for rid, spawn in plan['spawns'].items():
                pass
            # Setup-only initial state; no pose ever enters the skill.
            dump(out / 'setup-eval-only.json', dict(evaluation_only=True, spawns=plan['spawns']))
            ctrl = np.zeros((1, m.nu))
            for i in range(m.nu):
                if '__servo_' in m.actuator(i).name:
                    ctrl[0, i] = d.qpos[int(m.jnt_qposadr[int(m.actuator_trnid[i, 0])])]
            d.ctrl[:] = ctrl[0]
            wp.init()
            wm = mjw.put_model(m)
            with unused_efm(m, d):
                wd = mjw.put_data(m, d, nworld=1, nconmax=512, njmax=2048)
            mjw.step(wm, wd)
            wp.synchronize()
            with unused_efm(m, d):
                wd = mjw.put_data(m, d, nworld=1, nconmax=512, njmax=2048)
            if int(wm.opt.noslip_iterations) != 0:
                raise ValueError('NOSLIP0_REQUIRED')
            tape = wp.zeros((round(DT / m.opt.timestep), 1, m.nu), dtype=float)
            step_index = wp.zeros(1, dtype=int)

            @wp.kernel
            def issue(tape: wp.array3d(dtype=float), index: wp.array(dtype=int),
                      out: wp.array2d(dtype=float)):
                i, j = wp.tid()
                out[i, j] = tape[index[0], i, j]

            @wp.kernel
            def advance(index: wp.array(dtype=int)):
                index[0] = index[0] + 1

            with wp.ScopedCapture() as cap:
                for _ in range(round(DT / m.opt.timestep)):
                    wp.launch(issue, dim=(1, m.nu), inputs=[tape, step_index, wd.ctrl])
                    mjw.step(wm, wd)
                    wp.launch(advance, dim=1, inputs=[step_index])
            rc = Renderer(m, wm, wd, [('r1', 'r1__robot_cam', (640, 480))],
                          enabled=True, texture_after_lighting=True)
            mx, my = raw_fisheye_remap(640, 480)
            servos = (1, 3, 4, 5, 6)
            jointnames = {1: ('left_gripper_close', 'right_gripper_close'),
                          3: ('wrist_pitch',), 4: ('elbow',), 5: ('shoulder',), 6: ('arm_yaw',)}
            sidnames = {1: 'gripper', 3: 'wrist', 4: 'elbow', 5: 'shoulder', 6: 'yaw'}
            lookup = np.empty((5, 2001))
            servo_ids = []
            for k, sid in enumerate(servos):
                joints = [m.joint('r1__' + j).id for j in jointnames[sid]]
                ids = [i for i in range(m.nu) if int(m.actuator_trnid[i, 0]) in joints]
                servo_ids.append(ids)
                for pwm in range(500, 2501):
                    targets = MasterPiDynamicsV2.pulse_to_joint_targets(
                        SimpleNamespace(physical_params=hardware), {sid: pwm})
                    jid = joints[0]
                    v = targets[sidnames[sid]]
                    lookup[k, pwm - 500] = float(np.clip(v, *m.jnt_range[jid])) \
                        if m.jnt_limited[jid] else v
            wheel_ids = [m.actuator('r1__wheel_' + n + '_drive').id
                         for n in ('fl', 'fr', 'rl', 'rr')]
            applied = np.array([[SEARCH[s] for s in servos]], float)
            relay = np.zeros((1, 4), int)
            drive = __import__('sim.masterpi_drive_friction_v7', fromlist=['DriveParameters']).DriveParameters()
            memory = LandmarkMemory(option=MEMORY, options=MemoryOptions(implementation=a.implementation))
            skill = VisualGoalSearch(option=SKILL if a.enabled else 'off')
            body = m.body('r1__robot').id
            adr = int(m.jnt_qposadr[int(m.body_jntadr[body])])
            frames = []
            trace = []
            commands = []
            labels = []
            ring = deque(maxlen=101)
            previous = None
            last_servo = None
            status = 'cap_end'
            error = None
            found = False
            declared = False
            declared_t = None
            arrived_gt = False
            arrive_pose = None
            inside_at_declared = None
            colour_seen = False
            start_visibility = None
            start_paint_reason = None
            rotation_cmd = 0.
            rotation_gt = 0.
            last_yaw = None
            start = time.monotonic()
            obstacle_cache = []
            tick = 0
            try:
                for tick in range(int(round(a.sim_cap * HZ)) + 1):
                    t = tick / HZ
                    if (out / 'SUPERVISOR_STOP.json').exists():
                        status = 'SUPERVISOR_STOP'
                        break
                    qp = wd.qpos.numpy()[0].copy()
                    if not np.isfinite(qp).all() or np.any(wd.overflow.numpy()):
                        raise RuntimeError('NONFINITE_OR_CAPACITY')
                    images = rc.render()
                    raw = np.clip(images['r1'][0][0], 0, 255).astype(np.uint8)
                    im = cv2.remap(raw, mx, my, cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_CONSTANT)
                    file = out / 'frames' / f'{tick:05d}.jpg'
                    cv2.imwrite(str(file), cv2.cvtColor(im, cv2.COLOR_RGB2BGR),
                                [cv2.IMWRITE_JPEG_QUALITY, 90])
                    bgr = cv2.imread(str(file))
                    servo = {s: int(v) for s, v in zip(servos, np.rint(applied[0]))}
                    delta_nom = np.asarray(command_delta(previous)) if previous else np.zeros(3)
                    cov_nom = np.diag(motion_variance(delta_nom))
                    prior = own_prior.predict(delta_nom, cov_nom, previous, servo, last_servo, DT)
                    delta = np.asarray(prior['delta'])
                    cov = np.asarray(prior['covariance'])
                    if tick % 3 == 0:
                        obstacle_cache, _ = obstacle_detections(bgr, servo)
                    paint = detect_paint(bgr, servo, hue_band,
                                         saturation_min=skill.options.paint_saturation_min)
                    walls = wall_points(bgr, servo, calibration)
                    if tick == 0:
                        pm = (paint.get('mask') if paint.get('mask') is not None
                              else np.zeros(bgr.shape[:2], np.uint8))
                        cv2.imwrite(str(out / 'paint-mask.png'),
                                    (pm * 255).astype(np.uint8))
                        wm_tmp, _ = surface_masks(bgr, calibration)
                        cv2.imwrite(str(out / 'wall-mask.png'),
                                    (wm_tmp['wall'] * 255).astype(np.uint8))
                        dump(out / 'tick0-perception.json',
                             {k: v for k, v in paint.items()
                              if k not in ('labels', 'mask') and not isinstance(v, np.ndarray)})
                    patch = None
                    patch_rec = None
                    # The vendored floor_patch uses S>=30, which also matches
                    # the v5 blue floor.  Restrict its fitted segment to the
                    # calibrated high-saturation component; never fit without
                    # a visible destination-colour component.
                    paint_clear = component_clear(paint)
                    need_patch = (paint_clear is not None and
                                  (paint.get('nearest_range_m', 99.) <= 1.8
                                   or skill.stage in ('target', 'approach')))
                    if need_patch:
                        patch, patch_rec = floor_patch(
                            bgr, servo, 'B', (1.5, 1.5),
                            clear=paint_clear, excluded=None)
                    obs = skill.memory_observation(t, patch, patch_rec or {})
                    mem = memory.step(t, delta, cov, [obs] if obs else [])
                    action = skill.control(t, paint=paint, walls=walls,
                                           obstacles=obstacle_cache,
                                           memories=mem['memories'],
                                           patch_ok=patch is not None,
                                           patch_xy=patch)
                    if action['found']:
                        found = True
                    just_declared = bool(action['arrived'] and not declared)
                    if just_declared:
                        declared = True
                        declared_t = t
                        status = 'ARRIVED_DECLARED'
                    if action['stop'] and not declared:
                        status = 'STOPPED_NO_ARRIVAL'
                    # EVALUATION ONLY: pose/yaw/visibility never enter control.
                    w, x, y, z = qp[adr + 3:adr + 7]
                    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
                    if last_yaw is not None:
                        rotation_gt += abs(math.atan2(math.sin(yaw - last_yaw),
                                                      math.cos(yaw - last_yaw)))
                    last_yaw = yaw
                    rotation_cmd += abs(float(delta[2]))
                    inside = bool(4.3 <= qp[adr] <= 4.9 and -2.8 <= qp[adr + 1] <= -1.4)
                    if inside:
                        arrived_gt = True
                        arrive_pose = [float(qp[adr]), float(qp[adr + 1]), float(yaw)]
                    if just_declared:
                        inside_at_declared = bool(inside)
                    colour_seen = skill.colour_seen
                    if tick == 0:
                        start_paint_reason = paint.get('reason')
                        start_visibility = (int(paint.get('pixels', 0))
                                            if paint.get('reason') ==
                                            'destination_colour_observed' else 0)
                    labels.append(dict(t=t, frame_id=tick,
                                       pose=[float(qp[adr]), float(qp[adr + 1]), float(yaw)],
                                       inside_zone_B=inside,
                                       start_paint_pixels=start_visibility))
                    ring.append(tick)
                    paint_log = {k: v for k, v in paint.items()
                                 if k not in ('labels', 'mask') and not isinstance(v, np.ndarray)}
                    trace.append(dict(t=t, frame_id=tick, stage=action['stage'],
                                      paint=paint_log, walls=len(walls),
                                      obstacles=obstacle_cache,
                                      patch=None if patch is None else np.asarray(patch).tolist(),
                                      patch_record=patch_rec,
                                      memory=mem['memories'], memory_events=mem['events'],
                                      action=action, command_motion_source=prior['source'],
                                      command_delta=delta.tolist(),
                                      command_covariance=cov.tolist(),
                                      servo=servo, rgb=str(file.relative_to(out)),
                                      frame_sha256=sha(file)))
                    if tick == 0 and start_visibility is None:
                        start_visibility = 0
                    last_servo = servo
                    if declared_t is not None and t - declared_t >= 1.0:
                        break
                    if action['exact_turn']:
                        # The r2 calibration stores the positive-yaw pulse.
                        # Negating the wheel PWM signs gives the right turn;
                        # using the same signs for both made the bearing loop
                        # diverge (e13 preflight r2 stayed in approach).
                        wheels = signed_turn_wheels(
                            action['exact_turn'], command_calibration['wheels'])
                        duration = list(command_calibration['duration_s'])
                    else:
                        wheels, duration = duty([action['forward'], action['left'],
                                                 action['turn']])
                        if action['stop']:
                            wheels, duration = [0., 0., 0., 0.], [0., 0., 0., 0.]
                    cmd = dict(t=t, wheels=wheels, duration_s=duration,
                               pwm={s: SEARCH[s] for s in servos})
                    commands.append(cmd)
                    previous = cmd
                    values, cmd_state = control_tape(
                        [dict(ctrl=ctrl[0], wheels=wheels,
                              deadlines=[t + v if v else -1 for v in duration],
                              applied=applied[0], target=[SEARCH[s] for s in servos],
                              servo_active=[False] * 5, now=t, servo_time=t)],
                        relay, dt=float(m.opt.timestep),
                        steps=round(DT / m.opt.timestep), lookup=lookup,
                        wheel_ids=wheel_ids, servo_ids=servo_ids,
                        start_fraction=drive.start_fraction,
                        kinetic_fraction=drive.kinetic_fraction,
                        torque_cap_nm=drive.torque_cap_nm)
                    applied = cmd_state['applied']
                    relay = cmd_state['relay']
                    wp.copy(tape, wp.array(values, dtype=float))
                    step_index.zero_()
                    wp.capture_launch(cap.graph)
                    if tick % 100 == 0:
                        dump(out / 'progress.json',
                             dict(t=t, stage=action['stage'], found=found,
                                  declared=declared, source_sha=q['source_sha'],
                                  wall_s=time.monotonic() - start))
            except BaseException as exc:
                error = repr(exc)
                status = 'HOST_ERROR'
                raise
            finally:
                ep = dict(episode=episode_index, status=status, error=error,
                          frames=len(commands), sim_s=(len(commands) - 1) / HZ if commands else 0.,
                          wall_s=time.monotonic() - start,
                          source_sha=q['source_sha'], skill=SKILL,
                          found=found, colour_seen=colour_seen,
                          arrived_declared=declared,
                          arrival_verdict_gt_inside_zone_B=inside_at_declared,
                          entered_zone_gt_any=arrived_gt,
                          arrive_pose_eval_only=arrive_pose,
                          rotation_cmd_rad=rotation_cmd, rotation_gt_rad_eval_only=rotation_gt,
                          start_visibility_pixels=start_visibility,
                          start_paint_reason=start_paint_reason,
                          final_pose_eval_only=[float(locals()['qp'][adr]),
                                                float(locals()['qp'][adr + 1])]
                          if 'qp' in locals() else None,
                          spawn_eval_only=plan['spawns']['r1'],
                          camera_frames=len(labels),
                          memory_landmarks=len(mem['memories']) if 'mem' in dir() else 0,
                          terminal_ring=dict(hz=10, indices=list(ring),
                                             bytes=sum((out / 'frames' / f'{i:05d}.jpg').stat().st_size
                                                       for i in ring)),
                          static_map_control=0, spawn_control=0, truth_control=0,
                          top_camera_frames=0, held_world_reads=0, initial_prior='none',
                          noslip_iterations=int(m.opt.noslip_iterations),
                          rejection_table=str(a.output / 'rejection_table.json'))
                dump(out / 'episode.json', ep)
                with (out / 'trace.jsonl').open('w') as fh:
                    for row in trace:
                        fh.write(json.dumps(json_safe(row), allow_nan=False) + '\n')
                dump(out / 'commands.json', commands)
                dump(out / 'eval-only.json', dict(evaluation_only=True, frames=labels))
                dump(out / 'events.json', skill.events)
                dump(out / 'SHA256SUMS.json',
                     {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()})
                summaries.append(ep)
                dump(a.output / 'summary.json',
                     dict(status='running', episodes=summaries, n=len(summaries),
                          source_sha=q['source_sha'], raw=str(a.output)))
                # Free per-episode GPU objects before the next start.
                del rc, wd
                try:
                    import gc
                    gc.collect()
                except Exception:
                    pass
        # Aggregate summary and a prior-funnel shaped table for the next run.
        ok_found = sum(1 for e in summaries if e.get('found'))
        ok_colour = sum(1 for e in summaries if e.get('colour_seen'))
        ok_decl = sum(1 for e in summaries if e.get('arrived_declared'))
        ok_gt = sum(1 for e in summaries
                    if e.get('arrival_verdict_gt_inside_zone_B'))
        invisible = sum(1 for e in summaries
                        if (e.get('start_visibility_pixels') or 0) < 120)
        reasons = {}
        for e in summaries:
            if e.get('status') not in ('ARRIVED_DECLARED',):
                reasons[e.get('status', 'UNKNOWN')] = reasons.get(e.get('status', 'UNKNOWN'), 0) + 1
        gates = []
        left = len(summaries)
        for gate, passed in [('starts', left), ('found_metric_or_arrived', ok_found),
                             ('colour_seen', ok_colour),
                             ('arrived_declared', ok_decl), ('arrived_gt', ok_gt)]:
            passed = bool(left and passed)
            gates.append(dict(stage=gate, input_n=left, cumulative_pass_n=passed,
                              rejected_n=int(left) - int(passed)))
            left = int(passed)
        summary = dict(status='DONE', n=len(summaries), source_sha=q['source_sha'],
                       found_n=ok_found, colour_seen_n=ok_colour,
                       arrived_declared_n=ok_decl, arrived_gt_n=ok_gt,
                       initially_invisible_n=invisible,
                       episodes=summaries, raw=str(a.output),
                       rejection_table=str(a.output / 'rejection_table.json'),
                       stack_values=q['stack_values'], flow=q['flow'],
                       sim_s_total=sum(e.get('sim_s', 0.) for e in summaries),
                       static_map_control=0, truth_control=0, top_camera_frames=0)
        dump(a.output / 'summary.json', summary)
        dump(a.output / 'rejection_table.json',
             dict(unit='episode', funnel=gates, reasons=reasons,
                  invisible_starts=invisible, raw=str(a.output),
                  reproduction=sys.argv, blocked_object='not_observed',
                  minimum_gap_m=None, gap_status='not_measured'))
        dump(a.output / 'SHA256SUMS.json',
             {str(p.relative_to(a.output)): sha(p) for p in a.output.rglob('*') if p.is_file()})
        dump(a.output / 'EXIT', dict(status='PREFLIGHT_DONE' if a.preflight else 'DONE',
                                     error=None))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--preflight', action='store_true')
    p.add_argument('--implementation', default='legacy_v1')
    p.add_argument('--lease-name', default='visgoal')
    p.add_argument('--sim-cap', type=float, default=120.)
    p.add_argument('--episodes', default='')
    for key in ('queue', 'renderer', 'legacy', 'setups', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    run(p.parse_args())
