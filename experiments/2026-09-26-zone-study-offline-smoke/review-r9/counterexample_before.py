"""R9: truncated generations must never become study actions, even valid JSON."""
import io
import json
import socket

import pytest

from harness.zone_pilot_budget import PilotBudget, PROXY_SHA256
from harness.zone_send_ledger import completion_body
from harness.zone_study_contract import MAIN_CONDITIONS
from harness.zone_study_offline import FixtureActor
from harness.zone_study_scenarios import load, scenario_ids
from scripts.run_zone_study_pilot import AdapterTrial

USAGE = {'prompt_tokens': 150, 'completion_tokens': 80, 'total_tokens': 240}
PROFILE = {'source_sha256': PROXY_SHA256, 'source_path': '/not-executed',
           'url': 'http://127.0.0.1:8391/v1/chat/completions'}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('R9 is offline only')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket.socket, 'connect_ex', refuse)


def trial_for(tmp_path, condition, reason='length', mutate=None):
    budget = PilotBudget.create(tmp_path / 'budget.sqlite', identity={'source_head': 'offline-r9'})
    fixture = FixtureActor('r1', condition, 11)
    def wire(request, *, timeout=None):
        body = json.loads(request.data)
        messages = body['messages']
        user = next(p['text'] for p in messages[-1]['content'] if p['type'] == 'text')
        raw = fixture.respond({'messages': [messages[0], {'role': 'user', 'content': user}]})
        response = json.loads(completion_body(raw, usage=USAGE))
        response['choices'][0]['finish_reason'] = reason
        response['id'] = 'r9-proxy-response'
        if mutate:
            mutate(response)
        return io.BytesIO(json.dumps(response).encode())
    trial = AdapterTrial(load(scenario_ids()[0]), condition=condition, seed=11, stage='preflight',
                         run_id='r9-' + condition, budget=budget, profile=PROFILE, runtime=None,
                         output=tmp_path / 'run' / condition, wire=wire)
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
