"""Opt-in natural textures without changing the pinned legacy render module.

Select this module through ``render_profile_selection.for_name`` for the textured
condition. Legacy definitions and their registry are never modified here.
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET

from sim import render_profile as base
from sim import natural_scene_texture as texture

PROFILE = texture.PROFILE
PROFILES = {
    PROFILE: {
        'summary': 'Opt-in natural grey floor/wall wear over floor_light_v1 lighting; '
                   'one nonrepeating pinned image per surface, no markers. New scene version; '
                   'camera effectiveness and physics equivalence await GCP verification.',
        'xml_ops': [*base.PROFILES['floor_light_v1']['xml_ops'][:-1],
                    {'op': 'natural_surface_texture', 'manifest_sha256': texture.MANIFEST_SHA256}],
    },
}


def resolve(name):
    return name if name == PROFILE else base.resolve(name)


def profile_sha256(name):
    if name != PROFILE:
        return base.profile_sha256(name)
    canon = json.dumps({'schema': base.SCHEMA, 'name': name, 'xml_ops': PROFILES[name]['xml_ops']},
                       sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canon.encode()).hexdigest()


def profile_record(name):
    if name != PROFILE:
        return base.profile_record(name)
    return {'schema': base.SCHEMA, 'name': name, 'sha256': profile_sha256(name),
            'xml_ops': PROFILES[name]['xml_ops'], 'summary': PROFILES[name]['summary'],
            'changes_images': True, 'changes_physics': False}


def apply_xml(xml, name):
    if name != PROFILE:
        return base.apply_xml(xml, name)
    # The same four lighting operations as the original textured definition;
    # leave the checker edit out because the pinned PNG replaces it entirely.
    root = ET.fromstring(base.apply_xml(xml, 'noshadow_bright_v1'))
    texture.apply(root)
    return ET.tostring(root, encoding='unicode')


def install(scene, name):
    if name != PROFILE:
        return base.install(scene, name)
    existing = getattr(scene, '_render_profile_name', None)
    if existing is not None:
        if existing != name:
            raise ValueError(f'scene already carries render profile {existing!r}, refusing {name!r}')
        return scene
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
    if name != PROFILE:
        return base.verify_model(model, name)
    # Check the unchanged lighting contract without requiring the legacy
    # checker mean; the texture verifier checks pinned PNGs and model bindings.
    audit = base.verify_model(model, 'noshadow_bright_v1')
    audit['natural_textures'] = texture.verify_model(model)
    return audit
