"""Audit every v2 false confirmation and its pre-confirmation supporting patches."""
import json
from pathlib import Path

import cv2
import numpy as np

from replay import ROOT, dump, rows, sha
from harness.floor_goal_v2 import FloorGoalV2Options, detect_floor_v2


def main():
    exp = ROOT/'experiments/2026-10-07-mapfree-goal-floor'
    output = ROOT/'outputs/mapfree-goal-floor-v3/diagnosis'
    output.mkdir(parents=True, exist_ok=False)
    opts = FloorGoalV2Options(**json.loads((exp/'v2-selection.json').read_text())['selected']['options'])
    result, thumbnails = [], []
    for case in json.loads((exp/'cases.json').read_text()):
        episode = Path(case['episode'])
        previous = ROOT/'outputs/mapfree-goal-floor-v2/recorded-v2'/case['id']
        tracks = [t for t in json.loads((previous/'memory.json').read_text())['candidates'] if t['confirmed_t'] is not None]
        predictions = rows(previous/'predictions.jsonl')
        frames = {f['frame_id']: f for f in rows(episode/f'robots/{case["robot"]}/frames.jsonl')}
        cache = {}
        for track in tracks:
            observations = []
            for p in predictions:
                patches = [a for a in p['patches'] if a['track_id'] == track['id'] and p['t'] <= track['confirmed_t']]
                if not patches:
                    continue
                frame = frames[p['frame_id']]
                if frame['frame_id'] not in cache:
                    rgb_path = episode/frame['path']
                    if sha(rgb_path) != frame['sha256']:
                        raise ValueError('RECORDING_CHANGED')
                    bgr = cv2.imread(str(rgb_path))
                    _, labels, _ = detect_floor_v2(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB),
                        servo=frame['commanded_servo'], profile=case['camera_profile'], options=opts)
                    cache[frame['frame_id']] = (bgr, labels)
                bgr, labels = cache[frame['frame_id']]
                for patch in patches:
                    yy, xx = np.where(labels == patch['component'])
                    hull = np.array(patch['hull_body_m'], np.float32)
                    rect = cv2.minAreaRect(hull)
                    observation = {'frame_id': p['frame_id'], 't': p['t'], 'component': patch['component'],
                        'rgb_path': str(episode/frame['path']), 'sha256': frame['sha256'],
                        'centroid_px': [float(xx.mean()), float(yy.mean())],
                        'bbox_xywh_px': [int(xx.min()), int(yy.min()), int(xx.max()-xx.min()+1), int(yy.max()-yy.min()+1)],
                        'pixels': len(xx), 'projected_hull_area_m2': float(cv2.contourArea(hull)),
                        'projected_rect_sides_m': sorted(rect[1]), 'center_body_m': patch['center_body_m'],
                        'center_odom_m': patch['center_odom_m'],
                        'hsv_median': np.median(cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[labels == patch['component']], axis=0).tolist()}
                    observations.append(observation)
            item = {'case': case['id'], 'robot': case['robot'], 'profile': case['camera_profile'],
                    'track': track['id'], 'confirmed_t': track['confirmed_t'], 'observations': observations,
                    'category': 'unreviewed', 'classification_method': 'RGB review; not inferred from false-positive label alone'}
            # All supporting patches, including small early patches, remain in JSON.
            chosen = max(observations, key=lambda p: p['pixels'])
            item['representative'] = {k: chosen[k] for k in ('frame_id', 'component', 't')}
            image, labels = cache[chosen['frame_id']]
            image = image.copy()
            contours, _ = cv2.findContours((labels == chosen['component']).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(image, contours, -1, (0, 0, 255), 2)
            tile = cv2.resize(image, (320, 240))
            cv2.rectangle(tile, (0, 0), (320, 28), (0, 0, 0), -1)
            cv2.putText(tile, f'{len(result)+1}: {case["id"]} T{track["id"]} f{chosen["frame_id"]}',
                        (3, 17), cv2.FONT_HERSHEY_SIMPLEX, .40, (255, 255, 255), 1)
            thumbnails.append(tile)
            result.append(item)
    for start in range(0, len(thumbnails), 12):
        tiles = thumbnails[start:start+12]
        tiles += [np.zeros((240, 320, 3), np.uint8)]*(12-len(tiles))
        contact = np.vstack([np.hstack(tiles[i:i+3]) for i in range(0, 12, 3)])
        cv2.imwrite(str(output/f'confirmations-{start//12}.jpg'), contact)
    dump(output/'confirmations.json', result)
    print('confirmed tracks', len(result), 'supporting components', sum(len(r['observations']) for r in result))


if __name__ == '__main__':
    main()
