"""Offline first-30-SIM-second RGB/history verification; no physics or rendering."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from harness.grasp_act_contract import HISTORY, PERIOD_S, validate_observation, image_history
from harness.grasp_act_data import read, owned_image
from harness.grasp_act_solo_recording import camera_config


def check(root, *, seconds=30.):
    from PIL import Image
    root = Path(root)
    obs = read(root/'student-r1.jsonl', lines=True)
    labels = read(root/'teacher-r1.jsonl', lines=True)
    if not obs or len(obs) != len(labels):
        raise ValueError('incomplete or unpaired student/target files')
    expected = camera_config()
    if read(root/'student-camera.json') != expected:
        raise ValueError('student camera configuration drift')
    start = obs[0]['t']
    if obs[-1]['t']-start < seconds-PERIOD_S-1e-6:
        raise ValueError('first SIM interval not fully recorded')
    history = deepcopy(obs[0]['issued'])
    if len(history) != HISTORY or any(x != history[0] for x in history):
        raise ValueError('first command history bootstrap mismatch')
    refs, frames, byte_count, shapes, periods = [], set(), 0, set(), []
    checked = 0
    previous = None
    for row, label in zip(obs, labels):
        if row['t']-start > seconds+1e-6:
            break
        validate_observation(row)
        if row['issued'] != history:
            raise ValueError('issued history is not the preceding teacher actions')
        if (label['sample_id'] != row['sample_id'] or label['skill'] != row['skill']
                or label['object_kind'] != row['object_kind'] or label['clean_teacher_command']['t'] != row['t']):
            raise ValueError('teacher target alignment mismatch')
        if previous is not None:
            dt = row['t']-previous
            if abs(dt-PERIOD_S) > .002:
                raise ValueError('RGB period mismatch')
            periods.append(dt)
        current = row['rgb'][-1]
        if current['t'] != row['t']:
            raise ValueError('frame / command clock mismatch')
        refs.append(current)
        if row['rgb'] != image_history(refs, row['t']):
            raise ValueError('RGB lag selection mismatch')
        for ref in row['rgb']:
            image = owned_image(root, ref)
            if ref['path'] not in frames:
                with Image.open(image) as im:
                    im.load()
                    shapes.add(im.size)
                    if im.size != (expected['width'], expected['height']) or im.mode != 'RGB':
                        raise ValueError('RGB file resolution / mode mismatch')
                byte_count += image.stat().st_size
                frames.add(ref['path'])
        history = (history+[label['clean_teacher_command']])[-HISTORY:]
        previous = row['t']
        checked += 1
    if len(frames) != checked:
        raise ValueError('each recorded tick requires a unique native frame')
    result = {'schema': 'ugrp.grasp_act.solo_record_check.v1', 'passed': True,
        'scope': 'saved own RGB and issued history only; no physics-success claim',
        'seconds': seconds, 'observations': checked, 'frames': len(frames), 'rgb_bytes': byte_count,
        'resolution': [expected['width'], expected['height']],
        'period_min_s': min(periods, default=None), 'period_max_s': max(periods, default=None),
        'command_history_length': HISTORY, 'alignment': 'RGB before next command; previous commands only',
        'files': {str(p.relative_to(root)): {'bytes': p.stat().st_size,
            'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(root.iterdir()) if p.is_file()},
        'all_recorded_bytes': sum(p.stat().st_size for p in root.rglob('*') if p.is_file())}
    runtime_path = root/'evaluation/camera-runtime.json'
    runtime = read(runtime_path)
    import numpy as np
    from sim.masterpi_camera_profile import mujoco_pixel_intrinsic
    if (not np.allclose(runtime['pos'], expected['position_m'], atol=1e-10)
            or not np.allclose(runtime['quat'], expected['quat_wxyz'], atol=1e-10)
            or runtime['resolution'] != result['resolution']
            or not np.allclose(runtime['intrinsic'], mujoco_pixel_intrinsic(*result['resolution']), atol=1e-4)):
        raise ValueError('runtime camera differs from actual student configuration')
    result['runtime_camera_sha256'] = hashlib.sha256(runtime_path.read_bytes()).hexdigest()
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('root', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    result = check(a.root)
    a.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
