"""Default-off solo appearance profile ``solo_green_v1``: dark green walls, red and blue boxes only.

Appearance only.  Geometry, sizes, masses, friction, contacts, lights, cameras and the
physics are untouched.  Only the ``rgba`` attribute of the ``zone_wall_*`` geoms and of
the colour-box geoms changes.

* walls: one colour (``WALL_RGBA`` by default, or the optional ``wall_rgba``) for every
  ``zone_wall_*`` geom.
* boxes: the kind name is kept, only the paint changes.  ``cyan`` (the production kind)
  is painted blue, ``red`` stays red.  The two decoy kinds that the scenario places in the
  scene (``green``, ``yellow``) take a real paint (``DECOY_PAINT``), so the scene shows red
  and blue boxes only.  can, tile and beam are not boxes and are left unchanged.

Plan key ``solo_appearance = {'profile': 'solo_green_v1', 'jitter': bool, 'wall_rgba': str}``
(``wall_rgba`` optional, four floats in 0..1).  Absent or None means off: the scene XML is
then byte-identical to the base profile.  The profile is exclusive with ``scene_colors_v2``
(fail closed).

``jitter`` draws, per episode seed, one brightness factor (HSV value, +-BRIGHTNESS) and one
hue shift (+-HUE_DEG degrees) for the walls and one pair for the boxes.  The seed is hashed
with sha256 (never ``hash()``), so an episode always gets the same paint.

``activate_own_rgb_band`` moves the teacher's own-RGB hue band of the cyan kind from the
cyan paint to the blue paint.  It is a perception constant of the teacher (same own-camera
input, no ground truth).  It is process-wide, so it is called only when the profile is on.
"""
from __future__ import annotations

import colorsys
import hashlib
import random
import xml.etree.ElementTree as ET

PROFILE = 'solo_green_v1'
SCHEMA = 'ugrp.solo_appearance.v1'
WALL_RGBA = '.05 .27 .14 1'
RED_RGBA = '.80 .12 .10 1'
BLUE_RGBA = '.10 .25 .85 1'
BASE_CYAN_RGBA = '.20 .65 .70 1'
BOX_KINDS = ('cyan', 'red', 'green', 'yellow')
# Decoy kind -> the real paint it takes (its kind token is kept, only the colour changes).
DECOY_PAINT = {'green': 'red', 'yellow': 'cyan'}
BRIGHTNESS = .15
HUE_DEG = 2.0
# Own-RGB hue band (OpenCV H, 0..179) of the cyan kind under the blue paint.  Set from the
# measured pixels (preview/hue_measurement.json): the blue box is ~114, the bare floor ~108-109.
# The base cyan band is ((84, 100),).
BLUE_HUE_BAND = ((111, 122),)
BASE_CYAN_HUE_BAND = ((84, 100),)
KEYS = {'profile', 'jitter', 'wall_rgba'}


def _wall_text(value):
    """Validated 'r g b a' text: four floats, each in 0..1."""
    if not isinstance(value, str):
        raise ValueError('SOLO_APPEARANCE_BAD_WALL_RGBA')
    try:
        vals = [float(v) for v in value.split()]
    except ValueError:
        raise ValueError('SOLO_APPEARANCE_BAD_WALL_RGBA')
    if len(vals) != 4 or any(not (0. <= v <= 1.) for v in vals):
        raise ValueError('SOLO_APPEARANCE_BAD_WALL_RGBA')
    return value


def wall_paint(wall_rgba=None):
    return WALL_RGBA if wall_rgba is None else _wall_text(wall_rgba)


def validate_profile(opt):
    if not isinstance(opt, dict) or opt.get('profile') != PROFILE or not set(opt) <= KEYS:
        raise ValueError('SOLO_APPEARANCE_UNKNOWN_PROFILE')
    if not isinstance(opt.get('jitter', False), bool):
        raise ValueError('SOLO_APPEARANCE_JITTER_MUST_BE_BOOL')
    if 'wall_rgba' in opt:
        _wall_text(opt['wall_rgba'])


def _draw(seed, jitter):
    if not jitter:
        return {'wall': [1., 0.], 'box': [1., 0.]}
    digest = hashlib.sha256(f'{PROFILE}:{int(seed)}'.encode()).digest()
    rng = random.Random(int.from_bytes(digest[:8], 'big'))
    out = {}
    for part in ('wall', 'box'):
        out[part] = [round(rng.uniform(1 - BRIGHTNESS, 1 + BRIGHTNESS), 4),
                     round(rng.uniform(-HUE_DEG, HUE_DEG), 3)]
    return out


def _shade(rgba, value_factor, hue_deg):
    r, g, b, a = (float(v) for v in rgba.split())
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    r, g, b = colorsys.hsv_to_rgb((h + hue_deg / 360.) % 1., s, min(1., v * value_factor))
    return f'{r:.4f} {g:.4f} {b:.4f} {a:g}'


def rgba_table(seed=None, jitter=False, wall_rgba=None):
    """Paint of the walls and of each box kind (decoys take the colour of their real paint)."""
    draw = _draw(0 if seed is None else seed, jitter)
    wall = wall_paint(wall_rgba)
    if not jitter:
        table = {'wall': wall, 'cyan': BLUE_RGBA, 'red': RED_RGBA}
    else:
        table = {'wall': _shade(wall, *draw['wall']),
                 'cyan': _shade(BLUE_RGBA, *draw['box']),
                 'red': _shade(RED_RGBA, *draw['box'])}
    for decoy, paint in DECOY_PAINT.items():
        table[decoy] = table[paint]
    return table, draw


def record(seed, jitter, wall_rgba=None):
    table, draw = rgba_table(seed, jitter, wall_rgba)
    out = {'schema': SCHEMA, 'profile': PROFILE, 'jitter': bool(jitter),
           'seed': None if seed is None else int(seed), 'factors': draw, 'rgba': dict(table),
           'brightness_pm': BRIGHTNESS, 'hue_pm_deg': HUE_DEG,
           'changes': 'rgba of zone_wall_* and colour-box geoms only; physics untouched'}
    if wall_rgba is not None:
        out['wall_rgba'] = wall_paint(wall_rgba)
    return out


def apply_xml(xml, objects, *, seed=None, jitter=False, wall_rgba=None):
    """Rewrite the wall geoms and the colour-box geoms.  ``objects``: body name -> box kind.

    Fails closed: no wall geom, an unknown kind, a missing or duplicated box geom, a material
    on a painted geom, or an unmapped colour-box geom in the scene all raise.
    """
    table, _ = rgba_table(seed, jitter, wall_rgba)
    root = ET.fromstring(xml)
    world = root.find('worldbody')
    if world is None:
        raise ValueError('SOLO_APPEARANCE_NEEDS_WORLD')
    walls = [g for g in world.findall('geom') if (g.get('name') or '').startswith('zone_wall_')]
    if not walls:
        raise ValueError('SOLO_APPEARANCE_NO_WALL_GEOM')
    for geom in walls:
        if geom.get('material'):
            raise ValueError('SOLO_APPEARANCE_WALL_HAS_MATERIAL')
        geom.set('rgba', table['wall'])
    painted = {}
    for body, kind in sorted(objects.items()):
        if kind not in BOX_KINDS:
            raise ValueError('SOLO_APPEARANCE_UNKNOWN_BOX_KIND')
        found = world.findall(f".//geom[@name='{body}_geom']")
        if len(found) != 1 or found[0].get('material'):
            raise ValueError('SOLO_APPEARANCE_ONE_PLAIN_BOX_GEOM_REQUIRED')
        found[0].set('rgba', table[kind])
        painted[body] = (kind, table[kind])
    for geom in world.iter('geom'):
        name = geom.get('name') or ''
        if any(name.startswith(f'cargo_{k}_') for k in BOX_KINDS):
            if not any(name == f'{body}_geom' for body in painted):
                raise ValueError('SOLO_APPEARANCE_UNMAPPED_BOX_GEOM')
    return ET.tostring(root, encoding='unicode'), painted


def install(scene, *, seed, jitter=False, wall_rgba=None):
    """Wrap the scene's world-XML transform.  Called only when the plan carries the profile."""
    if getattr(scene, '_scene_colors_name', None) is not None:
        raise ValueError('SOLO_APPEARANCE_CONFLICTS_WITH_SCENE_COLORS_V2')
    if getattr(scene, '_solo_appearance_name', None) is not None:
        raise ValueError('SOLO_APPEARANCE_ALREADY_INSTALLED')
    render_profile = getattr(scene, '_render_profile_name', '') or ''
    if render_profile.startswith('walls_floor_contrast_v5_'):
        raise ValueError('SOLO_APPEARANCE_CONFLICTS_WITH_CONTRAST_V5_WALLS')
    inner = scene.transform

    def transform(xml):
        before = inner(xml)
        objects = {item['body_name']: item['kind'] for item in scene.config['setup_only']['objects'].values()}
        if not objects:
            raise ValueError('SOLO_APPEARANCE_NO_BOX_OBJECTS')
        after, painted = apply_xml(before, objects, seed=seed, jitter=jitter, wall_rgba=wall_rgba)
        scene.manifest['solo_appearance'] = {
            **record(seed, jitter, wall_rgba),
            'boxes': {body: {'kind': kind, 'rgba': rgba} for body, (kind, rgba) in sorted(painted.items())},
            'scene_xml_sha256_before': hashlib.sha256(before.encode()).hexdigest(),
            'scene_xml_sha256_after': hashlib.sha256(after.encode()).hexdigest()}
        return after

    scene.transform = transform
    scene._solo_appearance_name = PROFILE
    return scene


def set_cyan_band(band):
    """Set the teacher's own-RGB band of the cyan kind; returns the previous band."""
    from harness import zone_own_perception as zop
    previous = zop.APPEARANCE['cyan']['hue']
    zop.APPEARANCE['cyan']['hue'] = band
    return previous


def activate_own_rgb_band():
    """Blue paint for the cyan kind's own-RGB band.  Process-wide: call only when the profile is on."""
    set_cyan_band(BLUE_HUE_BAND)
    return [list(b) for b in BLUE_HUE_BAND]


def apply_plan(scene, plan):
    """Student-side hook called by scripts/run_grasp_act_student.py::run (default off).

    No ``solo_appearance`` key in the plan: the scene is returned untouched, so the world XML is
    the same as before this hook existed.  With the key: validate, then wrap the world XML.
    """
    appearance = plan.get('solo_appearance')
    if appearance is None:
        return scene
    validate_profile(appearance)
    return install(scene, seed=plan['seed'], jitter=appearance.get('jitter', False),
                   wall_rgba=appearance.get('wall_rgba'))
