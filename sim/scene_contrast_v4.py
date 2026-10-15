"""Opt-in wall/floor contrast candidates; unchanged v1 floor and physics.

Wall colour is constrained by the pre-existing paint S>=20 and white V>180
detectors. Values below are authored material choices, not admission limits.
The uniform wall is the standard low-texture alternative to increasing ORB.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from sim import render_profile as base
from sim import natural_scene_texture as v1

ASSETS = Path(__file__).resolve().parent/'assets'/'scene_contrast_v4'
MANIFEST_SHA256 = 'afe9bfd45ed707d5147dea59d333cb06920dc5fd525310d5169816c91c0c929d'
# R1 colours: dark matches the v1 wall's nominal V84; light V140 is below
# the old V180 white exclusion. S16 is below the existing all-hue S20 gate.
# The 8cm skirting is an authored ordinary building element, not a marker or
# an estimator assumption. It has no collision geometry and no identifiers.
PROFILES = {
    'walls_floor_contrast_v4_dark': {'rgb': [78, 81, 83], 'skirting_m': 0., 'amplitude': 0},
    'walls_floor_contrast_v4_light': {'rgb': [131, 136, 140], 'skirting_m': 0., 'amplitude': 0},
    'walls_floor_contrast_v4_skirt': {'rgb': [131, 136, 140], 'skirting_m': .08, 'amplitude': 0},
}


def resolve(name):
    if name not in PROFILES:
        raise ValueError('explicit v4 contrast profile required: '+str(name))
    return name


def profile_record(name):
    spec = PROFILES[resolve(name)]
    if hashlib.sha256((ASSETS/'manifest.json').read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise ValueError('v4 manifest hash mismatch')
    definition = {'schema': 'ugrp.scene_contrast.v4', 'name': name, 'wall': spec,
                  'floor_manifest_sha256': v1.MANIFEST_SHA256,
                  'asset_manifest_sha256': MANIFEST_SHA256}
    canonical = json.dumps(definition, sort_keys=True, separators=(',', ':'))
    return {**definition, 'sha256': hashlib.sha256(canonical.encode()).hexdigest(),
            'changes_images': True, 'changes_physics': False, 'default': 'off'}


def apply_xml(xml, name):
    spec = PROFILES[resolve(name)]
    profile_record(name)
    # Reuse the v1 XML floor binding without copying or recolouring its PNG.
    root = ET.fromstring(base.apply_xml(xml, 'noshadow_bright_v1'))
    v1.apply(root)
    asset = root.find('asset')
    record = json.loads((ASSETS/'manifest.json').read_text())
    for geom in root.findall('worldbody/geom'):
        if not geom.get('name', '').startswith('zone_wall_'):
            continue
        matname = 'contrast_v4_'+geom.get('name')
        attrs = {'name': matname, 'rgba': ' '.join(str(c/255) for c in spec['rgb'])+' 1',
                 'specular': '0', 'shininess': '0', 'reflectance': '0'}
        if spec['skirting_m']:
            # Ordinary skirting is painted into the existing cube faces.
            size = tuple(map(float, geom.get('size').split()))
            faces = record['heights'][str(round(2*size[2], 6))]
            for filename in faces.values():
                path = ASSETS/filename
                if hashlib.sha256(path.read_bytes()).hexdigest() != record['images'][filename]:
                    raise ValueError('v4 skirting asset hash mismatch')
            ET.SubElement(asset, 'texture', name=matname+'_tex', type='cube',
                          **{a: '../scene_contrast_v4/'+f for a, f in faces.items()})
            attrs.update(texture=matname+'_tex', texuniform='false', rgba='1 1 1 1')
        ET.SubElement(asset, 'material', **attrs)
        geom.set('material', matname)
        geom.set('rgba', '1 1 1 1')
    return ET.tostring(root, encoding='unicode')


def install(scene, name):
    resolve(name)
    if getattr(scene, '_render_profile_name', None) is not None:
        raise ValueError('scene already carries a render profile')
    inner = scene.transform

    def transform(xml):
        before = inner(xml)
        after = apply_xml(before, name)
        scene.manifest['render_profile'] = {**profile_record(name),
            'scene_xml_sha256_before_profile': hashlib.sha256(before.encode()).hexdigest(),
            'scene_xml_sha256_after_profile': hashlib.sha256(after.encode()).hexdigest()}
        return after

    scene.transform = transform
    scene._render_profile_name = name
    return scene


def verify_model(model, name):
    import numpy as np
    from PIL import Image
    resolve(name)
    audit = base.verify_model(model, 'noshadow_bright_v1')
    floor = model.geom('floor')
    material = model.mat(int(model.geom_matid[floor.id]))
    tids = np.asarray(material.texid).reshape(-1)
    tid = next(int(t) for t in tids if t >= 0)
    n = int(model.tex_width[tid]*model.tex_height[tid]*model.tex_nchannel[tid])
    start = int(model.tex_adr[tid])
    pixels = np.asarray(model.tex_data[start:start+n]).reshape(-1, 3)
    original = np.asarray(Image.open(v1.checked_file('floor', v1.manifest(), v1.ASSETS)).convert('RGB')).reshape(-1, 3)
    if pixels.shape != original.shape or any(not np.array_equal(np.bincount(pixels[:, c], minlength=256),
            np.bincount(original[:, c], minlength=256)) for c in range(3)):
        raise RuntimeError('v4 floor differs from v1')
    walls = [model.geom(i) for i in range(model.ngeom) if model.geom(i).name.startswith('zone_wall_')]
    if not walls or any(not model.mat(int(model.geom_matid[g.id])).name.startswith('contrast_v4_') for g in walls):
        raise RuntimeError('v4 wall material binding missing')
    return {**audit, 'contrast': profile_record(name), 'floor_v1_histogram_exact': True,
            'checked_walls': len(walls)}
