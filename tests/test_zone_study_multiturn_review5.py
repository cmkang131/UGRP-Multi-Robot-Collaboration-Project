"""Review 5 chained counterexamples, real scheduler/inputs and fake wire only."""
from dataclasses import asdict

import pytest

from harness import zone_study_integration as zi
from harness import zone_event_scheduler as core
from harness.zone_event_scheduler import CallPolicy
from harness.zone_send_ledger import send
from harness.zone_sim_cost import CostParams
from harness.zone_study_decisions import DecisionLimits, DecisionScheduler
from tests import test_zone_study_multiturn as fixture
from tests.test_zone_study_multiturn import offline_only  # noqa: F401
from tests.test_zone_study_multiturn_properties import common_schedule, signature, v64  # noqa: F401
from tests.test_zone_study_multiturn_exits import deliver


CHAIN_CASES = ('retry_refund', 'retry_held_refund', 'boundary_refund', 'reservation_refund')


def run_chain(case, condition, *, trial_cls=None):
    """Keep failures, own boundaries and common timers exogenous in all channels."""
    faults = []
    retry_at = 8.2 if case == 'retry_held_refund' else 8.1
    resent_at = round(retry_at + 2., 1)

    def fail(stage, call):
        faults.append({'stage': stage, 'actor': call.actor, 'at': call.started_sim_s,
                       'call_id': call.call_id, 'retry_of': call.retry_of})
        raise OSError('review5 ' + stage)

    def wire(payload, turn):
        if (case.startswith('retry_') and payload['robot_id'] == 'r1'
                and payload['sim_time_s'] in (6.1, resent_at)):
            raise OSError('review5 failed message send')

    def snapshot(call):
        if call.actor == 'r1' and (
                (case.startswith('retry_') and call.started_sim_s == retry_at)
                or (case == 'boundary_refund' and call.started_sim_s == 9.)):
            fail('snapshot', call)

    def prepare(call):
        if (case == 'boundary_refund' and call.actor == 'r1' and call.started_sim_s == 7.
                or case == 'reservation_refund' and call.actor == 'r3' and call.started_sim_s == 6.
                or case == 'retry_held_refund' and call.actor == 'r1' and call.started_sim_s == 6.2):
            fail('prepare', call)

    trial, clock, links, requests = fixture.make_trial(
        condition, first='claim' if case == 'boundary_refund' else 'continue',
        follow_claim=False, horizon=30., trial_cls=trial_cls,
        policy=CallPolicy(max_retries=1, max_attempts_total=5 if case == 'reservation_refund' else 90),
        limits=DecisionLimits(max_calls_total=5 if case == 'reservation_refund' else 90),
        wire_fault=wire, snapshot_fault=snapshot, prepare_fault=prepare)
    s = trial.scheduler
    # Tick the real event queue, so a pending call spans the 7.2 own boundary
    # before its minimum-cost reply resolution at 7.4 (likewise 6.4 refunds).
    s.arm_observations(period_s=.1, first_at=.1)
    if case == 'retry_held_refund':
        s.timer('r1', at=6.2)
    elif case == 'boundary_refund':
        s.timer('r1', at=7.)
    elif case == 'reservation_refund':
        s.timer('r2', at=5.5)  # fourth send, charged later
        s.timer('r3', at=6.)   # final slot reserved, 0-send refund at 6.4
    fixture.advance(trial, clock, links, 30. if case == 'boundary_refund' else 14.,
                    boundary=7.2 if case == 'boundary_refund' else None)
    r1 = [p for p in requests if p['robot_id'] == 'r1']
    times = [p['sim_time_s'] for p in r1]
    if condition != 'no_comm':
        if case.startswith('retry_'):
            assert times == [0., 6.1, resent_at], times
            rows = [r for r in s.ledger.values() if r['actor'] == 'r1'
                    and r['started_sim_s'] in (6.1, retry_at, resent_at)]
            assert [r['started_sim_s'] for r in rows] == [6.1, retry_at, resent_at]
            root = rows[0]['call_id']
            assert [r['retry_of'] for r in rows] == ['', root, root]
            assert s._retries[core.RetryRoot('message', root)] == 1
            assert sum(trial.send_ledger.sends(r['call_id']) for r in rows) == 2
        elif case == 'boundary_refund':
            assert times == [0., 11.], times
            assert r1[-1]['inbox']
            assert not any(e.active for e in s.event_inputs if e.actor == 'r1')
        else:
            assert times == [0., 6.4], times
            assert r1[-1]['inbox']
            assert trial.send_ledger.sends() == 5
            assert s.budget.used_total() == 5 and s.budget.outstanding() == 0
        assert not s.send_violations
        for fault in faults:
            assert s.ledger[fault['call_id']]['status'] == 'not_sent'
            assert trial.send_ledger.sends(fault['call_id']) == 0
            if fault['stage'] == 'prepare':
                assert s.ledger[fault['call_id']]['finished_sim_s'] == round(fault['at'] + .4, 1)
    return trial, requests, {
        'path': case, 'message_state': condition, 'handling': 'chained_refund',
        'exception': None, 'faults': faults, 'events': s.events,
        'calls': [{'actor': r['actor'], 'at': r['started_sim_s'], 'status': r['status'],
                   'retry_of': r['retry_of'], 'sends': trial.send_ledger.sends(r['call_id'])}
                  for r in s.ledger.values()],
        'ledger': s.ledger, 'budget': s.budget.to_dict(),
        'common_schedule': common_schedule(trial) if trial_cls is None else [],
        'event_inputs': [asdict(e) for e in getattr(s, 'event_inputs', ())],
    }


@pytest.mark.parametrize('case', CHAIN_CASES)
@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS[1:])
def test_review5_chained_counterexamples(case, condition):
    run_chain(case, condition)


@pytest.mark.parametrize('case', CHAIN_CASES)
def test_review5_chains_preserve_v64_and_add_only_message_calls(case, v64):
    old, old_requests, _ = run_chain(case, 'no_comm', trial_cls=v64)
    baseline, requests, _ = run_chain(case, 'no_comm')
    assert signature(baseline, requests) == signature(old, old_requests)
    expected = common_schedule(baseline)
    for condition in zi.MAIN_CONDITIONS[1:]:
        trial, _, _ = run_chain(case, condition)
        # Shared budgets may bind earlier after extra calls; compare eligibility
        # before the first refusal, just as in the existing generated properties.
        cutoff = min((e['sim_s'] for e in trial.scheduler.events
                      if e['kind'] == 'call_refused'), default=float('inf'))
        assert [r for r in common_schedule(trial) if r[1] < cutoff] == [
            r for r in expected if r[1] < cutoff]


BUDGET_KINDS = ('episode', 'team_http', 'actor_http', 'actor_call')
SETTLEMENTS = ('refund', 'pending_send', 'already_sent')


def run_budget_chain(kind, settlement):
    """Exercise every refundable cap, including spend before SIM settlement."""
    snapshots = []

    class Wire(core.ReplayTransport):
        def submit(self, call):
            snapshots.append(call)
            if len(snapshots) == 1 and settlement == 'already_sent':
                send(call.http_open)
            return super().submit(call)

        def reply(self, call):
            if call is snapshots[0]:
                if settlement == 'refund':
                    raise core.NotSent('first reservation returned without a send')
                if settlement == 'already_sent':
                    return core.CallReply()
            return self._sent(call, core.CallReply())

    s = DecisionScheduler(
        Wire({}), own_job=lambda actor: None,
        decision_limits=DecisionLimits(max_calls_total=1 if kind == 'episode' else 90),
        policy=CallPolicy(min_interval_s=0., max_outstanding_per_actor=2, max_retries=0,
                          max_attempts_total=1 if kind == 'team_http' else 90,
                          max_http_attempts_per_actor=1 if kind == 'actor_http' else 30,
                          max_calls_per_actor=1 if kind == 'actor_call' else 30),
        cost_params=CostParams(input_token_s=0., output_token_s=0., timeout_s=.5))
    if kind.startswith('actor_'):
        s.event('r1', cause='message', tags=('older-message',), available_at=0.)
    else:
        s.trigger('r3', 'start')
    s.arm_observations(period_s=.1, first_at=.1)
    deliver(s, .1)
    s.run(until_s=.2, close_at_horizon=False)
    event = next(e for e in s.event_inputs if 'peer-message' in e.tags)
    assert s.metrics['r1']['budget_refused'] == 1
    assert event.active == (settlement != 'already_sent')
    before = {'active': event.active, 'budget': s.budget.to_dict(), 'sends': s.send_ledger.sends()}
    s.run(until_s=3.)
    assert not any(e.active for e in s.event_inputs)
    assert s.send_ledger.sends() == 1
    assert s.budget.outstanding() == 0
    assert [c.started_sim_s for c in snapshots] == ([0., .4] if settlement == 'refund' else [0.])
    if settlement == 'refund':
        assert event.claimed_by == snapshots[-1].call_id
    return {'path': 'reservation_' + kind, 'message_state': settlement,
            'handling': 'resume' if settlement == 'refund' else 'terminal_spend', 'exception': None,
            'before': before, 'events': s.events, 'ledger': s.ledger, 'budget': s.budget.to_dict(),
            'calls': [{'at': c.started_sim_s, 'actor': c.actor, 'id': c.call_id} for c in snapshots]}


@pytest.mark.parametrize('kind', BUDGET_KINDS)
@pytest.mark.parametrize('settlement', SETTLEMENTS)
def test_only_confirmed_budget_spend_discards_inputs(kind, settlement):
    run_budget_chain(kind, settlement)


def test_common_snapshot_refund_keeps_the_consumed_message_retry_root():
    snapshots = []

    class Wire(core.ReplayTransport):
        def submit(self, call):
            snapshots.append(call)
            if not call.scheduling_lane:
                raise OSError('common snapshot failed after claiming a message retry')
            return super().submit(call)

        def reply(self, call):
            return self._sent(call, core.CallReply(attempts=(core.Attempt(outcome='error'),)))

    s = DecisionScheduler(Wire({}), own_job=lambda actor: None, decision_limits=DecisionLimits(),
                          policy=CallPolicy(max_retries=1))
    deliver(s, 0.)
    s.timer('r1', at=1.)
    s.arm_observations(period_s=.1, first_at=.1)
    s.run(until_s=10.)
    assert [c.started_sim_s for c in snapshots] == [0., 1., 3.]
    root = snapshots[0].call_id
    assert [c.retry_of for c in snapshots] == ['', '', root]
    assert s._retries == {core.RetryRoot('message', root): 1}
    assert s.send_ledger.sends() == 2
    assert not any(e.active for e in s.event_inputs)
