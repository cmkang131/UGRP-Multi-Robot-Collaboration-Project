"""Offline evaluation of real own-RGB frames; labels never enter the controller."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from harness.e2e_end_colors import observe, mask
from harness.e2e_live_mapping import camera_transform
from harness.owncam_view import _pixel_rays


def rays(servo, step=8):
    origin, rotation = camera_transform(servo)
    x, y, normal, valid = _pixel_rays(step)
    directions = np.column_stack((normal, np.ones(len(normal)))) @ rotation.T
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    return origin, directions, x, y, valid


def evaluate(root):
    root = Path(root)
    labels = json.loads((root / 'labels.json').read_text())
    records = []
    for row in labels['frames']:
        raw = (root / row['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('RGB_SHA_MISMATCH:' + row['id'])
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        results = {mode: observe(image, row['commanded_servo'], row['color'], rays, mode)
                   for mode in ('anchor_v2', 'component_v3', 'component_short_v3')}
        records.append(dict(id=row['id'], positive=row['visible'], color=row['color'],
                            legacy_color_pixels=int(mask(image, row['color']).sum()), results=results))
    summary = {}
    for mode in ('anchor_v2', 'component_v3', 'component_short_v3'):
        by_color = {}
        for color in ('teal', 'blue'):
            group = [r for r in records if r['positive'] and r['color'] == color]
            by_color[color] = dict(n=len(group),
                metric_grasp_admitted=sum(bool(r['results'][mode]['end_visible']) for r in group),
                band_presence=sum(bool(r['results'][mode].get('band_visible')) for r in group) if mode != 'anchor_v2' else None,
                reasons=dict(Counter(r['results'][mode]['reason'] for r in group)))
        negatives = [r for r in records if not r['positive']]
        summary[mode] = dict(positives=by_color, negative_n=len(negatives),
            false_grasp_admission=sum(bool(r['results'][mode]['end_visible']) for r in negatives),
            false_band_presence=sum(bool(r['results'][mode].get('band_visible')) for r in negatives) if mode != 'anchor_v2' else None)
    return dict(schema='ugrp.real_band_replay.v1', human_confirmed=labels['human_confirmed'],
                evaluation_only=True, independent_holdout=False, summary=summary, records=records)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('experiments/2026-10-14-e2e18-color-detector'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.root)
    # Compact JSON stays below the project's large-JSON limit for this finite cohort.
    data = (json.dumps(report, separators=(',', ':')) + '\n').encode()
    if len(data) > 65536:
        import subprocess
        if args.output.suffix != '.zst':
            raise ValueError('OUTPUT_REQUIRES_ZSTD')
        encoded = subprocess.check_output(['zstd', '-q', '-c'], input=data)
        assert subprocess.check_output(['zstd', '-qd', '-c'], input=encoded) == data
        args.output.write_bytes(encoded)
        args.output.with_suffix(args.output.suffix+'.manifest.json').write_text(json.dumps(dict(
            sha256=hashlib.sha256(encoded).hexdigest(), decoded_sha256=hashlib.sha256(data).hexdigest(),
            bytes=len(encoded), decoded_bytes=len(data)))+'\n')
    else:
        args.output.write_bytes(data)
    print(json.dumps(report['summary'], indent=2))
