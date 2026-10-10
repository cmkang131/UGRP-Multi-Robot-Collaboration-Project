"""egomap15 physical acquisition with an isolated, opt-in visual dressing."""
from pathlib import Path

from sim import wall_parallax_strafe as previous
from sim.wall_texture import transform_xml


def make_scene(bundle, seed):
    scene = previous.make_scene(bundle, seed)
    original = scene.transform
    profile = bundle.get('options', {}).get('wall_texture', 'off')
    scene.transform = lambda xml: transform_xml(original(xml), wall_texture=profile)
    return scene


class PhysicsBackend(previous.PhysicsBackend):
    # Only scene construction differs. Ports, reset, camera binding, capture,
    # stepping, no-weld checks and abort-only evaluation are inherited unchanged.
    def __init__(self, bundle, out, *, seed):
        self.out, self.bundle = Path(out), bundle
        self.world, self.ports, self.streams = None, {}, {}
        self.frame, self.deadline, self.commands = 0, None, {}
        self.eval_rows = []
        self.scene = make_scene(bundle, seed)
        try:
            self.world = previous.build_world(self.scene, drive_profile='masterpi_drive_friction_v7',
                roller_collision='mesh', idle_robot_contacts='off', seed=seed, width=640, height=480,
                render=True, warehouse_layout=self.scene.engine_layout, warehouse_cargo_ids=None)
            with self.world.physics_lock:
                for controller in self.world.controllers.values():
                    previous.bind_camera(controller)
            self.dt = float(self.world.model.opt.timestep)
            assert abs(.05 / self.dt - round(.05 / self.dt)) < 1e-7
            self.nearclip_audit = previous.audit(self.world.model)
            self._ports()
        except Exception:
            self.close()
            raise
