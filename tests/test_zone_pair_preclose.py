"""PR #240 P1: independent own-RGB beam geometry before/during close; no physics."""
from dataclasses import replace
import math

import pytest

from harness.zone_own_guards import OwnPose
from harness.zone_pair_geometry import PairSweepGuard
from harness.zone_pair_grasp import stationary_beam_estimate
from tests.test_zone_pair_grasp import beam_fit, fresh, real_pair, ready_to_close


def closing_commands(host):
    return [c for r in ('r1', 'r2') for c in host.robots[r].commands
            if c['kind'] == 'arm' and c['servo_id'] == 1 and c['pulse'] < 2000]


@pytest.fixture
def post_collision():
    # Review fixture: own RGB localization, NOT evaluator/simulator truth.
    return dict(x_m=1.5, y_m=.4, yaw_rad=0., std_xy_m=.001, std_yaw_rad=.001)


def test_review240_post_overlap_never_publishes_ready_or_closes(beam_fit, post_collision, monkeypatch):
    host, _, eps = real_pair()
    a = eps['r1']
    for ep in eps.values():
        ready_to_close(ep, 1.)
        ep.status.tick('aligning', 1.)
    a.own.last_report = replace(a.own.last_report, **post_collision)
    pose = OwnPose.from_report(a.own.last_report)
    guard = PairSweepGuard(a.own.guard, a.plan['beam_geometry'], a.arguments['role'])
    assert guard.arm_clearance(a.own.servo, pose, loaded=False)[0] == pytest.approx(.423, abs=.001)
    # Raw geometric overlap is -27.5 mm even BEFORE subtracting 35 mm + sigma.
    beam = stationary_beam_estimate(a.own.last_obs, a.own.servo)
    assert guard.stationary_beam_clearance(beam, pose)[0] < -.0275 - .035
    with monkeypatch.context() as diagnostic:
        diagnostic.setattr(guard, 'margin', lambda pose, lever: 0.)
        raw, wall = guard.stationary_beam_clearance({**beam, 'std_xy_m': 0., 'std_yaw_rad': 0.}, pose)
        assert raw == pytest.approx(-.0275, abs=.00001) and wall == 'wall_divider_2'
    for now in (1., 1.1, 1.2):
        for ep in eps.values():
            fresh(ep, now, grip=True)
            if ep.controller.state == 'wait_close':
                ep.controller._wait_close(now, True)
            ep.check(now)
    for i in range(25, 35):
        now = round(i * .05, 4)
        for ep in eps.values():
            fresh(ep, now, grip=True)
            ep.status.tick(ep.status.state, now)
        host._pair_arm_tick(now)
    assert not any(r['robot_id'] == 'r1' and r['state'] == 'close_ready_0'
                   for r in a.status.channel.log)
    assert closing_commands(host) == []
    assert all(ep.terminal and not ep.controller.arm.events for ep in eps.values())


@pytest.mark.parametrize('fault', ['missing', 'clipped', 'spread', 'axis', 'nan', 'zero_length', 'no_band'])
def test_unavailable_or_uncertain_rgb_beam_cannot_ready(beam_fit, fault):
    _, _, eps = real_pair()
    ep = eps['r1']
    ready_to_close(ep, 1.)
    if fault == 'missing': beam_fit.pop('grip_base_m')
    elif fault == 'clipped': beam_fit['end_visible'] = False
    elif fault == 'spread': beam_fit['lateral_spread_m'] = .051
    elif fault == 'axis': beam_fit.update(lateral_spread_m=.01, visible_length_m=.01)
    elif fault == 'nan': beam_fit['axis_heading_rad'] = math.nan
    elif fault == 'zero_length': beam_fit['visible_length_m'] = 0.
    else: beam_fit['grip_source'] = 'end_plus_inset_v1'
    ep.controller._wait_close(1., True)
    assert ep.controller.failure == 'PREGRASP_NOT_READY'
    assert not ep.controller.arm.events
    assert not any(r['state'] == 'close_ready_0' for r in ep.status.channel.log)


def test_grip_signature_without_full_beam_pose_is_not_ready():
    _, _, eps = real_pair()
    ep = eps['r1']
    ready_to_close(ep, 1.)
    ep.controller._wait_close(1., True)
    assert ep.controller.failure == 'PREGRASP_NOT_READY'
    assert not ep.controller.arm.events


@pytest.mark.parametrize('at', [1.25, 1.45, 1.7])
@pytest.mark.parametrize('fault', ['wall', 'missing', 'uncertain', 'stale'])
def test_each_close_pwm_rechecks_beam_and_clears_both_queues(beam_fit, post_collision, at, fault):
    host, _, eps = real_pair()
    for ep in eps.values():
        ready_to_close(ep, 1.)
        ep.status.tick('aligning', 1.)
    for now in (1., 1.1, 1.2):
        for ep in eps.values():
            fresh(ep, now, grip=True)
            ep.controller._wait_close(now, True)
    assert all(ep.controller.state == 'grasp' for ep in eps.values())
    before_fault = None
    for i in range(25, 36):
        now = round(i * .05, 4)
        for ep in eps.values():
            fresh(ep, now, grip=True)
            ep.status.tick(ep.status.state, now)
        if now >= at:
            if before_fault is None:
                before_fault = len(closing_commands(host))
            ep = eps['r1']
            if fault == 'wall': ep.own.last_report = replace(ep.own.last_report, **post_collision)
            elif fault == 'missing': beam_fit['visible'] = False
            elif fault == 'uncertain': beam_fit['lateral_spread_m'] = .051
            else: ep.own.last_obs['sim_time'] = 0.
        host._pair_arm_tick(now)
    assert len(closing_commands(host)) == before_fault
    if at == 1.25:
        assert closing_commands(host) == []
    assert all(ep.terminal and not ep.controller.arm.events for ep in eps.values())


def test_stationary_geometry_uses_rgb_pose_and_both_uncertainties(beam_fit):
    _, _, eps = real_pair()
    ep = eps['r1']
    ready_to_close(ep, 1.)
    # With this own pose, translating the observed beam toward the post changes
    # the decision, even though the commanded tool/grasp point stays unchanged.
    ep.own.last_report = replace(ep.own.last_report, x_m=1.35, y_m=.4,
                                 std_xy_m=.001, std_yaw_rad=.001)
    assert ep.command_guard.preclose_check(1., ep.own.last_obs)
    beam_fit['grip_base_m'] = [.32, 0.]
    assert not ep.command_guard.preclose_check(1., ep.own.last_obs)
    beam_fit['grip_base_m'] = [.162, 0.]
    beam_fit['lateral_spread_m'] = .025
    assert not ep.command_guard.preclose_check(1., ep.own.last_obs)


def test_stationary_beam_keeps_35mm_boundary(beam_fit):
    _, _, eps = real_pair()
    ep = eps['r1']
    guard = PairSweepGuard(ep.own.guard, ep.plan['beam_geometry'], ep.arguments['role'])
    beam = {**beam_fit, 'std_xy_m': 0., 'std_yaw_rad': 0.}
    pose = OwnPose(0., 0., 0., 0., 0.)
    radius = math.sqrt(.02 ** 2 + .016 ** 2 + .01 ** 2)
    # Flat wall in front of the far end; this also checks the full beam length.
    far = .162 + .57
    for clearance in (.0349, .0351):
        guard.boxes = [dict(id='fixture_wall', center=(far + radius + clearance + .1, 0.),
                            half=(.1, 1.), yaw=0., height=1.)]
        gap, wall = guard.stationary_beam_clearance(beam, pose)
        assert wall == 'fixture_wall'
        assert gap == pytest.approx(clearance - .035)
