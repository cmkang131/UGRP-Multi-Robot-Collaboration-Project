"""T13 setup-only Scene extension. Never imported by the student executor."""
import copy

from sim.zone_geometry_scene import GeometryCargoZoneScene
from sim.zone_cargo_scene import CARGO_SET_SCHEMA
from sim.session_scenes import ROOT
from harness.zone_target_identity import BOX_KINDS, BOX_SIZE


def box_inventory(placements):
    objects = {}
    for p in placements:
        if p['kind'] not in BOX_KINDS:
            continue
        if p['item_id'] in objects or p['pose_m'][2] != 0:
            raise ValueError('T13 box setup needs unique IDs and zero setup yaw')
        item = p['item_id']
        objects[item] = {'kind': p['kind'], 'body_name': 'cargo_'+item, 'joint_name': 'cargo_'+item+'_free',
                         'position_m': [*p['pose_m'][:2], BOX_SIZE[2]/2],
                         'half_extents_m': [d/2 for d in BOX_SIZE]}
    return objects


class TargetScene(GeometryCargoZoneScene):
    @classmethod
    def from_spec(cls, spec, contact_profile, base_dir=ROOT):
        selected = {'layout': 'zones/' + spec['map'], 'seed': spec['seed'], 'map_file': None,
                    'cargo_ids': None, 'robots': {}, 'objects': [], 'builder': None,
                    'contact_profile': contact_profile, 'cargo_contact_profile': None,
                    'params': {'goal': spec['goal'], 'extra_boxes': {},
                               'target_placements': copy.deepcopy(spec['target_placements']),
                               'cargo_set': {'schema': CARGO_SET_SCHEMA, 'items': copy.deepcopy(spec['team_cargo'])}}}
        return cls(selected, base_dir)

    def _resolve(self):
        super()._resolve()
        self.config['setup_only']['objects'] = box_inventory(self.scene['params']['target_placements'])
        self.inventory = list(self.config['setup_only']['objects'])
