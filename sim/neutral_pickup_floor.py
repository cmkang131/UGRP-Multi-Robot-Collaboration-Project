"""Neutral pickup-floor paint: keep the pickup *feature*, drop the blue hue.

Why this module exists (2026-10-18 nav gate):

* The shared map paints the pickup region ``rgba '.12 .36 .70 .14'``
  (``sim/zone_arena.py`` ``build_authored_map``).  The MJWarp native renderer
  draws that geoms **opaque** (no alpha blend): the first recorded nav-gate
  frame has 57.0 % of its pixels at OpenCV hue 107-108, S median 212, V median
  90 (``experiments/2026-10-18-nav-gate-1/raw/r1-tick5.jpg``).
* Zone B paint is OpenCV hue 110-114, so floor and destination are 2-6 hue
  units apart and the own-RGB detector cannot separate them.
* The floor pattern is intended design, so this module does not delete the
  overlay into one flat grey.  It replaces the single blue rectangle with a
  deterministic grid of **neutral** grey tiles: three tone levels, alpha 1.0
  (so opaque and alpha-blending renderers agree), keeping tile corners/edges
  as feature points.  Saturation is exactly 0, so no pixel can satisfy a
  detector band that requires ``S >= 100``.

Geometry, walls, doors, zone paint (including zone B), slots, spawns and the
authored map files are untouched; the change is visual-only and applied by the
scene profile ``walls_floor_contrast_v6_indigo110_s80_neutral_start``.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

SCHEMA = 'ugrp.neutral_pickup_paint.v1'
SOURCE_NAME = 'zone_pickup'
#: The authored map rgba this module replaces; a different value fails closed.
SOURCE_RGBA = '.12 .36 .70 .14'
GRID = (6, 10)                       # columns along +x, rows along +y
PALETTE_LINEAR = (0.75, 0.88, 1.0)   # equal RGB -> S == 0
ALPHA = 1.0
TILES = GRID[0] * GRID[1]


def _srgb8(value):
    value = max(0., min(1., float(value)))
    srgb = 12.92*value if value <= 0.0031308 else 1.055*value**(1/2.4)-0.055
    return int(round(255*srgb))


def record():
    """Deterministic specification, hashed by the scene profile record."""
    return {'schema': SCHEMA, 'source_geom': SOURCE_NAME, 'source_rgba': SOURCE_RGBA,
            'grid': list(GRID), 'palette_linear': list(PALETTE_LINEAR), 'alpha': ALPHA,
            'tiles': TILES, 'tile_srgb8': [_srgb8(v) for v in PALETTE_LINEAR],
            'features': 'tile corners/edges + three neutral tone levels',
            'changes_physics': False}


def _tile_rgba(level):
    text = f'{level:.6g}'
    return f'{text} {text} {text} {ALPHA:.6g}'


def apply_root(root):
    """Replace the mapped ``zone_pickup`` overlay with the neutral tile grid.

    ``root`` is an ``ElementTree`` root after the zone scene has painted every
    ``regions`` entry.  Returns the applied record; fails closed when the known
    overlay (name + authored rgba) is missing, so a changed map cannot silently
    fall back to the blue floor.
    """
    world = root.find('worldbody')
    if world is None:
        raise ValueError('neutral pickup paint requires a worldbody')
    source = world.find("geom[@name='%s']" % SOURCE_NAME)
    if source is None:
        raise ValueError('NEUTRAL_PICKUP_OVERLAY_MISSING: ' + SOURCE_NAME)
    rgba = source.get('rgba')
    if rgba != SOURCE_RGBA:
        raise ValueError(f'NEUTRAL_PICKUP_OVERLAY_RGBA_CHANGED: {rgba!r}')
    pos = [float(v) for v in source.get('pos', '').split()]
    size = [float(v) for v in source.get('size', '').split()]
    if len(pos) != 3 or len(size) != 3 or min(size) <= 0:
        raise ValueError('NEUTRAL_PICKUP_OVERLAY_BOX_INVALID')
    index = list(world).index(source)
    world.remove(source)
    columns, rows = GRID
    half_x, half_y = size[0]/columns, size[1]/rows
    for i in range(columns):
        for j in range(rows):
            center_x = pos[0] - size[0] + (2*size[0]/columns)*(i + .5)
            center_y = pos[1] - size[1] + (2*size[1]/rows)*(j + .5)
            level = PALETTE_LINEAR[(2*i + j) % len(PALETTE_LINEAR)]
            tile = ET.Element('geom', {
                'name': f'{SOURCE_NAME}_tile_{i}_{j}', 'type': 'box',
                'pos': f'{center_x:.9g} {center_y:.9g} {pos[2]:.9g}',
                'size': f'{half_x:.9g} {half_y:.9g} {size[2]:.9g}',
                'rgba': _tile_rgba(level), 'contype': '0', 'conaffinity': '0',
                'group': '0', 'mass': '0'})
            world.insert(index + i*rows + j, tile)
    return record()
