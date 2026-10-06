"""Static render planning and v1 preservation; no rendering in unit tests."""
import ast
import importlib.util
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import pytest

from harness.floor_goal import FloorGoalMemory
from harness.floor_goal_v2 import FloorGoalMemoryV2, FloorGoalV2Options, detect_floor_v2
from harness.self_wall_memory import SelfWallMemory

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


def test_palette_is_json_serializable(tmp_path):
    from v2_color_audit import palette
    scene = tmp_path/'scene.xml'
    scene.write_text('<mujoco><asset><texture name="ground" rgb1=".3 .3 .3" rgb2=".6 .6 .6"/></asset>'
        '<worldbody><geom name="zone_zone_B" rgba=".2 .4 .95 .3"/>'
        '<geom name="zone_zone_A" rgba=".95 .45 .1 .3"/><geom name="zone_zone_C" rgba=".7 .2 .85 .3"/>'
        '<geom name="zone_pickup" rgba=".12 .36 .7 .14"/></worldbody></mujoco>')
    value = json.loads(json.dumps(palette(scene), allow_nan=False))
    assert value['colours'][0]['deltaE76_to_raw_B'] == 0.


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


def test_renderer_refuses_occupied_lock_before_loading_scene(tmp_path, monkeypatch):
    monkeypatch.setattr(render, 'sha', lambda path: CONFIG['scene_sha256'])
    monkeypatch.setattr(render.agent_lock, 'status', lambda root: {'owner': 'other'})
    with pytest.raises(RuntimeError, match='LOCK_NOT_NULL'):
        render.render(HERE.parent/'v2-registration.json', tmp_path/'never-created')
    assert not (tmp_path/'never-created').exists()


def v2_options():
    return dict(hue_low=110, hue_high=116, saturation_min=100, min_pixels=128, minimum_solidity=.6)


def synthetic_patch(hue=112, saturation=150, hollow=False, tiny=False):
    hsv = np.full((480, 640, 3), (0, 0, 130), np.uint8)
    hsv[280:420, 240:390] = (hue, saturation, 180)
    if hollow:
        hsv[285:415, 245:385] = (0, 0, 130)
    if tiny:
        hsv[280:420, 240:390] = (0, 0, 130)
        hsv[300:308, 300:310] = (hue, saturation, 180)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)


def test_v2_hue_area_and_solidity_rejections():
    def detect(rgb):
        return detect_floor_v2(rgb, servo=CONFIG['arm_poses']['search'], profile='camera_v3',
                               options=FloorGoalV2Options(**v2_options()))
    assert len(detect(synthetic_patch())[0]) == 1
    assert not detect(synthetic_patch(104, 78))[0]  # Observed wall HSV example.
    assert not detect(synthetic_patch(tiny=True))[0]
    patches, _, diag = detect(synthetic_patch(hollow=True))
    assert not patches and diag['solidity'] == 1


def test_v2_requires_calibrated_parameters_and_keeps_private_memory():
    with pytest.raises(ValueError, match='FROZEN_DEV_OPTIONS'):
        SelfWallMemory('r3', self_map='odom_grid_v1', goal_detection='floor_color_v2')
    m = SelfWallMemory('r3', self_map='odom_grid_v1', goal_detection='floor_color_v2',
                       goal_detection_options=v2_options())
    assert isinstance(m.self_goal, FloorGoalMemoryV2)
    assert m.goal_target({'B': [4.6, -2.1]})['state'] == 'unknown'
    with pytest.raises(ValueError, match='PEER'):
        m.observe_goal_rgb(synthetic_patch(), robot_id='r1', frame_id=1, t=3.,
                            commanded_servo=CONFIG['arm_poses']['search'], camera_profile='camera_v3')


def test_static_scoring_positive_negative_small_and_center_error():
    from v2_evaluate import frame_score
    from harness.floor_goal import commanded_camera, floor_intersections, optical_rays
    mask = np.zeros((480, 640), bool)
    mask[300:320, 300:320] = True
    origin, axes = commanded_camera(CONFIG['arm_poses']['search'], 'camera_v3')
    truth = {'camera_xyz': origin.tolist(), 'camera_rotation': axes.T.tolist(), 'base_pose': [0, 0, 0]}
    projected, _ = floor_intersections(optical_rays(640, 480)[mask], origin, axes)
    patch = {'component': 1, 'center_body_m': projected[:, :2].mean(axis=0).tolist()}
    score = frame_score([patch], mask.astype(np.uint16), truth, mask)
    assert score['tp'] == 1 and score['fp'] == score['fn'] == 0
    assert score['errors_m'][0] < .01
    patch['center_body_m'][0] += .2
    assert frame_score([patch], mask.astype(np.uint16), truth, mask)['errors_m'][0] > .19
    assert frame_score([patch], mask.astype(np.uint16), truth, np.zeros_like(mask))['fp'] == 1
    assert frame_score([], np.zeros_like(mask), truth, mask)['fn'] == 1
    mask[305:] = False
    assert frame_score([], np.zeros_like(mask), truth, mask)['unscored'] == 1


def test_recorded_adapter_negative_scoring_happens_after_prediction(tmp_path):
    from v2_recorded import replay_case
    from replay import sha
    episode = tmp_path/'episode'
    folder = episode/'robots/r3'
    folder.mkdir(parents=True)
    rgb_path = folder/'frame.jpg'
    assert cv2.imwrite(str(rgb_path), cv2.cvtColor(synthetic_patch(), cv2.COLOR_RGB2BGR))
    (folder/'frames.jsonl').write_text(json.dumps({'frame_id': 1, 'sim_time': 3., 'path': 'robots/r3/frame.jpg',
        'sha256': sha(rgb_path), 'commanded_servo': CONFIG['arm_poses']['search']})+'\n')
    (folder/'commands.jsonl').write_text(json.dumps({'t': 0., 'kind': 'initial_servo_command',
                                                   'pulses': CONFIG['arm_poses']['search']})+'\n')
    baseline = tmp_path/'baseline/case'
    baseline.mkdir(parents=True)
    (baseline/'evaluation.json').write_text(json.dumps({'frames': [{'frame_id': 1, 'B_visible': False}]}))
    output = tmp_path/'prediction'
    result = replay_case({'id': 'case', 'episode': str(episode), 'robot': 'r3', 'camera_profile': 'camera_v3'},
                         v2_options(), baseline.parent, output)
    assert (output/'predictions.jsonl').exists()
    assert result['false_components'] == result['false_frames'] == 1
    assert result['false_confirmations'] == 0
