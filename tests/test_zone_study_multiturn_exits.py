"""Call-exit matrix: real scheduler/ledger, scripted transport, no model/physics.

Every row drives an actual exit, with common-only, message-only and both waits.
Settlement resumes eligibility; refusal has no in-flight call to settle;
interrupts and the episode horizon must not start work during shutdown.
"""
import asyncio
from dataclasses import dataclass, replace

import pytest

from harness import zone_event_scheduler as core
from harness.zone_send_ledger import send
from harness.zone_sim_cost import Attempt, CostParams
from harness.zone_study_decisions import DecisionLimits, DecisionScheduler
from tests.test_zone_study_multiturn import offline_only  # noqa: F401


@dataclass(frozen=True)
class ExitCase:
    path: str
    status: str
    handling: str
    sends: int = 1
    target_at: float = 0.


# Inventory of terminal branches, not just outcome labels. Keeping the expected
# handling beside the branch makes omissions visible during scheduler reviews.
EXIT_CASES = (
    ExitCase('normal', 'done', 'wake'),
    ExitCase('invalid_reply', 'failed', 'wake'),
    ExitCase('error_reply', 'failed', 'wake'),
    ExitCase('timeout_reply', 'failed', 'wake'),
    ExitCase('error_submit_after_send', 'failed', 'wake'),
    ExitCase('not_sent_after_send', 'failed', 'wake'),
    ExitCase('retry_exhausted', 'failed', 'wake', target_at=2.),
    ExitCase('zero_reply_error', 'not_sent', 'wake', sends=0),
    ExitCase('zero_reply_not_sent', 'not_sent', 'wake', sends=0),
    ExitCase('zero_request_store', 'not_sent', 'wake', sends=0),
    ExitCase('zero_wire_budget', 'not_sent', 'wake', sends=0),
    ExitCase('zero_submit_error', 'not_sent', 'never_pending', sends=0),
    ExitCase('zero_submit_not_sent', 'not_sent', 'never_pending', sends=0),
    ExitCase('actor_call_budget', '', 'refuse', sends=0),
    ExitCase('actor_http_budget', '', 'refuse', sends=0),
    ExitCase('team_http_budget', '', 'refuse', sends=0),
    ExitCase('episode_call_budget', '', 'refuse', sends=0),
    ExitCase('external_budget', '', 'refuse', sends=0),
    ExitCase('cancel_submit', 'interrupted', 'stop', sends=0),
    ExitCase('cancel_submit_after_send', 'interrupted', 'stop'),
    ExitCase('cancel_reply', 'outstanding', 'stop', sends=0),
    ExitCase('episode_pending', 'censored', 'close'),
    ExitCase('episode_charged', 'censored', 'close'),
    ExitCase('episode_zero_send', 'not_sent', 'close', sends=0),
)


def deliver(scheduler, at):
    """An exogenous peer delivery, via the real inbox/event handler."""
    scheduler._push('message', at, (0., 0, 0, 0), {
        'message_id': 'peer-message', 'call_id': 'peer-call', 'sender': 'r3',
        'recipient': 'r1', 'recipients': ('r1',), 'encoding': 'free_ko',
        'body': {'text': '다음 작업을 확인해 주세요.'}, 'broadcast': False,
        'reply_to': None, 'sent_sim_s': 0., 'slot': 0,
    })


class ExitTransport(core.ReplayTransport):
    def __init__(self, case):
        super().__init__({})
        self.case = case
        self.snapshots = []

    def target(self, call):
        return call.started_sim_s <= self.case.target_at

    def submit(self, call):
        self.snapshots.append((call, self.scheduler.inbox(call.actor)))
        if self.target(call):
            path = self.case.path
            if path in ('error_submit_after_send', 'not_sent_after_send', 'cancel_submit_after_send'):
                send(call.http_open)
            if path in ('zero_submit_error', 'error_submit_after_send'):
                raise ValueError('submit failed')
            if path in ('zero_submit_not_sent', 'not_sent_after_send'):
                raise core.NotSent('submit refused')
            if path.startswith('cancel_submit'):
                raise KeyboardInterrupt('cancelled submit')
        return super().submit(call)

    def reply(self, call):
        if self.target(call):
            path = self.case.path
            if path in ('zero_reply_error', 'episode_zero_send'):
                raise ValueError('request construction failed')
            if path == 'zero_reply_not_sent':
                raise core.NotSent('pre-wire refusal')
            if path == 'cancel_reply':
                raise asyncio.CancelledError('cancelled reply')
            if path in ('error_reply', 'retry_exhausted'):
                send(call.http_open)
                raise OSError('failed wire')
            outcome = {'invalid_reply': 'invalid', 'timeout_reply': 'timeout'}.get(path, 'ok')
            reply = core.CallReply(attempts=(Attempt(outcome=outcome),), action='fixture-action')
        else:
            reply = core.CallReply(action='fixture-action')
        return self._sent(call, reply)


def scheduler_for(case):
    transport = ExitTransport(case)
    holds, actions = [], []
    scheduler = DecisionScheduler(
        transport, own_job=lambda actor: None, decision_limits=DecisionLimits(),
        policy=core.CallPolicy(max_retries=1 if case.path == 'retry_exhausted' else 0),
        cost_params=CostParams(input_token_s=0., output_token_s=0., timeout_s=.5),
        on_hold=lambda *args: holds.append(args), on_action=lambda *args: actions.append(args))
    transport.scheduler = scheduler
    if case.path == 'zero_request_store':
        def store(row, kind, data):
            if kind == 'request' and row['call_id'] == 'call-0001-r1':
                raise OSError('request store failed')
        transport.send_ledger._store = store
    elif case.path == 'zero_wire_budget':
        authorize = transport.send_ledger._authorize
        transport.send_ledger._authorize = lambda cid: (
            'http_budget' if cid == 'call-0001-r1' else authorize(cid))
    return scheduler, transport, holds, actions


def queue_waits(scheduler, waits, at):
    if waits in ('message', 'both'):
        deliver(scheduler, at + .1)
    if waits in ('common', 'both'):
        scheduler.trigger('r1', 'idle', at=at + .2)


@pytest.mark.parametrize('waits', ['common', 'message', 'both'])
@pytest.mark.parametrize('budget_closed', [False, True])
@pytest.mark.parametrize('case', [c for c in EXIT_CASES if c.handling == 'wake'], ids=lambda c: c.path)
def test_settlement_exit_wakes_both_lanes(case, waits, budget_closed):
    s, transport, holds, actions = scheduler_for(case)
    s.arm_observations(('r1',), period_s=.1, first_at=.1)
    s.trigger('r1', 'start')
    s.run(until_s=case.target_at, close_at_horizon=False)
    queue_waits(s, waits, case.target_at)
    s.run(until_s=case.target_at + .2, close_at_horizon=False)
    assert ('r1' in s._deferred) == (waits in ('common', 'both'))
    assert any(e.active and e.actor == 'r1' for e in s.event_inputs) == (waits in ('message', 'both'))
    target = transport.snapshots[-1][0]
    assert target.started_sim_s == case.target_at
    if budget_closed:
        s.external_budget_spent = lambda: True
    s.run(until_s=case.target_at + 3.1, close_at_horizon=False)

    followups = [(call, inbox) for call, inbox in transport.snapshots
                 if call.started_sim_s > case.target_at]
    if budget_closed:
        assert not followups
        assert s.metrics['r1']['budget_refused'] == (2 if waits == 'both' else 1)
        assert not any(e.active for e in s.event_inputs)
        assert not any(e.kind == 'call_start' for e in s._queue)
    else:
        assert len(followups) == 1
        call, inbox = followups[0]
        assert call.started_sim_s == case.target_at + 2.
        assert s.call_causes[call.call_id]['cause'] == ('message' if waits == 'message' else 'common')
        assert bool(inbox) == (waits in ('message', 'both'))
        assert not any(e.active for e in s.event_inputs)
    assert not s._deferred and not s.holding()
    assert s.ledger[target.call_id]['status'] == case.status
    assert s.send_ledger.sends(target.call_id) == case.sends
    assert s.budget.outstanding() == 0
    assert any(a == 'r1' and not held for a, held, _ in holds)
    if case.status != 'done':
        assert not any(t < case.target_at + 2. for _, _, t in actions)
    if case.path == 'retry_exhausted':
        assert target.retry_of
        assert any(e.get('kind') == 'retry_exhausted' for e in s.events)


@pytest.mark.parametrize('waits', ['common', 'message', 'both'])
@pytest.mark.parametrize('case', [c for c in EXIT_CASES if c.handling == 'refuse'], ids=lambda c: c.path)
def test_budget_refusals_treat_both_lanes_as_ineligible(case, waits):
    s, transport, holds, actions = scheduler_for(case)
    path = case.path
    if path == 'actor_call_budget':
        s.metrics['r1']['calls'] = s.policy.max_calls_per_actor
    elif path == 'actor_http_budget':
        s.budget.used['r1'] = s.policy.max_http_attempts_per_actor
    elif path == 'team_http_budget':
        s.budget.used['r3'] = s.policy.max_attempts_total
    elif path == 'episode_call_budget':
        s.budget.used['r3'] = s.decision_limits.max_calls_total
    else:
        s.external_budget_spent = lambda: True
    queue_waits(s, waits, 0.)
    s.run(until_s=3., close_at_horizon=False)
    assert s.metrics['r1']['budget_refused'] == (2 if waits == 'both' else 1)
    assert not transport.snapshots and not s.ledger
    assert not s._queue and not s._deferred and not s.holding()
    assert not actions and not holds and s.send_ledger.sends() == 0
    # Message history is retained; no automatic retry or reservation was made.
    assert bool(s.inbox('r1')) == (waits in ('message', 'both'))
    assert s.budget.outstanding() == 0


@pytest.mark.parametrize('case', [c for c in EXIT_CASES if c.handling == 'never_pending'],
                         ids=lambda c: c.path)
def test_submit_zero_send_has_no_hold_or_deferred_wait_to_release(case):
    s, transport, holds, actions = scheduler_for(case)
    s.trigger('r1', 'start')
    if case.path == 'zero_submit_not_sent':
        with pytest.raises(core.NotSent):
            s.run(until_s=0.)
    else:
        s.run(until_s=0.)
    assert s.ledger['call-0001-r1']['status'] == 'not_sent'
    assert not s._pending and not s._thinking and not s._deferred and not any(e.active for e in s.event_inputs)
    assert not holds and not actions and not s.calls
    assert s.budget.outstanding() == s.send_ledger.sends() == 0
    # Later common/message events still enter through the same eligibility path.
    queue_waits(s, 'both', 0.)
    s.run(until_s=3.)
    assert transport.snapshots[1][0].started_sim_s == .1
    assert transport.snapshots[1][1]


@pytest.mark.parametrize('waits', ['common', 'message', 'both'])
@pytest.mark.parametrize('case', [c for c in EXIT_CASES if c.handling in ('stop', 'close')],
                         ids=lambda c: c.path)
def test_stop_and_horizon_do_not_restart_either_lane(case, waits):
    s, transport, holds, actions = scheduler_for(case)
    s.arm_observations(('r1',), period_s=.1, first_at=.1)
    s.trigger('r1', 'start')
    queue_waits(s, waits, 0.)
    if case.handling == 'stop':
        exc = asyncio.CancelledError if case.path == 'cancel_reply' else KeyboardInterrupt
        with pytest.raises(exc):
            s.run(until_s=3.)
        assert s.budget.outstanding() == 1  # interrupted send accounting is preserved
    else:
        # Pending horizon precedes min_call_s=.5; charged horizon follows it
        # but precedes the reply's release at 1.0. Both waits exist by .2.
        horizon = .8 if case.path == 'episode_charged' else .3
        s.run(until_s=horizon)
        assert not s.holding() and s.budget.outstanding() == 0
        assert len(s.censored) == case.sends
        assert s.now() == horizon
    assert s.ledger['call-0001-r1']['status'] == case.status
    assert len(transport.snapshots) == 1 and not actions
    assert s.send_ledger.sends() == case.sends
    assert not s.calls

# Every terminal row is also exercised when the failing snapshot itself has a
# received event to acknowledge/refund. Old tests only failed the empty start.
EXTRA_CASES = (
    ExitCase('snapshot_error', 'not_sent', 'never_pending', sends=0),
    ExitCase('transport_failure', 'failed', 'wake'),
    ExitCase('declared_mismatch', 'failed', 'wake'),
    ExitCase('attempts_overreported', 'failed', 'wake'),
    ExitCase('attempts_underreported', 'failed', 'wake', sends=2),
    ExitCase('reply_without_send', 'not_sent', 'wake', sends=0),
    ExitCase('wrong_reply_type', 'outstanding', 'stop'),
    ExitCase('emit_wrong_sender', 'done', 'stop'),
    ExitCase('action_callback_error', 'done', 'stop'),
)
MESSAGE_STATES = ('absent', 'held', 'just_received', 'during_call')


def run_exit_cell(case, message_state):
    """Executable table row, also used by the saved adversarial trace audit."""
    case = replace(case, target_at=8.1 if case.path == 'retry_exhausted' else 6.1)
    s, transport, holds, actions = scheduler_for(case)
    # All rows fail r1's target call at 6.1, after a prior delivery was held or
    # just after the message handler. No model, physical step or helper wake.
    job = [message_state == 'held']
    s.event_available_at = lambda actor, cause: float('inf') if job[0] else s.clock
    s.arm_observations(('r1',), period_s=.1, first_at=.1)
    if message_state != 'absent':
        deliver(s, 5.9 if message_state == 'held' else 6.2 if message_state == 'during_call' else 6.1)
    s.run(until_s=6., close_at_horizon=False)
    held_before = any(e.active for e in s.event_inputs)
    assert held_before == (message_state == 'held')
    job[0] = False
    s.available('r1', at=6.1)
    s.trigger('r1', 'start', at=6.1)
    path = case.path
    submit, reply = transport.submit, transport.reply
    def faulted_submit(call):
        if transport.target(call) and path == 'snapshot_error':
            transport.snapshots.append((call, s.inbox(call.actor)))
            raise ValueError('snapshot failure before submit')
        return submit(call)
    def faulted_reply(call):
        if not transport.target(call):
            return reply(call)
        if path == 'reply_without_send':
            return core.CallReply()
        if path in ('transport_failure', 'declared_mismatch', 'attempts_overreported',
                    'attempts_underreported', 'wrong_reply_type'):
            send(call.http_open)
            if path == 'transport_failure':
                raise core.TransportFailure('known billed failure', attempts=(Attempt(outcome='error'),))
            if path == 'wrong_reply_type':
                return None
            if path == 'attempts_underreported':
                send(call.http_open)
            if path in ('attempts_overreported', 'declared_mismatch'):
                return core.CallReply(attempts=(Attempt(), Attempt()), sent_attempts=2)
            return core.CallReply()
        if path == 'emit_wrong_sender':
            return transport._sent(call, core.CallReply(attempts=(Attempt(utterances=1),),
                messages=(core.Message('r2', ('r1',)),)))
        return reply(call)
    transport.submit, transport.reply = faulted_submit, faulted_reply
    if path == 'action_callback_error':
        def fail(*args):
            raise ValueError('action callback failed')
        s.on_action = fail
    if path == 'actor_call_budget':
        s.metrics['r1']['calls'] = s.policy.max_calls_per_actor
    elif path == 'actor_http_budget':
        s.budget.used['r1'] = s.policy.max_http_attempts_per_actor
    elif path in ('team_http_budget', 'episode_call_budget'):
        s.budget.used['r3'] = s.policy.max_attempts_total
    elif path == 'external_budget':
        s.external_budget_spent = lambda: True
    raised = None
    horizon = 6.9 if path == 'episode_charged' else 6.4
    until = horizon if case.handling == 'close' else 12.
    try:
        s.run(until_s=until, close_at_horizon=case.handling == 'close')
    except (core.NotSent, KeyboardInterrupt, asyncio.CancelledError, TypeError, ValueError) as exc:
        raised = type(exc).__name__
        if path == 'zero_submit_not_sent':
            s.run(until_s=12., close_at_horizon=False)
        elif case.handling != 'stop':
            raise
    # Fault paths must actually execute; stop/close never run a new decision.
    if case.handling == 'refuse':
        assert not transport.snapshots and not s.ledger
        assert s.metrics['r1']['budget_refused'] >= 1
    else:
        target = transport.snapshots[0][0]
        assert target.started_sim_s == 6.1
        assert s.ledger[target.call_id]['status'] == case.status
        assert s.send_ledger.sends(target.call_id) == case.sends
        resumed = [(c, inbox) for c, inbox in transport.snapshots if c.started_sim_s > case.target_at]
        if case.handling in ('stop', 'close'):
            assert not resumed
        elif case.status == 'not_sent' and message_state in ('held', 'just_received'):
            assert resumed and resumed[0][0].started_sim_s == 8.1
            assert resumed[0][1]
        if case.handling not in ('stop',):
            assert not s.holding() and s.budget.outstanding() == 0
    return {'path': path, 'message_state': message_state, 'handling': case.handling,
            'exception': raised, 'held_before': held_before,
            'calls': [{'at': c.started_sim_s, 'id': c.call_id,
                       'inbox_ids': [m['message_id'] for m in inbox]} for c, inbox in transport.snapshots],
            'ledger': s.ledger, 'events': s.events, 'budget': s.budget.to_dict(),
            'active_inputs': [e.tags for e in s.event_inputs if e.active]}


@pytest.mark.parametrize('message_state', MESSAGE_STATES)
@pytest.mark.parametrize('case', EXIT_CASES + EXTRA_CASES, ids=lambda c: c.path)
def test_every_exit_crossed_with_message_state(case, message_state):
    run_exit_cell(case, message_state)

def run_pending_api_probe(name):
    """Boundary/validation branches with one real delivered event still held."""
    from types import SimpleNamespace
    s, transport, holds, actions = scheduler_for(ExitCase('normal', 'done', 'wake'))
    blocked = [True]
    s.event_available_at = lambda actor, cause: float('inf') if blocked[0] else s.clock
    deliver(s, 0.)
    s.run(until_s=0., close_at_horizon=False)
    source = s.event_inputs[0]
    assert source.active and ('r1', 'message') in s._deferred
    caught = None
    probes = {
        'constructor_ledger': lambda: core.EventScheduler(object()),
        'constructor_bus': lambda: core.EventScheduler(core.ReplayTransport({}), bus=object()),
        'attempts_query': lambda: s._attempts_total,
        'trigger_label': lambda: s.trigger('r1', 'unknown'),
        'trigger_past': lambda: s.trigger('r1', at=-1.),
        'event_invalid': lambda: s.event('r1', cause='', tags=(), available_at=0.),
        'reask_label': lambda: s.arm_reask('r1', 'unknown', at=1.),
        'reask_nonfinite': lambda: s.arm_reask('r1', at=float('inf')),
        'reask_past': lambda: s.arm_reask('r1', at=-1.),
        'reask_accept_skip': lambda: (s.arm_reask('r1', at=10.), s.arm_reask('r1', at=10.), s.reask_pending('r1')),
        'observe_invalid': lambda: s.arm_observations(period_s=0.),
        'timer_return': lambda: (s.timer('r2', at=0.), s.run(max_events=1)),
        'delivery_query': lambda: (s.delivery_log('r1'), s.undelivered(), s.trace()),
        'contract_query': lambda: s.contract_log(run_id='probe', condition_name='peer_ko', seed=11, provenance={}),
        'unknown_actor': lambda: s.inbox('r9'),
        'clock_past': lambda: s._advance(-1.),
        'wire_unknown': lambda: s._authorize_send('unknown'),
        'reserve_settled': lambda: s._reserve_more(core.PendingCall('unknown', 'r1', 'start', 0.)),
    }
    try:
        if name in probes:
            probes[name]()
        elif name in ('reserve_accept', 'reserve_refuse', 'wire_settled'):
            s.arm_observations(('r2',), period_s=.1, first_at=.1)
            s.trigger('r2', 'start')
            s.run(until_s=0., close_at_horizon=False)
            call = next(iter(s._pending.values()))
            if name == 'wire_settled':
                s.ledger[call.call_id]['sends_closed'] = True
                assert s._authorize_send(call.call_id) == 'call_settled'
                del s.ledger[call.call_id]['sends_closed']
            else:
                count = 1 if name == 'reserve_accept' else 100
                assert s._reserve_more(call, count) == (name == 'reserve_accept')
        elif name == 'emit_missing_id':
            s.bus = SimpleNamespace()
            s._emit(core.PendingCall('probe-call', 'r2', 'start', 0.),
                    core.CallReply(attempts=(Attempt(utterances=1),),
                                   messages=(core.Message('r2', ('r1',)),)))
        elif name == 'invalid_envelope':
            s.bus = SimpleNamespace(commit_delivery=lambda *a, **kw: None,
                                    delivered={'bad': SimpleNamespace(record=lambda: {})})
            s._on_message({'message_id': 'bad', 'recipient': 'r1'})
        else:
            raise AssertionError(name)
    except (ValueError, TypeError, KeyError, AssertionError) as exc:
        caught = type(exc).__name__
    finally:
        s.bus = None
    assert source.active  # rejected input/query never swallows the pending event
    blocked[0] = False
    s.available('r1', at=4.)
    s.run(until_s=7., close_at_horizon=False)
    resumed = [(c, inbox) for c, inbox in transport.snapshots if c.actor == 'r1']
    assert resumed and resumed[0][0].started_sim_s == 4. and resumed[0][1]
    assert not source.active
    return {'path': name, 'message_state': 'held', 'handling': 'validation_then_wake',
            'exception': caught, 'held_before': True,
            'calls': [{'at': c.started_sim_s, 'id': c.call_id,
                       'inbox_ids': [m['message_id'] for m in inbox]} for c, inbox in transport.snapshots],
            'ledger': s.ledger, 'events': s.events, 'budget': s.budget.to_dict(), 'active_inputs': []}


API_PROBES = ('constructor_ledger', 'constructor_bus', 'attempts_query', 'trigger_label', 'trigger_past',
    'event_invalid', 'reask_label', 'reask_nonfinite', 'reask_past', 'reask_accept_skip',
    'observe_invalid', 'delivery_query', 'contract_query', 'unknown_actor', 'clock_past',
    'wire_unknown', 'reserve_settled', 'reserve_accept', 'reserve_refuse', 'wire_settled',
    'emit_missing_id', 'invalid_envelope', 'timer_return')


@pytest.mark.parametrize('name', API_PROBES)
def test_pending_event_survives_every_api_return_and_rejected_input(name):
    run_pending_api_probe(name)


def test_actual_send_cap_includes_multiple_http_attempts_in_one_call():
    class TwoSends(core.ReplayTransport):
        def reply(self, call):
            return self._sent(call, core.CallReply(attempts=(Attempt(), Attempt())))
    s = DecisionScheduler(TwoSends({}), own_job=lambda actor: None,
                          decision_limits=DecisionLimits(max_calls_total=2))
    s.trigger('r1', 'start')
    s.trigger('r2', 'start', at=4.)
    s.run(until_s=10.)
    assert len(s.calls) == 1
    assert s.send_ledger.sends() == s.budget.used_total() == 2
    assert s.calls_spent()


def test_persistent_zero_send_with_zero_interval_cannot_spin_at_one_time():
    class NeverSent(core.ReplayTransport):
        def submit(self, call):
            raise OSError('persistent pre-wire failure')
    s = DecisionScheduler(NeverSent({}), own_job=lambda actor: None,
                          policy=core.CallPolicy(min_interval_s=0.), decision_limits=DecisionLimits())
    deliver(s, 0.)
    s.run(until_s=1.)
    assert s.now() == 1.
    assert len(s.unsent_calls) == 11  # 0.0 through 1.0, bounded by the SIM quantum
    assert s.send_ledger.sends() == s.budget.used_total() == s.budget.outstanding() == 0


def test_tagged_event_lifecycle_is_generic_and_subclass_has_no_exit_overrides():
    # A non-message producer uses the exact same queue, refund, boundary and
    # resume path. This fails if the state machine moves under a message name.
    for method in ('_push', '_on_call_start', '_submit', '_resume_deferred', '_release_unsent', '_retry'):
        assert getattr(DecisionScheduler, method) is getattr(core.EventScheduler, method)
    transport = ExitTransport(ExitCase('zero_submit_error', 'not_sent', 'never_pending', target_at=6.1))
    s = core.EventScheduler(transport)
    transport.scheduler = s
    source = s.event('r1', cause='operator_notice', tags=('notice-1',), available_at=float('inf'))
    s.run(until_s=6., close_at_horizon=False)
    assert source.active and not transport.snapshots
    s.available('r1', at=6.1)
    s.run(until_s=10.)
    assert [c.started_sim_s for c, _ in transport.snapshots] == [6.1, 8.1]
    assert not source.active and len(s.event_inputs) == 1
    assert len(s.unsent_calls) == 1 and s.send_ledger.sends() == 1
    assert not s.messages
    assert s.call_causes[transport.snapshots[-1][0].call_id]['cause'] == 'operator_notice'
