"""Evaluation ONLY: saved actual camera/base poses and authored floor B geometry.

No simulation loading/forward/rendering, no predictor callback. Full-resolution
ray/box arithmetic supplies an upper bound on B visibility. A zero upper bound
is a certified negative even without dynamic-body occlusion labels; nonzero
upper bounds remain unscored unless an independently reviewed mask is supplied.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import cv2
import numpy as np

from replay import ROOT, dump, rows, sha
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix


def box_entry(origin, direction, lower, upper):
    """Ray/slab intersection, including parallel rays. No MuJoCo dependency."""
    parallel = abs(direction) < 1e-12
    safe = np.where(parallel, 1., direction)
    a, b = (lower-origin)/safe, (upper-origin)/safe
    near = np.where(parallel, -np.inf, np.minimum(a, b)).max(axis=-1)
    far = np.where(parallel, np.inf, np.maximum(a, b)).min(axis=-1)
    outside = (parallel & ((origin < lower) | (origin > upper))).any(axis=-1)
    return np.where((far >= np.maximum(near, 0.)) & ~outside, np.maximum(near, 0.), np.inf)


def ray_image(width, height):
    yy, xx = np.indices((height, width))
    k = np.asarray(scaled_camera_matrix(width, height))
    uv = np.stack([xx, yy], axis=-1).astype(float)
    xy = cv2.fisheye.undistortPoints(uv.reshape(-1, 1, 2), k, np.array(CAMERA_FISHEYE_D)).reshape(height, width, 2)
    ideal = xy*[k[0, 0], k[1, 1]] + k[:2, 2]
    valid = ((ideal >= 0) & (ideal < [width, height])).all(axis=-1)
    return np.concatenate([xy, np.ones((height, width, 1))], axis=-1), valid


def visibility_upper(origin, rotation, rays, image_valid, region, walls):
    direction = rays @ rotation.T
    with np.errstate(divide='ignore', invalid='ignore'):
        depth = (.0011-origin[2])/direction[..., 2]
        points = origin + direction*depth[..., None]
    valid = image_valid & np.isfinite(points).all(axis=-1) & (depth > 0.)
    front = np.full(depth.shape, np.inf)
    for lower, upper in walls:
        front = np.minimum(front, box_entry(origin, direction, lower, upper))
    unobstructed = valid & (depth < front-1e-6)
    b = unobstructed & (abs(points[..., :2]-region['center_m']) <= region['half_extents_m']).all(axis=-1)
    return b, points, valid & ~unobstructed


def evaluate(folder, manual_visibility, false_labels):
    manifest = json.loads((folder/'manifest.json').read_text())
    for relative, digest in manifest['artifacts'].items():
        if sha(folder/relative) != digest:
            raise ValueError('SEALED_PREDICTION_CHANGED')
    case = manifest['case']
    episode = Path(case['episode'])
    predictions = rows(folder/'predictions.jsonl')
    memory = json.loads((folder/'memory.json').read_text())
    no_camera = case['camera_truth'] == 'none'
    manual = {r['frame_id']: r for r in manual_visibility['frames'] if r['case'] == case['id']}
    labels = {(r['frame_id'], r['component']): r for r in false_labels if r['case'] == case['id']}
    gt_sources = []
    if not no_camera:
        map_path, scene_path = episode/'inputs/static_map.json', episode/'scene.xml'
        gt_sources += [map_path, scene_path]
        regions = json.loads(map_path.read_text())['regions']
        walls = []
        for geom in ET.parse(scene_path).getroot().find('worldbody').findall('geom'):
            if geom.get('name', '').startswith('zone_wall'):
                center = np.fromstring(geom.get('pos'), sep=' ')
                half = np.fromstring(geom.get('size'), sep=' ')
                walls.append((center-half, center+half))
        if not walls:
            raise ValueError('MISSING_EVAL_STATIC_WALLS')
        if case['camera_truth'] == 'cached_camera_pose':
            path = episode/'eval_only/camera-pose.jsonl'
            cameras = {round(r['t'], 7): (np.array(r['camera_cached_xyz_m']), np.array(r['camera_cached_optical_rotation']))
                       for r in rows(path)}
        else:
            path = episode/f'eval_only/{case["robot"]}/camera_labels.jsonl'
            cameras = {round(r['t'], 7): (np.array(r['base_position_m'])+np.array(r['base_rotation'])@r['origin_m'],
                                         np.array(r['base_rotation'])@r['rotation']) for r in rows(path)}
        gt_sources.append(path)
    results = []
    fp_types = Counter()
    for prediction in predictions:
        shape = cv2.imread(prediction['rgb_path']).shape
        labels_image = (np.zeros(shape[:2], np.uint16) if prediction['labels'] is None else
                        cv2.imread(str(folder/prediction['labels']), cv2.IMREAD_UNCHANGED))
        if no_camera:
            label = manual[prediction['frame_id']]
            if label['sha256'] != prediction['sha256']:
                raise ValueError('MANUAL_LABEL_FRAME_MISMATCH')
            visible = bool(label['B_visible'])
            upper_pixels = None
            # A positive RGB-only frame needs reviewed component masks before scoring.
            evaluable = not visible
            bmask = np.zeros(shape[:2], bool)
            points = wall_mask = None
        else:
            origin, rotation = cameras[round(prediction['t'], 7)]
            rays, lens_valid = ray_image(shape[1], shape[0])
            bmask, points, wall_mask = visibility_upper(origin, rotation, rays, lens_valid, regions['zone_B'], walls)
            upper_pixels = int(bmask.sum())
            visible = upper_pixels >= 64
            # Conservative: only zero/small upper bounds certify negative frames.
            evaluable = not visible
        component_results = []
        for patch in prediction['patches']:
            key = (prediction['frame_id'], patch['component'])
            mask = labels_image == patch['component']
            overlap = float((mask & bmask).sum()/max(1, mask.sum()))
            audit = labels.get(key)
            category = audit['category'] if audit else 'unreviewed'
            if evaluable:
                fp_types[category] += 1
            static_category = None
            if points is not None:
                counts = {'static_wall': int((mask & wall_mask).sum())}
                remaining = mask & ~wall_mask & np.isfinite(points).all(axis=-1)
                for name, reg in regions.items():
                    inside = (abs(points[..., :2]-reg['center_m']) <= reg['half_extents_m']).all(axis=-1)
                    counts[name] = int((remaining & inside).sum())
                    remaining &= ~inside
                counts['other_floor_or_dynamic_occluder'] = int(remaining.sum())
                static_category = counts
            component_results.append({'component': patch['component'], 'track_id': patch['track_id'],
                                      'status': 'false_positive' if evaluable else 'unscored',
                                      'B_upper_overlap': overlap, 'manual_category': category,
                                      'static_ray_pixel_counts': static_category})
        results.append({'frame_id': prediction['frame_id'], 't': prediction['t'], 'B_upper_pixels': upper_pixels,
                        'B_visible': False if evaluable else None, 'evaluable': evaluable,
                        'method': 'RGB_manual_negative' if no_camera else 'full_resolution_static_occlusion_upper_bound',
                        'components': component_results})
    scored = sum(r['evaluable'] for r in results)
    detections = sum(len(r['components']) for r in results if r['evaluable'])
    positive_unscored = sum(not r['evaluable'] for r in results)
    # This diagnostic cohort has no adjudicated positive masks. Never create
    # successful recall/projection values from an empty denominator.
    summary = {'case': case['id'], 'camera_profile': case['camera_profile'], 'split': case['split'],
               'frames': len(results), 'scored_frames': scored, 'unscored_frames': positive_unscored,
               'B_visible_frames': 0, 'true_components': 0, 'false_components': detections,
               'component_precision': 0. if detections else None, 'frame_recall': None,
               'projection_median_m': None, 'projection_p95_m': None, 'own_odom_median_m': None,
               'first_correct_confirmation_s': None,
               'first_candidate_confirmation_s': min((x['confirmed_t'] for x in memory['candidates']
                                                       if x['confirmed_t'] is not None), default=None),
               'confirmed_candidates': sum(x['confirmed_t'] is not None for x in memory['candidates']),
               'false_confirmation_count': (sum(x['confirmed_t'] is not None for x in memory['candidates'])
                                             if not positive_unscored else None),
               'false_component_types': dict(fp_types),
               'maximum_B_visibility_upper_pixels': max((r['B_upper_pixels'] or 0 for r in results), default=0)
                    if not no_camera else None,
               'limitations': 'No adjudicated B-positive samples: recall and both projection/odom error N/A. '
                              'Nonzero visibility upper bound requires independent occlusion annotation.',
               'prediction_manifest_sha256': sha(folder/'manifest.json'),
               'gt_inputs': [{'path': str(p), 'sha256': sha(p)} for p in gt_sources]}
    dump(folder/'evaluation.json', {'summary': summary, 'frames': results})
    print(case['id'], 'scored', scored, 'unscored', positive_unscored, 'FP', detections, dict(fp_types), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--manual-visibility', type=Path, required=True)
    parser.add_argument('--false-labels', type=Path, required=True)
    args = parser.parse_args()
    manual = json.loads(args.manual_visibility.read_text())
    false = json.loads(args.false_labels.read_text())['components']
    summaries = [evaluate(p.parent, manual, false) for p in sorted(args.predictions.glob('*/manifest.json'))]
    dump(args.predictions/'summary.json', {'recordings': summaries,
        'manual_visibility_sha256': sha(args.manual_visibility), 'false_labels_sha256': sha(args.false_labels),
        'evaluation_source_sha256': sha(Path(__file__))})
