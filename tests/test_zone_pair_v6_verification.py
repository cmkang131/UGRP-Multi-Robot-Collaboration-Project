"""PR #246 후속 검증 반례. 자기 입력 합성/저장 JPEG만 사용하며 물리 실행은 없다."""
import base64
import math

import pytest

from harness.zone_own_guards import OwnPose
from harness.zone_pair_relative import RelativeBeamTrack
from harness.zone_pair_v6_policy import pair_policy
from tests.test_zone_pair_v6_final_review import _anchored, _obs
from tests.test_zone_pair_v6_review2 import Scenario
from tests.test_zone_pair_v6_review3 import _real


def _image():
    data, servo, row = _real('v5b_dev09_r2_01491.jpg')
    return data, servo, row['observation']['sha256']


def test_fresh_frame_reread_preserves_close_in_fit_and_expired_repeat_waits():
    from tests.test_zone_pair_v6_review1 import image_at
    track = RelativeBeamTrack()
    obs, servo = image_at(.55)
    first = track.observe(obs, servo, 0, now=0.)
    assert first.closing_ready(0.) and not first.ready(0.)
    reread = track.observe(obs, servo, 0, now=0.)
    assert reread.closing_ready(0.) and reread.reasons == first.reasons
    repeated = track.observe({**obs, 'frame_id': 2, 'sim_time': .4}, servo, 0, now=.4)
    assert not repeated.closing_ready(.4) and not repeated.ready(.4)
    from harness.zone_pair_grasp import TRANSIENT_INPUT_REASONS
    assert set(repeated.reasons) & TRANSIENT_INPUT_REASONS


def test_identical_jpeg_four_seconds_cannot_certify_preclose_or_shrink_clearance_bound():
    data, servo, sha = _image()
    s = Scenario(state='pregrasp_descend', partner_state='stopped')
    guard = s.ep.command_guard
    s.own.servo = servo
    s.capture(1.)
    source = {**s.own.last_obs, **_obs(base64.b64encode(data).decode(), servo, 1491, 1., sha)}
    assert guard.preclose_check(1., source)
    first = guard.relative_track.last_report
    assert first.std_xy_m + first.bias_bound_m == pytest.approx(.0483, abs=.0001)
    for i in range(1, 41):
        now = 1. + i / 10
        s.capture(now)
        obs = {**source, 'frame_id': 1491+i, 'sim_time': now}
        report = guard.relative_report(now, obs)
        assert report.captured_at_s == first.captured_at_s
        assert report.std_xy_m == pytest.approx(guard.relative_track.beam['std_xy_m'])
        assert report.beam()['std_xy_m'] >= first.beam()['std_xy_m']
    assert report.beam()['std_xy_m'] == pytest.approx(.0503, abs=.0001)
    assert not guard.preclose_check(now, obs)
    # 같은 수신 프레임을 다시 읽어도 시간 경과가 상한에 반영된다.
    reread = guard.relative_report(now+.1, obs)
    assert reread.std_xy_m > report.std_xy_m and not reread.ready(now+.1)


@pytest.mark.parametrize('rejection', ['stale', 'camera', 'out_of_order'])
def test_rejected_frame_does_not_poison_later_fresh_identical_pixels(rejection):
    data, servo, sha = _image()
    track = RelativeBeamTrack()
    bad = _obs(data, servo, 1, 1., sha)
    if rejection == 'camera':
        bad['actuator_state'] = {'servo_pulses': {**servo, 6: servo[6]+1}}
    if rejection == 'out_of_order':
        track.last_capture = 1.5
    rejected = track.observe(bad, servo, 0, now=2. if rejection == 'stale' else 1.)
    assert not rejected.ready(2.)
    fresh = track.observe(_obs(data, servo, 2, 2.1, sha), servo, 0, now=2.1)
    assert fresh.ready(2.1) and fresh.anchor_time_s == 2.1


def test_same_frame_read_after_stale_rejection_recovers_on_distinct_fresh_frame():
    data, servo, sha = _image()
    track = RelativeBeamTrack()
    obs = _obs(data, servo, 1, 1., sha)
    assert track.observe(obs, servo, 0, now=1.).ready(1.)
    assert not track.observe(obs, servo, 0, now=2.).ready(2.)
    # A changed background pixel is an actual new image, not a copied verdict.
    import cv2
    import hashlib
    import numpy as np
    pixels = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    pixels[0:2, 0:2] = 0
    new = cv2.imencode('.jpg', pixels)[1].tobytes()
    fresh = track.observe(_obs(new, servo, 2, 2.1, hashlib.sha256(new).hexdigest()), servo, 0, now=2.1)
    assert fresh.ready(2.1) and fresh.anchor_time_s == 2.1


# The wire calls descent "aligning", closing "ready" and lifting "lift".
# Cover every enumerated phase/barrier rather than invented controller names.
from harness.zone_pair_status import STATES


@pytest.mark.parametrize('state', sorted(s for s in STATES if s in (
    'aligning', 'not_ready', 'ready', 'lift', 'carry', 'put_down') or '_ready_' in s or '_go_' in s))
def test_every_partner_motion_wire_phase_invalidates_anchor(state):
    # The anchor fixture uses a stationary peer; no model or physics loop.
    s = Scenario(state='pregrasp_descend', beam_grip=.40, partner_state='stopped')
    guard = s.ep.command_guard
    guard.relative_report(s.t, s.own.last_obs)
    assert guard.object_anchor is not None
    channel = s.ctl.status[0]
    channel.latest['r2'] = {**channel.latest.get('r2', {}), 'state': state}
    assert guard.object_pose(s.t) is None and guard.object_anchor is None
    guard._anchor_object(s.t, type('Report', (), {'ready': lambda self, now: True})())
    assert guard.object_anchor is None


def test_aligning_during_descent_rejects_219mm_pose_error_inside_old_association_gate():
    s, guard = _anchored()
    a, beam = guard.object_anchor, guard.relative_track.beam
    # Synthetic evaluation error only: the robot receives a moved own RGB track
    # and the peer wire phase, never this evaluation coordinate.
    original = guard.object_pose(s.t)
    beam['grip_base_m'][1] += .219
    guard.anchor_motion.travel_bound += .5  # old own-command reach masks peer motion
    old_pose = guard.object_pose(s.t)
    assert old_pose is not None
    error = math.dist((old_pose.x, old_pose.y), (original.x, original.y))
    assert error == pytest.approx(.219) and error > 2*old_pose.std_xy
    # A loose global envelope overlapped the wrong small object-bound pose.
    envelope = OwnPose(original.x, original.y, original.yaw, .3, .02)
    s.eps['r2'].status.tick('aligning', s.t, force=True)
    guard.global_envelope.pose = lambda report, now: envelope
    cert = guard.global_certificate(s.t)
    assert not cert['clear'] and cert['pose_source'] == 'global_envelope'
    assert guard.object_anchor is None


@pytest.mark.parametrize('policy', ['v5h', 'b-only', 'a+b'])
def test_stored_regrasp_resets_budget_before_actual_queue_grasp(policy):
    s = Scenario(state='cp_open', beam_grip=.40, partner_state='stopped')
    s.ep.policy = pair_policy(policy)
    ctl, guard = s.ctl, s.ep.command_guard
    r = guard.recheck
    assert ctl.regrasp == 'stored'
    ctl.align_look_count, ctl.align_look_total_s, r.waited_s = 8, 39., 9.5
    r.scheduled_count, r.scheduled_total_s = 4, 11.
    # Only isolate geometric readiness; execute the real checkpoint and budget path.
    ctl._grasp_pose_ready = lambda now: True
    ctl._queue_open_descent = lambda now: ctl.set('pregrasp_descend', now)
    ctl.align_look_choices = lambda: [{'pan': 1500}]
    ctl._cp_open(0., False)
    assert r.waited_s == 9.5 and ctl.align_look_count == 8  # no entry yet
    ctl._cp_open(0., True)
    assert ctl.seg == 1 and ctl.state != 'failed'
    assert ctl.align_look_count == (1 if policy == 'b-only' else 0)
    assert ctl.align_look_total_s == 0. and r.waited_s == 0.
    assert (r.scheduled_count, r.scheduled_total_s) == (4, 11.)
    resets = [e for e in s.ep.events if e['event'] == 'phase_budget_reset']
    assert resets[-1]['phase'] == 'stored_regrasp'
    # A retry within that phase must still spend its existing limit.
    if policy == 'b-only':
        ctl.align_look_count = 8
        ctl._queue_grasp(.1)
        assert ctl.state == 'failed'
        assert len([e for e in s.ep.events if e['event'] == 'phase_budget_reset']) == len(resets)
