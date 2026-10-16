"""Queue/issued-command ordering counterexamples without physics or rendering."""
from types import SimpleNamespace
import pytest

from harness.zone_s3_release_ack import attach, OPTION
from scripts.zone_teacher import ArmSequence


def endpoint(target='released'):
    queued, events = [], []
    own = SimpleNamespace(servo={1: 1600})
    port = SimpleNamespace(own=own, apply=lambda action, now: queued.append((now, action)))
    ctl = SimpleNamespace(state='wait_open', failure=None, port=port)
    ctl.arm = ArmSequence(port, {1: 1600})
    ctl._issued = lambda: dict(own.servo)
    def set_state(state, now, **detail):
        ctl.state = state
        events.append((state, now))
    def wait(now, idle):
        ctl.arm.queue({1: 2000}, now, duration=.4, settle=.5)
        ctl.set(target, now)
    ctl.set, ctl._wait_open = set_state, wait
    seen = []
    ctl.on_issued_command = seen.append
    return SimpleNamespace(controller=ctl), own, queued, events, seen


@pytest.mark.parametrize('target', ['released', 'cp_open'])
def test_queue_and_elapsed_time_cannot_release_without_current_host_ack(target):
    ep, own, queued, events, seen = endpoint(target)
    attach(ep, OPTION)
    ctl = ep.controller
    ctl.on_issued_command(dict(t=0., kind='arm', servo_id=1, pulse=2000))
    ctl._wait_open(1., True)
    assert ctl.arm.commanded[1] == 2000 and own.servo[1] == 1600
    assert ctl.state == 'wait_open' and not events
    pending_count = len(ctl.arm.events)
    ctl._wait_open(1.1, False)
    assert len(ctl.arm.events) == pending_count  # No duplicate GO/queue.
    ctl.arm.tick(1.5)  # Commands buffered but host hasn't consumed them.
    assert not ctl.arm.events and queued
    ctl._wait_open(2., True)
    assert ctl.state == 'wait_open'
    # Old receipt or other servo cannot confirm this release.
    for row in (dict(t=.9, kind='arm', servo_id=1, pulse=2000),
                dict(t=1.5, kind='arm', servo_id=3, pulse=2000)):
        ctl.on_issued_command(row)
    ctl._wait_open(2.1, True)
    assert ctl.state == 'wait_open'
    for t, action in queued:
        own.servo[action['servo_id']] = action['pulse']
        ctl.on_issued_command(dict(t=t, **action))
    ctl._wait_open(2.2, True)
    assert ctl.state == target and events == [(target, 2.2)]
    assert seen[-1]['pulse'] == 2000  # Original callback preserved.
    assert [r['event'] for r in ctl.s3_release_ack['audit']] == [
        'open_queued', 'open_host_issued', 'release_state_after_ack']


def test_off_is_identity_and_cancellation_cannot_be_revived():
    ep, own, *_ = endpoint()
    before = dict(vars(ep.controller))
    assert attach(ep) is ep and vars(ep.controller) == before
    ep.controller._wait_open(1., True)
    assert ep.controller.state == 'released' and own.servo[1] == 1600
    ep, own, *_ = endpoint()
    attach(ep, OPTION)
    ctl = ep.controller
    ctl._wait_open(1., True)
    ctl.failure = 'EXECUTION_ERROR'
    ctl.set('failed', 1.1)
    own.servo[1] = 2000
    ctl.on_issued_command(dict(t=1.2, kind='arm', servo_id=1, pulse=2000))
    assert ctl.state == 'failed'
    assert len(ctl.s3_release_ack['audit']) == 1
    with pytest.raises(ValueError):
        attach(ep, 'unknown')


def test_eight_pairs_change_only_explicit_release_control_option(monkeypatch):
    import json
    from scripts import run_s3_release_ack as runner
    from scripts.run_s3_release_ack_cohort import commands
    monkeypatch.setattr(runner, 'source_closure', lambda *args: ())
    monkeypatch.setattr(runner.base, 'source_closure', lambda *args: ())
    plan = json.loads((runner.ROOT/runner.PLAN).read_text())
    cases = commands(plan, 'a'*40)
    assert len(cases) == 8
    for distance in (.85, 1.5):
        for seed in (18601, 18602):
            off = runner.bundle('a'*40, distance, seed)
            on = runner.bundle('a'*40, distance, seed, OPTION)
            assert off.pop('release_ack')['option'] == 'off'
            assert on.pop('release_ack')['option'] == OPTION
            assert off == on
    with pytest.raises(ValueError):
        runner.bundle('a'*40, 4., 18601, OPTION)
