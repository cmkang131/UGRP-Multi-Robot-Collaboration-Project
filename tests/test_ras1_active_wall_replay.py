import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import pytest

from harness.active_wall_mapping import ActiveMapper, VISUAL_MAPPING


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
