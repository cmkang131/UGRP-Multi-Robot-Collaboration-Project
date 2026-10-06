"""Pure image/geometry/memory tests. No renderer, simulator or model calls."""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from harness.floor_goal import (FloorGoalMemory, FloorGoalOptions, commanded_camera,
                                detect_floor, floor_intersections, optical_rays)
from harness.self_wall_memory import SelfWallMemory
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix

SERVO = {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}


def rgb_patch(hue=115):
    hsv = np.full((480, 640, 3), (0, 0, 130), np.uint8)
    hsv[280:420, 240:390] = (hue, 170, 180)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)


@pytest.mark.parametrize('profile', ['legacy', 'camera_v3'])
def test_fisheye_floor_roundtrip_and_positive_depth(profile):
    origin, axes = commanded_camera(SERVO, profile)
    rays = optical_rays(640, 480)[[320, 400], [200, 360]]
    points, valid = floor_intersections(rays, origin, axes)
    assert valid.all()
    assert np.allclose(points[:, 2], 0.)
    optical = (points-origin) @ axes.T
    assert (optical[:, 2] > 0).all()
    uv, _ = cv2.fisheye.projectPoints(optical.reshape(1, -1, 3), np.zeros(3), np.zeros(3),
                                      np.array(scaled_camera_matrix(640, 480)), np.array(CAMERA_FISHEYE_D))
    assert np.allclose(uv.reshape(-1, 2), [[200, 320], [360, 400]], atol=1e-6)
    assert np.allclose(axes @ axes.T, np.eye(3))


def test_backward_horizon_far_rejected():
    rays = np.array([[0, 0, 1.], [1, 0, 0], [0, 0, -1.]])
    _, valid = floor_intersections(rays, [0, 0, .2], np.eye(3))
    assert not valid.any()
    _, valid = floor_intersections(np.array([[1, 0, .001]]), [0, 0, .2], -np.eye(3), downward_min=.0001)
    assert not valid.any()


def test_color_and_neutral_floor_connection():
    patches, labels, _ = detect_floor(rgb_patch(), servo=SERVO, profile='legacy')
    assert len(patches) == 1 and (labels > 0).sum() == 140*150
    assert not detect_floor(rgb_patch(20), servo=SERVO, profile='legacy')[0]
    # Explicit RGB convention; swapping R/B must not retain the blue patch.
    assert not detect_floor(rgb_patch()[:, :, ::-1].copy(), servo=SERVO, profile='legacy')[0]
    hsv = np.full((480, 640, 3), (30, 180, 180), np.uint8)
    hsv[280:420, 240:390] = (115, 170, 180)
    patches, _, diag = detect_floor(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), servo=SERVO, profile='legacy')
    assert not patches and diag['floor_connection'] == 1


@pytest.mark.parametrize('hue', [179, 1])
def test_hue_wrap(hue):
    opt = FloorGoalOptions(hue_low=170, hue_high=10)
    assert len(detect_floor(rgb_patch(hue), servo=SERVO, profile='legacy', options=opt)[0]) == 1


def test_accumulation_requires_distinct_times_and_baseline():
    memory = FloorGoalMemory('r1')
    def observe(t, pose=(0, 0, 0), **kw):
        args = dict(robot_id='r1', frame_id=t, t=t, pose=pose, servo=SERVO, profile='legacy', settled=True)
        args.update(kw)
        return memory.observe(rgb_patch(), **args)
    for t in (1., 3., 5.):
        observe(t)
    assert memory.snapshot()['state'] == 'visually_seen'
    observe(7., (.06, 0, 0))
    snap = memory.snapshot()
    assert snap['state'] == 'locally_confirmed_region'
    assert snap['candidates'][0]['confirmed_t'] == 7.
    assert snap['candidates'][0]['observations'] == 4
    with pytest.raises(ValueError, match='DUPLICATE'):
        observe(7.)
    with pytest.raises(ValueError, match='NON_MONOTONIC'):
        observe(6.)
    with pytest.raises(ValueError, match='PEER'):
        observe(8., robot_id='r2')
    with pytest.raises(ValueError, match='NONFINITE'):
        observe(8., (float('nan'), 0, 0))
    assert memory.snapshot() == snap


def test_integration_unknown_has_no_static_fallback_and_settle_gate():
    m = SelfWallMemory('r1', self_map='odom_grid_v1', goal_detection='floor_color_v1')
    static = {'B': [4.6, -2.1]}
    assert m.goal_target(static)['state'] == 'unknown'
    m.command({'t': 0., 'kind': 'initial_servo_command', 'pulses': SERVO})
    out = m.observe_goal_rgb(rgb_patch(), robot_id='r1', frame_id=1, t=.1,
                             commanded_servo=SERVO, camera_profile='legacy')
    assert out[2] == {'unsettled': 1}
    assert m.snapshot()['self_goal']['state'] == 'unknown'
    m.observe_goal_rgb(rgb_patch(), robot_id='r1', frame_id=2, t=.5,
                       commanded_servo=SERVO, camera_profile='legacy')
    assert m.snapshot()['self_goal']['state'] == 'visually_seen'


@pytest.mark.parametrize('explicit', [False, True])
def test_off_golden_bytes_and_static_goal_identity(explicit):
    out = []
    for config in ({}, {'self_map': 'odom_grid_v1'}):
        m = SelfWallMemory('r1', clock=lambda: 5., **config, **({'goal_detection': 'off'} if explicit else {}))
        m.observe({'observation_id': 'floor-1', 'cargo': [], 'sim_time': 2.}, 2.)
        m.command({'t': 0., 'kind': 'initial_servo_command', 'pulses': SERVO})
        static = b'{"B": [4.6, -2.1]}\n'
        assert m.goal_target(static) is static
        assert m.observe_goal_rgb(None, robot_id='other', frame_id=None, t=-100,
                                  commanded_servo=None, camera_profile='invalid') is None
        out.append(m.snapshot())
    golden = Path(__file__).parent/'fixtures/floor_goal/pre_goal_snapshot.json'
    assert (json.dumps(out, sort_keys=True, ensure_ascii=False)+'\n').encode() == golden.read_bytes()


def test_invalid_options_and_no_gt_constructor():
    with pytest.raises(ValueError):
        FloorGoalOptions(max_range_m=float('inf'))
    with pytest.raises(ValueError):
        SelfWallMemory('r1', goal_detection='floor_color_v1')
    with pytest.raises(TypeError):
        FloorGoalMemory('r1', static_map={'goal': [1, 2]})
