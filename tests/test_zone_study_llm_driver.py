"""B7 real multi-turn model driver (PR #254): fake model wire only.

No model call, socket, MuJoCo import or physical step. The client is the
registered GeminiProxyCompleter; only its wire is a local function.
"""
import base64
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
    assert zi.EXECUTION_BUNDLE_ID == 'zone-pair-v81-carry-dr-general'   # b-v6g carry stage probe (v80 + opt-in b-v6g)
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
    prereg = {'student': {}, 't0_s': 0., 'speech_cap_profile': 'main_pilot_10_30'}
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
