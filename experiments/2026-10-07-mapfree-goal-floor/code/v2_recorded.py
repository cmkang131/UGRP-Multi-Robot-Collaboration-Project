"""Frozen v2 options on the old negative-only recordings; no threshold fitting."""
import argparse
from collections import Counter
import json
from pathlib import Path

import cv2

from replay import ROOT, dump, rows, sample, sha
from harness.self_wall_memory import SelfWallMemory


def replay_case(case, options, baseline, output):
    episode = Path(case['episode'])
    frames = sample(rows(episode/f'robots/{case["robot"]}/frames.jsonl'))
    commands = sorted(rows(episode/f'robots/{case["robot"]}/commands.jsonl'), key=lambda r: round(r['t'], 8))
    memory = SelfWallMemory(case['robot'], self_map='odom_grid_v1', goal_detection='floor_color_v2',
                            goal_detection_options=options)
    output.mkdir(parents=True, exist_ok=False)
    predictions, diagnostics = [], Counter()
    ci = 0
    for frame in frames:
        while ci < len(commands) and commands[ci]['t'] <= frame['sim_time']+1e-8:
            memory.command(commands[ci])
            ci += 1
        path = episode/frame['path']
        if sha(path) != frame['sha256']:
            raise ValueError('RECORDING_RGB_CHANGED')
        rgb = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        patches, _, diag = memory.observe_goal_rgb(rgb, robot_id=case['robot'], frame_id=frame['frame_id'],
            t=frame['sim_time'], commanded_servo=frame['commanded_servo'], camera_profile=case['camera_profile'])
        diagnostics.update(diag)
        predictions.append({'frame_id': frame['frame_id'], 't': frame['sim_time'], 'sha256': frame['sha256'],
                            'pose': memory.self_map.odom.pose, 'patches': patches, 'diagnostics': diag})
    pred = output/'predictions.jsonl'
    pred.write_text(''.join(json.dumps(r)+'\n' for r in predictions))
    dump(output/'memory.json', memory.self_goal.snapshot())
    # Cached independent visibility labels are read only AFTER predictions exist.
    truth_path = baseline/case['id']/'evaluation.json'
    truth = json.loads(truth_path.read_text())['frames']
    expected = {r['frame_id']: r for r in truth}
    if set(expected) != {r['frame_id'] for r in predictions} or any(r['B_visible'] is not False for r in truth):
        raise ValueError('BASELINE_IS_NOT_IDENTICAL_NEGATIVE_COHORT')
    confirmed = [r for r in memory.self_goal.snapshot()['candidates'] if r['confirmed_t'] is not None]
    summary = {'case': case['id'], 'camera_profile': case['camera_profile'], 'frames': len(predictions),
               'false_components': sum(len(r['patches']) for r in predictions),
               'false_frames': sum(bool(r['patches']) for r in predictions),
               'false_confirmations': len(confirmed), 'confirmation_times': [r['confirmed_t'] for r in confirmed],
               'recall': None, 'projection_median_m': None, 'negative_truth_sha256': sha(truth_path),
               'predictions_sha256': sha(pred), 'diagnostics': dict(diagnostics)}
    dump(output/'summary.json', summary)
    print(case['id'], summary['false_components'], 'false components;', len(confirmed), 'false confirmations', flush=True)
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--cases', type=Path, required=True)
    p.add_argument('--selection', type=Path, required=True)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    selected = json.loads(args.selection.read_text())
    for path, digest in selected['code_hashes'].items():
        if sha(ROOT/path) != digest:
            raise ValueError('FROZEN_SOURCE_CHANGED')
    results = [replay_case(c, selected['selected']['options'], args.baseline, args.output/c['id'])
               for c in json.loads(args.cases.read_text())]
    dump(args.output/'summary.json', results)
