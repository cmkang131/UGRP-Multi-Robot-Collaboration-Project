"""Seventh review of PR 194, P1: the send ledger, the model-call adapter and the offline loop.

``test_zone_study_review_r7.py`` pins the scheduler's settlement rules with
scripted adapters; this file pins the pieces around them:

* :class:`harness.zone_send_ledger.SendLedger` itself (gate, counting, storage);
* :class:`harness.zone_study_llm_transport.ModelCallTransport` with the REAL
  ``GeminiProxyCompleter`` over an offline wire: every HTTP request of the real
  adapter path reaches the ledger, and HTTP errors, timeouts and malformed
  bodies are charged by it (no network: the wire is scripted, and ``urlopen``
  is patched to fail);
* the offline smoke loop, whose fixture replies now travel the same path; its
  SIM trace is unchanged against the committed v5 results.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import socket
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from harness import gemini_proxy
from harness import zone_event_scheduler as ds
from harness import zone_send_ledger as sl
from harness import zone_sim_cost as zc
from harness import zone_study_eval as ev
from harness import zone_study_llm_transport as lt
from harness import zone_study_offline as off
from harness.zone_study_contract import digest
from scripts import run_ci_tests

ROOT = Path(__file__).resolve().parents[1]
V5_RESULTS = ROOT / 'experiments' / '2026-09-26-zone-study-offline-smoke' / 'v5' / 'results.json'
IMAGE = 'data:image/jpeg;base64,' + base64.b64encode(b'\xff\xd8\xff\xe0 fixture').decode()


# =========================================================================== #
# SendLedger

class _Owner:
    def __init__(self, allow=True):
        self.allow, self.asked = allow, []

    def __call__(self, call_id):
        self.asked.append(call_id)
        return None if self.allow else 'http_budget'


def _ledger(wire=None, **kw):
    wire = wire or sl.ScriptedWire()
    ledger = sl.SendLedger(wire, **kw)
    owner = _Owner()
    ledger.attach(owner, owner=owner)
    return ledger, wire, owner


def test_r7_ledger_counts_a_request_before_the_wire_and_keeps_it_when_the_wire_fails():
    ledger, wire, owner = _ledger(sl.ScriptedWire([ConnectionResetError('reset after write'), b'{"ok":1}']))
    opener = ledger.opener_for('call-0001-r1', 'r1')
    with pytest.raises(ConnectionResetError):
        sl.send(opener, b'{"a":1}')
    assert sl.send(opener, b'{"a":2}') == b'{"ok":1}'
    assert ledger.sends('call-0001-r1') == 2 == len(wire.requests) and owner.asked == ['call-0001-r1'] * 2
    first, second = ledger.entries
    assert first['wire_error'] == 'ConnectionResetError' and 'response_sha256' not in first
    assert first['body_sha256'] == hashlib.sha256(b'{"a":1}').hexdigest() and first['bytes'] == 7
    assert second['response_sha256'] == hashlib.sha256(b'{"ok":1}').hexdigest()


def test_r7_ledger_blocks_a_refused_request_before_the_wire():
    wire = sl.ScriptedWire()
    ledger = sl.SendLedger(wire)
    ledger.attach(_Owner(allow=False), owner='test')
    with pytest.raises(sl.SendBlocked, match='http_budget') as info:
        sl.send(ledger.opener_for('call-0001-r1', 'r1'))
    assert not isinstance(info.value, OSError)           # the completer must not retry it
    assert wire.requests == [] and ledger.sends() == 0 and ledger.blocked() == 1
    unowned = sl.SendLedger(sl.ScriptedWire())
    with pytest.raises(sl.SendBlocked, match='no_owner'):
        sl.send(unowned.opener_for('call-0001-r1', 'r1'))


def test_r7_ledger_stores_every_send_and_never_overwrites(tmp_path):
    ledger, _, _ = _ledger(store_dir=tmp_path / 'wire')
    sl.send(ledger.opener_for('call-0001-r1', 'r1'), b'{"q":1}')
    stored = sorted(p.name for p in (tmp_path / 'wire').iterdir())
    assert stored == ['000001-call-0001-r1-request.json', '000001-call-0001-r1-response.json']
    assert (tmp_path / 'wire' / stored[0]).read_bytes() == b'{"q":1}'
    again, wire, _ = _ledger(store_dir=tmp_path / 'wire')          # a second run on the same directory
    with pytest.raises(FileExistsError):
        sl.send(again.opener_for('call-0001-r1', 'r1'), b'{"q":2}')
    assert wire.requests == [] and again.sends() == 0 and again.entries[0]['reason'] == 'store_failed'
    assert (tmp_path / 'wire' / stored[0]).read_bytes() == b'{"q":1}'


@pytest.mark.parametrize('body', [None, '{"text": 1}', 5, [b'x']])
def test_r7_ledger_boundary_a_request_without_a_byte_body_is_refused(body):
    ledger, wire, _ = _ledger()
    request = SimpleNamespace(data=body, full_url=sl.SCRIPTED_URL, get_method=lambda: 'POST')
    with pytest.raises(TypeError, match='bytes'):
        ledger.opener_for('call-0001-r1', 'r1')(request, timeout=1.0)
    assert ledger.entries == [] and wire.requests == []


@pytest.mark.parametrize('call_id', ['', None, 0, b'call'])
def test_r7_ledger_boundary_an_opener_needs_a_call_id(call_id):
    with pytest.raises(ValueError, match='call_id'):
        sl.SendLedger(sl.ScriptedWire()).opener_for(call_id, 'r1')


def test_r7_ledger_boundary_owner_wire_and_digest():
    with pytest.raises(TypeError, match='callable wire'):
        sl.SendLedger(None)
    ledger = sl.SendLedger(sl.ScriptedWire())
    with pytest.raises(TypeError, match='callable'):
        ledger.attach('not callable', owner='x')
    ledger.attach(_Owner(), owner='x')
    with pytest.raises(ValueError, match='owner'):
        ledger.attach(_Owner(), owner='y')
    twin, _, _ = _ledger()
    for target in (ledger, twin):
        sl.send(target.opener_for('call-0001-r1', 'r1'), b'{}')
    assert ledger.digest() == twin.digest() and 'entries' not in ledger.to_dict(entries=False)
    assert ledger.to_dict()['by_call'] == {'call-0001-r1': {'sent': 1, 'blocked': 0}}


# =========================================================================== #
# ModelCallTransport over the real GeminiProxyCompleter

class _Pipeline:
    """Builds a tiny labelled-image request; turns reply text into a CallReply."""

    def __init__(self, fail_prepare=None):
        self.fail_prepare, self.finished = fail_prepare, []

    def prepare_call(self, call):
        if self.fail_prepare is not None:
            raise self.fail_prepare
        user = json.dumps({'robot_id': call.actor, 'request_id': call.call_id})
        return SimpleNamespace(request={'messages': [{'role': 'system', 'content': '시스템 규칙'},
                                                     {'role': 'user', 'content': user}],
                                        'images': [{'label': 'WRIST RGB (own)', 'image': IMAGE}]})

    def finish_call(self, call, prepared, raw, *, provider_usage=None):
        self.finished.append((call.call_id, raw, provider_usage))
        return ds.CallReply(attempts=(zc.Attempt(input_tokens=100, output_tokens=20),), action=raw,
                            provider_usage=provider_usage)


@pytest.fixture
def no_network(monkeypatch):
    """The adapter path must never reach urllib's real opener or a socket."""
    def refuse(*args, **kwargs):
        raise AssertionError('network access in an offline test')

    monkeypatch.setattr(urllib.request, 'urlopen', refuse)
    monkeypatch.setattr(gemini_proxy, 'urlopen', refuse)
    monkeypatch.setattr(socket, 'create_connection', refuse)
    monkeypatch.setattr(socket.socket, 'connect', refuse)


def _adapter(responses, pipeline=None, **policy):
    wire = sl.ScriptedWire(responses)
    transport = lt.ModelCallTransport(pipeline or _Pipeline(), send_ledger=sl.SendLedger(wire),
                                      client_factory=lt.gemini_client_factory(
                                          model='gemini-3.8-flash', url='http://127.0.0.1:1/v1/chat/completions',
                                          max_tokens=1400, temperature=0.2))
    holds, actions = [], []
    policy.setdefault('max_calls_per_actor', 2)
    sched = ds.EventScheduler(transport, policy=ds.CallPolicy(**policy),
                              on_hold=lambda a, h, t: holds.append((h, t)),
                              on_action=lambda a, action, t: actions.append((action, t)))
    sched.trigger('r1', 'start')
    sched.run(until_s=120.0)
    return sched, wire, holds, actions


def test_r7_adapter_a_model_reply_is_one_ledgered_request_of_the_real_completer(no_network):
    usage = {'prompt_tokens': 812, 'completion_tokens': 95, 'total_tokens': 907}
    sched, wire, _, actions = _adapter([sl.completion_body('go', usage=usage)], max_calls_per_actor=1)
    assert [a for a, _ in actions] == ['go'] and len(wire.requests) == 1 == sched.send_ledger.sends()
    body = json.loads(wire.requests[0])
    assert body['model'] == 'gemini-3.8-flash' and body['max_tokens'] == 1400
    parts = body['messages'][1]['content']
    assert [p['type'] for p in parts] == ['text', 'text', 'image_url'] and parts[2]['image_url']['url'] == IMAGE
    assert sched.send_ledger.entries[0]['body_sha256'] == hashlib.sha256(wire.requests[0]).hexdigest()
    assert sched.calls[0].notes['provider_usage'] == usage and sched.send_violations == []


@pytest.mark.parametrize('failure, outcome', [
    (HTTPError('http://127.0.0.1:1', 500, 'upstream', None, None), 'error'),
    (socket.timeout('read timed out'), 'timeout'),
    (ConnectionRefusedError('proxy down'), 'error'),
])
def test_r7_adapter_a_wire_failure_is_charged_held_and_its_retry_is_a_new_request(no_network, failure,
                                                                                   outcome):
    sched, wire, holds, actions = _adapter([failure, sl.completion_body('go')])
    first, retry = sched.calls
    assert first.cost.outcome == outcome and first.notes['usage_known'] is False
    assert len(wire.requests) == 2 == sched.send_ledger.sends() == sched.budget.used['r1']
    # the failed call held the actor for its whole charged SIM cost and ran nothing
    assert holds[:2] == [(True, 0.0), (False, first.cost.sim_s)] and sched.discarded[0]['action'] is None
    assert actions == [('go', retry.finished_sim_s)] and retry.retry_of == first.call_id
    assert retry.trigger == ('timeout' if outcome == 'timeout' else 'retry')


def test_r7_adapter_a_malformed_body_is_a_charged_error(no_network):
    sched, wire, _, actions = _adapter([b'not json', b'{"choices": []}'], max_retries=1)
    assert [c.cost.outcome for c in sched.calls] == ['error', 'error'] and actions == []
    assert len(wire.requests) == 2 == sched.send_ledger.sends()


def test_r7_adapter_a_failure_before_the_request_is_refunded_and_sends_nothing(no_network):
    pipeline = _Pipeline(fail_prepare=ValueError('payload failed validation'))
    sched, wire, holds, actions = _adapter([], pipeline=pipeline)
    assert wire.requests == [] and sched.calls == [] and sched.budget.used['r1'] == 0
    assert sched.unsent_calls[0]['stage'] == 'reply' and holds[-1][0] is False and actions == []


def test_r7_adapter_boundary_the_completer_must_use_the_call_opener():
    factory = lt.gemini_client_factory(model='m', url='http://127.0.0.1:1', max_tokens=10, temperature=0.)
    for opener in (urllib.request.urlopen, None, lambda request, timeout=None: None):
        with pytest.raises(ValueError, match='send-ledger opener'):
            factory(opener)
    for url in (None, ''):
        with pytest.raises(ValueError, match='URL'):
            lt.gemini_client_factory(model='m', url=url, max_tokens=10, temperature=0.)
    with pytest.raises(TypeError, match='SendLedger'):
        lt.ModelCallTransport(_Pipeline(), send_ledger=object(), client_factory=factory)
    with pytest.raises(TypeError, match='prepare_call'):
        lt.ModelCallTransport(object(), send_ledger=sl.SendLedger(sl.ScriptedWire()), client_factory=factory)


def test_r7_adapter_the_live_ledger_wraps_urlopen_and_stores_on_disk(tmp_path):
    ledger = lt.live_send_ledger(store_dir=tmp_path / 'raw-wire')
    assert ledger._wire is urllib.request.urlopen and (tmp_path / 'raw-wire').is_dir()
    assert ledger.entries == []                                   # nothing was sent


def test_r7_fixture_wire_gives_the_fixture_exactly_the_text_on_the_wire():
    seen = []
    wire = sl.FixtureWire(lambda system, user: seen.append((system, user)) or '{"ok": true}')
    ledger = sl.SendLedger(wire)
    ledger.attach(_Owner(), owner='x')
    client = gemini_proxy.GeminiProxyCompleter(model='m', url=off.FIXTURE_URL,
                                               http_open=ledger.opener_for('call-0001-r1', 'r1'))
    text = client.complete([{'role': 'system', 'content': '규칙'}, {'role': 'user', 'content': '{"a": 1}'}],
                           images=[{'label': 'WRIST RGB (own)', 'image': IMAGE}])
    assert text == '{"ok": true}' and seen == [('규칙', '{"a": 1}')] and client.last_usage is None
    assert ledger.sends() == 1 == wire.requests


# =========================================================================== #
# The offline loop sends through the same path

def test_r7_offline_every_fixture_reply_is_a_ledgered_wire_request(no_network):
    trial, result = off.run_trial('s1_normal_mixed', 'peer_ko', 601)
    ledger = trial.send_ledger
    assert ledger.sends() == trial.wire.requests == sum(c['http_attempts'] for c in result.calls)
    assert ledger.sends() == trial.scheduler.budget.used_total() and ledger.blocked() == 0
    assert result.send_ledger['calls'] == {c['request_id']: c['http_attempts'] for c in result.calls}
    checks = off.cost_checks(trial, result)
    assert checks['ok'], checks['problems']
    assert trial.transport.submitted == trial.transport.resolved
    assert trial.provenance['execution_bundle_id'] == 'zone_study_offline_v3'
    assert trial.provenance['model_settings_sha256'] == digest(trial.client_factory.settings)


def test_r7_offline_the_fixture_input_is_the_archived_request_text():
    trial = off.OfflineTrial(off.load_scenario('s2_unmapped_blockage'), condition='leader_ko', seed=611,
                             horizon_s=40.0)
    seen, respond = [], trial.wire.respond
    trial.wire.respond = lambda system, user: seen.append((system, user)) or respond(system, user)
    result = trial.run()
    assert seen == [(row['system'], row['user']) for row in result.requests]


@pytest.mark.parametrize('condition', ['no_comm', 'peer_ko', 'leader_ko', 'structured', 'reference_R'])
def test_r7_offline_the_sim_trace_is_unchanged_against_v5(condition):
    """The ledger changes WHO counts the sends, not what the loop does."""
    v5 = {row['run_id']: row for row in json.loads(V5_RESULTS.read_text())['trials']}
    trial, result = off.run_trial('s1_normal_mixed', condition, 601)
    old = v5[result.run_id]
    assert digest(list(result.trace)) == old['trace_sha256']
    assert [r['input_sha256'] for r in result.requests] == old['request_input_sha256']
    assert len(result.calls) == old['calls'] == trial.send_ledger.sends()


def _record():
    trial, result = off.run_trial('s1_normal_mixed', 'no_comm', 601, horizon_s=30.0)
    return trial.trial_record(result)


def test_r7_offline_the_record_send_ledger_must_match_the_call_log():
    record = _record()
    assert ev.parse_trial(record)['send_ledger']['sent'] == sum(c['http_attempts'] for c in record['calls'])
    first = record['calls'][0]['request_id']
    for mutate, match in [
            (lambda r: r['send_ledger']['calls'].update({first: 2}), 'differ from the sends'),
            (lambda r: r['send_ledger'].update(sent=r['send_ledger']['sent'] + 1), 'sum of its per-call'),
            (lambda r: r['send_ledger']['calls'].pop(first), 'exactly the call log'),
            (lambda r: r['send_ledger']['calls'].update(req_extra=1), 'exactly the call log'),
            (lambda r: r['send_ledger'].pop('blocked'), 'exactly'),
            (lambda r: r['send_ledger'].update(extra=0), 'exactly'),
            (lambda r: r.update(send_ledger=[]), 'exactly')]:
        bad = json.loads(json.dumps(record))
        mutate(bad)
        with pytest.raises(ev.TrialError, match=match):
            ev.parse_trial(bad)


@pytest.mark.parametrize('value', [True, -1, 1.5, '1', None, math.nan, math.inf])
def test_r7_offline_boundary_a_corrupt_send_count_is_refused(value):
    record = json.loads(json.dumps(_record()))
    record['send_ledger']['calls'][record['calls'][0]['request_id']] = value
    with pytest.raises(ev.TrialError, match='send_ledger'):
        ev.parse_trial(record)
    record = json.loads(json.dumps(_record()))
    record['send_ledger']['blocked'] = value
    with pytest.raises(ev.TrialError, match='send_ledger'):
        ev.parse_trial(record)


def test_r7_all_files_of_this_round_are_collected_by_the_ci_patterns():
    collected = {path.relative_to(ROOT).as_posix()
                 for pattern in run_ci_tests.TEST_PATTERNS for path in ROOT.glob(pattern)}
    assert {'tests/test_zone_study_review_r7.py', 'tests/test_zone_study_review_r7_transport.py',
            'tests/test_zone_study_review_r7_contract.py'} <= collected
