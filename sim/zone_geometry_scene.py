"""Versioned geometry-only Scene using the standard cargo/zone transforms."""
import copy
import json
from sim.session_scenes import ROOT
from sim.zone_cargo_scene import CargoZoneScene, CARGO_SET_SCHEMA
from sim.research_dispatch_arena import digest

MAP_IDS = ('zone_wide_door_geometry_v2',)


def geometry_map(name, root=ROOT):
    if name not in MAP_IDS:
        raise ValueError(f'unknown geometry map: {name}')
    return json.loads((root / 'maps/zones' / (name + '.json')).read_text())


class GeometryCargoZoneScene(CargoZoneScene):
    @classmethod
    def from_spec(cls, spec, contact_profile, base_dir=ROOT):
        selected = {'layout': 'zones/' + spec['map'], 'seed': spec['seed'], 'map_file': None,
                    'cargo_ids': None, 'robots': {}, 'objects': [], 'builder': None,
                    'contact_profile': contact_profile, 'cargo_contact_profile': None,
                    'params': {'goal': spec['goal'], 'extra_boxes': spec.get('extra_boxes', {}),
                               'cargo_set': {'schema': CARGO_SET_SCHEMA, 'items': copy.deepcopy(spec.get('team_cargo', []))}}}
        return cls(selected, base_dir)

    def _resolve(self):
        selected = self.selection
        name = selected.split('/', 1)[1]
        static = geometry_map(name)
        self._read(ROOT / 'maps/zones' / (name + '.json'))
        try:
            self.selection = 'zones/' + static['base_map']['map_id']
            super()._resolve()
        finally:
            self.selection = selected
        if digest(self.config['static_map']) != static['base_map']['static_map_sha256']:
            raise ValueError('geometry scene base map hash mismatch')
        self.config.update(static_map=static, static_map_sha256=digest(static))
        if self.cargo:
            # Pair-only task: same setup-only placeholder removal as the pair runner.
            self.config['setup_only']['objects'] = {}
            self.inventory = []
        self.bounds = static['bounds_m']
        self._verify_camera()

    def transform(self, xml):
        xml = super().transform(xml)
        self.manifest['geometry_map_id'] = self.config['static_map']['map_id']
        self.manifest['wall_profile'] = copy.deepcopy(self.config['static_map'].get('wall_profile'))
        return xml
