"""Scene-fit patch: default off, exact opt-in, v6 pickup paint only (CPU, no simulator)."""
import hashlib
import sys
import types
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import act18_scene_fit as F  # noqa: E402

XML = ("<mujoco><worldbody><geom name='floor' type='plane' size='5 5 .1'/>"
       "<geom name='zone_pickup' type='box' pos='0.7 -0.85 0.001' size='1.15 1.95 0.001' "
       "rgba='.12 .36 .70 .14' contype='0' conaffinity='0'/></worldbody></mujoco>")


def fake_contrast():
    module = types.SimpleNamespace(__file__='fake/scene_contrast_v5.py', calls=[])

    def install(scene, name, *, extension=False):
        module.calls.append((name, extension))
        inner = scene.transform
        scene.transform = lambda xml: inner(xml)
        return scene
    module.install = install
    return module


def test_default_off_and_exact_value():
    assert F.requested({}) is False
    assert F.requested({F.ENV: ''}) is False
    assert F.requested({F.ENV: F.MODE}) is True
    with pytest.raises(ValueError):
        F.requested({F.ENV: 'on'})
    assert F.install_if_requested({}) is None


def test_neutral_module_is_byte_copy():
    assert hashlib.sha256(F.NEUTRAL_PATH.read_bytes()).hexdigest() == F.NEUTRAL_SHA256


def test_apply_xml_replaces_overlay_with_neutral_tiles():
    after, record = F.apply_xml(XML)
    root = ET.fromstring(after)
    names = [g.get('name') for g in root.iter('geom')]
    assert 'zone_pickup' not in names and 'floor' in names
    tiles = [g for g in root.iter('geom') if g.get('name', '').startswith('zone_pickup_tile_')]
    assert len(tiles) == 60 == record['tiles']
    for g in tiles:
        r, gr, b, a = (float(v) for v in g.get('rgba').split())
        assert r == gr == b and a == 1.0                       # saturation 0
        assert g.get('contype') == g.get('conaffinity') == '0'  # no physics contact
    assert record['changes_physics'] is False


def test_apply_xml_fails_closed_without_overlay():
    with pytest.raises(ValueError, match='NEUTRAL_PICKUP_OVERLAY_MISSING'):
        F.apply_xml("<mujoco><worldbody><geom name='floor'/></worldbody></mujoco>")


def test_install_wraps_v5_only_and_records_manifest():
    contrast = F.install(fake_contrast())
    assert F.install(contrast) is contrast             # idempotent
    scene = types.SimpleNamespace(transform=lambda xml: xml, manifest={})
    scene = contrast.install(scene, F.BASE_SCENE, extension=True)
    out = scene.transform(XML)
    assert 'zone_pickup_tile_0_0' in out
    rec = scene.manifest['act18_scene_fit']
    assert rec['mode'] == F.MODE and rec['appearance_equivalent_to'] == F.TARGET_SCENE
    assert rec['scene_xml_sha256_before_fit'] != rec['scene_xml_sha256_after_fit']
    with pytest.raises(ValueError):
        contrast.install(types.SimpleNamespace(transform=lambda x: x, manifest={}), 'other_scene')
