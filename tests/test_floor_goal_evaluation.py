"""Conservative visibility labels from analytic saved-pose geometry only."""
import importlib.util
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]/'experiments/2026-10-07-mapfree-goal-floor/code'
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('floor_goal_evaluation', HERE/'evaluate.py')
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def test_parallel_slab_rays_and_behind_boxes():
    rays = np.array([[1., 0, 0], [-1., 0, 0], [0, 1., 0]])
    hit = evaluation.box_entry(np.zeros(3), rays, np.array([1., -.1, -.1]), np.array([2., .1, .1]))
    assert np.allclose(hit[0], 1.)
    assert np.isinf(hit[1:]).all()


def test_wall_blocks_entire_goal_visibility_upper_bound():
    origin = np.array([0., 0., 1.])
    rays = np.array([[[1., 0., -1.], [1., .1, -1.]]])
    region = {'center_m': [1., 0.], 'half_extents_m': [.2, .2]}
    visible, _, _ = evaluation.visibility_upper(origin, np.eye(3), rays, np.ones((1, 2), bool), region, [])
    assert visible.all()
    wall = (np.array([.45, -.2, 0.]), np.array([.55, .2, 1.]))
    visible, _, _ = evaluation.visibility_upper(origin, np.eye(3), rays, np.ones((1, 2), bool), region, [wall])
    assert not visible.any()


def test_detector_and_prediction_have_no_evaluation_inputs():
    import ast
    root = HERE.parents[2]
    for path in (root/'harness/floor_goal.py', HERE/'replay.py'):
        tree = ast.parse(path.read_text())
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any('mujoco' in (name or '') or 'evaluate' in (name or '') for name in imports)
        constants = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        assert not any(v.endswith(('static_map.json', 'scene.xml', 'trajectory.jsonl', 'camera-pose.jsonl')) for v in constants)
