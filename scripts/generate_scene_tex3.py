"""Unique natural wear at physical scales, no glyphs, repeated tiles or markers.

Design lengths come from texel-scale.json: native ground depth footprint needs
centimetres nearby, decimetres/metres at3m. These are material design choices,
not new detection/admission thresholds. Physics and camera are untouched.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw
from scripts.generate_scene_textures import MAPS, ROOT
from sim.natural_scene_texture_v2 import CUBE_FACES, wall_key

SEED = 2026101603
# Existing all-hue paint starts atS20, relative dark ends atV96.9, white atV>180.
# Neutral floor restores v1 chroma; cool dark wall has only four HSV S levels.
# Brightness split is a visual material design, not a segmentation admission gate.
PALETTES = {'walls': {'h': 112, 's': 4, 'v': [100, 138]},
            'floor': {'h': 0, 's': 0, 'v': [142, 180]}}
# Native5–20px requested structures over0.5–3m from measured projection.
# 3m depth-axis needs0.318–1.272m; other axes need0.004–0.096m.
SCALES_M = (.01, .03, .1, .32, 1.)


def image(key, size, span, floor):
    rng = np.random.default_rng(int.from_bytes(hashlib.sha256(f'{SEED}:{key}'.encode()).digest()[:8], 'big'))
    w, h = size
    p = PALETTES['floor' if floor else 'walls']
    lo, hi = p['v']
    field = np.zeros((h, w), np.float32)
    # Multioctave irregular stains. Each octave spans the WHOLE physical face;
    # sampling anisotropically in face pixels preserves its physical length.
    for scale in SCALES_M:
        noise = rng.normal(0, 1, (max(2, round(span[1]/scale)), max(2, round(span[0]/scale)))).astype(np.float32)
        field += cv2.resize(noise, (w, h), interpolation=cv2.INTER_CUBIC) / len(SCALES_M)
    value = np.clip((lo+hi)/2 + field*(hi-lo)/2, lo, hi).astype(np.uint8)
    surface = Image.fromarray(value)
    draw = ImageDraw.Draw(surface)
    # Irregular high/low aggregate corners at several physical sizes. A fixed
    # 12% authored area per scale is cosmetic coverage, not a perception test.
    for radius in (.012, .04, .12, .4):
        count = max(1, round(span[0]*span[1]*.12/(np.pi*radius**2)))
        for _ in range(count):
            x, y = rng.uniform(0, w), rng.uniform(0, h)
            a = np.sort(rng.uniform(0, 2*np.pi, 7))
            r = rng.uniform(.45, 1, 7)
            points = [(x+np.cos(t)*rj*radius*w/span[0], y+np.sin(t)*rj*radius*h/span[1]) for t, rj in zip(a, r)]
            draw.polygon(points, fill=int(rng.choice([lo, hi])))
    hsv = np.empty((h, w, 3), np.uint8)
    hsv[..., 0], hsv[..., 1], hsv[..., 2] = p['h'], p['s'], np.asarray(surface)
    return Image.fromarray(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB))


def generate(output):
    output.mkdir(parents=True, exist_ok=False)
    specs = {'floor': ((3072, 3072), (16., 16.), True)}
    walls = {}
    for path in MAPS:
        for wall in json.loads(path.read_text())['obstacles']:
            if not wall['id'].startswith('wall_'):
                continue
            size = [*wall['half_extents_m'], wall['height_m']/2]
            key = wall_key('zone_'+wall['id'], size)
            walls[key] = {}
            for attr, ui, vi in CUBE_FACES:
                face = key+'_'+attr
                walls[key][attr] = face
                specs[face] = ((1024, 1024), (2*size[ui], 2*size[vi]), False)
    record = {'schema': 'ugrp.natural_surface_assets.v3', 'seed': SEED, 'palettes_hsv': PALETTES,
              'scales_m': SCALES_M, 'generator': 'scripts/generate_scene_tex3.py',
              'floor_extent_m': [16, 16], 'cube_face_pixels': 1024, 'wall_texuniform': False,
              'walls': walls, 'images': {}, 'maps': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in MAPS}}
    for key, (size, span, floor) in sorted(specs.items()):
        path = output/(key+'.png')
        im = image(key, size, span, floor)
        if floor:
            indexed = im.convert('P', palette=Image.Palette.ADAPTIVE, colors=256)
            if not np.array_equal(np.asarray(im), np.asarray(indexed.convert('RGB'))):
                raise ValueError('indexed floor must preserve every RGB pixel')
            im = indexed
        im.save(path, compress_level=9)
        record['images'][key] = dict(file=path.name, width=size[0], height=size[1], span_m=span,
                                    sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    path = output/'manifest.json'
    path.write_text(json.dumps(record, indent=2, sort_keys=True)+'\n')
    print(hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    generate(p.parse_args().output)
