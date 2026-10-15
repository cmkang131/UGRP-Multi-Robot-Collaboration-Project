"""Actual RGB/HSV PNG audit for v2, with legacy controls; no simulator imports."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image

from scripts.audit_scene_textures import color_ranges, features
from sim import natural_scene_texture_v2 as texture

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT/'experiments/2026-10-15-scene-tex2'


def measure_palette(rgb_counts, ranges):
    """Exact count on every published RGB pixel, not ideal HSV swatches."""
    keys = np.array(sorted(rgb_counts), np.uint32)
    rgb = np.stack((keys >> 16, (keys >> 8) & 255, keys & 255), axis=-1).astype(np.uint8)[None]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    counts = np.array([rgb_counts[int(k)] for k in keys], np.int64)
    result = []
    for row in ranges:
        mask = np.zeros(hsv.shape[:2], np.uint8)
        for lo, hi in row['ranges']:
            mask |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
        result.append({**row, 'hits': int(counts[mask[0] > 0].sum()), 'N': int(counts.sum())})
    r, g, b = rgb[0].astype(np.int16).T
    for label, mask in [('crate_blue', (b > 140) & (r < 90) & (g < 90)),
                        ('crate_teal', (g > 140) & (b > 60) & (b < g) & (r < 90)),
                        ('crate_pink', (r > 90) & (r > g+25) & (b > g-5) & (r > b))]:
        result.append({'label': label, 'source': 'pinned crate RGB inequalities',
                       'hits': int(counts[mask].sum()), 'N': int(counts.sum())})
    pil = np.asarray(Image.fromarray(rgb).convert('HSV'))[0]
    mask = (pil[:, 0] > 25) & (pil[:, 0] < 90) & (pil[:, 1] > 100) & (pil[:, 2] > 60)
    result.append({'label': 'PIL_beam', 'source': 'harness/own_beam_edge.py:68-71',
                   'hits': int(counts[mask].sum()), 'N': int(counts.sum())})
    return result, {'rgb_min': rgb[0].min(0).tolist(), 'rgb_max': rgb[0].max(0).tolist(),
                    'hsv_min': hsv[0].min(0).tolist(), 'hsv_max': hsv[0].max(0).tolist(),
                    'unique_rgb': len(keys)}


def audit(output):
    output.mkdir(parents=True, exist_ok=False)
    record = texture.manifest()
    ranges, inventory, _ = color_ranges()
    external = json.loads((EXPERIMENT/'color_external_sources.json').read_text())
    for p, digest in external['source_sha256'].items():
        if hashlib.sha256((ROOT/p).read_bytes()).hexdigest() != digest:
            raise ValueError(f'color source changed: {p}')
    ranges += external['additional_hsv_ranges']
    counts = {'floor': {}, 'walls': {}}
    metrics, low, high = [], {}, {}
    for key in record['images']:
        rgb = np.asarray(Image.open(texture.checked_file(key, record, texture.ASSETS)).convert('RGB'))
        kind = 'floor' if key == 'floor' else 'walls'
        values = rgb.astype(np.uint32)
        packed = (values[..., 0] << 16) | (values[..., 1] << 8) | values[..., 2]
        keys, n = np.unique(packed, return_counts=True)
        for k, count in zip(keys, n):
            counts[kind][int(k)] = counts[kind].get(int(k), 0)+int(count)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        metrics.append({'key': key, 'sha256': record['images'][key]['sha256'], **features(gray)})
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2Lab).reshape(-1, 3)
        low[kind] = np.minimum(low.get(kind, np.full(3, 255)), lab.min(0))
        high[kind] = np.maximum(high.get(kind, np.zeros(3)), lab.max(0))
    colors, palettes = {}, {}
    for kind, values in counts.items():
        colors[kind], palettes[kind] = measure_palette(values, ranges)
    floor = np.asarray(Image.open(texture.ASSETS/'floor.png'))
    crops = [features(cv2.cvtColor(floor[y:y+480, x:x+640], cv2.COLOR_RGB2GRAY))
             for x, y in ((128,128),(1152,128),(128,1152),(1152,1152))]
    gap = palettes['floor']['hsv_min'][2]-palettes['walls']['hsv_max'][2]
    result = {'schema': 'ugrp.scene_tex2_png_audit.v1', 'scope': 'all PNG pixels only',
              'profile': texture.PROFILE, 'manifest_sha256': texture.MANIFEST_SHA256,
              'python': sys.version.split()[0], 'opencv': cv2.__version__, 'numpy': np.__version__,
              'palettes': palettes, 'V_interval_gap': gap,
              'Lab_bounding_boxes': {k: [low[k].tolist(), high[k].tolist()] for k in low},
              'color_ranges_per_surface': len(colors['floor']), 'colors': colors,
              'contextual_checks': external['contextual_checks'],
              'source_inventory_count': len(inventory), 'floor_native_crops': crops,
              'camera_verified': False, 'ready_for_execution': False}
    # Keep the primary summary small; full rows and per-image measurements have
    # stable independent hashes and no >64 KiB JSON payload.
    for name, rows in [('image-metrics', metrics), ('color-hits-floor', colors.pop('floor')),
                       ('color-hits-walls', colors.pop('walls'))]:
        p = output/(name+'.json')
        p.write_text(json.dumps(rows, separators=(',', ':'))+'\n')
        result[name] = {'path': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
    del result['colors']
    lines = ['# HSV / RGB 색 범위 전체 픽셀 대조', '',
             '고정/상위집합 대상 색과 어두운/흰 표식. 문맥·지지 마스크는 별도 검증 대상이다.', '',
             '|대상|출처|범위|바닥 n/N|벽 n/N|', '|---|---|---|---|---|']
    floors = json.loads((output/'color-hits-floor.json').read_text())
    walls = json.loads((output/'color-hits-walls.json').read_text())
    for a, b in zip(floors, walls):
        lines.append(f"|{a['label']}|{a['source']}|`{a.get('ranges','RGB/PIL direct inequalities')}`|{a['hits']}/{a['N']}|{b['hits']}/{b['N']}|")
    (output/'color-ranges.md').write_text('\n'.join(lines)+'\n')
    lines = ['# 색 소스 전수 탐색 목록', '',
             'HSV/hsv/inRange 포함 Python을 AST로 검색. 직접 비교와 동적 범위는 별도 고정 목록 및 문맥 검사로 보충한다.', '']
    for entry in inventory:
        lines += [f"## {entry['path']}", '', f"SHA256 `{entry['sha256']}`", '']
        lines += [f"- L{c['line']} {c['classification']}: `{c['expression']}`" for c in entry['inRange_calls']]
        lines.append('')
    (output/'color-source-inventory.md').write_text('\n'.join(lines).rstrip()+'\n')
    (output/'offline-audit.json').write_text(json.dumps(result, indent=2)+'\n')
    return result, metrics, floors, walls


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result, images, floor, walls = audit(args.output)
    print(json.dumps({'images': len(images), 'ranges': len(floor),
                      'max_color_hits': max(r['hits'] for r in floor+walls),
                      'wall_orb_min_median_max': np.percentile([m['orb_count'] for m in images if m['key'] != 'floor'], [0,50,100]).tolist(),
                      'floor_crops': [c['orb_count'] for c in result['floor_native_crops']],
                      'V_interval_gap': result['V_interval_gap']}))
