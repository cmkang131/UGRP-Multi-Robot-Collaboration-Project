"""Physics owner for v88; evaluation is write-only relative to students."""
from __future__ import annotations

import base64
import io
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
    spec = {'map': bundle['map_id'], 'seed': seed, 'goal': DEFAULT_GOAL, 'extra_boxes': {},
            'team_cargo': [{'item_id': 'beam', 'kind': 'long_beam', 'pose': task(static)['beam_pose']}]}
    scene = FinalV3Scene.from_spec(spec, base_profile(bundle['contact_profile']))
    if bundle['check'] == 'calibration-loaded':
        from harness.zone_final_pair_calibration import teacher_stations
        staged = teacher_stations(scene.config['static_map'])
        for rid, (x, y, yaw) in staged.items():
            z = scene.config['setup_only']['spawns'][rid][2]
            scene.config['setup_only']['spawns'][rid] = [x, y, z, yaw]
        scene.config['setup_only']['teacher_measurement_stations'] = staged
    return install(scene, 'floor_light_v1')


class PhysicsBackend(BaseBackend):
    def __init__(self, bundle, out, *, seed):
        from sim.zone_final_v3_scene import build_world
        from sim.camera_robot_port import CameraRobotPort
        self.out, self.bundle = Path(out), bundle
        self.world, self.ports, self.streams = None, {}, {}
        self.frame, self.deadline, self.commands = 0, None, {}
        self.scene = make_scene(bundle, seed)
        try:
            self.world = build_world(self.scene, bundle['contact_profile'], seed=seed, width=640,
                height=480, render=True, warehouse_layout=self.scene.engine_layout, warehouse_cargo_ids=None)
            self.dt = float(self.world.model.opt.timestep)
            if abs(.05/self.dt-round(.05/self.dt)) > 1e-7:
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
        return elapsed

    def issue(self, rid, action):
        if action['kind'] == 'hold':
            self.ports[rid].hold(self.now)
            self._append(f'robots/{rid}/commands.jsonl', {'t': self.now, **action})
            return
        return super().issue(rid, action)

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
            rotation = rb.T @ np.asarray(cam.xmat).reshape(3, 3) @ np.diag([1., -1., -1.])
            origin = rb.T @ (np.asarray(cam.xpos)-base.xpos)
            # Actual extrinsics and joints are teacher labels only. They never
            # enter obs/actuator_state or a student calibration at runtime.
            self._append(f'eval_only/{rid}/camera_labels.jsonl', {
                't': self.now, 'frame_id': obs['frame_id'], 'sha256': obs['sha256'],
                'commanded_servo': self.commands[rid], 'origin_m': origin.tolist(),
                'rotation': rotation.tolist(), 'base_position_m': base.xpos.tolist(),
                'base_rotation': rb.tolist(), 'requested_check': self.bundle['check'],
                'load_validity': 'UNCLASSIFIED; inspect contacts and beam trajectory offline'})
            result[rid] = (obs, rgb)
        self.frame += 1
        return result

    def eval_sample(self):
        super().eval_sample()
        beam = self.world.data.body('cargo_beam')
        self._append('eval_only/trajectory.jsonl', {'t': self.now,
            'beam_xyz_m': beam.xpos.tolist(), 'beam_rotation': beam.xmat.tolist(),
            'qpos': self.world.data.qpos.tolist(), 'qvel': self.world.data.qvel.tolist(),
            'physical_success': None})
