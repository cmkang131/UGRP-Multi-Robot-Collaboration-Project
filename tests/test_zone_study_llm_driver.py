"""B7 real multi-turn model driver (PR #254): fake model wire only.

No model call, socket, MuJoCo import or physical step. The client is the
registered GeminiProxyCompleter; only its wire is a local function.
"""
import base64
from collections import Counter
import copy
import errno
import hashlib
import io
import json
from pathlib import Path
import socket
import sqlite3
import sys
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from harness import zone_study_integration as zi
from harness import zone_study_llm_driver as llm
from harness.zone_main_budget import BudgetExceeded, MainStudyBudget
from harness.zone_send_ledger import SendLedger, completion_body
from harness.zone_study_decisions import DecisionLimits
from harness.zone_study_contract import ContractViolation
from tests import test_zone_study_multiturn as tm
from tests.test_zone_study_integration import BUNDLE, SCENARIO, links_for
from scripts import run_zone_study_integration as runner

USAGE = {'prompt_tokens': 500, 'completion_tokens': 100, 'total_tokens': 600}
PROFILE = llm.driver_profile('main_study_gemini_v1')
GOLDEN = json.loads((Path(__file__).parent / 'fixtures/zone_study_multiturn/v64_wait_90s.json').read_text())


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    monkeypatch.setitem(sys.modules, 'mujoco', None)

    def refuse(*args, **kwargs):
        pytest.fail('network forbidden in the LLM driver tests')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket.socket, 'connect_ex', refuse)
    monkeypatch.setattr(socket, 'create_connection', refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
    monkeypatch.setattr(llm, 'check_disk', lambda path, *, min_free_gib: 1)


def budget_for(tmp_path, *, cap=None, charge=0, cohort='pilot-A'):
    budget = MainStudyBudget.create(tmp_path / 'main_budget.sqlite')
    budget.register_cohort(cohort, token_cap=cap, unknown_usage_charge_tokens=charge,
                           prereg_sha256='p' * 64, source={'test': True})
    return budget


class FakeModel:
    """Fake model wire: r3 talks on every turn (channel conditions), everyone claims order-1."""

    def __init__(self, condition, *, fault=None):
        self.condition, self.fault, self.bodies = condition, fault, []

    def __call__(self, request, *, timeout=None):
        body = json.loads(request.data)
        self.bodies.append(body)
        payload = json.loads(next(p['text'] for p in body['messages'][-1]['content'] if p['type'] == 'text'))
        if self.fault:
            self.fault(payload, len(self.bodies))
        messages = []
        if payload['robot_id'] == 'r3' and self.condition != 'no_comm':
            for peer in ('r1', 'r2'):
                message = {'recipients': [peer], 'reply_to': None}
                if self.condition == 'structured':
                    message['message'] = {'act': 'propose', 'item': 'order-2', 'zone': 'B', 'role': 'west',
                                          'passage': None, 'location_ref': None, 'state': 'unknown',
                                          'confidence': 'low', 'observed_at_sim_s': payload['sim_time_s'],
                                          'reply_to': None}
                else:
                    message['text'] = f'{peer}은 order-2를 맡아 주세요.'
                messages.append(message)
        order = next(o for o in SCENARIO['orders'] if o['order_id'] == 'order-1')
        raw = json.dumps({'request_id': payload['request_id'],
                          'action': {'kind': 'claim', 'order_id': 'order-1', 'role': 'west',
                                     'destination_zone': order['destination_zone']},
                          'decision_sources': ['own_rgb', 'order_sheet'], 'messages': messages},
                         ensure_ascii=False)
        return io.BytesIO(completion_body(raw, usage=USAGE, model='gemini-3.8-flash-low'))


def driven_trial(tmp_path, condition, *, budget=None, limits=None, fault=None, horizon=60., run_key='run#a1'):
    budget = budget or budget_for(tmp_path)
    wire = FakeModel(condition, fault=fault)
    driver = llm.LiveDriver(PROFILE, budget=budget, cohort_id='pilot-A', wire=wire)
    driver.start_run(run_key, bundle_id=zi.EXECUTION_BUNDLE_ID, bundle_sha256='b' * 64,
                     record={'condition': condition})
    adapter = driver.adapter(run_key=run_key, store_dir=tmp_path / 'wire')
    clock = [0.]
    links = links_for(clock)
    trial = tm.TimingTrial(SCENARIO, condition=condition, seed=11, links=links, horizon_s=horizon,
                           map_bundle=BUNDLE, actor='gemini_proxy', model_adapter=adapter,
                           policy=tm.CallPolicy(max_retries=0),
                           cost_params=tm.CostParams(input_token_s=0., output_token_s=.1, utterance_s=.1),
                           decision_limits=limits or llm.speech_caps('main_pilot_10_30')[0])
    trial.begin(0.)
    tm.advance(trial, clock, links, horizon, boundary=8.)
    return trial, wire, budget, driver


# ---------------------------------------------------------------------------
# Registry: speech caps and driver profile are selected per registered bundle

def test_speech_caps_are_registered_per_bundle_and_ad_hoc_limits_are_refused():
    limits, record = llm.speech_caps('main_pilot_10_30')
    assert (limits.max_utterances_per_actor, limits.max_utterances_total, limits.max_calls_total) == (10, 30, 90)
    assert llm.speech_caps('v66_default')[0] == DecisionLimits()          # v66 default 2/6
    assert record['profile'] == 'main_pilot_10_30' and len(record['sha256']) == 64
    assert llm.speech_caps_for({})[1]['profile'] == 'v66_default'
    assert llm.speech_caps_for({'speech_cap_profile': 'main_pilot_10_30'})[0] == limits
    with pytest.raises(ContractViolation, match='ad hoc'):
        llm.speech_caps_for({'decision_limits': {'max_utterances_per_actor': 10}})
    with pytest.raises(ContractViolation, match='not registered for bundle'):
        llm.speech_caps('main_pilot_10_30', bundle_id='zone-study-integration-v69-multiturn-landmark-agnostic')
    with pytest.raises(ContractViolation, match='not registered in'):
        llm.speech_caps('v66_default', bundle_id='zone-study-integration-v99-unknown')
    assert zi.EXECUTION_BUNDLE_ID == 'zone-pair-v83-carry-door-gain'   # b-v6h1 pre-seal candidate (v81 + five opt-in options)
    assert 'zone-study-integration-v69-multiturn-landmark-agnostic' in zi.RETIRED_BUNDLE_IDS


def test_driver_profile_matches_planned_model_and_refuses_drift(monkeypatch):
    assert {k: PROFILE['model'][k] for k in ('model', 'temperature', 'reasoning_effort')} == {
        k: zi.PLANNED_MODEL[k] for k in ('model', 'temperature', 'reasoning_effort')}
    assert llm.client_factory(PROFILE).settings['url'] == PROFILE['proxy_url']
    registry = llm.load_registry()
    registry['driver_profiles']['main_study_gemini_v1']['model']['temperature'] = 0.9
    with pytest.raises(ContractViolation, match='drifts'):
        llm.driver_profile('main_study_gemini_v1', registry=registry)
    with pytest.raises(ContractViolation, match='not registered for bundle'):
        llm.driver_profile('main_study_gemini_v1', bundle_id='zone-study-integration-v69-multiturn-landmark-agnostic')


# ---------------------------------------------------------------------------
# Real model path in all four conditions (fake wire)

@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
def test_every_robot_takes_several_model_turns_with_raw_bytes_tokens_latency(tmp_path, condition):
    trial, wire, budget, _ = driven_trial(tmp_path, condition, horizon=90.)
    ledger = trial.send_ledger
    assert isinstance(ledger, llm.MainStudySendLedger) and trial.scheduler.send_ledger is ledger
    assert not ledger.live and ledger.fatal is None
    rows = llm.call_rows(ledger)
    assert len(rows) == len(wire.bodies) == ledger.sends() > 3
    for rid in zi.ROBOTS:
        assert sum(r['actor'] == rid for r in rows) >= 2                  # multi-turn, per robot
    for row, body in zip(rows, wire.bodies):
        raw = (tmp_path / 'wire' / row['request_path']).read_bytes()
        assert json.loads(raw) == body and hashlib.sha256(raw).hexdigest() == row['body_sha256']
        response = (tmp_path / 'wire' / row['response_path']).read_bytes()
        assert hashlib.sha256(response).hexdigest() == row['response_sha256']
        jpeg = base64.b64decode(next(p['image_url']['url'] for p in body['messages'][-1]['content']
                                     if p['type'] == 'image_url').split(',', 1)[1])
        assert row['images'] == [{'sha256': hashlib.sha256(jpeg).hexdigest(), 'bytes': len(jpeg)}]
        assert trial.request_images[row['images'][0]['sha256']] == jpeg
        assert row['provider_usage'] == USAGE and row['usage_known'] and row['failure_class'] is None
        assert row['latency_ms'] is not None and row['response_model'] == 'gemini-3.8-flash-low'
    summary = llm.usage_summary(rows)
    assert summary['tokens_total_known'] == 600 * len(rows) and summary['tokens_complete']
    assert summary['failure_classes'] == {} and summary['latency_ms']['n'] == len(rows)
    stored = budget.requests('run#a1')
    assert [r['body_sha256'] for r in stored] == [r['body_sha256'] for r in rows]
    assert all(r['status'] == 'response_received' and r['total_tokens'] == 600 and r['latency_ms'] is not None
               and r['bundle_id'] == zi.EXECUTION_BUNDLE_ID for r in stored)
    assert budget.usage('pilot-A')['known_tokens'] == 600 * len(rows)
    result = trial.finish(trial.scheduler.now())
    assert bool(result.messages) == (condition != 'no_comm')
    assert llm.trial_failure_class(None, ledger) is None


def test_no_comm_keeps_frozen_v64_bytes_through_the_driver_ledger_and_any_speech_cap(tmp_path, monkeypatch):
    """The v64 90 s wait golden of no_comm, reproduced with the new ledger under 2/6 and 10/30."""
    for caps in ('v66_default', 'main_pilot_10_30'):
        budget = MainStudyBudget.create(tmp_path / f'{caps}.sqlite')
        budget.register_cohort('c', token_cap=None, unknown_usage_charge_tokens=0, prereg_sha256=None, source={})
        budget.start_run('r#a1', cohort_id='c', bundle_id=zi.EXECUTION_BUNDLE_ID, bundle_sha256='b', record={})
        made = []

        def ledger(wire, _budget=budget, _caps=caps):
            made.append(llm.MainStudySendLedger(store_dir=tmp_path / _caps, budget=_budget, run_key='r#a1',
                                                profile=PROFILE, wire=wire))
            return made[-1]
        monkeypatch.setattr(tm, 'SendLedger', ledger)
        trial, clock, links, requests = tm.make_trial('no_comm', first='wait', send=False, follow_claim=False,
                                                      policy=tm.CallPolicy(max_retries=0),
                                                      limits=llm.speech_caps(caps)[0])
        tm.advance(trial, clock, links, 90.)
        assert trial.send_ledger is made[0]
        assert tm.wait_control_record(trial, requests) == GOLDEN['conditions']['no_comm']
        assert len(budget.requests('r#a1')) == made[0].sends() > 0


def test_pilot_speech_caps_open_the_channel_beyond_v66_default(tmp_path):
    counts = {}
    for caps in ('v66_default', 'main_pilot_10_30'):
        path = tmp_path / caps
        path.mkdir()
        trial, _, _, _ = driven_trial(path, 'peer_ko', limits=llm.speech_caps(caps)[0], horizon=90.)
        result = trial.finish(trial.scheduler.now())
        counts[caps] = sum(m['sender'] == 'r3' for m in result.messages)
        assert trial.study_config()['decision_limits'] == llm.speech_caps(caps)[1]['values']
    assert counts['v66_default'] <= 2 < counts['main_pilot_10_30'] <= 10


# ---------------------------------------------------------------------------
# Failures (prereg §8)

@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
def test_partial_api_error_is_recorded_but_excluded_in_every_condition(tmp_path, condition):
    def fault(payload, n):
        if n == 2:
            raise HTTPError('http://127.0.0.1:8391/v1/chat/completions', 429, 'quota', {}, None)
    trial, wire, budget, _ = driven_trial(tmp_path, condition, fault=fault)
    rows = llm.call_rows(trial.send_ledger)
    bad = [r for r in rows if r['failure_class']]
    assert [(r['seq'], r['http_status'], r['wire_error'], r['failure_class']) for r in bad] == [
        (2, 429, 'HTTPError', llm.API_ERROR)]
    assert not bad[0]['usage_known'] and (tmp_path / 'wire' / bad[0]['request_path']).exists()
    stored = budget.requests('run#a1')[1]
    assert stored['status'] == 'wire_error' and stored['http_status'] == 429 and stored['total_tokens'] is None
    assert len(rows) > 2                                                    # later turns still happen
    assert llm.usage_summary(rows)['usage_unknown_requests'] == 1
    assert llm.trial_failure_class(None, trial.send_ledger) == llm.API_ERROR
    summary = llm.usage_summary(rows)
    assert summary['api_error_requests'] == 1 and not summary['api_clean']
    assert summary['api_error_fraction'] == 1 / len(rows)
    result = trial.finish(trial.scheduler.now())
    summary.update(failure_class=llm.API_ERROR, pose_provider={})
    runner.write_study(tmp_path / 'saved', trial, result, summary)
    saved = json.loads((tmp_path / 'saved/study/trial_record.json').read_text())
    assert saved['failure_class'] == llm.API_ERROR and saved['end_reason'] == 'api_failure'
    assert saved['model_usage']['api_error_requests'] == 1


def test_every_call_failing_with_api_errors_classifies_the_trial_as_api(tmp_path):
    def fault(payload, n):
        raise HTTPError('http://127.0.0.1:8391/v1/chat/completions', 503, 'down', {}, None)
    trial, *_ = driven_trial(tmp_path, 'no_comm', fault=fault, horizon=30.)
    assert llm.trial_failure_class(None, trial.send_ledger) == llm.API_ERROR


def test_enospc_while_storing_a_request_is_a_host_error_not_an_api_error(tmp_path, monkeypatch):
    store = SendLedger._store

    def full(self, row, kind, data):
        if row['seq'] == 3 and kind == 'request':
            raise OSError(errno.ENOSPC, 'No space left on device')
        return store(self, row, kind, data)
    monkeypatch.setattr(SendLedger, '_store', full)
    trial, wire, budget, _ = driven_trial(tmp_path, 'leader_ko', horizon=30.)
    ledger = trial.send_ledger
    assert isinstance(ledger.fatal, llm.HostError) and ledger.fatal.errno == errno.ENOSPC
    assert llm.classify_exception(ledger.fatal) == llm.HOST_ERROR
    assert llm.trial_failure_class(None, ledger) == llm.HOST_ERROR
    assert ledger.host_errors[0]['errno'] == errno.ENOSPC
    assert len(wire.bodies) == 2 and len(budget.requests('run#a1')) == 2   # nothing sent after the fatal error


def test_exception_classes():
    assert llm.classify_exception(OSError(errno.ENOSPC, 'full')) == llm.HOST_ERROR
    assert llm.classify_exception(llm.HostError('proxy down')) == llm.HOST_ERROR
    assert llm.classify_exception(PermissionError('x')) == llm.OTHER
    wrapped = RuntimeError('call failed')
    wrapped.__cause__ = llm.GeminiProxyError('timeout', error_kind='timeout', retryable=True)
    assert llm.classify_exception(wrapped) == llm.API_ERROR
    assert llm.classify_exception(BudgetExceeded('cap')) == llm.API_ERROR
    assert llm.classify_exception(ContractViolation('bug')) == llm.OTHER


def test_live_mode_without_proxy_identity_fails_before_any_request(tmp_path):
    budget = budget_for(tmp_path)
    driver = llm.LiveDriver(PROFILE, budget=budget, cohort_id='pilot-A')
    assert driver.live
    with pytest.raises(llm.HostError, match='proxy PID'):
        driver.adapter(run_key='x#a1', store_dir=tmp_path / 'wire')


# ---------------------------------------------------------------------------
# The only retry: once, in place, for a HOST_ERROR before the first model request

def _attempts(tmp_path, outcomes):
    budget = budget_for(tmp_path)
    calls = []

    def start(attempt, run_key):
        budget.start_run(run_key, cohort_id='pilot-A', bundle_id=zi.EXECUTION_BUNDLE_ID, bundle_sha256='b',
                         record={'attempt': attempt})

    def attempt_fn(attempt, run_key):
        calls.append(run_key)
        exc, requests = outcomes[attempt - 1]
        for i in range(requests):
            budget.record_request(run_key, {'call_id': f'c{i}'})
        return {'run_id': 'x', 'failure_class': None}, exc

    return llm.run_attempts(attempt_fn, budget=budget, run_id='peer_ko-e1', start=start), calls, budget


def test_host_error_before_first_request_is_retried_once_and_both_attempts_are_kept(tmp_path):
    (record, exc, attempts), calls, budget = _attempts(tmp_path, [(llm.HostError('mujoco init'), 0), (None, 4)])
    assert calls == ['peer_ko-e1#a1', 'peer_ko-e1#a2'] and exc is None
    assert [(a['failure_class'], a['model_requests'], a['retried']) for a in attempts] == [
        (llm.HOST_ERROR, 0, True), (None, 4, False)]
    assert budget.run('peer_ko-e1#a1')['status'] == 'failed' and budget.run('peer_ko-e1#a2')['status'] == 'finished'


@pytest.mark.parametrize('outcomes', [
    [(llm.HostError('ENOSPC mid run'), 3)],                                  # after the first request
    [(ContractViolation('bug'), 0)],                                         # not a host error
    [(llm.GeminiProxyError('down', error_kind='connection', retryable=True), 0)],
])
def test_no_retry_after_first_request_or_for_non_host_errors(tmp_path, outcomes):
    (_, exc, attempts), calls, _ = _attempts(tmp_path, outcomes)
    assert len(calls) == 1 and exc is not None and not attempts[0]['retried']


def test_second_pre_request_host_error_is_final(tmp_path):
    (_, exc, attempts), calls, _ = _attempts(tmp_path, [(llm.HostError('a'), 0), (llm.HostError('b'), 0)])
    assert len(calls) == 2 and isinstance(exc, llm.HostError)
    assert [a['retried'] for a in attempts] == [True, False]


# ---------------------------------------------------------------------------
# New ledger: records, never blocks when large, stops only at the registered cohort cap

def test_no_cap_never_blocks_and_cap_stops_only_at_the_registered_value(tmp_path):
    (tmp_path / 'a').mkdir()
    trial, wire, budget, _ = driven_trial(tmp_path / 'a', 'peer_ko', budget=budget_for(tmp_path / 'a', cap=None))
    assert not trial.transport.budget_exhausted and budget.usage('pilot-A')['requests'] == len(wire.bodies) > 3
    (tmp_path / 'b').mkdir()
    capped = budget_for(tmp_path / 'b', cap=1200)
    trial, wire, budget, _ = driven_trial(tmp_path / 'b', 'peer_ko', budget=capped)
    assert len(wire.bodies) == 2 and trial.transport.budget_exhausted       # 2 x 600 reaches 1200
    blocked = [r for r in llm.call_rows(trial.send_ledger) if r['status'] == 'blocked']
    assert blocked and blocked[0]['failure_class'] == 'budget_cap'
    assert blocked[0]['reason'] == 'budget_cap'
    assert isinstance(trial.send_ledger.fatal, BudgetExceeded)
    assert llm.trial_failure_class(None, trial.send_ledger) == llm.API_ERROR
    with pytest.raises(BudgetExceeded):
        llm.check_trial_health(trial)
    assert budget.usage('pilot-A') == {'requests': 2, 'known_tokens': 1200, 'usage_unknown_requests': 0,
                                       'pending_requests': 0, 'charged_tokens': 1200, 'token_cap': 1200}


def test_unknown_usage_is_charged_the_registered_amount_not_zero(tmp_path):
    budget = budget_for(tmp_path, cap=10_000, charge=6_000)
    budget.start_run('r#a1', cohort_id='pilot-A', bundle_id='b', bundle_sha256='s', record={})
    first = budget.record_request('r#a1', {'call_id': 'c1'})             # crashed driver: never settled
    usage = budget.usage('pilot-A')
    assert (usage['pending_requests'], usage['charged_tokens'], usage['known_tokens']) == (1, 6000, 0)
    budget.record_request('r#a1', {'call_id': 'c2'})
    with pytest.raises(BudgetExceeded):
        budget.record_request('r#a1', {'call_id': 'c3'})
    budget.settle_request(first['id'], status='response_received', provider_usage=USAGE)
    with pytest.raises(ValueError, match='immutable'):
        budget.settle_request(first['id'], status='wire_error')


def test_cohort_registration_is_immutable_and_ledger_is_never_created_implicitly(tmp_path):
    budget = budget_for(tmp_path, cap=5)
    budget.register_cohort('pilot-A', token_cap=5, unknown_usage_charge_tokens=0, prereg_sha256='p' * 64,
                           source={'other': 'source is not part of the fixed identity'})
    with pytest.raises(ValueError, match='different cap'):
        budget.register_cohort('pilot-A', token_cap=10, unknown_usage_charge_tokens=0, prereg_sha256='p' * 64,
                               source={})
    with pytest.raises(FileExistsError):
        MainStudyBudget.create(tmp_path / 'main_budget.sqlite')
    with pytest.raises(FileNotFoundError):
        MainStudyBudget(tmp_path / 'absent.sqlite')


def test_the_222_pilot_budget_file_is_refused_and_left_unchanged(tmp_path):
    from harness.zone_pilot_budget import PilotBudget
    PilotBudget.create(tmp_path / 'pilot.sqlite', identity={'test': True})
    before = (tmp_path / 'pilot.sqlite').read_bytes()
    with pytest.raises(ValueError, match='not a ugrp.zone_main_study_budget.v1'):
        MainStudyBudget(tmp_path / 'pilot.sqlite')
    assert (tmp_path / 'pilot.sqlite').read_bytes() == before


def test_prereg_driver_block_is_exact_and_needs_registered_speech_caps(tmp_path):
    block = {'profile': 'main_study_gemini_v1', 'cohort_id': 'pilot-A', 'cohort_token_cap': None,
             'unknown_usage_charge_tokens': 0, 'budget_db': str(tmp_path / 'db.sqlite')}
    with pytest.raises(ContractViolation, match='speech_cap_profile'):
        llm.LiveDriver.from_prereg({'llm_driver': block}, prereg_sha256=None, source={})
    with pytest.raises(ContractViolation, match='exactly'):
        llm.LiveDriver.from_prereg({'llm_driver': {**block, 'extra': 1}, 'speech_cap_profile': 'main_pilot_10_30'},
                                   prereg_sha256=None, source={})
    with pytest.raises(FileNotFoundError):                                  # no implicit creation
        llm.LiveDriver.from_prereg({'llm_driver': block, 'speech_cap_profile': 'main_pilot_10_30'},
                                   prereg_sha256=None, source={})
    driver = llm.LiveDriver.from_prereg({'llm_driver': block, 'speech_cap_profile': 'main_pilot_10_30'},
                                        prereg_sha256=None, source={}, create_budget=True, wire=FakeModel('no_comm'))
    assert driver.bundle_record()['profile_sha256'] == PROFILE['sha256']
    assert driver.ledger_record()['cohort']['token_cap'] is None


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
@pytest.mark.parametrize('profile', ['v66_default', 'main_pilot_10_30'])
def test_registered_prompt_text_matches_every_request_cap_and_role(tmp_path, condition, profile):
    trial, wire, *_ = driven_trial(tmp_path, condition, limits=llm.speech_caps(profile)[0], horizon=10.)
    roles = set()
    for body in wire.bodies:
        system = body['messages'][0]['content']
        payload = json.loads(next(p['text'] for p in body['messages'][-1]['content'] if p['type'] == 'text'))
        if condition == 'no_comm':
            assert 'dialogue_window' not in payload
            assert '이 조건의 발화 예산은 0입니다.' in system
        else:
            caps = payload['dialogue_window']
            assert (f'팀 전체 최대 {caps["max_utterances"]}발화, '
                    f'당신은 최대 {caps["max_your_utterances"]}발화입니다.') in system
        if 'role' in payload:
            roles.add(payload['role'])
    if condition == 'leader_ko':
        assert roles == {'leader', 'follower'}
    expected_version = (llm.pk.LEGACY_PROMPT_VERSION if condition == 'no_comm' or profile == 'v66_default'
                        else llm.pk.PROMPT_VERSION)
    assert {r['prompt_version'] for r in trial.requests} == {expected_version}


def test_default_system_prompt_bytes_are_frozen_at_f493df5a():
    frozen = {
        'no_comm': ['a5f3694f923e994450b3c932c7ed529e85670965ea261228a5312a2cd73d8b29',
                    '4de3ed7ce9a35e2afcb052d65a39c6042bc6ab021c6e7fd19c5c41182efd21f2',
                    'ad95016eeebc8054259309504822a6986b1ece32cdf5406d559f3fc4c32420a6'],
        'peer_ko': ['2d79575c2e87350576e7ba2a063c0778bbc4d2c78b3899868a6d5431bb2421f2',
                    '38f5996071f34ef382003c15bab18b1e9715813aba32c715185674b62b60665f',
                    '9b3c023690a8c21932bc30a6f2f1affc7f29afb8f2821d30ab9b45559e1a8f4f'],
        'leader_ko': ['6c68b91f650b7c0696112f50b533b7c363629601aad2ff4379b0380869320316',
                      '8f2d9f4fdab670d8de6a6bfb7d77bde12dd23a862a83c4734c5500784d59e613',
                      'b775d03e73f04350a3144bb1f0c42f041c04153f46786e25baf5a816b676787a'],
        'structured': ['75df2c93542bdee82f98f1e6ab660bcb631d64ac7a8c14a6efde5ed4d63d67a4',
                       '69577e19d0fe9a32bf01c9b2d3bfe14a5e3c4106af81d62e7df4b7688c140eff',
                       'e88268dfade3e3b57896c781d2817e084fcf2bb644c5f57e8a8a34c6af0a62b2'],
    }
    for condition, expected in frozen.items():
        assert [hashlib.sha256(llm.pk.system_prompt(condition, r, seed=11).encode()).hexdigest()
                for r in zi.ROBOTS] == expected
    assert llm.pk.prompt_version() == 'ugrp.zone_study_prompts_ko.v2'
    assert llm.pk.prompt_version(30, 10) == 'ugrp.zone_study_prompts_ko.v3'


def test_registry_rejects_prompt_version_mismatch_before_budget_creation(tmp_path, monkeypatch):
    registry = llm.load_registry()
    registry['speech_cap_profiles']['main_pilot_10_30']['prompt_versions'] = [llm.pk.LEGACY_PROMPT_VERSION]
    monkeypatch.setattr(llm, 'load_registry', lambda: registry)
    block = {'profile': 'main_study_gemini_v1', 'cohort_id': 'c', 'cohort_token_cap': None,
             'unknown_usage_charge_tokens': 0, 'budget_db': str(tmp_path / 'unused.sqlite')}
    with pytest.raises(ContractViolation, match='prompt version'):
        llm.LiveDriver.from_prereg({'llm_driver': block, 'speech_cap_profile': 'main_pilot_10_30'},
                                   prereg_sha256=None, source={}, create_budget=True)
    assert not (tmp_path / 'unused.sqlite').exists()


@pytest.mark.parametrize('code', [errno.ENOSPC, errno.EDQUOT, errno.EIO, errno.ENOMEM, errno.EMFILE, errno.ENFILE])
def test_host_errno_allowlist(code):
    assert llm.classify_exception(OSError(code, 'host failure')) == llm.HOST_ERROR


@pytest.mark.parametrize('error', [FileExistsError(errno.EEXIST, 'exists'), FileNotFoundError(errno.ENOENT, 'absent'),
                                  PermissionError(errno.EACCES, 'permission'), OSError('unknown')])
def test_other_os_errors_are_not_infrastructure_and_never_retried(tmp_path, error):
    assert llm.classify_exception(error) == llm.OTHER
    (_, exc, attempts), calls, _ = _attempts(tmp_path, [(error, 0)])
    assert exc is error and len(calls) == 1 and not attempts[0]['retried']


@pytest.mark.parametrize('error', [OSError(errno.ENOSPC, 'full'), sqlite3.OperationalError('database is locked')])
def test_ledger_settlement_failure_stops_future_sends_and_keeps_response(tmp_path, monkeypatch, error):
    budget = budget_for(tmp_path)
    monkeypatch.setattr(budget, 'settle_request', lambda *a, **k: (_ for _ in ()).throw(error))
    trial, wire, *_ = driven_trial(tmp_path, 'no_comm', budget=budget)
    ledger = trial.send_ledger
    assert len(wire.bodies) == 1
    assert isinstance(ledger.fatal, llm.HostError)
    assert ledger.host_errors[0]['what'] == 'ledger settle'
    assert llm.call_rows(ledger)[0]['failure_class'] == llm.HOST_ERROR
    assert budget.requests()[0]['status'] == 'sent_unknown'
    assert (tmp_path / 'wire' / ledger.entries[0]['response_path']).read_bytes()
    with pytest.raises(llm.HostError):
        llm.check_trial_health(trial)


@pytest.mark.parametrize('existing', ['no_comm-e1', 'no_comm-e1-attempt2', 'no_comm-e1.attempts.json'])
def test_existing_output_refused_before_start_run_and_no_retry(tmp_path, monkeypatch, existing):
    budget = budget_for(tmp_path)
    driver = llm.LiveDriver(PROFILE, budget=budget, cohort_id='pilot-A', wire=FakeModel('no_comm'))
    path = tmp_path / existing
    path.write_bytes(b'original evidence')
    monkeypatch.setattr(driver, 'start_run', lambda *a, **k: pytest.fail('no registration allowed'))
    monkeypatch.setattr(runner, 'run_trial', lambda *a, **k: pytest.fail('no attempt allowed'))
    with pytest.raises(SystemExit, match='refusing overwrite or rerun'):
        runner.run_llm_trial({}, {'episode_id': 'e1'}, 'no_comm', tmp_path, horizon_s=30., dev=True,
                             expected_source_sha=None, driver=driver)
    assert path.read_bytes() == b'original evidence'
    assert budget.requests() == []


def test_exhausted_cohort_refused_before_registration_host_or_output(tmp_path, monkeypatch):
    budget = budget_for(tmp_path, cap=1, charge=1)
    budget.start_run('old', cohort_id='pilot-A', bundle_id='b', bundle_sha256='s', record={})
    budget.record_request('old', {'call_id': 'old'})
    driver = llm.LiveDriver(PROFILE, budget=budget, cohort_id='pilot-A', wire=FakeModel('no_comm'))
    monkeypatch.setattr(driver, 'start_run', lambda *a, **k: pytest.fail('no registration allowed'))
    monkeypatch.setattr(runner, 'run_trial', lambda *a, **k: pytest.fail('no host allowed'))
    out = tmp_path / 'not-started'
    with pytest.raises(BudgetExceeded):
        runner.run_llm_trial({}, {'episode_id': 'e1'}, 'no_comm', out, horizon_s=30., dev=True,
                             expected_source_sha=None, driver=driver)
    assert not out.exists()
    # The database repeats the gate inside the start transaction for concurrent callers.
    with pytest.raises(BudgetExceeded):
        budget.start_run('new', cohort_id='pilot-A', bundle_id='b', bundle_sha256='s', record={})
    with pytest.raises(KeyError):
        budget.run('new')


def test_zero_send_zero_success_and_transport_cap_are_infra(tmp_path):
    trial, *_ = driven_trial(tmp_path, 'no_comm', horizon=1.)
    ledger = trial.send_ledger
    ledger.entries.clear()
    assert llm.trial_failure_class(None, ledger) == llm.API_ERROR
    assert llm.usage_summary([])['tokens_complete'] is False
    with pytest.raises(llm.GeminiProxyError, match='no successful model response'):
        llm.check_trial_health(trial, final=True)
    trial.transport.budget_exhausted = True
    assert llm.trial_failure_class(None, ledger, transport=trial.transport) == llm.API_ERROR
    with pytest.raises(BudgetExceeded):
        llm.check_trial_health(trial)


def test_pacer_spacing_is_shared_across_all_conditions_without_sim_time():
    wall, waits, starts = [0.], [], []
    def sleep(seconds):
        waits.append(seconds)
        wall[0] += seconds
    pacer = llm.RequestPacer(PROFILE['min_request_interval_s'], clock=lambda: wall[0], sleep=sleep)
    for _ in zi.MAIN_CONDITIONS:
        pacer.wait()
        starts.append(wall[0])
        wall[0] += .25
    assert starts == [0., 2., 4., 6.] and waits == [1.75] * 3


def test_new_driver_tests_are_collected_by_ci():
    import fnmatch
    from scripts.run_ci_tests import TEST_PATTERNS
    assert any(fnmatch.fnmatch('tests/test_zone_study_llm_driver.py', p) for p in TEST_PATTERNS)


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
@pytest.mark.parametrize('fault_kind', ['cap', 'zero_reply', 'prewire_input', 'settlement'])
def test_runner_aborts_before_next_host_step_and_records_infra(tmp_path, monkeypatch, fault_kind, condition):
    """Production runner + real scheduler/ledger, with NO MuJoCo or physics host."""
    for module in ('mujoco', 'cv2', 'numpy'):
        monkeypatch.setitem(sys.modules, module, SimpleNamespace(__version__='fake-no-physics'))
    budget = budget_for(tmp_path, cap=1200 if fault_kind == 'cap' else None)
    def fault(payload, n):
        if fault_kind == 'zero_reply':
            raise HTTPError('http://127.0.0.1:8391/v1/chat/completions', 503, 'down', {}, None)
    wire = FakeModel(condition, fault=fault)
    driver = llm.LiveDriver(PROFILE, budget=budget, cohort_id='pilot-A', wire=wire)
    if fault_kind == 'prewire_input':
        def prepare(call):
            raise ValueError('generated pre-wire input failure')
        monkeypatch.setattr(zi.IntegratedTrial, 'prepare_call', staticmethod(prepare))
    if fault_kind == 'settlement':
        def settle(*a, **k):
            raise sqlite3.OperationalError('database is locked')
        monkeypatch.setattr(budget, 'settle_request', settle)
    contact = {k: 0 for k in ('profile', 'base_profile', 'noslip_iterations', 'timestep_s')}
    bundle = {'pose_provider': {'label': {}}, 'contact_profile_expected': contact}
    monkeypatch.setattr(runner, 'run_bundle', lambda *a, **k: (bundle, SCENARIO, BUNDLE, {}))
    monkeypatch.setattr(runner, 'check_run_source', lambda *a, **k: {'sha': 'fake'})
    # PR #257 (B6): the runner builds the eval-only referee from the order sheet and the
    # host's static map before the first model boundary, so the stub spec carries one order.
    order = {'order_id': 'o1', 'kind': 'cyan', 'count': 1, 'identity': 'kind_fungible', 'destination_zone': 'A'}
    monkeypatch.setattr(runner, 'host_spec', lambda *a: {'order_sheet': {'orders': [order]}})
    monkeypatch.setattr(runner, 'placements_match', lambda *a: None)
    state = {'advanced': 0, 'closed': False}
    class NoPhysicsHost:
        def __init__(self, *a, **k):
            self.links = links_for([0.])
            self.contact_record, self.pairs = contact, None
            self.world = SimpleNamespace(data=SimpleNamespace(time=0.))
            self.static = {'regions': {}}
        def settle(self, t):
            return t
        def advance_to(self, t):
            state['advanced'] += 1
            pytest.fail('fatal model boundary must abort before another host/physics step')
        def close(self):
            state['closed'] = True
    monkeypatch.setattr(runner, 'StudyTeamHost', NoPhysicsHost)
    write_outputs = runner.write_outputs
    def write_without_physics(out, prereg, episode, condition, bundle, bundle_sha, host, *args, **kwargs):
        return write_outputs(out, prereg, episode, condition, bundle, bundle_sha, None, *args, **kwargs)
    monkeypatch.setattr(runner, 'write_outputs', write_without_physics)
    prereg = {'student': {}, 't0_s': 0., 'speech_cap_profile': 'main_pilot_10_30',
              'call_policy': {'max_retries': 0}}
    out = tmp_path / 'results'
    with pytest.raises(SystemExit):
        runner.run_llm_trial(prereg, {'episode_id': 'e1', 'trial_seed': 11}, condition, out,
                             horizon_s=30., dev=True, expected_source_sha=None, driver=driver)
    run_id = f'{condition}-e1'
    result = json.loads((out / run_id / 'result.json').read_text())
    expected = llm.HOST_ERROR if fault_kind == 'settlement' else llm.API_ERROR
    assert result['failure_class'] == expected and result['stop'] == 'exception'
    assert state == {'advanced': 0, 'closed': True}
    attempts = json.loads((out / f'{run_id}.attempts.json').read_text())['attempts']
    assert len(attempts) == 1 and not attempts[0]['retried']
    assert budget.run(f'{run_id}#a1')['failure_class'] == expected
    assert not (out / f'{run_id}-attempt2').exists()
    if fault_kind == 'prewire_input':
        assert wire.bodies == [] and budget.requests() == []
        assert attempts[0]['model_requests'] == 0


# P05: production driver/client/input builder/scheduler, fake wire + robot port.
# The fixture matches fixed Korean strings; it does not measure model understanding.
P05_COST = tm.CostParams(input_token_s=.00001, output_token_s=.001, utterance_s=.1)


def dialogue_scenario():
    scenario = copy.deepcopy(SCENARIO)
    # Public, specific item IDs exercise literal preservation without host poses.
    for order in scenario['orders']:
        order.update(identity='specific_item', item_ids=[f'cyan-{order["order_id"][-1]}'])
    return scenario


class DialogueWire:
    """Fixed proposal/ack script using only the actual request, never executor state."""

    def __init__(self, seed, *, talk=True, fault=None, usage=USAGE):
        self.sender = zi.ROBOTS[seed % 3]
        self.talk, self.fault = talk, fault
        self.usage = usage
        self.turns, self.payloads, self.requests, self.responses, self.headers = Counter(), [], [], [], []
        self.targets = {r: f'order-{i + 2}' for i, r in enumerate(r for r in zi.ROBOTS if r != self.sender)}

    @staticmethod
    def text(sender, recipient, order_id, item_id, *, ack=False):
        return (f'{sender}가 {recipient}에게 알립니다. {order_id}의 {item_id}를 '
                f'west 역할로 {"맡겠습니다" if ack else "맡아 주세요"}.')

    def message(self, payload, recipient, order_id, *, reply_to=None):
        item_id = next(o['item_ids'][0] for o in payload['order_sheet']['orders'] if o['order_id'] == order_id)
        message = {'recipients': [recipient], 'reply_to': reply_to}
        if payload['condition'] == 'structured':
            message['message'] = {'act': 'accept' if reply_to else 'propose', 'item': item_id,
                                  'zone': next(o['destination_zone'] for o in payload['order_sheet']['orders']
                                               if o['order_id'] == order_id),
                                  'role': 'west', 'passage': None, 'location_ref': None,
                                  'state': 'unknown', 'confidence': 'low',
                                  'observed_at_sim_s': payload['sim_time_s'], 'reply_to': reply_to}
        else:
            message['text'] = self.text(payload['robot_id'], recipient, order_id, item_id, ack=bool(reply_to))
        return message

    def __call__(self, request, *, timeout=None):
        body = json.loads(request.data)
        payload = json.loads(next(p['text'] for p in body['messages'][-1]['content'] if p['type'] == 'text'))
        self.requests.append(bytes(request.data))
        self.payloads.append(payload)
        self.headers.append(request.get_header('X-ugrp-call-id'))
        rid = payload['robot_id']
        self.turns[rid] += 1
        n = self.turns[rid]
        proposals = [m for m in payload.get('inbox', []) if m['sender'] == self.sender and m['reply_to'] is None]
        order_id, messages = 'order-1', []
        if proposals and n == 2 and self.fault != 'saturate':
            order_id = self.targets[rid]
            # Fixed fixture matching, with a positive assertion on the actual inbox bytes.
            proposal = proposals[0]
            item_id = next(o['item_ids'][0] for o in payload['order_sheet']['orders'] if o['order_id'] == order_id)
            expected = self.message({**payload, 'robot_id': self.sender,
                                     'sim_time_s': proposal['created_at_sim_s']}, rid, order_id)
            if payload['condition'] == 'structured':
                assert proposal['body']['item'] == expected['message']['item'] == item_id
                assert proposal['body']['role'] == 'west'
            else:
                assert proposal['body'] == {'text': expected['text']}
            messages = [self.message(payload, self.sender, order_id, reply_to=proposal['message_id'])]
        if self.talk and payload['condition'] != 'no_comm' and rid == self.sender and n == 1:
            messages = [self.message(payload, peer, target) for peer, target in self.targets.items()]
        order = next(o for o in payload['order_sheet']['orders'] if o['order_id'] == order_id)
        reply = {'request_id': payload['request_id'],
                 'action': ({'kind': 'claim', 'order_id': order_id, 'role': 'west',
                             'destination_zone': order['destination_zone']} if n <= 2 else {'kind': 'continue'}),
                 'decision_sources': ['own_rgb', 'order_sheet'] + (['message'] if proposals else []),
                 'messages': messages}
        if self.fault == 'saturate':
            reply.update(action={'kind': 'wait'}, decision_sources=['own_rgb', 'order_sheet'],
                         messages=[self.message(payload, payload['channel']['can_send_to'][0], 'order-1')])
        if self.fault == 'stale':
            reply['request_id'] = 'req_old_r1'
        raw = completion_body(json.dumps(reply, ensure_ascii=False), usage=None if self.fault == 'unknown' else self.usage,
                              model='fake-effective-model',
                              finish_reason=self.fault if self.fault in ('length', 'content_filter') else 'stop')
        self.responses.append(raw)
        if self.fault in ('429', '503'):
            raise HTTPError(request.full_url, int(self.fault), 'fake status', {}, None)
        if self.fault == 'lost':
            class LostResponse(io.BytesIO):
                def read(self, *a, **k):
                    raise TimeoutError('fake POST accepted; response lost while reading')
            return LostResponse(raw)
        return io.BytesIO(raw)


def dialogue_trial(tmp_path, condition, seed, *, profile='v66_default', talk=True, fault=None,
                   scenario=None, per_robot=None, budget=None, run_key='p05#a1', horizon=12., usage=USAGE):
    budget = budget or budget_for(tmp_path, charge=700)
    wire = DialogueWire(seed, talk=talk, fault=fault, usage=usage)
    driver = llm.LiveDriver(PROFILE, budget=budget, cohort_id='pilot-A', wire=wire)
    driver.start_run(run_key, bundle_id=zi.EXECUTION_BUNDLE_ID, bundle_sha256='b' * 64,
                     record={'condition': condition, 'seed': seed, 'fake_only': True})
    adapter = driver.adapter(run_key=run_key, store_dir=tmp_path / run_key.replace('#', '-') / 'wire')
    clock = [0.]
    links = links_for(clock, **(per_robot or {}))
    trial = zi.IntegratedTrial(scenario or dialogue_scenario(), condition=condition, seed=seed, links=links,
                               horizon_s=horizon, map_bundle=BUNDLE, actor='gemini_proxy', model_adapter=adapter,
                               policy=tm.CallPolicy(max_retries=0),
                               cost_params=P05_COST, decision_limits=llm.speech_caps(profile)[0])
    trial.begin(0.)
    return trial, wire, budget, clock, links


def dialogue_advance(trial, clock, links, to, *, boundaries=(4., 8.), outcome='job_done'):
    for tick in range(round(clock[0] * 10) + 1, round(to * 10) + 1):
        clock[0] = tick / 10
        for link in links.values():
            link.ex.now = clock[0]
            if clock[0] in boundaries and link.ex.job:
                if outcome == 'job_done':
                    link.ex._finish(clock[0], 'unconfirmed', 'P05_FAKE_OWN_BOUNDARY')
                else:
                    link.ex._fail(clock[0], 'P05_FAKE_OWN_FAILURE')
            for event in link.ex.drain_events():
                trial.on_executor_event(event, at_s=clock[0])
        trial.step_to(clock[0])


def assert_wire_accounting(trial, wire, budget, result, run_key='p05#a1'):
    """Re-open raw bytes and join every layer by call/request ID, not row position alone."""
    rows = llm.call_rows(trial.send_ledger)
    stored = {r['call_id']: r for r in budget.requests(run_key)}
    calls = {c.call_id: c for c in trial.scheduler.calls}
    recorded = {trial.request_call_ids[c['request_id']]: c for c in result.calls}
    archives = {r['call_id']: r for r in trial.requests}
    assert len(rows) == trial.send_ledger.sends() == len(wire.requests) == len(stored)
    for row, request, response, header in zip(rows, wire.requests, wire.responses, wire.headers, strict=True):
        db = stored[row['call_id']]
        body = json.loads(request)
        payload = json.loads(next(p['text'] for p in body['messages'][-1]['content'] if p['type'] == 'text'))
        archive = archives[row['call_id']]
        assert header == f'{run_key}:{row["call_id"]}:{row["seq"]}'
        assert archive['request_id'] == payload['request_id'] == f'req_{row["call_id"].replace("-", "_")}'
        assert Path(db['request_path']).read_bytes() == request
        assert db['body_sha256'] == row['body_sha256'] == hashlib.sha256(request).hexdigest()
        assert Path(db['response_path']).read_bytes() == response
        assert db['response_sha256'] == row['response_sha256'] == hashlib.sha256(response).hexdigest()
        assert archive['system'] == body['messages'][0]['content']
        assert archive['user'] == next(p['text'] for p in body['messages'][-1]['content'] if p['type'] == 'text')
        assert llm.pk.verify_archived_request(archive) == []
        assert trial.provenance['model_settings_sha256'] == zi.digest(trial.client_factory.settings)
        assert db['settings'] == {k: PROFILE['model'][k] for k in ('model', 'temperature', 'max_tokens', 'reasoning_effort')}
        jpeg = base64.b64decode(next(p['image_url']['url'] for p in body['messages'][-1]['content']
                                    if p['type'] == 'image_url').split(',', 1)[1])
        sha = hashlib.sha256(jpeg).hexdigest()
        assert row['images'] == db['images'] == [{'sha256': sha, 'bytes': len(jpeg)}]
        assert trial.request_images[sha] == jpeg
        assert payload['own_rgb_refs'][0]['ref'].startswith(f'own-{row["actor"]}-')
        assert archive['image_refs'][0]['bytes_sha256'] == sha
        assert row['provider_usage'] == db['provider_usage'] == archive['provider_usage'] == USAGE
        assert row['usage_known'] and db['usage_known'] and db['total_tokens'] == 600
        assert db['id'] == row['budget_request_id'] and db['run_key'] == run_key
        assert row['failure_class'] is None and db['status'] == 'response_received'
        call = calls[row['call_id']]
        terms = recorded[row['call_id']]['cost_terms']
        assert call.notes['provider_usage'] == terms['provider_usage'] == USAGE
        assert call.notes['usage_known'] == terms['usage_known'] == row['usage_known']
        assert terms['usage_bound'] == 'exact'
        attempt = call.cost.attempts[0]
        text = json.loads(response)['choices'][0]['message']['content']
        assert attempt.input_tokens == archive['billed_tokens']['total_text_billed']
        assert attempt.output_tokens == llm.pk.count_tokens(text)
        assert attempt.utterances == len(json.loads(text)['messages'])
        assert call.cost == zi.zo.call_cost((attempt,), trial.params)
        assert call.finished_sim_s == pytest.approx(call.started_sim_s + call.cost.sim_s)
        dispatch = next(d for d in trial.dispatch_log if d['call_id'] == call.call_id)
        assert dispatch['sim_s'] == call.finished_sim_s
    assert budget.usage('pilot-A')['known_tokens'] == 600 * len(rows)


@pytest.mark.parametrize('usage,known', [
    (USAGE, True),
    (None, False),
    ({**USAGE, 'total_tokens': 599}, False),
    ({'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}, True),
    ({'prompt_tokens': 500, 'total_tokens': 600}, False),
], ids=['known', 'missing', 'inconsistent', 'zero', 'partial'])
@pytest.mark.parametrize('fault', [None, 'late', 'length', 'stale'])
def test_p05_usage_agrees_from_raw_through_scheduler_and_result(tmp_path, usage, known, fault):
    """B2: MappingProxy replies retain the same usage classification as the durable ledger."""
    horizon = .5 if fault == 'late' else 3.
    trial, wire, budget, clock, links = dialogue_trial(
        tmp_path, 'peer_ko', 700, usage=usage, fault=fault, horizon=horizon)
    dialogue_advance(trial, clock, links, horizon, boundaries=())
    result = trial.finish(horizon)
    rows = llm.call_rows(trial.send_ledger)
    stored = {r['call_id']: r for r in budget.requests('p05#a1')}
    recorded = {trial.request_call_ids[r['request_id']]: r for r in result.calls}
    scheduled = ({r['call_id']: r for r in trial.scheduler.censored} if fault == 'late' else
                 {r.call_id: r.notes for r in trial.scheduler.calls})
    assert len(rows) == len(stored) == len(recorded) == len(scheduled) == 3
    for row in rows:
        db = stored[row['call_id']]
        raw = json.loads(Path(db['response_path']).read_bytes())
        assert raw.get('usage') == row['provider_usage'] == db['provider_usage'] == usage
        assert Path(db['response_path']).read_bytes() == wire.responses[row['seq'] - 1]
        assert row['usage_known'] == db['usage_known'] == known
        assert db['total_tokens'] == (usage['total_tokens'] if known else None)
        call = scheduled[row['call_id']]
        final = recorded[row['call_id']]
        terms = final['cost_terms']
        assert call['provider_usage'] == terms['provider_usage'] == usage
        assert call['usage_known'] == terms['usage_known'] == known
        assert terms['usage_bound'] == ('exact' if known else 'lower_bound')
        assert final['input_tokens']['text'] > 0 and terms['output_tokens'] > 0
    assert budget.usage('pilot-A')['charged_tokens'] == 3 * (usage['total_tokens'] if known else 700)
    if fault:
        assert not result.actions and not result.messages and not trial.dispatch_log
    else:
        assert result.actions


def test_p05_preserves_historical_v6e_and_sealed_successor_source_bytes():
    """B1: usage handling must preserve both versioned source receipts."""
    from tests.v6h_successor_pins import successor_pins
    expected = successor_pins()
    assert 'harness/zone_study_integration.py' in expected
    for path, sha in expected.items():
        assert hashlib.sha256((llm.ROOT / path).read_bytes()).hexdigest() == sha, path


def test_p05_callreply_readonly_usage_is_known():
    from harness.zone_event_scheduler import CallReply
    assert llm.known_total(CallReply(provider_usage=USAGE).provider_usage) == 600


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
@pytest.mark.parametrize('seed', [700, 701, 702])
@pytest.mark.parametrize('profile', ['v66_default', 'main_pilot_10_30'])
def test_p05_dialogue_ids_own_boundary_and_wire_accounting(tmp_path, condition, seed, profile):
    trial, wire, budget, clock, links = dialogue_trial(tmp_path, condition, seed, profile=profile)
    dialogue_advance(trial, clock, links, 3.)
    first = {d['actor']: d for d in trial.dispatch_log}
    assert set(first) == set(zi.ROBOTS) and all(d['ack']['accepted'] for d in first.values())
    assert all(d['args'][0] == 'order-1' for d in first.values())
    assert len(wire.requests) == 3  # delivered messages cannot interrupt a busy own job
    proposals = list(trial.scheduler.messages)
    assert len(proposals) == (0 if condition == 'no_comm' else 2)
    for edge in proposals:
        assert edge.sender == wire.sender and edge.call_id == first[wire.sender]['call_id']
        assert edge.delivered_sim_s > first[edge.recipient]['sim_s']
        assert edge.delivered_sim_s < 4.
        assert trial.channel.inbox(edge.recipient, now_sim_s=edge.delivered_sim_s - .001) == ()
        assert trial.channel.inbox(edge.recipient, now_sim_s=3.) == trial.scheduler.inbox(edge.recipient)
    dialogue_advance(trial, clock, links, 12.)
    assert wire.turns == Counter({rid: 3 for rid in zi.ROBOTS})
    for rid in zi.ROBOTS:
        payloads = [p for p in wire.payloads if p['robot_id'] == rid]
        assert [p['sim_time_s'] for p in payloads] == [0., 4., 8.]
        if condition == 'leader_ko':
            assert trial.leader_id == wire.sender
            assert {p['role'] for p in payloads} == ({'leader'} if rid == wire.sender else {'follower'})
        if condition != 'no_comm':
            cap = llm.speech_caps(profile)[1]['values']
            assert all(p['dialogue_window']['max_utterances'] == cap['max_utterances_total']
                       and p['dialogue_window']['max_your_utterances'] == cap['max_utterances_per_actor'] for p in payloads)
        if rid == wire.sender or condition == 'no_comm':
            continue
        edge = next(e for e in proposals if e.recipient == rid)
        inbox = payloads[1]['inbox']
        assert [m['message_id'] for m in inbox] == [edge.message_id]
        assert inbox[0]['sender'] == wire.sender and inbox[0]['recipients'] == [rid]
        second = [d for d in trial.dispatch_log if d['actor'] == rid][1]
        own_job_id = first[rid]['ack']['job_id']
        event = next(e for e in trial.executor_events if e['event'] == 'job_done' and e['job_id'] == own_job_id)
        assert event['robot_id'] == rid
        assert payloads[1]['own_command_history'][0]['command_id'] == f'cmd_{first[rid]["call_id"].replace("-", "_")}'
        assert payloads[1]['own_command_history'][0]['local_state'] == 'queue_empty'
        assert second['ack']['accepted'] and second['ack']['job_id'] != own_job_id
        assert second['args'][0] == wire.targets[rid] and second['action']['role'] == 'west'
        ack_edge = next(e for e in trial.scheduler.messages if e.call_id == second['call_id'])
        ack = next(m for m in trial.channel.inbox(wire.sender, now_sim_s=8.) if m['message_id'] == ack_edge.message_id)
        assert ack['reply_to'] == edge.message_id and ack['sender'] == rid
        sender_third = next(p for p in wire.payloads if p['robot_id'] == wire.sender and p['sim_time_s'] == 8.)
        assert ack in sender_third['inbox']
        if condition == 'structured':
            assert inbox[0]['body']['item'] == ack['body']['item'] == f'cyan-{wire.targets[rid][-1]}'
            assert inbox[0]['body']['role'] == ack['body']['role'] == 'west'
        else:
            assert inbox[0]['body']['text'] == wire.text(wire.sender, rid, wire.targets[rid], f'cyan-{wire.targets[rid][-1]}')
            assert ack['body']['text'] == wire.text(rid, wire.sender, wire.targets[rid], f'cyan-{wire.targets[rid][-1]}', ack=True)
    result = trial.finish(12.)
    assert result.channel['inbox_agrees_with_scheduler']
    assert not trial.scheduler.send_violations
    assert result.channel['follower_to_follower'] == 0
    if condition == 'no_comm':
        assert not result.messages and all('inbox' not in p for p in wire.payloads)
    elif condition == 'structured':
        assert result.channel['free_text_messages'] == 0
        assert all('text' not in m['body'] for m in result.messages)
    else:
        assert len(result.messages) == 4 and all(m['korean_ok'] for m in result.messages)
    assert_wire_accounting(trial, wire, budget, result)
    assert zi.zo.cost_checks(trial, result)['ok']
    # Persistent local test evidence alongside the dummy ledger and raw bytes.
    (tmp_path / 'contract_trace.json').write_text(json.dumps({
        'fake_only': True, 'profile': profile, 'pair_status_sha256': trial.pair_status.config_sha256(),
        'inputs': trial.input_log, 'dispatch': trial.dispatch_log, 'executor_events': trial.executor_events,
        'result': result.trial_record(provenance_row=trial.provenance)}, ensure_ascii=False, indent=2))


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
@pytest.mark.parametrize('outcome', ['job_done', 'job_failed'])
def test_p05_host_truth_and_peer_private_mutations_keep_common_calls(tmp_path, condition, outcome):
    runs = []
    for variant in ('base', 'host_truth', 'peer_private'):
        path = tmp_path / variant
        path.mkdir()
        scenario = dialogue_scenario()
        if variant != 'base':
            scenario['eval']['setup']['placements'][0]['pose_m'] = [999., -999., 3.]
            scenario['eval']['hidden_events'] = [{'at_sim_s': 4., 'kind': 'item_dropped', 'item': 'cyan-1'}]
            scenario['eval']['success'] = True
        private = ({'r2': {'frame_offset': 3, 'belief': {**zi.zo.belief_skeleton(),
                    'region': 'zone_B', 'held_item_guess': 'yes', 'notes_ko': '사적인 상태 변이'}}}
                   if variant == 'peer_private' else {})
        trial, wire, _, clock, links = dialogue_trial(path, condition, 702, talk=False,
                                                      scenario=scenario, per_robot=private, horizon=90.)
        # Audit-only pair/GT records must not be another observation or wake source.
        trial.pair_status._records = lambda v=variant: [{'status_messages': [], 'eval_only': v}]
        dialogue_advance(trial, clock, links, 90., outcome=outcome)
        runs.append((trial, wire))
    base, host, peer = runs
    assert base[1].requests == host[1].requests
    assert base[0].scheduler.trace() == host[0].scheduler.trace()
    assert base[0].pair_status.record() != host[0].pair_status.record()  # positive control
    assert len({t.pair_status.config_sha256() for t, _ in runs}) == 1
    own = lambda w, rid: [raw for raw, p in zip(w.requests, w.payloads, strict=True) if p['robot_id'] == rid]
    assert own(base[1], 'r2') != own(peer[1], 'r2')
    for rid in ('r1', 'r3'):
        assert own(base[1], rid) == own(peer[1], rid)
        assert base[0].wakeups(rid) == peer[0].wakeups(rid)
        calls = [c for c in peer[0].scheduler.calls if c.actor == rid]
        assert any('timer' in {c.trigger, *c.merged_triggers} for c in calls)
        assert any(('idle' if outcome == 'job_done' else 'failure') in {c.trigger, *c.merged_triggers}
                   for c in calls if c.started_sim_s == 4.)
    assert all(not t.scheduler.messages for t, _ in runs)


@pytest.mark.parametrize('profile', ['v66_default', 'main_pilot_10_30'])
def test_p05_pair_status_and_execution_settings_are_identical_across_conditions(tmp_path, profile):
    configs = []
    for condition in zi.MAIN_CONDITIONS:
        path = tmp_path / condition
        path.mkdir()
        trial, *_ = dialogue_trial(path, condition, 700, profile=profile)
        configs.append(zi.condition_invariant_config(trial.study_config()))
    assert all(c == configs[0] for c in configs)
    assert all(c['pair_status_sha256'] == zi.digest(c['pair_status']) for c in configs)


@pytest.mark.parametrize('condition', ['peer_ko', 'leader_ko', 'structured'])
@pytest.mark.parametrize('profile, per_actor, total', [('v66_default', 2, 6), ('main_pilot_10_30', 10, 30)])
def test_p05_effective_episode_caps_stop_actual_sends_but_keep_generated_cost(tmp_path, condition, profile, per_actor, total):
    trial, wire, _, clock, links = dialogue_trial(tmp_path, condition, 700, profile=profile,
                                                  fault='saturate', horizon=150.)
    tm.advance(trial, clock, links, 150.)  # advance only fake hold timers, no executor/physics step
    result = trial.finish(150.)
    assert trial.channel.sent_count() == len(result.messages) == total
    assert all(trial.channel.sent_count(rid) == per_actor for rid in zi.ROBOTS)
    assert trial.scheduler.rejected_messages
    assert sum(c.cost.breakdown['utterances'] for c in trial.scheduler.calls) > total
    assert trial.channel.windows == ['w1']  # turn boundaries cannot replenish the episode budget
    for raw, payload in zip(wire.requests, wire.payloads, strict=True):
        window = payload['dialogue_window']
        assert (window['max_your_utterances'], window['max_utterances']) == (per_actor, total)
        assert (f'팀 전체 최대 {total}발화, 당신은 최대 {per_actor}발화입니다.'
                in json.loads(raw)['messages'][0]['content'])
    assert any(p['dialogue_window']['your_utterances_left'] == 0 for p in wire.payloads)
    assert zi.zo.cost_checks(trial, result)['ok']


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
@pytest.mark.parametrize('fault', ['429', '503', 'lost', 'length', 'content_filter', 'stale', 'unknown', 'late'])
def test_p05_post_failure_costs_and_no_attempt_replay(tmp_path, condition, fault):
    """Run the real attempts wrapper; none of these post-wire cases may retry."""
    budget = budget_for(tmp_path, charge=700)
    trials = []
    def attempt(attempt, key):
        # A read timeout pays the unchanged 20 SIM-second timeout tariff.
        horizon = .5 if fault == 'late' else 30. if fault == 'lost' else 3.
        trial, wire, _, clock, links = dialogue_trial(tmp_path, condition, 700, fault=fault,
                                                      budget=budget, run_key=key, horizon=horizon)
        dialogue_advance(trial, clock, links, horizon, boundaries=())
        result = trial.finish(horizon)
        trials.append((trial, wire, result))
        return {'failure_class': llm.trial_failure_class(None, trial.send_ledger, transport=trial.transport)}, None
    # The helper registers before begin(), so the wrapper's start hook has no other work.
    record, exc, attempts = llm.run_attempts(attempt, budget=budget, run_id='fault', start=lambda *a: None)
    assert exc is None and len(attempts) == 1 and not attempts[0]['retried']
    trial, wire, result = trials[0]
    assert len(wire.requests) == trial.send_ledger.sends() == budget.run_requests('fault#a1') == 3
    assert all(trial.send_ledger.sends(r['call_id']) == 1 for r in trial.send_ledger.entries)
    usage = budget.usage('pilot-A')
    unknown = fault in ('429', '503', 'lost', 'unknown')
    assert usage['requests'] == 3 and usage['pending_requests'] == 0
    assert usage['known_tokens'] == (0 if unknown else 1800)
    assert usage['usage_unknown_requests'] == (3 if unknown else 0)
    assert usage['charged_tokens'] == (2100 if unknown else 1800)
    rows = llm.call_rows(trial.send_ledger)
    for row in rows:
        db = next(r for r in budget.requests('fault#a1') if r['id'] == row['budget_request_id'])
        assert Path(db['request_path']).read_bytes() == wire.requests[row['seq'] - 1]
        assert row['usage_known'] == db['usage_known'] == (not unknown)
        assert row['provider_usage'] == db['provider_usage'] == (None if unknown else USAGE)
        if fault in ('429', '503', 'lost'):
            assert row['response_path'] is None and db['status'] == 'wire_error'
            assert row['failure_class'] == llm.API_ERROR
            assert row['http_status'] == (int(fault) if fault != 'lost' else None)
        else:
            assert Path(db['response_path']).read_bytes() == wire.responses[row['seq'] - 1]
    if fault in ('429', '503', 'lost', 'length', 'content_filter', 'stale', 'late'):
        assert not trial.dispatch_log and not result.actions and not result.messages
        assert all(not history for history in trial._history.values())
        if fault == 'late':
            assert len(result.calls) == 3 and all(c['status'] == 'censored' for c in result.calls)
            assert all(c['cost_terms']['would_release_sim_s'] > .5 for c in result.calls)
            trial.step_to(20.)  # closing the horizon permanently discards those late actions
            assert not trial.dispatch_log and trial.send_ledger.sends() == 3
        else:
            assert len(trial.scheduler.calls) == 3
            assert all(c.cost.sim_s > 0 and c.cost.breakdown['attempts'] == 1 for c in trial.scheduler.calls)
            if fault in ('length', 'content_filter'):
                assert all(c.cost.breakdown['output_tokens'] > 0 for c in trial.scheduler.calls)
                assert sum(c.cost.breakdown['utterances'] for c in trial.scheduler.calls) == (0 if condition == 'no_comm' else 2)
    if fault in ('429', '503', 'lost', 'length', 'content_filter'):
        assert record['failure_class'] == llm.API_ERROR and budget.run('fault#a1')['status'] == 'failed'
    elif fault == 'stale':
        assert all(c['status'] == 'invalid_json' for c in result.calls)
    elif fault == 'unknown':
        assert all(not c['cost_terms']['usage_known'] for c in result.calls)
        assert all(c['cost_terms']['usage_bound'] == 'lower_bound' for c in result.calls)
        assert all(c.cost.breakdown['input_tokens'] > 0 and c.cost.breakdown['output_tokens'] > 0
                   for c in trial.scheduler.calls)
    # No old reply or adapter can reopen a completed/censored call and issue another POST.
    from harness.zone_send_ledger import SendBlocked, send
    first = rows[0]
    with pytest.raises(SendBlocked):
        send(trial.send_ledger.opener_for(first['call_id'], first['actor']), wire.requests[0])
    assert len(wire.requests) == 3
    assert budget.usage('pilot-A') == usage
    (tmp_path / 'failure_trace.json').write_text(json.dumps({
        'fake_only': True, 'fault': fault, 'attempts': attempts, 'budget_usage': usage,
        'calls': result.calls, 'send_rows': rows, 'actions': result.actions,
        'failure_class': record['failure_class']}, ensure_ascii=False, indent=2))


@pytest.mark.parametrize('when', ['first_request', 'both_pre_requests', 'first_response', 'after_one_post'])
def test_p05_enospc_real_send_boundary_retry_is_once_only_before_any_post(tmp_path, monkeypatch, when):
    budget = budget_for(tmp_path, charge=700)
    original = SendLedger._store
    injected, trials = [], []
    def full(self, row, kind, data):
        eligible = ((when in ('first_request', 'both_pre_requests') and kind == 'request' and row['seq'] == 1) or
                    (when == 'first_response' and kind == 'response') or
                    (when == 'after_one_post' and kind == 'request' and row['seq'] == 2))
        if eligible and len(injected) < (2 if when == 'both_pre_requests' else 1):
            injected.append((row['call_id'], kind))
            raise OSError(errno.ENOSPC, 'P05 fake disk full')
        return original(self, row, kind, data)
    monkeypatch.setattr(SendLedger, '_store', full)
    def attempt(attempt, key):
        trial, wire, _, clock, links = dialogue_trial(tmp_path, 'peer_ko', 700, budget=budget, run_key=key)
        trials.append((trial, wire))
        if trial.send_ledger.fatal is not None:
            with pytest.raises(llm.HostError):
                llm.check_trial_health(trial)  # runner's pre-next-step boundary
        else:
            dialogue_advance(trial, clock, links, 3., boundaries=())
        return {'failure_class': llm.trial_failure_class(None, trial.send_ledger)}, trial.send_ledger.fatal
    record, exc, attempts = llm.run_attempts(attempt, budget=budget, run_id='disk', start=lambda *a: None)
    assert injected
    first_trial, first_wire = trials[0]
    assert attempts[0]['failure_class'] == llm.HOST_ERROR
    assert budget.run('disk#a1')['status'] == 'failed'
    if when in ('first_request', 'both_pre_requests'):
        assert first_wire.requests == [] and attempts[0]['model_requests'] == 0
        assert [a['retried'] for a in attempts] == [True, False]
        if when == 'both_pre_requests':
            assert isinstance(exc, llm.HostError) and all(a['model_requests'] == 0 for a in attempts)
            assert budget.run('disk#a2')['status'] == 'failed'
        else:
            assert exc is None and record['failure_class'] is None
            assert budget.run('disk#a2')['status'] == 'finished'
    else:
        assert len(attempts) == 1 and not attempts[0]['retried']
        assert len(first_wire.requests) == attempts[0]['model_requests'] == 1
        assert isinstance(exc, llm.HostError)
        assert budget.usage('pilot-A')['requests'] == 1
        assert Path(budget.requests()[0]['request_path']).read_bytes() == first_wire.requests[0]
        assert llm.trial_failure_class(None, first_trial.send_ledger) == llm.HOST_ERROR
        assert not first_trial.dispatch_log
        if when == 'first_response':
            assert budget.usage('pilot-A')['usage_unknown_requests'] == 1
            assert budget.usage('pilot-A')['charged_tokens'] == 700


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
def test_p05_cap_stops_before_another_boundary_and_never_replays_paid_posts(tmp_path, condition):
    budget = budget_for(tmp_path, cap=1200, charge=700)
    trials = []
    def attempt(attempt, key):
        trial, wire, *_ = dialogue_trial(tmp_path, condition, 700, budget=budget, run_key=key)
        trials.append((trial, wire))
        with pytest.raises(BudgetExceeded):
            llm.check_trial_health(trial)
        return {'failure_class': llm.trial_failure_class(None, trial.send_ledger)}, trial.send_ledger.fatal
    _, exc, attempts = llm.run_attempts(attempt, budget=budget, run_id='cap', start=lambda *a: None)
    trial, wire = trials[0]
    assert isinstance(exc, BudgetExceeded)
    assert len(attempts) == 1 and not attempts[0]['retried']
    assert attempts[0]['model_requests'] == len(wire.requests) == 2
    assert budget.run('cap#a1')['status'] == 'failed'
    assert budget.run('cap#a1')['failure_class'] == llm.API_ERROR
    assert budget.usage('pilot-A')['known_tokens'] == budget.usage('pilot-A')['charged_tokens'] == 1200
    blocked = [r for r in trial.send_ledger.entries if r['status'] == 'blocked']
    assert len(blocked) == 1 and blocked[0]['budget_cap']
    assert (trial.send_ledger.store_dir / blocked[0]['request_path']).read_bytes()
    assert not trial.dispatch_log  # health check precedes any executor boundary/action release


@pytest.mark.parametrize('retries', [None, 1, 2, True])
def test_p05_driver_refuses_scheduler_retry_configuration_before_any_send(tmp_path, retries):
    budget = budget_for(tmp_path)
    wire = DialogueWire(700, fault='429')
    driver = llm.LiveDriver(PROFILE, budget=budget, cohort_id='pilot-A', wire=wire)
    driver.start_run('r#a1', bundle_id=zi.EXECUTION_BUNDLE_ID, bundle_sha256='b', record={})
    adapter = driver.adapter(run_key='r#a1', store_dir=tmp_path / 'wire')
    policy = tm.CallPolicy(max_retries=retries) if retries is not None else None
    with pytest.raises(ContractViolation, match='call_policy.max_retries=0'):
        zi.IntegratedTrial(dialogue_scenario(), condition='no_comm', seed=700, links=links_for([0.]),
                           horizon_s=3., map_bundle=BUNDLE, actor='gemini_proxy', model_adapter=adapter,
                           policy=policy)
    assert wire.requests == [] and budget.requests() == [] and adapter.send_ledger.entries == []
