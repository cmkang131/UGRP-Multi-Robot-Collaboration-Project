"""Synthetic own-image/command tests only; no simulation, renderer or model."""
import base64
import copy
import hashlib
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from test_solo_cyan_v106 import static, cal, FakePose, FakeVision, rt
from harness import zone_solo_cyan_camera_v3 as extension
from harness.zone_solo_cyan_scene_change import SiteMemory, CONFIG, lens_valid

BBOX = [280, 250, 80, 65]


def frame(*, present=True, held=False, blocked=False, shift=0, uniform=False):
    image = np.full((480, 640, 3), 128, np.uint8)
    if not uniform:
        for x in range(30, 620, 60):
            cv2.rectangle(image, (x, 40), (x+20, 100), (55, 55, 55), -1)
            cv2.rectangle(image, (x, 130), (x+25, 160), (210, 210, 210), -1)
    if present:
        image[250:315, 280:360] = (255, 255, 0)
    if blocked:
        image[217:347, 240:400] = 0
    if held:
        image[-27:, :] = (255, 255, 0)  # 5.625% full-image wrist strip, synthetic
    if shift:
        image = cv2.warpAffine(image, np.float32([[1, 0, shift], [0, 1, 0]]), (640, 480), borderValue=(128,)*3)
    return image


def obs(image, t=1., fid=1):
    jpeg = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()
    return {'robot_id': 'r3', 'camera': 'robot_cam', 'sim_time': t, 'frame_id': fid,
            'image': base64.b64encode(jpeg).decode(), 'sha256': hashlib.sha256(jpeg).hexdigest()}


def memory():
    return SiteMemory(obs(frame()), BBOX, [rt.GRASP_RADIUS_M, 0.], rt.pose_of('inspect'))


@pytest.mark.parametrize('present,expected', [(True, 'present'), (False, 'absent')])
@pytest.mark.parametrize('shift', [0, 8])
def test_registered_scene_change_with_small_held_strip(present, expected, shift):
    m = memory()
    after = obs(frame(present=present, held=True, shift=shift), 2., 2)
    result = m.compare(after)
    assert result['decision'] == expected
    assert result['before_sha256'] == m.record['before_sha256']
    assert result['after_sha256'] == after['sha256']
    assert result['before_cyan_area_px'] > 90
    assert result['after_cyan_area_px'] > 90 if present else result['after_cyan_area_px'] == 0
    assert result['physical_success'] is None


@pytest.mark.parametrize('image', [frame(present=False, blocked=True), frame(present=False, shift=30)])
def test_occlusion_or_wrong_view_is_not_success(image):
    assert memory().compare(obs(image, 2., 2))['decision'] == 'unknown'


@pytest.mark.parametrize('internal_lens_rim', [False, True])
def test_held_strip_over_old_site_cannot_mean_ground_object(internal_lens_rim):
    image = frame(present=False)
    image[270:, 300:340] = (255, 255, 0)
    if internal_lens_rim:
        image[~lens_valid()] = 0  # clipped inside the 640x480 canvas
    result = memory().compare(obs(image, 2., 2))
    assert result['decision'] == 'unknown'
    assert result['reason'] == 'held_or_clipped_cyan_overlaps_site'


def test_no_texture_hash_mismatch_and_missing_reference():
    m = SiteMemory(obs(frame(uniform=True)), BBOX, [.2, 0.], rt.pose_of('inspect'))
    assert m.compare(obs(frame(uniform=True, present=False), 2., 2))['decision'] == 'unknown'
    bad = obs(frame(present=False), 2., 2)
    bad['sha256'] = '0'*64
    with pytest.raises(ValueError, match='sha256'):
        memory().compare(bad)
    with pytest.raises(ValueError, match='insufficient cyan'):
        SiteMemory(obs(frame(present=False)), BBOX, [.2, 0.], rt.pose_of('inspect'))


def runtime(static, cal):
    r = extension.Runtime(static, None, None, setdown_relook='off',
        camera_profile=extension.camera.PROFILE_ID, grasp_check='pickup_site_v1',
        provider_factory=lambda *a, **kw: FakePose(cal), vision_factory=FakeVision)
    r.initial_commands(0., {'r3': {1: 2000, **rt.pose_of('inspect')}})
    r.last_report = r.pose.report(1.)
    r.last_obs = obs(frame())
    r.state, r.align_view, r.align_streak = 'align', 'inspect', 1
    r.vision.detect = lambda *a: [{'estimated_box_center_base_m': [rt.GRASP_RADIUS_M, 0., .016], 'pixel_bbox': BBOX}]
    r.detections = lambda: r.vision.detect()
    r.queued = []
    r.queue = lambda p, now, **kw: r.queued.append(dict(p))
    r._control(1., True)  # real align -> hover hook records the own image
    assert r.state == 'hover' and r.scene_check.memory is not None
    # Isolate the already-tested close/lift path using issued command fixtures.
    r.state, r.receipt, r.scene_check.phase = 'lift', True, 'pending'
    r.servo = {1: 1500, **rt.high.HIGH}
    r._control(2., True)
    assert r.scene_check.phase == 'position_view'
    assert all(p[1] == 1500 for p in r.queued[1:])
    r.servo = {1: 1500, **rt.pose_of('inspect')}
    r._control(3., True)
    return r


def samples(r, *, present=False, blocked=False):
    for i in range(7):
        now = 4.+i*.2
        r.last_obs = obs(frame(present=present, blocked=blocked, held=not present), now, i+10)
        r._control(now, True)


def test_scene_option_confirm_restores_high_and_preserves_final_place(static, cal):
    r = runtime(static, cal)
    try:
        samples(r)
        assert r.scene_check.visual_status == 'confirmed_by_site_disappearance'
        assert r.visual_grasp_confirmed and r.record()['profile'] == extension.SCENE_PROFILE
        assert r.scene_check.phase == 'restore_high' and r.state == 'lift'
        assert r.queued[-1] == {1: 1500, **rt.high.HIGH}
        r.servo = {1: 1500, **rt.high.HIGH}
        r._control(20., True)
        assert r.state == 'carry'
        assert not any(c['kind'] == 'mecanum' for c in r.commands)
        r.route_i = len(r.route)-1
        r.drive = lambda *a, **kw: ([{'kind': 'hold'}], True)
        r._control(21., True)
        assert r.state == 'lower'
        r._control(22., True)
        assert r.state == 'released' and any(p[1] == 2000 for p in r.queued)
        assert r.record()['physical_success'] is None
    finally:
        r.close()


def test_remaining_object_retries_from_new_rgb_once_then_stops(static, cal):
    r = runtime(static, cal)
    try:
        samples(r, present=True)
        assert r.scene_check.visual_status == 'failed' and r.scene_check.retries == 1
        assert r.scene_check.phase == 'retry_lower'
        r._control(10., True)
        assert r.scene_check.phase == 'retry_open' and r.queued[-3][1] == 2000
        r.on_command('r3', 11., {'kind': 'arm', 'servo_id': 1, 'pulse': 2000})
        r._control(12., True)
        assert r.state == 'search' and r.target is None and r.scene_check.memory is None
        assert not r.receipt and r.route_i == 0
        r.scene_check.samples = [{'decision': 'present'}]*7
        r.scene_check.finish_check(r, 13.)
        assert r.failure == 'CYAN_SCENE_RETRY_EXHAUSTED'
    finally:
        r.close()


def test_unknown_is_logged_without_visual_success_and_duplicate_frames_dont_vote(static, cal):
    r = runtime(static, cal)
    try:
        r.last_obs = obs(frame(present=False, blocked=True), 4., 5)
        for _ in range(5):
            r._control(4., True)
        assert len(r.scene_check.samples) == 1
        r.last_obs = obs(frame(present=False, blocked=True), 4.1, 6)
        r._control(4.1, True)
        r.last_obs = obs(frame(present=False, blocked=True), 4., 5)
        r._control(4.2, True)  # reordering an earlier frame is not another vote
        assert len(r.scene_check.samples) == 2
        r._control(34., True)
        assert r.scene_check.visual_status == 'unknown' and r.failure is None
        assert r.scene_check.phase == 'restore_high'
        assert r.drain_notifications()[0]['code'] == 'GRASP_SCENE_UNCONFIRMED'
        assert r.drain_notifications() == []
    finally:
        r.close()


def test_chassis_motion_revokes_repeat_view_comparison(static, cal):
    r = runtime(static, cal)
    try:
        r.on_command('r3', 3.1, {'kind': 'mecanum', 'forward': .01, 'left': 0., 'turn': 0., 'duration_s': .1})
        samples(r)
        assert r.scene_check.visual_status == 'unknown'
        assert all(x['reason'] == 'invalid_image_or_changed_base_or_view' for x in r.scene_check.samples)
    finally:
        r.close()


def test_carry_floor_cyan_notifies_log_only_and_clipped_strip_does_not(static, cal):
    r = runtime(static, cal)
    try:
        r.state, r.servo = 'carry', {1: 1500, **rt.high.HIGH}
        fit = {'pixel_bbox': BBOX, 'area_px': 5200}
        r.scene_check.floor_vision = SimpleNamespace(detect=lambda *a: [fit])
        before = (r.state, r.receipt, r.route_i, copy.deepcopy(r.commands), copy.deepcopy(r.queued))
        for i in range(2):
            r.last_obs = obs(frame(), 10.+i*.2, 20+i)
            r.scene_check.observe_carry(r, 10.+i*.2)
        notices = r.drain_notifications()
        assert len(notices) == 1 and notices[0]['code'] == 'CYAN_CARRY_DROP_SUSPECTED'
        assert notices[0]['policy'] == 'log_only' and len(notices[0]['evidence']) == 2
        assert (r.state, r.receipt, r.route_i, r.commands, r.queued) == before
        r.scene_check.drop_reported = False
        fit['pixel_bbox'] = [0, 453, 640, 27]
        for i in range(2):
            r.last_obs = obs(frame(present=False, held=True), 11.+i*.2, 30+i)
            r.scene_check.observe_carry(r, 11.+i*.2)
        assert r.drain_notifications() == []
    finally:
        r.close()


def test_grasp_option_requires_v3_and_defaults_off():
    assert 'grasp_check' not in extension.option_record()
    with pytest.raises(ValueError, match='explicit camera v3'):
        extension.option_record(grasp_check='pickup_site_v1')
    with pytest.raises(ValueError, match='grasp_check'):
        extension.option_record(grasp_check='yes')
