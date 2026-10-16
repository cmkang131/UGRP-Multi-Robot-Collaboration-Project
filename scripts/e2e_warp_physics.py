"""Native MJWarp E2E transport. Imported only after Linux/gcp6 admission.

Shared command/render code is byte-vendored. This initializer uses native
MJWarp options, with no C-equivalence shims, legacy plane or noslip10 path.
"""
from pathlib import Path
import importlib.util
import hashlib
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
    return backend, core


def build_context(seed, out, stack):
    """Privileged initial construction only. No CPU integration/settling."""
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
    scene = contrast.install(ScenarioFinalV3Scene.from_scenario('s1_normal_mixed_v7', seed),
                             stack['scene_profile'], extension=True)
    hw, _ = load_fitted_hardware()
    xml = scene.robot_transform(scene.transform(build_multi_robot_xml(hw)), hardware=hw, calibrated_keys=hw)
    xml = camera.transform_xml(nearclip(xml), profile_id=camera.PROFILE_ID)
    for rid in ('r1', 'r2', 'r3'):
        xml = stiffness(xml, servo_stiffness='real_v1', robot_id=rid)
    tree = ET.fromstring(xml)
    # Existing approved end-color appearance, exact owner RGBA, all beam IDs.
    for suffix, rgba in (('band_neg', '.02 .95 .60 1'), ('band_pos', '.02 .02 .95 1')):
        geoms = [g for g in tree.iter('geom') if g.get('name', '').endswith('__' + suffix)]
        if not geoms:
            raise ValueError('existing original beam band required')
        for g in geoms:
            g.set('rgba', rgba)
    xml = transform_xml(ET.tostring(tree, encoding='unicode'), DriveParameters(), 'mesh', 'off')
    xml = apply_xml(xml, stack['contact_profile'])
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    assert_model_profile(model, stack['contact_profile'], data.eq_active)
    hw = v3_hardware(hw)
    hw.setdefault('servo6_center_pwm', 1500.)
    robots, ports = {}, {}
    servo_joint = dict(yaw='arm_yaw', shoulder='shoulder', elbow='elbow', wrist='wrist_pitch')
    for rid, pose in scene.config['setup_only']['spawns'].items():
        bid = model.body(rid + '__robot').id
        adr = int(model.jnt_qposadr[int(model.body_jntadr[bid])])
        data.qpos[adr:adr+7] = [*pose[:3], np.cos(pose[3]/2), 0, 0, np.sin(pose[3]/2)]
        robot = SimpleNamespace(model=model, physical_params=hw,
            wheel_act=[model.actuator(rid+'__wheel_'+n+'_drive').id for n in ('fl', 'fr', 'rl', 'rr')],
            arm_joint={k: model.joint(rid+'__'+n).id for k, n in servo_joint.items()},
            servo_act={k: model.actuator(rid+'__servo_'+n).id for k, n in
                       dict(yaw='arm_yaw', shoulder='shoulder', elbow='elbow', wrist='wrist').items()},
            gripper_joint=[model.joint(rid+'__'+n+'_gripper_close').id for n in ('left', 'right')],
            gripper_act=[model.actuator(rid+'__servo_gripper_'+n).id for n in ('left', 'right')],
            servo_command_pulses=SEARCH.copy())
        robot.pulse_to_joint_targets = lambda p, r=robot: MasterPiDynamicsV2.pulse_to_joint_targets(r, p)
        targets = robot.pulse_to_joint_targets(SEARCH)
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
            _servo_applied=SEARCH.copy(), _servo_targets={}, _servo_tick_time=0.)
    for item in scene.config['setup_only']['objects'].values():
        jid = model.joint(item['joint_name']).id
        adr = int(model.jnt_qposadr[jid])
        data.qpos[adr:adr+7] = [*item['position_m'], 1, 0, 0, 0]
    data.eq_active[:] = 0
    # Kinematics for initialization/contact allocation only; never CPU step.
    mujoco.mj_forward(model, data)
    out.mkdir(parents=True, exist_ok=False)
    (out/'scene.xml').write_text(xml)
    cargo = [i for i in range(model.ngeom) if model.body(int(model.geom_bodyid[i])).name.startswith('cargo_')]
    fingers = {model.geom(r+'__'+s+'_finger').id: 2*k+j for k, r in enumerate(robots) for j, s in enumerate(('left', 'right'))}
    world = SimpleNamespace(model=model, data=data, scene_xml=xml, robot=robots.__getitem__,
                            drive_parameters=DriveParameters())
    return dict(world=world, ports=ports, gids=cargo, finger_ids=fingers, scene_xml_path=out/'scene.xml',
                scene=scene, static_map=scene.config['static_map'])


def transport(contexts, out, sha, stack):
    backend, core = source_module()

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
            self.wm = mjw.put_model(m)
            assert_model_profile(self.wm, stack['contact_profile'])
            # Allocation only, same full-scene envelope as mapbuild6; not an
            # acceptance tolerance. Overflow is a HOST_ERROR, never truncated.
            self.wd = mjw.put_data(m, contexts[0]['world'].data, nworld=self.n, nconmax=512, njmax=2048)
            self.copy_initial_state(contexts)
            self.robot_relay_states = {r: np.zeros((self.n, 4), int) for r in self.robot_ids}
            self.relay_state = self.robot_relay_states['r1']
            steps, chunk, launches = core.physics_schedule(.1, self.dt)
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
    port = context['ports'][robot]
    port._motor_commands = tuple(command['wheels'])
    port._wheel_deadlines = [command['t']+v if v else None for v in command['duration_s']]
    port._servo_targets.update({int(k): v for k, v in command['pwm'].items()})


def own_map(frame, state):
    """mapbuild6 qualified LK, own gauge only. No pretend static registration."""
    import cv2
    from harness.servo_camera_fk import transform_from_commands
    from harness.e2e_rgb_vo import ground_pair, compose
    rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(frame.jpeg, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    pwm = {int(k): v for k, v in frame.issued[-1]['pwm'].items()}
    camera, reason = transform_from_commands(pwm, camera_pose='servo_fk_v1')
    flow = dict(status='bootstrap')
    if state.get('rgb') is not None:
        if state['pwm'] != pwm:
            flow = dict(status='unknown_servo_change')
        elif camera is None:
            flow = dict(status='unknown_'+reason)
        else:
            flow = ground_pair(state['rgb'], rgb, pwm)
    pose = state.get('pose', np.zeros(3))
    if flow['status'] == 'measured':
        pose = compose(pose, flow['delta'])
    # No wheel commands are issued in the diagnostic. Unknown remains unknown;
    # do not convert stationary intent into a measured zero or a global fix.
    state.update(rgb=rgb, pwm=pwm, pose=pose)
    return dict(own_gauge_pose=pose.tolist(), static_map_registered=False, qualified_navigation=False,
                status=flow['status'], fk_status=reason, flow=flow,
                dependency_wait=['loaded_fk', 'static_map_registration', 'selected_ACT', 'release_relocalization'])
