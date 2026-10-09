"""Opt-in visual wall dressing. No physics, sensors, or controller dependencies.

The table describes physical tape cut-outs in metres; PNGs are a 1 mm raster of
that same table. Off returns the original XML verbatim, including whitespace.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import random
import xml.etree.ElementTree as ET

PROFILE_ID = 'tape_v1'
SEED = 16001
BACKGROUND = (.23, .28, .33)
INK = (.008, .009, .010)
OFFSET_M = .0001
DEFAULT_ASSETS = Path(__file__).resolve().parents[1] / 'experiments/2026-10-07-wall-parallax-texture/assets'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def walls_from_xml(xml):
    walls = []
    for g in ET.fromstring(xml).findall('worldbody/geom'):
        if not g.get('name', '').startswith('zone_wall_'):
            continue
        if g.get('type') != 'box' or any(k in g.attrib for k in ('quat', 'euler', 'axisangle', 'xyaxes', 'zaxis')):
            raise ValueError('tape_v1 admits only axis-aligned static box walls')
        walls.append(dict(name=g.get('name'), pos=list(map(float, g.get('pos').split())),
                          size=list(map(float, g.get('size').split()))))
    if not walls:
        raise ValueError('no admitted wall geometry')
    return sorted(walls, key=lambda w: w['name'])


def layout(walls):
    """Independent SHA-seeded faces; never repeat or mirror a tile."""
    faces = []
    axes = [('px', [1, 0, 0], [0, 1, 0], 0, 1),
            ('nx', [-1, 0, 0], [0, -1, 0], 0, 1),
            ('py', [0, 1, 0], [-1, 0, 0], 1, 0),
            ('ny', [0, -1, 0], [1, 0, 0], 1, 0)]
    for wall in walls:
        for side, normal, u, normal_axis, u_axis in axes:
            name = wall['name'] + '_' + side
            rng = random.Random(int.from_bytes(hashlib.sha256(f'{SEED}:{name}'.encode()).digest(), 'big'))
            length, height = 2 * wall['size'][u_axis], 2 * wall['size'][2]
            centre = [wall['pos'][i] + normal[i] * wall['size'][normal_axis] for i in range(3)]
            origin = [centre[i] - u[i] * length / 2 - (height / 2 if i == 2 else 0) for i in range(3)]
            tapes, patches = [], []
            x = length / 2 if length < .2 else rng.uniform(.07, .16)
            while x < length - .015:
                tapes.append(dict(centre_m=x, width_m=rng.uniform(.02, .03)))
                x += rng.uniform(.2, .3)
            for left, right in zip(tapes, tapes[1:]):
                lo = left['centre_m'] + left['width_m'] / 2 + .025
                hi = right['centre_m'] - right['width_m'] / 2 - .025
                for _ in range(rng.randint(2, 4)):
                    cx, cy = rng.uniform(lo, hi), rng.uniform(.035, height - .035)
                    width, high = rng.uniform(.02, .04), rng.uniform(.02, .04)
                    count = rng.randint(5, 8)
                    angles = [(k + rng.uniform(-.25, .25)) * 2 * math.pi / count for k in range(count)]
                    points = [(math.cos(a), math.sin(a)) for a in angles]
                    xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
                    ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
                    polygon = [[cx + width * ((a - xmin) / (xmax - xmin) - .5),
                                cy + high * ((b - ymin) / (ymax - ymin) - .5)] for a, b in points]
                    patches.append(dict(vertices_m=polygon, width_m=width, height_m=high))
            faces.append(dict(id=name, wall=wall['name'], side=side, length_m=length, height_m=height,
                              origin_m=origin, centre_m=centre, u_axis=u, v_axis=[0, 0, 1], normal=normal,
                              tapes=tapes, patches=patches))
    return dict(schema='ugrp.wall_texture.tape_v1', seed=SEED, wall_geometry=walls,
                background_rgb=BACKGROUND, ink_rgb=INK, offset_m=OFFSET_M, faces=faces)


def polygons(face):
    for t in face['tapes']:
        lo, hi = t['centre_m'] - t['width_m'] / 2, t['centre_m'] + t['width_m'] / 2
        yield [(lo, 0), (hi, 0), (hi, face['height_m']), (lo, face['height_m'])]
    for patch in face['patches']:
        yield patch['vertices_m']


def generate_assets(walls, directory):
    """Offline PNG/SVG/table generation, without loading MuJoCo or a scene."""
    from PIL import Image, ImageDraw
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    record = layout(walls)
    rows = []
    for face in record['faces']:
        width, height = round(face['length_m'] * 1000), round(face['height_m'] * 1000)
        image = Image.new('RGB', (width, height), tuple(round(v * 255) for v in BACKGROUND))
        draw = ImageDraw.Draw(image)
        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}">',
               f'<title>{face["id"]}: u right, z up, millimetres; print at 100%</title>',
               f'<rect width="{width}" height="{height}" fill="#3b4754"/>']
        for poly in polygons(face):
            points = [(x * 1000, height - y * 1000) for x, y in poly]
            draw.polygon(points, fill=tuple(round(v * 255) for v in INK))
            svg.append('<polygon fill="#020203" points="' + ' '.join(f'{x:.3f},{y:.3f}' for x, y in points) + '"/>')
        svg.append('</svg>')
        png = directory / (face['id'] + '.png')
        image.save(png, optimize=True)
        (directory / (face['id'] + '.svg')).write_text('\n'.join(svg) + '\n')
        face['png_sha256'] = sha(png)
        for i, tape in enumerate(face['tapes']):
            rows.append([face['wall'], face['side'], i, f'{tape["centre_m"] * 1000:.3f}',
                         f'{tape["width_m"] * 1000:.3f}', f'{face["height_m"] * 1000:.3f}',
                         ' '.join(f'{v:.6f}' for v in face['origin_m']), ' '.join(map(str, face['u_axis']))])
    (directory / 'layout.json').write_text(json.dumps(record, indent=2) + '\n')
    with (directory / 'tape-positions-mm.csv').open('w') as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerow(['wall', 'face', 'tape', 'centre_u_mm', 'width_mm', 'height_mm', 'origin_world_m', 'u_axis'])
        writer.writerows(rows)
    return record


def transform_xml(xml, *, wall_texture='off', assets=DEFAULT_ASSETS):
    if wall_texture == 'off':
        return xml
    if wall_texture != PROFILE_ID:
        raise ValueError(f'unknown wall_texture: {wall_texture}')
    assets = Path(assets).resolve()
    record = json.loads((assets / 'layout.json').read_text())
    if walls_from_xml(xml) != record['wall_geometry']:
        raise ValueError('scene walls differ from the fixed physical tape table')
    root = ET.fromstring(xml)
    asset = root.find('asset')
    if asset is None:
        asset = ET.SubElement(root, 'asset')
    body = root.find('worldbody')
    for face in record['faces']:
        name = 'tape_v1_' + face['id']
        if root.find(f".//*[@name='{name}']") is not None:
            raise ValueError('texture dressing already installed')
        png = assets / (face['id'] + '.png')
        if sha(png) != face['png_sha256']:
            raise ValueError('texture asset hash mismatch')
        ET.SubElement(asset, 'texture', name=name + '_tex', type='2d', file=str(png))
        ET.SubElement(asset, 'material', name=name + '_mat', texture=name + '_tex',
                      texrepeat='1 1', texuniform='false', rgba='1 1 1 1',
                      emission='0', specular='0', shininess='0', reflectance='0')
        pos = [c + n * OFFSET_M for c, n in zip(face['centre_m'], face['normal'])]
        ET.SubElement(body, 'geom', name=name, type='plane', pos=' '.join(map(str, pos)),
                      xyaxes=' '.join(map(str, face['u_axis'] + face['v_axis'])),
                      size=f'{face["length_m"] / 2} {face["height_m"] / 2} .1',
                      material=name + '_mat', contype='0', conaffinity='0', mass='0', group='0')
    return ET.tostring(root, encoding='unicode')
