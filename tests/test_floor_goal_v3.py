"""Geometry and temporal contracts without physics or rendering."""
import ast
import hashlib
import itertools
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import pytest

from harness.floor_goal_v2 import FloorGoalMemoryV2
from harness.floor_goal_v3 import FloorGoalMemoryV3, FloorGoalV3Options, footprint, metric_rejection
from harness.floor_goal_self_mask import geometry, body_envelopes, project_envelopes, self_body_mask
from harness.self_wall_memory import SelfWallMemory

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT/'experiments/2026-10-07-mapfree-goal-floor'
sys.path.insert(0, str(EXP/'code'))
import v3_render

REG = json.loads((EXP/'v3-registration.json').read_text())
V2 = json.loads((EXP/'v2-selection.json').read_text())['selected']['options']
OPTIONS = {**V2, 'minimum_observed_area_m2': .005, 'temporal_overlap_min': .35, 'temporal_center_max_m': .10}


def test_v2_golden_bytes_before_v3():
    hsv = np.full((480, 640, 3), (0, 0, 130), np.uint8)
    hsv[280:420, 240:390] = (115, 170, 180)
    rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    m = FloorGoalMemoryV2('r1', options=V2)
    records = []
    for t, x in [(1., 0.), (3., .03), (5., .06)]:
        patches, labels, diag = m.observe(rgb, robot_id='r1', frame_id=int(t), t=t, pose=(x, 0, 0),
                servo=REG['arm_poses']['search'], profile='legacy', settled=True)
        records.append({'patches': patches, 'labels_sha256': hashlib.sha256(labels.tobytes()).hexdigest(),
                        'diagnostics': diag, 'snapshot': m.snapshot()})
    assert (json.dumps(records, sort_keys=True)+'\n').encode() == (ROOT/'tests/fixtures/floor_goal/v2_before_v3.json').read_bytes()


def test_v3_options_and_actor_boundary():
    with pytest.raises(ValueError, match='FROZEN_DEV_OPTIONS'):
        SelfWallMemory('r1', self_map='odom_grid_v1', goal_detection='floor_color_v3')
    m = SelfWallMemory('r1', self_map='odom_grid_v1', goal_detection='floor_color_v3', goal_detection_options=OPTIONS)
    assert isinstance(m.self_goal, FloorGoalMemoryV3)
    with pytest.raises(ValueError, match='PEER'):
        m.self_goal.observe(None, robot_id='r2', frame_id=1, t=1., pose=(0, 0, 0), servo={}, profile='legacy', settled=True)
    with pytest.raises(TypeError):
        m.self_goal.observe(None, gt_pose=(0, 0, 0))


def test_model_has_no_world_or_peer_and_articulates():
    for profile, node in geometry().items():
        assert node['pos'] == [0., 0., .0325]
        names = [name for name, _ in body_envelopes(REG['arm_poses']['search'], profile)]
        assert all(not any(s in name for s in ('zone_', 'r1__', 'r2__', 'r3__')) for name in names)
    a = dict(body_envelopes(REG['arm_poses']['search'], 'camera_v3'))
    b = dict(body_envelopes(REG['arm_poses']['high'], 'camera_v3'))
    assert a.keys() == b.keys()
    assert any(not np.allclose(a[k], b[k]) for k in a)
    assert np.array_equal(self_body_mask(REG['arm_poses']['search'], 'camera_v3', 160, 120),
                          self_body_mask(REG['arm_poses']['search'], 'camera_v3', 160, 120))


def test_projected_body_positive_depth_and_camera_inside():
    cube = np.array(list(itertools.product([-.03, .03], [-.03, .03], [.2, .3])))
    forward = project_envelopes([('test', cube)], np.zeros(3), np.eye(3), 160, 120)
    behind = project_envelopes([('test', cube-[0, 0, .6])], np.zeros(3), np.eye(3), 160, 120)
    assert 0 < forward.sum() < forward.size and not behind.any()
    inside = project_envelopes([('test', cube)], np.array([0, 0, .25]), np.eye(3), 160, 120)
    assert inside.all()


def test_observed_area_excludes_holes_and_checks_metric_size():
    yy, xx = np.indices((100, 100))
    points = np.stack([xx*.01, yy*.01, np.zeros_like(xx)], axis=-1)
    region = np.zeros((100, 100), bool)
    region[20:61, 20:61] = True
    full = footprint(region, points)
    assert full['observed_area_m2'] == pytest.approx(.16, abs=1e-6)
    region[30:51, 30:51] = False
    holed = footprint(region, points)
    assert holed['observed_area_m2'] < full['observed_area_m2']
    assert metric_rejection(full, FloorGoalV3Options(**OPTIONS)) is None
    assert metric_rejection({**full, 'observed_area_m2': .001}, FloorGoalV3Options(**OPTIONS)) == 'metric_area'
    assert metric_rejection({**full, 'rect_sides_m': [.005, .3]}, FloorGoalV3Options(**OPTIONS)) == 'metric_size'


def sequence(poses, shifts=None, times=(1., 3., 5.)):
    m = FloorGoalMemoryV3('r1', options=OPTIONS)
    plane = np.array([[.8, -.1], [1., -.1], [1., .1], [.8, .1]])
    for i, (pose, t) in enumerate(zip(poses, times)):
        points = plane-np.array(pose[:2])+(np.array(shifts[i]) if shifts else 0)
        patch = {'component': 1, 'center_body_m': points.mean(axis=0).tolist(), 'hull_body_m': points.tolist(),
                 '_points_body_m': points, 'confidence': 1., 'pixels': 1000}
        m.detector = lambda *a, **kw: ([patch], np.ones((2, 2), np.uint16), {})
        m.observe(None, robot_id='r1', frame_id=i, t=t, pose=pose, servo={}, profile='legacy', settled=True)
    return m.snapshot()


def test_temporal_fixed_floor_and_drifting_candidate_and_yaw():
    assert sequence([(0, 0, 0), (.03, 0, 0), (.06, 0, 0)])['state'] == 'locally_confirmed_region'
    assert sequence([(0, 0, 0), (.03, 0, 0), (.06, 0, 0)], shifts=[(0, 0), (.08, 0), (.16, 0)])['state'] != 'locally_confirmed_region'
    assert sequence([(0, 0, 0)]*3)['state'] != 'locally_confirmed_region'
    assert sequence([(0, 0, 0), (.03, 0, 0), (.06, 0, 0)], times=(1., 3., 7.))['state'] != 'locally_confirmed_region'


def test_preregistered_576_views_and_no_physics_calls():
    groups = v3_render.groups(REG)
    assert len(groups) == 144 and sum(g[2] < 0 for g in groups) == 72
    for arm in REG['arm_poses']:
        commands, views = v3_render.planned_views(REG, arm)
        assert len(views) == 4
        assert np.linalg.norm(views[-1]['own_pose'][:2]) >= .05
        assert commands[-1]['forward'] == .25
    tree = ast.parse((EXP/'code/v3_render.py').read_text())
    calls = [n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert not {'mj_step', 'mj_step1', 'mj_step2', 'mj_forward'}.intersection(calls)


def test_binary_stl_mesh_uses_asset_scale(tmp_path):
    import struct
    import xml.etree.ElementTree as ET
    from v3_export_geometry import mesh_vertices
    p = tmp_path/'triangle.stl'
    p.write_bytes(bytes(80)+struct.pack('<I', 1)+struct.pack('<12fH', *([0, 0, 1]+[0, 0, 0, 1, 0, 0, 0, 1, 0]), 0))
    node = ET.Element('mesh', file=str(p), scale='2 3 4')
    assert np.array_equal(mesh_vertices(node), [[0, 0, 0], [2, 0, 0], [0, 3, 0]])
