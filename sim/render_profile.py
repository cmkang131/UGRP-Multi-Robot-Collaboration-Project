"""Versioned, opt-in render profiles (shadow / reflection) for the standard scene XML.

Why: the simulator draws four shadow-casting lights and a reflective floor. The user
judged them stronger than the real room, but every robot and TOP camera image, and
therefore every perception result, depends on them. So the profile is a new, named,
hashed condition; the default path is left byte-for-byte alone and nothing here
runs unless a runner passes an explicit profile name.

A profile only edits the scene XML string (``<light castshadow>``,
``<material reflectance>``; ``noshadow_bright_v1`` also ``<light cutoff>`` and the light colours). Geometry, masses, contacts, actuators, timestep and
camera pose/FOV are never touched, so physics is unchanged by construction; the
tests compile both models and diff every mjModel array to prove it.

The viewer's own shadow/reflection switch (``mjRND_SHADOW`` / ``mjRND_REFLECTION``
on ``viewer.user_scn``, ``scripts/dispatch_native_view.py``) acts on the observer
window only and never reaches the robot renderer, so it is not reused here.
``scripts/eval_zone_own_perception_v3_1.py`` (``LIGHTING`` stress profiles) edits
light arrays of a built model for a perception stress test; this module keeps to
XML so the change lands in the recorded ``scene_xml`` hash.

No MuJoCo import at module load (plan-only probe runs must stay simulator-free).
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET

SCHEMA = 'ugrp.render_profile.v1'
DEFAULT_PROFILE = 'shadows_v1'

PROFILES = {
    'shadows_v1': {
        'summary': 'Current behaviour: every light casts shadows, groundmat reflectance stays as authored. '
                   'Selecting it changes nothing.',
        'xml_ops': [],
    },
    'noshadow_v1': {
        'summary': 'Every <light> castshadow=false and every <material> reflectance=0 (only groundmat, .035, '
                   'is non-zero in the zone scene). Other light values (diffuse/ambient/specular/headlight), '
                   'texture, shadowsize and MSAA are unchanged.',
        'xml_ops': [{'op': 'light_castshadow', 'value': 'false'},
                    {'op': 'material_reflectance', 'value': '0'}],
    },
    'noshadow_bright_v1': {
        'summary': 'noshadow_v1 plus: every <light> becomes a point light (cutoff=180) and its diffuse, ambient and '
                   'specular colours are multiplied by 0.3. Deliberately brighter than shadows_v1 where the spot cones '
                   'leave the floor dark (user decision 2026-09-29); the real room was not measured. The point lights '
                   'avoid the all-black frames MuJoCo renders through its non-shadow spot-light path (README).',
        'xml_ops': [{'op': 'light_castshadow', 'value': 'false'},
                    {'op': 'material_reflectance', 'value': '0'},
                    {'op': 'light_cutoff', 'value': '180'},
                    {'op': 'light_color_scale', 'value': '0.3'}],
    },
    'floor_light_v1': {
        'summary': 'noshadow_bright_v1 plus a lighter floor: texture "ground" (the checker under material groundmat) '
                   'changes from rgb1 .20 .22 .24 / rgb2 .27 .29 .31 to a neutral mid-tone grey checker rgb1 .36 .35 .34 / '
                   'rgb2 .62 .61 .59 (checker contrast kept and raised). User statement 2026-09-29: the real floor is '
                   'lighter than the simulated dark blue-grey one; the real colour was not measured.',
        'xml_ops': [{'op': 'light_castshadow', 'value': 'false'},
                    {'op': 'material_reflectance', 'value': '0'},
                    {'op': 'light_cutoff', 'value': '180'},
                    {'op': 'light_color_scale', 'value': '0.3'},
                    {'op': 'texture_rgb', 'texture': 'ground', 'rgb1': '.36 .35 .34', 'rgb2': '.62 .61 .59'}],
    },
}

# MuJoCo defaults for the light colours a <light> may omit (XML reference), needed to scale an omitted attribute.
LIGHT_COLOR_DEFAULTS = {'ambient': (0., 0., 0.), 'diffuse': (.7, .7, .7), 'specular': (.3, .3, .3)}

# ``noshadow_bright_v1`` (user decision 2026-09-29: drop shadows/reflections and make it brighter) was sized on static
# frames at recorded probe poses, not on the real room: experiments/2026-09-29-render-profile/static_frames/
# calibrate_brightness.py. The 0.3 is the middle of the 0.26-0.34 plateau that passes the pre-set rules (README).
# ``softshadow_v1`` is deliberately absent: nothing in the repository (code, docs, measurement protocol)
# records the real room's light levels, so any diffuse/ambient number would be a guess. The user-facing
# question is shadows on vs off; a weaker-shadow profile can be added once the room is measured.


def _canon(profile_name):
    return json.dumps({'schema': SCHEMA, 'name': profile_name, 'xml_ops': PROFILES[profile_name]['xml_ops']},
                      sort_keys=True, separators=(',', ':'))


def resolve(name):
    """``None`` (flag absent) and ``shadows_v1`` both mean no change; unknown names fail."""
    if name is None:
        return None
    if name not in PROFILES:
        raise ValueError(f'unknown render profile {name!r}; choose from {sorted(PROFILES)}')
    return name


def profile_sha256(name):
    return hashlib.sha256(_canon(resolve(name) or DEFAULT_PROFILE).encode()).hexdigest()


def profile_record(name):
    """Name + hash + definition, written into every manifest that used the profile."""
    name = resolve(name) or DEFAULT_PROFILE
    return {'schema': SCHEMA, 'name': name, 'sha256': profile_sha256(name), 'xml_ops': PROFILES[name]['xml_ops'],
            'summary': PROFILES[name]['summary'],
            'changes_images': bool(PROFILES[name]['xml_ops']), 'changes_physics': False}


def apply_xml(xml, name):
    """Return ``xml`` edited for the profile. ``None``/``shadows_v1`` return the same string object."""
    name = resolve(name)
    if name is None or not PROFILES[name]['xml_ops']:
        return xml
    root = ET.fromstring(xml)
    for op in PROFILES[name]['xml_ops']:
        if op['op'] == 'light_castshadow':
            for light in root.iter('light'):
                light.set('castshadow', op['value'])
        elif op['op'] == 'material_reflectance':
            for material in root.iter('material'):
                if material.get('reflectance') is not None:   # absent means MuJoCo's default, 0
                    material.set('reflectance', op['value'])
        elif op['op'] == 'light_cutoff':
            for light in root.iter('light'):
                light.set('cutoff', op['value'])
        elif op['op'] == 'light_color_scale':
            factor = float(op['value'])
            for light in root.iter('light'):
                for key, default in LIGHT_COLOR_DEFAULTS.items():
                    values = [float(v) for v in light.get(key).split()] if light.get(key) is not None else list(default)
                    light.set(key, ' '.join(f'{v * factor:.6g}' for v in values))
        elif op['op'] == 'texture_rgb':
            named = [t for t in root.iter('texture') if t.get('name') == op['texture']]
            if not named:
                raise ValueError(f'render profile edits texture {op["texture"]!r} but the scene XML has none')
            for texture in named:
                texture.set('rgb1', op['rgb1'])
                texture.set('rgb2', op['rgb2'])
        else:  # pragma: no cover - registry is closed
            raise ValueError(f'unknown render profile op {op["op"]!r}')
    return ET.tostring(root, encoding='unicode')


def install(scene, name):
    """Wrap ``scene.transform`` (instance level) so the profile is applied after the scene's own XML build.

    Instance level keeps ``isinstance`` checks and every pinned scene module untouched. With ``name=None`` the
    scene is returned as is. The scene manifest (rebuilt on each ``transform`` call by the scene classes) gets
    ``render_profile`` after the inner transform, so ``scene.record()`` carries name, hash and XML hashes.
    """
    name = resolve(name)
    if name is None:
        return scene
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


def audit_model(model):
    """Values the compiled model actually uses (recorded next to the requested profile)."""
    import mujoco
    reflective = {mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_MATERIAL, i) or f'material{i}': float(model.mat_reflectance[i])
                  for i in range(model.nmat) if float(model.mat_reflectance[i]) != 0.}
    import numpy as np
    textures = {}
    for i in range(model.ntex):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_TEXTURE, i)
        if name == 'ground':
            n = int(model.tex_width[i] * model.tex_height[i] * model.tex_nchannel[i])
            data = np.asarray(model.tex_data[int(model.tex_adr[i]):int(model.tex_adr[i]) + n]).reshape(-1, int(model.tex_nchannel[i]))
            textures[name] = [round(float(v), 1) for v in data.mean(0)]
    return {'nlight': int(model.nlight), 'ground_texture_mean_rgb': textures.get('ground'), 'light_castshadow': [int(v) for v in model.light_castshadow],
            'light_cutoff': [float(v) for v in model.light_cutoff],
            'nmat': int(model.nmat), 'materials_with_reflectance': reflective}


def verify_model(model, name):
    """Fail closed when the compiled model does not carry the requested profile."""
    name = resolve(name)
    audit = audit_model(model)
    if name in ('noshadow_v1', 'noshadow_bright_v1', 'floor_light_v1') and (any(audit['light_castshadow']) or audit['materials_with_reflectance']):
        raise RuntimeError(f'render profile {name} requested but the compiled model still has shadows/reflections: {audit}')
    if name in ('noshadow_bright_v1', 'floor_light_v1') and any(c != 180. for c in audit['light_cutoff']):
        raise RuntimeError(f'render profile {name} requested but the compiled model still has spot lights: {audit}')
    if name == 'floor_light_v1':
        mean = audit['ground_texture_mean_rgb']
        if mean is None or not all(abs(m - e) <= 8 for m, e in zip(mean, (125., 122., 118.))):
            raise RuntimeError(f'render profile {name} requested but the floor texture mean is {mean}, expected about (125, 122, 118)')
    return audit
