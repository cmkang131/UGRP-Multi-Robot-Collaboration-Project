"""v98 render near-clip profile ``floor_light_nearclip_v1`` (2026-10-05, user finding relayed by the coordinator).

Why. In the HIGH carry posture (and the unloaded grasp hover, same servo 896/2035/1894) each robot camera sits about
13 mm above the beam's top face. The scene's ``<visual><map znear=".002">`` times the model extent (11.11 m) puts the
renderer's near clipping plane at 22.2 mm, so the part of the beam closer than 22.2 mm is cut away and the floor shows
through it. A real camera would see the beam fill the image: the simulator showed more than a real robot can
(sim2real gap). Render-only check: outputs/v105-nearclip-check-20261005 (light6 t=301.8 r1; before = recorded frame
byte for byte; after = beam top fills the view, no visible depth artefacts).

What. floor_light_v1 (sim.render_profile, unchanged) plus ``<visual><map znear>`` = ZNEAR_REL (0.0004 x 11.11 m =
4.4 mm, target <= 5 mm). Only the projection's near plane changes: geometry, physics, lights, textures and camera
pose/FOV are untouched. MuJoCo XML reference (visual/map znear): a near plane too close loses depth-buffer
resolution; MuJoCo renders with reversed Z (changelog, PR #978), and the before/after frames show no z-fighting.

How. Instance-level, v98 hosts only: ``scenes()`` wraps ``make_scene`` of sim.final_pair_v3 (case host) and
sim.final_pair_highpose_staged (stage probes) while the backend constructor runs, and the returned scene's
``transform`` applies the XML edit AFTER floor_light_v1. sim/render_profile.py, sim/final_pair_v3.py and every
earlier bundle/scene stay byte-identical; the run's scene.xml and scene manifest carry the new value and hashes.
Runs with this profile are a new render condition and are never pooled with runs before it.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import xml.etree.ElementTree as ET

ID = 'floor_light_nearclip_v1'
BASE_PROFILE = 'floor_light_v1'
SCHEMA = 'ugrp.highpose_render_nearclip.v1'
ZNEAR_REL = '0.0004'           # x model extent 11.112 m = 4.44 mm
NEAR_MAX_M = .005
PREVIOUS = {'znear_rel': .002, 'near_m_at_extent_11_112': .02222}


def _canon():
    return json.dumps({'schema': SCHEMA, 'id': ID, 'base_profile': BASE_PROFILE,
                       'xml_ops': [{'op': 'visual_map_znear', 'value': ZNEAR_REL}]}, sort_keys=True, separators=(',', ':'))


def sha256():
    return hashlib.sha256(_canon().encode()).hexdigest()


def record():
    return {'schema': SCHEMA, 'id': ID, 'sha256': sha256(), 'base_profile': BASE_PROFILE,
            'xml_ops': [{'op': 'visual_map_znear', 'value': ZNEAR_REL}], 'near_max_m': NEAR_MAX_M,
            'previous': PREVIOUS, 'changes_images': True, 'changes_physics': False,
            'reason': 'near plane 22.2 mm clipped the beam 13 mm under the HIGH camera (floor seen through cargo)',
            'pooling': 'new render condition: never pooled with earlier runs',
            'check': 'outputs/v105-nearclip-check-20261005'}


def apply_xml(xml):
    root = ET.fromstring(xml)
    visual = root.find('visual')
    if visual is None:
        visual = ET.SubElement(root, 'visual')
    maps = visual.findall('map')
    if len(maps) > 1:
        raise ValueError('scene XML has more than one <visual><map>')
    (maps[0] if maps else ET.SubElement(visual, 'map')).set('znear', ZNEAR_REL)
    return ET.tostring(root, encoding='unicode')


def wrap(scene):
    if getattr(scene, '_nearclip_id', None) == ID:
        return scene
    if getattr(scene, '_render_profile_name', None) != BASE_PROFILE:
        raise ValueError(f'{ID} needs a {BASE_PROFILE} scene, got {getattr(scene, "_render_profile_name", None)!r}')
    inner = scene.transform

    def transform(xml):
        before = inner(xml)
        after = apply_xml(before)
        scene.manifest['render_nearclip'] = {**record(),
            'scene_xml_sha256_before_nearclip': hashlib.sha256(before.encode()).hexdigest(),
            'scene_xml_sha256_after_nearclip': hashlib.sha256(after.encode()).hexdigest()}
        return after

    scene.transform = transform
    scene._nearclip_id = ID
    return scene


@contextmanager
def scenes():
    """Wrap ``make_scene`` of the v98 host modules while a backend constructor runs."""
    from sim import final_pair_v3, final_pair_highpose_staged
    saved = [(m, m.make_scene) for m in (final_pair_v3, final_pair_highpose_staged)]
    try:
        for module, original in saved:
            module.make_scene = (lambda f: lambda bundle, seed: wrap(f(bundle, seed)))(original)
        yield
    finally:
        for module, original in saved:
            module.make_scene = original


def audit(model):
    """Fail closed unless the compiled model uses the profile's near plane (MuJoCo stores it as float32)."""
    znear, extent = float(model.vis.map.znear), float(model.stat.extent)
    near_m = znear * extent
    if abs(znear - float(ZNEAR_REL)) > 1e-8 or not 0 < near_m <= NEAR_MAX_M:
        raise RuntimeError(f'{ID} requested but the compiled model has znear {znear} x extent {extent} = {near_m} m')
    return {**record(), 'compiled_znear_rel': znear, 'extent_m': extent, 'near_m': near_m}


class NearClip:
    """Mixin for a v98 physics backend; must precede the v3 backend in the MRO."""
    render_nearclip = ID

    def __init__(self, *args, **kwargs):
        with scenes():
            super().__init__(*args, **kwargs)
        self.nearclip_audit = audit(self.world.model)

    def reset(self, cap):
        out = super().reset(cap)
        if getattr(self, 'nearclip_audit', None) is not None:   # set by __init__ (unit-test stubs skip it)
            from scripts.run_final_environment_checks import write
            write(self.out / 'eval_only/render_nearclip.json', self.nearclip_audit)
        return out
