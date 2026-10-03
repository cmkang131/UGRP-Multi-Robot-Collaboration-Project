"""V94 shared physics owner; rendering is the only precheck/collection switch."""
import math
from pathlib import Path

from sim.final_pair_v3 import PhysicsBackend as V88Backend, make_scene as parent_scene


import numpy as np
from sim.final_pair_fast_guard import FastGuard, WallArrays, require_envelope
from harness import zone_final_pair_new_starts as heldout


def make_scene(bundle, seed):
    heldout.validate_bundle(bundle)
    scene = parent_scene(bundle, seed)
    for rid, (x, y, yaw) in bundle['start_xy_yaw'].items():
        z = scene.config['setup_only']['spawns'][rid][2]
        scene.config['setup_only']['spawns'][rid] = [x, y, z, yaw]
    scene.config['setup_only']['measurement_reset'] = {
        'authored_xy_yaw': bundle['start_xy_yaw'],
        'qualification': 'v94 teacher-only new starts; not student arrival'}
    return scene


class PhysicsBackend(FastGuard, V88Backend):
    def __init__(self, bundle, out, *, seed, render=True):
        from harness.zone_final_pair_new_starts import require_seed
        require_seed(bundle, seed)
        from harness.zone_final_pair_new_starts import require_collection_clearance
        require_collection_clearance(bundle)
        from sim.zone_final_v3_scene import build_world
        from sim.camera_robot_port import CameraRobotPort
        self.out, self.bundle = Path(out), bundle
        self.render_enabled = render
        self.minimum_wall_clearance_m = dict.fromkeys(heldout.ROBOTS, float("inf"))
        self.world, self.ports, self.streams = None, {}, {}
        self.frame, self.deadline, self.commands = 0, None, {}
        self.pose_sample_index, self._last_guard_xy = 0, {}
        self.scene = make_scene(bundle, seed)
        try:
            self.world = build_world(self.scene, bundle['contact_profile'], seed=seed, width=640,
                height=480, render=render, warehouse_layout=self.scene.engine_layout, warehouse_cargo_ids=None)
            self.dt = float(self.world.model.opt.timestep)
            if not math.isfinite(self.dt) or self.dt <= 0 or abs(.05/self.dt-round(.05/self.dt)) > 1e-7:
                raise ValueError('SIM timestep must divide 0.05 s')
            for rid in ('r1', 'r2', 'r3'):
                self.ports[rid] = CameraRobotPort(self.world, rid, allow_reverse=True, allow_mecanum=True)
        except Exception:
            self.close()
            raise

    def collection_guard(self):
        import mujoco
        from harness import zone_final_pair_contract as contract
        from harness.zone_final_pair_new_starts import design

        m, d = self.world.model, self.world.data
        try:
            if not hasattr(self, '_fast_plan'):
                self._fast_plan = design(self.bundle['check'], self.bundle['map_id'])
                self._fast_walls = WallArrays(self.scene.config['static_map'])
            plan, walls = self._fast_plan, self._fast_walls
            robots = heldout.ROBOTS
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
                minimum = min(minimum, walls.require_clearance(xy, plan))
                require_envelope(d.geom_xpos[ids], m.geom_rbound[ids], xy,
                                 plan['clearance']['robot_radius_bound_m'])
            for name, ids in groups:
                xyz = np.asarray(d.geom_xpos[ids], float)
                gaps = walls.sphere_clearances(xyz, m.geom_rbound[ids])
                xy = xyz[:, :2]
                if np.any(gaps < .35-1e-10):
                    raise ValueError('CLEARANCE_ABORT: collection geometry wall margin')
                previous = self._last_guard_xy.get(name)
                if previous is not None and np.any(np.linalg.norm(xy-previous, axis=1) > plan['clearance']['max_substep_displacement_m']):
                    raise ValueError('SUBSTEP_DISPLACEMENT_BOUND_EXCEEDED')
                self._last_guard_xy[name] = xy.copy()
                minimum = min(minimum, float(gaps.min()))
                self.minimum_wall_clearance_m[name] = min(self.minimum_wall_clearance_m[name], float(gaps.min()), walls.require_clearance(d.body(name+'__robot').xpos[:2], plan))
            self._clearance_min = minimum
        except Exception as exc:
            for port in self.ports.values():
                port.hold(self.now)
            self._append('eval_only/clearance_abort.jsonl', {'t': self.now, 'reason': str(exc),
                         'static_map_sha256': self.bundle['map_sha256']})
            raise

    def capture(self):
        if not self.render_enabled:
            raise RuntimeError('HEADLESS_PRECHECK_MUST_NOT_CAPTURE')
        return super().capture()

    def kinematic_sample(self):
        self.collection_guard()
        for rid in heldout.ROBOTS:
            body = self.world.data.body(rid+'__robot')
            self._append(f'eval_only/{rid}/pose.jsonl', {
                't': self.now, 'base_position_m': body.xpos.tolist(),
                'base_rotation': np.asarray(body.xmat).reshape(3, 3).tolist()})
