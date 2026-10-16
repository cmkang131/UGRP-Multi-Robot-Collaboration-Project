"""Door policy/protocol and real S3 composition; fake own estimates, no physics."""
import copy
from dataclasses import replace
import itertools
import math
from types import SimpleNamespace

import pytest

from harness import zone_s3_door_yield as door
from harness import zone_s3_contract as c
from harness import zone_s3_host as host
from tests.test_s3_host import FakePair, FakeSolo, frames, no_physics


def report(x=5., *, now=1., yaw=0., **kw):
    return SimpleNamespace(**dict(dict(initialized=True, x_m=x, y_m=0., yaw_rad=yaw,
        std_xy_m=.01, std_yaw_rad=.01, t_est=now, last_fix_t=now), **kw))


def clients():
    own = {r: {'done': False, 'report': report()} for r in host.ROBOTS}
    cs = {r: door.Client(r, own_report=lambda r=r: own[r]['report'],
                        own_done=lambda r=r: own[r]['done'], door_exit_x=2.225,
                        offset=(0., 0., 0.), envelope=(.8, .2)) for r in host.ROBOTS}
    return own, cs


def exchange(cs, now=1., order=host.ROBOTS):
    messages = [cs[r].offer(now) for r in order]
    for c in cs.values():
        c.receive(messages)
    return messages


@pytest.mark.parametrize('order', list(itertools.permutations(host.ROBOTS)))
def test_simultaneous_requests_pair_atomic_priority_and_end_barrier(order):
    own, cs = clients()
    exchange(cs, order=order)
    assert not any(c.permits() for c in cs.values())
    exchange(cs, order=order)
    assert [r for r, c in cs.items() if c.permits()] == ['r1', 'r2']
    # One member ending must not give the solo a lease.
    own['r1']['done'] = True
    exchange(cs)
    assert cs['r1'].state == 'CLEAR' and not cs['r3'].permits()
    own['r2']['done'] = True
    exchange(cs)
    exchange(cs)
    assert cs['r3'].permits() and not cs['r1'].permits() and not cs['r2'].permits()
    own['r3']['done'] = True
    exchange(cs)
    assert all(c.state == 'CLEAR' for c in cs.values())
    assert all(c.owner() is None for c in cs.values())


@pytest.mark.parametrize('changes', [
    {'x_m': 2.3}, {'std_xy_m': 2.}, {'std_yaw_rad': 2., 'x_m': 3.8}, {'t_est': -10.},
    {'t_est': 2.}, {'last_fix_t': None}, {'last_fix_t': 2.},
    {'initialized': False}, {'x_m': float('nan')}, {'std_xy_m': -.01},
])
def test_uncertain_stale_or_not_clear_estimate_never_releases(changes):
    own, cs = clients()
    exchange(cs); exchange(cs)
    own['r1'].update(done=True, report=report(**changes))
    own['r2']['done'] = True
    exchange(cs)
    assert cs['r1'].state == 'USING' and not cs['r3'].permits()
    exchange(cs, now=10000.)  # no expiry or elapsed-time handoff
    assert cs['r1'].state == 'USING' and not cs['r3'].permits()


def test_plan_completion_alone_or_pose_alone_never_releases():
    own, cs = clients()
    exchange(cs); exchange(cs)
    exchange(cs)
    assert cs['r1'].state == 'USING'
    own['r1'].update(done=True, report=None)
    exchange(cs)
    assert cs['r1'].state == 'USING'


@pytest.mark.parametrize('defect', ['missing', 'duplicate', 'stale', 'extra_field', 'foreign', 'nonowner', 'skip'])
def test_status_channel_rejects_missing_replay_foreign_fields_and_unowned_use(defect):
    _, cs = clients()
    exchange(cs)
    batch = [c.offer(1.) for c in cs.values()]
    if defect == 'missing': batch.pop()
    elif defect == 'duplicate': batch[-1] = batch[0]
    elif defect == 'stale': batch[-1] = replace(batch[-1], round=0)
    elif defect == 'extra_field': batch[-1] = {**vars(batch[-1]), 'peer_pose': [1., 2.]}
    elif defect == 'foreign': batch[-1] = replace(batch[-1], robot_id='r4')
    elif defect == 'nonowner': batch[-1] = replace(batch[-1], state='USING')
    elif defect == 'skip': batch[0] = replace(batch[0], state='CLEAR')
    with pytest.raises(ValueError, match='DOOR_STATUS'):
        cs['r1'].receive(batch)
    assert not cs['r1'].permits()


def test_relay_has_only_enum_transport_and_cannot_choose_owner():
    relay = door.Relay()
    batch = [door.Signal(r, 'door_1', 0, 'REQUEST') for r in host.ROBOTS]
    assert relay.broadcast(batch, 0.) == tuple(batch)
    assert set(vars(relay)) == {'round', 'events', 'previous'}
    assert set(relay.events[0]['signals'][0]) == {'robot_id', 'resource', 'round', 'state'}
    with pytest.raises(ValueError, match='INVALID'):
        relay.broadcast(batch, 1.)


def runtime(condition='rule'):
    scenario, mb, sheet = c.inputs()
    rt = door.Runtime(c.hp.resolve(c.solo.MAP_ID)[0], sheet['orders'], None, None,
                      seed=601, pair_factory=FakePair, solo_factory=FakeSolo, condition=condition)
    rt.trial = host.IntegratedTrial(scenario, seed=601, links=rt.links, map_bundle=mb,
        horizon_s=1800., code_sha='a'*40, pair_records=rt.pair.team.records)
    rt.initial_commands(0., {r: {'owner': r} for r in host.ROBOTS})
    rt.trial.begin(0.)
    return rt


def finish_pair(rt, now):
    for r, actor in rt.pair.actors.items():
        actor.jobs_done.append({'kind': 'pair_carry', 'confirmation': 'unconfirmed'})
        # Both imply the public carried-envelope centre x=4.6, with own yaw.
        dx, dy, heading = rt.clients[r].offset
        actor.last_report = report(4.6+dx, now=now, yaw=heading)


@pytest.mark.parametrize('condition', door.CONDITIONS)
def test_actual_host_waits_before_solo_producer_and_keeps_self_observation(condition):
    rt = runtime(condition)
    calls = []
    original = rt.solo.producer.step
    rt.solo.producer.step = lambda now: (calls.append(now) or original(now))
    try:
        rt.on_frames(0., frames(0.))
        rows = rt.step(0.)
        assert [cmd for r, cmd in rows if r == 'r3'] == [{'kind': 'hold'}]
        assert not calls and len(rt.solo.observations) == 1
        assert len(rt.pair.submissions) == 2
        for r, cmd in rows:
            rt.on_command(r, 0., cmd)
        assert rt.solo.commands == [('r3', 0., {'kind': 'hold'})]
        finish_pair(rt, 1.)
        assert [a for r, a in rt.step(1.) if r == 'r3'] == [{'kind': 'hold'}]
        assert not calls
        assert ('r3', {'kind': 'arm', 'servo_id': 1, 'pulse': 1500}) in rt.step(1.05)
        assert calls == [1.05]
        record = rt.record()['door_yield']
        assert record['wait_robot_s']['r3'] == pytest.approx(1.05)
        assert record['wait_robot_s']['r1'] == 0.
        assert not rt.trial.requests and not rt.trial.scheduler.calls
    finally:
        rt.close()


def test_condition_labels_cannot_change_protocol_or_commands():
    traces = []
    for condition in door.CONDITIONS:
        rt = runtime(condition)
        try:
            rows = rt.step(0.)
            finish_pair(rt, .1)
            rows += rt.step(.1)+rt.step(.15)
            traces.append((rows, rt.record()['door_yield']))
        finally:
            rt.close()
    assert traces[0] == traces[1] == traces[2]


def test_pair_failure_and_same_tick_failure_hold_everyone_without_release():
    rt = runtime()
    try:
        def fail(now):
            rt.pair.actors['r2'].jobs_done.append({'kind': 'pair_carry', 'confirmation': 'failed', 'outcome': 'TEST'})
            return [('r2', {'kind': 'arm', 'servo_id': 1, 'pulse': 2000})]
        rt.pair.producer.arm_step = fail
        assert rt.step(0.) == [(r, {'kind': 'hold'}) for r in host.ROBOTS]
        assert rt.terminal and rt.clients['r2'].state == 'USING'
        assert not rt.clients['r3'].permits()
    finally:
        rt.close()


def test_corrupt_status_fails_closed_and_records_reason():
    rt = runtime()
    try:
        rt.relay.broadcast = lambda batch, now: batch[:-1]
        assert rt.step(0.) == [(r, {'kind': 'hold'}) for r in host.ROBOTS]
        assert rt.failures['door_1'] == 'DOOR_STATUS_MISSING'
        assert not rt.pair.submissions
    finally:
        rt.close()
