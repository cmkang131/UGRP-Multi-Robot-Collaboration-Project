"""Pure setup inventory adapter for the opt-in P02 geometry scene; no World."""
import copy

from harness.zone_mixed_jobs import validate_contract, validate_inventory
from harness.zone_study_contract import ContractViolation
from sim.zone_geometry_scene import GeometryCargoZoneScene
from sim.session_scenes import ROOT
from sim.zone_cargo_scene import CARGO_SET_SCHEMA


class MixedGeometryCargoZoneScene(GeometryCargoZoneScene):
    """Opt-in standard Scene adapter; the pinned legacy scene stays unchanged."""
    @classmethod
    def from_spec(cls, spec, contact_profile, base_dir=ROOT):
        validate_contract(spec['mixed_jobs'])
        if spec['map'] != spec['mixed_jobs']['map_id']:
            raise ContractViolation('mixed scene map mismatch')
        selected = {'layout': 'zones/' + spec['map'], 'seed': spec['seed'], 'map_file': None,
                    'cargo_ids': None, 'robots': {}, 'objects': [], 'builder': None,
                    'contact_profile': contact_profile, 'cargo_contact_profile': None,
                    'params': {'goal': copy.deepcopy(spec['goal']), 'extra_boxes': copy.deepcopy(spec['extra_boxes']),
                               'mixed_jobs': copy.deepcopy(spec['mixed_jobs']),
                               'cargo_set': {'schema': CARGO_SET_SCHEMA, 'items': copy.deepcopy(spec['team_cargo'])}}}
        return cls(selected, base_dir)

    def _resolve(self):
        super()._resolve()
        # The legacy pair Scene intentionally removes all colour placeholders.
        # Recreate the same static prototype inventory from its declared seed
        # and goal; no World is built or queried here.
        from sim.zone_arena import episode
        params = self.scene['params']
        base = episode(self.config['variant'], self.scene['seed'], goal=params['goal'],
                       extra_boxes=params['extra_boxes'])
        objects, self.inventory = prepare_inventory(base['setup_only']['objects'],
                                                   self.config['cargo_set']['items'], params['mixed_jobs'])
        self.config['setup_only']['objects'] = objects
        self.config['mixed_jobs'] = copy.deepcopy(params['mixed_jobs'])


def prepare_inventory(objects, cargo, contract):
    validate_contract(contract)
    validate_inventory(contract, cargo, cargo_only=True)
    if len(objects) != 1 or next(iter(objects.values()))['kind'] != 'cyan':
        raise ContractViolation('mixed scene requires one cyan prototype inventory')
    p = next(p for p in contract['setup_placements'] if p['kind'] == 'cyan')
    if p['pose_m'][2] != 0.:
        raise ContractViolation('UNSUPPORTED_CYAN_SETUP_YAW')
    item = copy.deepcopy(next(iter(objects.values())))
    item.update(body_name='cargo_' + p['item_id'], joint_name='cargo_' + p['item_id'] + '_free',
                position_m=[*p['pose_m'][:2], item['position_m'][2]])
    result = {p['item_id']: item}
    validate_inventory(contract, [{'item_id': p['item_id'], 'kind': 'cyan', 'pose_m': p['pose_m']}, *cargo])
    return result, [p['item_id']]


def check_scene_inventory(objects, cargo, contract):
    """Check the actual prepared config, including an injected Scene, before World creation."""
    validate_contract(contract)
    rows = [{'item_id': item, 'kind': o['kind'], 'pose_m': [*o['position_m'][:2], 0.]}
            for item, o in objects.items()]
    validate_inventory(contract, [*rows, *cargo])
