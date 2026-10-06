"""Read-only post-freeze diagnostics and compact provenance/result delivery."""
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path

import cv2
import numpy as np

from replay import ROOT, dump, rows, sha
from harness.floor_goal import FloorGoalOptions, commanded_camera, floor_intersections, optical_rays
from harness.floor_goal_v2 import FloorGoalV2Options, detect_floor_v2
from harness.floor_goal_v3 import FloorGoalV3Options, detect_floor_v3, footprint, metric_rejection
from harness.floor_goal_self_mask import self_body_mask


def read(path):
    return json.loads(path.read_text())


def overlay(image, mask, color):
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(image, contours, -1, color, 2)


def panel(rgb, bmask, labels, title):
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    overlay(bgr, bmask, (0, 255, 0))
    overlay(bgr, labels > 0, (0, 0, 255))
    out = cv2.resize(bgr, (480, 360))
    cv2.rectangle(out, (0, 0), (480, 26), (0, 0, 0), -1)
    cv2.putText(out, title, (4, 18), cv2.FONT_HERSHEY_SIMPLEX, .48, (255, 255, 255), 1)
    return out


def main():
    exp = ROOT/'experiments/2026-10-07-mapfree-goal-floor'
    raw = ROOT/'outputs/mapfree-goal-floor-v3'
    out = raw/'report-complete'
    out.mkdir(exist_ok=False)
    selection = read(exp/'v3-selection.json')
    for path, digest in selection['code_hashes'].items():
        if sha(ROOT/path) != digest:
            raise ValueError('FROZEN_SOURCE_CHANGED')
    receipt = read(raw/'static-render/render_receipt.json')
    assert sha(raw/'static-render/render_receipt.json') == selection['render_receipt_sha256']
    for path, digest in receipt['artifacts'].items():
        if sha(raw/'static-render'/path) != digest:
            raise ValueError('RENDER_ARTIFACT_CHANGED')
    opts = FloorGoalV3Options(**selection['selected']['options'])
    v2opts = FloorGoalV2Options(**read(exp/'v2-selection.json')['selected']['options'])
    static = [read(raw/f'{split}-{version}/results.json')['summary']
              for split in ('development', 'confirmation') for version in ('v1', 'v2', 'v3')]
    retro = []
    for split in ('development', 'confirmation'):
        for version in ('v1', 'v2'):
            retro.append(read(ROOT/f'outputs/mapfree-goal-floor-v2/{split}-{version}/results.json')['summary'])
        retro.append(read(raw/f'retrospective-{split}-v3/results.json')['summary'])
    old = {r['case']: r for r in read(exp/'results.json')['recordings']}
    v2record = {r['case']: r for r in read(ROOT/'outputs/mapfree-goal-floor-v2/recorded-v2/summary.json')}
    recorded = []
    for r in read(raw/'recorded-v3/summary.json'):
        name = r['case']
        assert sha(raw/'recorded-v3'/name/'predictions.jsonl') == r['predictions_sha256']
        recorded.append({**r, 'v1_false_components': old[name]['false_components'],
                         'v1_false_confirmations': old[name]['false_confirmation_count'],
                         'v2_false_components': v2record[name]['false_components'],
                         'v2_false_confirmations': v2record[name]['false_confirmations']})
    missed, pictures = [], []
    for split in ('development', 'confirmation'):
        actors = {r['id']: r for r in rows(raw/'static-render'/split/'inputs.jsonl')}
        truths = {r['id']: r for r in rows(raw/'static-render'/split/'eval_only/truth.jsonl')}
        scores2 = {r['id']: r for r in read(raw/f'{split}-v2/results.json')['frames']}
        scores3 = {r['id']: r for r in read(raw/f'{split}-v3/results.json')['frames']}
        for name, s in scores3.items():
            lost = bool(scores2[name]['tp'] and s['fn'])
            example = split == 'confirmation' and (lost or s['tp'] or scores2[name]['fp'])
            if not lost and not example:
                continue
            row, truth = actors[name], truths[name]
            rgb = cv2.cvtColor(cv2.imread(row['rgb_path']), cv2.COLOR_BGR2RGB)
            bmask = cv2.imread(truth['B_mask_path'], 0) > 0
            params = {'servo': row['commanded_servo'], 'profile': row['camera_profile']}
            patches3, labels3, diag = detect_floor_v3(rgb, **params, options=opts)
            if lost:
                masked = rgb.copy()
                masked[self_body_mask(row['commanded_servo'], row['camera_profile'], rgb.shape[1], rgb.shape[0])] = 0
                patches2, labels2, _ = detect_floor_v2(masked, **params, options=v2opts)
                origin, axes = commanded_camera(**{'servo': row['commanded_servo'], 'profile': row['camera_profile']})
                points, _ = floor_intersections(optical_rays(rgb.shape[1], rgb.shape[0]), origin, axes,
                                                downward_min=opts.downward_min, max_range_m=opts.max_range_m)
                reasons = []
                for p in patches2:
                    region = labels2 == p['component']
                    if (region & bmask).sum() >= .5*region.sum():
                        shape = footprint(region, points)
                        reasons.append({'reason': metric_rejection(shape, opts), **shape})
                missed.append({'split': split, 'id': name, 'B_pixels': int(bmask.sum()), 'reasons': reasons,
                               'diagnostics': diag, 'arm': truth['arm'], 'distance': truth['distance'], 'occlusion': truth['occlusion']})
            category = ('missed B' if lost else 'occluded B' if s['tp'] and truth['occlusion'] != 'original'
                        else 'true B' if s['tp'] else 'FP rejected')
            if split == 'confirmation' and category not in [r[0] for r in pictures]:
                pictures.append((category, panel(rgb, bmask, labels3, f'{name}: {category}, B={int(bmask.sum())} px')))
    # Keep a clearly labeled 2x2 evidence sheet; no synthetic imagery.
    tiles = [p for _, p in pictures[:4]]
    while len(tiles) < 4:
        tiles.append(np.zeros((360, 480, 3), np.uint8))
    cv2.imwrite(str(out/'v3-confirmation-examples.jpg'), np.vstack([np.hstack(tiles[:2]), np.hstack(tiles[2:])]),
                [cv2.IMWRITE_JPEG_QUALITY, 88])
    conf = next(r for r in static if r['split'] == 'confirmation' and r['version'] == 'v3')
    criteria = {'precision': conf['frame_precision'] >= .95, 'recall': conf['frame_recall'] >= .9,
                'projection': conf['projection_median_m'] <= .1,
                'static_false_confirmation': conf['false_confirmations'] == 0,
                'recorded_false_confirmation': all(r['false_confirmations'] == 0 for r in recorded)}
    # The raw evaluator's options field is the caller's shared argument; factories
    # override it for v1/v2. Record the effective algorithm options unambiguously.
    effective = {'v1': asdict(FloorGoalOptions()), 'v2': asdict(v2opts), 'v3': asdict(opts)}
    result = {'new_static': static, 'retrospective_static': retro, 'recorded': recorded, 'criteria': criteria,
              'criteria_passed': sum(criteria.values()), 'criteria_total': len(criteria),
              'additional_missed_B_vs_v2': missed, 'visibility': read(raw/'visibility-audit.json'),
              'new_v2_false_sources': read(raw/'new-v2-false-sources.json'),
              'effective_options': effective, 'frozen_commit': '3bbf3337', 'render_source_commit': receipt['source_sha'],
              'selection_sha256': sha(exp/'v3-selection.json'), 'code_hashes': selection['code_hashes'],
              'render_receipt_sha256': sha(raw/'static-render/render_receipt.json'), 'report_source_sha256': sha(__file__)}
    dump(out/'v3-results.json', result)
    dump(out/'v3-artifacts.json', {str(p.relative_to(ROOT)): {'bytes': p.stat().st_size, 'sha256': sha(p)}
                                 for p in sorted(raw.rglob('*')) if p.is_file() and p != out/'v3-artifacts.json'})
    print(json.dumps({'criteria': criteria, 'additional_missed_reasons': dict(Counter(x['reason'] for r in missed for x in r['reasons']))}))


if __name__ == '__main__':
    main()
