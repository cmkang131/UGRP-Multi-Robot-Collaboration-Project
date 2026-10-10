"""Physics-only owner for bounded final-environment acquisition.

Imported only after execution admission. Teacher/GT measurements are written
to eval_only, never returned to a student, provider, or command scheduler.
"""
from __future__ import annotations

import json
from pathlib import Path

from harness import zone_final_environment as env
from scripts.run_final_environment_checks import ROBOTS, write


class PhysicsBackend:
    def __init__(self, bundle, out, *, seed):
        from sim.zone_final_v3_scene import FinalV3Scene, build_world
        from sim.zone_arena import DEFAULT_GOAL
        from sim.zone_cargo_contact import base_profile
        from sim.camera_robot_port import CameraRobotPort

        self.out, self.bundle = Path(out), bundle
        self.world, self.ports, self.streams = None, {}, {}
        self.frame, self.deadline = 0, None
        self.commands = {}
        spec = {'map': bundle['map_id'], 'seed': seed, 'goal': DEFAULT_GOAL,
                'extra_boxes': {}, 'team_cargo': []}
        self.scene = FinalV3Scene.from_spec(spec, base_profile(bundle['contact_profile']))
        try:
            self.world = build_world(self.scene, bundle['contact_profile'], seed=seed,
                                     width=640, height=480, render=True,
                                     warehouse_layout=self.scene.engine_layout, warehouse_cargo_ids=None)
            self.dt = float(self.world.model.opt.timestep)
            if abs(.05 / self.dt - round(.05 / self.dt)) > 1e-7:
                raise ValueError('SIM timestep must exactly divide the 0.05 s acquisition quantum')
            for rid in ROBOTS:
                self.ports[rid] = CameraRobotPort(self.world, rid, allow_reverse=True, allow_mecanum=True)
        except Exception:
            self.close()
            raise

    @property
    def now(self):
        return float(self.world.data.time) if self.world is not None else 0.

    def _append(self, relative, value):
        if relative not in self.streams:
            path = self.out / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            self.streams[relative] = path.open('x', buffering=1)
        self.streams[relative].write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')

    def set_deadline(self, t):
        self.deadline = t
        self.world._final_environment_deadline = t

    def reset(self, cap):
        import mujoco
        from harness.controller_exact_speedups import install as controller_speedups
        if not hasattr(self, '_controller_speedups'):
            self._controller_speedups = controller_speedups()
        write(self.out / 'controller-speedups.json', self._controller_speedups.snapshot())
        from sim.v7_exact_speedups import write_receipt
        write_receipt(self)
        # Include the world constructor's standard 0.30 s settle in reset.
        self.set_deadline(cap)
        self.scene.setup(self.world)  # standard reset, no altered camera/GT re-stage
        elapsed = self.now
        for rid, port in self.ports.items():
            # Only issued reset commands, never measured servo positions.
            self.commands[rid] = {int(k): int(v) for k, v in self.world.robot(rid).servo_command_pulses.items()}
            self._append(f'robots/{rid}/commands.jsonl',
                         {'t': self.now, 'kind': 'initial_servo_command', 'pulses': self.commands[rid]})
            port.hold(self.now)
        (self.out / 'scene.xml').write_text(self.world.scene_xml)
        write(self.out / 'scene.json', self.scene.manifest)
        write(self.out / 'inputs/static_map.json', self.scene.config['static_map'])
        write(self.out / 'eval_only/setup.json', self.scene.config['setup_only'])
        names = [mujoco.mj_id2name(self.world.model, mujoco.mjtObj.mjOBJ_GEOM, i) or ''
                 for i in range(self.world.model.ngeom)]
        cameras = {}
        for rid in ROBOTS:
            camera = self.world.model.camera(rid + '__robot_cam')
            cameras[rid] = {'name': rid + '__robot_cam', 'fovy': float(camera.fovy[0]),
                            'size': [640, 480], 'camera_pos': camera.pos.tolist(),
                            'camera_quat': camera.quat.tolist()}
        write(self.out / 'eval_only/applied.json',
              {'robot_model': 'masterpi_v3', 'map_id': self.bundle['map_id'],
               'static_map_sha256': env.digest(self.scene.config['static_map']),
               'scene_xml_sha256': env.sha(self.out / 'scene.xml'),
               'timestep_s': self.dt, 'noslip_iterations': int(self.world.model.opt.noslip_iterations),
               'tag_geom_names': [n for n in names if 'tag' in n.lower()],
               'cameras': cameras, 'reset_sim_s': elapsed, 'reset_sim_cap_s': cap})
        return elapsed

    def issue(self, rid, action):
        # The schedule contains only pre-authored own commands. Evaluation is
        # never consulted when issuing or logging them.
        self.ports[rid].apply(action, self.now)
        if action['kind'] == 'arm':
            self.commands[rid][action['servo_id']] = action['pulse']
        elif action['kind'] == 'look':
            self.commands[rid][6] = action['pan_pulse']
        self._append(f'robots/{rid}/commands.jsonl', {'t': self.now, **action})

    def advance_to(self, t):
        if self.deadline is None or t > self.deadline + 1e-8 or t < self.now - 1e-8:
            raise ValueError('advance outside SIM deadline')
        while self.now + self.dt <= t + 1e-8:
            for port in self.ports.values():
                port.tick(self.now)
            self.world._physics_step_for(self.world.robot('r1'))
        if abs(self.now - t) > 1e-7:
            raise RuntimeError('inexact SIM advance')

    def capture(self):
        from PIL import Image
        import numpy as np
        for rid in ROBOTS:
            rgb = self.world.render_rgb(robot_id=rid, camera='robot_cam')
            if rgb.shape != (480, 640, 3) or rgb.dtype != np.uint8:
                raise ValueError('own RGB shape/type differs from bundle')
            relative = f'robots/{rid}/rgb/{self.frame:05d}.png'
            path = self.out / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(rgb).save(path)
            self._append(f'robots/{rid}/frames.jsonl', {'t': self.now, 'frame_id': self.frame,
                          'camera': 'robot_cam', 'path': relative, 'sha256': env.sha(path),
                          'commanded_servo': self.commands[rid]})
            # Teacher calibration labels. No label is returned to any provider.
            base = self.world.data.body(rid + '__robot')
            cam = self.world.data.camera(rid + '__robot_cam')
            rb = np.asarray(base.xmat).reshape(3, 3)
            self._append(f'eval_only/{rid}/camera_labels.jsonl',
                         {'t': self.now, 'frame_id': self.frame,
                          'base_position_m': base.xpos.tolist(), 'base_rotation': rb.tolist(),
                          'camera_position_m': cam.xpos.tolist(),
                          'camera_rotation': np.asarray(cam.xmat).reshape(3, 3).tolist(),
                          'load_state': 'unloaded', 'qualification': 'teacher measurement only'})
        self.frame += 1

    def eval_sample(self):
        import mujoco
        m, d = self.world.model, self.world.data
        contacts = [{'geom1': mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, int(c.geom1)),
                     'geom2': mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, int(c.geom2)),
                     'dist_m': float(c.dist)} for c in d.contact[:d.ncon]]
        welds = [int(i) for i in range(m.neq) if m.eq_type[i] == mujoco.mjtEq.mjEQ_WELD and d.eq_active[i]]
        self._append('eval_only/contacts.jsonl', {'t': self.now, 'contacts': contacts, 'active_weld_ids': welds})
        if welds:
            raise RuntimeError('WELD_OFF_VIOLATION')

    def close(self):
        try:
            if self.world is not None:
                for port in self.ports.values():
                    port.hold(self.now)
                self.world.close()
        finally:
            for stream in self.streams.values():
                stream.close()
            speedups = getattr(self, '_controller_speedups', None)
            if speedups is not None:
                try:
                    write(self.out / 'controller-speedups.json', speedups.snapshot())
                finally:
                    speedups.close()
