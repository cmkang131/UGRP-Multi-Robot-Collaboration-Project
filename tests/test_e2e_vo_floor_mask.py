"""Pure camera geometry and saved-image estimator contracts; no physics."""
import math

import cv2
import numpy as np
import pytest

from harness import e2e_rgb_vo as vo
from harness import e2e_vo_floor_mask as mask
from harness.active_camera import SEARCH, transform
from harness.self_pulse_rotation import RotationPulseOdometry


def project(points, servo=SEARCH):
    o, r = transform(servo)
    return cv2.fisheye.projectPoints(((np.asarray(points)-o) @ r).reshape(-1, 1, 3),
        np.zeros(3), np.zeros(3), mask.K, mask.D)[0].reshape(-1, 2)


def test_wall_occlusion_horizon_and_floor_with_rotated_map_frame():
    # Same physical wall expressed in two map coordinate frames.
    wall = ((.8, 0., .025, 2., .4, 0.),)
    a = mask.geometric_mask(SEARCH, wall, (0., 0., 0.))
    b = mask.geometric_mask(SEARCH, ((2., 3.8, .025, 2., .4, math.pi/2),), (2., 3., math.pi/2))
    np.testing.assert_array_equal(a, b)
    for xyz, expected in [([.8, 0., .15], 0), ([.55, 0., 0.], 255), ([1.8, 0., 0.], 0)]:
        x, y = np.rint(project([xyz])[0]).astype(int)
        assert a[y, x] == expected
    _, direction = mask.rays(vo._servo_key(SEARCH))
    assert not a.reshape(-1)[direction[:, 2] >= 0].any()


def test_wall_behind_camera_does_not_mask_floor_and_height_matters():
    far = mask.geometric_mask(SEARCH, ((-3., 0., .025, 2., .4, 0.),), (0., 0., 0.))
    short = mask.geometric_mask(SEARCH, ((.8, 0., .025, 2., .01, 0.),), (0., 0., 0.))
    tall = mask.geometric_mask(SEARCH, ((.8, 0., .025, 2., .4, 0.),), (0., 0., 0.))
    x, y = np.rint(project([[.8, 0., .15]])[0]).astype(int)
    assert far[y, x] == short[y, x] == 255 and tall[y, x] == 0


def test_missing_registration_is_explicit_unknown_not_own_start_or_identity():
    a = np.full((480, 640, 3), 120, np.uint8); b = a.copy(); b[0, 0] += 1
    assert mask.geometric_mask(SEARCH, (), None) is None
    r = vo.ground_pair(a, b, SEARCH, vo_floor_mask='geom_v1', static_walls=((.8, 0., .025, 2., .4, 0.),))
    assert r['status'] == 'unknown_map_registration'
    with pytest.raises(ValueError, match='FINITE_REGISTERED'):
        mask.geometric_mask(SEARCH, (), [math.nan, 0, 0])


def test_homography_rejects_outliers_in_undistorted_coordinates():
    p = np.array([(x, y) for x in (.45, .6, .85, 1.1, 1.4) for y in (-.3, -.1, .1, .3)])
    q = p - [.012, .002]
    a = project(np.column_stack((p, np.zeros(len(p)))))
    b = project(np.column_stack((q, np.zeros(len(q)))))
    b[-3:] += [25, -30]
    keep = mask.homography_inliers(a, b)
    assert keep[:-3].all() and not keep[-3:].any()
    assert not mask.homography_inliers(a[:3], b[:3]).any()
    assert not mask.homography_inliers(np.ones((8, 2)), np.ones((8, 2))).any()


def test_ransac_inliers_only_reach_metric_fit(monkeypatch):
    a = np.random.default_rng(8).integers(50, 160, (480, 640), dtype=np.uint8)
    a = np.repeat(a[:, :, None], 3, axis=2); b = np.roll(a, 1, axis=1)
    seen = []
    def choose(p, q):
        keep = np.arange(len(p)) % 2 == 0
        seen.append(p[keep].copy())
        return keep
    def fit(p, q):
        np.testing.assert_allclose(p, vo.ground(SEARCH, seen[0])[0])
        return None
    monkeypatch.setattr(mask, 'homography_inliers', choose)
    monkeypatch.setattr(vo, 'rigid_ransac', fit)
    out = vo.ground_pair(a, b, SEARCH, vo_floor_mask='homography_v1')
    assert seen and out['status'] == 'unknown_rigid_consensus'
    assert out['homography_inliers'] < out['pre_homography_tracks']


def test_missing_map_keeps_command_increment_and_pose_propagation():
    d = RotationPulseOdometry(); d.command(dict(t=0., kind='initial_servo_command', pulses=SEARCH))
    f = vo.VOFusion(d, vo_floor_mask='geom_v1')
    a = np.full((480, 640, 3), 120, np.uint8)
    f.observe(t=1., frame_id=1, rgb=a, servo=SEARCH)
    f.command(dict(t=1., kind='mecanum', forward=.35, left=0., turn=0., duration_s=.1))
    b = a.copy(); b[0, 0] += 1
    r = f.observe(t=1.2, frame_id=2, rgb=b, servo=SEARCH)
    assert r['status'] == 'unknown_map_registration'
    assert r['fusion'] == 'command_kept' and r['command_delta'][0] > 0
    assert r['command_delta'] == r['fused_delta']


def test_off_never_reads_optional_map_input_and_is_identical():
    a = np.random.default_rng(7).integers(50, 160, (480, 640), dtype=np.uint8)
    a = np.repeat(a[:, :, None], 3, axis=2); b = np.roll(a, 1, axis=1)
    assert vo.ground_pair(a, b, SEARCH) == vo.ground_pair(a, b, SEARCH,
        vo_floor_mask='off', static_walls=object(), before_map_pose=object(), after_map_pose=object())


def test_static_map_whitelist_and_option_validation():
    m = dict(obstacles=[dict(kind='wall', center_m=[.8, 0], half_extents_m=[.025, 2.], height_m=.4)],
             robot_spawns=object(), evaluation=object())
    assert mask.wall_boxes(m) == ((.8, 0., .025, 2., .4, 0.),)
    with pytest.raises(ValueError, match='UNKNOWN_VO_FLOOR_MASK'):
        vo.VOFusion(RotationPulseOdometry(), vo_floor_mask='oops')
