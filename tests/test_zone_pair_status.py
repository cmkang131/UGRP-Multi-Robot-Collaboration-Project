"""Wire-only rendezvous; no MuJoCo, controller/peer objects or task content."""
import pytest

from harness.zone_pair_status import PairStatusChannel, PairStatusEndpoint, STATES
from harness.zone_pair_status import FIELDS


def endpoints():
    bus = PairStatusChannel('pair-000001')
    return bus, {r: PairStatusEndpoint(bus, r) for r in ('r1', 'r2')}


def ready(ep, key, now, yes=True):
    return ep.sync_for(key).report(ep.robot_id, ready=yes, observed_at_s=now, received_at_s=now,
                                   frame_id=f"{ep.robot_id}-{round(now * 1000)}-0123456789ab", reason='비공개 영상 판단')


@pytest.mark.parametrize('phase', ['lift', 'close'])
def test_joint_go_requires_both_status_readiness_and_survives_first_consumer(phase):
    bus, e = endpoints()
    for ep in e.values():
        ep.tick('aligning', 0.)
    key = phase + '@0'
    a, b = (ep.sync_for(key) for ep in e.values())
    ready(e['r1'], key, 0.)
    assert a.authorize(0.)['phase'] == 'WAIT'
    # Coarse legacy publication must not erase latched readiness.
    e['r1'].tick('ready', .4)
    ready(e['r1'], key, .4)
    ready(e['r2'], key, .4)
    for ep in e.values():
        ep.tick('ready', .5)
    assert a.authorize(.5)['phase'] == 'WAIT'
    assert a.authorize(.6)['phase'] == 'GO'
    e['r1'].tick('lift', .6)
    assert b.authorize(.6)['phase'] == a.authorize(.6)['phase'] == 'GO'
    assert all(set(m) == FIELDS and m['state'] in STATES for m in bus.log)
    assert 'LOCAL_ONLY' not in str(bus.log) and '비공개' not in str(bus.log)


def test_barrier_generation_and_task_scope_prevent_stale_go():
    bus, e = endpoints()
    for ep in e.values():
        ready(ep, 'lift@0', 0.)
    assert e['r1'].sync_for('lift@1').authorize(.3)['phase'] == 'WAIT'
    assert e['r1'].sync_for('lift@0').authorize(3.)['phase'] == 'WAIT'
    newer, _ = endpoints()
    newer.task_id = 'pair-000002'
    assert not newer.publish(bus.log[0], 0.)


def test_readiness_withdrawal_before_go_revokes_rendezvous():
    _, e = endpoints()
    for ep in e.values():
        ready(ep, 'open@0', 0.)
    a = e['r1'].sync_for('open@0')
    assert a.authorize(.1)['phase'] == 'WAIT'
    ready(e['r2'], 'open@0', .1, False)
    assert a.authorize(.2)['phase'] == 'WAIT'


@pytest.mark.parametrize('change', [
    {'pose': [1, 2]}, {'reason': 'carry X to B'}, {'state': 'arbitrary task'}, {'state': []},
    {'seq': True}, {'seq': 0}, {'sent_at_s': float('nan')}, {'sent_at_s': 1.},
    {'robot_id': []}, {'robot_id': 'r3'}, {'task_id': 'different'},
])
def test_invalid_wire_is_refused_without_raising(change):
    bus, _ = endpoints()
    raw = dict(robot_id='r1', task_id=bus.task_id, seq=1, state='aligning', sent_at_s=0., observed_at_s=None, frame_id=None, ready_until_s=None)
    assert not bus.publish({**raw, **change}, 0.)
    assert not bus.log


def test_replay_abort_and_monotonic_timestamps():
    bus, e = endpoints()
    e['r1'].tick('aligning', 1.)
    assert not bus.publish(bus.log[0], 1.)
    assert not bus.publish({**bus.log[0], 'seq': 2, 'sent_at_s': .5}, 1.)
    e['r1'].tick('abort', 1.1)
    assert not bus.publish({**bus.log[-1], 'seq': 3, 'state': 'ready'}, 1.1)
