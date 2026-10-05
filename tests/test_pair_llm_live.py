"""The live model path of the pair LLM layer, with ONLY the network replaced.

A ``LiveShapedWire`` stands where the loopback proxy stands: it receives the exact bytes ``GeminiProxyCompleter``
wrote and answers with a provider-shaped completion (usage, response model, finish reason) or an HTTP error. Every
other part is the real live chain: ``PairLiveLedger`` (a ``MainStudySendLedger``), the durable budget ledger, the
network fence, the health check, the study's retry rule. No socket is opened and no real model is called.
"""
import email.message
import hashlib
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from harness import pair_llm_contract as contract
from harness import pair_llm_live as live
from harness import pair_llm_plumbing as plumbing
from harness import zone_study_llm_driver as llm
from harness.pair_llm_stub import cooperative_model
from harness.zone_main_budget import MainStudyBudget
from harness.zone_send_ledger import completion_body
from tests.pair_llm_fakes import FakeBackend, offline_only, synthetic_cal  # noqa: F401

USAGE = {'prompt_tokens': 3100, 'completion_tokens': 70, 'total_tokens': 3170}
COHORT = 'pair-live-test'


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def http_error(code, body=b'', retry_after=None):
    headers = email.message.Message()
    if retry_after is not None:
        headers['Retry-After'] = str(retry_after)
    return HTTPError('http://127.0.0.1:8391/v1/chat/completions', code, 'error', headers, io.BytesIO(body))


class LiveShapedWire:
    """Where the proxy stands: ``faults[n]`` is raised for the n-th POST (0-based), else a provider-shaped reply."""

    def __init__(self, model=None, *, faults=None, usage=USAGE):
        self.model, self.faults, self.usage = model or cooperative_model(), dict(faults or {}), usage
        self.requests = []

    def __call__(self, request, *, timeout=None):
        index = len(self.requests)
        self.requests.append(bytes(request.data))
        if index in self.faults:
            fault = self.faults[index]
            raise fault() if callable(fault) else fault
        body = json.loads(request.data.decode('utf-8'))
        messages = body['messages']
        system = next(m['content'] for m in messages if m['role'] == 'system')
        user = messages[-1]['content']
        if isinstance(user, list):
            user = next(part['text'] for part in user if part.get('type') == 'text')
        return io.BytesIO(completion_body(self.model(system, user), usage=self.usage, model='gemini-3.8-flash-low'))


@pytest.fixture(autouse=True)
def no_disk_probe(monkeypatch):
    monkeypatch.setattr(llm, 'check_disk', lambda path, *, min_free_gib: 1)


def budget_for(tmp_path, *, cap=1100000, charge=12000):
    budget = MainStudyBudget.create(tmp_path / 'budget.sqlite')
    budget.register_cohort(COHORT, token_cap=cap, unknown_usage_charge_tokens=charge, prereg_sha256='p' * 64,
                           source={'test': True})
    return budget


def run_live(tmp_path, wire, *, condition='peer_nl', cap_s=12., budget=None, name='live', backend=FakeBackend):
    budget = budget or budget_for(tmp_path)
    from tests.pair_llm_admission_fakes import complete_rule, measured_no_comm, peer_receipt
    complete_rule(budget, COHORT)
    if condition == 'peer_nl':
        measured_no_comm(budget, COHORT)
    cal = synthetic_cal(tmp_path, f'cal-{name}')
    out_root = Path(tmp_path) / name
    out_root.mkdir()
    record, attempts = live.run_pair_live(
        out_root, condition=condition, seed=911, cap_s=cap_s, profile=contract.driver_profile(), budget=budget,
        cohort_id=COHORT, backend_factory=backend, calibration=cal['path'], calibration_sha=cal['sha256'],
        provider_factory=plumbing.blind_provider_factory, synthetic_calibration=True, source_sha='0' * 40, wire=wire,
        peer_measurement=peer_receipt() if condition == 'peer_nl' else None)
    return record, attempts, out_root / condition, budget


# --------------------------------------------------------------------------- a clean live-shaped run

@pytest.fixture(scope='module')
def clean(tmp_path_factory):
    tmp = tmp_path_factory.mktemp('live-clean')
    wire = LiveShapedWire()
    record, attempts, out, budget = run_live(tmp, wire)
    return record, attempts, out, budget, wire


def test_a_clean_run_records_every_post_with_tokens_latency_and_hashes(clean):
    record, attempts, out, budget, wire = clean
    assert record['status'] == 'COLLECTED_UNQUALIFIED' and record['failure_class'] is None
    assert record['model_kind'] == 'live' and attempts[0]['retried'] is False and len(attempts) == 1
    calls = rows(out / 'llm' / 'model_calls.jsonl')
    assert calls and len(calls) == len(wire.requests)
    for call in calls:
        assert call['status'] == 'sent' and call['usage_known'] is True and call['provider_usage'] == USAGE
        assert call['latency_ms'] is not None and call['response_model'] == 'gemini-3.8-flash-low'
        assert len(call['images']) == 2                                  # exactly the own frame and the map figure
        wire_dir = out / 'llm' / 'wire'
        request, response = (wire_dir / call['request_path']).read_bytes(), (wire_dir / call['response_path']).read_bytes()
        assert hashlib.sha256(request).hexdigest() == call['body_sha256']
        assert hashlib.sha256(response).hexdigest() == call['response_sha256']
        assert call['failure_class'] is None and call['completion']['finish_reason'] == 'stop'
    usage = record['metrics']['model_usage']
    assert usage['requests'] == len(calls) and usage['tokens_prompt'] == 3100 * len(calls)
    assert usage['tokens_completion'] == 70 * len(calls) and usage['tokens_complete'] is True
    assert usage['api_clean'] is True and usage['response_models'] == ['gemini-3.8-flash-low']
    assert record['metrics']['response_wall_s']['requests'] == len(calls)
    assert record['metrics']['failure_class'] is None


def test_the_budget_ledger_has_one_settled_row_per_post_and_matches_the_run_records(clean):
    record, _, out, budget, wire = clean
    requests = budget.requests('peer_nl-s911#a1')
    assert len(requests) == len(wire.requests) > 0
    assert all(r['status'] == 'response_received' and r['usage_known'] and r['total_tokens'] == 3170 for r in requests)
    assert budget.usage(COHORT)['known_tokens'] == 3170 * (len(requests) + 1)
    assert budget.usage(COHORT)['usage_unknown_requests'] == 0
    run = budget.run('peer_nl-s911#a1')
    assert run['status'] == 'finished' and run['model_requests'] == len(requests) and run['bundle_id'] == contract.BUNDLE_ID
    driver = json.loads((out / 'llm' / 'live_driver.json').read_text())
    assert driver['cohort_usage']['requests'] == len(requests) + 1 and driver['live'] is False   # the wire was replaced
    assert driver['budget_ledger_id'] == budget.meta['ledger_id'] and driver['cohort']['token_cap'] == 1100000
    assert driver['proxy_identity'] == {'profile': None, 'runtime': None} and driver['run_key'] == 'peer_nl-s911#a1'
    hashed = json.loads((out / 'artifacts.sha256.json').read_text())
    assert 'llm/live_driver.json' in hashed and 'llm/model_calls.jsonl' in hashed and 'bundle.json' in hashed


def test_the_live_bundle_records_the_retry_layers_the_rate_limit_rule_and_the_audited_proxy(clean):
    from harness.zone_pilot_budget import PROXY_SHA256
    bundle = json.loads((clean[2] / 'bundle.json').read_text())
    model = bundle['model']
    assert model['kind'] == 'live' and model['model'] == 'gemini-3.8-flash' and model['temperature'] == 0.2
    assert model['proxy_url'] == 'http://127.0.0.1:8391/v1/chat/completions' and model['seed'] is None
    assert model['audited_proxy_sha256'] == PROXY_SHA256 and model['min_request_interval_s'] == 2.0
    layers = model['retry_layers']
    assert layers['scheduler'].startswith('CallPolicy.max_retries=0')
    assert layers['run']['policy'] == 'once_in_place_only_if_host_error_before_first_model_request'
    assert layers['proxy_internal'] == {**layers['proxy_internal'], 'internal_429_retry': True,
                                        'upstream_attempts_per_post_bound': 2}
    assert 'RATE_LIMIT' in model['rate_limit_rule'] and 'nothing retries it' in model['rate_limit_rule']
    assert bundle['prompt']['template_sha256'] and bundle['condition'] == 'peer_nl'


def test_the_request_text_and_both_images_are_preserved_and_the_messages_were_delivered(clean):
    _, _, out, _, wire = clean
    archived = rows(out / 'llm' / 'requests.jsonl')
    assert archived and all(len(r['image_refs']) == 2 for r in archived)
    channel = json.loads((out / 'llm' / 'channel.json').read_text())
    assert channel['condition'] == 'peer_nl' and channel['accepted_messages'] > 0
    language = rows(out / 'llm' / 'language.jsonl')
    assert language and all(r['accepted'] for r in language)           # recorded, never a gate


# --------------------------------------------------------------------------- rate limit / quota

@pytest.mark.parametrize('status,body', [
    (429, b''),
    (429, b'{"error":{"message":"Too Many Requests"}}'),
    (403, b'{"error":{"status":"RESOURCE_EXHAUSTED","message":"Quota exceeded for this model"}}'),
    (503, b'quota exhausted, retry later')])
def test_a_rate_limit_or_quota_answer_stops_the_run_as_RATE_LIMIT_and_is_never_retried(tmp_path, status, body):
    wire = LiveShapedWire(faults={3: lambda: http_error(status, body, retry_after=7)})
    record, attempts, out, budget = run_live(tmp_path, wire)
    assert record['status'] == 'HOST_ERROR' and record['failure']['class'] == live.RATE_LIMIT
    assert record['failure_class'] == llm.API_ERROR                    # the study class of the same event
    assert record['protocol_complete'] is False and 'case_sim_s' not in record
    assert attempts == [{**attempts[0], 'attempt': 1, 'retried': False, 'failure_class': llm.API_ERROR}]
    assert not (out.parent / 'peer_nl-attempt2').exists()               # a 429 is never retried
    assert len(wire.requests) <= 3 + 2                                 # the request after the answer is at most the other robot's
    sent = [r for r in rows(out / 'llm' / 'model_calls.jsonl') if r['http_status'] == status]
    assert sent and sent[0]['rate_limit'] is True and sent[0]['failure_class'] == llm.API_ERROR
    answer = sent[0]['error_response']
    assert answer['http_status'] == status and answer['retry_after'] == '7' and answer['bytes'] == len(body)
    assert answer['sha256'] == hashlib.sha256(body).hexdigest()
    if body:
        stored = (out / 'llm' / 'wire' / answer['path']).read_bytes()
        assert stored == body
    assert 'RATE_LIMIT' in record['failure']['message'] or 'rate limit' in record['failure']['message']
    # the partial run keeps its records and the budget row is settled as a wire error
    assert (out / 'llm' / 'requests.jsonl').is_file() and (out / 'result.json').is_file()
    failed = [r for r in budget.requests() if r['status'] == 'wire_error']
    assert failed and failed[0]['http_status'] == status
    assert budget.run('peer_nl-s911#a1')['status'] == 'failed'


def test_an_ordinary_server_error_is_an_api_failure_but_does_not_stop_a_run_that_already_has_replies(tmp_path):
    wire = LiveShapedWire(faults={2: lambda: http_error(500, b'internal error')})
    record, attempts, out, _ = run_live(tmp_path, wire)
    assert record['status'] == 'COLLECTED_UNQUALIFIED' and record['protocol_complete'] is True
    assert record['failure_class'] == llm.API_ERROR                    # the study rule: any API error invalidates
    assert record['metrics']['model_usage']['api_clean'] is False
    assert record['metrics']['model_usage']['failure_classes'] == {llm.API_ERROR: 1}
    assert attempts[0]['retried'] is False and len(wire.requests) > 3
    calls = rows(out / 'llm' / 'model_calls.jsonl')
    assert calls[2]['http_status'] == 500
    assert any(r['failure_class'] is None and r['status'] == 'sent' for r in calls[3:])
    bad = [r for r in rows(out / 'llm' / 'model_calls.jsonl') if r['http_status'] == 500]
    assert bad and bad[0]['rate_limit'] is False and bad[0]['error_response']['bytes'] == len(b'internal error')


def test_a_run_whose_every_reply_failed_is_an_api_failure(tmp_path):
    wire = LiveShapedWire(faults={i: (lambda: http_error(500, b'x')) for i in range(30)})
    record, _, _, _ = run_live(tmp_path, wire)
    assert record['status'] == 'HOST_ERROR' and record['failure_class'] == llm.API_ERROR
    assert record['failure']['class'] != live.RATE_LIMIT


def test_the_cohort_token_cap_stops_the_run_before_the_next_request(tmp_path):
    budget = budget_for(tmp_path)
    # Keep the registered 1.1M cap; only 3000 tokens remain before this case.
    budget.start_run('prior', cohort_id=COHORT, bundle_id=contract.BUNDLE_ID, bundle_sha256='0'*64, record={})
    row = budget.record_request('prior', {})
    budget.settle_request(row['id'], status='response_received',
                          provider_usage={'prompt_tokens': 1097000, 'completion_tokens': 0, 'total_tokens': 1097000})
    budget.finish_run('prior', status='finished')
    wire = LiveShapedWire()
    record, _, out, _ = run_live(tmp_path, wire, budget=budget, condition='no_comm')
    assert record['status'] == 'HOST_ERROR' and record['failure_class'] == llm.API_ERROR
    assert 'cap' in record['failure']['message'].lower()
    assert len(wire.requests) <= 2
    capped = [r for r in rows(out / 'llm' / 'model_calls.jsonl') if r['status'] == 'blocked']
    assert capped or record['failure']['type'] == 'BudgetExceeded'


# --------------------------------------------------------------------------- the study retry rule

def test_a_host_error_before_the_first_request_is_retried_once_in_place_and_only_then(tmp_path, monkeypatch):
    calls = []
    real = live.live_adapter

    def flaky(*args, **kwargs):
        calls.append(kwargs['run_key'])
        if len(calls) == 1:
            raise llm.HostError('proxy preflight failed: not listening')
        return real(*args, **kwargs)

    monkeypatch.setattr(live, 'live_adapter', flaky)
    record, attempts, out, budget = run_live(tmp_path, LiveShapedWire())
    assert [a['attempt'] for a in attempts] == [1, 2] and attempts[0]['retried'] is True
    assert attempts[0]['failure_class'] == llm.HOST_ERROR and attempts[0]['model_requests'] == 0
    assert attempts[1]['failure_class'] is None and attempts[1]['retried'] is False
    assert (out.parent / 'peer_nl-attempt2').is_dir() and out.is_dir()    # attempt 1 is kept, never overwritten
    assert record['failure_class'] is None and calls == ['peer_nl-s911#a1', 'peer_nl-s911#a2']
    assert budget.run('peer_nl-s911#a1')['failure_class'] == llm.HOST_ERROR
    saved = json.loads((out.parent / 'attempts.json').read_text())
    assert saved['retry_policy'] == 'once_in_place_only_if_host_error_before_first_model_request'


def test_a_host_error_is_not_retried_a_second_time(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise llm.HostError('proxy preflight failed: not listening')

    monkeypatch.setattr(live, 'live_adapter', broken)
    record, attempts, out, _ = run_live(tmp_path, LiveShapedWire())
    assert len(attempts) == 2 and [a['retried'] for a in attempts] == [True, False]
    assert record['failure_class'] == llm.HOST_ERROR and record['status'] == 'HOST_ERROR'


def test_the_live_path_refuses_the_rule_arm_and_a_long_case(tmp_path):
    cal = synthetic_cal(tmp_path)
    common = dict(seed=911, profile=contract.driver_profile(), budget=budget_for(tmp_path), cohort_id=COHORT,
                  backend_factory=FakeBackend, calibration=cal['path'], calibration_sha=cal['sha256'], wire=LiveShapedWire())
    with pytest.raises(ValueError, match='no model call'):
        live.run_pair_live(tmp_path / 'a', condition='rule', cap_s=12., **common)
    with pytest.raises(ValueError, match='capped at 900'):
        live.run_pair_live(tmp_path / 'b', condition='peer_nl', cap_s=901., **common)


# --------------------------------------------------------------------------- the ledger and the CLI

def test_the_ledger_keeps_the_error_body_hash_and_retry_after_even_without_a_body(tmp_path):
    budget = budget_for(tmp_path)
    budget.start_run('r#a1', cohort_id=COHORT, bundle_id='b', bundle_sha256='0' * 64, record={})
    from urllib.request import Request
    ledger = live.PairLiveLedger(store_dir=tmp_path / 'wire', budget=budget, run_key='r#a1',
                                 profile=contract.driver_profile(),
                                 wire=LiveShapedWire(faults={0: http_error(429, b'', retry_after=3)}))
    ledger.attach(lambda call_id: None, owner=type('Owner', (), {'policy': type('P', (), {'max_retries': 0})()})())
    request = Request('http://127.0.0.1:8391/v1/chat/completions', data=b'{"messages": []}', method='POST')
    with pytest.raises(HTTPError):
        ledger._send('c1', 'r1', request, 5.)
    row = ledger.entries[0]
    assert row['http_status'] == 429 and row['rate_limit'] is True and row['failure_class'] == llm.API_ERROR
    assert row['error_response'] == {'http_status': 429, 'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest(),
                                     'excerpt': '', 'retry_after': '3'}
    assert live.rate_limited_rows(ledger) == [row]


@pytest.mark.parametrize('status,text,expected', [
    (429, '', True), (429, 'anything', True), (403, 'Quota exceeded', True), (500, 'RESOURCE_EXHAUSTED', True),
    (500, 'internal error', False), (200, 'quota', False), (None, 'quota', False), (404, 'not found', False)])
def test_is_rate_limit(status, text, expected):
    assert live.is_rate_limit(status, text) is expected


def test_cli_live_refusals_need_no_network_or_filesystem(capsys):
    from scripts import run_pair_llm as cli
    base = ['--condition', 'peer_nl', '--expected-source-sha', 'a' * 40, '--output',
            '/Users/changmin/projects/ugrp/outputs/never-created', '--synthetic-plumbing-calibration', '--live', '--cap-s', '60']
    with pytest.raises(ValueError, match='LLM condition'):
        cli.main(['--condition', 'rule', *base[2:]])
    with pytest.raises(ValueError, match='capped at 900'):
        cli.main(base + ['--cap-s', '901'])
    assert cli.main(base) == 0                       # a plan only
    assert json.loads(capsys.readouterr().out)['model_kind'] == 'live'
    with pytest.raises(ValueError, match='needs --proxy-pid, --budget-db, --cohort-id, --cohort-token-cap'):
        cli.main(base + ['--execute'])
    full = ['--proxy-pid', '1', '--cohort-id', 'c', '--cohort-token-cap', '1100000']
    with pytest.raises(ValueError, match='absolute path'):
        cli.main(base + ['--execute', '--budget-db', 'relative.sqlite', *full])
    with pytest.raises(ValueError, match='positive int'):
        cli.main(base + ['--execute', '--budget-db', '/x/b.sqlite', '--proxy-pid', '1', '--cohort-id', 'c',
                         '--cohort-token-cap', '0'])
    assert not Path('/Users/changmin/projects/ugrp/outputs/never-created').exists()


def test_the_live_modules_never_import_the_evaluator_or_a_simulator():
    import re
    source = (contract.ROOT / 'harness' / 'pair_llm_live.py').read_text()
    assert not re.search(r'pair_llm_eval|mujoco|import sim|from sim', source)


# --------------------------------------------------------------------------- reply format: fences are counted, not failed

def fenced(model, how):
    """A model whose valid JSON reply is wrapped the way real models do (the wire sees the wrapped text)."""
    def wrap(system, user):
        text = model(system, user)
        return {'fence': f'```json\n{text}\n```', 'bare_fence': f'```\n{text}\n```',
                'prose': f'다음은 결정입니다.\n```json\n{text}\n```', 'oneline': f'```json {text}```',
                'plain': text}[how]
    return wrap


def format_run(tmp_path, how):
    record, _, out, _ = run_live(tmp_path, LiveShapedWire(fenced(cooperative_model(), how)), name=f'fmt-{how}')
    return record, out


def test_a_whole_reply_fence_is_stripped_once_and_counted_and_the_run_is_not_failed(tmp_path):
    record, out = format_run(tmp_path, 'fence')
    fmt = record['metrics']['reply_format']
    assert fmt['schema'] == live.REPLY_FORMAT_VERSION and fmt['replies'] > 0
    assert fmt['fence_removed_calls'] == fmt['fenced_calls'] == fmt['replies'] and fmt['plain_json_calls'] == 0
    assert fmt['fence_not_removed_calls'] == 0 and fmt['fence_marker_lines_total'] == 2 * fmt['replies']
    assert record['status'] == 'COLLECTED_UNQUALIFIED' and record['failure_class'] is None
    by_status = record['metrics']['model_calls_by_status']                            # every fenced reply was accepted
    assert set(by_status) <= {'ok', 'censored'} and sum(by_status.values()) == fmt['replies']
    assert record['metrics']['model_usage']['api_clean'] is True


def test_a_bare_triple_backtick_fence_is_also_one_removed_fence(tmp_path):
    fmt = format_run(tmp_path, 'bare_fence')[0]['metrics']['reply_format']
    assert fmt['fence_removed_calls'] == fmt['replies'] > 0 and fmt['fence_not_removed_calls'] == 0


def test_a_plain_json_reply_counts_no_fence(tmp_path):
    fmt = format_run(tmp_path, 'plain')[0]['metrics']['reply_format']
    assert fmt['replies'] > 0 and fmt['plain_json_calls'] == fmt['replies']
    assert fmt['fenced_calls'] == fmt['fence_removed_calls'] == fmt['fence_marker_lines_total'] == 0


def first_r1_call_wrapped(model, how):
    """Only robot r1's FIRST reply is wrapped the way ``how`` says; every other reply is plain JSON."""
    seen = []

    def wrap(system, user):
        text = model(system, user)
        if json.loads(user)['robot_id'] != 'r1' or seen:
            return text
        seen.append(1)
        return fenced(lambda *_: text, how)(system, user)
    return wrap


@pytest.mark.parametrize('how', ['prose', 'oneline'])
def test_a_fence_the_study_cannot_unwrap_is_counted_as_not_removed_and_does_not_fail_a_run_that_has_replies(
        tmp_path, how):
    """The sealed study strips ONE fence that wraps the whole reply on its own lines and nothing else: a fence
    with prose around it (or on one line) is not unwrapped and that reply is rejected by the study as non-JSON
    (``model_output_rejected``). The metric makes it visible; the parser is not loosened and a run that also has
    normal replies is not failed."""
    record, _, out, _ = run_live(tmp_path, LiveShapedWire(first_r1_call_wrapped(cooperative_model(), how)),
                                 name=f'mixed-{how}', cap_s=30.)
    fmt = record['metrics']['reply_format']
    assert fmt['fenced_calls'] == fmt['fence_not_removed_calls'] == 1 and fmt['fence_removed_calls'] == 0
    assert fmt['plain_json_calls'] == fmt['replies'] - 1 > 0
    assert record['failure_class'] is None and record['status'] == 'COLLECTED_UNQUALIFIED'
    rejected = [c for c in rows(out / 'llm' / 'model_calls.jsonl') if c['failure_class'] == 'model_output_rejected']
    assert len(rejected) == 1 and rejected[0]['completion']['json_fence_removed'] is False
    assert rejected[0]['completion']['rejection_reasons'] == ['study_reply_incomplete_or_non_json']
    assert record['metrics']['model_calls_by_status']['ok'] > 0


def test_when_every_reply_is_an_unwrappable_fence_the_studys_zero_normal_reply_rule_stops_the_run(tmp_path):
    """Not a fence rule: the sealed study stops any run with no normal model reply at all (class infra:API). The
    fence metric is still written, so the cause is visible in the record."""
    record, out = format_run(tmp_path, 'prose')
    fmt = record['metrics']['reply_format']
    assert fmt['fence_not_removed_calls'] == fmt['replies'] > 0 and fmt['fence_removed_calls'] == 0
    assert record['failure_class'] == 'infra:API' and record['failure']['message'] == 'no successful model response'
