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
    if not v4.PROFILES[name]['skirting_m'] and not v4.PROFILES[name].get('v1_tint'):
        expected = [c/255 for c in v4.PROFILES[name]['rgb']]+[1.]
        for geom in after.findall('worldbody/geom'):
            if geom.get('name', '').startswith('zone_wall_'):
                assert list(map(float, geom.get('rgba').split())) == expected


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


def test_tinted_wall_assets_keep_v1_nominal_gray_and_floor_is_not_rewritten():
    import hashlib
    import json
    import cv2
    import numpy as np
    from PIL import Image
    record = json.loads((v4.LUMA_ASSETS/'manifest.json').read_text())
    assert hashlib.sha256((v4.LUMA_ASSETS/'manifest.json').read_bytes()).hexdigest() == v4.LUMA_MANIFEST_SHA256
    for key, r in record['images'].items():
        p = v4.LUMA_ASSETS/r['file']
        assert hashlib.sha256(p.read_bytes()).hexdigest() == r['sha256']
        before = np.asarray(Image.open(v4.v1.checked_file(key, v4.v1.manifest(), v4.v1.ASSETS)))
        after = np.asarray(Image.open(p))
        assert np.array_equal(cv2.cvtColor(before, cv2.COLOR_RGB2GRAY), cv2.cvtColor(after, cv2.COLOR_RGB2GRAY))
        assert cv2.cvtColor(after, cv2.COLOR_RGB2HSV)[..., 1].max() < 20
    assert 'floor' not in record['images']
