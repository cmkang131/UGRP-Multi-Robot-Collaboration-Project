"""PR #235 review 5: real report/controller paths, no physics or model calls."""
from dataclasses import replace

import pytest

from harness.zone_own_sweep import SWEEP_REOBSERVE_S
from tests.test_zone_own_executor_guards import ScriptedLoc
from tests.test_zone_pair_executor import active, ends, m2_controller, pair_obs, setup, start
from tests.test_zone_pair_review4 import checkpoint


def accumulated_time():
    now = 0.
    for _ in range(2400):
        now += .00025
    return now


def real_report(own, now):
    loc = own.pose.loc
    loc.initialized, loc.t = True, now
    loc.px[:] = [0., 0., 0.]
    return own.pose.report(now)


@pytest.mark.parametrize('entry', ['submission', 'before_control', 'command'])
def test_p1_1_real_rounded_report_on_accumulated_clock_is_fresh(entry):
    host, exs = setup(factory=m2_controller)
    now = accumulated_time()
    if entry != 'submission':
        assert start(host)['accepted']
    for rid, own in exs.items():
        own.last_report = real_report(own, now)
        own.last_obs = pair_obs(rid, 2, now, own.servo)
        assert own.last_report.t_est == .6 > now
    host.world.data.time = now
    if entry == 'submission':
        assert start(host)['accepted']
        return
    ep = active(host)['r1']
    ep.controller.state = 'carry'
    if entry == 'before_control':
        assert ep.command_guard.before_control(now)
    else:
        cmd = {'kind': 'mecanum', 'forward': .01, 'left': 0., 'turn': 0., 'duration_s': .1}
        assert ep.command_guard.check(now, [cmd]) == [cmd]
    assert not ep.terminal


@pytest.mark.parametrize('entry', ['submission', 'before_control', 'command'])
@pytest.mark.parametrize('offset,accepted', [(.000099, True), (.0001, True), (.000101, False),
                                            (-.3, True), (-.30001, False),
                                            (float('nan'), False), (float('inf'), False)])
def test_p1_1_timestamp_tolerance_is_bounded(entry, offset, accepted):
    host, exs = setup()
    if entry != 'submission':
        assert start(host)['accepted']
    own = exs['r1']
    own.last_report = replace(own.last_report, t_est=offset)
    if entry == 'submission':
        assert host.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')['accepted'] == accepted
        return
    ep = active(host)['r1']
    ep.controller.state = 'carry'
    if entry == 'before_control':
        assert ep.command_guard.before_control(0.) == accepted
    else:
        cmd = {'kind': 'mecanum', 'forward': .01, 'left': 0., 'turn': 0., 'duration_s': .1}
        assert ep.command_guard.check(0., [cmd]) == ([cmd] if accepted else [{'kind': 'hold'}])
    assert ep.terminal != accepted


def uncertain_approach():
    host, exs = setup(factory=m2_controller)
    assert start(host)['accepted']
    ep, own = active(host)['r1'], exs['r1']
    own.last_report = replace(own.last_report, std_xy_m=.081)
    ep.controller.driver.loc = ScriptedLoc(lambda t: (0., 0., 0., .081, .01, 0.))
    ep.controller.driver.state = 'drive'
    decision = ep.step(0.)
    assert decision['commands'] == [{'kind': 'hold'}]
    assert ep.controller.driver.state == 'look_arm'
    return host, ep, own


def fresh(own, now, sigma):
    own.last_report = replace(own.last_report, t_est=now, initialized=True,
                              x_m=0., y_m=0., yaw_rad=0., std_xy_m=sigma, std_yaw_rad=.01)
    own.last_obs = pair_obs(own.robot_id, own.last_obs['frame_id'] + 1, now, own.servo)


def test_p1_2_real_approach_high_sigma_keeps_stationary_relook_alive():
    _, ep, own = uncertain_approach()
    fresh(own, .05, .081)
    ep.step(.05)
    assert not ep.terminal
    fresh(own, .1, .081)
    commands = ep.step(.1)['commands']
    assert commands and all(c['kind'] in ('hold', 'arm', 'look') for c in commands)
    assert not ep.terminal
    fresh(own, .15, .01)
    assert ep.command_guard.before_control(.15)
    assert not ep.terminal


def test_p1_2_checkpoint_high_sigma_preserves_64_queued_arm_commands():
    ep, own = checkpoint()
    fresh(own, .05, .081)
    ep.step(.05)
    assert not ep.terminal and len(ep.controller.arm.events) == 64
    commands = ep.arm_step(.05)
    assert commands and all(c['kind'] in ('hold', 'arm', 'look') for c in commands)
    assert not ep.terminal


@pytest.mark.parametrize('kind', ['drive', 'mecanum'])
def test_p1_2_high_sigma_relook_still_rejects_all_base_motion(kind):
    ep, own = checkpoint()
    fresh(own, .05, .081)
    cmd = {'kind': kind, 'forward': .01, 'left': 0., 'turn': 0., 'duration_s': .1}
    assert ep.command_guard.check(.05, [cmd]) == [{'kind': 'hold'}]
    assert ep.terminal


def test_p1_2_collision_wait_preserves_arm_queue_then_resumes_without_burst():
    from harness.zone_own_guards import OwnPose
    from harness.zone_pair_geometry import PairSweepGuard
    from harness.zone_pair_status import PairStatusEndpoint
    ep, own = checkpoint()
    peer = PairStatusEndpoint(ep.status.channel, 'r2')
    peer.seq = ep.status.channel.latest['r2']['seq']
    arm = ep.controller.arm
    original, until = list(arm.events), arm.until
    first_targets = {**own.servo, **{sid: pulse for _, sid, pulse in original[:4]}}
    geometry = PairSweepGuard(own.guard, ep.plan['beam_geometry'], ep.arguments['role'])
    high, low = OwnPose(-.8, 0., 0., .081, .01), OwnPose(-.8, 0., 0., .01, .01)
    assert not geometry.transition_clear(own.servo, first_targets, high, loaded=False)
    assert geometry.transition_clear(own.servo, first_targets, low, loaded=False)
    for now, sigma in [(.05, .081), (.1, .081), (.15, .01)]:
        fresh(own, now, sigma)
        own.last_report = replace(own.last_report, x_m=-.8)
        ep.status.tick('aligning', now)
        peer.tick('aligning', now)
        commands = ep.arm_step(now)
        assert not ep.terminal
        if sigma > .08:
            assert commands == [{'kind': 'hold'}]
            assert len(arm.events) == 64
            assert [(s, p) for _, s, p in arm.events] == [(s, p) for _, s, p in original]
        else:
            assert len(commands) == 4 and len(arm.events) == 60
    assert arm.until == pytest.approx(until + .1)


def test_p1_2_driver_collision_wait_and_high_sigma_spend_one_budget():
    from harness.zone_own_guards import OwnPose
    host, exs = setup(factory=m2_controller)
    assert start(host)['accepted']
    ep, own = active(host)['r1'], exs['r1']
    driver = ep.controller.driver
    # Moderate uncertainty blocks the inflated sweep near the west wall.
    # The real driver's sweep budget is also the pair's high-sigma budget.
    pose = OwnPose(-.85, 0., 0., .07, .01)
    from harness.owncam_drive import LOOK_P20
    assert driver.sweep_recheck.check(0., own.guard, own.servo, LOOK_P20, pose, loaded=False) == 'wait'
    assert driver.sweep_recheck.check(6., own.guard, own.servo, LOOK_P20,
                                      replace(pose, std_xy=.001), loaded=False) == 'clear'
    driver.state = 'look_arm'
    for now in (6., 9.99):
        fresh(own, now, .081)
        assert ep.command_guard.before_control(now)
    fresh(own, 10., .081)
    assert not ep.command_guard.before_control(10.)
    assert ends(own)[0]['detail']['reason'] == 'PAIR_REOBSERVE_TIMEOUT'


def test_p1_2_budget_is_cumulative_across_clear_intervals_and_new_sweeps():
    _, ep, own = uncertain_approach()
    for now, sigma in [(4., .081), (6., .01), (7., .081), (10.99, .081)]:
        fresh(own, now, sigma)
        assert ep.command_guard.before_control(now)
        if now == 6.:
            # The real driver starts another look; this must not refill the budget.
            ep.controller.driver._start_look(now, 'gate_uncertain', allow_backoff=False)
    fresh(own, 11., .081)
    assert not ep.command_guard.before_control(11.)
    assert ends(own)[0]['detail']['reason'] == 'PAIR_REOBSERVE_TIMEOUT'


def test_p1_2_budget_exhaustion_stops_both_and_clears_all_pending_motion():
    host, ep, own = uncertain_approach()
    eps = active(host)
    for rid in eps:
        host.robots[rid].timeline = [(20., [{'kind': 'arm', 'servo_id': 1, 'pulse': 2000}])]
        host.robots[rid].capture_after = True
    # Keep the peer heartbeat live without consulting its private controller state.
    for tick in range(1, 201):
        now = round(tick * .05, 4)
        fresh(own, now, .081)
        eps['r2'].status.tick('aligning', now)
        ep.step(now)
        host._pair_safety(now)
        if ep.terminal:
            break
    assert now == SWEEP_REOBSERVE_S
    assert ends(own)[0]['detail']['reason'] == 'PAIR_REOBSERVE_TIMEOUT'
    assert ends(eps['r2'].own)[0]['detail']['reason'] == 'PARTNER_ABORT'
    for rid, endpoint in eps.items():
        assert endpoint.terminal and not endpoint.controller.arm.events and not endpoint.controller.schedule
        assert not host.robots[rid].timeline and not host.robots[rid].capture_after
        assert any(t == now and k == 'hold' for t, k, _ in host.robots[rid].port.log)


@pytest.mark.parametrize('phase', ['grasp', 'wait_lift', 'lift', 'wait_carry', 'carry'])
def test_p1_2_high_sigma_during_joint_grasp_stops_both_without_unilateral_relook(phase):
    host, exs = setup(factory=m2_controller)
    assert start(host)['accepted']
    eps = active(host)
    for ep in eps.values():
        ep.controller.state = phase
    fresh(exs['r1'], .05, .081)
    host._decide('r1', .05)
    assert all(ep.terminal and not ep.controller.arm.events for ep in eps.values())
    assert ends(exs['r1'])[0]['detail']['reason'] == 'POSE_UNCERTAIN'
    assert ends(exs['r2'])[0]['detail']['reason'] == 'PARTNER_ABORT'
    for rid in eps:
        assert any(t == .05 and k == 'hold' for t, k, _ in host.robots[rid].port.log)
