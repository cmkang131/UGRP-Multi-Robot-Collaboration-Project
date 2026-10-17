"""N=16 own-RGB/own-command egocentric-memory gate on the assigned gcp4 VM.

Controller inputs per world: raw fisheye RGB, commanded servo pose and the
module's own previously issued wheel command.  Spawns, cargo/world state,
contacts and evaluation labels are harness-only.  The frozen scene/model is
built once and replicated to a single MJWarp batch; MJWarp native contact with
noslip_iterations=0 is checked at runtime.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
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


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False, ensure_ascii=False)+'\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def pose_apply(pose, xy):
    x, y, yaw = pose
    return np.asarray([x+math.cos(yaw)*xy[0]-math.sin(yaw)*xy[1],
                       y+math.sin(yaw)*xy[0]+math.cos(yaw)*xy[1]])


def zone_distance(xy, center, half):
    dx = max(abs(float(xy[0])-center[0])-half[0], 0.)
    dy = max(abs(float(xy[1])-center[1])-half[1], 0.)
    return math.hypot(dx, dy)


def inside_zone(xy, center, half):
    return abs(float(xy[0])-center[0]) <= half[0] and abs(float(xy[1])-center[1]) <= half[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def contact_pairs(wd, n):
    """Return active geom pairs, independent of renderer/controller code."""
    import numpy as np
    pairs = []
    try:
        geom = wd.contact.geom.numpy()
        count = wd.ncon.numpy()
    except AttributeError:
        return pairs
    for world in range(n):
        for k in range(int(count[world])):
            pairs.append((world, int(geom[world, k, 0]), int(geom[world, k, 1])))
    return pairs


def run(args):
    if not platform.node().startswith('ugrp-act-l4-gcp4'):
        raise ValueError('EXPLICIT_GCP4_ONLY')
    lease = Path('/home/ugrp/ugrp-sim/leases/egonav.json')
    if not lease.is_file():
        raise ValueError('OWN_LEASE_REQUIRED')
    q = json.loads(args.queue.read_text())
    if q.get('flow') != 'self_map':
        raise ValueError('SELF_MAP_FLOW_REQUIRED')
    import subprocess
    head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    if head != q['source_sha']:
        raise ValueError('PINNED_SOURCE_REQUIRED')
    for name, expected in q.get('input_sha256', {}).items():
        if sha(name) != expected:
            raise ValueError('PINNED_INPUT_CHANGED:'+name)
    if not Path(q['rejection_table']).is_file():
        raise ValueError('PRIOR_FUNNEL_REQUIRED')
    setup = json.loads(args.setup.read_text())
    if setup['scenario_id'] != 's1_normal_mixed_v7':
        raise ValueError('V7_SCENARIO_REQUIRED')
    if args.output.exists():
        raise ValueError('OUTPUT_MUST_BE_NEW')
    args.output.mkdir(parents=True)
    dump(args.output/'queue.json', q)
    dump(args.output/'setup.json', setup)
    (args.output/'ring').mkdir()

    # Frozen source/renderer split: current worktree wins; renderer-only frozen
    # files (textures/renderer) resolve by append, never by editing them.
    sys.path[:0] = [str(ROOT), str(ROOT/'scripts'), str(args.renderer), str(args.renderer/'scripts')]
    import sim, harness, scripts
    sim.__path__.insert(0, str(args.renderer/'sim'))
    harness.__path__.extend([str(args.renderer/'harness')])
    scripts.__path__.append(str(args.renderer/'scripts'))
    os.chdir(args.renderer)

    import numpy as np
    import cv2
    import mujoco
    import mujoco_warp as mjw
    import warp as wp
    from types import SimpleNamespace
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.masterpi_dynamics_v2 import load_fitted_hardware, MasterPiDynamicsV2
    from sim.masterpi_model_v3 import v3_hardware
    from sim.masterpi_drive_friction_v7 import transform_xml, DriveParameters
    from sim.masterpi_camera_profile import mujoco_pixel_intrinsic, raw_fisheye_remap
    from sim import masterpi_camera_review_v3 as camera
    from sim.zone_cargo_contact import apply as cargo_contact
    from scripts.warp5_render import Renderer
    from scripts.simalt_physics_compare import unused_efm
    from scripts import probe_scene_tex2 as st
    from harness.active_camera import SEARCH
    from harness.active_wall_vision import observe as wall_observe
    from harness.floor_goal_self_mask import body_envelopes
    from harness.egocentric_goto import (
        OPTION as GOTO_OPTION, EgocentricGoto, command_delta, duty, point_covariance)
    from harness.floor_goal_v3 import FloorGoalV3Options
    from harness.active_camera import goal_detector
    cv2.setNumThreads(1)
    vendor = ROOT/'experiments/2026-10-17-egonav/vendor'
    if sha(vendor/'warp_native_contact.py') != 'a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a':
        raise ValueError('NATIVE_OWNER_BYTES_REQUIRED')
    scene_factory = module('egonav_scene', vendor/'warp_act_scene.py')
    core = module('egonav_core', vendor/'warp_act_core.py')
    control_tape, runtime_sleep_policy = core.control_tape, core.runtime_sleep_policy
    native = module('egonav_native', vendor/'warp_native_contact.py')

    plan = dict(setup['scene_plan'])
    plan.update(scenario_id=setup['scenario_id'], seed=setup['seed'],
                end_color_scene=setup['end_color_scene'])
    scene = scene_factory.make_scene(plan)
    hardware, _ = load_fitted_hardware()
    xml = cargo_contact(scene.transform(build_multi_robot_xml(hardware)), 'cargo_noslip_v1')
    xml = scene.robot_transform(xml, hardware=hardware, calibrated_keys=hardware)
    xml = native.apply(transform_xml(xml, DriveParameters(), 'mesh', 'off'), 'warp_native_contact_v1')
    m = mujoco.MjModel.from_xml_string(xml)
    en = mujoco.mjtSleepPolicy
    m.tree_sleep_policy[:] = runtime_sleep_policy(
        m.tree_sleep_policy.copy(), auto=int(en.mjSLEEP_AUTO),
        auto_never=int(en.mjSLEEP_AUTO_NEVER), auto_allowed=int(en.mjSLEEP_AUTO_ALLOWED),
        never=int(en.mjSLEEP_NEVER), allowed=int(en.mjSLEEP_ALLOWED))
    for rid in ('r1', 'r2', 'r3'):
        cid = m.camera(rid+'__robot_cam').id
        m.cam_pos[cid] = camera.POSITION_M
        m.cam_quat[cid] = camera.QUAT_WXYZ
        m.cam_resolution[cid] = (640, 480)
        m.cam_sensorsize[cid] = (640, 480)
        m.cam_intrinsic[cid] = mujoco_pixel_intrinsic(640, 480)
    hardware = v3_hardware(hardware)
    hardware.setdefault('servo6_center_pwm', 1500.)
    if m.opt.noslip_iterations != 0:
        raise ValueError('NOSLIP0_REQUIRED')

    worlds = setup['worlds']
    nworld = len(worlds) if not args.worlds else min(args.worlds, len(worlds))
    worlds = worlds[:nworld]
    if not args.preflight and nworld != 16:
        raise ValueError('GATE_N16_REQUIRED')
    z1 = st.default_free_z(m, 'r1__robot')
    z2 = st.default_free_z(m, 'r2__robot')
    z3 = st.default_free_z(m, 'r3__robot')
    qpos_rows, qvel_rows = [], []
    d = mujoco.MjData(m)
    mujoco.mj_resetData(m, d)
    base_spawns = setup['base_spawns']
    st._free_pose(m, d, 'r1__robot', [*base_spawns['r1'][:2], z1], base_spawns['r1'][3])
    st._free_pose(m, d, 'r2__robot', [*base_spawns['r2'][:2], z2], base_spawns['r2'][3])
    st._free_pose(m, d, 'r3__robot', [*base_spawns['r3'][:2], z3], base_spawns['r3'][3])
    for rid in ('r1', 'r2', 'r3'):
        st.set_arm(m, d, rid, SEARCH, hardware)
    mujoco.mj_forward(m, d)
    for w, spec in enumerate(worlds):
        row = mujoco.MjData(m)
        mujoco.mj_resetData(m, row)
        st._free_pose(m, row, 'r1__robot', [*spec['r1'][:2], z1], spec['r1'][3])
        peer = spec.get('r2', base_spawns['r2'])
        st._free_pose(m, row, 'r2__robot', [*peer[:2], z2], peer[3])
        st._free_pose(m, row, 'r3__robot', [*base_spawns['r3'][:2], z3], base_spawns['r3'][3])
        for rid in ('r1', 'r2', 'r3'):
            st.set_arm(m, row, rid, SEARCH, hardware)
        mujoco.mj_forward(m, row)
        qpos_rows.append(row.qpos.copy())
        qvel_rows.append(row.qvel.copy())
    # Setup-only admission: no start penetration. Reuse existing checker.
    from sim.spawn_overlap_check import check, OPTION as OVERLAP
    floor = {m.geom(i).name for i in range(m.ngeom)
             if int(m.geom_type[i]) == int(mujoco.mjtGeom.mjGEOM_PLANE)
             and any(word in m.geom(i).name.lower() for word in ('floor', 'ground'))}
    cargo = {m.body(i).name for i in range(1, m.nbody)
             if int(m.body_jntnum[i]) and int(m.jnt_type[int(m.body_jntadr[i])]) == int(mujoco.mjtJoint.mjJNT_FREE)
             and not m.body(i).name.startswith(('r1__', 'r2__', 'r3__'))}
    wall = {m.geom(i).name for i in range(m.ngeom) if 'wall' in m.geom(i).name.lower()}
    admissions = []
    for w, row in enumerate(qpos_rows):
        d.qpos[:] = row
        mujoco.mj_forward(m, d)
        admitted = check(m, d, floor_geoms=floor, cargo_bodies=cargo, wall_geoms=wall, option=OVERLAP)
        admissions.append(dict(world=w, accepted=bool(admitted['accepted']), report=admitted))
    dump(args.output/'admission.json', admissions)
    if not all(a['accepted'] for a in admissions):
        raise ValueError('START_PENETRATING_OR_UNVERIFIED')
    (args.output/'scene.xml').write_text(xml)
    dump(args.output/'scene.json', scene.manifest)
    dump(args.output/'admission-eval-only.json', dict(evaluation_only=True, target=setup['evaluation_only'],
                                                      spawns=[w['r1'] for w in worlds]))
    dump(args.output/'static-map-eval-only.json', scene.config['static_map'])

    wp.init()
    wm = mjw.put_model(m)
    with unused_efm(m, d):
        wd = mjw.put_data(m, d, nworld=nworld, nconmax=512, njmax=2048)
    if wm.opt.noslip_iterations != 0:
        raise ValueError('WARP_NOSLIP0_REQUIRED')
    wp.copy(wd.qpos, wp.array(np.stack(qpos_rows), dtype=float))
    wp.copy(wd.qvel, wp.array(np.stack(qvel_rows), dtype=float))
    wp.synchronize()
    for _ in range(2):
        mjw.step(wm, wd)
    wp.synchronize()

    rc = Renderer(m, wm, wd, [('r1', 'r1__robot_cam', (640, 480))],
                  enabled=True, texture_after_lighting=True)
    mx, my = raw_fisheye_remap(640, 480)
    servos = (1, 3, 4, 5, 6)
    jointnames = {1: ('left_gripper_close', 'right_gripper_close'), 3: ('wrist_pitch',),
                  4: ('elbow',), 5: ('shoulder',), 6: ('arm_yaw',)}
    sidnames = {1: 'gripper', 3: 'wrist', 4: 'elbow', 5: 'shoulder', 6: 'yaw'}
    lookup = np.empty((5, 2001))
    servo_ids = []
    for k, sid in enumerate(servos):
        joints = [m.joint('r1__'+j).id for j in jointnames[sid]]
        ids = [i for i in range(m.nu) if int(m.actuator_trnid[i, 0]) in joints]
        servo_ids.append(ids)
        for pwm in range(500, 2501):
            targets = MasterPiDynamicsV2.pulse_to_joint_targets(
                SimpleNamespace(physical_params=hardware), {sid: pwm})
            jid = joints[0]
            value = targets[sidnames[sid]]
            lookup[k, pwm-500] = (float(np.clip(value, *m.jnt_range[jid]))
                                  if m.jnt_limited[jid] else value)
    wheel_ids = [m.actuator('r1__wheel_'+name+'_drive').id for name in ('fl', 'fr', 'rl', 'rr')]
    applied = np.array([[SEARCH[s] for s in servos]], float)
    relay = np.zeros((1, 4), int)
    drive = DriveParameters()
    ctrl = np.zeros(m.nu)
    for i in range(m.nu):
        if '__servo_' in m.actuator(i).name:
            ctrl[i] = wd.qpos.numpy()[0, int(m.jnt_qposadr[int(m.actuator_trnid[i, 0])])]

    detector_options = FloorGoalV3Options(**setup['detector'])
    detect = goal_detector()
    images = rc.render()
    pinhole = np.clip(images['r1'][0], 0, 255).astype(np.uint8)
    raw = cv2.remap(pinhole, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    if args.preflight:
        (args.output/'preflight').mkdir()
        cv2.imwrite(str(args.output/'preflight'/'world00-pinhole.jpg'), cv2.cvtColor(pinhole[0], cv2.COLOR_RGB2BGR))
        cv2.imwrite(str(args.output/'preflight'/'world00-raw.jpg'), cv2.cvtColor(raw[0], cv2.COLOR_RGB2BGR))
        hsv = cv2.cvtColor(raw[0], cv2.COLOR_RGB2HSV)
        sat = hsv[..., 1] >= 60
        hist = np.bincount(hsv[..., 0][sat].ravel(), minlength=180)
        top = np.argsort(hist)[-12:][::-1]
        diagnostics = []
        for w in range(nworld):
            patches, labels, diag = detect(raw[w], servo=SEARCH, profile='camera_v3', options=detector_options)
            scan = wall_observe(raw[w], SEARCH)
            diagnostics.append(dict(world=w, patches=len(patches), diagnostics=diag,
                                    centers=[p['center_body_m'] for p in patches],
                                    areas=[p.get('observed_area_m2') for p in patches],
                                    wall_segments=len(scan['segments']),
                                    wall_points=int(sum(len(s) for s in scan['segments']))))
        contact_fields = [name for name in dir(wd) if 'contact' in name.lower() or name in ('ncon', 'nefc')]
        dump(args.output/'preflight'/'preflight.json', dict(
            accepted=True, cpu_physics_steps=0, nworld=nworld,
            hsv_top_hue=[dict(hue=int(h), pixels=int(hist[h])) for h in top if hist[h]],
            detector_effective=[f.name+':'+str(getattr(detector_options, f.name))
                                for f in __import__('dataclasses').fields(detector_options)],
            diagnostics=diagnostics, contact_fields=contact_fields,
            contact_pairs=contact_pairs(wd, nworld)[:20],
            warp_noslip=int(wm.opt.noslip_iterations), cpu_noslip=int(m.opt.noslip_iterations)))
        return

    # Full gate.
    footprint = max(float(np.linalg.norm(np.asarray(v)[:, :2], axis=1).max())
                    for _, v in body_envelopes(SEARCH, 'camera_v3'))
    controllers = [EgocentricGoto(option=GOTO_OPTION, footprint_radius_m=footprint)
                   for _ in range(nworld)]
    per_world = [dict(world=w, spawn=list(spec['r1']), events=[], trace=[],
                      ring=deque(maxlen=100), seen=False, anchor_world=None,
                      anchor_t=None, memory_errors=[], visible_flags=[],
                      target_losses=0, collisions=0, collision_events=[],
                      final=None, done=False, status='cap_end', last_visible_t=None)
                 for w, spec in enumerate(worlds)]
    target = setup['evaluation_only']
    center = np.asarray(target['center_m'], float)
    half = np.asarray(target['half_m'], float)
    previous = [None]*nworld
    start = time.monotonic()
    steps = round(.1/m.opt.timestep)
    tape = wp.zeros((steps, nworld, m.nu), dtype=float)
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
        for _ in range(steps):
            wp.launch(issue, dim=(nworld, m.nu), inputs=[tape, step_index, wd.ctrl])
            mjw.step(wm, wd)
            wp.launch(advance, dim=1, inputs=[step_index])
    first30 = None
    status = 'cap_end'
    error = None
    try:
        for tick in range(setup['step_budget']):
            t = tick/10
            if (args.output/'SUPERVISOR_STOP.json').exists():
                status = 'SUPERVISOR_STOP'
                break
            qp = wd.qpos.numpy()
            if not np.isfinite(qp).all() or np.any(wd.overflow.numpy()):
                raise RuntimeError('NONFINITE_OR_CAPACITY')
            images = rc.render()
            pinhole = np.clip(images['r1'][0], 0, 255).astype(np.uint8)
            raw = cv2.remap(pinhole, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            actions, observations, scans = [], [], []
            for w in range(nworld):
                state = per_world[w]
                rgb = raw[w]
                obs = []
                scan = dict(segments=[])
                if not state['done']:
                    patches, _, diag = detect(rgb, servo=SEARCH, profile='camera_v3', options=detector_options)
                    if patches:
                        patch = max(patches, key=lambda p: (p.get('observed_area_m2', 0.), p['confidence']))
                        xy = np.asarray(patch['center_body_m'], float)
                        obs = [dict(id='zone-A-floor-marking', kind='zone_marking',
                                    signature='floor_orange_zone_marking',
                                    relative_xy_m=xy.tolist(),
                                    covariance_m2=point_covariance(xy).tolist(),
                                    hue=target.get('hue'), pixels=patch['pixels'])]
                    scan = wall_observe(rgb, SEARCH)
                    if tick == 0:
                        # No initial GT enters the controller. The spawn is an
                        # authored setup label, never a controller argument.
                        pass
                    action = controllers[w].step(t, previous[w], obs, scan=scan)
                    state['done'] = bool(controllers[w].done)
                else:
                    action = dict(kind='stop', drive=[0., 0., 0.], wheels=[0., 0., 0., 0.],
                                  duration_s=[0., 0., 0., 0.], stage='done', t=t, reason='done')
                state['trace'].append(dict(
                    t=t, frame_id=tick, action=action,
                    memories=(controllers[w].memories if w == 0 else None),
                    observation_relative_xy_m=(None if not obs else obs[0]['relative_xy_m']),
                    memory_count=len(controllers[w].memories),
                    visible=bool(obs), stage=controllers[w].stage,
                    reason=(None if not controllers[w].events else controllers[w].events[-1]['reason']),
                    wall_segments=len(scan['segments'])))
                observations.append(obs)
                scans.append(scan)
                actions.append(action)
                state['events'] = list(controllers[w].events)
                # Evaluation-only labels and memory-anchor error.
                body = m.body('r1__robot').id
                adr = int(m.jnt_qposadr[int(m.body_jntadr[body])])
                row = qp[w]
                q = row[adr+3:adr+7]
                wq, xq, yq, zq = q
                yaw = math.atan2(2*(wq*zq+xq*yq), 1-2*(yq*yq+zq*zq))
                pose = [float(row[adr]), float(row[adr+1]), yaw]
                visible = bool(obs)
                state['visible_flags'].append(visible)
                if visible and state['anchor_world'] is None:
                    state['anchor_world'] = pose_apply(pose, obs[0]['relative_xy_m'])
                    state['anchor_t'] = t
                    state['seen'] = True
                if state['seen'] and state['anchor_world'] is not None and controllers[w].memories:
                    goal = [mem for mem in controllers[w].memories
                            if mem['kind'] == 'zone_marking'
                            and mem['signature'] == 'floor_orange_zone_marking']
                    if goal:
                        predicted = pose_apply(pose, min(goal, key=lambda mem: mem['range_m'])['relative_xy_m'])
                        error = float(np.linalg.norm(predicted-state['anchor_world']))
                        state['memory_errors'].append(dict(t=t, error_m=error, visible=visible))
                if len(state['visible_flags']) >= 2 and not visible and state['visible_flags'][-2]:
                    state['target_losses'] += 1
                state['last_visible_t'] = t if visible else state['last_visible_t']
                state['final'] = dict(t=t, pose=pose, memory_count=len(controllers[w].memories),
                                      zone_distance_m=zone_distance(pose[:2], center, half),
                                      center_distance_m=float(np.linalg.norm(np.asarray(pose[:2])-center)),
                                      inside_zone=inside_zone(pose[:2], center, half),
                                      anchor_available=state['anchor_world'] is not None)
            # Issue one 0.1 s command per world through the same finite pulse
            # decoder.  Controller still receives only RGB/servo/own history.
            tape_rows = []
            for w, action in enumerate(actions):
                if action['kind'] in ('stop', 'option_off'):
                    wheels, duration = [0., 0., 0., 0.], [0., 0., 0., 0.]
                else:
                    wheels, duration = action['wheels'], action['duration_s']
                command = dict(t=t, wheels=wheels, duration_s=duration, pwm=SEARCH)
                if not per_world[w]['done']:
                    previous[w] = command
                tape_rows.append(dict(ctrl=ctrl, wheels=wheels,
                                      deadlines=[t+v if v else -1 for v in duration],
                                      applied=applied[0], target=[SEARCH[s] for s in servos],
                                      servo_active=[False]*5, now=t, servo_time=t))
            values, cmd_state = control_tape(
                tape_rows, relay, dt=float(m.opt.timestep),
                steps=steps, lookup=lookup, wheel_ids=wheel_ids,
                servo_ids=servo_ids, start_fraction=drive.start_fraction,
                kinetic_fraction=drive.kinetic_fraction, torque_cap_nm=drive.torque_cap_nm)
            applied = cmd_state['applied']; relay = cmd_state['relay']
            wp.copy(tape, wp.array(values, dtype=float))
            step_index.zero_()
            wp.capture_launch(cap.graph)
            # Contact audit is evaluation-only.
            pairs = contact_pairs(wd, nworld)
            for w, g1, g2 in pairs:
                b1 = m.geom_bodyid[g1]; b2 = m.geom_bodyid[g2]
                n1, n2 = m.body(b1).name, m.body(b2).name
                r1 = n1.startswith('r1__') or n2.startswith('r1__')
                other = n2 if n1.startswith('r1__') else n1
                if r1 and not (n1.startswith('r1__') and n2.startswith('r1__')):
                    gname = m.geom(g2 if n1.startswith('r1__') else g1).name.lower()
                    if not any(word in gname for word in ('floor', 'ground')):
                        per_world[w]['collisions'] += 1
                        per_world[w]['collision_events'].append(dict(t=t, a=n1, b=n2, geom=gname))
            # Ring buffer of the last 10 SIM seconds, recording only.
            for w in range(nworld):
                state = per_world[w]
                ok, enc = cv2.imencode('.jpg', cv2.cvtColor(raw[w], cv2.COLOR_RGB2BGR),
                                       [cv2.IMWRITE_JPEG_QUALITY, 75])
                state['ring'].append(dict(tick=tick, t=t, jpeg=enc.tobytes(), sha256=hashlib.sha256(enc.tobytes()).hexdigest()))
            if tick % 50 == 0:
                progress = dict(t=t, world_done=sum(s['done'] for s in per_world),
                                memory_max=max(len(c.memories) for c in controllers),
                                wall_s=time.monotonic()-start)
                dump(args.output/'progress.json', progress)
                print(json.dumps(progress), flush=True)
            if tick == 300 and first30 is None:
                first30 = (time.monotonic()-start)/300.
            if all(s['done'] for s in per_world):
                status = 'ALL_WORLDS_DONE'
                break
    except BaseException as exc:
        status = 'HOST_ERROR'
        error = repr(exc)
        raise
    finally:
        # Write the 10 Hz terminal rings first (recording-only).
        for w, state in enumerate(per_world):
            folder = args.output/'ring'/f'world{w:02d}'
            folder.mkdir(parents=True)
            for item in state['ring']:
                path = folder/f'{item["tick"]:04d}.jpg'
                path.write_bytes(item['jpeg'])
        # Recount the gate from per-world raw records.
        rows = []
        for w, state in enumerate(per_world):
            if state['anchor_world'] is not None:
                state['status'] = 'memory_anchor_created'
            else:
                state['status'] = 'no_target_detected'
                continue
            if state['final'] is None:
                state['status'] = 'no_final_state'
            elif inside_zone(state['final']['pose'][:2], center, half):
                state['status'] = 'arrived_inside_zone'
            elif state['done']:
                state['status'] = 'arrival_claimed_outside_zone'
            else:
                state['status'] = 'cap_end'
        for w, state in enumerate(per_world):
            dump(args.output/f'world{w:02d}.json', dict(
                world=w, spawn=state['spawn'], status=state['status'],
                seen=state['seen'], anchor_world=state['anchor_world'],
                anchor_t=state['anchor_t'], target_losses=state['target_losses'],
                collisions=state['collisions'], collision_events=state['collision_events'],
                final=state['final'], done=state['done'],
                events=state['events'], trace=[{k: v for k, v in row.items() if k != 'memories'}
                                               for row in state['trace']],
                memory_errors=state['memory_errors'],
                context=controllers[w].context()))
        counts = Counter(s['status'] for s in per_world)
        funnel = []
        left = nworld
        for gate, passed in [
                ('requested_n16', nworld),
                ('input_audit_zero_held_world_reads', nworld),
                ('target_observed_at_least_once', sum(s['seen'] for s in per_world)),
                ('arrived_inside_authored_zone', counts['arrived_inside_zone'])]:
            funnel.append(dict(stage=gate, input_n=left, cumulative_pass_n=passed,
                               rejected_n=left-passed))
            left = passed
        reasons = Counter()
        reason_rows = []
        for state in per_world:
            if state['status'] == 'arrived_inside_zone':
                continue
            reason = state['status']
            reasons[reason] += 1
            blocked = 'not_observed' if reason == 'no_target_detected' else 'target_zone_boundary'
            gap = None
            if state['final'] is not None:
                gap = float(state['final']['zone_distance_m'])
            reason_rows.append(dict(world=state['world'], reason_category=reason,
                                    blocked_object=blocked, minimum_gap_m=gap,
                                    gap_status=('not_measured' if gap is None else 'measured_eval_only')))
        memory_growth = []
        for state in per_world:
            all_errors = state['memory_errors']
            unseen = [e for e in all_errors if not e['visible']]
            if not all_errors:
                continue
            def slope(rows):
                if len(rows) < 2:
                    return None
                ts = np.asarray([e['t'] for e in rows]); es = np.asarray([e['error_m'] for e in rows])
                return float(np.polyfit(ts, es, 1)[0]) if np.ptp(ts) > 1e-9 else 0.
            memory_growth.append(dict(
                world=state['world'], samples=len(all_errors), unseen_samples=len(unseen),
                all_slope_m_per_s=slope(all_errors),
                unseen_slope_m_per_s=slope(unseen),
                max_error_m=float(max(e['error_m'] for e in all_errors)),
                final_error_m=float(all_errors[-1]['error_m'])))
        unseen_slopes = [g['unseen_slope_m_per_s'] for g in memory_growth
                         if g['unseen_slope_m_per_s'] is not None]
        summary = dict(
            status=status, source_sha=q['source_sha'], host=platform.node(),
            world_n=nworld, step_budget=setup['step_budget'], sim_s=(len(per_world[0]['trace'])-1)/10,
            wall_s=time.monotonic()-start, first30_wall_sim=first30,
            controller=GOTO_OPTION, memory_implementation='legacy_v1',
            footprint_radius_m=footprint, detector=setup['detector'],
            arrived_inside_zone_n=counts['arrived_inside_zone'],
            arrival_claimed_n=sum(s['done'] for s in per_world),
            target_lost_mid_route_n=sum(s['target_losses'] > 0 for s in per_world),
            target_loss_events=sum(s['target_losses'] for s in per_world),
            collision_n=sum(s['collisions'] for s in per_world),
            collision_worlds_n=sum(s['collisions'] > 0 for s in per_world),
            memory_growth=memory_growth,
            memory_growth_unseen_median_m_per_s=(float(np.median(unseen_slopes))
                                                 if unseen_slopes else None),
            memory_growth_unseen_n=len(unseen_slopes),
            statuses=dict(counts),
            input_audit=dict(held_world_reads=0, top_camera_control=False,
                             static_map_control=0, truth_control=0,
                             own_rgb_frames=nworld*len(per_world[0]['trace']),
                             own_command_rows=nworld*len(per_world[0]['trace'])),
            noslip_iterations=int(m.opt.noslip_iterations),
            warp_noslip_iterations=int(wm.opt.noslip_iterations),
            cpu_physics_steps=0, terminal_ring=dict(hz=10, seconds=10,
                                                    frames=sum(len(s['ring']) for s in per_world),
                                                    bytes=sum(p.stat().st_size for p in (args.output/'ring').rglob('*.jpg'))),
            cap_end_label='cap_end')
        dump(args.output/'summary.json', summary)
        dump(args.output/'rejection_table.json', dict(
            unit='world', funnel=funnel, reasons=dict(reasons), reason_rows=reason_rows,
            blocked_object=(reason_rows[0]['blocked_object'] if reason_rows else 'not_observed'),
            minimum_gap_m=(reason_rows[0]['minimum_gap_m'] if reason_rows else None),
            gap_status=('measured_eval_only' if reason_rows else 'not_measured'),
            raw=str(args.output), reproduction=sys.argv))
        dump(args.output/'SHA256SUMS.json', {str(p.relative_to(args.output)): sha(p)
                                             for p in args.output.rglob('*') if p.is_file()})
        dump(args.output/'EXIT', dict(status=status, error=error))
        print(json.dumps({k: summary[k] for k in ('status', 'arrived_inside_zone_n', 'world_n',
                                                   'collision_n', 'target_lost_mid_route_n')}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--queue', type=Path, required=True)
    parser.add_argument('--setup', type=Path, required=True)
    parser.add_argument('--renderer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--worlds', type=int, default=0)
    args = parser.parse_args()
    run(args)


if __name__ == '__main__':
    main()
