"""PR #235 review 4: own-input regressions, no simulator or physical stepping."""
import math
from dataclasses import replace

import pytest

from harness import visual_arm as va
from harness.zone_own_guards import OwnPose
from tests.test_zone_pair_executor import (
    active, m2_controller, pair_obs, setup, start,
)
from tests.test_zone_own_executor import rgb_of


def checkpoint():
    host, exs = setup(factory=m2_controller)
    assert start(host)['accepted']
    ep, own = active(host)['r1'], exs['r1']
    ep.started = ep.control_started = True
    ep.next_control = .1
    ctl = ep.controller
    ctl.state = 'cp_open'
    ctl.arm.events.clear()
    ctl.arm.until = 0.
    assert ep.command_guard.before_control(0.)
    ctl._cp_open(0., True)  # REAL M2 transition resets the shared localizer
    assert ctl.state == 'pregrasp_look' and len(ctl.arm.events) == 64
    frame = pair_obs('r1', 2, .05, own.servo)
    own.on_frame(.05, frame, rgb_of(frame))  # recorded, tagless own-camera fixture
    assert not own.last_report.initialized
    return ep, own


def test_p1_1_checkpoint_first_tagless_frame_keeps_stationary_look_queue():
    ep, own = checkpoint()
    ep.step(.05)
    assert not ep.terminal and len(ep.controller.arm.events) == 64
    commands = ep.arm_step(.05)
    assert commands and all(c['kind'] in ('hold', 'arm', 'look') for c in commands)
    assert not ep.terminal


@pytest.mark.parametrize('kind', ['mecanum', 'drive'])
def test_p1_1_reobservation_never_allows_base_motion(kind):
    ep, _ = checkpoint()
    cmd = {'kind': kind, 'forward': .05, 'turn': 0., 'duration_s': .15}
    if kind == 'mecanum':
        cmd['left'] = 0.
    assert ep.command_guard.check(.05, [cmd]) == [{'kind': 'hold'}]
    assert ep.terminal


@pytest.mark.parametrize('fault', ['motion_since_pose', 'no_anchor', 'wall', 'carry', 'grasp', 'stale_frame'])
def test_p1_1_cached_pose_cannot_bypass_motion_pose_or_arm_collision_guards(fault):
    from harness.zone_own_guards import SweepGuard
    ep, own = checkpoint()
    if fault == 'motion_since_pose':
        own.on_command({'t': 0., 'kind': 'mecanum', 'forward': .05, 'left': 0., 'turn': 0., 'duration_s': .01})
        own.on_command({'t': .01, 'kind': 'hold'})
    elif fault == 'no_anchor':
        ep.command_guard.stationary_pose = None
    elif fault == 'wall':
        own.guard = SweepGuard({'obstacles': [{'id': 'wall', 'center_m': [0., 0.],
                                              'half_extents_m': [1., 1.], 'height_m': 1.}]})
    elif fault in ('carry', 'grasp'):
        ep.controller.state = fault
    else:
        own.last_report = replace(own.last_report, t_est=-1.)
    cmd = {'kind': 'look', 'pan_pulse': 1520}
    assert ep.command_guard.check(.05, [cmd]) == [{'kind': 'hold'}]
    assert ep.terminal


def test_p1_1_tagless_sweeps_reach_original_bounded_failure_not_first_frame_abort():
    from harness.zone_pair_status import PairStatusEndpoint
    ep, own = checkpoint()
    peer_wire = PairStatusEndpoint(ep.status.channel, 'r2')
    peer_wire.seq = ep.status.channel.latest['r2']['seq']
    ep.status.tick('start_ready', 0.)
    peer_wire.tick('start_ready', 0.)
    emitted = []
    # Real M2 control/arm clocks and tagless recorded frames; no world stepping.
    for tick in range(1, 401):
        now = round(tick * .05, 3)
        peer_wire.tick('aligning', now)
        frame = pair_obs('r1', tick + 2, now, own.servo)
        own.on_frame(now, frame, rgb_of(frame))
        result = ep.step(now)
        commands = result.get('commands', []) + ep.arm_step(now)
        emitted.extend(commands)
        for cmd in commands:
            own.on_command({'t': now, **cmd})
        if ep.terminal:
            break
    assert ep.terminal and ep.controller.pregrasp_sweeps == 2
    assert ep.controller.failure == 'DOOR_POSE_NOT_LOCALIZED'
    assert own.gate.state == 'uncertain'
    assert len([c for c in emitted if c['kind'] in ('arm', 'look')]) > 64
    assert not any(c['kind'] in ('mecanum', 'drive') for c in emitted)


@pytest.mark.parametrize('duration,clear', [(.1, True), (.6, False)])
def test_p1_2_full_backoff_duration_rejects_collision_after_first_control_tick(duration, clear):
    host, exs = setup()
    assert start(host)['accepted']
    ep, own = active(host)['r1'], exs['r1']
    ep.controller.state = 'align'
    own.last_report = replace(own.last_report, x_m=-.826, std_xy_m=.001, std_yaw_rad=.001)
    pose = OwnPose.from_report(own.last_report)
    # Actual tagged map: rear chassis is clear at 0.1 s, hits the west wall at 0.2 s.
    assert own.guard.chassis_clearance(pose.moved(-.05 * 1.6 * .1, 0.))[0] > 0.
    assert own.guard.chassis_clearance(pose.moved(-.05 * 1.6 * .2, 0.))[0] < 0.
    cmd = {'kind': 'mecanum', 'forward': -.05, 'left': 0., 'turn': 0., 'duration_s': duration}
    assert ep.command_guard.check(0., [cmd]) == ([cmd] if clear else [{'kind': 'hold'}])
    assert ep.terminal != clear


def beam_pair(y=.35, sigma=.001, yaw=0.):
    host, exs = setup()
    assert start(host)['accepted']
    x = va.chassis_x_for_arm_radius(.155)
    grasp = va.solve_grip_ik(x, 0., .024, -90.)
    hover = {**va.solve_grip_ik(x, 0., .095, va.tool_pose(grasp).pitch_deg), 1: 1500}
    for rid, sign in (('r1', -1.), ('r2', 1.)):
        ep, own = active(host)[rid], exs[rid]
        ep.controller.state = 'carry'
        ep.controller.beam_grasp_confirmed = True  # explicit own-grip fixture; phase alone is insufficient
        own.servo = dict(hover)
        own.last_report = replace(own.last_report,
                                  x_m=2.2 + sign * .425 * math.cos(yaw),
                                  y_m=y + sign * .425 * math.sin(yaw),
                                  yaw_rad=yaw + (0. if rid == 'r1' else math.pi),
                                  std_xy_m=sigma, std_yaw_rad=.001)
    return active(host)


@pytest.mark.parametrize('rid', ['r1', 'r2'])
def test_p1_3_beam_middle_hits_door_post_while_both_carriers_are_clear(rid):
    eps = beam_pair()
    for ep in eps.values():
        own = ep.own
        pose = OwnPose.from_report(own.last_report)
        assert own.guard.chassis_clearance(pose)[0] > 0.
        assert own.guard.arm_clearance(own.servo, pose, loaded=True)[0] > 0.
    cmd = {'kind': 'mecanum', 'forward': .01, 'left': 0., 'turn': 0., 'duration_s': .15}
    assert eps[rid].command_guard.check(0., [cmd]) == [{'kind': 'hold'}]
    assert eps[rid].terminal


def test_p1_3_beam_sigma_margin_changes_near_post_decision():
    cmd = {'kind': 'mecanum', 'forward': .01, 'left': 0., 'turn': 0., 'duration_s': .15}
    low, high = beam_pair(y=.22), beam_pair(y=.22, sigma=.025)
    for rid in ('r1', 'r2'):
        assert low[rid].command_guard.check(0., [cmd]) == [cmd]
        assert high[rid].command_guard.check(0., [cmd]) == [{'kind': 'hold'}]


@pytest.mark.parametrize('duration,clear', [(.1, True), (.6, False)])
def test_p1_2_turn_checks_beam_through_command_expiry(duration, clear):
    ep = beam_pair(y=.19)['r1']
    cmd = {'kind': 'mecanum', 'forward': 0., 'left': 0., 'turn': .15, 'duration_s': duration}
    assert ep.command_guard.check(0., [cmd]) == ([cmd] if clear else [{'kind': 'hold'}])


def test_p1_3_loaded_arm_pan_sweeps_whole_beam_into_post():
    ep = beam_pair(y=.22)['r1']
    assert ep.command_guard.check(0., [{'kind': 'look', 'pan_pulse': 1600}]) == [{'kind': 'hold'}]
    assert ep.terminal


def test_p1_3_yaw_sigma_inflates_full_beam_lever():
    ep = beam_pair(y=.22)['r1']
    ep.own.last_report = replace(ep.own.last_report, std_yaw_rad=.04)
    cmd = {'kind': 'mecanum', 'forward': .01, 'left': 0., 'turn': 0., 'duration_s': .15}
    assert ep.command_guard.check(0., [cmd]) == [{'kind': 'hold'}]


@pytest.mark.parametrize('yaw', [0., .3, math.pi / 2])
def test_p1_3_each_own_role_reconstructs_both_ends_of_the_rotated_catalogue_bar(yaw):
    from harness.zone_pair_geometry import PairSweepGuard
    for ep in beam_pair(y=.35, yaw=yaw).values():
        own = ep.own
        geometry = ep.plan['beam_geometry']
        assert geometry['half_extents_m'] == [.3, .02, .016]
        guard = PairSweepGuard(own.guard, geometry, ep.arguments['role'])
        pose = OwnPose.from_report(own.last_report)
        spheres = guard.beam_spheres(own.servo)
        for sphere, sign in ((spheres[0], -1.), (spheres[-1], 1.)):
            bx, by, z, radius = sphere
            wx = pose.x + math.cos(pose.yaw) * bx - math.sin(pose.yaw) * by
            wy = pose.y + math.sin(pose.yaw) * bx + math.cos(pose.yaw) * by
            assert wx == pytest.approx(2.2 + sign * .3 * math.cos(yaw), abs=.0001)
            assert wy == pytest.approx(.35 + sign * .3 * math.sin(yaw), abs=.0001)
            assert z == pytest.approx(.095 + .016 - .024, abs=.0002)
            assert radius >= math.hypot(.02, .016)


@pytest.mark.parametrize('entry', ['before_control', 'check'])
def test_pair_direct_sigma_check_rejects_carry_while_shared_gate_is_still_ok(entry):
    ep = beam_pair(y=.05)['r1']
    ep.own.last_report = replace(ep.own.last_report, std_xy_m=.20, std_yaw_rad=.15)
    assert ep.own.gate.ok  # The shared dwell implementation is intentionally unchanged.
    if entry == 'before_control':
        assert not ep.command_guard.before_control(0.)
    else:
        cmd = {'kind': 'mecanum', 'forward': .01, 'left': 0., 'turn': 0., 'duration_s': .15}
        assert ep.command_guard.check(0., [cmd]) == [{'kind': 'hold'}]
    assert ep.terminal


@pytest.mark.parametrize('tag_seen', [False, True])
def test_p1_5_tagless_low_sigma_look_preserves_m2_failure_increment(tag_seen):
    host, _ = setup(factory=m2_controller)
    assert start(host)['accepted']
    drv = active(host)['r1'].controller.driver
    drv.loc.initialized = True
    drv.loc.px[:] = [0., 0., 0.]
    drv.loc.last_tag_t = 1. if tag_seen else None
    drv.look_t0 = 0.
    drv.state, drv.state_since = 'look_pan', 0.
    drv.arm_target, drv.look_queue = {}, []
    drv.looks_without_fix = 2
    drv.tick(2.)
    assert drv.looks_without_fix == (0 if tag_seen else 3)
    done = next(e for e in drv.log if e['event'] == 'look_done')
    assert done['fixed'] == tag_seen
    assert drv.last_look['fixed'] == tag_seen
    assert (drv.monitor.baseline is not None) == tag_seen
