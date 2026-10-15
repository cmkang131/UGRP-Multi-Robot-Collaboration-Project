"""PNG/XML-only regression; import hook forbids simulator use in the subprocess."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import cv2
import numpy as np
from PIL import Image
import pytest

from sim import natural_scene_texture_v2 as texture
from sim.render_profile_selection import for_name
from scripts.generate_scene_textures import MAPS
from tests.test_natural_scene_texture import scene_xml

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('map_path', MAPS, ids=lambda p: p.stem)
def test_v2_changes_only_visual_materials(map_path):
    rp = for_name(texture.PROFILE)
    before = ET.fromstring(rp.apply_xml(scene_xml(map_path), 'floor_light_v1'))
    after = ET.fromstring(rp.apply_xml(scene_xml(map_path), texture.PROFILE))
    assert len(list(before.iter('geom'))) == len(list(after.iter('geom')))
    for a, b in zip(before.find('worldbody').iter(), after.find('worldbody').iter()):
        aa, bb = dict(a.attrib), dict(b.attrib)
        if a.get('name', '').startswith('zone_wall_'):
            for k in ('rgba', 'material'):
                aa.pop(k, None)
                bb.pop(k, None)
        assert (a.tag, aa) == (b.tag, bb)
    for tag in ('option', 'actuator'):
        assert ET.tostring(before.find(tag)) == ET.tostring(after.find(tag))
    assert after.find('compiler').get('texturedir') == texture.TEXTURE_DIR.as_posix()
    # Per-face PNGs describe a complete unit-box face. True scales the cube
    # direction by thin wall dimensions and selects other faces across it.
    assert all(m.get('texuniform') == 'false' for m in after.findall('asset/material')
               if m.get('name', '').startswith('natural_v2_'))


def test_pinned_pixels_and_nominal_surface_classes():
    from harness.scene_tex2_perception import surface_masks
    m = texture.manifest()
    hashes = set()
    for key, row in m['images'].items():
        rgb = np.asarray(Image.open(texture.checked_file(key, m, texture.ASSETS)))
        assert row['sha256'] not in hashes
        hashes.add(row['sha256'])
        kind = 'floor' if key == 'floor' else 'walls'
        masks = surface_masks(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), texture.PROFILE)
        assert masks[kind].all()
        assert not masks['walls' if kind == 'floor' else 'floor'].any()
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        assert hsv[..., 1].max() < 20
        assert hsv[..., 2].min() > .38*255
        assert hsv[..., 2].max() <= 180


def test_refuse_profile_mixing_and_corruption(tmp_path):
    rp = for_name(texture.PROFILE)
    out = rp.apply_xml(scene_xml(), texture.PROFILE)
    with pytest.raises(ValueError, match='another wall dressing'):
        rp.apply_xml(out, texture.PROFILE)
    (tmp_path/'manifest.json').write_text('{}')
    with pytest.raises(ValueError, match='manifest hash'):
        texture.manifest(tmp_path)
    from harness.scene_tex2_perception import surface_masks
    with pytest.raises(ValueError, match='explicit render profile'):
        surface_masks(np.zeros((8, 8, 3), np.uint8), 'floor_light_v1')


def test_texture_selection_and_png_paths_never_import_mujoco():
    source = """
import importlib.abc, sys, runpy
class Forbid(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] == 'mujoco':
            raise AssertionError('Mac offline path imported simulator')
sys.meta_path.insert(0, Forbid())
from sim.render_profile_selection import for_name
from harness.scene_tex2_perception import surface_masks
from scripts.audit_scene_tex2 import measure_palette
import numpy as np
ns=runpy.run_path('tests/test_natural_scene_texture.py')
for_name('walls_floor_textured_v2').apply_xml(ns['scene_xml'](),'walls_floor_textured_v2')
surface_masks(np.zeros((8,8,3),np.uint8),'walls_floor_textured_v2')
"""
    r = subprocess.run([sys.executable, '-c', source], cwd=ROOT, text=True, capture_output=True)
    assert r.returncode == 0, r.stderr


def test_v1_definition_and_xml_hashes_are_unchanged():
    rp = for_name('floor_light_textured_v1')
    assert rp.profile_sha256('floor_light_textured_v1') == '45f268ab22c9c198132eef78716d614b8ee49457279b84f31b84836d765d55a3'
    xml = rp.apply_xml(scene_xml(), 'floor_light_textured_v1')
    assert hashlib.sha256(xml.encode()).hexdigest() == '7464e7901905c48ee97c0f5afcd452fcf27437da10693c2a7d5a549ff30f0aa6'


def test_nearclip_records_v2_parent():
    from sim.final_pair_highpose_nearclip import wrap
    class Scene:
        def transform(self, xml):
            self.manifest = {}
            return xml
    scene = wrap(for_name(texture.PROFILE).install(Scene(), texture.PROFILE))
    scene.transform(scene_xml())
    assert scene.manifest['render_nearclip']['base_profile'] == texture.PROFILE


def test_v2_adapter_rejects_internal_texture_edges():
    from types import SimpleNamespace
    from harness.scene_tex2_perception import detect_boundaries
    # Two geometric candidates: a dark speckle transition inside the wall and
    # the actual wall/floor boundary. The broad variance bound alone accepts
    # both; the material transition must eliminate the internal one.
    class Probe:
        DEFAULT_DETECTOR = {'window_px': 3}
        @staticmethod
        def detect_boundaries(image, camera, params):
            return SimpleNamespace(columns=np.array([10]), vb=np.array([[8., 19.]]),
                                   vt=np.array([[2., 2.]]))
    image = np.full((32, 32, 3), 125, np.uint8)
    image[20:] = 160
    result = detect_boundaries(Probe, image, None, profile=texture.PROFILE)
    assert np.isnan(result.vb[0, 0])
    assert result.vb[0, 1] == 19.
