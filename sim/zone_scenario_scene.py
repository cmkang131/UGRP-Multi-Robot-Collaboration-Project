"""Privileged v4 setup loader on the standard final-v3 Scene, without a World.

Exact poses are authored scenario data, never controller inputs. Legacy Scene
factories, random box placement and pair-only placeholder removal are unchanged.
"""
from __future__ import annotations

import copy
import hashlib
import json

from harness import zone_environment_registry as registry
from harness import zone_final_environment as final_v3
from sim.session_scenes import ROOT
from sim.zone_arena import BOX_HALF, COLORS, DEFAULT_GOAL
from sim.zone_cargo_scene import CARGO_SET_SCHEMA
from sim.zone_final_v3_scene import FinalV3Scene

DEV_CONFIG = 'configs/zone_study_dev/dev_s1lite.json'


def load_scenario(scenario):
    if scenario == 'dev_s1lite':
        return json.loads((ROOT / DEV_CONFIG).read_text())
    return registry.load_scenario(scenario) if isinstance(scenario, str) else copy.deepcopy(scenario)


def scene_spec(scenario, seed):
    """Validate static map/hash/slots/clearance, then derive private initialization."""
    scenario = load_scenario(scenario)
    if scenario['scenario_id'] == 'e2e_one_beam_ownmap':
        from harness.e2e_environment import MAP_ID
        if scenario['map_id'] != MAP_ID:
            raise ValueError('E2E_NEW_MAP_REQUIRED')
    static, _, _ = final_v3.resolve(scenario['map_id'])
    report = registry.validate(scenario)
    if not report.ok:
        raise ValueError(f'invalid scenario setup: {report.problems}')
    setup = scenario['eval']['setup']
    if (setup['weld'] != 'off' or setup['contact_profile'] != 'cargo_noslip_v1'
            or (setup['robot_spawns'] != 'arena_default' and scenario['scenario_id'] != 'e2e_one_beam_ownmap')):
        raise ValueError('scenario scene requires cargo_noslip_v1, weld off and arena_default')
    # ZoneScene reset uses the production box's identity quaternion. Refuse
    # unsupported colour yaw rather than silently resetting an authored rotation.
    boxes = [p for p in setup['placements'] if p['kind'] in COLORS]
    if any(p['pose_m'][2] != 0. for p in boxes):
        raise ValueError('scenario colour boxes require zero setup yaw')
    goal = {}
    for order in scenario['orders']:
        if order['kind'] in COLORS:
            kinds = goal.setdefault(order['destination_zone'], {})
            kinds[order['kind']] = kinds.get(order['kind'], 0) + order['count']
    return {'map': static['map_id'], 'robot_model': 'masterpi_v3',
            'static_map_sha256': final_v3.digest(static), 'seed': seed,
            'goal': goal or copy.deepcopy(DEFAULT_GOAL), 'extra_boxes': {},
            'contact_profile': setup['contact_profile'],
            'colour_boxes': copy.deepcopy(boxes),
            'team_cargo': [{'item_id': p['item_id'], 'kind': p['kind'], 'pose': list(p['pose_m'])}
                           for p in setup['placements'] if p['kind'] not in COLORS]}


class ScenarioFinalV3Scene(FinalV3Scene):
    """Add explicit colour inventory after the inherited pair-only resolver."""

    @classmethod
    def from_scenario(cls, scenario, seed, *, base_dir=ROOT):
        source = scenario if isinstance(scenario, str) else None
        scenario = load_scenario(scenario)
        spec = scene_spec(scenario, seed)
        selected = {'layout': 'zones/' + spec['map'], 'seed': seed, 'map_file': None,
                    'cargo_ids': None, 'robots': {}, 'objects': [], 'builder': None,
                    'contact_profile': spec['contact_profile'], 'cargo_contact_profile': None,
                    'params': {'goal': spec['goal'], 'extra_boxes': {},
                               'cargo_set': {'schema': CARGO_SET_SCHEMA, 'items': spec['team_cargo']},
                               'scenario_setup': scenario}}
        scene = cls(selected, base_dir)
        scene.spec = spec
        if source:
            path = (ROOT / 'configs/zone_study_dev/e2e_one_beam_ownmap.json' if source == 'e2e_one_beam_ownmap' else
                    ROOT / DEV_CONFIG if source == 'dev_s1lite' else
                    registry.ROOT / 'configs' / 'zone_study_scenarios_v4' / (source + '.json'))
            scene._read(path)
        return scene

    def _resolve(self):
        # This class is only for explicit scenario setup, never inherited from_spec.
        scenario = self.scene['params']['scenario_setup']
        spec = scene_spec(scenario, self.scene['seed'])
        if self.selection != 'zones/' + spec['map']:
            raise ValueError('scenario scene map mismatch')
        super()._resolve()
        objects = {}
        for p in spec['colour_boxes']:
            item_id = p['item_id']
            objects[item_id] = {'kind': p['kind'], 'body_name': 'cargo_' + item_id,
                                'joint_name': 'cargo_' + item_id + '_free',
                                'position_m': [*p['pose_m'][:2], BOX_HALF[2]],
                                'half_extents_m': list(BOX_HALF)}
        if scenario['scenario_id'] == 'e2e_one_beam_ownmap':
            spawns = scenario['eval']['setup']['robot_spawns']
            import math
            if (not isinstance(spawns, dict) or set(spawns) != {'r1','r2','r3'}
                    or any(not isinstance(p, list) or len(p) != 4
                           or any(type(v) not in (int,float) or not math.isfinite(v) for v in p)
                           for p in spawns.values())):
                raise ValueError('E2E_EXPLICIT_INITIAL_SPAWNS_REQUIRED')
            self.config['setup_only']['spawns'] = copy.deepcopy(spawns)
        self.config['setup_only']['objects'] = objects
        self.config['setup_only']['scenario'] = {
            'scenario_id': scenario['scenario_id'], 'config_sha256': final_v3.digest(scenario),
            'map_file_sha256': scenario['eval']['setup']['map_file_sha256']}
        self.inventory = list(objects) + [c.item_id for c in self.cargo]

    def transform(self, xml):
        xml = super().transform(xml)
        # CargoZoneScene records the profile only through cargo_contact_profile;
        # the scenario explicitly requests it through the standard zone hook.
        self.manifest['scenario_setup'] = copy.deepcopy(self.config['setup_only']['scenario'])
        self.manifest['scene_xml_sha256'] = hashlib.sha256(xml.encode()).hexdigest()
        return xml
