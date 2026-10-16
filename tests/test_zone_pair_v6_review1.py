"""PR #246 review counterexamples: analytic own RGB, no physics/model calls."""
from dataclasses import replace
import hashlib
import math

import numpy as np
import pytest

from harness.owncam_pair_beam_v2 import pose_of
from harness.owncam_view import base_rays
from harness.zone_pair_global import GlobalEnvelope
from harness.zone_pair_relative import RelativeBeamTrack
from harness.zone_pair_v6_policy import pair_policy
from harness.zone_own_guards import OwnPose
from tests.test_zone_pair_grasp import real_pair
from tests.test_zone_pair_v6 import good


def box_pixels(servo, intervals, *, lateral=0., face_at=None, step=1):
    """Ray-cast a 40 mm wide, 32 mm tall bar lying on the floor.

    Review 3: real renders show the near end face (floor edge to top edge).
    face_at renders that vertical face at x=face_at; None models an occluded
    or clipped near end. Returns (x, y, top_hit, face_hit) pixel samples.
    """
    origin, rays, x, y, valid = base_rays(servo, step)
    distance = (.032-origin[2])/np.where(abs(rays[:, 2]) > 1e-8, rays[:, 2], 1.)
    pts = origin+distance[:, None]*rays
    along = np.zeros(len(pts), bool)
    for lo, hi in intervals:
        along |= (pts[:, 0] >= lo) & (pts[:, 0] <= hi)
    top = valid & (distance > 0) & (rays[:, 2] < -1e-6) & along & (abs(pts[:, 1]-lateral) <= .02)
    face = np.zeros(len(pts), bool)
    if face_at is not None:
        tf = (face_at-origin[0])/np.where(abs(rays[:, 0]) > 1e-8, rays[:, 0], np.inf)
        fp = origin+tf[:, None]*rays
        face = (valid & (tf > 0) & (fp[:, 2] >= 0) & (fp[:, 2] <= .032)
                & (abs(fp[:, 1]-lateral) <= .02) & ~top)
    return x.astype(int), y.astype(int), top, face


def image_at(grip, name='search', *, fid=1, t=0., lateral=0., face=True):
    """Ray-cast an ideal unmarked 600x40x32 mm catalogue bar (lit top, darker end face)."""
    servo = pose_of(name)
    x, y, top, end = box_pixels(servo, [(grip-.03, grip+.57)], lateral=lateral,
                                face_at=grip-.03 if face else None)
    frame = np.full((480, 640, 3), 100, np.uint8)
    frame[y[top], x[top]] = [0, 220, 120]
    frame[y[end], x[end]] = [0, 160, 88]
    return dict(frame_id=fid, sha256=hashlib.sha256(frame.tobytes()).hexdigest(),
                sim_time=t, image=frame, actuator_state={'servo_pulses':servo}), servo


@pytest.mark.parametrize('state', ['approach', 'reapproach'])
def test_approach_forward_19mm_clearance_uses_6cm_envelope(state, monkeypatch):
    _, _, eps = real_pair(); ep = eps['r1']; own = ep.own
    ep.policy = pair_policy('a+b'); ep.controller.state = state
    own.last_report = replace(good(), x_m=1.83, y_m=-1.8)
    envelope = OwnPose(1.83, -1.8, 0., .06, .01)
    guard = ep.command_guard.sweep_guard()
    cmd = dict(kind='mecanum', forward=.12, left=0., turn=0., duration_s=.15)
    assert .019 <= guard.certificate(own.servo, envelope)['clearance_m'] < .020
    assert guard.motion_clear(own.servo, OwnPose.from_report(own.last_report), cmd, loaded=False)
    assert not guard.motion_clear(own.servo, envelope, cmd, loaded=False)
    monkeypatch.setattr(ep.command_guard.global_envelope, 'pose', lambda *a: envelope)
    assert ep.command_guard.check(0., [cmd]) == [{'kind':'hold'}]
    assert ep.terminal


@pytest.mark.parametrize('state', ['approach', 'reapproach'])
def test_approach_arm_sweep_receives_same_global_envelope(state, monkeypatch):
    _, _, eps = real_pair(); ep = eps['r1']
    ep.policy = pair_policy('a+b'); ep.controller.state = state
    ep.own.last_report = good()
    envelope = OwnPose(.6, 0., 0., .06, .01)
    monkeypatch.setattr(ep.command_guard.global_envelope, 'pose', lambda *a: envelope)
    guard = ep.command_guard.sweep_guard(); seen = []
    original = guard.plan
    def plan(servo, target, pans, pose, **kw):
        seen.append(pose)
        return original(servo, target, pans, pose, **kw)
    monkeypatch.setattr(guard, 'plan', plan)
    monkeypatch.setattr(ep.command_guard, 'sweep_guard', lambda: guard)
    cmd = {'kind':'arm', 'servo_id':6, 'pulse':1500}
    assert ep.command_guard.check(0., [cmd]) == [cmd]
    assert seen == [envelope]


def test_yaw_jump_without_rotation_cannot_replace_anchor_or_shrink_bounds():
    env = GlobalEnvelope(); env.pose(good(), 0.)
    jump = replace(good(1.), yaw_rad=math.pi/2)
    assert env.pose(jump, 1.) is None
    assert env.fix_t == 0. and env.anchor.yaw == 0. and env.anchor.std_yaw == .01
    predicted = env.pose(replace(jump, last_fix_t=0., fix_age_s=1.,
                                observation_quality={}), 1.)
    assert predicted.std_yaw > .78


def test_commanded_turn_and_wrapped_yaw_are_reachable():
    env = GlobalEnvelope(); env.pose(good(), 0.)
    env.command(dict(kind='drive', t=0., turn=1., duration_s=1.))
    assert env.pose(replace(good(1.), yaw_rad=math.pi/2), 1.) is not None
    assert env.fix_t == 1.
    env = GlobalEnvelope(); env.pose(replace(good(), yaw_rad=math.pi-.01), 0.)
    assert env.pose(replace(good(.2), yaw_rad=-math.pi+.01), .2) is not None


@pytest.mark.parametrize('jump', [{'yaw_rad':math.pi/2}, {'x_m':1.5}])
def test_out_of_range_reacquisition_needs_three_distinct_consistent_fixes(jump):
    env = GlobalEnvelope(); env.pose(good(), 0.)
    for t in (1., 1.2):
        report = replace(good(t), **jump)
        assert env.pose(report, t) is None
        assert env.pose(report, t) is None  # repeated reads cannot count
        assert env.fix_t == 0.
    assert env.pose(replace(good(1.4), **jump), 1.4) is not None
    assert env.fix_t == 1.4


@pytest.mark.parametrize('interrupt', ['uninformative', 'inconsistent', 'motion', 'gap'])
def test_reacquisition_interruption_does_not_confirm_old_candidate(interrupt):
    env = GlobalEnvelope(); env.pose(good(), 0.)
    def jump(t, yaw=math.pi/2):
        return replace(good(t), yaw_rad=yaw)
    assert env.pose(jump(1.), 1.) is None
    assert env.pose(jump(1.2), 1.2) is None
    end = 1.6
    if interrupt == 'uninformative':
        env.pose(replace(jump(1.3), observation_quality={}), 1.3)
    elif interrupt == 'inconsistent':
        assert env.pose(jump(1.3, -math.pi/2), 1.3) is None
    elif interrupt == 'motion':
        env.command(dict(kind='drive', t=1.3, forward=.01, duration_s=.1))
    else:
        end = 3.
    assert env.pose(jump(end), end) is None and env.fix_t == 0.


def test_33cm_to_306mm_normal_forward_recovers_from_complete_stationary_views(monkeypatch):
    from harness.owncam_pair_beam import align_command
    # Review 3: the rendered bar now shows its near end face as in real renders;
    # at .33 m that face reaches the search view's lower border, so the same
    # normal forward case starts from the nearest complete view (.36 -> .336 m).
    track = RelativeBeamTrack()
    first, servo = image_at(.36)
    initial = track.observe(first, servo, 0, now=0.)
    assert initial.ready(0.)
    command = align_command(initial.beam())
    assert command['forward'] == .08 and command['duration'] == .3
    track.command({**command, 't':0., 'duration_s':command['duration']}, servo)
    after, _ = image_at(.336, fid=2, t=.3)
    clipped = track.observe(after, servo, 0, now=.3)
    assert not clipped.ready(.3) and clipped.std_xy_m+clipped.bias_bound_m > .07
    assert 'END_CLIPPED' in clipped.reasons
    # The production align state chooses its existing next view, no base backoff.
    _, _, eps = real_pair(); ctl = eps['r1'].controller
    eps['r1'].policy = pair_policy('a+b'); ctl.state = 'align'; ctl.state_t = 0.
    ctl.look_name = 'search'; ctl.next_look = 0.; ctl.aligned_streak = 0
    monkeypatch.setattr(ctl, 'look', lambda t: after)
    monkeypatch.setattr(ctl, 'relative_report', lambda t, o: clipped)
    chosen = []; monkeypatch.setattr(ctl, '_set_look', lambda name,t,**kw: chosen.append(name))
    ctl._align(.3, True)
    assert chosen == ['p45']
    view, new_servo = image_at(.336, 'p45', fid=3, t=1.)
    for sid, pulse in new_servo.items():
        if servo.get(sid) != pulse:
            track.command(dict(kind='arm', t=.3, servo_id=sid, pulse=pulse), servo)
    updated = track.observe(view, new_servo, 0, now=1.)
    assert updated.ready(1.)
    # Mid-height end-face hypothesis: error stays inside the reported bound.
    assert abs(updated.grip_base_m[0]-.336) <= updated.std_xy_m+updated.bias_bound_m
    assert updated.std_xy_m+updated.bias_bound_m <= .05  # original bound unchanged
    assert 'STATIONARY_MULTIVIEW_COMPLETE_SHAPE' in updated.reasons
    assert track.beam['identity_time_s'] == 0. and updated.anchor_time_s == 1.
    ctl.look_name = 'p45'; ctl.next_look = 0.
    monkeypatch.setattr(ctl, 'look', lambda t: view)
    monkeypatch.setattr(ctl, 'relative_report', lambda t, o: updated)
    monkeypatch.setattr(ctl, 'global_certificate', lambda *a: {'clear':True})
    issued = []; monkeypatch.setattr(ctl, 'drive', lambda command,t: issued.append(command))
    ctl._align(1., True)
    assert len(issued) == 1 and issued[0]['forward'] > 0. and ctl.state == 'align'


@pytest.mark.parametrize('fault', ['unanchored', 'segment', 'expired', 'near_clipped', 'moved', 'occluded'])
def test_partial_shape_never_invents_endpoint_identity(fault):
    track = RelativeBeamTrack(); first, servo = image_at(.36)
    if fault != 'unanchored':
        assert track.observe(first, servo, 0, now=0.).ready(0.)
    t = 31. if fault == 'expired' else 1.
    name = 'search' if fault == 'near_clipped' else 'p45'
    frame, servo = image_at(.336, name, fid=2, t=t, lateral=.3 if fault == 'moved' else 0.)
    if fault == 'occluded':
        # Only a short interior patch is visible; neither end meets a FOV boundary.
        frame['image'][:220] = 100
        frame['image'][280:] = 100
    report = track.observe(frame, servo, int(fault == 'segment'), now=t)
    if fault in ('near_clipped', 'occluded'):
        assert report.anchor_time_s == 0. and 'NEAR_END_AND_PAIRED_EDGES_UPDATE' not in report.reasons
    else:
        assert not report.ready(t)


def test_full_shape_target_association_fallback_is_a_flag_only():
    from harness.zone_pair_obstruction import target_component
    o, servo = image_at(.36); frame = o['image']
    model = np.full_like(frame, 100)
    labels = np.any(frame != model, axis=2).astype(np.int32)
    target = dict(order_id='beam', grip_base_m=[.36, 0.], axis_heading_rad=0.,
                  xy_slack_m=.05, yaw_slack_rad=.05, source='static order')
    assert target_component(frame, model, labels, 1, servo, target) is None
    target['allow_shape_identity'] = True
    assert target_component(frame, model, labels, 1, servo, target)['classification'] == 'expected_target_occupancy'
    assert target_component(frame, model, labels, 1, servo,
                            {**target, 'grip_base_m':[.6, .3]}) is None
    frame[200:260, 300:340] = (0, 0, 255); labels[200:260, 300:340] = 1
    assert target_component(frame, model, labels, 1, servo, target) is None


def test_partial_updates_do_not_extend_full_shape_identity_lifetime():
    track = RelativeBeamTrack(); first, servo = image_at(.36)
    assert track.observe(first, servo, 0, now=0.).ready(0.)
    partial, servo = image_at(.336, 'p45', fid=2, t=29.)
    report = track.observe(partial, servo, 0, now=29.)
    assert not report.ready(29.) and report.anchor_time_s == 0.
    assert track.beam['identity_time_s'] == 0.
    later, servo = image_at(.337, 'p45', fid=3, t=30.1)
    assert not track.observe(later, servo, 0, now=30.1).ready(30.1)
    assert track.beam['anchor_time_s'] == 0.


def test_ablation_adjacent_conditions_differ_in_exactly_one_behavior_flag():
    flags = lambda name: {k:v for k,v in vars(pair_policy(name)).items() if k != 'name'}
    for left, right in [('v5h', 'b-only'), ('b-only', 'a+b')]:
        a, b = flags(left), flags(right)
        assert sum(a[k] != b[k] for k in a) == 1


@pytest.mark.parametrize('fault', ['retained_quality', 'future_receipt', 'missing_receipt'])
def test_reacquisition_requires_current_information_not_only_retained_receipt(fault):
    env = GlobalEnvelope(); env.pose(good(), 0.)
    for t in (1., 1.2):
        assert env.pose(replace(good(t), yaw_rad=math.pi/2), t) is None
    bad = replace(good(1.3), yaw_rad=math.pi/2)
    if fault == 'retained_quality':
        bad = replace(bad, last_fix_t=1.2, observation_quality={
            'accepted':True, 'informative':False, 'settled':True, 'ambiguous':False,
            'last_fix_quality':{**good().observation_quality, 't':1.2}})
    elif fault == 'future_receipt':
        bad = replace(bad, last_fix_t=2.)
    else:
        bad = replace(bad, last_fix_t=None)
    env.pose(bad, 1.3)
    assert env.pose(replace(good(1.4), yaw_rad=math.pi/2), 1.4) is None
    assert env.fix_t == 0.


def test_reacquisition_receipt_itself_must_follow_command_stop_tail():
    env = GlobalEnvelope(); env.pose(good(), 0.)
    env.command(dict(kind='drive', t=0., forward=.01, duration_s=1.))
    # Delivery is after stopping, but the first fix predates the .2 s tail.
    for fix_t, now in ((1.05,1.3), (1.2,1.4), (1.4,1.5)):
        report = replace(good(now), last_fix_t=fix_t, yaw_rad=math.pi/2)
        assert env.pose(report, now) is None
    assert env.fix_t == 0.
