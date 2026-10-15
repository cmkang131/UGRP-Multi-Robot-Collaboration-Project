"""XML-only regression: camera, contact geometry, v1 floor and legacy pins."""
import xml.etree.ElementTree as ET
import pytest
from sim import scene_contrast_v4 as v4
from sim.render_profile_selection import for_name
from scripts.generate_scene_textures import MAPS
from tests.test_natural_scene_texture import scene_xml


@pytest.mark.parametrize('name', list(v4.PROFILES))
@pytest.mark.parametrize('map_path', MAPS, ids=lambda p: p.stem)
def test_only_wall_materials_change(name, map_path):
    before = ET.fromstring(for_name('floor_light_textured_v1').apply_xml(scene_xml(map_path), 'floor_light_textured_v1'))
    after = ET.fromstring(for_name(name).apply_xml(scene_xml(map_path), name))
    a, b = list(before.find('worldbody').iter()), list(after.find('worldbody').iter())
    assert len(a) == len(b)
    for x, y in zip(a, b):
        aa, bb = dict(x.attrib), dict(y.attrib)
        if x.get('name', '').startswith('zone_wall_'):
            for key in ('material', 'rgba'):
                aa.pop(key, None); bb.pop(key, None)
        assert (x.tag, aa) == (y.tag, bb)
    for tag in ('option', 'actuator', 'compiler'):
        assert ET.tostring(before.find(tag)) == ET.tostring(after.find(tag))
    for tag in ('texture', 'material'):
        key = 'ground' if tag == 'texture' else 'groundmat'
        assert ET.tostring(before.find(f'asset/{tag}[@name="{key}"]')) == ET.tostring(after.find(f'asset/{tag}[@name="{key}"]'))


def test_new_profile_is_explicit_and_nearclip_compatible():
    from sim.final_pair_highpose_nearclip import wrap
    assert for_name(None).resolve(None) is None
    with pytest.raises(ValueError): v4.resolve(None)
    class Scene:
        def transform(self, xml):
            self.manifest = {}
            return xml
    name = next(iter(v4.PROFILES))
    scene = wrap(for_name(name).install(Scene(), name))
    scene.transform(scene_xml())
    assert scene.manifest['render_profile']['default'] == 'off'
    assert scene.manifest['render_nearclip']['base_profile'] == name
