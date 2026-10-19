"""Start-area floor neutralization for the nav gate; no MuJoCo model or render.

The nav gate's own-RGB view showed the shared map's pickup overlay as an
opaque indigo floor (OpenCV H 107-108, S median 212, V median 90) only 2-6 hue
units from zone B paint (110-114).  The scene profile
``walls_floor_contrast_v6_indigo110_s80_neutral_start`` replaces that overlay
with neutral grey tiles (S == 0) and keeps the base light scale (0.30); zone B
paint and every map file stay unchanged.  These tests check the authored paint,
not a rendered frame: V values are predictions and the GPU gate frame is the
evidence.
"""
import copy
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
import pytest

from sim import neutral_pickup_floor as neutral
from sim import scene_contrast_v5 as contrast
from sim.zone_arena import build_zone_xml
from sim.zone_environment_scene_provider import scenario_scene

ROOT = Path(__file__).resolve().parents[1]
OLD = 'walls_floor_contrast_v5_indigo110_s80'
NEW = 'walls_floor_contrast_v6_indigo110_s80_neutral_start'
MAP = ROOT / 'maps/zones_final_v3/zone_wide_two_doors_final_v3.json'
MAP_SHA = 'b6a61f7e748b995f13800aa0e4c3a0ec4a50dcd152fc75815225115d0354a41b'
RECORDED_FRAME = ROOT / 'experiments/2026-10-18-nav-gate-1/raw/r1-tick5.jpg'


def synthetic_xml():
    source = ET.fromstring(
        '<mujoco><worldbody>'
        '<geom name="floor" type="plane" size="8 8 .1" pos="0 0 0"/>'
        '<geom name="zone_pickup" type="box" pos=".7 -.85 .0006" size="1.15 1.95 .0005" '
        'rgba=".12 .36 .70 .14" contype="0" conaffinity="0" group="0" mass="0"/>'
        '<geom name="zone_zone_B" type="box" pos="4.6 -2.1 .0006" size=".3 .7 .0005" '
        'rgba=".20 .40 .95 .30" contype="0" conaffinity="0" group="0" mass="0"/>'
        '</worldbody></mujoco>')
    return source


def opencv_hsv(rgba):
    """Authored linear rgba -> OpenCV H/S/V (the units the detector uses)."""
    linear = np.asarray([float(v) for v in rgba.split()[:3]])
    srgb = np.where(linear <= 0.0031308, 12.92*linear, 1.055*np.power(linear, 1/2.4) - 0.055)
    rgb8 = np.clip(np.rint(srgb*255), 0, 255).astype(np.uint8).reshape(1, 1, 3)
    return [float(v) for v in cv2.cvtColor(rgb8, cv2.COLOR_RGB2HSV)[0, 0]]


def in_zone_b_band(h, s, v, *, lo=110., hi=114., sat=100., vlo=30., vhi=110.):
    return lo <= h <= hi and s >= sat and vlo <= v <= vhi


def zone_b_geoms(xml):
    return [g for g in ET.fromstring(xml).iter('geom') if g.get('name') == 'zone_zone_B']


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for name in ('mujoco', 'torch', 'sim.multi_masterpi_production'):
        monkeypatch.setitem(sys.modules, name, None)


def test_neutral_pickup_replaces_overlay_and_keeps_zone_b():
    root = synthetic_xml()
    before_zone_b = copy.deepcopy(
        [g.attrib for g in root.iter('geom') if g.get('name') == 'zone_zone_B'])
    source = root.find("worldbody/geom[@name='zone_pickup']")
    assert source is not None and source.get('rgba') == neutral.SOURCE_RGBA
    record = neutral.apply_root(root)

    assert root.find("worldbody/geom[@name='zone_pickup']") is None
    tiles = [g for g in root.iter('geom') if (g.get('name') or '').startswith('zone_pickup_tile_')]
    assert len(tiles) == neutral.TILES == 60
    assert record == neutral.record()
    # Every tile is an exact grey (R == G == B) and opaque: no S>=100 pixel can exist.
    for tile in tiles:
        channels = [float(v) for v in tile.get('rgba').split()[:3]]
        assert channels[0] == channels[1] == channels[2]
        assert float(tile.get('rgba').split()[3]) == 1.
        assert tile.get('contype') == '0' and tile.get('conaffinity') == '0' and tile.get('mass') == '0'
        assert float(tile.get('pos').split()[2]) == pytest.approx(.0006)
    # Tile area exactly covers the authored pickup rectangle and stays inside it.
    half_x, half_y = 1.15/6, 1.95/10
    assert len(tiles)*4*half_x*half_y == pytest.approx(2*1.15*2*1.95)
    for tile in tiles:
        x, y = [float(v) for v in tile.get('pos').split()[:2]]
        assert -0.45 - 1e-9 <= x - half_x and x + half_x <= 1.85 + 1e-9
        assert -2.8 - 1e-9 <= y - half_y and y + half_y <= 1.1 + 1e-9
    # Three neutral tone levels keep corners/edges as feature points.
    levels = {tile.get('rgba').split()[0] for tile in tiles}
    assert len(levels) == len(neutral.PALETTE_LINEAR) == 3
    # Zone B paint is bit-identical to the map's authored paint.
    assert [g.attrib for g in root.iter('geom') if g.get('name') == 'zone_zone_B'] == before_zone_b
    assert before_zone_b[0]['rgba'] == '.20 .40 .95 .30'


def test_missing_overlay_fails_closed_with_the_named_error():
    """No silent blue-floor fallback when a map loses the pickup overlay."""
    root = ET.fromstring(
        '<mujoco><worldbody>'
        '<geom name="floor" type="plane" size="8 8 .1" pos="0 0 0"/>'
        '</worldbody></mujoco>')
    before = ET.tostring(root, encoding='unicode')
    with pytest.raises(ValueError) as excinfo:
        neutral.apply_root(root)
    assert str(excinfo.value) == 'NEUTRAL_PICKUP_OVERLAY_MISSING: zone_pickup'
    assert ET.tostring(root, encoding='unicode') == before  # nothing was painted


def test_changed_overlay_rgba_fails_closed_with_the_named_error():
    """A map rgba edit must stop the profile, not repaint an unknown overlay."""
    root = synthetic_xml()
    source = root.find("worldbody/geom[@name='zone_pickup']")
    source.set('rgba', '.12 .36 .70 .20')
    before = ET.tostring(root, encoding='unicode')
    with pytest.raises(ValueError) as excinfo:
        neutral.apply_root(root)
    assert str(excinfo.value) == "NEUTRAL_PICKUP_OVERLAY_RGBA_CHANGED: '.12 .36 .70 .20'"
    assert ET.tostring(root, encoding='unicode') == before  # source kept, no tiles added


def test_start_paint_is_outside_the_zone_b_hue_band_while_zone_b_stays_blue():
    old_h, old_s, old_v = opencv_hsv(neutral.SOURCE_RGBA)
    # The removed overlay sits 2-6 units below zone B's hue and is saturated.
    assert 100. <= old_h <= 120. and old_s >= 100.
    assert not in_zone_b_band(old_h, old_s, old_v)  # V is far above the band, but H/S are not
    zone_b_h, zone_b_s, zone_b_v = opencv_hsv('.20 .40 .95 .30')
    assert 100. <= zone_b_h <= 125. and zone_b_s >= 100.
    for level in neutral.PALETTE_LINEAR:
        h, s, v = opencv_hsv(f'{level} {level} {level} 1')
        assert s == 0.                       # hue is undefined for an exact grey
        assert not in_zone_b_band(h, s, v)   # cannot pass S>=100 at any V
        assert 0. <= h <= 180.


def test_recorded_before_frame_shows_the_indigo_pickup_floor():
    """Evidence for the before side: the recorded nav-gate frame, not a re-render."""
    assert RECORDED_FRAME.is_file()
    rgb = cv2.cvtColor(cv2.imread(str(RECORDED_FRAME)), cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    indigo = (h >= 100) & (h <= 120) & (s >= 100)
    assert indigo.mean() >= .40                     # 0.57 measured
    assert 100 <= float(np.median(h[indigo])) <= 120
    assert float(np.median(s[indigo])) >= 150
    assert 60 <= float(np.median(v[indigo])) <= 120  # 90 measured; dark, as reported


def test_v6_scene_profile_pins_the_light_and_pickup_contract():
    old = contrast.profile_record(OLD)
    new = contrast.profile_record(NEW)
    assert old['sha256'] == 'b95ad4e77326ccce3a428d77efbddb9a25ac03fc606d74ed952732a82bd94fc4'
    assert 'light_scale' not in old and 'pickup_paint' not in old
    assert new['base_render_profile'] == 'noshadow_bright_v1'
    # 2026-10-19 Claude review §3(a): v6 keeps the base lighting (0.30, factor 1.0)
    # so zone B stays inside the frozen v1 band (H 110-114 / S>=100 / V 30-110).
    # #611 used 0.70 and measured zone B at V~195 => 0 px in the v1 band.
    assert new['light_scale'] == .30
    assert new['light_scale_factor_vs_base'] == pytest.approx(1.0, rel=1e-9)
    assert new['sha256'] == '1c57232468d2b7a3e580eb0d3e78ccdccdef7a94161cd7567baa3adee8c39bed'
    assert new['changes_physics'] is False
    assert new['texture_asset_profile'] == OLD
    assert new['pickup_paint'] == neutral.record()
    assert new['sha256'] != old['sha256']
    assert contrast.resolve(NEW) == NEW
    with pytest.raises(ValueError):
        contrast.resolve('not_a_scene_profile')


def test_current_stack_and_map_are_pinned():
    stack = json.loads((ROOT / 'configs/current_stack.json').read_text())
    rule = next(r for r in stack['rules'] if r['id'] == 'scene_profile')
    assert rule['current'] == NEW
    static = json.loads(MAP.read_text())
    assert hashlib.sha256(MAP.read_bytes()).hexdigest() == MAP_SHA
    assert static['regions']['zone_B']['rgba'] == '.20 .40 .95 .30'
    assert static['regions']['pickup']['rgba'] == neutral.SOURCE_RGBA  # map file intentionally unchanged


def test_final_v3_scene_xml_carries_the_neutral_grid(monkeypatch):
    """The real s7 scene XML (nav-gate scenario) through the real zone builder."""
    from sim import research_dispatch_arena, research_scene_xml
    template = ET.Element('mujoco')
    ET.SubElement(template, 'option', timestep='.002')
    world = ET.SubElement(template, 'worldbody')
    ET.SubElement(world, 'geom', name='floor')
    ET.SubElement(world, 'camera', name='cctv_top')
    box = ET.SubElement(world, 'body', name='dispatch_box')
    ET.SubElement(box, 'freejoint', name='dispatch_box_free')
    ET.SubElement(box, 'geom', name='dispatch_box_geom', type='box', size='.03 .02 .016', mass='.03')
    beam = ET.SubElement(world, 'body', name='team_beam')
    ET.SubElement(beam, 'geom', name='team_beam_geom')
    for rid in ('r1', 'r2', 'r3'):
        for side in ('left', 'right'):
            ET.SubElement(world, 'geom', name=rid + '__' + side + '_finger')
    monkeypatch.setattr(research_scene_xml, 'plain_beam_xml', lambda xml: xml)
    monkeypatch.setattr(research_dispatch_arena, 'build_scene_xml', lambda xml, config: (xml, {'robot_xml_sha256': {}}))
    scene = scenario_scene('s7_pair_with_solo_v7', 911)
    xml = scene.transform(ET.tostring(template, encoding='unicode'))
    root = ET.fromstring(xml)
    assert root.find("worldbody/geom[@name='zone_pickup']") is not None
    assert zone_b_geoms(xml) and zone_b_geoms(xml)[0].get('rgba') == '.20 .40 .95 .30'
    record = neutral.apply_root(root)
    assert record['tiles'] == neutral.TILES
    assert root.find("worldbody/geom[@name='zone_pickup']") is None
    assert zone_b_geoms(ET.tostring(root, encoding='unicode'))[0].get('rgba') == '.20 .40 .95 .30'
    assert scene.config['static_map']['map_id'] == 'zone_wide_two_doors_final_v3'


def test_scene_profile_application_neutralizes_pickup_only_for_v6(monkeypatch):
    """apply_xml wiring: v6 replaces the overlay, the frozen v5 profile does not."""
    manifest = json.loads((ROOT / 'sim/assets/scene_contrast_v5/manifest.json').read_text())
    prefix = OLD + '/'
    faces = {}
    for key in manifest['images']:
        if key.startswith(prefix) and key.endswith('_fileright.png'):
            stem = key[len(prefix):-len('_fileright.png')]
            for face in ('right', 'left', 'up', 'down', 'front', 'back'):
                faces['file' + face] = f'{stem}_file{face}.png'
            break
    assert len(faces) == 6
    # The real per-face files are already published; only the floor/wall dressing
    # (v1.apply) is stubbed because that needs a full zone scene.
    monkeypatch.setattr(contrast.v1, 'apply', lambda root, extension=False: None)
    texture = ' '.join(f'{k}="{v}"' for k, v in faces.items())
    base = (f'<mujoco><asset><material name="natmat" texture="nattex"/>'
            f'<texture name="nattex" type="2d" {texture}/></asset><worldbody>'
            '<geom name="zone_wall_west" type="box" pos="0 0 1" size=".025 2 1" material="natmat"/>'
            '<geom name="zone_pickup" type="box" pos=".7 -.85 .0006" size="1.15 1.95 .0005" '
            'rgba=".12 .36 .70 .14"/>'
            '<geom name="zone_zone_B" type="box" pos="4.6 -2.1 .0006" size=".3 .7 .0005" '
            'rgba=".20 .40 .95 .30"/>'
            '<light name="l" diffuse=".7 .7 .7"/></worldbody></mujoco>')
    v6 = ET.fromstring(contrast.apply_xml(base, NEW))
    assert v6.find("worldbody/geom[@name='zone_pickup']") is None
    assert len([g for g in v6.iter('geom') if (g.get('name') or '').startswith('zone_pickup_tile_')]) == 60
    new_light = v6.find("worldbody/light")
    # light_scale 0.30 (factor 1.0) keeps the base lighting: diffuse .7 x .3 = .21,
    # byte-for-byte the same light attributes as the frozen v5 profile.
    assert [float(v) for v in new_light.get('diffuse').split()] == pytest.approx([.21]*3)
    assert new_light.get('cutoff') == '180'
    wall = v6.find("worldbody/geom[@name='zone_wall_west']")
    assert wall.get('material') == 'contrast_v5_zone_wall_west' and wall.get('rgba') == '1 1 1 1'
    assert v6.find("worldbody/geom[@name='zone_zone_B']").get('rgba') == '.20 .40 .95 .30'
    v5 = ET.fromstring(contrast.apply_xml(base, OLD))
    old_light = v5.find("worldbody/light")
    for attr in ('diffuse', 'ambient', 'specular', 'cutoff', 'pos', 'directional'):
        assert new_light.get(attr) == old_light.get(attr)  # no light change vs frozen v5
    assert v5.find("worldbody/geom[@name='zone_pickup']").get('rgba') == neutral.SOURCE_RGBA
    assert v5.find("worldbody/geom[@name='zone_zone_B']").get('rgba') == '.20 .40 .95 .30'
