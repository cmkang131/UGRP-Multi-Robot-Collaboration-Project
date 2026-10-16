"""Read preserved REAL thumbnails, without mistaking them for native frames."""
import argparse
import json
from pathlib import Path
import platform
import cv2
import numpy as np
from scripts.probe_scene_tex3 import measure
from scripts.summarize_scene_tex3 import sha


def run(path, output):
    bgr = cv2.imread(str(path))
    if bgr.shape != (568, 960, 3):
        raise ValueError('unexpected preserved comparison plate')
    # Rectangles manually checked on the preserved plate, solely evaluator
    # annotations of unoccupied neutral table/surface pixels. They are NOT an
    # automatic floor detector or robot observation channel.
    rois = ((5, 5, 85, 200), (240, 5, 315, 75), (240, 5, 315, 150),
            (5, 5, 85, 200), (240, 5, 315, 75), (250, 5, 315, 110))
    rows = []
    for n, roi in enumerate(rois):
        i, j = n % 3, n // 3
        y = 44 if j == 0 else 328
        image = bgr[y:y+240, i*320:(i+1)*320]
        mask = np.zeros((240, 320), bool)
        x0, y0, x1, y1 = roi
        mask[y0:y1, x0:x1] = True
        rows.append({'thumbnail': n, 'native_size_available': False, 'dimensions': [320, 240],
                     'manual_unoccupied_surface_roi': roi,
                     'metrics': measure(image, {'floor': mask, 'wall': np.zeros_like(mask)})['floor']})
    out = {'source': str(path), 'source_sha256': sha(path),
        'git_source': 'experiments/2026-10-06-robot-camera-review/real-post-lift-comparison.jpg',
        'git_blob': 'f3276961fd32e62e213b4287da9200d324445954', 'real_thumbnails': rows,
        'qualification': 'historical real table/surface, downsampled then JPEG composite; original640x480 absent; different surface/distance/lighting; cannot certify real-floor parity',
        'real_floor_native_reference_available': False,
        'user_observation': 'actual robot recognizes floor features well; remains qualitative task motivation'}
    output.write_text(json.dumps(out, indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if not platform.node().startswith('ugrp-sim-gcp2'):
        p.error('gcp2 only')
    run(a.input, a.output)
