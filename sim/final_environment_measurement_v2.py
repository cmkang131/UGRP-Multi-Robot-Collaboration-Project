"""Physics-owner acquisition only; imported after source/lock/output admission.

The diagnostic interlock may ONLY abort the run, never re-plan/recenter or
correct a command. No evaluation/pose is returned to the fixed scheduler or
to a student. Not a robot controller and not an admissible student GT channel.
"""
from __future__ import annotations

import math
from pathlib import Path
import xml.etree.ElementTree as ET

from harness import final_environment_measurement_v2 as env
from scripts.run_final_environment_checks import ROBOTS, write
from sim.final_environment_checks import PhysicsBackend as PreviousBackend
from sim.zone_final_v3_scene import FinalV3Scene
from sim import render_profile


class MeasurementScene(FinalV3Scene):
    """One authored empty-floor reset; no runtime relocation or teacher path."""
    def _resolve(self):
        super()._resolve()
        plan = env.protocol()
        if self.config['static_map']['map_id'] != plan['map_id']:
            raise ValueError('motion v2 requires its single registered map')
        pose = self.config['setup_only']['spawns']['r1']
        pose[0], pose[1], pose[3] = plan['spawn_xy_yaw']
        self.config['setup_only']['measurement_reset'] = {
            'id': env.BUNDLE_ID, 'robot_id': 'r1', 'authored_xy_yaw': plan['spawn_xy_yaw'],
            'qualification': 'diagnostic staging, not student arrival'}

    def transform(self, xml):
        xml = super().transform(xml)
        root = ET.fromstring(xml)
        body = root.find("worldbody/body[@name='r1__robot']")
        if body is None:
            raise ValueError('missing r1 reset body')
        pose = self.config['setup_only']['spawns']['r1']
        body.set('pos', ' '.join(map(str, pose[:3])))
        body.set('quat', '1 0 0 0')
        self.manifest['measurement_reset'] = self.config['setup_only']['measurement_reset']
        return ET.tostring(root, encoding='unicode')


class PhysicsBackend(PreviousBackend):
    def __init__(self, bundle, out, *, seed):
        # Direct callers must pass the same preflight as the managed runner,
        # before importing/building a world or opening a renderer.
        env.validate(bundle['measurement'])
        from sim.zone_final_v3_scene import build_world
        from sim.zone_arena import DEFAULT_GOAL
        from sim.zone_cargo_contact import base_profile
        from sim.camera_robot_port import CameraRobotPort

        if bundle != env.bundle():
            raise ValueError('measurement bundle differs from registered source')
        self.out, self.bundle, self.plan = Path(out), bundle, bundle['measurement']
        self.world, self.ports, self.streams = None, {}, {}
        self.frame, self.deadline, self.pose_sample_index = 0, None, 0
        self.commands, self._last_guard_xy = {}, None
        self.scene = MeasurementScene.from_spec({'map': bundle['map_id'], 'seed': seed,
                                                'goal': DEFAULT_GOAL, 'extra_boxes': {}, 'team_cargo': []},
                                               base_profile(bundle['contact_profile']))
        self.scene = render_profile.install(self.scene, 'floor_light_v1')
        try:
            self.world = build_world(self.scene, bundle['contact_profile'], seed=seed,
                                     width=640, height=480, render=True,
                                     warehouse_layout=self.scene.engine_layout, warehouse_cargo_ids=None)
            self.render_audit = render_profile.verify_model(self.world.model, 'floor_light_v1')
            self.dt = float(self.world.model.opt.timestep)
            if not math.isfinite(self.dt) or self.dt <= 0 or abs(.05 / self.dt - round(.05 / self.dt)) > 1e-7:
                raise ValueError('timestep must divide 0.05 s')
            for rid in ROBOTS:
                self.ports[rid] = CameraRobotPort(self.world, rid, allow_reverse=True, allow_mecanum=True)
        except Exception:
            self.close()
            raise

    def reset(self, cap):
        elapsed = super().reset(cap)
        self.guard(check_geometry=True)  # no excitation before clearance admission
        path = self.out / 'eval_only/applied.json'
        applied = env.read(path)
        applied.update(render_profile=render_profile.profile_record('floor_light_v1'),
                       render_profile_applied=self.render_audit, measurement_sha256=self.bundle['measurement_sha256'],
                       eval_pose_period_s=.05, clearance_interlock='physics-owner abort only; no correction')
        write(path, applied)
        return elapsed

    def guard(self, *, check_geometry=False):
        """Private abort-only wall interlock; no pose crosses this capability."""
        import mujoco
        import numpy as np
        m, d = self.world.model, self.world.data
        base = d.body('r1__robot')
        xy = np.asarray(base.xpos[:2], float)
        try:
            gap = env.require_clearance(self.scene.config['static_map'], xy, self.plan)
            # Verify the assumed disc against every actual r1 geom bounding
            # sphere, including the empty arm. Missing geometry fails closed.
            if check_geometry:
                ids = [i for i in range(m.ngeom) if (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, i) or '').startswith('r1__')]
                if not ids:
                    raise ValueError('MISSING_ROBOT_GEOMETRY')
                for i in ids:
                    envelope = env.geometry_envelope(d.geom_xpos[i], m.geom_rbound[i], xy)
                    if envelope > self.plan['clearance']['robot_radius_bound_m']:
                        raise ValueError('ROBOT_ENVELOPE_BOUND_EXCEEDED')
            if self._last_guard_xy is not None and np.linalg.norm(xy - self._last_guard_xy) > self.plan['clearance']['max_substep_displacement_m']:
                raise ValueError('SUBSTEP_DISPLACEMENT_BOUND_EXCEEDED')
            self._last_guard_xy = xy.copy()
            return gap
        except Exception as exc:
            for port in self.ports.values():
                port.hold(self.now)
            self._append('eval_only/clearance_abort.jsonl', {'t': self.now, 'reason': str(exc),
                         'base_xy_m': [float(v) if math.isfinite(v) else None for v in xy],
                         'static_map_sha256': self.bundle['map_sha256']})
            raise

    def issue(self, rid, action):
        if rid != 'r1' or action.get('kind') != 'mecanum' or action.get('turn') != 0:
            raise ValueError('motion-v2 admits only r1 translational commands')
        self.guard()
        return super().issue(rid, action)

    def advance_to(self, t):
        if self.deadline is None or not math.isfinite(t) or t > self.deadline + 1e-8 or t < self.now - 1e-8:
            raise ValueError('advance outside SIM deadline')
        while self.now + self.dt <= t + 1e-8:
            self.guard()
            for port in self.ports.values():
                port.tick(self.now)
            self.world._physics_step_for(self.world.robot('r1'))
            self.guard()
        if abs(self.now - t) > 1e-7:
            raise RuntimeError('inexact SIM advance')

    def eval_sample(self):
        import numpy as np
        super().eval_sample()
        gap = self.guard(check_geometry=True)
        base = self.world.data.body('r1__robot')
        self._append('eval_only/r1/pose.jsonl', {'t': self.now, 'sample_index': self.pose_sample_index,
                     'base_position_m': base.xpos.tolist(),
                     'base_rotation': np.asarray(base.xmat).reshape(3, 3).tolist(),
                     'wall_clearance_lower_bound_m': gap, 'load_state': 'unloaded',
                     'qualification': 'teacher measurement only; no scheduler observation'})
        self.pose_sample_index += 1
