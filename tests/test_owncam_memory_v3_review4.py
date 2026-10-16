"""Review 4: current pose uncertainty and rejected gate sweeps, without physics."""
import math
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pytest

from harness.owncam_drive import CARRY_POSTURE
from tests.test_owncam_memory_v3 import controller, fix, report
from tests.test_owncam_memory_v3_review import leg_fixture
from tests.test_owncam_memory_v3_review3 import door_map


def ready_leg(*, loaded=True, sigma_xy=.02, sigma_yaw=.005, travel=0., arrived=False):
    leg, loc, est = leg_fixture(loaded, yaw=.005)
    fix(leg.memory, 1.8, (est['x'] - travel, est['y']))
    leg.last_look_xy = tuple(leg.memory.last_look_fix['xy'])
    leg.state, leg.state_since = 'drive', 1.8
    leg.servo = dict(CARRY_POSTURE)
    if arrived:
        leg.goal = [est['x'], est['y']]
        leg.arrival_checked, leg.verification_since = True, 1.5
    est.update(std_xy_m=sigma_xy, std_yaw_rad=sigma_yaw,
               cov=np.diag([sigma_xy**2/2]*2 + [sigma_yaw**2]))
    assert leg.memory.guard.consistent(2.)
    assert leg.memory.look_fix_fresh(2., (est['x'], est['y']))
    return leg, loc, est


@pytest.mark.parametrize('travel', [0., .099])
@pytest.mark.parametrize('sigma_xy,sigma_yaw', [(.20, .15), (.20, .005), (.02, .15)])
def test_p1_current_uncertainty_blocks_loaded_movement_after_recent_fix(travel, sigma_xy, sigma_yaw):
    leg, _, est = ready_leg(sigma_xy=sigma_xy, sigma_yaw=sigma_yaw, travel=travel)
    # The inherited efficiency rule still suppresses a repeated look here.
    assert not leg._uncertain(est)
    commands = leg.tick(2.)
    assert commands == [{'kind': 'hold'}]
    assert leg.outcome != 'arrived'
    assert leg.state == 'look_arm' or leg.outcome == 'look_collision_unverified'


@pytest.mark.parametrize('entry', ['tick', 'arrive'])
@pytest.mark.parametrize('sigma_xy,sigma_yaw', [(.20, .15), (.20, .005), (.02, .15)])
def test_p1_current_uncertainty_blocks_already_verified_arrival(entry, sigma_xy, sigma_yaw):
    leg, _, _ = ready_leg(sigma_xy=sigma_xy, sigma_yaw=sigma_yaw, arrived=True)
    assert leg.memory.look_fix_since(leg.verification_since)
    commands = leg.tick(2.) if entry == 'tick' else leg._arrive(2.)
    assert commands == [{'kind': 'hold'}]
    assert leg.outcome != 'arrived'
    assert not any(row['event'] == 'arrived' for row in leg.log)


def gate_controller(x, y):
    ctl = controller()
    ctl.map, ctl.servo = door_map(), dict(CARRY_POSTURE)
    ctl.pose.report = lambda t: report(t, x=x, y=y, sigma=.001)
    ctl.skill = SimpleNamespace(box=SimpleNamespace(held=True))
    obs = {'actuator_state': {'servo_pulses': {str(k): v for k, v in ctl.servo.items()}}}
    return ctl, obs


@pytest.mark.parametrize('reason', ['post_manipulation', 'gate:nav_loaded:std_xy'])
def test_p2_rejected_gate_sweep_finishes_without_exception_or_motion(reason):
    ctl, obs = gate_controller(2., -.5)
    # Real authored 0.40 m wall and real transition checker, not a mocked rejection.
    with mock.patch.object(ctl.memory, 'reset_view_checks') as reset, \
         mock.patch.object(ctl, '_arm_steps') as arm:
        result = ctl._gate_look(2., reason, obs, loaded=True)
        assert result == {'mode': 'done', 'outcome': 'LOOK_COLLISION_UNVERIFIED'}
        assert ctl.decide(2.1) == result
        reset.assert_not_called()
        arm.assert_not_called()
    assert ctl.sweep is None
    assert not ctl.reanchor_needed
    assert any(row['event'] == 'look_collision_unverified' for row in ctl.events)


@pytest.mark.parametrize('loaded,xy_limit', [(False, .05), (True, .07)])
@pytest.mark.parametrize('field', ['std_xy_m', 'std_yaw_rad'])
def test_drive_uncertainty_limit_is_inclusive_and_independent_of_travel(loaded, xy_limit, field):
    limits = {'std_xy_m': xy_limit, 'std_yaw_rad': math.radians(3.)}
    for offset, blocked in [(0., False), (1e-6, True)]:
        values = dict(limits)
        values[field] += offset
        leg, _, _ = ready_leg(loaded=loaded, sigma_xy=values['std_xy_m'], sigma_yaw=values['std_yaw_rad'])
        commands = leg.tick(2.)
        assert any(c['kind'] == 'mecanum' for c in commands) is not blocked


@pytest.mark.parametrize('loaded,xy_limit', [(False, .05), (True, .06)])
@pytest.mark.parametrize('field', ['std_xy_m', 'std_yaw_rad'])
def test_arrival_uses_fix_limits_even_inside_drive_limits(loaded, xy_limit, field):
    limits = {'std_xy_m': xy_limit, 'std_yaw_rad': math.radians(2.)}
    for offset, allowed in [(0., True), (1e-6, False)]:
        values = dict(limits)
        values[field] += offset
        leg, _, _ = ready_leg(loaded=loaded, sigma_xy=values['std_xy_m'], sigma_yaw=values['std_yaw_rad'], arrived=True)
        assert leg._arrive(2.) == [{'kind': 'hold'}]
        assert (leg.outcome == 'arrived') is allowed


@pytest.mark.parametrize('entry', ['tick', 'arrive'])
@pytest.mark.parametrize('field', ['std_xy_m', 'std_yaw_rad'])
@pytest.mark.parametrize('bad', [float('nan'), float('inf')])
def test_nonfinite_current_uncertainty_never_authorizes_motion_or_arrival(entry, field, bad):
    leg, _, est = ready_leg(arrived=entry == 'arrive')
    est[field] = bad
    commands = leg.tick(2.) if entry == 'tick' else leg._arrive(2.)
    assert commands == [{'kind': 'hold'}]
    assert leg.outcome != 'arrived'


@pytest.mark.parametrize('reason,mode', [('post_manipulation', 'full'),
                                       ('gate:nav_loaded:std_xy', 'short'),
                                       ('preplace', 'full'), ('verify_grasp_v3', 'full'),
                                       ('verify_place_v3', 'full')])
def test_safe_gate_sweep_preserves_full_and_memory_short_policies(reason, mode):
    ctl, obs = gate_controller(0., 0.)
    with mock.patch.object(ctl.memory, 'plan_look', return_value={'pans': [1500]}) as plan:
        result = ctl._gate_look(2., reason, obs, loaded=True)
    assert result == ctl._hold()
    assert ctl.outcome is None and ctl.sweep is not None
    assert ctl.gate_modes[-1]['mode'] == mode
    assert ctl.reanchor_needed
    assert plan.call_count == (1 if mode == 'short' else 0)
    if mode == 'short':
        assert ctl.sweep['mode'] == 'short' and ctl.sweep['short_target']
        assert ctl.sweep['queue'] == [1500]


def test_review4_regressions_are_in_ci():
    from scripts.run_ci_tests import TEST_PATTERNS
    assert 'tests/test_owncam_memory_v3_review4.py' in TEST_PATTERNS
