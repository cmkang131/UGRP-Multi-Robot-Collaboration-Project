"""Offline deterministic material PNG generation; never imports MuJoCo.

A complete surface is sampled once; no tiling, glyphs, codes or marker shapes.
Dependencies/versions are pinned in requirements-test.txt. Published PNG bytes
and manifest hashes, not cross-version regeneration, define the scene version.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from sim.natural_scene_texture import CUBE_FACES, wall_key

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261015
MAPS = tuple(sorted((ROOT / 'maps/zones_final_v3').glob('zone_*.json')))


def texture(key, width, height, *, floor=False):
    seed = int.from_bytes(hashlib.sha256(f'{SEED}:{key}'.encode()).digest()[:8], 'big')
    rng = np.random.default_rng(seed)
    base = np.full((height, width), 146. if floor else 132., np.float32)
    # Multiscale mottling, with independent random samples across the whole face.
    for scale, strength in ((160, 7), (40, 5), (9, 2)):
        small = rng.normal(0, strength, (max(2, height//scale), max(2, width//scale))).astype(np.float32)
        base += cv2.resize(small, (width, height), interpolation=cv2.INTER_CUBIC)
    surface = Image.fromarray(np.clip(base, 90, 195).astype(np.uint8))
    draw = ImageDraw.Draw(surface)
    # Irregular wear/chips and short branching scuffs, with no periodic grid.
    for _ in range(max(6, width*height//1100)):
        x, y = rng.uniform(0, width), rng.uniform(0, height)
        radius = rng.uniform(1.5, 9 if floor else 7)
        angles = np.sort(rng.uniform(0, 2*np.pi, 7))
        points = [(x+np.cos(a)*radius*rng.uniform(.45, 1), y+np.sin(a)*radius*rng.uniform(.3, 1)) for a in angles]
        value = int(rng.integers(100, 183) if floor else rng.integers(93, 165))
        draw.polygon(points, fill=value)
    for _ in range(max(3, width*height//9000)):
        x, y = rng.uniform(0, width), rng.uniform(0, height)
        angle, length = rng.uniform(0, 2*np.pi), rng.uniform(5, 32)
        points = [(x, y), (x+np.cos(angle)*length*.55, y+np.sin(angle)*length*.55),
                  (x+np.cos(angle+.15)*length, y+np.sin(angle+.15)*length)]
        draw.line(points, fill=int(rng.integers(96, 125)), width=1)
    surface = surface.filter(ImageFilter.GaussianBlur(.35))
    gray = np.clip(np.asarray(surface, dtype=float)+rng.normal(0, .65, (height, width)), 88, 198).astype(np.uint8)
    return Image.fromarray(np.repeat(gray[..., None], 3, axis=2))


def generate(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    specs = {'floor': (3072, 3072, True)}
    walls = {}
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
                specs[face] = (max(32, round(2*size[ui]*512)), max(32, round(2*size[vi]*512)), False)
    record = {'schema': 'ugrp.natural_surface_assets.v1', 'seed': SEED,
              'generator': 'scripts/generate_scene_textures.py', 'floor_extent_m': [16, 16],
              'wall_source_pixels_per_m': 512, 'cube_face_pixels': 512, 'walls': walls, 'rgb_channels_equal': True, 'pixel_value_bounds_before_cube_resample': [88, 198],
              'maps': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in MAPS},
              'images': {}}
    for key, (width, height, floor) in sorted(specs.items()):
        path = directory / (key+'.png')
        im = texture(key, width, height, floor=floor)
        if not floor:
            im = im.resize((512, 512), Image.Resampling.LANCZOS)
        im.save(path, compress_level=9)
        record['images'][key] = {'file': path.name, 'width': im.width, 'height': im.height,
                                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    path = directory / 'manifest.json'
    path.write_text(json.dumps(record, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'manifest_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'images': len(specs), 'bytes': sum(p.stat().st_size for p in directory.iterdir())}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    generate(p.parse_args().output)
