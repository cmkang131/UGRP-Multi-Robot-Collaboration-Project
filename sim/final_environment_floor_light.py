"""v87 physics owner; same v84 schedule/scene, explicit audited render change."""
from pathlib import Path

from harness import zone_final_environment_floor_light as env
from scripts.run_final_environment_checks import ROBOTS, write
from sim.final_environment_checks import PhysicsBackend as PreviousBackend
from sim import render_profile


class PhysicsBackend(PreviousBackend):
    def __init__(self, bundle, out, *, seed):
        from sim.zone_final_v3_scene import FinalV3Scene, build_world
        from sim.zone_arena import DEFAULT_GOAL
        from sim.zone_cargo_contact import base_profile
        from sim.camera_robot_port import CameraRobotPort

        if (bundle['execution_bundle_id'] != env.BUNDLE_ID
                or bundle['render_profile'] != env.RENDER_PROFILE
                or bundle['render_profile_contract'] != render_profile.profile_record(env.RENDER_PROFILE)):
            raise ValueError('v87 requires the registered floor_light_v1 render profile')
        self.out, self.bundle = Path(out), bundle
        self.world, self.ports, self.streams = None, {}, {}
        self.frame, self.deadline = 0, None
        self.commands = {}
        spec = {'map': bundle['map_id'], 'seed': seed, 'goal': DEFAULT_GOAL,
                'extra_boxes': {}, 'team_cargo': []}
        self.scene = FinalV3Scene.from_spec(spec, base_profile(bundle['contact_profile']))
        self.scene = render_profile.install(self.scene, env.RENDER_PROFILE)
        try:
            self.world = build_world(self.scene, bundle['contact_profile'], seed=seed,
                                     width=640, height=480, render=True,
                                     warehouse_layout=self.scene.engine_layout, warehouse_cargo_ids=None)
            self.render_audit = render_profile.verify_model(self.world.model, env.RENDER_PROFILE)
            self.dt = float(self.world.model.opt.timestep)
            if abs(.05 / self.dt - round(.05 / self.dt)) > 1e-7:
                raise ValueError('SIM timestep must exactly divide the 0.05 s acquisition quantum')
            for rid in ROBOTS:
                self.ports[rid] = CameraRobotPort(self.world, rid, allow_reverse=True, allow_mecanum=True)
        except Exception:
            self.close()
            raise

    def reset(self, cap):
        elapsed = super().reset(cap)
        path = self.out / 'eval_only/applied.json'
        applied = env.read(path)
        applied['render_profile'] = render_profile.profile_record(env.RENDER_PROFILE)
        applied['render_profile_applied'] = self.render_audit
        write(path, applied)
        return elapsed
