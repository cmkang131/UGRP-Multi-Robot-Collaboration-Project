"""Physics owner for the v104 loaded rest calibration: v92 loaded owner with a per-run beam pose (position and yaw).

Same world builder, contact profile (cargo_noslip_v1), render profile (floor_light_v1), v91 abort-only guard and 0.05 s
pose log as v92. The ONLY changes: the beam and carrier stations come from the run's registered ``beam_xy_yaw``, and
no camera frame is captured. The guard may only abort; no pose returns to the command table.
"""
import math
from pathlib import Path

from harness import final_pair_loaded_rest_v104 as env
from sim.final_pair_fast_guard import FastGuard
from sim.final_pair_v3 import PhysicsBackend as V88Backend


def make_scene(bundle, run, seed):
    from harness import zone_final_pair_contract as contract
    from sim.render_profile import install
    from sim.zone_arena import DEFAULT_GOAL
    from sim.zone_cargo_contact import base_profile
    from sim.zone_final_v3_scene import FinalV3Scene
    spec = {'map': bundle['map_id'], 'seed': seed, 'goal': DEFAULT_GOAL, 'extra_boxes': {},
            'team_cargo': [{'item_id': 'beam', 'kind': 'long_beam', 'pose': list(run['beam_xy_yaw'])}]}
    scene = FinalV3Scene.from_spec(spec, base_profile(bundle['contact_profile']))
    staged = env.stations(run['beam_xy_yaw'])
    for rid, (x, y, yaw) in staged.items():
        z = scene.config['setup_only']['spawns'][rid][2]
        scene.config['setup_only']['spawns'][rid] = [x, y, z, yaw]
    scene.config['setup_only']['teacher_measurement_stations'] = staged
    if contract.resolve(bundle['map_id'])[0] != scene.config['static_map']:
        raise ValueError('scene static map differs from the registered map')
    return install(scene, 'floor_light_v1')


class PhysicsBackend(FastGuard, V88Backend):
    def __init__(self, bundle, out, *, seed):
        plan = bundle['measurement']
        env.validate(plan)
        run = env.run_row(plan, bundle['run_id'])
        if bundle['execution_bundle_id'] != env.BUNDLE_ID or bundle['check'] != env.CHECK or seed != run['seed']:
            raise ValueError('wrong loaded rest bundle or seed')
        from sim.zone_final_v3_scene import build_world
        from sim.camera_robot_port import CameraRobotPort
        self.out, self.bundle, self.run = Path(out), bundle, run
        self.world, self.ports, self.streams = None, {}, {}
        self.frame, self.deadline, self.commands = 0, None, {}
        self.pose_sample_index, self._last_guard_xy = 0, {}
        self.scene = make_scene(bundle, run, seed)
        try:
            self.world = build_world(self.scene, bundle['contact_profile'], seed=seed, width=640, height=480,
                                     render=True, warehouse_layout=self.scene.engine_layout, warehouse_cargo_ids=None)
            self.dt = float(self.world.model.opt.timestep)
            if not math.isfinite(self.dt) or self.dt <= 0 or abs(.05 / self.dt - round(.05 / self.dt)) > 1e-7:
                raise ValueError('SIM timestep must divide 0.05 s')
            for rid in ('r1', 'r2', 'r3'):
                self.ports[rid] = CameraRobotPort(self.world, rid, allow_reverse=True, allow_mecanum=True)
        except Exception:
            self.close()
            raise
