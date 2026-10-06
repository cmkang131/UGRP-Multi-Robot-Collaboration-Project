"""v2 insertion policy and historical output contracts; no simulation/models."""
import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load_report(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_insertion_diagnosis_changes_selection_only_and_deduplicates_frame():
    report = load_report('csm_insertion_diagnosis')
    contacts = [{'t': float(i), 'frame_id': i, 'camera': [0., 0.],
                 'segments': [[[1., -.2], [1., .2]]]} for i in range(3)]
    poses = [{'t': float(i), 'pose': [float(i), 0., 0.]} for i in range(3)]
    decisions = [{'frame_id': i, 'status': s} for i, s in enumerate(('accepted', 'deferred', 'rejected'))]
    a = report.rebuild('r1', contacts, poses, decisions, {'accepted'})
    b = report.rebuild('r1', contacts+contacts[:1], poses, decisions, {'accepted', 'deferred'})
    c = report.rebuild('r1', contacts, poses, decisions, {'accepted', 'deferred', 'rejected'})
    assert (a.frames, b.frames, c.frames) == (1, 2, 3)
    assert np.max(a.occupied_points()[:, 0]) < 1.1
    assert 2. <= np.max(b.occupied_points()[:, 0]) < 2.1
    assert 3. <= np.max(c.occupied_points()[:, 0]) < 3.1
