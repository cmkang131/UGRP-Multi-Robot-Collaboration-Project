"""Physics-owner acquisition for the v101 unloaded gain calibration; imported after source/slot/output admission.

Extends the v89 measurement backend (same scene, abort-only wall interlock, 0.05 s pose log) with a per-run spawn
(position AND yaw), turn commands, and an abort check that r2/r3/cargo are far from every bounded path. The interlock
may ONLY abort the run, never re-plan or correct a command. No pose returns to the fixed command table.
"""
from __future__ import annotations

import math
from pathlib import Path
import xml.etree.ElementTree as ET

from harness import final_environment_gain_calibration_v101 as env
from scripts.run_final_environment_checks import ROBOTS
from sim.final_environment_measurement_v2 import PhysicsBackend as MeasurementBackend
from sim.zone_final_v3_scene import FinalV3Scene
from sim import render_profile


def make_scene_class(run):
    spawn = list(run['spawn_xy_yaw'])

    class GainScene(FinalV3Scene):
        """One authored empty-floor reset with the run's spawn; no runtime relocation or teacher path."""
        def _resolve(self):
            super()._resolve()
            if self.config['static_map']['map_id'] != env.MAP_ID:
                raise ValueError('gain calibration requires its single registered map')
            pose = self.config['setup_only']['spawns']['r1']
            pose[0], pose[1], pose[3] = spawn
            self.config['setup_only']['measurement_reset'] = {
                'id': env.BUNDLE_ID, 'run_id': run['id'], 'robot_id': 'r1', 'authored_xy_yaw': spawn,
                'qualification': 'diagnostic staging, not student arrival'}

        def transform(self, xml):
            xml = super().transform(xml)
            root = ET.fromstring(xml)
            body = root.find("worldbody/body[@name='r1__robot']")
            if body is None:
                raise ValueError('missing r1 reset body')
            pose = self.config['setup_only']['spawns']['r1']
            body.set('pos', ' '.join(map(str, pose[:3])))
            body.set('quat', f'{math.cos(spawn[2] / 2)} 0 0 {math.sin(spawn[2] / 2)}')
            self.manifest['measurement_reset'] = self.config['setup_only']['measurement_reset']
            return ET.tostring(root, encoding='unicode')

    return GainScene


class PhysicsBackend(MeasurementBackend):
    def __init__(self, bundle, out, *, seed):
        # Same preflight as the managed runner, before any world/renderer exists.
        plan = bundle['measurement']
        run = env.run_row(plan, bundle['run_id'])
        env.validate(plan)
        from sim.zone_final_v3_scene import build_world
        from sim.zone_arena import DEFAULT_GOAL
        from sim.zone_cargo_contact import base_profile
        from sim.camera_robot_port import CameraRobotPort

        if bundle != env.bundle(bundle['run_id']):
            raise ValueError('gain calibration bundle differs from registered source')
        if seed != run['seed']:
            raise ValueError('seed differs from the registered run seed')
        self.out, self.bundle, self.plan, self.run = Path(out), bundle, plan, run
        self.world, self.ports, self.streams = None, {}, {}
        self.frame, self.deadline, self.pose_sample_index = 0, None, 0
        self.commands, self._last_guard_xy = {}, None
        self.scene = make_scene_class(run).from_spec(
            {'map': bundle['map_id'], 'seed': seed, 'goal': DEFAULT_GOAL, 'extra_boxes': {}, 'team_cargo': []},
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
        # r2/r3/cargo must be outside every bounded corner path (east room is empty); abort before any excitation.
        margin = env.other_objects_clear(self.scene.config['setup_only'], self.run, self.plan)
        if margin < .5:
            raise ValueError(f'OTHER_OBJECTS_TOO_CLOSE: {margin:.3f} m')
        return super().reset(cap)

    def issue(self, rid, action):
        if rid != 'r1' or action.get('kind') != 'mecanum':
            raise ValueError('gain calibration admits only r1 mecanum commands')
        self.guard()
        return super(MeasurementBackend, self).issue(rid, action)
