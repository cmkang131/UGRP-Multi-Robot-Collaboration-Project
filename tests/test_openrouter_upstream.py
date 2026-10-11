import json
import hashlib
import pytest

from harness.s4_relay_journal import Journal
from scripts import openrouter_upstream as orp

REQ = {'model': 'gemma-4-31b-it', 'temperature': .2, 'max_tokens': 800, 'reasoning_effort': 'none',
       'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}]}
RAW = json.dumps(REQ).encode()
OK = {'id': 'x', 'model': 'google/gemma-4-31b-it', 'provider': 'DeepInfra',
      'choices': [{'message': {'role': 'assistant', 'content': '{}'}}],
      'usage': {'prompt_tokens': 1586, 'completion_tokens': 40, 'cost': 0.000125}}


def engine(tmp_path, replies, **kw):
    calls = []
    def send(payload, key):
        calls.append((payload, key))
        status, body = replies[min(len(calls) - 1, len(replies) - 1)]
        return status, json.dumps(body).encode(), None
    return orp.OpenRouter(tmp_path, key='SECRET', send=send, sleep=lambda s: None, **kw), calls


def test_request_shape_and_pinning(tmp_path):
    e, calls = engine(tmp_path, [(200, OK)])
    status, raw, _ = e.complete(RAW, 'cid')
    payload = calls[0][0]
    assert status == 200
    assert payload['model'] == 'google/gemma-4-31b-it' and not payload['model'].endswith(':free')
    assert 'reasoning_effort' not in payload
    assert payload['usage'] == {'include': True}
    assert payload['provider'] == {'order': ['DeepInfra'], 'allow_fallbacks': False}
    assert payload['messages'] == REQ['messages'] and payload['max_tokens'] == 800
    assert 'SECRET' not in json.dumps(payload)


def test_provider_list_is_config(tmp_path):
    e, calls = engine(tmp_path, [(200, {**OK, 'provider': 'Other'})], provider_order=('Other',))
    e.complete(RAW, 'cid')
    assert calls[0][0]['provider']['order'] == ['Other']
    assert orp.config(('A', 'B'))['provider_order'] == ['A', 'B']


def test_receipt_fields_and_ledger(tmp_path):
    e, _ = engine(tmp_path, [(200, OK)])
    status, raw, _ = e.complete(RAW, 'cid')
    r = json.loads(raw)['ugrp_openrouter']
    assert (r['provider_returned'], r['prompt_tokens'], r['completion_tokens'], r['cost'],
            r['http_status'], r['retries']) == ('DeepInfra', 1586, 40, 0.000125, 200, 0)
    assert r['latency_s'] >= 0 and json.loads(raw)['upstream'] == 'openrouter_v1'
    row = json.loads((tmp_path / 'ledger.jsonl').read_text())
    assert row['upstream'] == 'openrouter_v1' and row['openrouter']['cost'] == 0.000125
    assert 'SECRET' not in (tmp_path / 'ledger.jsonl').read_text()


def test_retry_then_success(tmp_path):
    e, calls = engine(tmp_path, [(503, {'error': 'x'}), (429, {'error': 'y'}), (200, OK)])
    status, raw, _ = e.complete(RAW, 'cid')
    assert status == 200 and len(calls) == 3
    assert json.loads(raw)['ugrp_openrouter']['retries'] == 2


def test_repeated_failure_is_host_error_and_not_cached(tmp_path):
    e, calls = engine(tmp_path, [(503, {'error': 'x'})] * 3 + [(200, OK)])
    key = hashlib.sha256(b'k').hexdigest()
    status, raw, _ = e.complete(RAW, 'cid', idempotency_key=key)
    assert status == 503 and len(calls) == 3 and json.loads(raw)['host_error'] is True
    assert 'choices' not in json.loads(raw)
    assert not (tmp_path / 'responses' / (key + '.json')).exists()
    status, raw, _ = e.complete(RAW, 'cid', idempotency_key=key)  # client retry re-forwards
    assert status == 200 and len(calls) == 4
    status, _, _ = e.complete(RAW, 'cid', idempotency_key=key)    # success is cached
    assert status == 200 and len(calls) == 4


def test_unpinned_provider_rejected(tmp_path):
    e, _ = engine(tmp_path, [(200, {**OK, 'provider': 'Elsewhere'})])
    status, raw, _ = e.complete(RAW, 'cid')
    assert status == 502 and 'choices' not in json.loads(raw)


def test_bad_request_not_forwarded(tmp_path):
    e, calls = engine(tmp_path, [(200, OK)])
    status, _, _ = e.complete(json.dumps({**REQ, 'model': 'other'}).encode(), 'cid')
    assert status == 400 and not calls


def test_journal_default_still_caches_errors(tmp_path):
    j = Journal(tmp_path)
    key = hashlib.sha256(b'a').hexdigest()
    n = []
    def fwd():
        n.append(1); return 503, b'{}', None
    j.call(key, b'b', fwd); j.call(key, b'b', fwd)
    assert len(n) == 1


def test_remote_receipt_accepts_only_pinned_openrouter_identity():
    from pathlib import Path
    from harness.s4_live_transport import validate_receipt
    from harness.zone_study_llm_driver import HostError
    sha=hashlib.sha256(Path(orp.__file__).read_bytes()).hexdigest()
    r=dict(schema='ugrp.s4_ssh_proxy.v1',remote_url='http://127.0.0.1:18393/v1/chat/completions',
        proxy=dict(source_sha256=sha),driver_profile='study_gemma4_31b_v1',single_model=True,
        fallback_enabled=False,upstream='openrouter_v1',openrouter_v1=dict(orp.config(),source_sha256=sha),
        checked_unix=100,valid_for_s=3600,audit_per_post=True,
        authentication='existing_mac_proxy_no_credentials_transferred')
    assert validate_receipt(r,now=101,remote_url=r['remote_url'])==r
    for field,value in [('allow_fallbacks',True),('provider_order',['Other']),('source_sha256','0'*64)]:
        bad={**r,'openrouter_v1':{**r['openrouter_v1'],field:value}}
        with pytest.raises(HostError):validate_receipt(bad,now=101,remote_url=r['remote_url'])
