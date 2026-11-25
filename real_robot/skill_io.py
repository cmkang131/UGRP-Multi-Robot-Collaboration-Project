"""The two sides a skill test can run on, with one surface: start(pwm), frame(), send(row), now(), close().

SimIO  : the solo MuJoCo world exactly as solo_pipeline/scripts/run_grasp_act_student.py builds it
         (same scene hooks, solo_green_v1 look, 640x480 own camera), commands applied as that runner
         does (all four wheels replaced, each stops after its pulse, servos only on change), physics
         advanced 0.1 s per tick. Evaluation values are read only by `truth()`, after the brain acted.
RealIO : the Pi command server (real_robot/server.py) and camera stream (real_robot/camera.py).
         The control clock is logical (0.1 s per tick, like the simulator): when ACT inference takes
         longer than a tick the robot waits (every pulse ends within 0.15 s, so it stands still),
         and the next tick uses the newest frame. The wall time of every tick is logged.
"""
from __future__ import annotations

import base64
import math
import time

PERIOD_S = 0.1


class SimIO:
    def __init__(self, plan, *, appearance=None, signs_dir=None, objects=None):
        """signs_dir: also stand the wall number signs 11-13 (harness/robot_tags_v1.add_signs, as the team runner does
        with --robot-tags), drawings written there. objects: {box id: [x, y]} moves boxes before setup."""
        from pathlib import Path
        import importlib.util as ilu
        root = Path(__file__).resolve().parents[1]
        if appearance is None:
            spec = ilu.spec_from_file_location('solo_appearance_v1', str(root / 'scripts' / 'solo_appearance_v1.py'))
            appearance = ilu.module_from_spec(spec); spec.loader.exec_module(appearance)
        from sim.zone_scenario_scene import ScenarioFinalV3Scene
        from sim.render_profile import install
        from sim.final_pair_highpose_nearclip import wrap
        from sim import masterpi_camera_review_v3 as camera
        from sim.s2_servo_stiffness import transform_xml as stiffness
        from sim.s2_realism_camera_binding import bind_camera
        from sim.masterpi_drive_friction_v7 import build_world, PROFILE
        from sim.camera_robot_port import CameraRobotPort
        scene = wrap(install(ScenarioFinalV3Scene.from_scenario(plan['scenario_id'], plan['seed']), 'floor_light_v1'))
        scene.config['setup_only']['spawns'] = plan['spawns']
        for k, xy in (objects or {}).items():
            scene.config['setup_only']['objects'][k]['position_m'][:2] = [float(xy[0]), float(xy[1])]
        tags = None
        if signs_dir is not None:
            spec = ilu.spec_from_file_location('robot_tags_v1', str(root / 'harness' / 'robot_tags_v1.py'))
            tags = ilu.module_from_spec(spec); spec.loader.exec_module(tags)
            textures = tags.write_textures(Path(signs_dir), list(tags.SIGNS))
        plan = dict(plan); plan.setdefault('solo_appearance', {'profile': 'solo_green_v1', 'jitter': False})
        scene = appearance.apply_plan(scene, plan)
        original = scene.robot_transform
        def transform(xml, **kw):
            xml = camera.transform_xml(original(xml, **kw), profile_id=camera.PROFILE_ID)
            for rid in ('r1', 'r2', 'r3'):
                xml = stiffness(xml, servo_stiffness='real_v1', robot_id=rid)
            if tags is not None:
                xml = tags.add_signs(xml, textures)
            return xml
        scene.robot_transform = transform
        self.world = build_world(scene, drive_profile=PROFILE, seed=plan['seed'], width=640, height=480, render=True,
                                 warehouse_layout=scene.engine_layout, warehouse_cargo_ids=None,
                                 roller_collision='mesh', idle_robot_contacts='off')
        for ctl in self.world.controllers.values():
            bind_camera(ctl)
        scene.setup(self.world)
        self.rid = plan['robot_id']
        self.port = CameraRobotPort(self.world, self.rid)
        self.robot = self.world.robot(self.rid)
        self.objects = scene.config['setup_only']['objects']
        self.item = plan.get('item_id')
        self.pwm = None
        self.origin = None

    def _step_until(self, until, wheels=(0.,) * 4, deadlines=(0.,) * 4):
        w = self.world
        while float(w.data.time) < until - 1e-8:
            t = float(w.data.time)
            self.port.tick(t)
            self.port._set_motors(tuple(v if t < d else 0. for v, d in zip(wheels, deadlines)))
            w._physics_step_for(self.robot)

    def _servo(self, s, p, t):
        self.port.apply({'kind': 'look', 'pan_pulse': p} if s == 6 else {'kind': 'arm', 'servo_id': s, 'pulse': p}, t)

    def start(self, pwm):
        t = float(self.world.data.time)
        for s, v in pwm.items():
            self._servo(int(s), int(v), t)
        self._step_until(t + 1.)
        self.pwm = {str(k): int(v) for k, v in pwm.items()}
        self.origin = float(self.world.data.time)

    def now(self):
        return float(self.world.data.time)

    def frame(self):
        return base64.b64decode(self.port.capture()['image'])

    def send(self, row):
        now = self.now()
        self.port._command_expires_at = self.port._drive_expires_at = None
        self.port._set_motors(tuple(row['wheels']))
        deadlines = [now + d for d in row['duration_s']]
        for s, p in row['pwm'].items():
            if p != self.pwm[s]:
                self._servo(int(s), int(p), now)
        self.pwm = dict(row['pwm'])
        tick = round((now - self.origin) / PERIOD_S) + 1
        self._step_until(self.origin + tick * PERIOD_S, row['wheels'], deadlines)

    def truth(self):
        """Evaluation only: the base pose and every box (x, y, z, kind)."""
        w = self.world
        boxes = {k: dict(kind=v['kind'], xyz=[round(float(x), 4) for x in w.data.xpos[w.model.body(v['body_name']).id]])
                 for k, v in self.objects.items() if 'body_name' in v}
        xyz = self.robot.base_xyz()
        return {'t': round(self.now() - self.origin, 2), 'base': [round(float(xyz[0]), 4), round(float(xyz[1]), 4),
                round(float(self.robot.base_rpy()[2]), 4)], 'boxes': boxes}

    def close(self):
        pass


class RealIO:
    def __init__(self, host, *, cmd_port=8765, cam_port=8766, timeout_s=3.0, frame_transform=None, adapter=None):
        from real_robot.server import RobotLink
        from real_robot.camera import CameraLink
        self.robot = RobotLink(host, cmd_port, timeout_s)
        self.camera = CameraLink(host, cam_port, timeout_s)
        self.adapter = adapter
        self.frame_transform = frame_transform if frame_transform is not None else (
            adapter.frame_transform if adapter is not None else None
        )
        self.tick = 0
        self.t_wall0 = None
        self.last_frame_id = None
        self.ticks = []

    def start(self, pwm, settle_s=1.0):
        r = self.robot.init_servos({str(k): int(v) for k, v in pwm.items()}, duration_s=1.0)
        if r.get('status') != 'initialized':
            raise RuntimeError(f'servo init refused: {r}')
        time.sleep(settle_s)
        deadline = time.monotonic() + 5
        while self.camera.newest() is None:
            if time.monotonic() > deadline:
                raise RuntimeError(f'no camera frame: {self.camera.error}')
            time.sleep(0.05)
        self.t_wall0 = time.monotonic()

    def now(self):
        return self.tick * PERIOD_S

    def frame(self):
        header, jpeg = self.camera.newest()
        self.last_frame_id = header['frame_id']
        self._header = header
        if self.frame_transform is not None:
            jpeg = self.frame_transform(jpeg)
        return jpeg

    def send(self, row):
        t_send = time.monotonic()
        reply = self.robot.send(row)
        self.ticks.append({'tick': self.tick, 't_wall': round(t_send - self.t_wall0, 3), 'frame_id': self.last_frame_id,
                           'frame_age_s': round(t_send - self._header['t_arrival_laptop'], 3), 'reply': reply})
        if reply.get('status') == 'rejected':
            raise RuntimeError(f'command refused: {reply}')
        self.tick += 1
        # at least 0.1 s between two commands, as in the simulator (a new command replaces all four wheels, so
        # sending faster would cut pulses short); a slow tick is not made up with a burst of commands
        time.sleep(max(0.0, t_send + PERIOD_S - time.monotonic()))

    def truth(self):
        return None

    def close(self):
        try:
            self.robot.stop('skill test end')
        finally:
            self.robot.close()
            self.camera.close()
