"""Explicit, default-off preparation adapter; no runner or policy admission."""
import copy
from harness.zone_heldout_maps import BASE_ID, CATALOG, MAP_DIR, load
from harness.zone_map_schematic import digest


def install(scene, *, heldout_map='off'):
    if heldout_map == 'off':
        return scene
    from sim.zone_final_v3_scene import FinalV3Scene
    if not isinstance(scene, FinalV3Scene) or scene.config['static_map']['map_id'] != BASE_ID:
        raise ValueError('HELDOUT_REQUIRES_BASE_FINAL_V3_SCENE')
    value = load(heldout_map)
    scene.config.update(static_map=copy.deepcopy(value), static_map_sha256=digest(value),
                        scene_version=heldout_map)
    scene._read(CATALOG)
    scene._read(MAP_DIR/(heldout_map+'.json'))
    scene._verify_camera()
    return scene
