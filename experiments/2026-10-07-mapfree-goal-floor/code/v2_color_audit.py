"""Offline audit of exact v1 accepted pixels and saved XML colour sources."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import cv2
import numpy as np

from replay import dump, rows, sha


def colour(rgb):
    a = np.array(rgb, np.float32).reshape(1, 1, 3)
    hsv = cv2.cvtColor(a, cv2.COLOR_RGB2HSV).reshape(3)
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).reshape(3)
    return hsv, lab


def palette(scene):
    root = ET.parse(scene).getroot()
    target = np.fromstring(root.find('.//geom[@name="zone_zone_B"]').get('rgba'), sep=' ')
    bh, bl = colour(target[:3])
    grouped = defaultdict(list)
    for node in root.iter():
        if node.tag not in ('geom', 'material', 'texture'):
            continue
        for key in ('rgba', 'rgb1', 'rgb2'):
            if key in node.attrib:
                value = tuple(np.fromstring(node.get(key), sep=' '))
                if len(value) == 3:
                    value += (1.,)
                grouped[(node.tag, value)].append(node.get('name', 'unnamed')+':'+key)
    result = []
    for (kind, rgba), names in grouped.items():
        hsv, lab = colour(rgba[:3])
        hue = min(abs(hsv[0]-bh[0]), 360-abs(hsv[0]-bh[0]))
        result.append({'kind': kind, 'names': names, 'rgba': rgba, 'hsv_float_degrees': hsv.tolist(),
                       'hsv_opencv_u8': cv2.cvtColor(np.round(np.array(rgba[:3])*255).astype(np.uint8).reshape(1, 1, 3),
                                                  cv2.COLOR_RGB2HSV).reshape(3).tolist(),
                       'hue_distance_deg_to_raw_B': float(hue),
                       'rgb_l2_to_raw_B': float(np.linalg.norm(np.array(rgba[:3])-target[:3])),
                       'deltaE76_to_raw_B': float(np.linalg.norm(lab-bl)),
                       'alpha_zero': rgba[3] == 0})
    composites = []
    texture = root.find('.//texture[@name="ground"]')
    for ground_key in ('rgb1', 'rgb2'):
        ground = np.fromstring(texture.get(ground_key), sep=' ')
        for name in ('zone_pickup', 'zone_zone_A', 'zone_zone_B', 'zone_zone_C'):
            rgba = np.fromstring(root.find(f'.//geom[@name="{name}"]').get('rgba'), sep=' ')
            blend = rgba[:3]*rgba[3]+ground*(1-rgba[3])
            hsv, lab = colour(blend)
            composites.append({'name': name, 'ground': ground_key, 'unlit_alpha_blend_rgb': blend.tolist(),
                               'hsv_float_degrees': hsv.tolist(), 'lab': lab.tolist()})
    lights = [n.attrib for n in root.iter() if n.tag in ('light', 'headlight')]
    return {'scene': str(scene), 'sha256': sha(scene), 'raw_B_rgba': target.tolist(),
            'colours': sorted(result, key=lambda x: x['deltaE76_to_raw_B']), 'unlit_composites': composites,
            'lights': lights, 'limitations': 'Raw XML RGB/alpha and unlit blend proxies are not lit JPEG colours. '
                    'DeltaE76 uses OpenCV float sRGB-to-Lab; hue degrees circular. Inactive alpha-zero geoms retained explicitly.'}


def audit(predictions, annotations, output):
    output.mkdir(parents=True, exist_ok=False)
    groups = defaultdict(list)
    frames = []
    annotations = json.loads(annotations.read_text())['components']
    for case in sorted({a['case'] for a in annotations}):
        folder = predictions/case
        pred = {r['frame_id']: r for r in rows(folder/'predictions.jsonl')}
        for a in (r for r in annotations if r['case'] == case):
            r = pred[a['frame_id']]
            if sha(r['rgb_path']) != a['sha256']:
                raise ValueError('ANNOTATION_RGB_CHANGED')
            hsv = cv2.cvtColor(cv2.imread(r['rgb_path']), cv2.COLOR_BGR2HSV)
            lab = cv2.imread(str(folder/r['labels']), cv2.IMREAD_UNCHANGED)
            pixels = hsv[lab == a['component']]
            cohort = 'camera_v3' if case.startswith('s104') else 'legacy'
            groups[(cohort, a['category'])].append(pixels)
            frames.append({**a, 'pixels': len(pixels), 'HSV_p05_median_p95': np.quantile(pixels, [.05, .5, .95], axis=0).tolist(),
                           'hue_histogram': np.bincount(pixels[:, 0], minlength=180).tolist(),
                           'v_below_60_fraction': float((pixels[:, 2] < 60).mean()),
                           'v_above_230_fraction': float((pixels[:, 2] > 230).mean())})
    summary = []
    for (cohort, surface), chunks in sorted(groups.items()):
        pixels = np.concatenate(chunks)
        summary.append({'cohort': cohort, 'surface': surface, 'components': len(chunks), 'pixels': len(pixels),
                        'HSV_p05_median_p95': np.quantile(pixels, [.05, .5, .95], axis=0).tolist()})
    dump(output/'false_hsv.json', {'summary': summary, 'components': frames,
                                  'v1_gate': 'H100..130, S>=35, V>=30; OpenCV uint8 scale'})
    manifests = list(predictions.glob('*/manifest.json'))
    scenes = {Path(json.loads(p.read_text())['case']['episode'])/'scene.xml' for p in manifests}
    dump(output/'palettes.json', [palette(scene) for scene in sorted(scenes)])
    for r in summary:
        print(r['cohort'], r['surface'], r['components'], 'HSV median', r['HSV_p05_median_p95'][1])


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--predictions', type=Path, required=True)
    p.add_argument('--annotations', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    audit(a.predictions, a.annotations, a.output)
