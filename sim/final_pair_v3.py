"""Physics owner for v88; evaluation is write-only relative to students."""
from __future__ import annotations

import base64
import io
import math
from pathlib import Path

from harness import zone_final_pair_contract as contract
from harness.zone_final_pair_skill import task
from sim.final_environment_checks import PhysicsBackend as BaseBackend
from scripts.run_final_environment_checks import write


def make_scene(bundle, seed):
    from sim.zone_final_v3_scene import FinalV3Scene
    from sim.zone_arena import DEFAULT_GOAL
    from sim.zone_cargo_contact import base_profile
    from sim.render_profile import install
    static, _, _ = contract.resolve(bundle['map_id'])
    from harness.zone_final_pair_excitation import LOADED_BEAM_POSE, UNLOADED_POSE
    loaded = bundle['check'] == 'calibration-loaded'
    spec = {'map': bundle['map_id'], 'seed': seed, 'goal': DEFAULT_GOAL, 'extra_boxes': {},
            'team_cargo': [{'item_id': 'beam', 'kind': 'long_beam',
                            'pose': LOADED_BEAM_POSE if loaded else task(static)['beam_pose']}]}
    scene = FinalV3Scene.from_spec(spec, base_profile(bundle['contact_profile']))
    if bundle['check'] == 'calibration-loaded':
        from harness.zone_final_pair_calibration import teacher_stations
        staged = teacher_stations(scene.config['static_map'])
        for rid, (x, y, yaw) in staged.items():
            z = scene.config['setup_only']['spawns'][rid][2]
            scene.config['setup_only']['spawns'][rid] = [x, y, z, yaw]
        scene.config['setup_only']['teacher_measurement_stations'] = staged
    elif bundle['check'].startswith('calibration-'):
        pose = scene.config['setup_only']['spawns']['r1']
        pose[0], pose[1], pose[3] = UNLOADED_POSE
        scene.config['setup_only']['measurement_reset'] = {
            'robot_id': 'r1', 'authored_xy_yaw': UNLOADED_POSE,
            'qualification': 'empty-floor collection reset, not student arrival'}
    return install(scene, 'floor_light_v1')


class PhysicsBackend(BaseBackend):
    def __init__(self, bundle, out, *, seed):
        from sim.zone_final_v3_scene import build_world
        from sim.camera_robot_port import CameraRobotPort
        self.out, self.bundle = Path(out), bundle
        self.world, self.ports, self.streams = None, {}, {}
        self.frame, self.deadline, self.commands = 0, None, {}
        self.pose_sample_index, self._last_guard_xy = 0, {}
        self.scene = make_scene(bundle, seed)
        try:
            self.world = build_world(self.scene, bundle['contact_profile'], seed=seed, width=640,
                height=480, render=True, warehouse_layout=self.scene.engine_layout, warehouse_cargo_ids=None)
            self.dt = float(self.world.model.opt.timestep)
            if not math.isfinite(self.dt) or self.dt <= 0 or abs(.05/self.dt-round(.05/self.dt)) > 1e-7:
                raise ValueError('SIM timestep must divide 0.05 s')
            for rid in ('r1', 'r2', 'r3'):
                self.ports[rid] = CameraRobotPort(self.world, rid, allow_reverse=True, allow_mecanum=True)
        except Exception:
            self.close()
            raise

    def reset(self, cap):
        from sim.render_profile import verify_model
        from sim.camera_robot_port import CameraRobotPort
        elapsed = super().reset(cap)
        # Scene.setup issued the standard search posture through the scene
        # owner. Recreate command-only ports from those issued reset pulses.
        self.ports = {rid: CameraRobotPort(self.world, rid, allow_reverse=True, allow_mecanum=True)
                      for rid in self.ports}
        write(self.out / 'eval_only/render.json', verify_model(self.world.model, 'floor_light_v1'))
        self.collection_guard()
        return elapsed

    def issue(self, rid, action):
        self.collection_guard()
        if action['kind'] == 'hold':
            self.ports[rid].hold(self.now)
            self._append(f'robots/{rid}/commands.jsonl', {'t': self.now, **action})
            return
        return super().issue(rid, action)

    def collection_guard(self):
        """#347 abort-only interlock, full path including coast/arm/camera time.

        Actual geometry bounds cover both carriers AND the beam for loaded
        acquisition. Each substep displacement is bounded, leaving 5 cm abort
        buffer over the 30 cm wall margin. No pose is returned to a scheduler.
        Student p03/carry never consult this teacher diagnostic interlock.
        """
        if not self.bundle['check'].startswith('calibration-'):
            return
        import mujoco
        import numpy as np
        from harness.zone_final_pair_clearance import require_clearance, sphere_clearances
        from harness.zone_final_pair_excitation import design
        plan = design(self.bundle['check'])
        static = self.scene.config['static_map']
        m, d = self.world.model, self.world.data
        try:
            # Every geom sphere, including beam geometry, is checked at every
            # substep: an arm moving between the 50 ms samples cannot evade it.
            robots = contract.ROBOTS if self.bundle['check'] == 'calibration-loaded' else ('r1',)
            cached = getattr(self, '_guard_groups', None)
            if cached is None:
                names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, i) or '' for i in range(m.ngeom)]
                groups = [(rid, np.array([i for i, n in enumerate(names) if n.startswith(rid+'__')], int)) for rid in robots]
                if self.bundle['check'] == 'calibration-loaded':
                    beam_id = int(m.body('cargo_beam').id)
                    groups.append(('beam', np.array([i for i in range(m.ngeom) if int(m.geom_bodyid[i]) == beam_id], int)))
                if any(not len(ids) for _, ids in groups):
                    raise ValueError('MISSING_COLLECTION_GEOMETRY')
                self._guard_groups = (m.ngeom, groups)
            else:
                count, groups = cached
                if count != m.ngeom:
                    raise ValueError('COLLECTION_GEOMETRY_CHANGED')
            minimum = float('inf')
            for rid, ids in groups[:len(robots)]:
                xy = np.asarray(d.body(rid+'__robot').xpos[:2], float)
                minimum = min(minimum, require_clearance(static, xy, plan))
                radius = float(np.max(np.linalg.norm(d.geom_xpos[ids, :2]-xy, axis=1) + m.geom_rbound[ids]))
                if not math.isfinite(radius) or radius > plan['clearance']['robot_radius_bound_m']:
                    raise ValueError('ROBOT_ENVELOPE_BOUND_EXCEEDED')
            for name, ids in groups:
                xy = np.asarray(d.geom_xpos[ids, :2], float)
                gaps = sphere_clearances(static, xy, m.geom_rbound[ids])
                if np.any(gaps < .35-1e-10):
                    raise ValueError('CLEARANCE_ABORT: collection geometry wall margin')
                previous = self._last_guard_xy.get(name)
                if previous is not None and np.any(np.linalg.norm(xy-previous,axis=1) > plan['clearance']['max_substep_displacement_m']):
                    raise ValueError('SUBSTEP_DISPLACEMENT_BOUND_EXCEEDED')
                self._last_guard_xy[name] = xy.copy()
                minimum = min(minimum, float(gaps.min()))
            self._clearance_min = minimum
        except Exception as exc:
            for port in self.ports.values():
                port.hold(self.now)
            self._append('eval_only/clearance_abort.jsonl', {'t': self.now, 'reason': str(exc),
                         'static_map_sha256': self.bundle['map_sha256']})
            raise

    def advance_to(self, t):
        if not self.bundle['check'].startswith('calibration-'):
            return super().advance_to(t)
        if self.deadline is None or not math.isfinite(t) or not self.now-1e-8 <= t <= self.deadline+1e-8:
            raise ValueError('advance outside SIM deadline')
        while self.now+self.dt <= t+1e-8:
            self.collection_guard()
            for port in self.ports.values():
                port.tick(self.now)
            self.world._physics_step_for(self.world.robot('r1'))
            self.collection_guard()
        if abs(self.now-t) > 1e-7:
            raise RuntimeError('inexact SIM advance')

    def capture(self):
        import numpy as np
        from PIL import Image
        result = {}
        for rid in contract.ROBOTS:
            obs = self.ports[rid].capture()
            jpeg = base64.b64decode(obs['image'], validate=True)
            rgb = np.asarray(Image.open(io.BytesIO(jpeg)).convert('RGB'))
            relative = f'robots/{rid}/rgb/{self.frame:05d}.jpg'
            path = self.out / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(jpeg)
            self._append(f'robots/{rid}/frames.jsonl', {**{k:v for k,v in obs.items() if k != 'image'},
                'path': relative, 'commanded_servo': self.commands[rid]})
            base = self.world.data.body(rid+'__robot')
            cam = self.world.data.camera(rid+'__robot_cam')
            rb = np.asarray(base.xmat).reshape(3, 3)
            from harness.zone_final_pair_camera import measurement_label
            label = measurement_label(base.xpos, rb, cam.xpos, np.asarray(cam.xmat).reshape(3, 3))
            # Actual extrinsics and joints are teacher labels only. They never
            # enter obs/actuator_state or a student calibration at runtime.
            self._append(f'eval_only/{rid}/camera_labels.jsonl', {
                't': self.now, 'frame_id': obs['frame_id'], 'sha256': obs['sha256'],
                'commanded_servo': self.commands[rid], **label, 'base_position_m': base.xpos.tolist(),
                'base_rotation': rb.tolist(), 'requested_check': self.bundle['check'],
                'load_validity': 'UNCLASSIFIED; inspect contacts and beam trajectory offline'})
            result[rid] = (obs, rgb)
        self.frame += 1
        return result

    def eval_sample(self):
        super().eval_sample()
        self.collection_guard()
        beam = self.world.data.body('cargo_beam')
        self._append('eval_only/trajectory.jsonl', {'t': self.now,
            'beam_xyz_m': beam.xpos.tolist(), 'beam_rotation': beam.xmat.tolist(),
            'qpos': self.world.data.qpos.tolist(), 'qvel': self.world.data.qvel.tolist(),
            'physical_success': None})
        if self.bundle['check'].startswith('calibration-'):
            import numpy as np
            for rid in contract.ROBOTS:
                body = self.world.data.body(rid+'__robot')
                self._append(f'eval_only/{rid}/pose.jsonl', {
                    't': self.now, 'sample_index': self.pose_sample_index,
                    'base_position_m': body.xpos.tolist(),
                    'base_rotation': np.asarray(body.xmat).reshape(3, 3).tolist(),
                    'wall_clearance_lower_bound_m': self._clearance_min,
                    'requested_check': self.bundle['check'],
                    'qualification': 'eval_only; loaded validity must be judged offline'})
            self.pose_sample_index += 1
