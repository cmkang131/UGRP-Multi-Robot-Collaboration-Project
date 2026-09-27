"""Call-exit matrix: real scheduler/ledger, scripted transport, no model/physics.

Every row drives an actual exit, with common-only, message-only and both waits.
Settlement resumes eligibility; refusal has no in-flight call to settle;
interrupts and the episode horizon must not start work during shutdown.
"""
import asyncio
from dataclasses import dataclass

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
    assert ('r1' in s._message_waiting) == (waits in ('message', 'both'))
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
        assert bool(s._message_waiting) == (waits in ('message', 'both'))
        assert not any(e.kind == 'call_start' for e in s._queue)
    else:
        assert len(followups) == 1
        call, inbox = followups[0]
        assert call.started_sim_s == case.target_at + 2.
        assert s.call_causes[call.call_id]['cause'] == ('message' if waits == 'message' else 'common')
        assert bool(inbox) == (waits in ('message', 'both'))
        assert not s._message_waiting
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
        s._calls_started = s.decision_limits.max_calls_total
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
    assert not s._pending and not s._thinking and not s._deferred and not s._message_waiting
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
