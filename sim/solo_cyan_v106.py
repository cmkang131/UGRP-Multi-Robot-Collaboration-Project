"""Physics owner only. Same final v3 Scene/contact/camera/clock as v98 pair.

Only capture() returns student input; evaluation reads stay write-only and
the post-run geometric judge cannot terminate or steer a controller.
"""
from __future__ import annotations

import base64
import io
import math
from pathlib import Path

from sim.final_environment_checks import PhysicsBackend as BaseBackend
from sim.final_pair_highpose_clock import IntegerClock
from scripts.run_final_environment_checks import write


def make_scene(bundle, seed):
    from sim.zone_final_v3_scene import FinalV3Scene
    from sim.zone_cargo_contact import base_profile
    from sim.render_profile import install
    from sim.final_pair_highpose_nearclip import wrap
    from harness.zone_own_contract import pickup_slots
    task = bundle['task']
    spec = {'map': bundle['map_id'], 'seed': seed, 'goal': {task['destination']: {'cyan': 1}},
            'extra_boxes': {}, 'team_cargo': []}
    scene = FinalV3Scene.from_spec(spec, base_profile(bundle['contact_profile']))
    # DEV fixture only, no mixed-cargo S1 implementation. Original robot reset
    # and randomized dock row assignment remain the standard Scene's.
    slot = pickup_slots(scene.config['static_map'])[task['pickup_slot']]
    obj = next(iter(scene.config['setup_only']['objects'].values()))
    obj['position_m'][:2] = slot['center_m']
    scene.config['setup_only']['solo_dev_fixture'] = {
        'slot': task['pickup_slot'], 'placement': 'slot centre; controller receives slot region only',
        'not_study_scenario': True}
    return wrap(install(scene, 'floor_light_v1'))


class PhysicsBackend(IntegerClock, BaseBackend):
    def __init__(self, bundle, out, *, seed):
        from sim.zone_final_v3_scene import build_world
        from sim.camera_robot_port import CameraRobotPort
        from sim.final_pair_highpose_nearclip import audit
        self.out, self.bundle = Path(out), bundle
        self.world, self.ports, self.streams = None, {}, {}
        self.frame, self.deadline, self.commands = 0, None, {}
        self.scene = make_scene(bundle, seed)
        self.eval_rows = []
        try:
            self.world = build_world(self.scene, bundle['contact_profile'], seed=seed, width=640,
                height=480, render=True, warehouse_layout=self.scene.engine_layout, warehouse_cargo_ids=None)
            self.dt = float(self.world.model.opt.timestep)
            if not math.isfinite(self.dt) or self.dt <= 0 or abs(.05/self.dt-round(.05/self.dt)) > 1e-7:
                raise ValueError('SIM timestep must divide 0.05 s')
            self.nearclip_audit = audit(self.world.model)
            self.ports = {r: CameraRobotPort(self.world, r, allow_reverse=True, allow_mecanum=True)
                          for r in ('r1', 'r2', 'r3')}
        except Exception:
            self.close()
            raise

    def reset(self, cap):
        from sim.render_profile import verify_model
        elapsed = super().reset(cap)
        write(self.out/'eval_only/render.json', verify_model(self.world.model, 'floor_light_v1'))
        write(self.out/'eval_only/render_nearclip.json', self.nearclip_audit)
        return elapsed

    def issue(self, rid, action):
        if rid != self.bundle['task']['robot_id']:
            raise ValueError('solo backend refuses commands to idle robots')
        if action['kind'] == 'hold':
            self.ports[rid].hold(self.now)
            self._append(f'robots/{rid}/commands.jsonl', {'t': self.now, **action})
        else:
            super().issue(rid, action)

    def capture(self):
        from sim.lazy_camera import capture_robot_frames
        return capture_robot_frames(self, (self.bundle['task']['robot_id'],))

    def eval_sample(self):
        super().eval_sample()  # weld OFF checked; no contact/success return channel
        from sim.zone_arena import BOX_HALF
        item = next(iter(self.scene.config['setup_only']['objects'].values()))
        body = self.world.data.body(item['body_name'])
        robot = self.world.data.body(self.bundle['task']['robot_id']+'__robot')
        row = {'t': self.now, 'cyan_xyz_m': body.xpos.tolist(), 'cyan_rotation': body.xmat.tolist(),
            'robot_xyz_m': robot.xpos.tolist(),
            'robot_yaw_rad': math.atan2(float(robot.xmat[3]), float(robot.xmat[0])),
            'box_half_m': list(BOX_HALF)}
        self.eval_rows.append(row)
        self._append('eval_only/trajectory.jsonl', row)


def evaluate(rows, static, destination):
    """Post-loop provisional geometry: whole cuboid inside zone, lifted earlier,
    floor resting/stable for the final 2 s. Never a controller observation.
    """
    import numpy as np
    region = static['regions']['zone_'+destination]
    if not rows:
        return {'status': 'NO_EVALUATION', 'success': False}
    tail = [r for r in rows if r['t'] >= rows[-1]['t']-2.-1e-8]
    lifted = any(r['cyan_xyz_m'][2] > .06 for r in rows)
    inside, floor = True, True
    for r in tail:
        centre = np.asarray(r['cyan_xyz_m'])
        extent = abs(np.asarray(r['cyan_rotation']).reshape(3, 3)) @ np.asarray(r['box_half_m'])
        inside &= bool(np.all(abs(centre[:2]-region['center_m'])+extent[:2] <= region['half_extents_m']))
        floor &= bool(abs(centre[2]-extent[2]) < .008 and centre[2] < .04)
    stable = max(math.dist(r['cyan_xyz_m'], tail[-1]['cyan_xyz_m']) for r in tail) <= .008
    duration = tail[-1]['t']-tail[0]['t']
    return {'status': 'PROVISIONAL_GEOMETRIC_JUDGE', 'success': bool(lifted and inside and floor and stable and duration >= 1.95),
        'lifted': lifted, 'inside': inside, 'floor': floor, 'stable': stable, 'settled_s': duration,
        'qualification': 'post-run DEV only; no study/physical hardware success claim'}
