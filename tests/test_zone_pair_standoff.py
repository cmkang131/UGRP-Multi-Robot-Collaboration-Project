"""PR #240 review2: exact dev06 own inputs, no synthetic detector/physics.

PoseReport coordinates are independent safety fixtures, NOT dev06 ground
truth or a claim that its old localizer met the new readiness thresholds.
"""
import base64
import copy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path

import pytest

from harness.owncam_pair_beam_v2 import observe_beam
from harness.zone_pair_beam_track import MAX_AGE_S, RestingBeamTrack, standoff_estimate
from harness.zone_pair_grasp import FIX_STD_XY_M, FIX_STD_YAW_RAD, stationary_beam_estimate
from tests.test_zone_pair_grasp import real_pair

FIXTURES = Path(__file__).parent / 'fixtures/zone_pair_standoff'
RECORD = json.loads((FIXTURES / 'manifest.json').read_text())


def frame(label):
    record = RECORD['frames'][label]
    obs = copy.deepcopy(record['observation'])
    jpeg = (FIXTURES / record['file']).read_bytes()
    assert len(jpeg) == record['bytes'] < 1024 * 1024
    assert hashlib.sha256(jpeg).hexdigest() == obs['sha256']
    obs['image'] = base64.b64encode(jpeg).decode()
    return obs


def servo(obs):
    return {int(k): v for k, v in obs['actuator_state']['servo_pulses'].items()}


def install(ep, obs, *, collision=False):
    own, ctl = ep.own, ep.controller
    now = obs['sim_time']
    own.now, own.last_obs = now, copy.deepcopy(obs)
    own.last_report = replace(own.last_report, t_est=now, x_m=1.5 if collision else 0.,
                              y_m=.4 if collision else 0., yaw_rad=0.,
                              std_xy_m=.001, std_yaw_rad=.001, since_tag_s=0., fix_age_s=0., last_fix_t=now)
    own.pose.loc.last_tag_t = now
    own.last_report = replace(own.last_report, last_fix_t=now)
    own.servo = servo(obs)
    ctl.arm.commanded = dict(own.servo)
    return now


def replay_to_open():
    host, _, eps = real_pair()
    ep = eps['r2']
    obs = frame('approach')
    install(ep, obs)
    ep.controller.state = 'align'
    # The production look hook records the full visible band, before motion.
    ep.controller.look(obs['sim_time'])
    assert ep.command_guard.beam_track.beam is not None
    anchor = frame('standoff')
    opened = frame('open_grasp')
    seen_anchor = False
    for row in RECORD['commands']:
        if row['t'] > opened['sim_time']:
            break
        if not seen_anchor and row['t'] > anchor['sim_time']:
            install(ep, anchor)
            ep.controller.look(anchor['sim_time'])
            seen_anchor = True
        ep.own.on_command(row)  # actual recorded issued PWM/motion, no plant
    assert seen_anchor
    assert ep.own.servo == servo(opened)
    now = install(ep, opened)
    ctl = ep.controller
    ctl.state, ctl.state_t = 'wait_close', now
    ctl.pregrasp_started_at, ctl.pregrasp_done = anchor['sim_time'], True
    ctl.grasp_pose = dict(ep.own.servo)
    for endpoint in eps.values():
        endpoint.own.job.deadline = now + 60
        endpoint.status.tick('aligning', now)
    return host, eps, ep, now


def test_exact_saved_open_frame_reproduces_old_rejection_but_now_publishes_ready():
    _, _, ep, now = replay_to_open()
    obs = ep.own.last_obs
    assert observe_beam(obs['image'], ep.own.servo)['reason'] == 'BAND_CLIPPED'
    assert stationary_beam_estimate(obs, ep.own.servo) is None  # HEAD's P1
    track = ep.command_guard.beam_track
    prior = copy.deepcopy(track.beam)
    estimate = track.estimate(now, obs, ep.own.servo, ep.controller.seg)
    assert estimate is not None
    assert estimate['anchor_sha256'] == frame('standoff')['sha256']
    assert estimate['partial_sha256'] == obs['sha256']
    assert estimate['std_xy_m'] > .015
    assert estimate['std_yaw_rad'] > math.radians(1.)
    assert estimate['std_xy_m'] >= prior['std_xy_m']
    assert estimate['std_yaw_rad'] >= prior['std_yaw_rad']
    ep.controller._wait_close(now, True)
    assert ep.controller.failure is None
    assert any(r['robot_id'] == 'r2' and r['state'] == 'close_ready_0' for r in ep.status.channel.log)
    assert not ep.controller.arm.events  # peer readiness still required


def test_same_saved_pixels_keep_previous_doorpost_counterexample_blocked():
    _, eps, ep, now = replay_to_open()
    install(ep, ep.own.last_obs, collision=True)
    ep.controller._wait_close(now, True)
    assert ep.controller.failure == 'PREGRASP_NOT_READY'
    assert not any(r['robot_id'] == 'r2' and r['state'] == 'close_ready_0' for r in ep.status.channel.log)
    assert any(e['event'] == 'preclose_beam_guard' and e.get('clearance_after_margin_m', 0.) < 0
               for e in ep.events)
    # Even a pre-existing close queue is cancelled for both endpoints.
    for endpoint in eps.values():
        endpoint.controller.arm.events = [(now + .05, 1, 1986)]
        endpoint.check(now)
    assert all(endpoint.terminal and not endpoint.controller.arm.events for endpoint in eps.values())


def test_saved_partial_alone_cannot_initialize_or_renew_a_beam_pose():
    obs = frame('open_grasp')
    track = RestingBeamTrack()
    assert standoff_estimate(obs, servo(obs)) is None
    assert not track.observe_standoff(obs, servo(obs), 0)
    assert track.estimate(obs['sim_time'], obs, servo(obs), 0) is None
    _, _, ep, now = replay_to_open()
    track = ep.command_guard.beam_track
    anchor_t, sxy, syaw = (track.beam[k] for k in ('anchor_time_s', 'std_xy_m', 'std_yaw_rad'))
    for t in (now, now + .1, now + 1.):
        track.estimate(t, obs, servo(obs), 0)
    assert track.beam['anchor_time_s'] == anchor_t
    assert track.beam['std_xy_m'] > sxy and track.beam['std_yaw_rad'] > syaw


@pytest.mark.parametrize('fault', ['expired', 'segment', 'xy', 'yaw', 'missing', 'inconsistent', 'stale', 'camera_command'])
def test_saved_input_track_fails_closed(fault):
    _, _, ep, now = replay_to_open()
    track = ep.command_guard.beam_track
    if fault == 'expired': track.beam['anchor_time_s'] = now - MAX_AGE_S - .01
    elif fault == 'segment': track.segment += 1
    elif fault == 'xy': track.beam['std_xy_m'] = FIX_STD_XY_M + .00001
    elif fault == 'yaw': track.beam['std_yaw_rad'] = FIX_STD_YAW_RAD + .00001
    elif fault == 'missing': track.beam = None
    elif fault == 'inconsistent': track.beam['grip_base_m'][1] += .5
    elif fault == 'camera_command': ep.own.servo[6] += 10
    else: ep.own.last_obs['sim_time'] -= 1.
    assert not ep.command_guard.preclose_check(now, ep.own.last_obs)


def test_issued_motion_includes_stall_and_never_reduces_uncertainty():
    obs = frame('standoff')
    track = RestingBeamTrack()
    assert track.observe_standoff(obs, servo(obs), 0)
    before = copy.deepcopy(track.beam)
    now = obs['sim_time']
    track.command({'t': now, 'kind': 'mecanum', 'forward': .035, 'left': .01,
                   'turn': .01, 'duration_s': .2}, servo(obs))
    track.advance(now + .1)
    assert track.beam['grip_base_m'] != before['grip_base_m']
    # No-motion is within the grown bound even when the prediction moves.
    assert math.dist(track.beam['grip_base_m'], before['grip_base_m']) < track.beam['std_xy_m'] - before['std_xy_m']
    track.command({'t': now + .1, 'kind': 'hold'}, servo(obs))
    point = list(track.beam['grip_base_m'])
    track.advance(now + .2)
    assert track.beam['grip_base_m'] == point
    assert track.beam['std_yaw_rad'] > before['std_yaw_rad']
    assert not track.observe_standoff(obs, servo(obs), 0)  # old frame can't refill


def test_pregrasp_standoff_waits_for_arm_then_records_actual_pixels_before_descent():
    _, _, eps = real_pair()
    ep, obs = eps['r2'], frame('standoff')
    now = install(ep, obs)
    ctl = ep.controller
    ctl.state = 'pregrasp_standoff'
    ctl.grip_base = standoff_estimate(obs, servo(obs))['grip_base_m']
    ctl._pregrasp_standoff(now, False)
    assert ep.command_guard.beam_track.beam is None
    ctl._pregrasp_standoff(now, True)
    assert ctl.state == 'pregrasp_descend'
    assert ep.command_guard.beam_track.beam['anchor_sha256'] == obs['sha256']
    assert ctl.arm.events and all(sid != 1 or pulse == 2000 for _, sid, pulse in ctl.arm.events)


def test_saved_closing_frame_rechecks_predicted_beam_before_next_pwm():
    _, _, ep, now = replay_to_open()
    assert ep.command_guard.preclose_check(now, ep.own.last_obs)
    obs = frame('closing')
    for row in RECORD['commands']:
        if now < row['t'] <= obs['sim_time']:
            ep.own.on_command(row)
    assert ep.own.servo == servo(obs)
    now = install(ep, obs)
    assert ep.command_guard.preclose_check(now, obs)
    install(ep, obs, collision=True)
    assert not ep.command_guard.preclose_check(now, obs)


def test_real_pixels_guard_the_actual_close_command_path():
    _, _, ep, now = replay_to_open()
    cmd = {'kind': 'arm', 'servo_id': 1, 'pulse': 1986}
    assert ep.command_guard.check(now, [cmd]) == [cmd]
    install(ep, ep.own.last_obs, collision=True)
    assert ep.command_guard.check(now, [cmd]) == [{'kind': 'hold'}]
    assert ep.terminal
