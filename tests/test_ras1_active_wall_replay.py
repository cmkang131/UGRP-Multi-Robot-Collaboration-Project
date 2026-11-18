import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import pytest

from harness.active_wall_mapping import ActiveMapper, VISUAL_MAPPING
from harness.carry_nav_v1 import CarryNav
from harness.ras1_place_observations import Ras1PlaceObservations


@pytest.fixture
def adapter(monkeypatch):
    folder = Path(__file__).resolve().parents[1] / 'experiments/2026-11-12-green-wall'
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location('ras1_replay', folder / 'replay_active_map.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_observed_wall_is_stationary_under_camera_translation_and_turn(adapter):
    world_wall = [[.275, .025], [.275, .125]]
    grid_map = ActiveMapper('ras1', 0., adapter.POSE, active_mapping=VISUAL_MAPPING)
    for index, (pose, camera_relative_wall) in enumerate([
        ([0., 0., 0.], [[27.5, 2.5], [27.5, 12.5]]),
        ([.07, -.02, .13], [[20.5, 4.5], [20.5, 14.5]]),
    ]):
        checkpoint = dict(camera_xy_cm=np.asarray(pose[:2]) * 100,
                          yaw_deg=np.degrees(pose[2]), contact_points_cm=camera_relative_wall,
                          tracking=dict(reason='ok', pose_status='nominal_floor_pose', pose={'x': 0}))
        observation, recovered = adapter.from_checkpoint(checkpoint, anchor=index == 0)
        assert np.allclose(recovered, pose)
        hold, trace = grid_map.receive(robot_id='ras1', t=float(index), frame_id=index,
                                      rgb=None, servo=adapter.POSE, observation=observation,
                                      visual_pose=recovered)
        assert hold['kind'] == 'hold' and trace['map_updated']
    assert grid_map.grid.wall_frames == {grid_map.grid.cell(p): {0, 1} for p in world_wall}
    assert not grid_map.grid.floor_frames

    hold, trace = grid_map.receive(robot_id='ras1', t=2., frame_id=2, rgb=None,
                                   servo=adapter.POSE, observation=None)
    assert hold['kind'] == 'hold' and not trace['map_updated']
    assert trace['pose'] == recovered
    assert grid_map.grid.revision == 2
    with pytest.raises(ValueError, match='NON_MONOTONIC_FRAME'):
        grid_map.receive(robot_id='ras1', t=3., frame_id=2, rgb=None,
                         servo=adapter.POSE, observation=None)
    with pytest.raises(ValueError, match='MAPPING_ONLY'):
        grid_map.command(hold)


def test_rgb_replay_uses_verified_native_frame_and_visible_floor(adapter, tmp_path):
    profile = json.loads((Path(adapter.__file__).parent / 'floor-profile-dev-181359.json').read_text())
    image = np.full((480, 640, 3), 145, dtype=np.uint8)
    image[:290] = (25, 110, 25)
    for y in range(310, 470, 15):
        for x in range(15, 630, 21):
            cv2.circle(image, (x, y), 2, (65, 65, 65), -1)
    ok, encoded = cv2.imencode('.jpg', image)
    assert ok
    frame = tmp_path / 'frame-00000.jpg'
    frame.write_bytes(encoded.tobytes())
    (tmp_path / 'frames.jsonl').write_text(json.dumps(dict(
        image=frame.name, t=1., sha256=hashlib.sha256(frame.read_bytes()).hexdigest())) + '\n')
    checkpoint = dict(image=frame.name, t=1., commanded_arm_pose=adapter.POSE)
    (tmp_path / 'result.json').write_text(json.dumps(dict(
        scale=dict(camera_height_cm=adapter.camera_geometry()[0][2] * 100),
        checkpoints=[checkpoint], floor_profile=profile)))

    result = adapter.replay(tmp_path)
    assert result['updates'] == 1
    assert any(cell['state'] == 1 and cell['wall_frames'] == [0] for cell in result['cells'])
    assert any(cell['state'] == -1 and cell['floor_frames'] == [0] for cell in result['cells'])
    assert result['traces'][0]['command']['kind'] == 'hold'

    frame.write_bytes(frame.read_bytes() + b'corruption')
    with pytest.raises(ValueError, match='HASH_MISMATCH'):
        adapter.replay(tmp_path)


def test_ras1_contacts_feed_current_carry_navigation_and_drop_invalid_pose(adapter):
    profile = {'pose': adapter.POSE}
    scale = dict(camera_height_cm=20., camera_origin_design_m=[.10, 0., .20])
    source = Ras1PlaceObservations(scale=scale, floor_profile=profile)
    anchor = dict(t=1., commanded_arm_pose=adapter.POSE, camera_xy_cm=[0., 0.],
                  contact_points_cm=[[20., 0.], [20., 10.]], tracking=dict(reason='anchor'))
    assert source.observe(anchor)
    # Body pose back 5 cm and turned 0.2 rad. The contact samples retain the
    # initial axes, so they should land on the same two wall cells.
    motion = dict(anchor, t=2., camera_xy_cm=[-5.199334, 1.986693],
                  contact_points_cm=[[25.199334, -1.986693], [25.199334, 8.013307]],
                  tracking=dict(reason='ok', pose_status='nominal_floor_pose',
                                pose=dict(x=-.25, y=0., yaw_deg=np.degrees(.2))))
    assert source.observe(motion)
    assert np.allclose(list(source.pose.values()), [-.05, 0., .2])
    assert len(source.places.walls) == 2
    carry = CarryNav(None, source.places, source.pose, [], 'through_door')
    assert np.allclose([p[:2] for p in carry._around()], [[.3, 0.], [.3, .1]])
    # Losing tracking leaves the last contacts in memory and withholds pose.
    assert not source.observe(dict(motion, t=3., tracking=dict(reason='tracking_lost_map_frozen')))
    assert source.pose is None and source.record()['updates'] == 2
    assert len(source.places.walls) == 2
    # Changing the commanded wrist breaks the fixed orientation session.
    changed = {**adapter.POSE, 3: adapter.POSE[3] + 1}
    assert not source.observe(dict(motion, t=4., commanded_arm_pose=changed))
    assert not source.observe(dict(motion, t=5.))


def test_fixed_floor_pose_handles_return_and_rejects_scale_change(adapter):
    from fixed_floor_motion import fixed_floor_pose

    intrinsics = np.array([[500., 0., 320.], [0., 500., 240.], [0., 0., 1.]])
    camera_axes = np.diag([1., -1., -1.])
    offset = np.array([.1, -.05, 1.])
    xx, yy = np.meshgrid(np.linspace(-.4, .4, 9), np.linspace(-.2, .3, 7))
    current = np.column_stack((xx.ravel(), yy.ravel()))

    def pixels(points):
        return np.column_stack((320 + 500 * points[:, 0], 240 - 500 * points[:, 1]))

    for yaw, shift in [(0., np.zeros(2)), (.036, np.array([.06, -.024]))]:
        c, s = np.cos(yaw), np.sin(yaw)
        rotation = np.array([[c, -s], [s, c]])
        anchor = current @ rotation.T + shift
        pose, support = fixed_floor_pose(pixels(anchor), pixels(current), intrinsics, camera_axes, offset)
        assert support['inliers'] == len(current)
        assert np.allclose([pose['camera_x'], pose['camera_y']], shift)
        assert np.allclose([pose['x'], pose['y']], shift + (np.eye(2) - rotation) @ offset[:2])
        assert np.isclose(pose['yaw_deg'], np.degrees(yaw))

    pose, support = fixed_floor_pose(pixels(1.15 * current), pixels(current), intrinsics, camera_axes, offset)
    assert pose is None
    assert support['reason'] == 'ground_scale_changed'
