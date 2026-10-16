"""V91 owner: unchanged v88 physics/acquisition, equivalent fast abort guard."""
import math
from pathlib import Path

from sim.final_pair_v3 import PhysicsBackend as V88Backend, make_scene


from sim.final_pair_fast_guard import FastGuard


class PhysicsBackend(FastGuard, V88Backend):
    def __init__(self, bundle, out, *, seed):
        from harness.zone_final_pair_fast import require_seed
        require_seed(bundle, seed)
        from harness.zone_final_pair_fast_clearance import require_collection_clearance
        require_collection_clearance(bundle)
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
