"""Replay verification tests on a synthetic recorded-frame directory."""
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location(
        'e2ewarp_visdet_replay',
        ROOT / 'scripts' / 'e2ewarp_visdet_replay.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_raw(root: Path):
    import cv2
    frames = root / 'world-00' / 'review-rgb'
    frames.mkdir(parents=True)
    for tick in (0, 5):
        img = np.full((480, 640, 3), 150, np.uint8)  # neutral gray: no zone colour
        cv2.imwrite(str(frames / f'r1-{tick:06d}.jpg'), img)
    rows = [dict(world=0, robot='r1', t=t / 10.0,
                 wheels=[0., 0., 0., 0.], duration_s=[0., 0., 0., 0.],
                 pwm={'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1000})
            for t in (0, 5)]
    (root / 'commands.json').write_text(json.dumps(rows))


def test_replay_runs_on_recorded_frames_without_engine():
    raw = ROOT / 'outputs' / 'replay-test-raw'
    if raw.exists():
        import shutil
        shutil.rmtree(raw)
    write_raw(raw)
    try:
        m = load_module()
        report = m.replay(raw, robots=('r1',), max_extent_m='default')
        assert report['frames'] == 2
        assert report['observed_n'] == 0
        assert report['arrival_evidence_n'] == 0
        assert 'destination_colour_absent' in json.dumps(report['reason_distribution'])
        assert report['frames_by_world_robot'] == {'0-r1': 2}
        assert report['dependency_wait']
        assert 'simulator/GT pose' in report['not_read']
        assert 'mujoco' not in sys.modules
        assert 'warp' not in sys.modules
    finally:
        import shutil
        shutil.rmtree(raw, ignore_errors=True)
