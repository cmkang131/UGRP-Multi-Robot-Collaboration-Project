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

import copy
import json
import math
import types

import pytest

from harness.self_map_csm import CorrectedOdomGrid
from harness.self_map_csm_v2 import CorrectedOdomGridV2
from harness.self_wall_memory import SelfWallMemory
from harness.self_odom_grid import OdomGrid, transform

SEGMENTS = np.array([[[2., -1.], [2., 1.]], [[.5, 1.], [2., 1.]]])


def contacts(grid, t, frame, segments=SEGMENTS):
    return grid.observe_contacts(t=t, frame_id=frame, segments=segments, camera_xy=[0., 0.], robot_id='r1')


def test_deferred_insertion_changes_map_only_not_pose_uncertainty_or_reference():
    a, b = CorrectedOdomGrid('r1', settle_s=None), CorrectedOdomGridV2('r1', settle_s=None)
    for g in (a, b):
        contacts(g, 0., 1)
        g.odom.command({'t': .01, 'kind': 'drive', 'forward': .1, 'turn': .02, 'duration_s': 1.})
        contacts(g, .3, 2, SEGMENTS+[0., .3])
    assert a.frames == 1 and b.frames == 2
    assert b.decisions[-1]['reason'] == 'keyframe_interval'
    assert b.decisions[-1]['insertion_policy'] == 'deferred_at_current_estimate'
    assert a.odom.pose == b.odom.pose
    np.testing.assert_array_equal(a.odom.covariance, b.odom.covariance)
    assert [r['frame_id'] for r in a.keyframes] == [r['frame_id'] for r in b.keyframes] == [1]
    assert b.ledger[-1]['pose'] == list(b.odom.pose)
    for g in (a, b):
        contacts(g, 1.3, 3)
    assert a.odom.pose == b.odom.pose
    assert a.decisions[-1]['reason'] == b.decisions[-1]['reason']
    assert b.decisions[-1]['reference_frames'] == a.decisions[-1]['reference_frames'] == [1]
    np.testing.assert_array_equal(a.odom.covariance, b.odom.covariance)


def test_actual_rejection_never_inserts_but_next_deferred_frame_is_separate():
    g = CorrectedOdomGridV2('r1', settle_s=None)
    contacts(g, 0., 1)
    before = copy.deepcopy(g.cells)
    contacts(g, 1., 2, SEGMENTS+[-1.5, 0.])
    assert g.decisions[-1]['status'] == 'rejected'
    assert g.decisions[-1]['matching_attempted']
    assert g.decisions[-1]['inserted'] is False and g.cells == before
    contacts(g, 1.1, 3, SEGMENTS)
    assert g.decisions[-1]['status'] == 'deferred'
    assert g.decisions[-1]['inserted']
    assert g.frames == 2


def test_duplicate_geometry_is_new_scan_but_duplicate_frame_is_no_op():
    g = CorrectedOdomGridV2('r1', settle_s=None)
    contacts(g, 0., 1)
    contacts(g, 1., 2)
    assert g.decisions[-1]['reason'] == 'duplicate_geometry'
    assert g.frames == 2
    frozen = json.dumps([g.export(), g.ledger, g.decisions])
    contacts(g, 1., 2)
    assert json.dumps([g.export(), g.ledger, g.decisions]) == frozen


def test_valid_short_scan_maps_without_matching_invalid_gates_do_not():
    g = CorrectedOdomGridV2('r1', settle_s=None)
    contacts(g, 0., 1, np.array([[[1., 0.], [1., .01]]]))
    assert g.frames == 1 and not g.keyframes
    assert g.decisions[-1]['reason'] == 'insufficient_match_points'
    assert g.decisions[-1]['matching_attempted'] is False
    before = copy.deepcopy(g.cells)
    contacts(g, 1., 2, np.array([[[4., 0.], [4.1, 0.]]]))
    assert g.cells == before
    h = CorrectedOdomGridV2('r1')
    h.odom.command({'t': 0., 'kind': 'initial_servo_command', 'pulses': {1: 2000, 3: 740}})
    contacts(h, .1, 1)
    assert not h.cells and h.decisions[-1]['reason'] == 'unsettled'
    with pytest.raises(ValueError, match='PEER'):
        h.observe_contacts(t=.2, frame_id=2, segments=SEGMENTS, camera_xy=[0., 0.], robot_id='r2')


def test_dense_ledger_rebuild_and_causal_references():
    g = CorrectedOdomGridV2('r1', settle_s=None)
    contacts(g, 0., 1)
    contacts(g, .2, 2, SEGMENTS+[0., .2])
    contacts(g, 1.2, 3, SEGMENTS)
    rebuilt = OdomGrid('r1', settle_s=None)
    for row in g.ledger:
        rebuilt.insert(transform([row['camera']], row['pose'])[0], [transform(s, row['pose']) for s in row['segments']])
    assert rebuilt.cells == g.cells
    assert len(g.ledger) == g.frames == g.revision
    assert all(e['frame_id'] not in e['reference_frames'] for e in g.decisions)


@pytest.mark.parametrize('option', [None, 'off', 'own_map_csm_v1'])
def test_off_and_v1_golden_bytes_against_frozen_pre_v2_memory(option):
    old = types.ModuleType('before_v2')
    exec((ROOT/'tests/fixtures/self_wall_memory_before_csm_v2.py.txt').read_text(), old.__dict__)
    kwargs = {'self_map': 'odom_grid_v1', 'self_map_options': {'settle_s': None}, 'clock': lambda: 9.}
    if option is not None:
        kwargs['pose_correction'] = option
    before, after = old.SelfWallMemory('r1', **kwargs), SelfWallMemory('r1', **kwargs)
    for i in range(4):
        record = {'t_sim': float(i), 'view_index': i, 'posture': 'other', 'load': False,
                  'seg': [[math.hypot(*a), math.atan2(a[1], a[0]), math.hypot(*b), math.atan2(b[1], b[0]), None]
                          for a, b in SEGMENTS]}
        for memory in (before, after):
            memory.command({'t': float(i), 'kind': 'drive', 'forward': .01, 'turn': .01, 'duration_s': .2})
            memory.observe_wall(record, camera_xy=[0., 0.], robot_id='r1')
        assert json.dumps(before.self_map.export()).encode() == json.dumps(after.self_map.export()).encode()
        assert json.dumps(before.snapshot()).encode() == json.dumps(after.snapshot()).encode()
        if option == 'own_map_csm_v1':
            assert json.dumps(before.self_map.decisions) == json.dumps(after.self_map.decisions)
