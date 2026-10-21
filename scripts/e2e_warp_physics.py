"""Native MJWarp E2E transport. Imported only after Linux/gcp6 admission.

Shared command/render code is byte-vendored. This initializer uses native
MJWarp options, with no C-equivalence shims, legacy plane or noslip10 path.
"""
from pathlib import Path
import importlib.util
import hashlib
import json
from types import SimpleNamespace
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'scripts/e2ewarp_vendor'


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def source_module():
    # Frozen backend imports the original unqualified core name. Bind it to the
    # byte-vendored core only while importing, without editing upstream files.
    core = module_at('_e2ewarp_core', VENDOR / 'warp_act_core.py')
    old = sys.modules.get('warp_act_core')
    sys.modules['warp_act_core'] = core
    try:
        backend = module_at('_e2ewarp_backend', VENDOR / 'warp_act_backend.py')
    finally:
        if old is None:
            sys.modules.pop('warp_act_core', None)
        else:
            sys.modules['warp_act_core'] = old
    schedule = module_at('_e2ewarp_schedule', VENDOR / 'warp_schedule_core.py')
    return backend, core, schedule


def build_context(seed, out, stack, *, nav_scene=False, nav_spawns=None, nav_keep=('r1', 'r2'),
                  nav_cubes=None, nav_arm_pwm=None):
    """Privileged initial construction only. No CPU integration/settling.

    ``nav_scene`` builds the contract-v1 two-robot navigation gate: cargo is not
    spawned, r3 is pruned from the XML and only the two wide-door lane spawns are
    initialised. Setup-only values never reach a controller.

    E2E-min (default off, harness/e2e_min_world.py): ``nav_cubes`` keeps the
    named colour boxes at setup-only xy (beam still removed) and records their
    eval-only qpos rows; ``nav_arm_pwm`` replaces SEARCH as the initial servo
    pose of a robot (render tests only).  Both None = unchanged nav gate world.
    """
    from harness.e2ewarp_nav_gate import NAV_SCENARIO, eval_geometry, pair_lane_spawns
    import mujoco
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.masterpi_dynamics_v2 import load_fitted_hardware, MasterPiDynamicsV2
    from sim.masterpi_model_v3 import v3_hardware
    from sim.masterpi_drive_friction_v7 import transform_xml, DriveParameters
    from sim import masterpi_camera_review_v3 as camera
    from sim.masterpi_camera_profile import mujoco_pixel_intrinsic
    from sim.s2_servo_stiffness import transform_xml as stiffness
    from sim.final_pair_highpose_nearclip import apply_xml as nearclip
    from sim.execution_contact_profile import apply_xml, assert_model_profile
    from sim import scene_contrast_v5 as contrast
    from harness.active_camera import SEARCH
    import xml.etree.ElementTree as ET

    # The owner file is byte-identical. Only its module-location resource root
    # is bound here because the vendor copy lives outside sim/.
    natural = module_at('_e2ewarp_natural', VENDOR / 'natural_scene_texture.py')
    natural.ASSETS = ROOT / 'sim/assets/floor_light_textured_v1'
    original_manifest, original_apply = natural.manifest, natural.apply
    natural.manifest = lambda assets=natural.ASSETS, extension=False: original_manifest(assets, extension=extension)
    natural.apply = lambda root, extension=False: original_apply(root, assets=natural.ASSETS, extension=extension)
    contrast.v1 = natural
    scenario_id = NAV_SCENARIO if nav_scene else 's1_normal_mixed_v7'
    scene = contrast.install(ScenarioFinalV3Scene.from_scenario(scenario_id, seed),
                             stack['scene_profile'], extension=True)
    if nav_scene:
        # Navigation gate: no cargo bodies and no cargo setup rows (gate 2 loads).
        scene.cargo = []
        if nav_cubes is None:
            scene.config['setup_only']['objects'] = {}
        else:
            from harness.e2e_min_world import select_cube_objects
            scene.config['setup_only']['objects'] = select_cube_objects(
                scene.config['setup_only']['objects'], nav_cubes)
    elif nav_cubes is not None or nav_arm_pwm is not None:
        raise ValueError('E2E-min cubes/arm pose require the nav scene')
    hw, _ = load_fitted_hardware()
    # The zone scene builder itself requires the three production robots, so the
    # XML is authored with all three and r3 is pruned after every scene/hardware
    # /contact transform (navigation gate only).
    xml = scene.robot_transform(scene.transform(build_multi_robot_xml(hw)),
                                hardware=hw, calibrated_keys=hw)
    xml = camera.transform_xml(nearclip(xml), profile_id=camera.PROFILE_ID)
    for rid in ('r1', 'r2', 'r3'):
        xml = stiffness(xml, servo_stiffness='real_v1', robot_id=rid)
    tree = ET.fromstring(xml)
    # Existing approved end-color appearance, exact owner RGBA, all beam IDs.
    # The navigation gate spawns no cargo, so the long-beam bands do not exist;
    # the recolour only applies to runs that carry the beam (gate 2 and later).
    if not nav_scene:
        for suffix, rgba in (('band_neg', '.02 .95 .60 1'), ('band_pos', '.02 .02 .95 1')):
            geoms = [g for g in tree.iter('geom') if g.get('name', '').endswith('__' + suffix)]
            if not geoms:
                raise ValueError('existing original beam band required')
            for g in geoms:
                g.set('rgba', rgba)
    xml = transform_xml(ET.tostring(tree, encoding='unicode'), DriveParameters(), 'mesh', 'off')
    xml = apply_xml(xml, stack['contact_profile'])
    if nav_scene:
        from harness.e2ewarp_nav_gate import prune_robots
        xml = prune_robots(xml, keep=nav_keep)
    if nav_cubes is not None:
        from harness.e2e_min_world import audit_cube_bodies
        audit_cube_bodies(xml, nav_cubes)
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    assert_model_profile(model, stack['contact_profile'], data.eq_active)
    hw = v3_hardware(hw)
    hw.setdefault('servo6_center_pwm', 1500.)
    robots, ports = {}, {}
    if nav_scene:
        spawns = nav_spawns or pair_lane_spawns(scene.config['setup_only']['spawns'])
        # The r4 solo diagnostic keeps exactly one authored robot in the scene.
        spawns = {r: pose for r, pose in spawns.items() if r in tuple(nav_keep)}
    else:
        spawns = scene.config['setup_only']['spawns']
    servo_joint = dict(yaw='arm_yaw', shoulder='shoulder', elbow='elbow', wrist='wrist_pitch')
    robot_qpos_adr = {}
    for rid, pose in spawns.items():
        bid = model.body(rid + '__robot').id
        adr = int(model.jnt_qposadr[int(model.body_jntadr[bid])])
        data.qpos[adr:adr+7] = [*pose[:3], np.cos(pose[3]/2), 0, 0, np.sin(pose[3]/2)]
        robot_qpos_adr[rid] = adr
        robot = SimpleNamespace(model=model, physical_params=hw,
            wheel_act=[model.actuator(rid+'__wheel_'+n+'_drive').id for n in ('fl', 'fr', 'rl', 'rr')],
            arm_joint={k: model.joint(rid+'__'+n).id for k, n in servo_joint.items()},
            servo_act={k: model.actuator(rid+'__servo_'+n).id for k, n in
                       dict(yaw='arm_yaw', shoulder='shoulder', elbow='elbow', wrist='wrist').items()},
            gripper_joint=[model.joint(rid+'__'+n+'_gripper_close').id for n in ('left', 'right')],
            gripper_act=[model.actuator(rid+'__servo_gripper_'+n).id for n in ('left', 'right')],
            servo_command_pulses=SEARCH.copy())
        robot.pulse_to_joint_targets = lambda p, r=robot: MasterPiDynamicsV2.pulse_to_joint_targets(r, p)
        from harness.e2e_min_world import arm_pwm
        initial_pwm = arm_pwm(nav_arm_pwm, rid, SEARCH)
        robot.servo_command_pulses = dict(initial_pwm)
        targets = robot.pulse_to_joint_targets(initial_pwm)
        for key, jid in robot.arm_joint.items():
            value = np.clip(targets[key], *model.jnt_range[jid])
            data.qpos[int(model.jnt_qposadr[jid])] = value
            data.ctrl[robot.servo_act[key]] = value
        for jid, aid in zip(robot.gripper_joint, robot.gripper_act):
            data.qpos[int(model.jnt_qposadr[jid])] = targets['gripper']
            data.ctrl[aid] = targets['gripper']
        cid = model.camera(rid+'__robot_cam').id
        model.cam_pos[cid], model.cam_quat[cid] = camera.POSITION_M, camera.QUAT_WXYZ
        model.cam_resolution[cid] = (640, 480)
        model.cam_sensorsize[cid] = (640, 480)
        model.cam_intrinsic[cid] = mujoco_pixel_intrinsic(640, 480)
        robots[rid] = robot
        ports[rid] = SimpleNamespace(_motor_commands=(0.,)*4, _wheel_deadlines=[None]*4,
            _servo_applied=dict(initial_pwm), _servo_targets={}, _servo_tick_time=0.)
    for item in scene.config['setup_only']['objects'].values():
        jid = model.joint(item['joint_name']).id
        adr = int(model.jnt_qposadr[jid])
        data.qpos[adr:adr+7] = [*item['position_m'], 1, 0, 0, 0]
    data.eq_active[:] = 0
    # Kinematics for initialization/contact allocation only; never CPU step.
    mujoco.mj_forward(model, data)
    out.mkdir(parents=True, exist_ok=False)
    (out/'scene.xml').write_text(xml)
    if nav_scene:
        geometry = eval_geometry(scene, spawns, robot_qpos_adr)
        if nav_cubes is not None:
            from harness.e2e_min_world import cargo_pair_audit, cube_geometry
            geometry.update(cube_geometry(model, nav_cubes, scene.config['setup_only']['objects']))
            geometry['cargo_contact_pairs'] = cargo_pair_audit(xml)
        if nav_arm_pwm is not None:
            geometry['initial_arm_pwm'] = {r: {str(k): int(v) for k, v in p.items()}
                                           for r, p in nav_arm_pwm.items()}
        (out/'eval-geometry.json').write_text(json.dumps(geometry, ensure_ascii=False, indent=1) + '\n')
    cargo = [i for i in range(model.ngeom) if model.body(int(model.geom_bodyid[i])).name.startswith('cargo_')]
    fingers = {model.geom(r+'__'+s+'_finger').id: 2*k+j for k, r in enumerate(robots) for j, s in enumerate(('left', 'right'))}
    world = SimpleNamespace(model=model, data=data, scene_xml=xml, robot=robots.__getitem__,
                            drive_parameters=DriveParameters())
    return dict(world=world, ports=ports, gids=cargo, finger_ids=fingers, scene_xml_path=out/'scene.xml',
                scene=scene, static_map=scene.config['static_map'], no_cargo=not cargo)


def transport(contexts, out, sha, stack):
    backend, core, schedule = source_module()
    if all(not context.get('gids') for context in contexts):
        # Navigation gate: no cargo exists, so the evaluator-only contact
        # telemetry has no targets. An all-zero target mask is the honest
        # representation (the evaluate kernel then reports no finger force);
        # the vendored file stays byte-identical (module-level rebind only).
        def _no_cargo_contact_maps(ngeom, targets, fingers):
            return (np.zeros((len(targets), ngeom), dtype=np.int32),
                    np.full((len(targets), ngeom), -1, dtype=np.int32))
        backend.contact_maps = _no_cargo_contact_maps

    class NativeE2E(backend.WarpTransport):
        def initialize(self, contexts):
            import mujoco_warp as mjw
            import warp as wp
            from sim.masterpi_camera_profile import raw_fisheye_remap
            from sim.execution_contact_profile import assert_model_profile
            self.wp, self.mjw = wp, mjw
            self.contexts, self.n = contexts, len(contexts)
            self.robot_ids = tuple(contexts[0]['ports'])
            self.camera_size, self.finger_channels = (640, 480), contexts[0]['finger_ids']
            self.m = m = contexts[0]['world'].model
            self.dt, self.origin, self.tick = float(m.opt.timestep), 0., 0
            if len({hashlib.sha256(c['world'].scene_xml.encode()).hexdigest() for c in contexts}) != 1:
                raise ValueError('one exact scene model per batch required')
            wp.init()
            if not wp.is_cuda_available():
                raise RuntimeError('CUDA required; no CPU physics fallback')
            wp.set_device('cuda:0')
            self.wm = mjw.put_model(m)
            assert_model_profile(self.wm, stack['contact_profile'])
            # Allocation only, same full-scene envelope as mapbuild6; not an
            # acceptance tolerance. Overflow is a HOST_ERROR, never truncated.
            self.wd = mjw.put_data(m, contexts[0]['world'].data, nworld=self.n, nconmax=512, njmax=2048)
            self.copy_initial_state(contexts)
            self.robot_relay_states = {r: np.zeros((self.n, 4), int) for r in self.robot_ids}
            self.relay_state = self.robot_relay_states.get(self.robot_ids[0])
            steps, chunk, launches = schedule.physics_schedule(.1, self.dt)
            self.launches = launches
            self.tape = wp.zeros((steps, self.n, m.nu), dtype=float)
            self.graph_tick = wp.zeros(1, dtype=int)
            self.force_out = wp.zeros((self.n, len(self.finger_channels)), dtype=float)
            self.init_kernels(contexts)
            mjw.step(self.wm, self.wd)
            wp.synchronize()
            self.wd = mjw.put_data(m, contexts[0]['world'].data, nworld=self.n, nconmax=512, njmax=2048)
            self.copy_initial_state(contexts)
            with wp.ScopedCapture() as capture:
                for _ in range(chunk):
                    wp.launch(self.command_kernel, dim=(self.n, m.nu), inputs=[self.tape, self.graph_tick, self.wd.ctrl])
                    mjw.step(self.wm, self.wd)
                    wp.launch(self.advance_kernel, dim=1, inputs=[self.graph_tick])
            self.graph = capture.graph
            self.rc = mjw.create_render_context(m, nworld=self.n, cam_res=(640, 480), render_rgb=True,
                render_depth=False, render_seg=False, use_textures=True, use_shadows=True,
                enabled_geom_groups=[0, 1, 2, 3], cam_active=[r+'__robot_cam' for r in self.robot_ids])
            self.device_rgb = wp.zeros((self.n, 480, 640), dtype=wp.vec3)
            self.mx, self.my = raw_fisheye_remap(640, 480)
            self.bindings = {}
            for rid in self.robot_ids:
                self.build_lookup(contexts[0]['world'].robot(rid))
                self.bindings[rid] = dict(lookup=self.lookup, wheel_ids=self.wheel_ids, servo_ids=self.servo_ids)
            self.sync_render(contexts)

        def launch_step(self):
            import time
            self._physics_started = time.perf_counter()
            self.graph_tick.zero_()
            for _ in range(self.launches):
                self.wp.capture_launch(self.graph)

    return NativeE2E('gcp6', sha, 'mjwarp_batch_v1', out)


def issue(context, robot, command):
    """Issue one contract command row to a robot port.

    ``command()`` from harness.grasp_act_contract emits wheel values in percent
    (0 or 31..40), while the MJWarp relay consumes normalized [-1, 1] commands.
    The conversion belongs here; mixing both conventions in the port was the
    cause of 'finite normalized issued commands required' on the first executed
    navigation-gate calibration attempt.
    """
    wheels = []
    for value in command['wheels']:
        value = float(value)
        if value == 0.:
            wheels.append(0.)
        elif .31 - 1e-9 <= abs(value) <= .40 + 1e-9:
            wheels.append(value)
        elif .31 - 1e-9 <= abs(value) <= 40. + 1e-9:
            wheels.append(value / 100.0)
        else:
            raise ValueError('wheel command outside the 31..40 percent vocabulary')
    port = context['ports'][robot]
    port._motor_commands = tuple(wheels)
    port._wheel_deadlines = [command['t']+v if v else None for v in command['duration_s']]
    from harness import e2e_min_actuation
    if e2e_min_actuation.mode() == 'duty_port_v1':
        # E2E-min opt-in: ACT owner (DutyActPort) servo-update order.
        e2e_min_actuation.duty_port_servos(port, command['pwm'], command['t'])
        return
    port._servo_targets.update({int(k): v for k, v in command['pwm'].items()})


def own_map(frame, state, *, keyframe_policy='off'):
    """mapbuild6 qualified LK, own gauge only. No pretend static registration."""
    import cv2
    from harness.servo_camera_fk import transform_from_commands
    from harness.e2e_rgb_vo import ground_pair, compose, PARAMS
    from harness.self_odom_grid import OdomGrid, transform
    from harness.self_map_csm import CSMOptions
    from harness.e2e_warp_runtime import keyframe_due, rejection
    from harness.mapbuild_rbpf import virtual_scan
    from harness.scene_colour_boundary import ColourBoundaryState, RELOC16_OPTION
    import json
    rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(frame.jpeg, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    pwm = {int(k): v for k, v in frame.issued[-1]['pwm'].items()}
    camera, reason = transform_from_commands(pwm, camera_pose='servo_fk_v1')
    flow = dict(status='bootstrap')
    if state.get('pwm') != pwm:
        state['servo_changed_s'] = frame.sim_s
    settled = frame.sim_s-state['servo_changed_s'] >= max(PARAMS['settle_s'])
    if state.get('rgb') is not None:
        if state['pwm'] != pwm:
            flow = dict(status='unknown_servo_change')
        elif camera is None:
            flow = dict(status='unknown_'+reason)
        elif not settled:
            flow = dict(status='unknown_commanded_camera_settling')
        else:
            flow = ground_pair(state['rgb'], rgb, pwm)
    pose = state.get('pose', np.zeros(3))
    if flow['status'] == 'measured':
        pose = compose(pose, flow['delta'])
    # No wheel commands are issued in the diagnostic. Unknown remains unknown;
    # do not convert stationary intent into a measured zero or a global fix.
    state.update(rgb=rgb, pwm=pwm, pose=pose)
    if 'grid' not in state:
        calibration=ROOT/'experiments/2026-10-17-e2ewarp/vendor-data/colour-calibration.json'
        if hashlib.sha256(calibration.read_bytes()).hexdigest() != 'a37cf96551abbfb8b38df3efc1cd61f3f357ac9eb3a1dcd0b4d9947242e4e24f':
            raise ValueError('FROZEN_COLOUR_CALIBRATION_REQUIRED')
        state['colour'] = ColourBoundaryState('walls_floor_contrast_v5_indigo110_s80',
            json.loads(calibration.read_text()), option=RELOC16_OPTION)
        state['grid'] = OdomGrid(frame.robot_id, profiles={})
    scan_status, hits, inserted = 'unknown_commanded_camera_settling', 0, False
    input_rejection=rejection(scan_status,category='camera_qualification')
    if camera is not None and settled:
        scan = virtual_scan(rgb, pwm, state['colour'])
        hits = sum(c['status'] == 'hit' for c in scan['columns'])
        scan_status = 'observed_wall_contacts' if hits else 'unknown_wall_contact'
        input_rejection=rejection('unknown_wall_contact' if not hits else 'keyframe_interval_wait',
                                  category='wall_observation' if not hits else 'map_keyframe_scheduler')
        # Use the frozen LK-only map insertion from mapbuild5_replay; RBPF stays
        # off pending its owner comparison. This map remains in the own gauge.
        interval_ticks=round(CSMOptions().keyframe_interval_s*10)
        if scan['segments'] and keyframe_due(frame.tick, state.get('last_map_tick'), interval_ticks, option=keyframe_policy):
            state['grid'].insert(transform([scan['camera']], pose)[0],
                                 [transform(s, pose) for s in scan['segments']])
            inserted = True
            state['last_map_tick'] = frame.tick
            input_rejection=None
    return dict(own_gauge_pose=pose.tolist(), static_map_registered=False, qualified_navigation=False,
                status=flow['status'], fk_status=reason, flow=flow,
                self_map=dict(frame='own_start', occupied_cells=sum(v>0 for v in state['grid'].cells.values()),
                              known_cells=len(state['grid'].cells), wall_columns=hits, scan_status=scan_status,
                              inserted=inserted, rbpf='off', input_rejection=input_rejection),
                dependency_wait=['loaded_fk', 'static_map_registration', 'selected_ACT', 'release_relocalization'])
