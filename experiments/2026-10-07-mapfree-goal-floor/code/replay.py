"""Offline predictor. Input whitelist: own JPEG, issued commands, static camera profile.

Never opens static maps, scene XML, trajectory or evaluation camera poses. The
separate evaluate.py opens them only after verifying a sealed prediction manifest.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import cv2

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from harness.floor_goal import FloorGoalOptions
from harness.self_wall_memory import SelfWallMemory


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def sample(frames):
    selected = []
    for f in frames:
        if not selected or f['sim_time']-selected[-1]['sim_time'] >= 2.-1e-8:
            selected.append(f)
    if selected and selected[-1]['frame_id'] != frames[-1]['frame_id']:
        selected.append(frames[-1])
    return selected


def predict(case, output):
    ep = Path(case['episode'])
    robot = case['robot']
    paths = [ep/f'robots/{robot}/{name}.jsonl' for name in ('frames', 'commands')]
    frames = rows(paths[0])
    commands = rows(paths[1])
    # Initial-servo t can differ from first frame/hold by 1e-14. Stable ordering
    # retains recorded ties and CommandOdometry's existing 1e-8 time tolerance.
    commands.sort(key=lambda c: round(c['t'], 8))
    memory = SelfWallMemory(robot, self_map='odom_grid_v1', goal_detection='floor_color_v1')
    output.mkdir(parents=True, exist_ok=False)
    (output/'labels').mkdir()
    chosen = sample(frames)
    ci = 0
    predictions = []
    sources = [{'path': str(p), 'sha256': sha(p)} for p in paths]
    diagnostics = Counter()
    for frame in chosen:
        t = frame['sim_time']
        while ci < len(commands) and commands[ci]['t'] <= t+1e-8:
            memory.command(commands[ci])
            ci += 1
        path = ep/frame['path']
        digest = sha(path)
        if digest != frame['sha256']:
            raise ValueError(f'RGB_HASH_MISMATCH: {frame["frame_id"]}')
        rgb = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        patches, labels, diag = memory.observe_goal_rgb(rgb, robot_id=robot, frame_id=frame['frame_id'], t=t,
                           commanded_servo=frame['commanded_servo'], camera_profile=case['camera_profile'])
        diagnostics.update(diag)
        label_path = None
        if labels is not None:
            label_path = f'labels/{frame["frame_id"]:06d}.png'
            if not cv2.imwrite(str(output/label_path), labels):
                raise OSError('LABEL_WRITE_FAILED')
        predictions.append({'frame_id': frame['frame_id'], 't': t, 'rgb_path': str(path), 'sha256': digest,
                            'pose': memory.self_map.odom.pose, 'patches': patches, 'diagnostics': diag,
                            'labels': label_path})
        sources.append({'path': str(path), 'sha256': digest})
    pred_path = output/'predictions.jsonl'
    pred_path.write_text(''.join(json.dumps(p, allow_nan=False)+'\n' for p in predictions))
    dump(output/'memory.json', memory.self_goal.snapshot())
    source_files = ['harness/floor_goal.py', 'harness/self_wall_memory.py', 'harness/self_odom_grid.py',
                    'harness/visual_arm.py', 'sim/masterpi_camera_profile.py',
                    'experiments/2026-10-07-mapfree-goal-floor/code/replay.py']
    dump(output/'manifest.json', {'case': case, 'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'],
        cwd=ROOT, text=True).strip(), 'code_hashes': {s: sha(ROOT/s) for s in source_files},
        'goal_detection': 'floor_color_v1', 'options': asdict(FloorGoalOptions()),
        'input_contract': 'own RGB + commanded_servo + issued base commands; no GT/static map',
        'total_frames': len(frames), 'sampled_frames': len(chosen), 'sample_min_gap_s': 2.,
        'diagnostics': dict(diagnostics), 'inputs': sources,
        'artifacts': {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()}})
    print(case['id'], len(chosen), dict(diagnostics), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--split', choices=['development', 'confirmation'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    for case in json.loads(args.cases.read_text()):
        if case['split'] == args.split:
            predict(case, args.output/case['id'])
