"""Recorded R10 response replay; no model calls, network or physics."""
import hashlib
import json
from pathlib import Path
import socket

import pytest

from harness.llm_completion import assess_completion, completion_aggregate
from harness.three_robot_plan import parse
from harness.zone_study_contract import MAIN_CONDITIONS
from test_zone_study_review_r9 import assert_record_chain, corrupt, trial_for
import test_zone_study_review_r9 as r9

FIXTURE = Path(__file__).parent / 'fixtures/zone_study_preflight_r10'
RAW = (FIXTURE / 'response.json').read_bytes()
RESPONSE = json.loads(RAW)
TEXT = RESPONSE['choices'][0]['message']['content']
PLAIN = TEXT.removeprefix('```json\n').removesuffix('\n```')


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('recorded replay must never contact a model')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket.socket, 'connect_ex', refuse)


def test_original_response_fixture_proves_old_json_gate_failure():
    provenance = json.loads((FIXTURE / 'provenance.json').read_text())
    assert hashlib.sha256(RAW).hexdigest() == provenance['sha256']
    assert len(RAW) == provenance['bytes'] == 568
    with pytest.raises(json.JSONDecodeError):
        json.loads(TEXT)  # exact pre-fix admission operation
    assert parse(TEXT)['request_id'] == 'req_call_0001_r1'


@pytest.mark.parametrize('condition', MAIN_CONDITIONS)
def test_recorded_fenced_response_passes_all_four_adapter_conditions(tmp_path, condition):
    # Replay exact response bytes; the scheduler's original request_id matches.
    def recorded(response):
        response.clear()
        response.update(json.loads(RAW))
    trial, budget = trial_for(tmp_path, condition, 'stop', recorded)
    result = trial.run_adapter()
    call = result['calls'][0]
    assert call['status'] == 'ok'
    assert result['actions'] and not result['messages']
    completion = call['cost_terms']['completion']
    assert completion['json_fence_removed'] is True
    assert completion['upstream_finish_verified'] is False
    assert next(iter(result['scheduler_ledger'].values()))['completion'] == completion
    assert result['request_archive'][0]['completion'] == completion
    sent = budget.snapshot()['sends'][0]
    assert sent['completion'] == sent['ledger']['completion'] == completion
    assert sent['provider_usage'] == RESPONSE['usage']
    assert budget.snapshot()['reserved_attempts'] == 2
    assert result['model_evaluation']['completion']['json_fence_removed_calls'] == 1
    assert call['output_tokens'] == trial.sim_output_tokens(TEXT, 0)
    stored = trial.send_ledger.store_dir / sent['ledger']['response_path']
    assert stored.read_bytes() == RAW


@pytest.mark.parametrize('condition', MAIN_CONDITIONS)
@pytest.mark.parametrize('reason', ['stop', 'length'])
def test_fenced_channel_messages_keep_original_costs_and_stop_gate(tmp_path, condition, reason):
    trial, budget = trial_for(tmp_path, condition, reason, corrupt('fenced_json'))
    result = trial.run_adapter()
    assert_record_chain(trial, budget, result, reason, accepted=reason == 'stop')
    assert result['calls'][0]['cost_terms']['completion']['json_fence_removed'] is True
    assert bool(result['messages']) == (reason == 'stop' and condition != 'no_comm')
    assert result['model_evaluation']['completion']['json_fence_removed_calls'] == 1


@pytest.mark.parametrize('opening', ['```json', '```'])
@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_exact_single_fence_and_outer_whitespace(opening, newline):
    response = json.loads(RAW)
    response['choices'][0]['message']['content'] = ' \t\n' + opening + newline + PLAIN + newline + '```\n\t '
    completion = assess_completion(response, study_json=True)
    assert completion['normal_completion'] and completion['json_fence_removed']


BAD_TEXTS = [
    'Here is the JSON:\n' + TEXT, TEXT + '\nDone.',
    TEXT + '\n' + TEXT, '```json\n' + TEXT + '\n```',
    TEXT[:-3], TEXT.removeprefix('```json\n'),
    '```json\n' + PLAIN[:-1] + '\n```',
    '```json\n' + PLAIN + '\n' + PLAIN + '\n```',
    '```python\n' + PLAIN + '\n```', '```JSON\n' + PLAIN + '\n```',
    '````json\n' + PLAIN + '\n````', '```json ' + PLAIN + '```',
    '```json\n[]\n```', '```\nnull\n```',
]


@pytest.mark.parametrize('condition', MAIN_CONDITIONS)
@pytest.mark.parametrize('text', BAD_TEXTS)
def test_fence_counterexamples_remain_rejected_and_billed(tmp_path, condition, text):
    def corrupt(response):
        response['choices'][0]['message']['content'] = text
    trial, budget = trial_for(tmp_path, condition, 'stop', corrupt)
    result = trial.run_adapter()
    assert result['calls'][0]['status'] != 'ok'
    assert not result['actions'] and not result['messages']
    assert budget.snapshot()['reserved_attempts'] == 2
    assert completion_aggregate(result['calls'])['successful_calls'] == 0


def test_plain_reply_reports_no_fence_and_legacy_is_unknown():
    response = json.loads(RAW)
    response['choices'][0]['message']['content'] = PLAIN
    completion = assess_completion(response, study_json=True)
    assert completion['normal_completion'] and completion['json_fence_removed'] is False
    aggregate = completion_aggregate([
        {'status': 'ok', 'cost_terms': {'completion': completion}}, {'status': 'ok'}])
    assert aggregate['json_fence_removed_calls'] == 0
    assert aggregate['json_fence_unknown_calls'] == 1


def test_pilot_manifest_counts_fences_per_condition_and_in_total(tmp_path, monkeypatch, capsys):
    wire = r9.fixture_wire
    monkeypatch.setattr(r9, 'fixture_wire', lambda condition, reason: wire(condition, reason, corrupt('fenced_json')))
    budget, manifest = r9.run_mock_cli(tmp_path, monkeypatch)
    assert json.loads(capsys.readouterr().out)['json_fence_removed_calls'] == 4
    assert manifest['json_fence_removed_calls'] == 4
    assert [row['json_fence_removed_calls'] for row in manifest['trials']] == [1] * 4
    assert all(sent['completion']['json_fence_removed'] for sent in budget.snapshot()['sends'])
