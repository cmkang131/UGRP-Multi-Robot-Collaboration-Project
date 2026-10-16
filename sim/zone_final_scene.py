"""Standard Scene extension for final two-door/corridor maps; legacy source frozen."""
from harness.zone_environment_registry import REGISTRY_FILE, environment_entry, resolve_static_map, static_map_path
from sim.session_scenes import ROOT
from sim.research_dispatch_arena import digest
from sim.zone_cargo_scene import CargoZoneScene
from sim.zone_geometry_scene import GeometryCargoZoneScene


class FinalGeometryCargoZoneScene(GeometryCargoZoneScene):
    def _resolve(self):
        selected = self.selection
        name = selected.split('/', 1)[1]
        static, _ = resolve_static_map(name, robot_model='masterpi_v2')
        self._read(ROOT / REGISTRY_FILE)
        self._read(ROOT / environment_entry(name)['catalog_file'])
        self._read(static_map_path(name))
        try:
            self.selection = 'zones/' + static['base_map']['map_id']
            # Reuse standard base scene/cargo reset; do not alter the frozen
            # door-only GeometryCargoZoneScene resolver or its default behavior.
            CargoZoneScene._resolve(self)
        finally:
            self.selection = selected
        if digest(self.config['static_map']) != static['base_map']['static_map_sha256']:
            raise ValueError('final scene base map hash mismatch')
        self.config.update(static_map=static, static_map_sha256=digest(static))
        if self.cargo:
            self.config['setup_only']['objects'] = {}
            self.inventory = []
        self.bounds = static['bounds_m']
        self._verify_camera()
