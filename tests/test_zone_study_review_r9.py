"""R9: truncated generations must never become study actions, even valid JSON."""
import io
import json
import socket
import sqlite3
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.zone_pilot_budget import PilotBudget, PROXY_SHA256
from harness.zone_send_ledger import completion_body
from harness.zone_study_contract import MAIN_CONDITIONS
from harness.zone_study_offline import FixtureActor
from harness.zone_study_scenarios import load, scenario_ids
from scripts.run_zone_study_pilot import AdapterTrial
from scripts import run_zone_study_pilot as runner
from harness import zone_pilot_ledger as pl
from harness.llm_completion import (COMPLETION_POLICY, PROXY_COMPLETION_LIMITATION,
                                     assess_completion, completion_aggregate)
from harness.zone_pilot_reconcile import reconcile, require_preflight
from harness.zone_pilot_budget import sha
from harness.zone_study_eval import model_aggregate, _request_view
from harness.gemini_proxy import GeminiProxyCompleter, GeminiProxyError

USAGE = {'prompt_tokens': 150, 'completion_tokens': 80, 'total_tokens': 240}
PROFILE = {'source_sha256': PROXY_SHA256, 'source_path': '/not-executed',
           'url': 'http://127.0.0.1:8391/v1/chat/completions'}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('R9 is offline only')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket.socket, 'connect_ex', refuse)


def test_shared_completion_source_is_pinned_without_zone_dependencies():
    from harness.rgb_execution_bundle import source_closure

    helper = 'harness/llm_completion.py'
    closure = source_closure()
    assert helper in closure
    assert not {path for path in closure if 'zone' in path}
    identity = runner.source_identity(PROFILE)
    assert identity['files'][helper] == sha((runner.ROOT / helper).read_bytes())
    assert 'harness/zone_completion.py' not in identity['files']
    assert identity['completion_policy'] == COMPLETION_POLICY


def fixture_wire(condition, reason='length', mutate=None):
    def wire(request, *, timeout=None):
        body = json.loads(request.data)
        messages = body['messages']
        user = next(p['text'] for p in messages[-1]['content'] if p['type'] == 'text')
        actor = json.loads(user)['robot_id']
        raw = FixtureActor(actor, condition, 11).respond({
            'messages': [messages[0], {'role': 'user', 'content': user}]})
        response = json.loads(completion_body(raw, usage=USAGE))
        response['choices'][0]['finish_reason'] = reason
        response['id'] = 'r9-proxy-response'
        if mutate:
            mutate(response)
        return io.BytesIO(json.dumps(response).encode())
    return wire


def trial_for(tmp_path, condition, reason='length', mutate=None):
    budget = PilotBudget.create(tmp_path / 'budget.sqlite', identity={'source_head': 'offline-r9'})
    trial = AdapterTrial(load(scenario_ids()[0]), condition=condition, seed=11, stage='preflight',
                         run_id='r9-' + condition, budget=budget, profile=PROFILE, runtime=None,
                         output=tmp_path / 'run' / condition, wire=fixture_wire(condition, reason, mutate))
    return trial, budget


@pytest.mark.parametrize('condition', MAIN_CONDITIONS)
def test_r9_length_valid_json_is_failed_not_executed(tmp_path, condition):
    trial, budget = trial_for(tmp_path, condition)
    result = trial.run_adapter()
    assert not result['actions'], 'length reply executed an action'
    assert not result['messages'], 'length reply delivered messages'
    assert list(result['scheduler_ledger'].values())[0]['status'] == 'failed'
    assert result['calls'][0]['status'] != 'ok'
    assert budget.snapshot()['reserved_attempts'] == 2


def assert_record_chain(trial, budget, result, reason, *, accepted=False):
    call = result['calls'][0]
    completion = call['cost_terms']['completion']
    saved = PilotBudget(budget.path).snapshot()
    sent = saved['sends'][0]
    assert completion['finish_reason'] == reason
    assert completion['upstream_finish_reason_verified'] is False
    assert sent['completion'] == sent['ledger']['completion'] == completion
    assert next(iter(result['scheduler_ledger'].values()))['completion'] == completion
    assert result['request_archive'][0]['completion'] == completion
    assert _request_view(call)['completion'] == completion
    assert reconcile(saved)['calls'][0]['completion'] == completion
    assert call['cost_terms']['provider_usage'] == sent['provider_usage'] == USAGE
    assert saved['reserved_attempts'] == 2 and saved['reserved_tokens'] > 2 * 8192
    assert call['http_attempts'] == 1 and call['sim_cost_s'] > 0
    assert call['input_tokens']['text'] == result['request_archive'][0]['billed_tokens']['total_text_billed']
    response = json.loads((trial.send_ledger.store_dir / sent['ledger']['response_path']).read_bytes())
    text = response['choices'][0]['message'].get('content')
    assert call['output_tokens'] == runner.pk.count_tokens(text if isinstance(text, str) else '')
    evaluation = model_aggregate({'calls': result['calls'], 'messages': result['messages']})
    assert evaluation == result['model_evaluation']
    assert evaluation['completion']['finish_reasons'] == {reason if reason is not None else 'unknown': 1}
    assert evaluation['completion']['successful_calls'] == int(accepted)
    assert evaluation['provider_usage'] == USAGE
    if not accepted:
        assert call['status'] != 'ok'
        assert not result['actions'] and not result['messages'] and not trial.envelopes
        assert sent['status'] == 'completion_rejected'
        assert evaluation['completion']['rejected_completions'] == 1


@pytest.mark.parametrize('condition', MAIN_CONDITIONS)
@pytest.mark.parametrize('reason', ['length', 'content_filter', 'tool_calls', 'SAFETY', 'MAX_TOKENS', None, ''])
def test_non_stop_preserved_through_client_ledger_evaluation(tmp_path, condition, reason):
    trial, budget = trial_for(tmp_path, condition, reason)
    result = trial.run_adapter()
    assert_record_chain(trial, budget, result, reason)
    assert 'finish_reason_not_stop' in result['calls'][0]['cost_terms']['completion']['rejection_reasons']
    # Refused generated utterances remain billed even though none are relayed.
    assert trial.scheduler.calls[0].cost.breakdown['utterances'] == (0 if condition == 'no_comm' else 1)


@pytest.mark.parametrize('condition', MAIN_CONDITIONS)
def test_stop_complete_reply_is_accepted_without_claiming_upstream_stop(tmp_path, condition):
    trial, budget = trial_for(tmp_path, condition, 'stop')
    result = trial.run_adapter()
    assert_record_chain(trial, budget, result, 'stop', accepted=True)
    assert result['actions']
    assert bool(result['messages']) == (condition != 'no_comm')
    assert result['channel']['inbox_agrees_with_scheduler']
    assert result['completion_limitation'] == PROXY_COMPLETION_LIMITATION
    assert result['model_evaluation']['completion']['upstream_finish_reason_verified_calls'] == 0


def corrupt(kind):
    def mutate(response):
        choice = response['choices'][0]
        message = choice['message']
        if kind == 'missing_reason':
            choice.pop('finish_reason')
        elif kind == 'blank':
            message['content'] = ' \n '
        elif kind == 'truncated_json':
            message['content'] = message['content'][:-1]
        elif kind == 'missing_field':
            value = json.loads(message['content'])
            value.pop('messages')
            message['content'] = json.dumps(value)
        elif kind == 'fenced_json':
            message['content'] = '```json\n' + message['content'] + '\n```'
        elif kind == 'missing_content':
            message.pop('content')
        elif kind == 'refusal':
            message['refusal'] = 'blocked'
        elif kind == 'tool_call':
            message['tool_calls'] = [{'type': 'function'}]
        elif kind == 'blocked_prompt':
            response['promptFeedback'] = {'blockReason': 'SAFETY'}
        elif kind == 'blocked_candidate':
            response['response'] = {'candidates': [{'safetyRatings': [{'blocked': True}]}]}
        elif kind == 'upstream_reason':
            choice['upstream_finish_reason'] = 'SAFETY'
        elif kind == 'candidate_reason':
            response['candidates'] = [{'finishReason': 'SAFETY'}]
        else:
            raise AssertionError(kind)
    return mutate


@pytest.mark.parametrize('condition', MAIN_CONDITIONS)
@pytest.mark.parametrize('kind', ['missing_reason', 'blank', 'truncated_json', 'missing_field',
                                'fenced_json', 'missing_content', 'refusal', 'tool_call',
                                'blocked_prompt', 'blocked_candidate', 'upstream_reason', 'candidate_reason'])
def test_proxy_stop_cannot_hide_visible_failure_signals(tmp_path, condition, kind):
    trial, budget = trial_for(tmp_path, condition, 'stop', corrupt(kind))
    result = trial.run_adapter()
    assert_record_chain(trial, budget, result, None if kind == 'missing_reason' else 'stop')


def test_client_preserves_finish_reason_usage_on_rejection_and_resets():
    bodies = iter([completion_body('text', usage=USAGE, finish_reason='length'),
                   completion_body('text', usage=USAGE, finish_reason='stop'), b'{broken'])
    client = GeminiProxyCompleter(http_open=lambda *a, **kw: io.BytesIO(next(bodies)),
                                  require_normal_completion=True)
    with pytest.raises(GeminiProxyError, match='finish_reason_not_stop'):
        client.complete([])
    assert client.last_finish_reason == 'length' and client.last_usage == USAGE
    assert client.complete([]) == 'text' and client.last_finish_reason == 'stop'
    with pytest.raises(GeminiProxyError):
        client.complete([])
    assert client.last_finish_reason is None and client.last_usage is None and client.last_completion is None


def test_transport_cannot_disable_stop_admission_with_client_flag(tmp_path):
    trial, budget = trial_for(tmp_path, 'peer_ko', 'length')
    factory = trial.transport.client_factory
    def unchecked_client(opener):
        client = factory(opener)
        client.require_normal_completion = False
        return client
    trial.transport.client_factory = unchecked_client
    result = trial.run_adapter()
    assert_record_chain(trial, budget, result, 'length')


@pytest.mark.parametrize('kind', ['response', 'settle', 'sqlite'])
def test_storage_error_keeps_observed_finish_reason_without_releasing_reply(tmp_path, monkeypatch, kind):
    from harness.zone_send_ledger import SendLedger
    trial, budget = trial_for(tmp_path, 'peer_ko', 'length')
    if kind == 'response':
        original = SendLedger._store
        def fail(row_self, row, stage, data):
            if stage == 'response':
                raise OSError('injected response fsync failure')
            return original(row_self, row, stage, data)
        monkeypatch.setattr(SendLedger, '_store', fail)
    else:
        def fail(*a, **kw):
            error = sqlite3.OperationalError if kind == 'sqlite' else OSError
            raise error('injected settlement failure')
        monkeypatch.setattr(budget, 'settle', fail)
    result = trial.run_adapter()
    assert not result['actions'] and not result['messages']
    assert result['calls'][0]['cost_terms']['completion']['finish_reason'] == 'length'
    assert trial.send_ledger.entries[0]['completion']['finish_reason'] == 'length'
    assert result['model_evaluation']['completion']['successful_calls'] == 0
    assert result['calls'][0]['output_tokens'] == trial.send_ledger.entries[0]['sim_generated']['output_tokens'] > 0
    saved = PilotBudget(budget.path).snapshot()
    assert saved['reserved_attempts'] == 2
    if kind == 'response':
        assert saved['sends'][0]['completion']['finish_reason'] == 'length'
    else:
        assert saved['sends'][0]['status'] == 'reserved_unknown'


def test_pipeline_failure_after_stop_preserves_reason_without_claiming_success(tmp_path, monkeypatch):
    trial, budget = trial_for(tmp_path, 'peer_ko', 'stop')
    def fail(*a, **kw):
        raise RuntimeError('injected protocol pipeline failure')
    monkeypatch.setattr(trial, 'finish_call', fail)
    result = trial.run_adapter()
    assert not result['actions'] and not result['messages']
    assert result['calls'][0]['cost_terms']['completion']['finish_reason'] == 'stop'
    assert result['model_evaluation']['completion']['successful_calls'] == 0
    assert result['calls'][0]['cost_terms']['provider_usage'] == USAGE
    assert budget.snapshot()['reserved_attempts'] == 2


def test_length_with_broken_usage_is_failed_and_unknown_not_dropped(tmp_path):
    trial, budget = trial_for(tmp_path, 'peer_ko', 'length', lambda response: response.update(usage=['broken']))
    result = trial.run_adapter()
    assert not result['actions'] and not result['messages']
    assert result['calls'][0]['cost_terms']['completion']['finish_reason'] == 'length'
    assert result['calls'][0]['cost_terms']['usage_known'] is False
    assert result['model_evaluation']['completion']['successful_calls'] == 0
    assert budget.snapshot()['reserved_attempts'] == 2


@pytest.mark.parametrize('condition', MAIN_CONDITIONS)
@pytest.mark.parametrize('timing', ['sim_horizon', 'wall_timeout'])
def test_discarded_late_response_preserves_reason_and_never_counts_success(tmp_path, monkeypatch, condition, timing):
    trial, budget = trial_for(tmp_path, condition, 'length')
    if timing == 'sim_horizon':
        trial.horizon_s = .001
    else:
        actual = trial.send_ledger._wire
        clock = [100.]
        def late(request, *, timeout=None):
            response = actual(request, timeout=timeout)
            clock[0] += timeout + 1
            return response
        monkeypatch.setattr(trial.send_ledger, '_wire', late)
        monkeypatch.setattr(pl.time, 'monotonic', lambda: clock[0])
    result = trial.run_adapter()
    assert not result['actions'] and not result['messages']
    assert result['calls'][0]['cost_terms']['completion']['finish_reason'] == 'length'
    assert budget.snapshot()['sends'][0]['completion']['finish_reason'] == 'length'
    assert result['model_evaluation']['completion']['successful_calls'] == 0
    assert budget.snapshot()['reserved_attempts'] == 2
    assert result['calls'][0]['output_tokens'] == trial.send_ledger.entries[0]['sim_generated']['output_tokens'] > 0


def test_legacy_and_forged_ok_never_become_successful_calls():
    length = assess_completion(json.loads(completion_body('valid', finish_reason='length')))
    assert completion_aggregate([{'status': 'ok', 'cost_terms': {'completion': length}}])['successful_calls'] == 0
    legacy = {'status': 'ok'}
    before = copy.deepcopy(legacy)
    aggregate = completion_aggregate([legacy])
    assert aggregate['successful_calls'] == 0 and aggregate['completion_unknown_calls'] == 1
    assert legacy == before


def run_mock_cli(tmp_path, monkeypatch, *, failing_condition=None):
    identity = {'source_head': 'offline-r9'}
    monkeypatch.setattr(runner, 'proxy_profile', lambda *a: PROFILE)
    monkeypatch.setattr(runner, 'source_identity', lambda *a: identity)
    monkeypatch.setattr(runner, 'runtime_identity', lambda *a: {'pid': 0, 'offline_injection': True})
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=''))
    actual = pl.PilotSendLedger
    def ledger(**kwargs):
        condition = kwargs['context']['condition']
        kwargs['wire'] = fixture_wire(condition, 'length' if condition == failing_condition else 'stop')
        return actual(**kwargs)
    monkeypatch.setattr(runner, 'PilotSendLedger', ledger)
    budget = PilotBudget.create(tmp_path / 'budget.sqlite', identity=identity)
    out = tmp_path / 'preflight'
    assert runner.main(['--execute', '--budget-file', str(budget.path), '--output', str(out)]) == 2
    return budget, json.loads((out / 'manifest.json').read_text())


@pytest.mark.parametrize('condition', MAIN_CONDITIONS)
def test_actual_cli_aggregation_stops_on_length_in_each_condition(tmp_path, monkeypatch, condition):
    budget, manifest = run_mock_cli(tmp_path, monkeypatch, failing_condition=condition)
    assert manifest['status'] == 'failed'
    row = manifest['trials'][-1]
    assert row['condition'] == condition and row['successful_calls'] == 0
    assert row['completion']['finish_reasons'] == {'length': 1}
    assert manifest['call_links'][-1]['completion']['finish_reason'] == 'length'
    assert manifest['completion_limitation'] == PROXY_COMPLETION_LIMITATION
    assert len(manifest['trials']) == list(MAIN_CONDITIONS).index(condition) + 1
    assert budget.snapshot()['reserved_attempts'] == 2 * len(manifest['trials'])


def test_preflight_gate_recomputes_completion_instead_of_trusting_success_count(tmp_path, monkeypatch):
    budget, manifest = run_mock_cli(tmp_path, monkeypatch)
    snapshot = budget.snapshot()
    # Isolate completion gating from the separate upstream billing gate.
    require_preflight(snapshot, {'complete': True}, manifest)
    path = Path(manifest['trials'][0]['trial_path'])
    trial = json.loads(path.read_text())
    trial['calls'][0]['cost_terms']['completion']['finish_reason'] = 'length'
    path.write_text(json.dumps(trial))
    # Even rebinding all file hashes with a claimed successful count cannot
    # turn status=ok / finish_reason=length into a completed preflight.
    manifest['trials'][0]['trial_sha256'] = sha(path.read_bytes())
    snapshot['runs'][0]['manifest_sha256'] = sha(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n')
    with pytest.raises(ValueError, match='successful stop'):
        require_preflight(snapshot, {'complete': True}, manifest)


def test_dry_manifest_declares_masked_safety_limitation(tmp_path):
    manifest = runner.dry_run(tmp_path, 'preflight', load(scenario_ids()[0]), 11, PROFILE)
    assert manifest['completion_policy'] == COMPLETION_POLICY
    assert manifest['completion_limitation'] == PROXY_COMPLETION_LIMITATION
    assert manifest['completion_limitation']['upstream_finish_reason_verified'] is False
    assert 'SAFETY' in manifest['completion_limitation']['proxy_mapping']
    assert manifest['network_calls'] == 0
