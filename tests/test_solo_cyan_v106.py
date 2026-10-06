"""S2 offline acceptance: measured camera math and command-only controller.

No MuJoCo model, renderer, stepping, or real physics is instantiated.
"""
import base64
import copy
import hashlib
import math
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from harness import zone_solo_cyan_v106 as rt
from harness import zone_solo_cyan_contract_v106 as c
from harness.zone_solo_cyan_vision_v106 import CyanVision, BlindCyan
from harness.zone_final_pair_vision import grasp_postures, GRASP_RADIUS_M
from harness.zone_robot_model_runtime import require_v3_consumers
from harness.owncam_pair_beam_v2 import pose_of
from harness import zone_pair_highpose_frame_gate as fg


@pytest.fixture(scope='module')
def static():
    return c.hp.resolve(c.MAP_ID)[0]


@pytest.fixture(scope='module')
def cal():
    return c.hp.student_calibration(c.hp.calibration_for(c.hp.DEV_PILOT, c.ROOT/c.CALIBRATION,
                                                       c.CALIBRATION_SHA, c.MAP_ID))


def observation(now, frame_id=1, *, rid='r3', uniform=False):
    frame = np.full((480, 640, 3), 128, np.uint8)
    if not uniform:
        frame[:, 320:] = 180
    jpeg = cv2.imencode('.jpg', frame)[1].tobytes()
    return {'robot_id': rid, 'camera': 'robot_cam', 'sim_time': now, 'frame_id': frame_id,
            'image': base64.b64encode(jpeg).decode(), 'sha256': hashlib.sha256(jpeg).hexdigest()}, frame[..., ::-1]


class FakePose:
    def __init__(self, calibration, **kwargs):
        self.calibration = calibration
        self.provider = self
        self.failure = None
        self.loc = SimpleNamespace(_pf=SimpleNamespace(params=calibration['params']))
        self.frames, self.commands, self.relooks = [], [], []
        self.xy = (0., -.85)
        self.closed = False

    def init_prior(self, mean, std, source):
        self.prior = (mean, std, source)

    def on_command(self, row):
        self.commands.append(copy.deepcopy(row))

    def begin_relocalization(self, now, servo):
        self.relooks.append(now)

    def on_frame(self, now, rgb):
        self.frames.append(None if rgb is None else rgb.shape)
        return self.report(now)

    def report(self, now):
        return SimpleNamespace(t_est=now-.16, x_m=self.xy[0], y_m=self.xy[1], yaw_rad=0., initialized=True,
            std_xy_m=.01, std_yaw_rad=.01, last_fix_t=now-.16, observation_quality={},
            cov=((.0001, 0., 0.), (0., .0001, 0.), (0., 0., .0001)))

    def record(self):
        return {'frames': self.frames, 'commands': self.commands}

    def close(self):
        self.closed = True


class FakeVision:
    def __init__(self, cal):
        pass

    def detect(self, obs, servo):
        return [{'estimated_box_center_base_m': [GRASP_RADIUS_M, 0., .016]}]

    def hover_support(self, obs, servo, center):
        return True

    def mask_bottom_row(self, obs):
        return 300  # mid-frame: no field-of-view step


def runtime(static, cal):
    return rt.Runtime(static, None, None, provider_factory=lambda *a, **kw: FakePose(cal), vision_factory=FakeVision)


def test_v3_consumers_and_named_passage(static):
    require_v3_consumers({'skill_module': 'harness.zone_solo_cyan_v106'}, rt.build_provider)
    assert rt.build_provider.uses_landmark_tags is False
    route = rt.passage_route(static, 'door_1', 'B')
    assert route[0][0] < 2.2 < route[1][0]
    for bad in ('missing', 'corridor'):
        with pytest.raises(ValueError, match='named door'):
            rt.passage_route(static, bad, 'B')
    with pytest.raises(ValueError, match='DEV_ONLY'):
        rt.Runtime(static, None, None, dev_light=False)


def test_real_partial_provider_solo_load_and_predict_only(static):
    provider = rt.build_provider(static, c.ROOT/c.CALIBRATION, c.CALIBRATION_SHA)
    try:
        inner = provider.provider
        pf = inner.loc._pf
        assert pf.partial_fix['record']['id'] == rt.partial.ID
        assert pf.params['motion_loaded'] == pf.params['motion']
        assert inner.carry_yaw_fallback is None and pf.pair_plan is None
        provider.init_prior((-.7, -.85, 0.), (.1, .5, .1), source='test public region')
        floor = {**grasp_postures()[1][-1], 1: 2000}
        provider.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': floor})
        provider.on_command({'t': .2, 'kind': 'arm', 'servo_id': 1, 'pulse': 1500})
        report = provider.on_frame(.5, None)
        assert pf.load.loaded
        assert report.last_fix_t is None  # no observation never mints a partial fix
        assert report.t_est == pytest.approx(.34)
        provider.on_command({'t': .6, 'kind': 'mecanum', 'forward': .06, 'left': 0., 'turn': 0., 'duration_s': 1.})
        provider.on_frame(.9, None)
        assert inner.failure is None and pf.pair_matched == 0
    finally:
        provider.close()


@pytest.mark.parametrize('name,xy', [('search', (.5, .01)), ('p45', (.30, -.01)), ('inspect', (GRASP_RADIUS_M, 0.))])
def test_cyan_cuboid_uses_measured_v3_projection(cal, name, xy, monkeypatch):
    """Independent synthetic pinhole/fisheye projection catches the axes transpose and v2 fallback."""
    from harness import markerless_box as mb
    from harness.zone_color_boxes import BOX_DIMS_M
    servo = pose_of(name)
    rec = c.hp.camera_record(cal, 'unloaded', servo)
    origin, rotation = np.asarray(rec['origin_m']), np.asarray(rec['rotation'])
    corners = mb._cuboid_corners(xy, .0, BOX_DIMS_M)
    optical = (corners-origin) @ rotation
    pixels, _ = cv2.fisheye.projectPoints(optical.reshape(1, -1, 3), np.zeros(3), np.zeros(3),
        mb.scaled_camera_matrix(640, 480), np.asarray(mb.CAMERA_FISHEYE_D))
    mask_color = cv2.cvtColor(np.uint8([[[92, 200, 180]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
    image = np.full((480, 640, 3), 100, np.uint8)
    cv2.fillConvexPoly(image, cv2.convexHull(np.rint(pixels.reshape(-1, 2)).astype(np.int32)), mask_color)
    monkeypatch.setattr(mb, 'camera_extrinsics', lambda *a: pytest.fail('legacy camera used'))
    detections = CyanVision(cal).detect({'image': image}, servo)
    assert len(detections) == 1
    assert math.dist(detections[0]['estimated_box_center_base_m'][:2], xy) < .007


def confirmed_window():
    b = BlindCyan()
    servo = {**grasp_postures()[0], 1: 2000}
    obs = {'frame_id': 1, 'sha256': 'a'*64}
    assert not b.confirm(0., obs, servo, (GRASP_RADIUS_M, 0.), True)
    assert not b.confirm(.1, obs, servo, (GRASP_RADIUS_M, 0.), True)  # duplicate not a confirmation
    assert b.confirm(.2, {**obs, 'frame_id': 2}, servo, (GRASP_RADIUS_M, 0.), True)
    return b, servo


@pytest.mark.parametrize('action', [
    {'kind': 'mecanum', 'forward': .01}, {'kind': 'look', 'pan_pulse': 1770},
    {'kind': 'arm', 'servo_id': 3, 'pulse': 500}, {'kind': 'unknown'}])
def test_blind_close_refuses_motion_or_off_path_commands(action):
    b, servo = confirmed_window()
    b.command(action, servo)
    assert b.disarmed and not b.ready(1., grasp_postures()[1][-1])


def test_blind_close_fixed_path_expiry_and_failed_hover():
    b, servo = confirmed_window()
    for p in grasp_postures()[1]:
        for k, v in p.items():
            b.command({'kind': 'look', 'pan_pulse': v} if k == 6 else
                      {'kind': 'arm', 'servo_id': k, 'pulse': v}, servo)
            servo[k] = v
    assert b.ready(1.5, servo)
    assert not b.ready(100., servo)
    assert not b.confirm(2., {'frame_id': 3}, servo, (GRASP_RADIUS_M, 0.), False)
    assert b.window is None


@pytest.mark.parametrize('state,held,allowed', [('carry', True, True), ('lower', True, True),
    ('carry', False, False), ('align', False, False)])
def test_own_load_occlusion_is_no_update_and_never_a_fix(static, cal, state, held, allowed):
    r = runtime(static, cal)
    r.initial_commands(0., {'r3': {1: 1500 if held else 2000, **rt.high.HIGH}})
    r.state, r.receipt = state, held
    obs, rgb = observation(.5, uniform=True)
    r.on_frames(.5, {'r3': (obs, rgb)})
    assert (r.failure is None) is allowed
    assert r.pose.frames == [None]
    if allowed:
        assert r.own_load_occlusion.export()['occluded_frames'] == 1
    r.close()


def test_stale_foreign_and_hash_bad_frames_cancel_pending_commands(static, cal):
    for mutate in (lambda o: {**o, 'sim_time': 0.}, lambda o: {**o, 'robot_id': 'r1'},
                   lambda o: {**o, 'sha256': '0'*64}):
        r = runtime(static, cal)
        r.initial_commands(0., {'r3': {1: 1500, **rt.high.HIGH}})
        r.state, r.receipt = 'carry', True
        r.arm.queue({1: 2000}, .4, duration=.5)
        obs, rgb = observation(1.)
        r.on_frames(1., {'r3': (mutate(obs), rgb)})
        assert r.step(1.) == [('r3', {'kind': 'hold'})]
        assert r.failure == 'INVALID_OWN_IMAGE' and not r.arm.events
        r.close()


def test_command_only_full_sequence_no_success_claim(static, cal, monkeypatch):
    r = runtime(static, cal)
    r.initial_commands(0., {'r3': {1: 2000, **pose_of('search')}})
    # Drive acceptance is tested separately; here exercise the real queued arm
    # path, all issued-command feedback, hover/blind checks and state transitions.
    def arrived(xy, now, **kwargs):
        r.pose.xy = tuple(xy)
        r.last_report.x_m, r.last_report.y_m = xy
        return [{'kind': 'hold'}], True
    monkeypatch.setattr(r, 'drive', arrived)
    monkeypatch.setattr(fg, 'gate', lambda: SimpleNamespace(assess=lambda *a, **kw: (fg.VALID, {})))
    for i in range(int(rt.CAP_S/.05)):
        now = i*.05
        obs = {'frame_id': i, 'sha256': 'a'*64, 'sim_time': now}
        r.on_frames(now, {'r3': (obs, np.zeros((1, 1, 3), np.uint8))})
        for rid, action in r.step(now):
            r.on_command(rid, now, action)
        if r.terminal:
            break
    assert r.state == 'done', r.record()
    assert r.receipt is False and r.servo[1] == 2000
    assert r.route_i == 3
    events = [e['event'] for e in r.events]
    assert events.index('cyan_hover_check') < events.index('cyan_close_receipt') < events.index('high_carry_pose')
    assert 'place_sequence_complete' in events
    assert r.record()['physical_success'] is None
    assert all(e.get('physical_success') is None for e in r.events)
    r.close()


def test_real_map_planning_and_motion_inverse(static, cal):
    r = runtime(static, cal)
    r.initial_commands(0., {'r3': {1: 1500, **rt.high.HIGH}})
    r.last_report = r.pose.report(1.)
    r.state, r.receipt = 'carry', True
    commands, arrived = r.drive(r.route[0], 1.)
    assert not arrived and commands[0]['kind'] == 'mecanum'
    assert any(e['event'] == 'path' for e in r.events)
    assert commands[0]['forward'] > 0
    from sim.camera_robot_port import validate_raw_action
    validate_raw_action(commands[0], allow_reverse=True, allow_mecanum=True)
    validate_raw_action(r.motion(np.array([-.1, .1, .15]), 1.)[0], allow_reverse=True, allow_mecanum=True)
    # Position can already match while heading does not: A* has no next cell.
    r.path, r.path_goal = [], None
    r.last_report.yaw_rad = .12
    commands, arrived = r.drive((r.last_report.x_m, r.last_report.y_m), 1.1)
    assert not arrived and commands[0]['turn'] < 0
    assert abs(commands[0]['forward']) < 1e-10 and abs(commands[0]['left']) < 1e-10
    r.close()


def test_default_v98_speedups_attach_to_actual_solo_provider_and_undo(static):
    from harness import zone_pair_highpose_exact_speedups as speed
    from harness.vision_pose_source_highpose import HighPoseSource
    before = HighPoseSource.__init__
    record, undo = speed.install('v98-exact-v6')
    provider = None
    try:
        provider = rt.build_provider(static, c.ROOT/c.CALIBRATION, c.CALIBRATION_SHA)
        assert isinstance(provider.provider.loc._pf.expected, speed.ExpectedMemo)
        assert len(record['expected_memo']) == 1
        assert 'render_pipeline' not in record['items']
    finally:
        if provider is not None:
            provider.close()
        undo()
    assert HighPoseSource.__init__ is before


def test_align_steps_view_down_before_cyan_leaves_frame_bottom(static, cal):
    # 2026-10-06 s911: the cuboid clipped at the p45 bottom edge before x < .255.
    r = runtime(static, cal)
    r.initial_commands(0., {'r3': {1: 2000, **pose_of('p45')}})
    r.state, r.state_t, r.last_obs = 'align', 0., {'frame_id': 7}
    r.last_report = r.pose.report(1.)
    r.arm.until = 0.
    r.detections = lambda: [{'estimated_box_center_base_m': [.27, 0., .016]}]
    r.vision.mask_bottom_row = lambda obs: 452
    assert r._control(1., True) == [{'kind': 'hold'}]
    assert r.align_view == 'inspect'
    assert [e for e in r.events if e['event'] == 'cyan_view_step'][0]['bottom_row'] == 452
    # Never steps back up to p45 while x still says p45.
    for k, v in pose_of('inspect').items():
        r.servo[k] = v
    r.arm.until = 0.
    r.vision.mask_bottom_row = lambda obs: 300
    r._control(2., True)
    assert r.align_view == 'inspect' and r.failure is None
    r.close()


def test_checkpoint_release_relook_before_route_advance(static, cal):
    r = runtime(static, cal)
    r.initial_commands(0., {'r3': {1:1500, **rt.high.HIGH}})
    r.last_report = r.pose.report(1.)
    r.state, r.receipt = 'carry', True
    r.drive = lambda *a, **kw: ([{'kind':'hold'}], True)
    r._control(1., True)
    assert r.state == 'lower' and r.route_i == 0 and r.regrasp
    assert r.relooked == {0}
    r.close()


def test_regrasp_unique_cyan_does_not_use_original_slot(static, cal):
    r = runtime(static, cal)
    r.last_obs = {'frame_id':1}
    r.last_report = r.pose.report(1.)
    r.last_report.x_m, r.last_report.y_m = 1.5, .05
    assert r.detections() == []  # outside the original static pickup slot
    r.regrasp = True
    assert len(r.detections()) == 1
    r.vision.detect = lambda *a: [dict(estimated_box_center_base_m=[.2, 0., .016])]*2
    r.initial_commands(0., {'r3':{1:2000, **pose_of('search')}})
    r.state, r.search_poses = 'search', []
    r._control(1., True)
    assert r.failure == 'CYAN_REGRASP_NOT_UNIQUELY_VISIBLE'
    r.close()


def test_stale_fix_at_relook_is_logged_and_dev_continues(static, cal):
    r = runtime(static, cal)
    r.initial_commands(0., {'r3':{1:2000, **pose_of('search')}})
    r.last_report = r.pose.report(100.)
    r.last_report.last_fix_t = 37.75
    r.state, r.regrasp = 'relook_pickup', True
    r.relook_index, r.relook_started = 0, 99.
    r._control(100., True)
    assert r.state == 'search' and not r.terminal and r.route_i == 0
    assert r.soft_counts['REOBSERVATION_NO_FIX'] == 1
    assert not [e for e in r.events if e['event']=='cyan_relook_result'][0]['fresh_fix']
    r.close()


def test_final_checkpoint_relooks_then_corrects_before_completion(static, cal):
    r = runtime(static, cal)
    r.initial_commands(0., {'r3':{1:2000, **pose_of('search')}})
    r.state, r.regrasp = 'relook_pickup', True
    r.route_i = r.relook_index = 2
    r.relook_started = 99.
    r.last_report = r.pose.report(100.)  # fresh but far from destination
    r._control(100., True)
    assert r.route_i == 2 and r.state == 'search' and not r.terminal
    r.state = 'relook_pickup'
    r.last_report.x_m, r.last_report.y_m = r.route[2]
    r._control(100.1, True)
    assert r.route_i == 3 and r.state == 'done'
    assert r.record()['physical_success'] is None
    r.close()
