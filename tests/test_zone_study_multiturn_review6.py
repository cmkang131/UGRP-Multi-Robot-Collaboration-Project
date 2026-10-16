"""Review 6 causal chains, with real study inputs and a fake wire only."""
import json

import pytest

from harness import zone_event_scheduler as core
from harness import zone_study_integration as zi
from tests import test_zone_study_multiturn as fixture
from tests.test_zone_study_multiturn import offline_only  # noqa: F401
from tests.test_zone_study_multiturn_properties import (  # noqa: F401
    v64, signature, common_schedule, finish_for_comparison)


def run_review6(case, condition, *, trial_cls=None, at=5.5):
    def wire(payload, turn):
        if (case == 'separate_roots' and payload['robot_id'] == 'r1'
                and payload['sim_time_s'] in (at, round(at + 4., 6))):
            raise OSError('common failure or fresh message failure')

    def snapshot(call):
        if (case == 'separate_roots' and call.actor == 'r1'
                and call.started_sim_s == round(at + 2., 6)):
            raise OSError('common retry consumes a fresh message, then refunds')
        if (case == 'refund_horizon' and call.actor in ('r1', 'r2')
                and call.started_sim_s == 6.4):
            raise OSError('recipient snapshot sends nothing')

    def prepare(call):
        if (case == 'timer_reservation' and call.actor == 'r3'
                and call.started_sim_s in (0., at)):
            raise OSError('last slot reserved but refunded')
        if case == 'refund_horizon' and call.actor == 'r3' and call.started_sim_s == 6.:
            raise OSError('last slot refunded after delivery refusal')

    cap = {'separate_roots': 90, 'timer_reservation': 3, 'refund_horizon': 4}[case]
    trial, clock, links, requests = fixture.make_trial(
        condition, trial_cls=trial_cls, first='continue', follow_claim=False,
        send=case != 'timer_reservation', horizon=30.,
        policy=core.CallPolicy(max_retries=1, max_attempts_total=cap),
        limits=zi.DecisionLimits(max_calls_total=cap),
        wire_fault=wire, snapshot_fault=snapshot, prepare_fault=prepare)
    s = trial.scheduler
    s.arm_observations(period_s=.1, first_at=.1)
    s.timer('r1' if case == 'separate_roots' else 'r3',
            at=6. if case == 'refund_horizon' else at)
    end = {'separate_roots': 14., 'timer_reservation': 30., 'refund_horizon': 6.7}[case]
    fixture.advance(trial, clock, links, end)
    result = finish_for_comparison(trial, end)
    if case == 'separate_roots' and condition != 'no_comm':
        assert [p['sim_time_s'] for p in requests if p['robot_id'] == 'r1'] == [
            0., at, round(at + 4., 6), round(at + 6., 6)]
        rows = [r for r in s.ledger.values() if r['actor'] == 'r1']
        assert [r['retry_of'] for r in rows[:5]] == [
            '', '', rows[1]['call_id'], '', rows[3]['call_id']]
        assert s._retries[core.RetryRoot('common', rows[1]['call_id'])] == 1
        assert s._retries[core.RetryRoot('message', rows[3]['call_id'])] == 1
    elif case == 'timer_reservation':
        assert [(p['robot_id'], p['sim_time_s']) for p in requests] == [
            ('r1', 0.), ('r2', 0.), ('r1', 15.3)]
    elif case == 'refund_horizon' and condition != 'no_comm':
        assert sum(m['budget_refused'] for m in s.metrics.values()) > 0
        assert s.budget.used_total() == 3 and s.budget.remaining() == 1
        assert not s.holding() and not trial.decision_budget_spent()
        # Coordinator review7: preserve v64's historical-refusal label, while
        # the factual record exposes the restored budget after the refund.
        assert result.end_reason == 'budget_exhausted'
        assert result.end_state['remaining_budget']['http_total'] == 1
        assert not result.end_state['quiescent']
    assert not s.send_violations
    return trial, requests, {
        'path': case, 'message_state': condition, 'handling': 'review6_chain', 'exception': None,
        'calls': [{'at': r['started_sim_s'], 'actor': r['actor'], 'id': cid,
                   'retry_of': r['retry_of'], 'sends': s.send_ledger.sends(cid)}
                  for cid, r in s.ledger.items()],
        'events': s.events, 'ledger': s.ledger, 'budget': s.budget.to_dict(),
        'end_reason': result.end_reason, 'holding': s.holding(),
        'decision_budget_spent': trial.decision_budget_spent() if trial_cls is None else None,
    }


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS[1:])
@pytest.mark.parametrize('at', [5.4, 5.5, 5.6, 5.7, 5.8, 5.9])
def test_new_message_never_inherits_common_retry_allowance(condition, at):
    run_review6('separate_roots', condition, at=at)


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
@pytest.mark.parametrize('at', [4.9, 5., 5.1, 5.2, 5.3, 5.4, 5.5, 5.6])
def test_refundable_reservation_cannot_cancel_v64_reask(v64, condition, at):
    old, old_requests, _ = run_review6('timer_reservation', 'no_comm', trial_cls=v64, at=at)
    baseline, requests, _ = run_review6('timer_reservation', 'no_comm', at=at)
    # Compare every diagnostic byte too: no filtering of refusals or trace.
    assert signature(baseline, requests) == signature(old, old_requests)
    assert json.dumps(baseline.scheduler.ledger, sort_keys=True).encode() == json.dumps(
        old.scheduler.ledger, sort_keys=True).encode()
    assert baseline.scheduler.trace() == old.scheduler.trace()
    assert baseline.scheduler.budget.to_dict() == old.scheduler.budget.to_dict()
    if condition != 'no_comm':
        trial, _, _ = run_review6('timer_reservation', condition, at=at)
        assert common_schedule(trial) == common_schedule(baseline)


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS[1:])
def test_past_refusal_label_preserves_refunded_terminal_facts(condition):
    run_review6('refund_horizon', condition)


def test_coalesced_fresh_message_has_its_own_retry_allowance():
    from harness.zone_study_decisions import DecisionScheduler, DecisionLimits
    from harness.zone_sim_cost import CostParams
    from tests.test_zone_study_multiturn_exits import deliver

    class Wire(core.ReplayTransport):
        def reply(self, call):
            return self._sent(call, core.CallReply(attempts=(core.Attempt(
                outcome='error' if call.scheduling_lane else 'ok'),)))
    s = DecisionScheduler(Wire({}), own_job=lambda actor: None, decision_limits=DecisionLimits(),
                          cost_params=CostParams(input_token_s=0., output_token_s=0.),
                          policy=core.CallPolicy(max_retries=1))
    s.arm_observations(('r1',), period_s=.1, first_at=.1)
    deliver(s, 0., message_id='older-message')
    s.timer('r1', at=.4)  # starts before the first message fails
    deliver(s, .6, message_id='fresh-message')  # fresh input coalesces with its deferred retry
    s.run(until_s=8.)
    rows = list(s.ledger.values())
    assert [r['started_sim_s'] for r in rows] == [0., .4, 2.4, 4.4]
    assert [r['retry_of'] for r in rows] == ['', '', rows[0]['call_id'], rows[2]['call_id']]
    assert s._retries == {core.RetryRoot('message', rows[0]['call_id']): 1,
                          core.RetryRoot('message', rows[2]['call_id']): 1}
    # Only the fresh input participates in the last retry. The old root cannot
    # be refreshed by merging; no fifth send and no resurrection of old input.
    assert s.call_causes[rows[-1]['call_id']]['message_ids'] == ['fresh-message']
    assert [e.claimed_by for e in s.event_inputs] == [rows[2]['call_id'], rows[3]['call_id']]
    assert not any(e.active for e in s.event_inputs)
