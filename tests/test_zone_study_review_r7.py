"""Regressions of the seventh review round of PR 194, P1 (Codex ``codex-194-r7``).

The scheduler charged what an adapter REPORTED it sent: ``NotSent`` refunded a
call whose request had left, and a too small ``sent_attempts`` freed a budget
slot for one more request. Root fix: every request passes the transport's send
ledger (``harness/zone_send_ledger.py``), the scheduler authorises each one
against the budget before it reaches the wire, charges what the ledger counted,
refunds only a call the ledger shows 0 sends for, and cross-checks the report
(a mismatch is a recorded violation; the reply executes nothing).

The two Codex counterexamples are reproduced first. Their adapters send through
``PendingCall.http_open`` when the scheduler provides one and straight to the
wire otherwise, so the same tests run against the pre-fix code and fail there
with the reviewed numbers (``review-r7/test_results.json``); the import guard
below exists only for that run, and ``test_r7_the_send_ledger_is_required``
fails whenever the guard was used. Offline only: no simulator, no model call.
The adapter and offline-loop tests are in ``test_zone_study_review_r7_transport.py``,
the P2 contract-version tests in ``test_zone_study_review_r7_contract.py``.
"""
from __future__ import annotations

import pytest

from harness import zone_event_scheduler as ds
from harness import zone_sim_cost as zc

try:                                   # pre-fix code has no ledger (fail-before run only)
    from harness import zone_send_ledger as sl
except ImportError:                    # pragma: no cover - the check below fails then
    sl = None


def test_r7_the_send_ledger_is_required():
    assert sl is not None, 'harness.zone_send_ledger is missing'
    with pytest.raises(TypeError, match='SendLedger'):
        ds.EventScheduler(object())


class _Wire:
    """Where an adapter's requests go: the ledger opener, or (pre-fix) straight out."""

    def __init__(self):
        self.scripted = sl.ScriptedWire() if sl else None
        self.send_ledger = sl.SendLedger(self.scripted) if sl else None
        self.direct = 0

    @property
    def sends(self):
        """Requests that really reached the wire."""
        return self.direct + (len(self.scripted.requests) if self.scripted else 0)

    def send(self, call):
        """One request; False when the ledger blocked it (nothing left)."""
        opener = getattr(call, 'http_open', None)
        if opener is None:
            self.direct += 1
            return True
        try:
            sl.send(opener)
        except sl.SendBlocked:
            return False
        return True


def _charged(sched):
    """Attempts the scheduler charged (completed + censored calls)."""
    return sum(len(call.cost.attempts) for call in sched.calls) + sum(r['http_attempts'] for r in sched.censored)


def _violations(sched):
    return [v for row in getattr(sched, 'send_violations', ()) for v in row['violations']]


# =========================================================================== #
# Counterexample 1 — submit() sends, then raises NotSent; the caller runs again

class _SendsThenClaimsNotSent(_Wire):
    def __init__(self, *, sends_per_submit=1):
        super().__init__()
        self.sends_per_submit = sends_per_submit

    def submit(self, call):
        for _ in range(self.sends_per_submit):
            self.send(call)
        raise ds.NotSent('claims nothing left')

    def reply(self, token):
        raise AssertionError('reply() is never reached for a failed submit()')


def _run_caller_loop(sched, runs=3):
    """The review scenario: the caller handles the exception and runs again."""
    for _ in range(runs):
        sched.trigger('r1', 'start')
        try:
            sched.run(until_s=sched.now() + 60.0)
        except ds.NotSent:
            pass


def test_r7_codex_1_cap_1_a_contradicted_not_sent_is_charged_and_the_reruns_are_refused():
    """Pre-fix: 3 sends, 0 charged, 0 reserved, 0 SIM s. Now: the one send the cap
    allows is charged, the claim is a violation, the reruns never send."""
    adapter = _SendsThenClaimsNotSent()
    sched = ds.EventScheduler(adapter, policy=ds.CallPolicy(max_http_attempts_per_actor=1,
                                                            max_calls_per_actor=5))
    _run_caller_loop(sched)
    assert adapter.sends == 1 == _charged(sched) == sched.budget.used['r1']
    assert sched.send_ledger.sends() == 1 and sched.unsent_calls == []
    assert _violations(sched) == ['not_sent_contradicted']
    assert sched.calls[0].cost.sim_s > 0 and sched.calls[0].notes['send_violation'] is True
    assert sched.metrics['r1']['budget_refused'] >= 2              # the reruns: refused, not sent


def test_r7_codex_1_uncapped_all_three_sends_are_charged_with_three_violations():
    adapter = _SendsThenClaimsNotSent()
    sched = ds.EventScheduler(adapter, policy=ds.CallPolicy(max_http_attempts_per_actor=5, max_retries=0,
                                                            max_calls_per_actor=5, min_interval_s=0.))
    _run_caller_loop(sched)
    assert adapter.sends == 3 == _charged(sched) == sched.send_ledger.sends() == sched.budget.used['r1']
    assert _violations(sched) == ['not_sent_contradicted'] * 3
    assert sum(call.cost.sim_s for call in sched.calls) == 3 * zc.call_cost([zc.Attempt(outcome='error')],
                                                                            sched.params).sim_s


def test_r7_codex_1_cap_1_extra_sends_inside_one_submit_are_blocked_before_the_wire():
    adapter = _SendsThenClaimsNotSent(sends_per_submit=3)
    sched = ds.EventScheduler(adapter, policy=ds.CallPolicy(max_http_attempts_per_actor=1,
                                                            max_calls_per_actor=5))
    _run_caller_loop(sched, runs=1)
    assert adapter.sends == 1 == _charged(sched) == sched.send_ledger.sends()
    assert sched.send_ledger.blocked() == 2
    assert [row['reason'] for row in sched.blocked_sends] == ['http_budget', 'http_budget']


# =========================================================================== #
# Counterexample 2 — both requests left, the failure declares sent_attempts=1

class _DeclaresOneSend(_Wire):
    """Sends the request and its reserved retry, then claims only one left.

    ``force`` = also try one more retry although the reservation was refused.
    """

    def __init__(self, *, force=False):
        super().__init__()
        self.force = force

    def submit(self, call):
        self.send(call)
        return call

    def reply(self, token):
        if token.reserve(1) or self.force:
            self.send(token)
        raise ds.TransportFailure('retry failed', attempts=(zc.Attempt(outcome='error'),),
                                  usage_known=False, sent_attempts=1)


def test_r7_codex_2_cap_2_the_ledger_is_charged_and_the_freed_slot_never_exists():
    """Pre-fix: 3 sends under a cap of 2, 2 charged, no violation. Now: both sends
    of the first call are charged, the declaration is a violation, and the
    scheduler's retry is refused instead of sending a third request."""
    adapter = _DeclaresOneSend()
    sched = ds.EventScheduler(adapter, policy=ds.CallPolicy(max_http_attempts_per_actor=2,
                                                            max_calls_per_actor=5))
    sched.trigger('r1', 'start')
    sched.run(until_s=60.0)
    sched.trigger('r1', 'retry')                    # the caller asks again as well
    sched.run(until_s=120.0)
    assert adapter.sends == 2 == _charged(sched) == sched.budget.used['r1'] == sched.send_ledger.sends()
    assert _violations(sched) == ['declared_sent_mismatch']
    first = sched.calls[0]
    assert len(first.cost.attempts) == 2 and first.notes['usage_known'] is False
    assert sched.discarded[0]['reason'] == 'send_ledger_violation' and len(sched.calls) == 1
    assert sched.metrics['r1']['budget_refused'] == 1


def test_r7_codex_2_cap_3_three_sends_are_charged_and_a_forced_fourth_is_blocked():
    adapter = _DeclaresOneSend(force=True)
    sched = ds.EventScheduler(adapter, policy=ds.CallPolicy(max_http_attempts_per_actor=3,
                                                            max_calls_per_actor=5))
    sched.trigger('r1', 'start')
    sched.run(until_s=60.0)
    sched.trigger('r1', 'retry')
    sched.run(until_s=120.0)
    assert adapter.sends == 3 == _charged(sched) == sched.budget.used['r1']
    assert sched.send_ledger.blocked() == 1 and sched.blocked_sends[0]['reason'] == 'http_budget'
    # the second call's "1 sent" is true (its forced retry was blocked): no violation
    assert _violations(sched) == ['declared_sent_mismatch']
    assert [len(call.cost.attempts) for call in sched.calls] == [2, 1]


# =========================================================================== #
# The settlement rules around the counterexamples

class _Scripted(_Wire):
    """``submit_sends``/``reply_sends`` requests, then ``outcome`` (raise or return)."""

    def __init__(self, outcome, *, submit_sends=0, reply_sends=0, raise_in_submit=None):
        super().__init__()
        self.outcome, self.submit_sends, self.reply_sends = outcome, submit_sends, reply_sends
        self.raise_in_submit = raise_in_submit

    def submit(self, call):
        for _ in range(self.submit_sends):
            self.send(call)
        if self.raise_in_submit is not None:
            raise self.raise_in_submit
        return call

    def reply(self, token):
        for _ in range(self.reply_sends):
            self.send(token)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def _sched(transport, **kw):
    kw.setdefault('max_calls_per_actor', 3)
    holds, actions = [], []
    sched = ds.EventScheduler(transport, policy=ds.CallPolicy(**kw),
                              on_hold=lambda a, h, t: holds.append((a, h, t)),
                              on_action=lambda a, action, t: actions.append(action))
    sched.trigger('r1', 'start')
    sched.run(until_s=60.0)
    return sched, holds, actions


def test_r7_a_reply_without_any_send_is_refunded_and_executes_nothing():
    reply = ds.CallReply(attempts=(zc.Attempt(output_tokens=40),), action='go')
    sched, holds, actions = _sched(_Scripted(reply), max_retries=0, max_calls_per_actor=1)
    assert actions == [] and sched.calls == [] and sched.budget.used['r1'] == 0
    (row,) = sched.unsent_calls
    assert row['stage'] == 'reply' and row['refunded'] == 1 and sched.budget.outstanding() == 0
    assert _violations(sched) == ['reply_without_send']
    assert sched.metrics['r1']['calls'] == 0 and sched.metrics['r1']['not_sent'] == 1
    assert holds[0][:2] == ('r1', True) and holds[-1][:2] == ('r1', False)        # the hold ends
    assert sched.ledger[row['call_id']]['status'] == 'not_sent'
    # the refunded logical call is really available again
    sched.transport.outcome = reply
    sched.transport.reply_sends = 1
    sched.trigger('r1', 'retry')
    sched.run(until_s=120.0)
    assert actions == ['go'] and sched.budget.used['r1'] == 1


@pytest.mark.parametrize('stage', ['submit', 'reply'])
def test_r7_a_local_failure_before_any_send_is_refunded_without_a_violation(stage):
    error = ValueError('payload failed validation before the wire')
    transport = _Scripted(error, raise_in_submit=error if stage == 'submit' else None)
    sched, _, actions = _sched(transport)
    assert sched.calls == [] and sched.budget.used['r1'] == 0 and _violations(sched) == []
    assert sched.unsent_calls[0]['stage'] == stage and sched.unsent_calls[0]['error'].startswith('ValueError')
    assert actions == []


@pytest.mark.parametrize('claim, expected', [
    (lambda: ds.TransportFailure('x', attempts=(zc.Attempt(outcome='invalid', input_tokens=9),)),
     ['attempts_without_send']),
    (lambda: ds.TransportFailure('x', attempts=(), usage_known=False, sent_attempts=2),
     ['declared_sent_mismatch']),
])
def test_r7_a_submit_claim_without_a_send_is_a_violation_and_refunded(claim, expected):
    sched, _, _ = _sched(_Scripted(None, raise_in_submit=claim()))
    assert _violations(sched) == expected and sched.budget.used['r1'] == 0 and sched.calls == []


def test_r7_a_known_usage_reply_that_under_reports_the_ledger_is_padded_and_discarded():
    reply = ds.CallReply(attempts=(zc.Attempt(input_tokens=100, output_tokens=20),), action='go')
    sched, _, actions = _sched(_Scripted(reply, submit_sends=1, reply_sends=1), max_retries=0)
    call = sched.calls[0]
    assert [a.outcome for a in call.cost.attempts] == ['error', 'ok'] and call.notes['usage_known'] is False
    assert _violations(sched) == ['attempts_underreported'] and actions == []
    assert sched.unreported_attempts[0]['counted'] == 2 == sched.budget.used['r1']


def test_r7_an_agreeing_report_is_taken_as_is():
    reply = ds.CallReply(attempts=(zc.Attempt(outcome='error'), zc.Attempt(output_tokens=20)), action='go',
                         sent_attempts=2)
    sched, _, actions = _sched(_Scripted(reply, submit_sends=1, reply_sends=1))
    assert actions == ['go'] and _violations(sched) == [] and sched.unreported_attempts == []
    assert sched.budget.used['r1'] == 2 == sched.send_ledger.sends()


def test_r7_a_send_after_the_reply_is_blocked_and_recorded():
    """A late request of a settled call never reaches the wire."""
    class Late(_Scripted):
        def reply(self, token):
            self.stale = token
            return super().reply(token)

    transport = Late(ds.CallReply(attempts=(zc.Attempt(),)), submit_sends=1)
    sched, _, _ = _sched(transport, max_calls_per_actor=1)
    assert transport.send(transport.stale) is False and transport.sends == 1
    assert sched.blocked_sends[-1]['reason'] == 'call_settled'
    assert _violations(sched) == ['send_after_settlement']
    with pytest.raises(ValueError, match='not outstanding'):
        transport.stale.reserve(1)


def test_r7_nothing_sent_by_the_horizon_is_refunded_not_censored():
    """The censor path fetches the reply at the horizon through the same rule."""
    sched = ds.EventScheduler(_Scripted(RuntimeError('local')), policy=ds.CallPolicy(max_calls_per_actor=2))
    sched.trigger('r1', 'start')
    sched.arm_observations(('r1',), period_s=1.0, first_at=0.4)
    sched.run(until_s=0.3)
    assert sched.censored == [] and sched.unsent_calls[0]['stage'] == 'reply'
    assert sched.budget.used['r1'] == 0 and sched.budget.outstanding() == 0


def test_r7_the_team_cap_holds_at_the_wire_when_three_actors_send_twice():
    transport = _Scripted(ds.CallReply(attempts=(zc.Attempt(outcome='error'), zc.Attempt()), sent_attempts=2),
                          submit_sends=1, reply_sends=1)
    sched = ds.EventScheduler(transport, policy=ds.CallPolicy(max_attempts_total=4, max_calls_per_actor=1))
    for actor in ds.DEFAULT_ACTORS:
        sched.trigger(actor, 'start')
    sched.run(until_s=60.0)
    assert transport.sends == 4 == sched.budget.used_total() == _charged(sched)
    assert sched.send_ledger.blocked() == 2 and sched.budget.outstanding() == 0
    # the two actors whose retry was blocked still claimed 2: violations, charged 1 each
    assert sorted(len(call.cost.attempts) for call in sched.calls) == [1, 1, 2]
    assert _violations(sched).count('attempts_overreported') == 2


def test_r7_replay_transport_sends_every_scripted_attempt_through_the_ledger():
    two = ds.CallReply(attempts=(zc.Attempt(outcome='error'), zc.Attempt()), action='go')
    transport = ds.ReplayTransport({'r1': [two]})
    sched = ds.EventScheduler(transport, policy=ds.CallPolicy(max_calls_per_actor=1))
    sched.trigger('r1', 'start')
    sched.run(until_s=60.0)
    assert sched.send_ledger is transport.send_ledger and len(transport.wire.requests) == 2
    assert sched.send_ledger.by_call() == {sched.calls[0].call_id: {'sent': 2, 'blocked': 0}}


@pytest.mark.parametrize('ledger', [None, {}, 'ledger', 0])
def test_r7_boundary_a_transport_without_a_real_ledger_is_refused(ledger):
    class Transport:
        send_ledger = ledger

        def submit(self, call):
            return call

        def reply(self, token):
            return ds.CallReply()

    with pytest.raises(TypeError, match='SendLedger'):
        ds.EventScheduler(Transport())


def test_r7_boundary_one_ledger_cannot_serve_two_schedulers():
    transport = ds.ReplayTransport({})
    ds.EventScheduler(transport)
    with pytest.raises(ValueError, match='owner'):
        ds.EventScheduler(transport)


def test_r7_boundary_an_interrupt_keeps_the_reservation_and_records_the_sends():
    transport = _Scripted(None, submit_sends=1, raise_in_submit=KeyboardInterrupt())
    sched = ds.EventScheduler(transport, policy=ds.CallPolicy())
    sched.trigger('r1', 'start')
    with pytest.raises(KeyboardInterrupt):
        sched.run(until_s=60.0)
    (entry,) = sched.ledger.values()
    assert entry['status'] == 'interrupted' and entry['ledger_sends'] == 1
    assert sched.budget.outstanding() == 1


def test_r7_boundary_commit_refuses_more_attempts_than_reserved():
    budget = ds.AttemptBudget(per_actor=2, total=None)
    assert budget.reserve('r1', 1)
    with pytest.raises(AssertionError, match='reserved'):
        budget.commit('r1', reserved=1, actual=2)
    budget.commit('r1', reserved=1, actual=0)                     # 0 ledgered = refund
    assert budget.used['r1'] == 0 and budget.outstanding() == 0
