"""v98 DEV stage-probe physics owner: v3 backend + staged spawns (TEST SETUP).

Robots spawn at the catalogue grasp stations of the case beam pose (v3
station_offset convention, as the v92 teacher stations). Everything else is
the unchanged sim.final_pair_v3 backend (floor_light_v1, weld off). The
staging record goes to eval_only/setup.json (setup_only) and the run record.
2026-10-05: host clock v2 (sim.final_pair_highpose_clock: integer substep time).
"""
from __future__ import annotations

import math
from pathlib import Path

from sim.final_pair_v3 import PhysicsBackend as V3Backend, make_scene
from sim.final_pair_highpose_clock import IntegerClock


class StagedBackend(IntegerClock, V3Backend):
    def __init__(self, bundle, out, *, seed, stations):
        from harness.zone_final_pair_clearance import require_collection_clearance
        require_collection_clearance(bundle)
        from sim.zone_final_v3_scene import build_world
        from sim.camera_robot_port import CameraRobotPort
        self.out, self.bundle = Path(out), bundle
        self.world, self.ports, self.streams = None, {}, {}
        self.frame, self.deadline, self.commands = 0, None, {}
        self.pose_sample_index, self._last_guard_xy = 0, {}
        self.scene = make_scene(bundle, seed)
        spawns = self.scene.config['setup_only']['spawns']
        for rid, (x, y, yaw) in stations.items():
            spawns[rid] = [float(x), float(y), spawns[rid][2], float(yaw)]
        self.scene.config['setup_only']['stage_probe_staging'] = {
            'stations_xyyaw': {rid: list(v) for rid, v in stations.items()},
            'qualification': 'DEV stage-probe test setup before the controller exists; not student arrival'}
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
