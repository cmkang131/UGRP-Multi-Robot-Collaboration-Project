"""Natural-floor sparse SLAM contracts; synthetic points, no simulator truth input."""
import math

import numpy as np
import pytest

from harness.natural_floor_slam import NaturalFloorSLAM, Observation, extract, transform


def descriptors(n, seed=7):
    return np.random.default_rng(seed).integers(0, 256, (n, 32), dtype=np.uint8)


def body_points(world, pose):
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return (np.asarray(world)-pose[:2]) @ np.array([[c, -s], [s, c]])


def observation(frame, pose, world, desc, *, t=None):
    return Observation(frame, float(frame if t is None else t), body_points(world, np.asarray(pose)),
                       desc.copy(), f'{frame:064x}')


def covariance(x=.002):
    return np.diag([x*x, x*x, math.radians(.5)**2])


def scene(n=30):
    rng = np.random.default_rng(11)
    return rng.uniform([.15, -.65], [1.4, .65], (n, 2)), descriptors(n)


def test_starts_empty_then_builds_metric_natural_landmark_map():
    world, desc = scene()
    slam = NaturalFloorSLAM('r1')
    assert slam.snapshot()['landmarks'] == []
    first = slam.step(observation(1, [0, 0, 0], world, desc),
                      command_delta=[0, 0, 0], command_covariance=np.zeros((3, 3)))
    assert first['status'] == 'bootstrap' and first['landmarks_added'] == len(world)
    saved = np.asarray([r['position_m'] for r in slam.snapshot()['landmarks']])
    np.testing.assert_allclose(saved, world)
    assert slam.snapshot()['coordinate_frame'] == 'r1/natural_floor_origin'


def test_visual_floor_points_correct_command_prediction_and_add_new_area():
    world, desc = scene()
    slam = NaturalFloorSLAM('r1')
    slam.step(observation(1, [0, 0, 0], world, desc), command_delta=[0, 0, 0],
              command_covariance=np.zeros((3, 3)))
    true_pose = np.array([.22, -.04, .07])
    extra = np.array([[1.55, -.5], [1.60, -.2], [1.58, .2], [1.52, .5]])
    current_world = np.vstack([world, extra])
    current_desc = np.vstack([desc, descriptors(len(extra), seed=99)])
    row = slam.step(observation(2, true_pose, current_world, current_desc),
                    command_delta=[.15, 0, .02], command_covariance=covariance(.03))
    assert row['status'] == 'visual_update' and row['inliers'] == len(world)
    np.testing.assert_allclose(slam.pose, true_pose, atol=1e-9)
    assert row['landmarks_added'] == len(extra)


def test_unknown_texture_keeps_command_motion_and_grows_uncertainty():
    world, desc = scene()
    slam = NaturalFloorSLAM('r1')
    slam.step(observation(1, [0, 0, 0], world, desc), command_delta=[0, 0, 0],
              command_covariance=np.zeros((3, 3)))
    blank = Observation(2, 2., np.empty((0, 2)), np.empty((0, 32), np.uint8))
    row = slam.step(blank, command_delta=[.10, 0, .02], command_covariance=covariance(.04))
    assert row['status'] == 'command_only' and row['reason'] == 'insufficient_matches'
    assert slam.pose[0] == pytest.approx(.10) and slam.pose[2] == pytest.approx(.02)
    assert np.trace(slam.covariance) > 0 and row['landmarks_added'] == 0


def test_global_reobservation_recovers_after_command_drift():
    world, desc = scene(40)
    slam = NaturalFloorSLAM('r1', options={'local_gate_m': .05, 'global_min_inliers': 12})
    slam.step(observation(1, [0, 0, 0], world, desc), command_delta=[0, 0, 0],
              command_covariance=np.zeros((3, 3)))
    true_pose = np.array([.08, .03, -.04])
    row = slam.step(observation(2, true_pose, world, desc),
                    command_delta=[.7, -.4, .3], command_covariance=covariance(.2))
    assert row['status'] == 'visual_relocalized'
    np.testing.assert_allclose(slam.pose, true_pose, atol=1e-9)
    assert slam.keyframes[-1]['source'] == 'visual_relocalized'


def test_bad_geometry_is_not_written_as_a_map_update():
    world, desc = scene()
    slam = NaturalFloorSLAM('r1')
    slam.step(observation(1, [0, 0, 0], world, desc), command_delta=[0, 0, 0],
              command_covariance=np.zeros((3, 3)))
    bad = np.random.default_rng(4).uniform(-2, 2, world.shape)
    count = len(slam.landmarks)
    row = slam.step(Observation(2, 2., bad, desc), command_delta=[.05, 0, 0],
                    command_covariance=covariance(.02))
    assert row['status'] == 'command_only' and row['reason'] == 'no_rigid_consensus'
    assert len(slam.landmarks) == count


def test_export_declares_only_runtime_inputs_and_observation_validation():
    slam = NaturalFloorSLAM('r3')
    snap = slam.snapshot()
    assert snap['started_empty'] is True
    assert snap['runtime_inputs'] == ['own_rgb', 'issued_wheel_commands', 'fixed_camera_calibration']
    assert not any('april' in key.lower() or 'static_map' in key.lower() or 'truth' in key.lower()
                   for key in snap)
    with pytest.raises(ValueError, match='INVALID_NATURAL_FLOOR_OBSERVATION'):
        slam.step(Observation(1, 1., np.zeros((2, 2)), np.zeros((1, 32), np.uint8)),
                  command_delta=[0, 0, 0], command_covariance=np.zeros((3, 3)))


def test_transform_uses_robot_pose_convention():
    points = np.array([[1., 0.], [0., 1.]])
    np.testing.assert_allclose(transform(points, [2., 3., math.pi/2]),
                               [[2., 4.], [1., 3.]], atol=1e-12)


def test_rgb_adapter_extracts_only_calibrated_floor_points(monkeypatch):
    import harness.e2e_rgb_vo as frontend

    rng = np.random.default_rng(71)
    gray = rng.integers(40, 220, (480, 640), dtype=np.uint8)
    rgb = np.dstack([gray]*3)
    monkeypatch.setattr(frontend, 'image_mask', lambda image, servo: np.full((480, 640), 255, np.uint8))
    monkeypatch.setattr(frontend, 'ground', lambda servo, uv: (np.asarray(uv)/100., np.ones(len(uv))))
    found = extract(rgb, {3: 1}, frame_id=4, t=.8, sha256='a'*64)
    points, desc = found.checked()
    assert len(points) > 20 and desc.shape == (len(points), 32)
    assert found.frame_id == 4 and found.sha256 == 'a'*64
