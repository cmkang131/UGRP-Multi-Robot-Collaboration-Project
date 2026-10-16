"""gcp2 RGB asset transform preserving v1 nominal grayscale (no renderer).

OpenCV Y=.299R+.587G+.114B. RGB offset(-1,0,+3) changes Y by
0.043 levels before rounding and gives a cool wall below the old S20 paint
threshold. This is an authored material comparison, never an image filter.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import cv2
import numpy as np
from PIL import Image
from sim import natural_scene_texture as v1


def generate(output):
    if not platform.node().startswith('ugrp-sim-gcp2'): raise RuntimeError('gcp2 only')
    output.mkdir(parents=True, exist_ok=False)
    record = {'schema': 'ugrp.scene_contrast_luma_assets.v4', 'v1_manifest': v1.MANIFEST_SHA256,
              'offset_rgb': [-1, 0, 3], 'nominal_delta_Y': .043, 'images': {}}
    for key, spec in v1.manifest()['images'].items():
        if key == 'floor': continue
        source = v1.checked_file(key, v1.manifest(), v1.ASSETS)
        before = np.asarray(Image.open(source).convert('RGB'))
        after = (before.astype(np.int16)+np.array([-1, 0, 3])).astype(np.uint8)
        assert np.array_equal(cv2.cvtColor(before, cv2.COLOR_RGB2GRAY), cv2.cvtColor(after, cv2.COLOR_RGB2GRAY))
        hsv = cv2.cvtColor(after, cv2.COLOR_RGB2HSV)
        assert hsv[..., 1].max() < 20
        p = output/source.name
        Image.fromarray(after).save(p, compress_level=9)
        record['images'][key] = {'file': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                                 'source_sha256': spec['sha256'], 'gray_equal_v1': True}
    p = output/'manifest.json'
    p.write_text(json.dumps(record, sort_keys=True, indent=2)+'\n')
    print(hashlib.sha256(p.read_bytes()).hexdigest())


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    generate(p.parse_args().output)
