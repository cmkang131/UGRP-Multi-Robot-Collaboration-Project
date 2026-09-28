"""PR #246 final adversarial review: P1-1..3, P2-1..3 regressions (no physics, no model calls)."""
import math

import numpy as np
import pytest

from harness.zone_own_guards import OwnPose
from harness.zone_pair_global import SCHEDULED_REOBSERVE
from tests.test_zone_pair_v6_review2 import Scenario
from tests.test_zone_pair_v6_review3 import REALISTIC, _real


# ------------------------------------------------------------ P1-1 planned looks end in align

def test_three_scheduled_align_relooks_each_get_their_own_allowance():
    s = Scenario(state='align', beam_grip=.40, **REALISTIC)
    guard = s.ep.command_guard
    original = guard.global_certificate
    triggers = []

    def forced(now, beam=None):
        cert = original(now, beam)
        # Force the reserve on the first align tick after each (re)entry.
        if s.ctl.state == 'align' and beam is None and (now in triggers or len(triggers) < 3):
            if now not in triggers:
                triggers.append(now)
            cert = {**cert, 'clear': True, 'relook_reserve_low': True}
        return cert
    guard.global_certificate = forced
    s.run_until(lambda: s.ctl.state == 'pregrasp_descend', limit=90.)
    events = [e for e in s.ep.events if e['event'] == 'scheduled_reobserve']
    assert len(triggers) == 3 and [e['index'] for e in events][:3] == [1, 2, 3]
    r = guard.recheck
    assert r.scheduled_count >= 3 and r.scheduled is None
    assert r.waited_s == 0.  # HIGH recovery untouched: each look used its own 6 s
    assert r.scheduled_total_s <= 3*SCHEDULED_REOBSERVE['per_look_s']


# ------------------------------------------------------------ P1-2 identical pixels

def _obs(data, servo, fid, t, sha):
    return dict(frame_id=fid, sha256=sha, sim_time=t, image=data, actuator_state={'servo_pulses': servo})


def test_real_identical_frame_without_command_keeps_the_verdict():
    from harness.zone_pair_relative import RelativeBeamTrack
    data, servo, row = _real('v5b_dev09_r2_01491.jpg')  # raw own JPEG; stationary renders repeat bytes
    sha = row['observation']['sha256']
    track = RelativeBeamTrack()
    first = track.observe(_obs(data, servo, 1491, 1., sha), servo, 0, now=1.)
    second = track.observe(_obs(data, servo, 1492, 1.4, sha), servo, 0, now=1.4)
    assert first.ready(1.) and second.ready(1.4)
    assert second.frame_id == 1492 and second.grip_base_m == first.grip_base_m
    assert 'IDENTICAL_PIXELS_NO_NEW_COMMAND' in second.reasons and 'DUPLICATE_IMAGE' not in second.reasons
    assert second.anchor_time_s == first.anchor_time_s  # no new anchor from repeated pixels
    assert not second.closing_ready(1.4)
    # After an own issued command the same bytes are stale evidence.
    track.command({'t': 1.5, 'kind': 'mecanum', 'forward': .05, 'left': 0., 'turn': 0., 'duration_s': .3}, servo)
    third = track.observe(_obs(data, servo, 1493, 2., sha), servo, 0, now=2.)
    assert third.reasons == ('DUPLICATE_IMAGE',) and not third.ready(2.)


def test_align_skips_transient_input_instead_of_failing():
    from harness.zone_pair_relative import BeamRelativeReport
    s = Scenario(state='align', beam_grip=.36); ctl = s.ctl
    for reason in ('DUPLICATE_IMAGE', 'OUT_OF_ORDER', 'BEAM_MOVED_OR_ASSOCIATION_LOST'):
        unknown = BeamRelativeReport(frame_id=1, sha256=reason, captured_at_s=0., segment=0, camera_pwm=(),
                                     reasons=(reason,))
        ctl.look = lambda t: None
        ctl.relative_report = lambda t, o, u=unknown: u
        ctl.next_look = 0.; ctl.state_t = 0.; ctl.aligned_frame = None
        ctl._align(.1, True)
        assert ctl.state == 'align' and not s.ep.terminal


@pytest.mark.parametrize('reason', ['SHAPE_AMBIGUOUS', 'END_ID_AMBIGUOUS', 'PAIRED_EDGES_UNOBSERVABLE'])
def test_align_tries_remaining_views_for_view_dependent_identity(reason):
    from harness.zone_pair_relative import BeamRelativeReport
    s = Scenario(state='align', beam_grip=.36); ctl = s.ctl
    unknown = BeamRelativeReport(frame_id=1, sha256='a', captured_at_s=0., segment=0, camera_pwm=(),
                                 reasons=(reason,))
    chosen = []
    ctl.look = lambda t: None
    ctl.relative_report = lambda t, o: unknown
    ctl._set_look = lambda name, t, **kw: chosen.append(name)
    ctl.look_name = 'search'; ctl.next_look = 0.; ctl.state_t = 0.
    ctl._align(.1, True)
    assert chosen == ['p45'] and not s.ep.terminal


# ------------------------------------------------------------ P1-3 static-beam premise

def _anchored():
    s = Scenario(state='align', beam_grip=.40)
    s.run_until(lambda: s.ctl.state == 'pregrasp_descend', limit=60.)
    guard = s.ep.command_guard
    assert guard.object_anchor is not None and guard.object_pose(s.t) is not None
    return s, guard


def _fresh_anchor_reference(s, guard):
    # Re-take the anchor's relative reference now: no own base command since.
    from harness.zone_pair_global import GlobalEnvelope
    a, b = guard.object_anchor, guard.relative_track.beam
    a.update(rel_grip=tuple(b['grip_base_m']), rel_heading=b['axis_heading_rad'])
    m = GlobalEnvelope(); m.anchor = OwnPose(0., 0., 0., 0., 0.); m.fix_t = m.t = s.t
    guard.anchor_motion = m
    return a, b


def test_anchor_dropped_when_beam_moves_beyond_command_reach():
    s, guard = _anchored()
    a, beam = _fresh_anchor_reference(s, guard)
    gate = 2*(a['rel_bound']+beam['std_xy_m']+beam['bias_bound_m'])  # no own motion: views only
    beam['grip_base_m'] = [beam['grip_base_m'][0], beam['grip_base_m'][1]+.03]
    assert guard._anchor_invalid(s.t, a, beam) is None  # within the two view bounds
    beam['grip_base_m'] = [beam['grip_base_m'][0], beam['grip_base_m'][1]+gate]  # peer pushed it
    assert guard.object_pose(s.t) is None and guard.object_anchor is None
    assert any(e['event'] == 'object_anchor_invalidated' and e['reason'] == 'BEAM_MOVED_SINCE_ANCHOR'
               for e in s.ep.events)


def test_anchor_accepts_beam_consistent_with_own_commands():
    s, guard = _anchored()
    assert guard._anchor_invalid(s.t, guard.object_anchor, guard.relative_track.beam) is None


def test_anchor_dropped_when_global_and_anchored_bounds_disagree():
    s, guard = _anchored()
    anchored = guard.object_pose(s.t)
    far = OwnPose(anchored.x+.5, anchored.y, anchored.yaw, .03, .02)
    assert guard.safety_pose(s.t, far) is far and guard.object_anchor is None
    assert any(e['event'] == 'object_anchor_invalidated' and e['reason'] == 'GLOBAL_ANCHOR_DISAGREE'
               for e in s.ep.events)


@pytest.mark.parametrize('state', ['close_ready_0', 'close_go_0', 'ready', 'lift'])
def test_anchor_dropped_and_not_recreated_while_partner_grasps(state):
    s, guard = _anchored()
    channel = s.ctl.status[0]
    other = next(r for r in channel.participants if r != s.own.robot_id)
    channel.latest[other] = {**channel.latest.get(other, {}), 'robot_id': other, 'state': state}
    assert guard.object_pose(s.t) is None and guard.object_anchor is None
    report = type('R', (), dict(ready=lambda self, t: True))()
    guard._anchor_object(s.t, report)
    assert guard.object_anchor is None


# ------------------------------------------------------------ P2-1 approach fix-confirm dwell

def test_approach_look_fix_confirm_dwell_is_bounded():
    s = Scenario(goal=(1., -1., 0.))
    drv = s.ctl.driver
    drv.verified_global_fix = lambda now, t0: False
    drv.look_queue.clear()
    drv.arm_target = {k: s.own.servo[k] for k in (3, 4, 5)}
    drv.servo = dict(s.own.servo)
    drv.look_t0 = 10.
    assert drv._look_step(10.+SCHEDULED_REOBSERVE['per_look_s']-.1) == [{'kind': 'hold'}]
    calls = []
    import harness.zone_pair_guards as guards
    base = guards.PairApproachDriverV2.__mro__[1]
    original = base.tick
    try:
        base.tick = lambda self, now: calls.append(now) or []
        assert drv._look_step(10.+SCHEDULED_REOBSERVE['per_look_s']) == []
    finally:
        base.tick = original
    assert calls  # handed to the frozen look_done / no-fix path


# ------------------------------------------------------------ P2-2 per-attempt budgets

@pytest.mark.parametrize('policy', ['v5h', 'b-only', 'a+b'])
def test_look_and_high_budgets_reset_per_alignment_attempt_for_every_condition(policy):
    from harness.zone_pair_v6_policy import pair_policy
    s = Scenario(state='align', beam_grip=.40)
    s.ep.policy = pair_policy(policy)
    ctl, r = s.ctl, s.ep.command_guard.recheck
    ctl.align_look_count, ctl.align_look_total_s, r.waited_s = 8, 39., 9.5
    ctl.set('align', 5.)  # a new attempt (e.g. regrasp), not a relook return
    assert r.waited_s == 0.
    assert ctl.align_look_count <= 1 and ctl.align_look_total_s == 0.  # v5h/b-only take one entry look
    assert any(e['event'] == 'phase_budget_reset' for e in s.ep.events)
