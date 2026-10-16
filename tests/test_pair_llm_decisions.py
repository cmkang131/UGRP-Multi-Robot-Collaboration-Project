"""v100 coordinator decisions, fake replies only; no provider, physics or renderer."""
import json
from types import SimpleNamespace

import pytest

from harness import pair_llm_contract as contract
from harness import pair_llm_decisions as d
from harness import pair_llm_dispatch as dispatch
from harness import pair_llm_inputs as inputs
from harness import pair_llm_prompts_ko as prompt
from harness import pair_llm_eval as ev
from harness import zone_pair_highpose_refix as rf
from harness import zone_study_protocol as protocol
from harness.pair_llm_live import LIVE_MAX_CAP_S
from harness.pair_llm_stub import reply_json
from harness.zone_sim_cost import params
from harness.zone_study_offline import PreparedCall
from tests.pair_llm_fakes import make_inputs, offline_only  # noqa: F401


@pytest.mark.parametrize('condition,caps', [('no_comm', (0, 0, 0)), ('peer_nl', (6, 12, 12))])
def test_utterance_caps_apply_only_to_peer_nl(tmp_path, condition, caps):
    from harness.pair_llm_case import stub_adapter
    from harness.pair_llm_stub import cooperative_model
    from tests.pair_llm_fakes import map_bundle
    adapter, _ = stub_adapter(cooperative_model(), tmp_path/'ledger')
    trial = dispatch.PairTrial(contract.scenario(), condition=condition, seed=911,
        links={r: SimpleNamespace(robot_id=r) for r in prompt.PAIR_ROBOTS}, horizon_s=10.,
        map_bundle=map_bundle(), model_adapter=adapter, model_settings={'model': 'fake'})
    assert (trial.channel.cap_robot, trial.channel.cap_window, trial.channel.cap_total) == caps
    assert trial.decision_limits.max_calls_total == 72


def test_coordinator_limits_match_registry_runtime_and_hook():
    reg = contract.read_registry()
    policy = dispatch.PAIR_POLICY
    assert (policy.max_calls_per_actor, policy.max_http_attempts_per_actor, policy.max_attempts_total) == (36, 36, 72)
    assert reg['decision_limits'] == dict(max_calls_total=72, max_utterances_per_actor=6, max_utterances_total=12)
    assert reg['stop_decisions'] == d.record()
    assert contract.CAP_S == LIVE_MAX_CAP_S == 900.
    assert d.DECISION_WINDOW_S == rf.DECIDE_WINDOW_S == rf.POST_LOOK_WINDOW_S == 10.
    assert d.LOOK_AGAIN_PER_STOP == rf.LOOK_AGAIN_PER_STOP == 1
    assert d.LOOK_AGAIN_PER_CASE == rf.LOOK_AGAIN_PER_CASE == 1
    assert tuple(rf.CARRY_CHOICES) == d.CARRY_CHOICES
    assert tuple(rf.POST_LOOK_CHOICES) == d.POST_LOOK_CHOICES
    assert d.COHORT_TOKEN_CAP == 1_100_000 and d.LLM_INERT_THRESHOLD == .5


@pytest.mark.parametrize('kind', ['wait', 'give_up'])
def test_excluded_vocabulary_cannot_reach_executor(kind):
    with pytest.raises(protocol.ProtocolError, match='excluded'):
        dispatch.validate_reply(reply_json('req_test', {'kind': kind}))
    assert kind not in dispatch.PAIR_ACTION_KINDS
    for condition in prompt.PAIR_CONDITIONS:
        assert '"kind": "'+kind+'"' not in prompt.system_prompt(condition, 'r1')


@pytest.mark.parametrize('defaults,inert', [(0, False), (1, False), (2, True)])
def test_inert_is_strictly_more_than_half_and_never_changes_raw_success(defaults, inert):
    records = [{'decided_by': 'rule_default' if i < defaults else 'llm', 'decided_s': i+1.} for i in range(2)]
    row = ev.decision_evidence(condition='peer_nl', success=True, decisions=records)
    assert row['decisions_total'] == 2 and row['rule_default_fraction'] == defaults/2
    assert ('LLM_INERT' in row['classifications']) is inert
    assert row['llm_condition_evidence'] is not inert
    assert row['primary_success'] is not inert
    rule = ev.decision_evidence(condition='rule', success=True, decisions=records)
    assert rule['primary_success'] and not rule['classifications']


@pytest.mark.parametrize('label', ev.CALL_CAP_LABELS)
def test_actual_scheduler_cap_labels_exclude_llm_success_but_keep_rule_completion(label):
    events = [{'kind': 'call_refused', 'line': f'call_refused r1 idle {label}'}]
    row = ev.decision_evidence(condition='no_comm', success=True, scheduler_events=events)
    assert row['classifications'] == ['LLM_CALL_CAP_REACHED']
    assert row['call_cap_end_reason'] == 'budget_exhausted'
    assert row['completed_by_rule_default'] and not row['primary_success']
    token = ev.decision_evidence(condition='no_comm', success=True, failure_class='infra:API',
                                 scheduler_events=[{'event': 'pilot_budget_exhausted'}])
    assert token['classifications'] == ['infra:API'] and not token['completed_by_rule_default']
    assert token['token_cap_label'] == 'pilot_budget_exhausted'


@pytest.mark.parametrize('valid', [True, False])
@pytest.mark.parametrize('usage', [None, {'prompt_tokens': 7000, 'completion_tokens': 50, 'total_tokens': 7050}])
def test_every_reply_has_separate_local_text_counts_image_charge_and_provider_usage(valid, usage):
    bundled, _, _ = make_inputs('no_comm')
    request = inputs.build_request(bundled)
    trial = dispatch.PairTrial.__new__(dispatch.PairTrial)
    trial.condition, trial.params = 'no_comm', params()
    trial.requests, trial._output_token_counts = [], {}
    call = SimpleNamespace(actor='r1', call_id='call-1', started_sim_s=0.)
    raw = reply_json(bundled.request_id, {'kind': 'continue'}) if valid else 'bad json'
    trial.finish_call(call, PreparedCall(bundled, request, bundled.request_id), raw, provider_usage=usage)
    (row,) = trial.requests
    m = row['token_measurement']
    assert m['input_text_tokens'] == request['tokens']['system'] + request['tokens']['user']
    assert m['image_charge_tokens'] == 2980 and m['provider_image_tokens'] is None
    assert m['output_text_tokens'] == dispatch.pk.count_tokens(raw)
    assert m['provider_usage'] == usage and m['provider_usage_measured'] is (usage is not None)
    assert row['status'] == ('ok' if valid else 'invalid_json')


def test_unknown_response_tokens_are_unknown_not_zero():
    bundled, _, _ = make_inputs('no_comm')
    request = inputs.build_request(bundled)
    row = dispatch.billing.token_measurement(request)
    assert row['output_text_tokens'] is None and row['provider_usage'] is None
