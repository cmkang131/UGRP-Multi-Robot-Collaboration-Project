"""Can arm command/guard boundary regressions; analytic inputs, no physics."""
import copy

import pytest

from harness.zone_own_guards import OwnPose
from tests.test_zone_own_executor_can import MAP, FakeOwnPose, make
from harness.zone_can_skill import CanSkill, VIEWS


@pytest.mark.parametrize('loaded', [False, True])
@pytest.mark.parametrize('delta', [
    {1: -500, 3: -101, 4: -21, 5: -40, 6: 97},
    {1: 500, 3: 21, 4: 101, 5: 40, 6: -97},
    {1: 0, 3: 1, 4: -1, 5: 0, 6: 0},
])
def test_every_emitted_increment_is_the_checked_target(monkeypatch, loaded, delta):
    skill = make()
    initial = {1: 1500, 3: 1200, 4: 1800, 5: 1800, 6: 1500}
    skill.on_command(dict(robot_id='r1', t=0., kind='initial_servo_command', pulses=initial))
    target = {k: initial[k] + v for k, v in delta.items()}
    own = OwnPose(0., 0., 0., .002, .002)
    checks = []

    def record_check(current, next_target, pose, *, loaded):
        checks.append((dict(current), dict(next_target), pose, loaded))
        return True

    monkeypatch.setattr(skill.guard, 'transition_clear', record_check)
    # Feed only emitted commands back, until the requested target settles.
    for tick in range(1, 30):
        out = skill._arm_to(target, own, float(tick), loaded=loaded)
        current, checked, checked_pose, checked_load = checks[-1]
        issued = dict(current)
        for command in out['commands'] if out else []:
            if command['kind'] == 'arm':
                issued[command['servo_id']] = command['pulse']
                assert command['duration_ms'] == 100
            skill.on_command(dict(robot_id='r1', t=float(tick), **command))
        assert issued == checked
        assert checked_pose is own and checked_load is loaded
        assert all(abs(issued[k]-current[k]) <= 40 for k in current)
        if out is None:
            break
    assert out is None and skill.servo == target


@pytest.mark.parametrize('loaded', [False, True])
def test_clear_endpoints_do_not_bypass_blocked_interior(monkeypatch, loaded):
    skill = make()
    skill.on_command(dict(robot_id='r1', t=0., kind='initial_servo_command', pulses=dict(VIEWS[0])))
    # Endpoint-only checking would allow this step. Exercise the real sampler
    # through a synthetic arm-clearance boundary strictly inside the increment.
    def clearance(servo, pose, *, loaded):
        return (-.01 if 773 <= servo[3] <= 787 else .1), 'synthetic_intermediate'

    monkeypatch.setattr(skill.guard, 'arm_clearance', clearance)
    out = skill._arm_to({3: 760}, OwnPose(0., 0., 0., .002, .002), 1., loaded=loaded)
    assert out['phase'] == 'failed' and out['reason'] == 'static_arm_sweep_blocked'
    assert out['commands'] == [{'kind': 'hold'}]


def test_real_guard_permits_the_review_increment_when_static_post_is_absent():
    skill = CanSkill('r1', copy.deepcopy(MAP), destination_zone='C', pose_source=FakeOwnPose())
    initial = {1: 2000, 3: 1164, 4: 2321, 5: 2080, 6: 1174}
    skill.on_command(dict(robot_id='r1', t=0., kind='initial_servo_command', pulses=initial))
    out = skill._arm_to(VIEWS[0], OwnPose(0., 0., 0., .002, .002), 1.)
    assert out['phase'] == 'approach'
    assert {c['servo_id']: c['pulse'] for c in out['commands'] if c['kind'] == 'arm'} == {
        3: 1124, 4: 2300, 5: 2040, 6: 1214,
    }


def test_ci_collects_promoted_review_and_sweep_regressions():
    import fnmatch
    from scripts.run_ci_tests import TEST_PATTERNS
    for name in ('tests/test_review_e2e_batch_i.py', 'tests/test_zone_own_executor_can_sweep.py'):
        assert any(fnmatch.fnmatch(name, pattern) for pattern in TEST_PATTERNS)
