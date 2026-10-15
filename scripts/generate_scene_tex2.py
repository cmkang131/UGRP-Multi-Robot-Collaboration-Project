"""Deterministic PNG material assets only; no simulator imports or tiled motifs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from scripts.generate_scene_textures import MAPS, ROOT
from sim.natural_scene_texture_v2 import CUBE_FACES, wall_key

SEED = 2026101502
# C camera montages show the 512-square cube's long wall faces averaging
# 512 px/m source chips into weak grain (e.g. 6.5 m spans only 512 texels).
# D authors coarser irregular plaster wear at 64 source px/m, preserving face
# aspect down to 8 px instead of stretching thin dimensions to 128 px.
# These are material-design scales, not perception acceptance thresholds.
WALL_SOURCE_PX_PER_M = 64
MIN_SOURCE_FACE_PX = 8
# Material design bounds, not detector acceptance thresholds. The existing
# all-hue paint mask starts at S=20; white_markers starts at V>180; relative
# peer-dark's largest possible V is .38*255=96.9. Stay inside that free interval.
# B camera JPEG interior S99=24 from authored S16 (error +8), versus paint
# S>=20. Candidate C uses S8; the new rendered audit still measures all tails.
# Hue differs despite low chroma; brightness supplies the large step.
PALETTES = {'walls': {'h': 112, 's': 8, 'v': [98, 134]},
            'floor': {'h': 18, 's': 8, 'v': [146, 180]}}


def texture(key, width, height, *, floor=False):
    rng = np.random.default_rng(int.from_bytes(hashlib.sha256(f'{SEED}:{key}'.encode()).digest()[:8], 'big'))
    palette = PALETTES['floor' if floor else 'walls']
    lo, hi = palette['v']
    base = np.full((height, width), hi-7., np.float32)
    # Independent, multiscale aggregate and wear. Scales/densities are authored
    # material parameters; measure their effect rather than calling them gates.
    for scale, strength in ((120, 3), (31, 2), (7, 1)):
        samples = rng.normal(0, strength, (max(2, height//scale), max(2, width//scale))).astype(np.float32)
        base += cv2.resize(samples, (width, height), interpolation=cv2.INTER_CUBIC)
    surface = Image.fromarray(np.clip(base, lo, hi).astype(np.uint8))
    draw = ImageDraw.Draw(surface)
    for _ in range(max(8, width*height//450)):
        x, y = rng.uniform(0, width), rng.uniform(0, height)
        radius = rng.uniform(2, 12)
        angles = np.sort(rng.uniform(0, 2*np.pi, 7))
        points = [(x+np.cos(a)*radius*rng.uniform(.4, 1), y+np.sin(a)*radius*rng.uniform(.4, 1)) for a in angles]
        draw.polygon(points, fill=int(rng.integers(lo, lo+5)))
    surface = surface.filter(ImageFilter.GaussianBlur(.35))
    value = np.clip(np.asarray(surface, dtype=float)+rng.normal(0, .8, (height, width)), lo, hi).astype(np.uint8)
    hsv = np.empty((height, width, 3), np.uint8)
    hsv[..., 0], hsv[..., 1], hsv[..., 2] = palette['h'], palette['s'], value
    return Image.fromarray(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB))


def generate(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    specs, walls = {'floor': (3072, 3072, True)}, {}
    for path in MAPS:
        for w in json.loads(path.read_text())['obstacles']:
            if not w['id'].startswith('wall_'):
                continue
            size = [*w['half_extents_m'], w['height_m']/2]
            key = wall_key('zone_'+w['id'], size)
            walls[key] = {}
            for attr, ui, vi in CUBE_FACES:
                face = key+'_'+attr
                walls[key][attr] = face
                specs[face] = (max(MIN_SOURCE_FACE_PX, round(2*size[ui]*WALL_SOURCE_PX_PER_M)),
                               max(MIN_SOURCE_FACE_PX, round(2*size[vi]*WALL_SOURCE_PX_PER_M)), False)
    record = {'schema': 'ugrp.natural_surface_assets.v2', 'seed': SEED,
              'generator': 'scripts/generate_scene_tex2.py', 'palettes_hsv': PALETTES,
              'floor_extent_m': [16, 16], 'wall_source_pixels_per_m': WALL_SOURCE_PX_PER_M,
              'cube_face_pixels': 512, 'wall_texuniform': False, 'minimum_source_face_dimension_px': MIN_SOURCE_FACE_PX, 'walls': walls,
              'maps': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in MAPS}, 'images': {}}
    for key, (width, height, floor) in sorted(specs.items()):
        im = texture(key, width, height, floor=floor)
        if not floor:
            im = im.resize((512, 512), Image.Resampling.LANCZOS)
            # Resampling RGB can overshoot both V and S. Reapply the authored
            # HSV palette after resampling so the published pixels obey it.
            value = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2HSV)[..., 2].astype(float)
            grain_rng = np.random.default_rng(int.from_bytes(hashlib.sha256((key+':grain').encode()).digest()[:8], 'big'))
            value = np.rint(value+grain_rng.normal(0, .8, value.shape)).astype(np.int16)
            p = PALETTES['walls']
            hsv = np.empty((512, 512, 3), np.uint8)
            hsv[..., 0], hsv[..., 1], hsv[..., 2] = p['h'], p['s'], np.clip(value, *p['v'])
            im = Image.fromarray(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB))
        path = directory/(key+'.png')
        im.save(path, compress_level=9)
        record['images'][key] = {'file': path.name, 'width': im.width, 'height': im.height,
                                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    path = directory/'manifest.json'
    path.write_text(json.dumps(record, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'manifest_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'images': len(specs), 'bytes': sum(p.stat().st_size for p in directory.iterdir())}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    generate(parser.parse_args().output)
