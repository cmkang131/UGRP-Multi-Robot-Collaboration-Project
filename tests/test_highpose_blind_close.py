"""v98 blind final approach (no simulator, no renderer, no model).

Replays three recorded own frames of DEV probe raise_high_align at 3358372e (r1): standoff anchor, hover,
floor grasp posture (0 beam pixels), with the recorded issued commands in between and the measured camera
models of the three fixed postures (tests/fixtures/highpose_blind_close). No ground truth is used.
"""
import inspect
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_pair_grasp as grasp
from harness import zone_pair_highpose_blind_close as blind
from harness import zone_pair_highpose_contract as c
from harness import zone_pair_highpose_runtime as rt
from harness.zone_final_pair_skill import V3Controller
from harness.zone_final_pair_vision import PairVision, grasp_postures
from scripts import run_m2_pair as m2
from tests.test_highpose_frame_gate import KEYS, refs
from tests.test_highpose_grasp_view import Fake, representative_class

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT/'tests/fixtures/highpose_blind_close'
MANIFEST = json.loads((FIX/'manifest.json').read_text())
HOVER, PATH = grasp_postures()


def servo_of(row):
    return {int(k): v for k, v in row['servo_pulses'].items()}


def obs_of(role):
    row = next(r for r in MANIFEST['frames'] if r['role'] == role)
    return {'image': (FIX/row['file']).read_bytes(), 'sim_time': row['sim_time'], 'frame_id': row['frame_id'],
            'sha256': row['sha256']}, servo_of(row)


def new_track():
    vision = PairVision({'camera_models': {'unloaded': MANIFEST['camera_models_unloaded']}})
    guard, ctl = SimpleNamespace(beam_track=vision.beam_track()), SimpleNamespace()
    track = blind.adopt(guard, ctl)
    assert ctl.blind_track is track and isinstance(track, blind.BlindTrack)
    return track


def feed(track, servo, until, start=-math.inf):
    """Issue the recorded own command rows in (start, until] to the track (as PairCommandGuard.on_command)."""
    for row in MANIFEST['commands_after_anchor']:
        if start < row['t'] <= until+1e-9:
            track.command(row, servo)
            if row['kind'] == 'arm':
                servo[int(row['servo_id'])] = row['pulse']
            elif row['kind'] == 'look':
                servo[6] = row['pan_pulse']
    return servo


def anchored():
    track = new_track()
    obs, servo = obs_of('standoff')
    assert track.observe_standoff(obs, servo, 0)
    return track, servo


def confirmed():
    track, servo = anchored()
    obs, frame_servo = obs_of('hover')
    servo = feed(track, servo, obs['sim_time'])
    assert blind.at_posture(servo, HOVER) and blind.at_posture(frame_servo, HOVER)
    track.begin_hover_check()
    got = track.estimate(obs['sim_time'], obs, frame_servo, 0)
    assert got is not None and got['evidence'] == 'visual'
    assert track.confirm(obs['sim_time'], obs, {**frame_servo, 1: 2000}, 0, HOVER, PATH) is None
    return track, servo, obs['sim_time']


def test_recorded_descent_hover_is_visual_and_grasp_pose_is_blind_without_confirmation():
    track, servo = anchored()
    hover, hover_servo = obs_of('hover')
    feed(track, servo, hover['sim_time'])
    got = track.estimate(hover['sim_time'], hover, hover_servo, 0)
    assert got['evidence'] == 'visual' and got['partial_support_fraction'] == 1.
    assert .035 < got['partial_cross_section_m'] < .04
    obs, grasp_servo = obs_of('grasp')
    feed(track, servo, obs['sim_time'], hover['sim_time'])
    assert blind.at_posture(grasp_servo, PATH[-1])
    assert len(track._partial_points(obs, grasp_servo)[0]) == 0          # 0 beam pixels at the grasp posture
    assert track.estimate(obs['sim_time'], obs, grasp_servo, 0) is None
    assert track.blind_code == 'BLIND_NOT_CONFIRMED'                     # = the 3358372e refusal, now named


def test_hover_confirmation_lets_the_grasp_pose_use_the_propagated_hypothesis():
    track, servo, t_confirm = confirmed()
    w = track.blind_window
    assert abs(w['lateral_m']) < .001 and abs(w['drop_m']-.0711) < .0005 and w['xy_m'] < .001
    obs, grasp_servo = obs_of('grasp')
    feed(track, servo, obs['sim_time'], t_confirm)
    got = track.estimate(obs['sim_time'], obs, grasp_servo, 0)
    assert got is not None and got['evidence'] == 'blind_after_hover_confirmation'
    assert track.blind_code is None and 0 < got['blind_s'] < 1.5
    assert got['blind_confirmed_frame_id'] == 1033 and got['std_xy_m'] <= grasp.FIX_STD_XY_M
    assert abs(got['grip_base_m'][0]-.2046) < .001                       # standoff fit, no base motion since
    for value in (blind.record(), track.window_record(), got):          # bundle/student records are JSON
        json.dumps(value)
    # The close PWM ramp (gripper only) keeps the window: every close step re-runs preclose_check.
    for i, pulse in enumerate((1900, 1750, 1600, 1500)):
        track.command({'t': obs['sim_time']+.05*(i+1), 'kind': 'arm', 'servo_id': 1, 'pulse': pulse},
                      {**grasp_servo, 1: 2000 if i == 0 else 1900})
    assert track.estimate(obs['sim_time']+.2, obs, {**grasp_servo, 1: 1600}, 0) is not None


@pytest.mark.parametrize('row, code', [
    ({'kind': 'mecanum', 'forward': .1, 'left': 0., 'turn': 0., 'duration_s': .15}, 'BLIND_BASE_MOVED'),
    ({'kind': 'drive', 'forward': 0., 'left': 0., 'turn': .2, 'duration_s': .15}, 'BLIND_BASE_MOVED'),
    ({'kind': 'look', 'pan_pulse': 1600}, 'BLIND_PAN_MOVED'),
    ({'kind': 'arm', 'servo_id': 6, 'pulse': 1400}, 'BLIND_PAN_MOVED'),
    ({'kind': 'arm', 'servo_id': 3, 'pulse': 600}, 'BLIND_ARM_OFF_PATH'),
    ({'kind': 'arm', 'servo_id': 5, 'pulse': 2600}, 'BLIND_ARM_OFF_PATH'),
    ({'kind': 'teleport'}, 'BLIND_UNKNOWN_COMMAND')])
def test_any_command_outside_the_fixed_descent_disarms_the_window(row, code):
    track, servo, t_confirm = confirmed()
    obs, grasp_servo = obs_of('grasp')
    feed(track, servo, obs['sim_time'], t_confirm)
    track.command({**row, 't': obs['sim_time']-.01}, dict(grasp_servo))
    assert track.estimate(obs['sim_time'], obs, grasp_servo, 0) is None and track.blind_code == code


def test_zero_velocity_motion_rows_and_same_pan_looks_do_not_disarm():
    for row in ({'kind': 'hold'}, {'kind': 'mecanum', 'forward': 0., 'left': 0., 'turn': 0.},
                {'kind': 'look', 'pan_pulse': HOVER[6]}, {'kind': 'arm', 'servo_id': 1, 'pulse': 1700}):
        assert blind.off_window(row, {1: 2000}, {'pan': HOVER[6], 'envelope': {}}) is None
    assert blind.off_window({'kind': 'arm', 'servo_id': 1, 'pulse': 2000}, {1: 1500},
                            {'pan': HOVER[6], 'envelope': {}}) == 'BLIND_GRIPPER_REOPENED'


def test_window_time_segment_and_posture_limits():
    track, servo, t_confirm = confirmed()
    obs, grasp_servo = obs_of('grasp')
    feed(track, servo, obs['sim_time'], t_confirm)
    late = t_confirm+blind.limits()['blind_max_s']+.05
    assert track.estimate(late, {**obs, 'sim_time': late}, grasp_servo, 0) is None
    assert track.blind_code == 'BLIND_WINDOW_EXPIRED'
    track, servo, t_confirm = confirmed()
    feed(track, servo, obs['sim_time'], t_confirm)
    assert track.estimate(obs['sim_time'], obs, grasp_servo, 1) is None
    assert track.blind_code == 'BLIND_SEGMENT_CHANGED'
    # Any posture other than the fixed grasp posture keeps the frozen visual verdict (no blind fallback).
    track, servo, t_confirm = confirmed()
    feed(track, servo, obs['sim_time'], t_confirm)
    track.blind_code = None
    hover_servo = obs_of('hover')[1]                       # a beam-free frame at the (measured) hover posture
    assert track.estimate(obs['sim_time'], obs, hover_servo, 0) is None
    assert track.blind_code is None


def test_reopening_the_closed_gripper_through_the_issued_command_disarms_the_window():
    track, servo, t_confirm = confirmed()
    obs, grasp_servo = obs_of('grasp')
    feed(track, servo, obs['sim_time'], t_confirm)
    closed = {**grasp_servo, 1: 1500}                                    # the close ramp already reached 1500
    track.command({'t': obs['sim_time']-.02, 'kind': 'arm', 'servo_id': 1, 'pulse': 1600}, dict(closed))
    assert track.blind_window['disarmed'] is None                      # a further close step keeps the window
    track.command({'t': obs['sim_time']-.01, 'kind': 'arm', 'servo_id': 1, 'pulse': blind.OPEN_PWM}, dict(closed))
    assert track.blind_window['disarmed']['code'] == 'BLIND_GRIPPER_REOPENED'
    assert track.estimate(obs['sim_time'], obs, closed, 0) is None and track.blind_code == 'BLIND_GRIPPER_REOPENED'


@pytest.mark.parametrize('key, value', [('drop_m', blind.BLIND_MAX_DROP_M+.001), ('xy_m', blind.BLIND_MAX_XY_M+.001)])
def test_a_window_longer_than_the_configured_descent_is_refused(key, value):
    # Configuration sanity check only: the window distances come from the fixed hover/grasp postures, which the
    # command envelope and the exact grasp-posture match already pin; this guards a mis-set posture table.
    track, servo, t_confirm = confirmed()
    obs, grasp_servo = obs_of('grasp')
    feed(track, servo, obs['sim_time'], t_confirm)
    track.blind_window[key] = value
    assert track.estimate(obs['sim_time'], obs, grasp_servo, 0) is None
    assert track.blind_code == 'BLIND_DISTANCE_EXCEEDED'


@pytest.mark.parametrize('limit', ['FIX_STD_XY_M', 'FIX_STD_YAW_RAD'])
def test_a_propagated_track_wider_than_the_fix_limit_is_refused(monkeypatch, limit):
    track, servo, t_confirm = confirmed()
    obs, grasp_servo = obs_of('grasp')
    feed(track, servo, obs['sim_time'], t_confirm)
    monkeypatch.setattr(blind, limit, 1e-9)                            # any real track sigma is now too wide
    assert track.estimate(obs['sim_time'], obs, grasp_servo, 0) is None
    assert track.blind_code == 'BLIND_TRACK_UNCERTAIN'


def test_a_stale_anchor_is_refused_as_track_uncertain():
    track, servo, t_confirm = confirmed()
    obs, grasp_servo = obs_of('grasp')
    feed(track, servo, obs['sim_time'], t_confirm)
    assert track.estimate(obs['sim_time'], obs, grasp_servo, 0) is not None   # advances the frozen track to now
    track.beam['anchor_time_s'] = obs['sim_time']-blind.resting.MAX_AGE_S-1.
    assert track._blind(obs['sim_time'], 0) == ('BLIND_TRACK_UNCERTAIN', None)


def test_new_standoff_anchor_or_hover_restart_clears_the_window():
    track, servo, _ = confirmed()
    obs, s = obs_of('standoff')
    assert track.observe_standoff({**obs, 'frame_id': 9999}, s, 0) and track.blind_window is None
    track, servo, _ = confirmed()
    track.begin_hover_check()
    assert track.blind_window is None


def test_hover_requires_the_band_on_the_station_line_and_the_hover_posture():
    track, servo = anchored()
    obs, frame_servo = obs_of('hover')
    feed(track, servo, obs['sim_time'])
    track.estimate(obs['sim_time'], obs, frame_servo, 0)
    visual = dict(track.last_visual)
    track.last_visual = {**visual, 'patch': np.asarray(visual['patch'])+[0., .004]}     # band 4 mm off the line
    assert track.confirm(obs['sim_time'], obs, {**frame_servo, 1: 2000}, 0, HOVER, PATH) == 'HOVER_LATERAL_SHIFT'
    track.last_visual = visual
    assert track.confirm(obs['sim_time'], obs, {**frame_servo, 1: 1500}, 0, HOVER, PATH) == 'HOVER_POSE_NOT_COMMANDED'
    assert track.confirm(obs['sim_time']+.05, obs, {**frame_servo, 1: 2000}, 0, HOVER, PATH) == 'HOVER_NOT_VISUAL'
    assert track.blind_window is None
    assert track.confirm(obs['sim_time'], obs, {**frame_servo, 1: 2000}, 0, HOVER, PATH) is None


class Arm:
    def __init__(self):
        self.until, self.queued, self.events = 0., [], []

    def queue(self, pose, now, duration=None, settle=.1):
        self.queued.append((dict(pose), duration, settle))
        self.until = max(now, self.until)+(duration or 0.)+settle


class Track:
    def __init__(self, refuse=None):
        self.refuse, self.blind_window, self.calls = refuse, None, []

    def begin_hover_check(self): self.calls.append('begin')
    def confirm(self, now, obs, servo, seg, hover, path):
        self.calls.append('confirm')
        if self.refuse is None:
            self.blind_window = {'drop_m': .0711}
        return self.refuse
    def window_record(self): return self.blind_window


class Ctl(blind.HoverConfirm):
    def __init__(self, preclose=True, refuse=None):
        self.rid, self.seg, self.state, self.grip_base = 'r1', 0, 'align', [.2032, 0.]
        self.arm, self.blind_track, self.preclose, self.logs = Arm(), Track(refuse), preclose, []
        self.port = SimpleNamespace(own=SimpleNamespace(servo={1: 2000, **HOVER}))
        self.failed, self.descended = None, False

    def log(self, rid, kind, now, **v): self.logs.append((kind, v))
    def set(self, state, now, **v): self.state = state
    def fail(self, reason, now): self.state, self.failed = 'failed', reason
    def look(self, now): return {'frame_id': int(now*20), 'sha256': 'x', 'sim_time': now}
    def preclose_check(self, now, obs): return self.preclose
    def _grasp_pose_checks(self, now): return {'fix': True}


def test_descent_pauses_at_the_hover_and_queues_the_fixed_path_only_after_confirmation(monkeypatch):
    calls = []
    monkeypatch.setattr(grasp.PairGraspRelook, '_pregrasp_descend',
                        lambda self, now, idle: calls.append(now), raising=True)
    Base = type('Base', (blind.HoverConfirm, grasp.PairGraspRelook), {})
    ctl = Ctl()
    ctl.__class__ = type('C', (Ctl, Base), {})
    ctl._queue_open_descent(10.)
    assert ctl.state == 'pregrasp_descend' and ctl.blind_phase == 'hover'
    assert ctl.arm.queued == [({**HOVER, 1: m2.study.OPEN}, 1., .1)]
    assert ctl.arm.until == pytest.approx(10.+1.+.1+blind.HOVER_SETTLE_S)
    ctl._pregrasp_descend(11.5, True)
    assert ctl.blind_track.calls == ['begin', 'confirm'] and ctl.blind_phase == 'hover' and len(ctl.arm.queued) == 1
    ctl._pregrasp_descend(11.55, True)                          # second consecutive passing own frame
    assert ctl.blind_track.calls == ['begin', 'confirm']*2 and ctl.blind_phase == 'descend'
    assert [q[0] for q in ctl.arm.queued[1:]] == PATH and all(q[1:] == (.12, 0.) for q in ctl.arm.queued[1:])
    assert [(v['ok'], v['streak']) for k, v in ctl.logs if k == 'blind_hover_check'] == [(True, 1), (True, 2)]
    ctl._pregrasp_descend(13., True)
    assert calls == [13.]                                       # then the parent's unchanged descend -> wait_close


@pytest.mark.parametrize('preclose, refuse, code', [(False, None, 'PREGRASP_HOVER_UNCONFIRMED'),
                                                    (True, 'HOVER_LATERAL_SHIFT', 'PREGRASP_HOVER_LATERAL_SHIFT')])
def test_hover_refusal_retries_on_new_frames_then_fails_closed(preclose, refuse, code):
    ctl = Ctl(preclose, refuse)
    ctl._queue_open_descent(10.)
    ctl._pregrasp_descend(11.5, True)
    assert ctl.state == 'pregrasp_descend' and ctl.failed is None and len(ctl.arm.queued) == 1
    ctl._pregrasp_descend(11.5+blind.HOVER_CONFIRM_MAX_S, True)
    assert ctl.failed == code and len(ctl.arm.queued) == 1      # never descends without a confirmation


def test_hover_needs_two_consecutive_distinct_passing_frames():
    ctl = Ctl()
    ctl._queue_open_descent(10.)
    ctl._pregrasp_descend(11.5, True)
    ctl._pregrasp_descend(11.5, True)                           # same own frame again: not a new confirmation
    assert ctl.blind_phase == 'hover' and ctl.blind_hover_streak == 1
    ctl.preclose = False
    ctl._pregrasp_descend(11.55, True)                          # a failing frame resets the count
    assert ctl.blind_hover_streak == 0 and ctl.failed is None
    ctl.preclose = True
    ctl._pregrasp_descend(11.6, True)
    assert ctl.blind_phase == 'hover' and len(ctl.arm.queued) == 1
    ctl._pregrasp_descend(11.65, True)
    assert ctl.blind_phase == 'descend' and len(ctl.arm.queued) == 1+len(PATH)
    assert blind.limits()['hover_confirm_frames'] == blind.HOVER_CONFIRM_FRAMES == 2


def test_alignment_bound_is_the_parent_one():
    ctl = Ctl()
    ctl.grip_base = [.2032+.0031, 0.]
    ctl._queue_open_descent(10.)
    assert ctl.failed == 'V3_GRIP_OUTSIDE_FIXED_POSTURE' and ctl.arm.queued == []
    src = inspect.getsource(V3Controller._queue_open_descent)
    for term in ('ALIGN_TOL_X_M+1e-9', 'ALIGN_TOL_Y_M+1e-9', 'grasp_postures()', 'duration=1.',
                 'duration=.12, settle=0.', 'FINAL_DESCENT_SETTLE_S'):
        assert term in src


def test_wait_close_names_the_blind_refusal(monkeypatch):
    from harness import zone_pair_highpose_frame_gate as frame_gate
    monkeypatch.setattr(m2, 'grip_view_m2', lambda image: {'seen': False})
    monkeypatch.setattr(frame_gate, 'gate', lambda: SimpleNamespace(controller_gate=lambda ctl: lambda o, r, n: True))
    ctl = Fake()
    ctl.blind_track = SimpleNamespace(blind_code='stale', window_record=lambda: None)
    def refuse(now, obs):
        ctl.blind_track.blind_code = 'BLIND_WINDOW_EXPIRED'
        return False
    ctl.preclose_check = refuse
    rt.HighController._wait_close(ctl, 10.5, True)
    assert ctl.failed == 'PREGRASP_BLIND_WINDOW_EXPIRED'
    ok = Fake()
    ok.blind_track = SimpleNamespace(blind_code='stale', window_record=lambda: None)
    rt.HighController._wait_close(ok, 10.5, True)
    assert ok.failed is None and ok.state == 'grasp' and ok.blind_track.blind_code is None


def test_mixin_placement_and_no_frozen_gate_reference():
    mro = representative_class().__mro__
    i_high, i_mixin, i_v3 = mro.index(rt.HighController), mro.index(blind.HoverConfirm), mro.index(V3Controller)
    assert i_mixin == i_high+1 and i_mixin < i_v3
    for k in (blind.HoverConfirm, blind.BlindTrack):
        assert '_grasp' not in vars(k) and '_wait_close' not in vars(k)
        for f in vars(k).values():
            if inspect.isfunction(f):
                assert not refs(f.__code__) & KEYS
    assert 'preclose_check' not in vars(blind.HoverConfirm)            # the guard's gated frozen check is used
    assert 'blind.adopt(self.command_guard, ctl)' in inspect.getsource(rt.Execution.__init__)


def test_limits_registry_and_bundle_record():
    lim = blind.limits()
    assert lim['blind_max_s'] == pytest.approx(7*.12+.3+grasp.CLOSE_WAIT_S+.5+.5)
    assert lim['commanded_drop_m'] == pytest.approx(.0711, abs=5e-4) and lim['commanded_xy_m'] < 5e-4
    assert lim['commanded_drop_m'] <= blind.BLIND_MAX_DROP_M and lim['base_motion_m'] == 0.
    assert blind.OPEN_PWM == m2.study.OPEN
    assert c.registry()['blind_final_approach']['profile'] == blind.PROFILE
    b = c.bundle('zone_wide_door_geometry_v3', 'p03')
    assert b['timing']['blind_final_approach'] == blind.record()
    path = 'harness/zone_pair_highpose_blind_close.py'
    assert b['source_sha256'][path] == c.base.sha(ROOT/path)


def test_every_refusal_name_is_listed_and_classified():
    import re
    from scripts import run_pair_highpose as runner
    src = inspect.getsource(blind)
    made = {'PREGRASP_'+k for k in re.findall(r"'((?:BLIND|HOVER)_[A-Z_]+)'", src)}
    made |= {'PREGRASP_HOVER_UNCONFIRMED'}
    made -= {'PREGRASP_HOVER_', 'PREGRASP_BLIND_'}
    assert made <= set(blind.HOVER_CODES) | set(blind.BLIND_CODES)
    assert len(set(blind.HOVER_CODES)) == 4 and len(set(blind.BLIND_CODES)) == 10
    for code in blind.HOVER_CODES:
        assert runner.failure_cause(code) == {'code': 'HOVER_NOT_CONFIRMED', 'sub': code}
    for code in blind.BLIND_CODES:
        assert runner.failure_cause(code) == {'code': 'BLIND_WINDOW_CLOSED', 'sub': code}
    assert set(runner.FAILURE_CAUSE_TEXT) == {'HOVER_NOT_CONFIRMED', 'BLIND_WINDOW_CLOSED', 'ARRIVAL_VIEW_NOT_CONFIRMED'}
    assert runner.failure_cause('PAIR_COLLISION_GUARD')['code'] == 'COLLISION_GUARD'
    assert runner.failure_cause('PREGRASP_NOT_READY')['code'] == 'UNCLASSIFIED' and runner.failure_cause(None) is None
