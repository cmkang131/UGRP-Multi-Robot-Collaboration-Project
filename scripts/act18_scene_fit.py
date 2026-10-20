"""ACT18 scene-fit test patch: render the ACT owner on the nav v6 pickup paint.

Default OFF.  Only when ``UGRP_ACT18_SCENE_FIT=v6_neutral_pickup_v1`` is set
does :func:`install_if_requested` wrap ``sim.scene_contrast_v5.install`` so the
v5 scene (``walls_floor_contrast_v5_indigo110_s80``, ``warp_act_scene.py:2``)
additionally gets the neutral pickup-floor paint of the nav scene
``walls_floor_contrast_v6_indigo110_s80_neutral_start``.

Why this is the v6 appearance (nav branch ``sim/scene_contrast_v5.py:31-34``):
v6 = same indigo wall rgb/hsv/pattern, the v5 wall texture assets (alias),
``light_scale 0.30`` which equals the ``noshadow_bright_v1`` base scale
(factor 1.0, i.e. no lighting change), and ``pickup: neutral_grid_v1``.  So the
only visual difference is ``sim/neutral_pickup_floor.apply_root`` replacing the
``zone_pickup`` overlay (rgba ``.12 .36 .70 .14``) by 60 neutral grey tiles
(contype/conaffinity 0, mass 0 -> no physics change, but ngeom +59).  The file
``sim/neutral_pickup_floor.py`` here is a byte copy of commit 46ea6b4d8
(sha256 76d28879...71d8), identical to the nav r5 branch.

Hook: ``scripts/act16w_native_run.py`` calls :func:`install_if_requested` after
the frozen ``sim`` package path is set.  Both the compiled-reference export
(teacher mode, ``warp_act_episode.py:103-104``) and the eval owner
(``warp_act_api.py:152``) build the scene through
``warp_act_scene.make_scene -> sim.scene_contrast_v5.install``, so one wrap
covers both.  Because the scene XML changes, the C312 compiled references
(``simalt_compiled_compat.py:85-89`` binds the exact XML sha256 and geom names)
MUST be regenerated with the same env set; old v5 references fail closed.

No physics, controller, policy, clock or checkpoint change.  Eval/diagnostic
only; results are never pooled with C2c v5 runs.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import os
from pathlib import Path

ENV = 'UGRP_ACT18_SCENE_FIT'
MODE = 'v6_neutral_pickup_v1'
BASE_SCENE = 'walls_floor_contrast_v5_indigo110_s80'
TARGET_SCENE = 'walls_floor_contrast_v6_indigo110_s80_neutral_start'
ROOT = Path(__file__).resolve().parents[1]
NEUTRAL_PATH = ROOT / 'sim' / 'neutral_pickup_floor.py'
NEUTRAL_SHA256 = '76d28879101c0fdb2ca2cce6173f239adfc432ae8629d2844e57ed2811ea71d8'
SCHEMA = 'ugrp.act18.scene_fit.v1'


def requested(environ=None):
    """True only for the exact opt-in value; any other non-empty value fails."""
    value = (os.environ if environ is None else environ).get(ENV, '')
    if value == '':
        return False
    if value != MODE:
        raise ValueError(f'{ENV} must be unset or {MODE!r}, got {value!r}')
    return True


def _neutral_module():
    raw = NEUTRAL_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != NEUTRAL_SHA256:
        raise ValueError('neutral_pickup_floor.py hash mismatch')
    spec = importlib.util.spec_from_file_location('_act18_neutral_pickup_floor', NEUTRAL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply_xml(xml):
    """v5 scene XML -> same XML with the v6 neutral pickup tiles (fails closed)."""
    import xml.etree.ElementTree as ET
    neutral = _neutral_module()
    root = ET.fromstring(xml)
    record = neutral.apply_root(root)
    return ET.tostring(root, encoding='unicode'), record


def record(before, after, paint, contrast_file):
    return dict(schema=SCHEMA, mode=MODE, env=ENV, base_scene=BASE_SCENE,
                appearance_equivalent_to=TARGET_SCENE, light_scale_factor_vs_base=1.0,
                pickup_paint=paint, neutral_module_sha256=NEUTRAL_SHA256,
                contrast_module_file=str(contrast_file), changes_physics=False,
                scene_xml_sha256_before_fit=hashlib.sha256(before.encode()).hexdigest(),
                scene_xml_sha256_after_fit=hashlib.sha256(after.encode()).hexdigest(),
                pooling_with_v5='forbidden')


def install(contrast):
    """Wrap ``contrast.install`` (the resolved ``sim.scene_contrast_v5`` module)."""
    if getattr(contrast.install, '_act18_scene_fit', False):
        return contrast
    original = contrast.install

    def patched(scene, name, *, extension=False):
        if name != BASE_SCENE:
            raise ValueError(f'scene fit applies only on {BASE_SCENE}, got {name!r}')
        scene = original(scene, name, extension=extension)
        inner = scene.transform

        def transform(xml):
            before = inner(xml)
            after, paint = apply_xml(before)
            scene.manifest['act18_scene_fit'] = record(before, after, paint,
                                                       getattr(contrast, '__file__', None))
            return after
        scene.transform = transform
        return scene

    patched._act18_scene_fit = True
    contrast.install = patched
    return contrast


def install_if_requested(environ=None):
    """Called by act16w_native_run.py; no-op unless the env opt-in is exact."""
    if not requested(environ):
        return None
    return install(importlib.import_module('sim.scene_contrast_v5'))
