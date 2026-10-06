"""Static render planning and v1 preservation; no rendering in unit tests."""
import ast
import importlib.util
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np

from harness.floor_goal import FloorGoalMemory

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT/'experiments/2026-10-07-mapfree-goal-floor/code'
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('floor_goal_static_render', HERE/'v2_render.py')
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)
CONFIG = json.loads((HERE.parent/'v2-registration.json').read_text())


def test_group_split_and_command_only_baseline():
    groups = render.groups(CONFIG)
    assert len(groups) == 96
    assert sum(g[2] < 0 for g in groups) == sum(g[2] > 0 for g in groups) == 48
    for arm in CONFIG['arm_poses']:
        commands, views = render.planned_views(CONFIG, arm)
        assert len(commands) == len(views) == 3
        assert np.allclose(views[0]['own_pose'], [0, 0, 0])
        assert 4 < np.degrees(views[1]['own_pose'][2]) < 6
        assert 9 < np.degrees(views[2]['own_pose'][2]) < 11


def test_static_renderer_has_no_physics_call():
    tree = ast.parse((HERE/'v2_render.py').read_text())
    calls = [n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert not {'mj_step', 'mj_step1', 'mj_step2', 'mj_forward'}.intersection(calls)
    assert {'mj_kinematics', 'mj_camlight'}.issubset(calls)


def test_v1_before_v2_golden_bytes():
    hsv = np.full((480, 640, 3), (0, 0, 130), np.uint8)
    hsv[280:420, 240:390] = (115, 170, 180)
    rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    m = FloorGoalMemory('r1')
    records = []
    for t, x in [(1., 0.), (3., .03), (5., .06)]:
        patches, labels, diag = m.observe(rgb, robot_id='r1', frame_id=int(t), t=t, pose=(x, 0, 0),
              servo=CONFIG['arm_poses']['search'], profile='legacy', settled=True)
        records.append({'patches': patches, 'labels_sha256': hashlib.sha256(labels.tobytes()).hexdigest(),
                        'diagnostics': diag, 'snapshot': m.snapshot()})
    assert (json.dumps(records, sort_keys=True)+'\n').encode() == (
        ROOT/'tests/fixtures/floor_goal/v1_before_v2.json').read_bytes()
