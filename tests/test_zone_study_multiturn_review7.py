"""Review 7: remaining executor work is distinct from decision budget spend.

Only fake wire/clock and own executor job events; no model or physical step.
"""
from dataclasses import replace
import json

import pytest

from harness import zone_study_integration as zi
from harness.zone_event_scheduler import CallPolicy
from tests import test_zone_study_multiturn as fixture
from tests.test_zone_study_multiturn import offline_only  # noqa: F401
from tests.test_zone_study_multiturn_properties import (  # noqa: F401
    v64, signature, finish_for_comparison)
from tests.test_zone_study_multiturn_model import actual
from tests.zone_multiturn_reference import ACTORS, U, Scenario, reference


HORIZONS = (8., 12., 20.)


def run_review7(condition, horizon, *, trial_cls=None, first='claim'):
    trial, clock, links, requests = fixture.make_trial(
        condition, horizon=horizon, policy=CallPolicy(max_attempts_total=3),
        trial_cls=trial_cls, first=first, follow_claim=False)
    fixture.advance(trial, clock, links, horizon)
    result = finish_for_comparison(trial, horizon)
    assert trial.send_ledger.sends() == len(requests) == 3
    assert len(trial.dispatch_log) == 3
    if first == 'claim':
        assert all(row['ack']['accepted'] for row in trial.dispatch_log)
    assert all((link.job() is not None) == (first == 'claim') for link in links.values())
    assert trial.quiescent() == (first != 'claim')
    assert not trial.scheduler.holding() and not trial.scheduler.censored
    assert trial.scheduler.budget.remaining() == 0
    return trial, requests, result


def expected_state(trial, pending, *, horizon_hit=True, unfinished=0):
    # Fixture facts: exactly one confirmed HTTP/logical call per actor; no
    # outstanding reservation after reconciliation. No production helper used.
    return {
        'quiescent': pending == unfinished == 0,
        'pending_work_count': pending, 'in_flight_calls': unfinished,
        'censored_calls': unfinished, 'committed_sends': 3, 'reserved': 0,
        'remaining_budget': {'http_total': 0, 'http_per_actor': dict.fromkeys(ACTORS, 0),
                             'calls_per_actor': dict.fromkeys(ACTORS, 29), 'calls_total': 87},
        'horizon_hit': horizon_hit,
    }


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
@pytest.mark.parametrize('horizon', HORIZONS)
def test_review7_http_cap_with_running_jobs_is_horizon(condition, horizon, v64):
    old, old_requests, old_result = run_review7('no_comm', horizon, trial_cls=v64)
    trial, requests, result = run_review7(condition, horizon)
    assert old_result.end_reason == 'sim_horizon'
    assert result.end_reason == old_result.end_reason
    assert result.end_state == expected_state(trial, 3)
    if condition == 'no_comm':
        assert signature(trial, requests) == signature(old, old_requests)


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
@pytest.mark.parametrize('first,horizon', [('continue', 8.), ('claim', 90.), ('continue', 90.)])
def test_v64_refusal_label_is_independent_of_terminal_jobs(condition, first, horizon, v64, tmp_path):
    old, old_requests, old_result = run_review7('no_comm', horizon, trial_cls=v64, first=first)
    trial, requests, result = run_review7(condition, horizon, first=first)
    # Idle communication recipients attempt an extra decision at 6.1 s and
    # record a refusal. Busy recipients defer it; no_comm has no such event.
    assert result.end_reason == ('sim_horizon' if horizon == 8. and condition == 'no_comm'
                                 else 'budget_exhausted')
    assert result.end_state == expected_state(trial, 3 if first == 'claim' else 0)
    if condition == 'no_comm':
        assert result.end_reason == old_result.end_reason
        assert signature(trial, requests) == signature(old, old_requests)
    record = trial.trial_record(result)
    path = tmp_path / 'trial_record.json'
    path.write_text(json.dumps(record, sort_keys=True))
    assert json.loads(path.read_text())['end_state'] == result.end_state
    record['end_state']['remaining_budget']['http_total'] = -1
    assert result.end_state['remaining_budget']['http_total'] == 0


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
@pytest.mark.parametrize('end,horizon', [(4., 4.), (4., 8.), (8., 20.)])
def test_end_state_keeps_censored_calls_and_actual_horizon(condition, end, horizon):
    trial, clock, links, _ = fixture.make_trial(
        condition, first='continue', follow_claim=False, horizon=horizon,
        policy=CallPolicy(max_attempts_total=3))
    fixture.advance(trial, clock, links, end)
    result = trial.finish(end)
    assert result.end_reason == ('budget_exhausted' if end == 8. and condition != 'no_comm'
                                 else 'sim_horizon')
    assert result.end_state == expected_state(trial, 0, horizon_hit=end == horizon,
                                               unfinished=3 if end == 4. else 0)


class SuccessfulScenario(Scenario):
    def response(self, actor, at):
        return 'ok', 0, True


def job_scenario(horizon=8.):
    return SuccessfulScenario(
        0, tuple((0., kind, a) for kind in ('busy', 'common') for a in ACTORS),
        horizon, 0, 3, 30, 30, 0, 60 * U)


@pytest.mark.parametrize('horizon', HORIZONS)
def test_reference_accounts_for_unfinished_executor_jobs(horizon):
    spec = job_scenario(horizon)
    expected = reference(spec)
    assert expected['end_reason'] == 'sim_horizon'
    observed, _ = actual(spec)
    assert observed == expected


@pytest.mark.parametrize('idle_actors', [(), ('r1',), ('r1', 'r2'), ACTORS])
def test_only_last_job_boundary_can_make_trial_quiescent(idle_actors):
    spec = job_scenario()
    spec = replace(spec, events=spec.events + tuple((7., 'boundary', a) for a in idle_actors))
    expected = reference(spec)
    assert expected['end_reason'] == 'sim_horizon'  # no admission was refused
    assert expected['end_state']['quiescent'] == (idle_actors == ACTORS)
    assert expected['end_state']['pending_work_count'] == 3 - len(idle_actors)
    observed, _ = actual(spec)
    assert observed == expected
