"""Post-freeze reporting only: read predictions, audit masks, make evidence figures.

No parameter selection, rendering, physics, or production-source changes.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

import cv2
import numpy as np

from replay import ROOT, dump, rows, sha
from harness.floor_goal_v2 import FloorGoalV2Options, detect_floor_v2


def outline(rgb, mask, color):
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(rgb, contours, -1, color, 2)


def panel(rgb, caption):
    p = cv2.resize(rgb, (480, 360))
    cv2.rectangle(p, (0, 0), (480, 26), (0, 0, 0), -1)
    cv2.putText(p, caption, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, .47, (255, 255, 255), 1)
    return p


def report(raw, experiment, output):
    output.mkdir(parents=True, exist_ok=False)
    selection = json.loads((experiment/'v2-selection.json').read_text())
    for path, digest in selection['code_hashes'].items():
        if sha(ROOT/path) != digest:
            raise ValueError('FROZEN_SOURCE_CHANGED')
    dataset = raw/'static-render'
    receipt = json.loads((dataset/'render_receipt.json').read_text())
    if sha(dataset/'render_receipt.json') != selection['render_receipt_sha256']:
        raise ValueError('RENDER_RECEIPT_CHANGED')
    for path, digest in receipt['artifacts'].items():
        if sha(dataset/path) != digest:
            raise ValueError('RENDER_ARTIFACT_CHANGED: '+path)
    options = FloorGoalV2Options(**selection['selected']['options'])
    geometry = json.loads((dataset/'geometry_ids.json').read_text())
    static, false_sources, static_panels = [], [], []
    for split in ('development', 'confirmation'):
        truth = {r['id']: r for r in rows(dataset/split/'eval_only/truth.jsonl')}
        actors = {r['id']: r for r in rows(dataset/split/'inputs.jsonl')}
        for version in ('v1', 'v2'):
            result = json.loads((raw/f'{split}-{version}/results.json').read_text())
            static.append(result['summary'])
        result = json.loads((raw/f'{split}-v2/results.json').read_text())
        for score in result['frames']:
            # Keep all FP source labels, plus one near B and one partial-occlusion example.
            t = truth[score['id']]
            example = split == 'confirmation' and score['id'] in ('g004-v0', 'g005-v0', 'g031-v1', 'g055-v0')
            if not score['fp'] and not example:
                continue
            row = actors[score['id']]
            rgb = cv2.cvtColor(cv2.imread(row['rgb_path']), cv2.COLOR_BGR2RGB)
            patches, labels, _ = detect_floor_v2(rgb, servo=row['commanded_servo'], profile=row['camera_profile'], options=options)
            prediction = json.loads((raw/f'{split}-v2'/f'{row["id"]}.json').read_text())
            if len(patches) != len(prediction['patches']):
                raise ValueError('PREDICTION_MASK_REPLAY_MISMATCH')
            if score['fp']:
                ids = cv2.imread(t['ids_path'], cv2.IMREAD_UNCHANGED).astype(np.int32)-1
                hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
                for patch in patches:
                    region = labels == patch['component']
                    votes = Counter(ids[region].tolist())
                    geom_id, votes_n = votes.most_common(1)[0]
                    false_sources.append({'split': split, 'id': row['id'], 'component': patch['component'],
                        'dominant_geometry': geometry[geom_id] if geom_id >= 0 else 'background',
                        'dominant_fraction': votes_n/int(region.sum()), 'pixels': int(region.sum()),
                        'hsv_median': np.median(hsv[region], axis=0).tolist(),
                        'target': t['target'], 'occlusion': t['occlusion']})
            if example:
                shown = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                outline(shown, cv2.imread(t['B_mask_path'], 0) > 0, (0, 255, 0))
                outline(shown, labels > 0, (0, 0, 255))
                static_panels.append(panel(shown, f'{row["id"]}: B={score["B_pixels"]} px, FP={score["fp"]}'))
    static_image = np.vstack([np.hstack(static_panels[:2]), np.hstack(static_panels[2:])])
    cv2.imwrite(str(output/'v2-static-examples.jpg'), static_image, [cv2.IMWRITE_JPEG_QUALITY, 88])

    previous = json.loads((experiment/'results.json').read_text())['recordings']
    previous = {r['case']: r for r in previous}
    cases = json.loads((experiment/'cases.json').read_text())
    current = json.loads((raw/'recorded-v2/summary.json').read_text())
    current = {r['case']: r for r in current}
    recorded, recorded_examples, recorded_panels = [], [], []
    for case in cases:
        name = case['id']
        c, p = current[name], previous[name]
        predictions = rows(raw/'recorded-v2'/name/'predictions.jsonl')
        baseline = rows(ROOT/'outputs/mapfree-goal-floor-v1'/name/'predictions.jsonl')
        if sha(raw/'recorded-v2'/name/'predictions.jsonl') != c['predictions_sha256']:
            raise ValueError('RECORDED_PREDICTIONS_CHANGED')
        recorded.append({'case': name, 'camera_profile': c['camera_profile'], 'frames': c['frames'],
            'v1_false_components': p['false_components'], 'v1_false_frames': sum(bool(r['patches']) for r in baseline),
            'v1_false_confirmations': p['false_confirmation_count'], 'v2_false_components': c['false_components'],
            'v2_false_frames': c['false_frames'], 'v2_false_confirmations': c['false_confirmations'],
            'v2_first_false_confirmation_s': min(c['confirmation_times']) if c['confirmation_times'] else None})
        # Descriptive examples selected by maximum accepted pixel area, never by desired outcome.
        selected = max(predictions, key=lambda r: sum(patch['pixels'] for patch in r['patches']))
        frames = {r['frame_id']: r for r in rows(Path(case['episode'])/f'robots/{case["robot"]}/frames.jsonl')}
        frame = frames[selected['frame_id']]
        rgb = cv2.cvtColor(cv2.imread(str(Path(case['episode'])/frame['path'])), cv2.COLOR_BGR2RGB)
        patches, labels, _ = detect_floor_v2(rgb, servo=frame['commanded_servo'], profile=case['camera_profile'], options=options)
        if len(patches) != len(selected['patches']):
            raise ValueError('RECORDED_MASK_REPLAY_MISMATCH')
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        recorded_examples.append({'case': name, 'frame_id': frame['frame_id'], 't': frame['sim_time'],
            'patches': len(patches), 'pixels': int((labels > 0).sum()),
            'hsv_median': np.median(hsv[labels > 0], axis=0).tolist(),
            'fraction_pixels_above_v1_roi': float((labels[:int(np.ceil(rgb.shape[0]*.35))] > 0).sum()/max(1, (labels > 0).sum()))})
        if name in ('s1042', 's1044', 's1045', 's911-r1'):
            shown = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            outline(shown, labels > 0, (0, 0, 255))
            recorded_panels.append(panel(shown, f'{name}: f{frame["frame_id"]}, {len(patches)} false patches'))
    recorded_image = np.vstack([np.hstack(recorded_panels[:2]), np.hstack(recorded_panels[2:])])
    cv2.imwrite(str(output/'v2-recorded-failures.jpg'), recorded_image, [cv2.IMWRITE_JPEG_QUALITY, 88])
    confirmation = next(r for r in static if r['split'] == 'confirmation' and r['version'] == 'v2')
    criteria = {'precision': confirmation['frame_precision'] >= .95, 'recall': confirmation['frame_recall'] >= .9,
                'projection': confirmation['projection_median_m'] <= .1,
                'false_confirmation': confirmation['false_confirmations'] == 0 and
                    all(r['v2_false_confirmations'] == 0 for r in recorded)}
    result = {'static': static, 'recorded': recorded, 'static_false_sources': false_sources,
              'recorded_max_area_examples': recorded_examples, 'criteria': criteria,
              'passed_primary_criteria': sum(criteria.values()), 'total_primary_criteria': len(criteria),
              'render_receipt_sha256': sha(dataset/'render_receipt.json'),
              'selection_sha256': sha(experiment/'v2-selection.json'), 'frozen_commit': '9e4e4cbd',
              'physics_steps': receipt['physics_steps'], 'forward_dynamics_calls': receipt['forward_dynamics_calls'],
              'rendered_frames': receipt['frames'], 'rendered_bytes': receipt['bytes'],
              'render_lock_released': receipt['lock_released']}
    dump(output/'v2-results.json', result)
    # Full local artifacts remain local; only their hashes and compact reports go to Git.
    manifest = {str(path.relative_to(ROOT)): {'bytes': path.stat().st_size, 'sha256': sha(path)}
                for path in sorted(raw.rglob('*')) if path.is_file() and path != output/'v2-artifacts.json'}
    dump(output/'v2-artifacts.json', manifest)
    print(json.dumps({'criteria': criteria, 'static_false_geometry': dict(Counter(r['dominant_geometry'] for r in false_sources))}))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--experiment', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    report(args.raw.resolve(), args.experiment.resolve(), args.output.resolve())
