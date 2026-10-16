"""PR #308 exact-head adversarial checks; expected to FAIL before repair.

Copy this file into an archived PR tree's tests/ as test_review_usage.py, then
run pytest under the primary checkout's run_ci_tests.run_locked guard.
Uses fake wire and new pytest-local SQLite only; no physics/model service.
"""
import json
from harness import zone_main_budget as budget_module
from harness.zone_event_scheduler import CallReply
from tests.test_zone_study_llm_driver import dialogue_trial, dialogue_advance, USAGE

def test_consistent_provider_usage_remains_known(tmp_path):
    trial, wire, budget, clock, links = dialogue_trial(tmp_path, 'no_comm', 700)
    dialogue_advance(trial, clock, links, 12.)
    result = trial.finish(12.)
    assert budget.usage('pilot-A')['known_tokens'] == 600 * len(result.calls)
    assert all(row['usage_known'] for row in budget.requests())
    assert all(c['cost_terms']['provider_usage'] == USAGE for c in result.calls)
    assert all(c['cost_terms']['usage_known'] for c in result.calls), json.dumps([c['cost_terms'] for c in result.calls])

def test_callreply_mapping_accepted_by_usage_classifier():
    reply = CallReply(provider_usage=USAGE)
    assert budget_module.known_total(USAGE) == 600
    assert budget_module.known_total(reply.provider_usage) == 600
