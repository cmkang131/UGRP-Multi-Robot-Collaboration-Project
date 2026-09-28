"""PR #235 review 6: stop before reobserving, no physics or model calls."""
import hashlib
import types
from pathlib import Path

import pytest

from tests.test_zone_own_executor_guards import ScriptedLoc
from tests.test_zone_pair_executor import active, ends, m2_controller, setup, start
from tests.test_zone_pair_review5 import fresh


@pytest.fixture(scope='module')
def baseline_guard():
    # Exact historical module, so A/B also runs in clones without Git history.
    path = Path(__file__).parent / 'fixtures/zone_pair_review6/zone_pair_guards_1628a03f.py'
    source = path.read_bytes()
    assert hashlib.sha256(source).hexdigest() == 'fcd2aef1b7e40b591f02814d340de910bc50eed46cc3f60ff780c1b9b88292cf'
    module = types.ModuleType('pair_guards_1628a03f')
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module.PairCommandGuard


def drive_then_hold(guard_cls=None):
    host, exs = setup(factory=m2_controller)
    assert start(host)['accepted']
    eps = active(host)
    if guard_cls is not None:
        for ep in eps.values():
            ep.command_guard = guard_cls(ep)
    ep, own = eps['r1'], exs['r1']
    driver = ep.controller.driver
    driver.loc = ScriptedLoc(lambda t: (0., 0., 0., .01 if t < .1 else .055, .01, 0.))
    driver.state, driver.state_since = 'drive', 0.
    host._decide('r1', 0.)
    commands = host.robots['r1'].commands
    assert commands[-1]['kind'] == 'mecanum'
    assert commands[-1]['t'] == 0. and commands[-1]['duration_s'] == .15
    assert ep.command_guard.motion_until == .15
    assert not any(p.terminal for p in eps.values())

    fresh(own, .1, .055)  # above M2's look threshold, below the HIGH abort threshold
    host._decide('r1', .1)
    assert driver.state == 'look_arm'
    return host, exs, eps


def test_p1_drive_to_reobserve_hold_preempts_unexpired_motion_without_abort():
    host, exs, eps = drive_then_hold()
    ep = eps['r1']
    assert not any(p.terminal for p in eps.values())
    assert all(not ends(exs[rid]) for rid in eps)
    assert host.robots['r1'].commands[-1] == {'t': .1, 'kind': 'hold'}
    assert ep.command_guard.motion_until == .1
    assert ep.command_guard.recheck.waited_s == 0.

    # After the host records the stop, normal arm reobservation can continue.
    for now in (.15, .2):
        fresh(exs['r1'], now, .055)
        eps['r2'].status.tick('aligning', now)
        host._decide('r1', now)
    assert not any(p.terminal for p in eps.values())
    after_hold = [c for c in host.robots['r1'].commands if c['t'] > .1]
    assert any(c['kind'] in ('arm', 'look') for c in after_hold)
    assert all(c['kind'] in ('hold', 'arm', 'look') for c in after_hold)


def test_p1_drive_to_hold_matches_1628a03f_guard_ab(baseline_guard):
    def snapshot(guard_cls):
        host, exs, eps = drive_then_hold(guard_cls)
        return {
            'commands': {rid: host.robots[rid].commands for rid in eps},
            'terminal': {rid: ep.terminal for rid, ep in eps.items()},
            'failures': {rid: [e['detail']['reason'] for e in ends(exs[rid])] for rid in eps},
            'driver_state': eps['r1'].controller.driver.state,
            'motion_until': eps['r1'].command_guard.motion_until,
        }

    baseline = snapshot(baseline_guard)
    assert baseline['terminal'] == {'r1': False, 'r2': False}
    assert baseline['failures'] == {'r1': [], 'r2': []}
    assert baseline['motion_until'] == .1
    assert snapshot(None) == baseline


@pytest.mark.parametrize('fault', ['moving', 'missing_pose', 'expired_budget'])
def test_p1_hold_alone_is_allowed_before_reobserve_checks(fault):
    host, exs = setup(factory=m2_controller)
    assert start(host)['accepted']
    ep, own = active(host)['r1'], exs['r1']
    ep.controller.driver.state = 'look_arm'
    now = .1
    if fault == 'moving':
        own.on_command({'t': 0., 'kind': 'mecanum', 'forward': .1, 'left': 0., 'turn': 0., 'duration_s': .15})
    elif fault == 'missing_pose':
        own.last_report = None
    else:
        now = 10.
        fresh(own, now, .081)
        ep.command_guard.recheck.check_gate(0., ready=False)
    assert ep.command_guard.check(now, [{'kind': 'hold'}]) == [{'kind': 'hold'}]
    assert not ep.terminal and not ends(own)
    if fault == 'expired_budget':
        assert ep.command_guard.recheck.waited_s == 10.
        assert not ep.command_guard.before_control(now)
        assert ends(own)[0]['detail']['reason'] == 'PAIR_REOBSERVE_TIMEOUT'


@pytest.mark.parametrize('kind', ['arm', 'look', 'drive', 'mecanum'])
@pytest.mark.parametrize('with_hold', [False, True])
def test_p1_unapplied_hold_cannot_authorize_arm_or_motion_during_reobserve(kind, with_hold):
    host, exs = setup(factory=m2_controller)
    assert start(host)['accepted']
    ep, own = active(host)['r1'], exs['r1']
    own.on_command({'t': 0., 'kind': 'mecanum', 'forward': .1, 'left': 0., 'turn': 0., 'duration_s': .15})
    ep.controller.driver.state = 'look_arm'
    fresh(own, .1, .055)
    cmd = ({'kind': 'arm', 'servo_id': 6, 'pulse': 1520} if kind == 'arm' else
           {'kind': 'look', 'pan_pulse': 1520} if kind == 'look' else
           {'kind': kind, 'forward': .01, 'left': 0., 'turn': 0., 'duration_s': .1})
    commands = ([{'kind': 'hold'}] if with_hold else []) + [cmd]
    assert ep.command_guard.check(.1, commands) == [{'kind': 'hold'}]
    host._pair_safety(.1)
    assert ends(own)[0]['detail']['reason'] == 'POSE_UNCERTAIN'
    assert ends(exs['r2'])[0]['detail']['reason'] == 'PARTNER_ABORT'
