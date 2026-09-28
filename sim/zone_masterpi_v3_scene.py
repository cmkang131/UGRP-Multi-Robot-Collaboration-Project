"""New, tag-free zone scene versions. Legacy Scene implementations stay frozen.

The robot model is selected by the registered map, never by a runtime override.
Construction/setup is privileged; only the static map is public robot input.
"""
from __future__ import annotations

import copy
import hashlib
import json
import xml.etree.ElementTree as ET

from sim.session_scenes import ROOT
from sim.research_dispatch_arena import digest
from sim.zone_geometry_scene import GeometryCargoZoneScene, geometry_map
from sim.masterpi_robot_models import LEGACY_SCENE_ROBOT_MODEL, v3_robot_xml_transform, ROBOT_MODEL_V3

PARENT_MAP_ID = 'zone_wide_door_geometry_v2'
MAP_IDS = ('zone_wide_door_geometry_v3', 'zone_wide_door_geometry_v3_dock_v1')
REGISTRY = ROOT / 'configs/masterpi_v3_scenes.json'


def scene_robot_model(scene):
    if isinstance(scene, MasterPiV3ZoneScene):
        name = scene.selection.split('/', 1)[1]
        if (scene.config.get('robot_model') != ROBOT_MODEL_V3
                or scene.config['static_map'] != static_map(name)):
            raise ValueError('registered v3 scene identity changed')
        return ROBOT_MODEL_V3
    if scene.config.get('robot_model', LEGACY_SCENE_ROBOT_MODEL) != LEGACY_SCENE_ROBOT_MODEL:
        raise ValueError('legacy scene versions cannot override robot_model')
    return LEGACY_SCENE_ROBOT_MODEL


def static_map(name):
    if name not in MAP_IDS:
        raise ValueError(f'unknown v3 scene: {name}')
    registry = json.loads(REGISTRY.read_text())
    entry = registry['scenes'][name]
    raw = (ROOT / entry['map_file']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry['file_sha256']:
        raise ValueError('v3 scene file hash mismatch')
    value = json.loads(raw)
    parent = geometry_map(PARENT_MAP_ID)
    if (value['robot_model'] != ROBOT_MODEL_V3 or value['map_id'] != name
            or value['parent_scene'] != {'map_id': PARENT_MAP_ID, 'sha256': digest(parent)}
            or digest(value) != entry['static_map_sha256']):
        raise ValueError('v3 scene identity mismatch')
    return value


class MasterPiV3ZoneScene(GeometryCargoZoneScene):
    def _resolve(self):
        selection = self.selection
        name = selection.split('/', 1)[1]
        static = static_map(name)
        try:
            self.selection = 'zones/' + PARENT_MAP_ID
            super()._resolve()
        finally:
            self.selection = selection
        self._read(REGISTRY)
        self._read(ROOT / 'maps/zones' / (name + '.json'))
        self.config.update(static_map=static, static_map_sha256=digest(static),
                           robot_model=ROBOT_MODEL_V3, scene_version=name)
        from sim.zone_model_conventions import apply_spawn_layout, convention
        self.config['station_convention'] = convention(self)
        apply_spawn_layout(self.config)

    def robot_transform(self, xml, *, hardware=None, calibrated_keys=()):
        """After the inherited environment/contact transform, at the host hook."""
        xml = v3_robot_xml_transform(hardware, calibrated_keys=calibrated_keys)(xml)
        world = ET.fromstring(xml).find('worldbody')
        robots = {node.get('name'): hashlib.sha256(ET.tostring(node)).hexdigest()
                  for node in world if node.tag == 'body' and str(node.get('name', '')).endswith('__robot')}
        self.manifest.update(robot_model=ROBOT_MODEL_V3, scene_version=self.selection,
                             robot_xml_sha256=robots,
                             scene_xml_sha256=hashlib.sha256(xml.encode()).hexdigest())
        return xml


def build_world(scene, profile, **kwargs):
    """Bind the existing per-instance hook to the actual template's hardware.

MultiMasterPiProductionV2 assigns physical_params/calibration_parameters before
calling xml_transform. Allocate the instance first so that the callback can
read those static construction parameters without a second template or step.
"""
    from sim.multi_masterpi_production import MultiMasterPiProductionV2
    from sim.zone_cargo_contact import CARGO_PROFILES, apply
    from sim.masterpi_model_v3 import v3_hardware
    from sim.masterpi_robot_models import V3_DRAWING_HARDWARE_KEYS

    if scene_robot_model(scene) != ROBOT_MODEL_V3:
        raise ValueError('v3 world requires a registered v3 scene')
    world = MultiMasterPiProductionV2.__new__(MultiMasterPiProductionV2)

    def transform(xml):
        xml = scene.transform(xml)
        if profile in CARGO_PROFILES:
            xml = apply(xml, profile)
        return scene.robot_transform(xml, hardware=world.physical_params,
                                     calibrated_keys=world.calibration_parameters)

    MultiMasterPiProductionV2.__init__(world, xml_transform=transform, **kwargs)
    hw = copy.deepcopy(world.physical_params)
    for key in V3_DRAWING_HARDWARE_KEYS:
        if key not in world.calibration_parameters:
            hw.pop(key, None)
    # Controllers share this dict. Publish the same drawing/calibrated values
    # that went into XML, rather than describing v3 wheels with v2 dimensions.
    world.physical_params.update(v3_hardware(hw))
    return world
