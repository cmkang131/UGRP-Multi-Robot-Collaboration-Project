"""Offline DEV-only threshold selection, then sealed static-set comparison.

Actor inference consumes only own RGB/servo/commands. GT masks and world camera
poses enter scoring after inference, never the detector or memory API.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import itertools
import json
from pathlib import Path

import cv2
import numpy as np

from replay import ROOT, dump, rows, sha
from harness.floor_goal import FloorGoalMemory, floor_intersections, optical_rays
from harness.floor_goal_v2 import FloorGoalMemoryV2, FloorGoalV2Options, detect_floor_v2
from harness.self_odom_grid import CommandOdometry, transform
from harness.floor_goal_v3 import FloorGoalMemoryV3, FloorGoalV3Options
from harness.floor_goal_self_mask import self_body_mask


def image(row):
    if sha(row['rgb_path']) != row['rgb_sha256']:
        raise ValueError('STATIC_RGB_CHANGED')
    return cv2.cvtColor(cv2.imread(row['rgb_path']), cv2.COLOR_BGR2RGB)


def truth_image(row):
    if sha(row['B_mask_path']) != row['B_sha256']:
        raise ValueError('STATIC_TRUTH_CHANGED')
    return cv2.imread(row['B_mask_path'], cv2.IMREAD_GRAYSCALE) > 0


def frame_score(patches, labels, truth, mask, min_b_pixels=256):
    """Mislocalized positives are both FP and FN. Small B frames are unscored."""
    b_pixels = int(mask.sum())
    matches, errors = [], []
    if 0 < b_pixels < min_b_pixels:
        return {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0, 'unscored': 1,
                'positive': 0, 'matches': [], 'errors_m': [], 'B_pixels': b_pixels}
    for patch in patches:
        region = labels == patch['component']
        hit = region & mask
        matched = bool(b_pixels >= min_b_pixels and hit.sum() >= .5*region.sum())
        matches.append({'component': patch['component'], 'track_id': patch.get('track_id'), 'true': matched})
        if matched:
            origin = np.array(truth['camera_xyz'])
            origin[2] -= .0011  # Paint surface z; XY intersections are unchanged by adding it back.
            rays = optical_rays(mask.shape[1], mask.shape[0])[hit]
            gt_points, valid = floor_intersections(rays, origin, np.array(truth['camera_rotation']).T,
                                                  downward_min=0., max_range_m=float('inf'))
            if not valid.all():
                raise ValueError('B_GT_MASK_HAS_NON_FLOOR_RAY')
            projected = transform([patch['center_body_m']], truth['base_pose'])[0]
            errors.append(float(np.linalg.norm(projected-gt_points[:, :2].mean(axis=0))))
    positive = b_pixels >= min_b_pixels
    tp = positive and any(r['true'] for r in matches)
    return {'tp': int(tp), 'fp': int(bool(patches) and not tp), 'fn': int(positive and not tp),
            'tn': int(not positive and not patches), 'unscored': 0, 'positive': int(positive),
            'matches': matches, 'errors_m': errors, 'B_pixels': b_pixels}


def summarize(scored):
    counts = Counter()
    errors = []
    for row in scored:
        counts.update({k: row[k] for k in ('tp', 'fp', 'fn', 'tn', 'unscored', 'positive')})
        errors += row['errors_m']
    return {**dict(counts), 'frame_precision': counts['tp']/(counts['tp']+counts['fp']) if counts['tp']+counts['fp'] else None,
            'frame_recall': counts['tp']/counts['positive'] if counts['positive'] else None,
            'projection_median_m': float(np.median(errors)) if errors else None,
            'projection_p95_m': float(np.quantile(errors, .95)) if errors else None,
            'projection_samples': len(errors)}


def run(dataset, split, version, options, output=None):
    actors = rows(dataset/split/'inputs.jsonl')
    # Truth held in a separate table and never passed to the actor/memory.
    truth = {r['id']: r for r in rows(dataset/split/'eval_only/truth.jsonl')}
    predictions, scored, confirmations = [], [], []
    by_group = defaultdict(list)
    for row in actors:
        by_group[row['group']].append(row)
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
    for group, inputs in sorted(by_group.items()):
        baseline = json.loads((ROOT/'experiments/2026-10-07-mapfree-goal-floor/v2-selection.json').read_text())['selected']['options']
        memory = (FloorGoalMemory('r3') if version == 'v1' else
                  FloorGoalMemoryV2('r3', options=baseline) if version == 'v2' else FloorGoalMemoryV3('r3', options=options))
        odom = CommandOdometry()
        sent = set()
        track_hits = defaultdict(set)
        for row in inputs:
            for command in row['commands']:
                key = json.dumps(command, sort_keys=True)
                if key not in sent:
                    odom.command(command)
                    sent.add(key)
            pose = odom.advance(row['t'])
            patches, labels, diag = memory.observe(image(row), robot_id='r3', frame_id=row['id'], t=row['t'], pose=pose,
                servo=row['commanded_servo'], profile=row['camera_profile'], settled=True)
            # Serialize actor outputs before evaluating this frame.
            prediction = {'id': row['id'], 'pose': pose, 'patches': patches, 'diagnostics': diag}
            predictions.append(prediction)
            if output is not None:
                dump(output/(row['id']+'.json'), prediction)
            score = frame_score(patches, labels, truth[row['id']], truth_image(truth[row['id']]))
            for match in score['matches']:
                if match['true']:
                    track_hits[match['track_id']].add(row['id'])
            scored.append({'id': row['id'], 'group': group, **score})
        for track in memory.snapshot()['candidates']:
            if track['confirmed_t'] is not None:
                confirmations.append({'group': group, 'track': track['id'], 't': track['confirmed_t'],
                                      'true_views': len(track_hits[track['id']]),
                                      'true': len(track_hits[track['id']]) >= 3})
    summary = {**summarize(scored), 'split': split, 'version': version, 'frames': len(scored), 'groups': len(by_group),
               'true_confirmations': sum(c['true'] for c in confirmations),
               'false_confirmations': sum(not c['true'] for c in confirmations),
               'negative_three_view_groups': sum(all(not r['positive'] and not r['unscored'] for r in scored if r['group'] == group)
                                                 for group in by_group)}
    if output is not None:
        dump(output/'results.json', {'summary': summary, 'frames': scored, 'confirmations': confirmations, 'options': options})
    return summary


def tune(dataset, registration, output):
    """Only development paths may be read. Confirmation is opened by a later command."""
    output.mkdir(parents=True, exist_ok=False)
    config = json.loads(registration.read_text())
    baseline = json.loads((ROOT/'experiments/2026-10-07-mapfree-goal-floor/v2-selection.json').read_text())['selected']['options']
    search = config['threshold_search']
    candidates = []
    for area, overlap, residual in itertools.product(search['minimum_observed_area_m2'], search['temporal_overlap_min'], search['temporal_center_max_m']):
        options = {**baseline, 'minimum_observed_area_m2': area, 'temporal_overlap_min': overlap, 'temporal_center_max_m': residual}
        result = run(dataset, 'development', 'v3', options)
        candidates.append({'options': options, 'summary': result})
    def key(candidate):
        s = candidate['summary']
        # Stable product order is the declared tie break: no hidden confirmation use.
        return (s['frame_precision'] if s['frame_precision'] is not None else -1,
                s['frame_recall'] if s['frame_recall'] is not None else -1, -s['false_confirmations'], s['true_confirmations'])
    selected = max(candidates, key=key)
    files = ['harness/floor_goal.py', 'harness/floor_goal_v2.py', 'harness/floor_goal_v3.py',
             'harness/floor_goal_self_mask.py', 'harness/data/floor_goal_self_geometry.json',
             'harness/self_wall_memory.py', 'harness/self_odom_grid.py', 'harness/visual_arm.py',
             'sim/masterpi_camera_profile.py', 'experiments/2026-10-07-mapfree-goal-floor/code/v3_evaluate.py']
    dump(output/'selection.json', {'selected': selected, 'candidates': candidates, 'registration_sha256': sha(registration),
         'render_receipt_sha256': sha(dataset/'render_receipt.json'),
         'retrospective_receipt_sha256': sha(ROOT/'outputs/mapfree-goal-floor-v2/static-render/render_receipt.json'),
         'code_hashes': {p: sha(ROOT/p) for p in files}, 'confirmation_opened': False})
    print(json.dumps(selected['summary']), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--dataset', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    sub = p.add_subparsers(dest='mode', required=True)
    t = sub.add_parser('tune')
    t.add_argument('--registration', type=Path, required=True)
    e = sub.add_parser('evaluate')
    e.add_argument('--selection', type=Path, required=True)
    e.add_argument('--split', choices=['development', 'confirmation'], required=True)
    e.add_argument('--version', choices=['v1', 'v2', 'v3'], required=True)
    e.add_argument('--retrospective', action='store_true')
    args = p.parse_args()
    if args.mode == 'tune':
        tune(args.dataset, args.registration, args.output)
    else:
        selection = json.loads(args.selection.read_text())
        for path, digest in selection['code_hashes'].items():
            if sha(ROOT/path) != digest:
                raise ValueError('FROZEN_SOURCE_CHANGED')
        if sha(args.dataset/'render_receipt.json') != selection['retrospective_receipt_sha256' if args.retrospective else 'render_receipt_sha256']:
            raise ValueError('FROZEN_DATASET_CHANGED')
        print(json.dumps(run(args.dataset, args.split, args.version, selection['selected']['options'], args.output)))
