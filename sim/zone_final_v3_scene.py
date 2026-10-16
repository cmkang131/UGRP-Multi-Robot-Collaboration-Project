"""Final v3 maps through the standard Scene reset/contact/robot XML hooks."""
from __future__ import annotations

import copy

from harness import zone_final_environment as env
from sim.zone_geometry_scene import GeometryCargoZoneScene
from sim.zone_cargo_scene import CargoZoneScene
from sim.zone_model_conventions import apply_spawn_layout, convention
from sim.zone_masterpi_v3_scene import MasterPiV3ZoneScene


class FinalV3Scene(GeometryCargoZoneScene):
    def _resolve(self):
        selected = self.selection
        static, entry, _ = env.resolve(selected.split('/', 1)[1])
        try:
            self.selection = 'zones/' + static['base_map']['map_id']
            CargoZoneScene._resolve(self)
        finally:
            self.selection = selected
        if env.digest(self.config['static_map']) != static['base_map']['static_map_sha256']:
            raise ValueError('final v3 base map hash mismatch')
        self.config.update(static_map=static, static_map_sha256=env.digest(static),
                           robot_model='masterpi_v3', scene_version=static['map_id'])
        self.config['station_convention'] = convention(self)
        apply_spawn_layout(self.config)
        if self.cargo:
            self.config['setup_only']['objects'] = {}
            self.inventory = []
        for rel in (env.REGISTRY, entry['file'], entry['parent_file'], entry['calibration_contract']):
            self._read(env.ROOT / rel)
        self.bounds = static['bounds_m']
        self._verify_camera()

    # Reuse the existing, per-instance v3 body replacement and XML receipts.
    robot_transform = MasterPiV3ZoneScene.robot_transform


def cap_world_steps(world, cap_s):
    """Install before engine construction, including its initial 0.30 s reset."""
    world._final_environment_deadline = float(cap_s)
    step = world._physics_step_for

    def limited_step(*args, **kwargs):
        if float(world.data.time) + float(world.model.opt.timestep) > world._final_environment_deadline + 1e-8:
            raise RuntimeError('SIM_CAP_EXCEEDED')
        return step(*args, **kwargs)

    world._physics_step_for = limited_step


def build_world(scene, profile, *, initial_sim_cap_s=5., **kwargs):
    """Same standard v3 construction hook, explicit new-map admission.

    Kept outside frozen zone_masterpi_v3_scene: its allow-list and historical
    bundles continue to mean exactly the same thing.
    """
    if not isinstance(scene, FinalV3Scene):
        raise ValueError('final v3 world requires FinalV3Scene')
    expected, _, _ = env.resolve(scene.selection.split('/', 1)[1])
    if scene.config['static_map'] != expected or scene.config['robot_model'] != 'masterpi_v3':
        raise ValueError('final v3 world scene identity mismatch')
    from sim.multi_masterpi_production import MultiMasterPiProductionV2
    from sim.zone_cargo_contact import apply
    from sim.masterpi_model_v3 import v3_hardware
    from sim.masterpi_robot_models import V3_DRAWING_HARDWARE_KEYS
    if profile != 'cargo_noslip_v1':
        raise ValueError('final v3 check requires cargo_noslip_v1')
    world = MultiMasterPiProductionV2.__new__(MultiMasterPiProductionV2)
    cap_world_steps(world, initial_sim_cap_s)

    def transform(xml):
        xml = apply(scene.transform(xml), profile)
        return scene.robot_transform(xml, hardware=world.physical_params,
                                     calibrated_keys=world.calibration_parameters)

    try:
        MultiMasterPiProductionV2.__init__(world, xml_transform=transform, **kwargs)
        hardware = copy.deepcopy(world.physical_params)
        for key in V3_DRAWING_HARDWARE_KEYS:
            if key not in world.calibration_parameters:
                hardware.pop(key, None)
        world.physical_params.update(v3_hardware(hardware))
        return world
    except Exception:
        # The engine constructor owns its partially initialized resources.
        # On a completed constructor we can close through the normal owner.
        if hasattr(world, 'controllers') and hasattr(world, 'renderer'):
            world.close()
        raise
