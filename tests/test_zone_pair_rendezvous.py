"""T12 own-request recovery on enum wires and the real host with fake ports.

The r3 tests exercise the proposed role-aware port, NOT T07's motion routing.
No physics, renderer, provider/model calls or hidden-event input to recovery.
"""
from dataclasses import asdict, replace
import copy
import socket
import sys

import pytest

from harness.zone_pair_rendezvous import LegacyOwnPairPort, OwnPairRecovery, PairRequest, RoleAwareOwnPairPort
from harness.zone_pair_status import EPS, FIELDS, STATES, PairStatusChannel, PairStatusEndpoint
from harness import zone_study_protocol as protocol

CONDITIONS = ('no_comm', 'peer_ko', 'leader_ko', 'structured')


@pytest.fixture(autouse=True)
def no_physics_or_models(monkeypatch):
    for name in ('mujoco', 'torch', 'google.genai', 'openai'):
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    monkeypatch.setattr(socket.socket, 'connect_ex', lambda *a: pytest.fail('network forbidden'))


class FakeOwnPort:
    """Only the own job; partner communication is a production enum channel."""
    def __init__(self, actor):
        self.actor, self.now, self.generation = actor, 0., 0
        self.job = self.ep = None
        self.commands, self.arm_events, self.host_queue, self.calls = [], [], [], []
        self.available, self.cancel_ok = True, True

    def status(self):
        return {'job': copy.deepcopy(self.job)}

    def endpoint(self):
        return self.ep

    def submit(self, request):
        self.calls.append(('submit', asdict(request)))
        if not self.available:
            return {'accepted': False, 'rejected_reason': 'SELF_UNCERTAIN'}
        assert self.job is None
        self.generation += 1
        jid = f'{self.actor}-job-{self.generation}'
        self.job = {'job_id': jid, 'kind': 'pair_carry', 'phase': 'waiting_partner'}
        wire = PairStatusChannel(f'{self.actor}-task-{self.generation}', (self.actor, request.partner_id))
        self.ep = PairStatusEndpoint(wire, self.actor)
        self.ep.tick('start_ready', self.now)
        self.arm_events = [(100., {'kind': 'arm', 'job_id': jid})]
        self.host_queue = [(100., {'kind': 'mecanum', 'job_id': jid})]
        return {'accepted': True, 'robot_id': self.actor, 'api': 'pair_carry', 'job_id': jid,
                'arguments': {'order_id': request.order_id, 'target_ref': request.destination_zone,
                              'role': request.role}}

    def abort(self):
        self.calls.append(('abort', self.job['job_id']))
        if not self.cancel_ok:
            return {'accepted': False}
        self.ep.tick('abort', self.now)
        self.arm_events.clear()
        self.host_queue.clear()
        self.commands.clear()
        self.job = None
        return {'accepted': True}


def fake(actor='r3', partner='r1', role='end_pos', now=0.):
    port = FakeOwnPort(actor)
    port.now = now
    ctl = OwnPairRecovery(actor, port)
    request = PairRequest('beam-order', 'B', partner, role)
    result = ctl.submit(request, now=now)
    assert result.state == 'waiting'
    peer = PairStatusEndpoint(port.ep.channel, partner)
    return ctl, port, request, result.job_id, peer


def poll(ctl, port, now):
    port.now = now
    return ctl.poll(now=now)


@pytest.mark.parametrize('condition', CONDITIONS)
@pytest.mark.parametrize('seed', [0, 1, 2])
@pytest.mark.parametrize('role', ['end_neg', 'end_pos'])
@pytest.mark.parametrize('partner', ['r1', 'r2'])
def test_r3_each_end_and_leader_axis_use_identical_wire(condition, seed, role, partner):
    transport = protocol.Transport(condition, seed=seed, order_ids=['beam-order'], roles=['end_neg', 'end_pos'])
    ctl, port, request, jid, peer = fake(partner=partner, role=role)
    assert protocol.leader_for_seed(seed) == ('r1', 'r2', 'r3')[seed]
    assert ctl.record()['assignment'] == request.assignment_record('r3')
    peer.tick('start_ready', .1)
    assert poll(ctl, port, .1).state == 'active'
    assert transport.sent_count() == 0  # enum channel is common, not a language message
    assert all(set(row) == FIELDS and row['state'] in STATES for row in port.ep.channel.log)
    assert not any('beam-order' in str(row) for row in port.ep.channel.log)
    # Physical readiness is still governed by the SAME evidence/GO protocol.
    a, b = port.ep.sync_for('approach@0'), peer.sync_for('approach@0')
    for ep, barrier in ((port.ep, a), (peer, b)):
        assert barrier.report(ep.robot_id, ready=True, observed_at_s=.1, received_at_s=.1,
                              frame_id=f'{ep.robot_id}-1-0123456789ab')
    assert a.authorize(.2)['phase'] == b.authorize(.2)['phase'] == 'WAIT'
    for ep in (port.ep, peer):
        ep.tick(ep.state, .25)
    assert a.authorize(.3)['phase'] == b.authorize(.3)['phase'] == 'GO'
    assert poll(ctl, port, .3).job_id == jid


@pytest.mark.parametrize('condition', CONDITIONS)
@pytest.mark.parametrize('role', ['end_neg', 'end_pos'])
@pytest.mark.parametrize('joined_at,expected', [
    (4., 'active'), (5. - 2 * EPS, 'active'), (5. - EPS, 'cancelled'),
    (5., 'cancelled'), (5. + EPS, 'cancelled'), (5.01, 'cancelled'),
])
def test_before_just_before_at_and_after_deadline(condition, role, joined_at, expected):
    protocol.Transport(condition, seed=2, order_ids=['beam-order'], roles=['end_neg', 'end_pos'])
    ctl, port, _, _, peer = fake(role=role)
    peer.tick('start_ready', joined_at)
    result = poll(ctl, port, joined_at)
    assert result.state == expected
    if expected == 'cancelled':
        assert result.reason == 'PAIR_RENDEZVOUS_TIMEOUT'
        assert not port.host_queue and not port.arm_events
        assert port.ep.state == 'abort'


@pytest.mark.parametrize('condition', CONDITIONS)
@pytest.mark.parametrize('role', ['end_neg', 'end_pos'])
def test_private_40_second_command_noncompliance_does_not_inform_recovery(condition, role):
    # Private plant truth lives here only. Recovery never receives it.
    results = []
    for private in ({'hold': None, 'wheel_motion': True},
                    {'hold': [12., 52.], 'wheel_motion': False, 'pose': [999, -999], 'success': True}):
        transport = protocol.Transport(condition, seed=2, order_ids=['beam-order'], roles=['end_neg', 'end_pos'])
        ctl, port, request, jid, peer = fake(role=role, now=12.)
        trace = [asdict(poll(ctl, port, 16.9)), asdict(poll(ctl, port, 17.))]
        assert trace[-1]['reason'] == 'PAIR_RENDEZVOUS_TIMEOUT'
        old_wire = peer.channel
        # All 40 seconds of ignored motor commands belong to the fake plant.
        plant_attempts = [{'t': t, 'issued': True, 'moved': private['wheel_motion']}
                          for t in range(12, 52)]
        assert len(plant_attempts) == 40
        assert poll(ctl, port, 52.).state == 'idle'  # no auto-resurrection at event end
        peer.tick('start_ready', 52.)
        assert poll(ctl, port, 52.).state == 'idle'
        port.available = False  # own stale/uncertain image, regardless of private event end
        assert ctl.submit(request, now=52.).reason == 'SELF_UNCERTAIN'
        port.now = 52.1
        port.available = True  # new own-input admission fixture, not a truth callback
        resumed = ctl.submit(request, now=52.1)
        assert resumed.job_id != jid and port.ep.channel is not old_wire
        assert poll(ctl, port, 52.1).state == 'waiting'
        fresh_peer = PairStatusEndpoint(port.ep.channel, request.partner_id)
        fresh_peer.tick('start_ready', 52.2)
        trace.append(asdict(poll(ctl, port, 52.2)))
        assert trace[-1]['state'] == 'active'
        assert transport.sent_count() == 0
        results.append((trace, ctl.events, port.calls, port.ep.channel.log))
    assert results[0] == results[1]


@pytest.mark.parametrize('condition', CONDITIONS)
def test_joined_pair_does_not_infer_a_physical_hold_from_command_acceptance(condition):
    protocol.Transport(condition, seed=2, order_ids=['beam-order'], roles=['end_neg', 'end_pos'])
    ctl, port, _, jid, peer = fake(now=11.)
    peer.tick('start_ready', 11.)
    assert poll(ctl, port, 11.).state == 'active'
    own_barrier = port.ep.sync_for('approach@0')
    peer_barrier = peer.sync_for('approach@0')
    for now in range(12, 53):
        assert own_barrier.report('r3', ready=True, observed_at_s=now, received_at_s=now,
                                  frame_id=f'r3-{now}-0123456789ab')
        peer.tick('aligning', now)
        assert poll(ctl, port, now).state == 'active'
        assert own_barrier.authorize(now)['phase'] == 'WAIT'
    # No GO at private event end: the partner must independently publish
    # fresh own-camera readiness, then BOTH consume the common-grid grant.
    assert peer_barrier.report('r1', ready=True, observed_at_s=52., received_at_s=52.,
                               frame_id='r1-52-0123456789ab')
    for ep in (port.ep, peer):
        ep.tick(ep.state, 52.1)
    assert own_barrier.authorize(52.2)['phase'] == peer_barrier.authorize(52.2)['phase'] == 'GO'
    assert poll(ctl, port, 52.2).state == 'active'
    port.now = 52.2
    assert ctl.cancel(jid, now=52.2).state == 'cancelled'


@pytest.mark.parametrize('role', ['end_neg', 'end_pos'])
def test_explicit_reassignment_cancels_only_old_job_and_fences_stale_cancel(role):
    ctl, port, request, jid, _ = fake(role=role)
    old_ep = port.ep
    old_arm, old_queue = port.arm_events, port.host_queue
    port.commands.append({'job_id': jid, 'kind': 'mecanum'})
    port.now = 1.
    result = ctl.replace(jid, replace(request, partner_id='r2'), now=1.)
    assert result.state == 'waiting' and result.job_id != jid
    assert not old_arm and not old_queue and not port.commands
    assert old_ep.state == 'abort' and port.ep.channel is not old_ep.channel
    calls, queues = copy.deepcopy((port.calls, (port.host_queue, port.arm_events)))
    assert ctl.cancel(jid, now=1.).reason == 'STALE_JOB'
    assert port.calls == calls and (port.host_queue, port.arm_events) == queues
    assert ctl.request.partner_id == 'r2'


def test_cancel_refusal_does_not_submit_a_replacement():
    ctl, port, request, jid, _ = fake()
    port.cancel_ok = False
    port.now = 1.
    result = ctl.replace(jid, replace(request, partner_id='r2'), now=1.)
    assert result.reason == 'CANCEL_NOT_CONFIRMED'
    assert ctl.job_id == jid and port.generation == 1


def test_busy_and_unconfirmed_cancel_do_not_submit_or_forget_handle():
    ctl, port, request, jid, _ = fake()
    calls = list(port.calls)
    assert ctl.submit(request, now=0.).reason == 'SELF_BUSY'
    assert port.calls == calls
    port.abort = lambda: {'accepted': True}  # broken port: ack without clearing own job
    assert ctl.replace(jid, replace(request, partner_id='r2'), now=0.).reason == 'CANCEL_NOT_CONFIRMED'
    assert ctl.job_id == jid and port.generation == 1


@pytest.mark.parametrize('fault', ['role', 'robot', 'task', 'participants'])
def test_bad_port_ack_is_fail_closed(fault):
    port = FakeOwnPort('r3')
    submit = port.submit
    def broken(request):
        ack = submit(request)
        if fault == 'role':
            ack['arguments']['role'] = 'end_neg'
        elif fault == 'robot':
            ack['robot_id'] = 'r2'
        elif fault == 'task':
            ack['arguments']['order_id'] = 'another-order'
        else:
            port.ep.channel.participants = ('r3', 'r2')
        return ack
    port.submit = broken
    ctl = OwnPairRecovery('r3', port)
    with pytest.raises(ValueError, match='PAIR_PORT_CONTRACT_MISMATCH'):
        ctl.submit(PairRequest('beam-order', 'B', 'r1', 'end_pos'), now=0.)
    assert port.job is None and not port.host_queue and not port.arm_events


@pytest.mark.parametrize('fault', ['missing', 'task', 'participants'])
def test_endpoint_change_aborts_only_owned_attempt(fault):
    ctl, port, _, _, _ = fake()
    old_ep = port.ep
    if fault == 'missing':
        port.endpoint = lambda: None
    elif fault == 'task':
        port.ep.channel.task_id = 'unexpected-task'
    else:
        port.ep.channel.participants = ('r3', 'r2')
    result = poll(ctl, port, .1)
    assert result.reason == 'OWN_ENDPOINT_LOST'
    assert old_ep.state == 'abort' and port.job is None


def test_unrelated_new_own_job_is_never_cancelled_by_old_handle():
    ctl, port, _, jid, _ = fake()
    port.job = {'job_id': 'new-solo', 'kind': 'deliver'}
    calls = list(port.calls)
    assert ctl.cancel(jid, now=1.).reason == 'STALE_JOB'
    assert poll(ctl, port, 1.).state == 'ended'
    assert port.calls == calls and port.job['job_id'] == 'new-solo'


@pytest.mark.parametrize('peer_state,reason', [('abort', 'PARTNER_ABORT'), ('silent', 'PARTNER_SILENT')])
def test_peer_abort_and_heartbeat_loss_are_enum_only(peer_state, reason):
    ctl, port, _, _, peer = fake()
    peer.tick('start_ready', 0.)
    assert poll(ctl, port, 0.).state == 'active'
    if peer_state == 'abort':
        peer.tick('abort', .2)
    result = poll(ctl, port, .2)
    assert result.state == 'cancelled' and result.reason == reason


@pytest.mark.parametrize('condition', CONDITIONS)
def test_r3_solo_is_not_a_pair_delay_and_unseen_r3_truth_cannot_change_pair(condition):
    protocol.Transport(condition, seed=2, order_ids=['beam-order'], roles=['end_neg', 'end_pos'])
    results = []
    for private_r3 in ('held', 'moving', 'failed', 'late', 'delivered'):
        ctl, port, request, _, peer = fake(actor='r1', partner='r2', role='end_neg')
        peer.tick('start_ready', .1)
        assert poll(ctl, port, .1).state == 'active'
        # Assignment membership is necessary, never sufficient, for T12's
        # physical pair-delay denominator. A solo hold is a separate exposure.
        assert 'r3' not in request.assignment_record('r1')['role_to_robot'].values()
        results.append((ctl.record(), ctl.events, port.ep.channel.log))
    assert all(row == results[0] for row in results)


@pytest.mark.parametrize('bad', [
    PairRequest('x', 'B', 'r3', 'end_pos'), PairRequest('x', 'B', 'r4', 'end_pos'),
    PairRequest('', 'B', 'r1', 'end_pos'), PairRequest('x', 'Z', 'r1', 'end_pos'),
    PairRequest('x', 'B', 'r1', 'west'), None,
])
def test_invalid_replacement_preserves_old_attempt(bad):
    ctl, port, _, jid, _ = fake()
    calls = list(port.calls)
    with pytest.raises(ValueError, match='BAD_PAIR_REQUEST'):
        ctl.replace(jid, bad, now=1.)
    assert port.calls == calls and port.job['job_id'] == jid


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), -.1, .19, 30.01])
def test_invalid_timeout_is_rejected(value):
    with pytest.raises(ValueError, match='BAD_RENDEZVOUS_TIMEOUT'):
        OwnPairRecovery('r3', FakeOwnPort('r3'), rendezvous_timeout_s=value)


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), -1.])
def test_invalid_clock_is_rejected_without_cancellation(value):
    ctl, port, _, _, _ = fake(now=1.)
    calls = list(port.calls)
    with pytest.raises(ValueError, match='BAD_OWN_CLOCK'):
        ctl.poll(now=value)
    assert calls == port.calls


def test_clock_reversal_and_future_join_do_not_start_motion():
    ctl, port, _, _, peer = fake(now=1.)
    with pytest.raises(ValueError, match='BAD_OWN_CLOCK'):
        ctl.poll(now=.9)
    peer.tick('start_ready', 2.)
    assert poll(ctl, port, 1.1).state == 'waiting'


def legacy(host, actor):
    ex = host.robots[actor].executor
    port = LegacyOwnPairPort(actor, call=lambda api, *args: host.call(actor, api, *args),
                             status=ex.status, endpoint=lambda: ex._pair.status if ex._pair else None)
    return OwnPairRecovery(actor, port, rendezvous_timeout_s=host.pairs.rendezvous_timeout_s)


def test_legacy_port_does_not_silently_promote_fake_r3_support():
    from tests.test_zone_pair_executor import setup
    host, _ = setup()
    ctl = legacy(host, 'r3')
    result = ctl.submit(PairRequest('cargoX', 'B', 'r1', 'end_pos'), now=0.)
    assert result.reason == 'T07_ROLE_ROUTING_REQUIRED'
    assert not host.pairs.sessions


def test_role_aware_port_forwards_role_without_legacy_fallback():
    calls = []
    port = RoleAwareOwnPairPort('r3', call=lambda *args: calls.append(args) or {'accepted': False},
                               status=lambda: {'job': None}, endpoint=lambda: None)
    ctl = OwnPairRecovery('r3', port)
    assert ctl.submit(PairRequest('x', 'B', 'r1', 'end_neg'), now=0.).state == 'refused'
    assert calls == [('pair_carry', 'x', 'B', 'r1', 'end_neg')]


@pytest.mark.parametrize('condition', CONDITIONS)
def test_real_peer_private_mutation_does_not_affect_wait_or_cancel(condition):
    from tests.test_zone_pair_executor import setup, active
    results = []
    for mutate in (False, True):
        transport = protocol.Transport(condition, seed=2, order_ids=['cargoX'], roles=['end_neg', 'end_pos'])
        host, exs = setup()
        ctl = legacy(host, 'r1')
        req = PairRequest('cargoX', 'B', 'r2', 'end_neg')
        result = ctl.submit(req, now=0.)
        if mutate:
            exs['r2'].last_report = replace(exs['r2'].last_report, x_m=999., y_m=-999., std_xy_m=123.)
            exs['r2']._holding_after = {'answer': 'yes', 'source': 'private fixture'}
            exs['r2'].orders['cargoX']['destination_zone'] = 'C'
            exs['r2'].stopped = {'reason': 'private fixture'}
            host.eval_only['hidden_event'] = {'robot': 'r2', 'until': 52., 'success': True}
        before_peer = copy.deepcopy((exs['r2'].events, exs['r2'].api_log, host.robots['r2'].commands))
        assert ctl.poll(now=4.9).state == 'waiting'
        host.world.data.time = 5.
        assert ctl.poll(now=5.).reason == 'PAIR_RENDEZVOUS_TIMEOUT'
        assert (exs['r2'].events, exs['r2'].api_log, host.robots['r2'].commands) == before_peer
        assert transport.sent_count() == 0
        # Random opaque channel IDs are not behavioural differences.
        wire = [{k: v for k, v in row.items() if k != 'task_id'}
                for row in active(host)['r1'].status.channel.log]
        results.append((ctl.events, host.robots['r1'].commands, wire))
    assert results[0] == results[1]


@pytest.mark.parametrize('condition', CONDITIONS)
def test_real_host_cancel_flushes_both_and_stale_handle_preserves_new_own_job(condition):
    from tests.test_zone_pair_executor import setup, active
    protocol.Transport(condition, seed=2, order_ids=['cargoX'], roles=['end_neg', 'end_pos'])
    host, exs = setup()
    one, two = legacy(host, 'r1'), legacy(host, 'r2')
    request = PairRequest('cargoX', 'B', 'r2', 'end_neg')
    first = one.submit(request, now=0.)
    assert two.submit(replace(request, partner_id='r1', role='end_pos'), now=0.).state == 'waiting'
    endpoints = dict(active(host))
    for r in ('r1', 'r2'):
        host.robots[r].timeline = [(100., [{'kind': 'mecanum', 'forward': .1, 'left': 0.,
                                           'turn': 0., 'duration_s': .1}])]
        endpoints[r].port.commands.append({'kind': 'arm', 'servo_id': 1, 'pulse': 1500})
    assert one.cancel(first.job_id, now=0.).state == 'cancelled'
    assert all(ep.terminal and not ep.port.commands and not ep.controller.arm.events
               and not ep.controller.schedule for ep in endpoints.values())
    assert all(not host.robots[r].timeline and host.robots[r].port.log[-1][1] == 'hold'
               and exs[r].job is None for r in ('r1', 'r2'))
    assert exs['r3'].job is None and not exs['r3'].api_log
    fresh = one.submit(request, now=0.)
    assert fresh.state == 'waiting' and fresh.job_id != first.job_id
    assert one.cancel(first.job_id, now=0.).reason == 'STALE_JOB'
    assert exs['r1'].job.job_id == fresh.job_id
    # Retired controller callbacks cannot emit any old commands at their old deadlines.
    assert endpoints['r1'].arm_step(100.) == endpoints['r2'].arm_step(100.) == []


@pytest.mark.parametrize('offset', [-.01, -2 * EPS, 0., .01])
def test_real_pairteam_late_submission_uses_fresh_session(offset):
    from tests.test_zone_pair_executor import setup, active
    host, exs = setup()
    first = legacy(host, 'r1')
    second = legacy(host, 'r2')
    req = PairRequest('cargoX', 'B', 'r2', 'end_neg')
    assert first.submit(req, now=0.).state == 'waiting'
    old = active(host)['r1']
    now = 5. + offset
    host.world.data.time = now
    old.status.tick('start_ready', now)  # independent caller remains alive while waiting
    host._capture('r2', now)
    exs['r2'].gate.state = 'ok'
    result = second.submit(replace(req, partner_id='r1', role='end_pos'), now=now)
    assert result.state == 'waiting'
    joined = exs['r2']._pair.status.channel is old.status.channel
    assert joined == (offset < -EPS)
    if not joined:
        assert old.terminal and exs['r1'].job is None
        assert first.poll(now=now).state == 'ended'


def test_real_safety_can_end_an_accepted_submission_before_ack_returns():
    from tests.test_zone_pair_executor import setup, active
    host, exs = setup()
    first, second = legacy(host, 'r1'), legacy(host, 'r2')
    req = PairRequest('cargoX', 'B', 'r2', 'end_neg')
    assert first.submit(req, now=0.).state == 'waiting'
    host.world.data.time = 4.99
    host._capture('r2', 4.99)
    exs['r2'].gate.state = 'ok'
    # First robot emitted no heartbeat for 4.99 seconds. The real safety
    # poll ends both jobs even though second's admission ack was accepted.
    result = second.submit(replace(req, partner_id='r1', role='end_pos'), now=4.99)
    assert result.state == 'ended' and result.reason == 'OWN_JOB_ENDED_DURING_SUBMIT'
    assert all(ep.terminal for ep in active(host).values())
    assert second.job_id is None and exs['r2'].job is None


def test_real_started_pair_cancel_does_not_override_unknown_holding_for_retry():
    from tests.test_zone_pair_executor import setup, active
    host, exs = setup()
    ctl = legacy(host, 'r1')
    req = PairRequest('cargoX', 'B', 'r2', 'end_neg')
    first = ctl.submit(req, now=0.)
    host.call('r2', 'pair_carry', 'cargoX', 'B', 'r1')
    active(host)['r1'].started = True  # manipulation-in-progress fixture
    assert ctl.cancel(first.job_id, now=0.).state == 'cancelled'
    assert exs['r1']._holding_after['answer'] == 'unknown'
    assert ctl.submit(req, now=0.).reason == 'SELF_OCCUPIED'
