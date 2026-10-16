"""v98 look-around (#363 probe 7623c4dc): r2 held 6.3 s at the dock with two ``hold`` per tick.

Simulator-free. The scripted own estimates are interpolated from the recorded r1/r2 localizer replays (position
x/y, sigma along x and y, yaw sigma, shifted by the 1.3 s job start); arm moves and views are NOT simulated, so
the sigma traces are counterfactual fixtures (r2's stays at the no-pan trajectory), not closed-loop logs.
The shared executor/guard modules are untouched; the fix is installed by ``adopt_v98_frame_gate``.
"""
from __future__ import annotations

import json
import math
import types

import numpy as np
import pytest

from harness import zone_own_guards as guards
from harness import zone_pair_highpose_lookaround as look
from harness import zone_pair_highpose_runtime as rt
from harness.owncam_pose_source import PoseReport
from harness.zone_final_pair_guards import PairArmGuard
from harness import zone_pair_highpose_contract as c
from harness.zone_own_executor import ZoneOwnExecutor
from tests.test_zone_final_pair_v3 import MAPS
from tests.test_zone_own_executor import Driver
from tests.test_zone_own_executor_guards import scripted

JOB_START_S = 1.3                         # both robots started the look-around job at 1.3 s in the probe
T = [1.3, 1.95, 2.0, 2.1, 2.5, 3.0, 5.0, 8.3]
RECORDED = {                              # x, y, yaw, sigma_x, sigma_y, sigma_yaw per T, from the faithful replay
    'r1': ([-.810, -.825, -.846, -.858, -.868, -.870, -.839, -.920], [-.918, -.026, .542, .616, .645, .664, .609, .575],
           [.001, -.028, -.027, -.028, -.036, -.044, -.020, -.017], [.103, .086, .081, .064, .027, .019, .005, .006],
           [1.235, .758, .331, .111, .044, .036, .006, .002], [.162, .088, .070, .045, .015, .012, .004, .003]),
    'r2': ([-.814, -.869, -.902, -.914, -.927, -.929, -.924, -.922], [-.833, -.528, -.548, -.587, -.634, -.654, -.676, -.675],
           [.004, -.014, -.002, .004, .010, .010, .007, .005], [.103, .071, .048, .036, .023, .017, .007, .003],
           [1.190, .608, .465, .376, .206, .174, .121, .070], [.178, .075, .044, .030, .017, .012, .005, .004]),
}
SERVO = {1: 2000, 3: 1072, 4: 2400, 5: 1482, 6: 1500}


class CovPose:
    """Scripted own estimate that also reports the position covariance (as the real provider does)."""
    source = 'diagnostic_scripted_estimate'

    def __init__(self, rid):
        self.table = RECORDED[rid]

    def on_command(self, row):
        pass

    def on_frame(self, now, rgb):
        return self.report(now)

    def set_motion_profile(self, t, name):
        pass

    def report(self, now):
        t = now + JOB_START_S
        x, y, yaw, sx, sy, syaw = (float(np.interp(t, T, v)) for v in self.table)
        cov = ((sx * sx, 0., 0.), (0., sy * sy, 0.), (0., 0., syaw * syaw))
        return PoseReport(now, True, x, y, yaw, cov, math.hypot(sx, sy), syaw, .1,
                          source=self.source, last_fix_t=now - .1, fix_age_s=.1)


def pair_executor(rid, *, adopted=True):
    """The pair runtime's executor: ZoneOwnExecutor + PairArmGuard, optionally through the real v98 adoption."""
    ex = scripted(lambda t: (0., 0., 0., 0., 0., .1), rid=rid)
    ex.pose = CovPose(rid)
    ex.guard = PairArmGuard(c.resolve(MAPS[0])[0])
    if adopted:
        rt.adopt_v98_frame_gate(types.SimpleNamespace(actors={rid: ex}))
    return ex


def look_around(ex, limit_s=20.):
    d = Driver(ex)
    ex.look_around()
    d.run(limit_s, stop=lambda: ex.job is None)
    done = [e for e in ex.events if e['event'] in ('job_done', 'job_failed')]
    assert len(done) == 1, done
    return d, done[0]


def first_pan_s(d):
    return min(t for t, raw in d.decisions if any(c['kind'] == 'look' for c in json.loads(raw)['commands']))


def kinds_per_tick(d):
    return [(t, [c['kind'] for c in json.loads(raw)['commands']]) for t, raw in d.decisions]


# ------------------------------------------------------------------ the executor, through the v98 adoption
@pytest.mark.parametrize('rid', ['r1', 'r2'])
def test_look_around_finishes_in_bounded_time_with_one_hold_per_tick(rid):
    ex = pair_executor(rid)
    d, end = look_around(ex)
    assert end['event'] == 'job_done' and end['detail']['outcome'] in ('LOOKED', 'LOOKED_POSE_UNCERTAIN'), end
    # v98 dock look (relook.DOCK_LOOK_PANS): 8 pans x 0.6 s settle + 3200 PWM of pan travel at 60 PWM per 0.1 s tick
    # + arm/restore: 12.3 s for both robots (was 9.0 s with the 6 WIDE_LOOK_PANS). The probe's r1 (0.05 s tick)
    # took 7.0 s with the old pans; r2 never finished.
    assert end['sim_s'] <= 12.5, end['sim_s']
    assert end['sim_s'] > 9.5, end['sim_s']                       # the two extra pans are visited
    assert first_pan_s(d) <= 2.0, first_pan_s(d)
    assert all(kinds.count('hold') <= 1 for _, kinds in kinds_per_tick(d))


def test_both_robots_finish_together():
    ends = {rid: look_around(pair_executor(rid))[1]['sim_s'] for rid in ('r1', 'r2')}
    assert abs(ends['r1'] - ends['r2']) <= .5, ends             # the pair rendezvous waits 5 s for the slower one


def test_shared_pair_guard_waits_for_r2_until_sigma_y_falls():
    """Control: adopted executor but the shared PairArmGuard (isotropic): the probe's wait, now one hold per tick."""
    ex = pair_executor('r2')
    ex.guard.__class__ = PairArmGuard
    d, end = look_around(ex, limit_s=40.)
    assert first_pan_s(d) >= 6.5, first_pan_s(d)
    assert end['event'] == 'job_failed' or end['sim_s'] > 12., end   # the 10 s wait budget is spent on the way
    waits = [kinds for t, kinds in kinds_per_tick(d) if 1. <= t < 6.]
    assert waits and all(kinds == ['hold'] for kinds in waits), waits[:2]


def test_shared_executor_still_double_holds_in_a_guard_wait():
    """Documents the shared behaviour v98 overrides (probe: [hold, hold] per tick). Delete with a shared fix."""
    ex = pair_executor('r2', adopted=False)
    d, _ = look_around(ex)
    assert ['hold', 'hold'] in [kinds for t, kinds in kinds_per_tick(d) if 1. <= t < 6.]


def test_r1_is_unchanged_by_the_obstacle_normal_margin():
    ex = pair_executor('r1')
    ex.guard.__class__ = PairArmGuard
    _, iso = look_around(ex)
    _, directional = look_around(pair_executor('r1'))
    assert iso['sim_s'] == pytest.approx(directional['sim_s'], abs=.3)


def test_adoption_installs_the_v98_classes_and_fails_closed_on_another_guard():
    ex = pair_executor('r1')
    assert type(ex) is rt.OwnExecutor and type(ex.guard) is look.LookAroundGuard
    assert rt.OwnExecutor._sweep_steps.v98_look_around and rt.OwnExecutor._tick_sweep.v98_look_around
    assert rt.OwnExecutor.__mro__[1] is ZoneOwnExecutor
    assert rt.adopt_v98_frame_gate(types.SimpleNamespace(actors={}))['look_around'] == look.record()
    other = scripted(lambda t: (0., 0., 0., 0., 0., .1), rid='r2')       # default SweepGuard, not the pair arm guard
    with pytest.raises(TypeError, match='PairArmGuard'):
        rt.adopt_v98_frame_gate(types.SimpleNamespace(actors={'r2': other}))
    assert type(other) is ZoneOwnExecutor


def test_shared_classes_are_not_modified_by_adoption():
    pair_executor('r1')
    assert not hasattr(PairArmGuard, 'directional_sigma') and not hasattr(guards.OwnPose, 'cov_xy')
    assert not hasattr(ZoneOwnExecutor._tick_sweep, 'v98_look_around') and not hasattr(ZoneOwnExecutor._sweep_steps, 'v98_look_around')
    plain = PairArmGuard(c.resolve(MAPS[0])[0])
    assert type(plain) is PairArmGuard and plain.arm_clearance(SERVO, guards.OwnPose(-.9, -.7, 0., .1, .02), loaded=False)[1]


# ------------------------------------------------------------------ the guard itself
def box(yaw=0.):
    return {'id': 'b', 'center': (.3, -.2), 'half': (.4, .05), 'yaw': yaw, 'height': 1.}


@pytest.mark.parametrize('yaw', [0., .6])
def test_rect_normal_is_a_subgradient_of_the_distance_and_the_distance_is_bit_identical(yaw):
    rng = np.random.default_rng(3)
    b = box(yaw)
    for _ in range(300):
        p = rng.uniform(-1.2, 1.5, 2)
        d, n = look.rect_distance_normal(b, *p)
        assert d == guards._rect_distance(b, *p)
        if n is None:
            assert d == 0.
            continue
        assert math.hypot(*n) == pytest.approx(1.)
        delta = rng.normal(0., .1, 2)
        assert guards._rect_distance(b, *(p + delta)) >= d + n[0] * delta[0] + n[1] * delta[1] - 1e-12


def hinted(static, pose, report_cov):
    guard = look.LookAroundGuard(static)
    guard.hint = (pose.x, pose.y, pose.yaw, pose.std_xy, pose.std_yaw, look.cov_xy(report_cov, pose.std_xy))
    return guard


def test_obstacle_normal_sigma_never_exceeds_the_shared_margin_and_matches_it_for_a_round_estimate():
    static = c.resolve(MAPS[0])[0]
    shared = PairArmGuard(static)
    for sx, sy in [(.03, .4), (.4, .03), (.1, .1), (.0, .0), (.05, .07)]:
        std = math.hypot(sx, sy)
        cov = ((sx * sx, 0, 0), (0, sy * sy, 0))
        pose = guards.OwnPose(-.9, -.7, 0., std, .02)
        guard = hinted(static, pose, cov)
        shared_c, new_c = shared.arm_clearance(SERVO, pose, loaded=False), guard.arm_clearance(SERVO, pose, loaded=False)
        assert new_c[0] >= shared_c[0] - 1e-12
        assert guard.margin(pose, .2) == shared.margin(pose, .2)               # the plain margin is unchanged
    round_pose = guards.OwnPose(-.9, -.7, 0., .1, .02)
    round_guard = hinted(static, round_pose, ((.005, 0, 0), (0, .005, 0)))
    assert round_guard.arm_clearance(SERVO, round_pose, loaded=False) == shared.arm_clearance(SERVO, round_pose, loaded=False)
    assert look.sigma_toward(.4, look.cov_xy(((.0009, 0, 0), (0, .16, 0)), math.hypot(.03, .4)), (0., 1.)) == pytest.approx(.4)
    assert look.sigma_toward(.4, look.cov_xy(((.0009, 0, 0), (0, .16, 0)), math.hypot(.03, .4)), (1., 0.)) == \
        pytest.approx(math.sqrt(2.) * .03)


def test_only_the_ticks_own_pose_gets_the_obstacle_normal_margin():
    static = c.resolve(MAPS[0])[0]
    pose = guards.OwnPose(-.92, -.675, 0., math.hypot(.003, .47), .02)
    guard = hinted(static, pose, ((.003 ** 2, 0, 0), (0, .47 ** 2, 0)))
    shared = PairArmGuard(static)
    assert guard.arm_clearance(SERVO, pose, loaded=False)[0] > shared.arm_clearance(SERVO, pose, loaded=False)[0]
    moved = pose.moved(.05, 0.)                                                # back-off candidate: isotropic
    assert guard.arm_clearance(SERVO, moved, loaded=False) == shared.arm_clearance(SERVO, moved, loaded=False)
    no_hint = look.LookAroundGuard(static)
    assert no_hint.arm_clearance(SERVO, pose, loaded=False) == shared.arm_clearance(SERVO, pose, loaded=False)


def test_covariance_that_disagrees_with_std_xy_keeps_the_isotropic_margin():
    cov = ((.0025, 0., 0.), (0., .01, 0.))                               # sqrt(trace) = 0.112
    assert look.cov_xy(cov, math.sqrt(.0125)) is not None
    assert look.cov_xy(cov, .3) is None                                  # a provider inflated std_xy only
    assert look.cov_xy((), .1) is None and look.cov_xy(None, .1) is None
    assert look.cov_xy(((.01, .02, 0.), (.02, .01, 0.)), math.sqrt(.02)) is None   # not PSD


def test_diagnostic_reports_the_margin_the_decision_used():
    static = c.resolve(MAPS[0])[0]
    pose = guards.OwnPose(-.92, -.675, 0., math.hypot(.003, .47), .02)
    guard = hinted(static, pose, ((.003 ** 2, 0, 0), (0, .47 ** 2, 0)))
    cur = {**SERVO}
    evidence = guard.transition_diagnostic(cur, {6: 1230}, pose, loaded=False)
    clearance = min(guard.arm_clearance(s, pose, loaded=False)[0] for s in guard.transition_samples(cur, {6: 1230}))
    assert evidence['limiting']['clearance_mm'] == pytest.approx(1000 * clearance)
    assert evidence['sigma_model'] == look.ID and clearance > 0.
