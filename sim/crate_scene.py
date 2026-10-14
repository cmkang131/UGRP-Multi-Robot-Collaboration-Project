"""Heavy-crate demo scene: ``grasp_act_scene`` plus optional lug colours (toggle, default off).

``crate_lug_colors_v1`` paints the west lug teal and the east lug blue (RGBA only, no
geometry, mass, contact or camera change). Without it both lugs are the same black and a
robot cannot tell, from its own RGB, which lug its ``west``/``east`` ticket means. This is
the crate analogue of the beam end colours; the user's allowance (2026-10-14) names beam
ends, so extending it to crate lugs is a coordinator decision awaiting user confirmation.
Colour runs are a separate scene version and are not pooled with black-lug runs.
"""
from __future__ import annotations
import hashlib
import xml.etree.ElementTree as ET
from sim.grasp_act_scene import make_scene

OFF = 'off'
LUG_COLORS_V1 = 'crate_lug_colors_v1'
LUG_RGBA = {'west': (.02, .95, .60, 1.), 'east': (.02, .02, .95, 1.)}


def paint_lugs(xml, item_id, option):
    if option == OFF:
        return xml
    if option != LUG_COLORS_V1:
        raise ValueError('unknown lug appearance profile')
    tree = ET.fromstring(xml)
    for side, rgba in LUG_RGBA.items():
        found = tree.findall(f".//geom[@name='cargo_{item_id}__lug_{side}']")
        if len(found) != 1:
            raise ValueError('one original crate lug required')
        found[0].set('rgba', ' '.join(map(str, rgba)))
    return ET.tostring(tree, encoding='unicode')


def make_crate_scene(plan):
    option = plan.get('lug_color_scene', OFF)
    # the parent scene builder only knows the beam colour option; keep it off here
    scene = make_scene({**plan, 'end_color_scene': OFF})
    inner = scene.robot_transform

    def transform(xml, **kwargs):
        before = inner(xml, **kwargs)
        after = paint_lugs(before, plan['target_item'], option)
        scene.manifest['crate_scene'] = {
            'version': 'crate_scene_v1', 'lug_colors': option,
            'parent_xml_sha256': hashlib.sha256(before.encode()).hexdigest(),
            'scene_xml_sha256': hashlib.sha256(after.encode()).hexdigest(),
            'cargo_scene_version': plan.get('cargo_scene_version', 'catalogue_v1'),
            'appearance_only': 'crate lug RGBA; the mass comes from cargo_scene_version (sim/cargo_scene_version.py)'}
        return after
    scene.robot_transform = transform
    return scene
