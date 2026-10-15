"""Generate small skirting cube PNGs on gcp2 only; no simulator or rendering."""
from pathlib import Path
import hashlib
import json
import platform
import numpy as np
from PIL import Image
from scripts.generate_scene_textures import MAPS
import argparse


def generate(assets):
    if not platform.node().startswith('ugrp-sim-gcp2'):
        raise RuntimeError('gcp2 asset generation only')
    assets.mkdir(parents=True, exist_ok=False)
    heights = sorted({round(float(w['height_m']), 6) for p in MAPS
                      for w in json.loads(p.read_text())['obstacles'] if w['id'].startswith('wall_')})
    record = {'schema': 'ugrp.scene_contrast_assets.v4', 'heights': {}, 'images': {},
              'wall_rgb': [131, 136, 140], 'skirting_rgb': [78, 81, 83], 'skirting_m': .08,
              'source': 'Khronos ARB_texture_cube_map face axes; same existing cube geometry'}
    for height in heights:
        band = round(1024*.08/height)
        faces = {}
        for attr in ('fileright', 'fileleft', 'fileup', 'filedown', 'filefront', 'fileback'):
            rgb = np.full((1024, 1024, 3), record['wall_rgb'], np.uint8)
            # +/-X: s=-/+Z. +/-Y: t=+/-Z. +/-Z is ceiling/floor face.
            if attr == 'fileright': rgb[:, -band:] = record['skirting_rgb']
            elif attr == 'fileleft': rgb[:, :band] = record['skirting_rgb']
            elif attr == 'fileup': rgb[:band] = record['skirting_rgb']
            elif attr == 'filedown': rgb[-band:] = record['skirting_rgb']
            elif attr == 'fileback': rgb[:] = record['skirting_rgb']
            filename = f'{height}-{attr}.png'
            p = assets/filename
            Image.fromarray(rgb).save(p, compress_level=9)
            faces[attr] = filename
            record['images'][filename] = hashlib.sha256(p.read_bytes()).hexdigest()
        record['heights'][str(height)] = faces
    (assets/'manifest.json').write_text(json.dumps(record, sort_keys=True, indent=2)+'\n')
    print(json.dumps({'assets': str(assets), 'files': len(record['images'])}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    generate(p.parse_args().output)
