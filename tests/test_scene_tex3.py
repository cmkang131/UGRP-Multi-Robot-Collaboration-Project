"""Pure sampling tests: no simulator import, GL context or Mac rendering."""
import cv2
import numpy as np
import pytest
from sim import camera_render_quality as q


def test_native_is_existing_remap_exactly():
    from sim.masterpi_camera_profile import raw_fisheye_remap
    rgb = np.random.default_rng(3).integers(0, 256, (480, 640, 3), dtype=np.uint8)
    expected = cv2.remap(rgb, *raw_fisheye_remap(640, 480), cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT)
    assert np.array_equal(q.sampling_stages(rgb, 'native')['final'], expected)


def test_supersampling_preserves_sensor_size_and_label_domain():
    image = np.full((960, 1280, 3), 127, np.uint8)
    out = q.sampling_stages(image, 'ss2_area_v1')
    assert out['final'].shape == (480, 640, 3)
    ids = np.zeros((960, 1280), np.int32)
    ids[:, 640:] = 37
    labels = q.remap_ids(ids, 'ss2_area_v1')
    assert labels.shape == (480, 640)
    assert set(np.unique(labels)) <= {-1, 0, 37}
    with pytest.raises(ValueError):
        q.sampling_stages(image, 'native')


def test_profile_requires_explicit_known_name():
    with pytest.raises(ValueError):
        q.resolve(None)
    assert q.resolve('native').scale == 1


def test_surface_measurements_are_json_serializable():
    import json
    from scripts.probe_scene_tex3 import measure
    image = np.random.default_rng(6).integers(0, 256, (96, 128, 3), dtype=np.uint8)
    masks = {'floor': np.ones((96, 128), bool), 'wall': np.zeros((96, 128), bool)}
    result = measure(image, masks)
    json.dumps(result, allow_nan=False)
    assert result['floor']['orb20'] > 0
    assert result['wall']['laplacian_variance'] is None


def test_v3_materials_leave_scene_physics_and_camera_xml_unchanged():
    import xml.etree.ElementTree as ET
    from tests.test_natural_scene_texture import scene_xml
    from scripts.generate_scene_textures import MAPS
    from sim.render_profile_selection import for_name
    profile = for_name('walls_floor_textured_v3')
    for path in MAPS:
        before = ET.fromstring(profile.apply_xml(scene_xml(path), 'floor_light_v1'))
        after = ET.fromstring(profile.apply_xml(scene_xml(path), 'walls_floor_textured_v3'))
        for a, b in zip(before.find('worldbody').iter(), after.find('worldbody').iter()):
            aa, bb = dict(a.attrib), dict(b.attrib)
            if a.get('name', '').startswith('zone_wall_'):
                for key in ('rgba', 'material'):
                    aa.pop(key, None)
                    bb.pop(key, None)
            assert (a.tag, aa) == (b.tag, bb)
        for tag in ('option', 'actuator'):
            assert ET.tostring(before.find(tag)) == ET.tostring(after.find(tag))


def test_v3_png_integrity_and_no_nominal_colour_range_intrusion():
    from PIL import Image
    from sim import natural_scene_texture_v3 as t
    record = t.manifest()
    for key in record['images']:
        rgb = np.asarray(Image.open(t.checked_file(key, record, t.ASSETS)).convert('RGB'))
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        if key == 'floor':
            from sim import natural_scene_texture as v1
            assert t.checked_file(key, record, t.ASSETS).read_bytes() == v1.checked_file('floor', v1.manifest(), v1.ASSETS).read_bytes()
            continue
        assert hsv[..., 1].max() < 20
        assert hsv[..., 2].min() > .38*255
        assert hsv[..., 2].max() <= 180
