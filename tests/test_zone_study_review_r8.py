"""R8 regressions: no live network; mocked HTTP handler and deterministic race."""
import io
import threading
from email.message import Message
from urllib.error import HTTPError
from urllib.request import HTTPHandler
from urllib.response import addinfourl

import pytest

from harness.zone_event_scheduler import AttemptBudget
from harness.zone_send_ledger import send
from harness.zone_study_llm_transport import live_send_ledger


def test_redirect_never_makes_a_second_request(monkeypatch, tmp_path):
    requests = []

    def http_open(self, req):
        requests.append(req.get_method())
        headers = Message()
        if len(requests) == 1:
            headers['Location'] = 'http://127.0.0.1:1/redirect'
        response = addinfourl(io.BytesIO(b'{}'), headers, req.full_url,
                              302 if len(requests) == 1 else 200)
        response.msg = 'mock'
        return response

    monkeypatch.setattr(HTTPHandler, 'http_open', http_open)
    ledger = live_send_ledger(store_dir=tmp_path / 'wire')
    ledger.attach(lambda _: None, owner='test')
    with pytest.raises(HTTPError, match='302'):
        send(ledger.opener_for('call', 'r1'), url='http://127.0.0.1:1/start')
    assert requests == ['POST']
    assert ledger.sends() == 1


def test_cap_two_retry_race_cannot_send_three():
    # R8 schedule: first send; retry pauses AFTER reading remaining=1;
    # r2 reserves/sends; retry resumes and used+reserved becomes 3 at cap=2.
    budget = AttemptBudget(total=2)
    assert budget.reserve('r1')
    sent = ['first']
    paused, resume = threading.Event(), threading.Event()
    original = budget.remaining
    errors = []

    def remaining(actor=None):
        left = original(actor)
        if threading.current_thread().name == 'retry':
            paused.set()
            assert resume.wait(2)
        return left

    budget.remaining = remaining

    def retry():
        try:
            if budget.reserve('r1'):
                sent.append('retry')
        except RuntimeError as exc:
            errors.append(str(exc))
        finally:
            paused.set()

    worker = threading.Thread(target=retry, name='retry')
    worker.start()
    assert paused.wait(2)
    try:
        if budget.reserve('r2'):
            sent.append('r2')
    finally:
        resume.set()
        worker.join(2)
    assert len(sent) <= 2, f'cap=2 -> sends={len(sent)}: {sent}'
    assert errors and 'single-thread' in errors[0]

# Everything below uses offline wires, real adapter/scheduler, and SQLite.
import json
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request

from harness import zone_pilot_budget as pb
from harness import zone_pilot_ledger as pl
from harness.zone_pilot_network import NetworkFence
from harness.zone_pilot_reconcile import reconcile, require_preflight
from harness.zone_send_ledger import ScriptedWire, completion_body
from harness.zone_study_contract import MAIN_CONDITIONS
from harness.zone_study_offline import FixtureActor
from harness.zone_study_scenarios import load as load_scenario, scenario_ids
from scripts import run_zone_study_pilot as runner

URL = 'http://127.0.0.1:8391/v1/chat/completions'
USAGE = {'prompt_tokens': 150, 'completion_tokens': 80, 'total_tokens': 240}
PROFILE = {'source_sha256': pb.PROXY_SHA256, 'source_path': '/not-executed', 'url': URL}
IDENTITY = {'source_head': 'offline-test'}


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError('offline R8 tests must never access the network')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket.socket, 'connect_ex', refuse)


def make_trial(tmp_path, condition='peer_ko', failure=None, wire=None, stage='preflight'):
    budget = pb.PilotBudget.create(tmp_path / 'budget.sqlite', identity=IDENTITY)
    scenario = load_scenario(scenario_ids()[0])
    fixture = FixtureActor('r1', condition, 11)

    def success(request, *, timeout=None):
        payload = json.loads(request.data)
        messages = payload['messages']
        user = messages[-1]['content']
        if isinstance(user, list):
            user = next(p['text'] for p in user if p['type'] == 'text')
        raw = fixture.respond({'messages': [messages[0], {'role': 'user', 'content': user}]})
        response = json.loads(completion_body(raw, usage=USAGE))
        response['id'] = 'proxy-response-test'
        return io.BytesIO(json.dumps(response).encode())

    injected = wire or (ScriptedWire([failure]) if failure is not None else success)
    trial = runner.AdapterTrial(scenario, condition=condition, seed=11, stage=stage,
                                run_id='test-' + condition, budget=budget, profile=PROFILE,
                                runtime=None, output=tmp_path / 'run' / condition, wire=injected)
    return trial, budget


@pytest.mark.parametrize('condition', MAIN_CONDITIONS)
@pytest.mark.parametrize('failure', [
    HTTPError(URL, 429, 'rate limited', {}, None),
    HTTPError(URL, 503, 'upstream unavailable', {}, None),
    TimeoutError('after send'), b'{broken',
])
def test_failed_requests_remain_spent_and_execute_nothing(tmp_path, condition, failure):
    trial, budget = make_trial(tmp_path, condition, failure)
    result = trial.run_adapter()
    assert not result['actions'] and not result['messages']
    assert trial.send_ledger.sends() == 1
    snapshot = budget.snapshot()
    assert snapshot['reserved_attempts'] == 2 and snapshot['reserved_tokens'] > 2 * 8192
    assert len(snapshot['sends']) == 1
    assert not reconcile(snapshot)['complete']
    again = pb.PilotBudget(budget.path, identity=IDENTITY)
    assert again.snapshot()['reserved_tokens'] == snapshot['reserved_tokens']


@pytest.mark.parametrize('condition', MAIN_CONDITIONS)
def test_effective_settings_real_text_cost_and_condition_isolation(tmp_path, condition):
    trial, budget = make_trial(tmp_path, condition)
    result = trial.run_adapter()
    assert trial.send_ledger.sends() == 1 and len(result['calls']) == 1
    assert result['calls'][0]['status'] == 'ok'
    saved = budget.snapshot()['sends'][0]
    assert saved['effective_settings'] == pb.EFFECTIVE
    assert saved['envelope']['output_reasoning_bound'] == 8192
    assert saved['provider_usage'] == USAGE  # total includes 10 hidden reasoning tokens
    assert saved['actual_upstream_attempts'] is None
    raw_response = Path(trial.send_ledger.store_dir / saved['ledger']['response_path']).read_bytes()
    raw = json.loads(raw_response)['choices'][0]['message']['content']
    assert result['calls'][0]['output_tokens'] == runner.pk.count_tokens(raw)
    assert result['channel']['inbox_agrees_with_scheduler']
    if condition == 'no_comm':
        assert result['channel']['sent'] == 0
    if condition == 'leader_ko':
        assert result['channel']['follower_to_follower'] == 0
    if condition == 'structured':
        assert result['channel']['free_text_messages'] == 0
    assert not reconcile(budget.snapshot())['complete']  # legacy logs cannot close the chain


@pytest.mark.parametrize('kind', ['request', 'response', 'settle'])
def test_storage_failure_never_releases_action(tmp_path, monkeypatch, kind):
    trial, budget = make_trial(tmp_path)
    original = trial.send_ledger._store
    if kind == 'settle':
        def fail(*a, **kw):
            raise OSError('injected disk full at settlement')
        monkeypatch.setattr(budget, 'settle', fail)
    else:
        def store(row, stage, data):
            if stage == kind:
                raise OSError('injected disk full')
            return original(row, stage, data)
        monkeypatch.setattr(trial.send_ledger, '_store', store)
    result = trial.run_adapter()
    assert not result['actions'] and not result['messages']
    snapshot = pb.PilotBudget(budget.path).snapshot()
    if kind == 'request':
        assert trial.send_ledger.sends() == 0 and snapshot['reserved_attempts'] == 0
        assert trial.send_ledger.entries[0]['reason'] == 'store_failed'
    else:
        assert trial.send_ledger.sends() == 1 and snapshot['reserved_attempts'] == 2
        if kind == 'settle':
            assert snapshot['sends'][0]['status'] == 'reserved_unknown'


def test_late_response_keeps_usage_and_never_executes(tmp_path, monkeypatch):
    trial, budget = make_trial(tmp_path)
    actual = trial.send_ledger._wire
    clock = [100.0]

    def late(request, *, timeout=None):
        response = actual(request, timeout=timeout)
        clock[0] += timeout + 1
        return response

    monkeypatch.setattr(trial.send_ledger, '_wire', late)
    monkeypatch.setattr(pl.time, 'monotonic', lambda: clock[0])
    result = trial.run_adapter()
    assert not result['actions'] and not result['messages']
    saved = budget.snapshot()['sends'][0]
    assert saved['late'] and saved['provider_usage'] == USAGE and saved['reserved_attempts'] == 2


def test_concurrent_pilot_send_hard_assertion_and_no_wire(tmp_path):
    trial, budget = make_trial(tmp_path)
    ledger = trial.send_ledger
    errors = []

    def worker():
        try:
            send(ledger.opener_for('unowned', 'r1'))
        except RuntimeError as exc:
            errors.append(str(exc))
    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(2)
    assert errors and 'single-thread' in errors[0]
    assert ledger.sends() == 0 and budget.snapshot()['reserved_attempts'] == 0


def test_network_fence_blocks_other_openers_sockets_children_and_second_connect():
    guard = NetworkFence(URL)
    with guard:
        with pytest.raises(RuntimeError, match='only the ledger'):
            sys.audit('socket.connect', None, ('127.0.0.1', 8391))
        with pytest.raises(RuntimeError, match='subprocess'):
            sys.audit('subprocess.Popen', 'curl', [], None, None)
        with pytest.raises(RuntimeError, match='only the ledger'):
            socket.socket.sendall(None, b'not sent')
        with guard.wire():
            with pytest.raises(RuntimeError, match='unapproved'):
                sys.audit('socket.connect', None, ('127.0.0.1', 8392))
            sys.audit('socket.connect', None, ('127.0.0.1', 8391))
            with pytest.raises(RuntimeError, match='second connection'):
                sys.audit('socket.connect', None, ('127.0.0.1', 8391))


def test_pipeline_direct_network_bypass_is_blocked_before_any_send(tmp_path, monkeypatch):
    trial, budget = make_trial(tmp_path)
    def bypass(call):
        sys.audit('socket.connect', None, ('127.0.0.1', 8391))
    monkeypatch.setattr(trial, 'prepare_call', bypass)
    result = trial.run_adapter()
    assert not result['actions'] and not result['messages']
    assert trial.send_ledger.sends() == 0 and budget.snapshot()['reserved_attempts'] == 0


def reserve(budget, n=1, tokens=10):
    for index in range(n):
        budget.reserve({'call_id': str(index), 'trial_id': 'unit'},
                       {'reserved_tokens': tokens, 'per_upstream_tokens': tokens // 2})


def test_global_attempt_cap_is_atomic_across_db_connections_and_restarts(tmp_path):
    budget = pb.PilotBudget.create(tmp_path / 'pilot.sqlite', identity=IDENTITY)
    reserve(budget, n=299)
    barrier = threading.Barrier(8)
    def attempt(_):
        reopened = pb.PilotBudget(budget.path, identity=IDENTITY)
        barrier.wait(3)
        try:
            reserve(reopened)
            return True
        except pb.BudgetExceeded:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(attempt, range(8)))
    assert sum(outcomes) == 1
    assert pb.PilotBudget(budget.path).snapshot()['reserved_attempts'] == 600


def test_five_million_tokens_reserves_before_send_and_never_refunds(tmp_path):
    budget = pb.PilotBudget.create(tmp_path / 'pilot.sqlite', identity=IDENTITY)
    reserve(budget, tokens=5_000_000)
    row = budget.snapshot()['sends'][0]
    budget.settle(row['reservation_id'], status='failed', provider_usage=None)
    with pytest.raises(pb.BudgetExceeded):
        reserve(pb.PilotBudget(budget.path))
    assert budget.snapshot()['reserved_tokens'] == 5_000_000
    with pytest.raises(FileExistsError):
        pb.PilotBudget.create(budget.path, identity=IDENTITY)
    with pytest.raises(ValueError, match='changed'):
        pb.PilotBudget(budget.path, identity={'source_head': 'changed'})


def test_oversized_provider_usage_stops_response_and_cannot_refund(tmp_path):
    trial, budget = make_trial(tmp_path)
    trial.send_ledger._wire = ScriptedWire([completion_body('ignored', usage={
        'prompt_tokens': 5_000_000, 'completion_tokens': 1, 'total_tokens': 5_000_001})])
    result = trial.run_adapter()
    assert not result['actions'] and budget.snapshot()['sends'][0]['status'] == 'usage_exceeds_reservation'


def test_running_process_restart_does_not_reset_or_start_a_second_run(tmp_path):
    budget = pb.PilotBudget.create(tmp_path / 'pilot.sqlite', identity=IDENTITY)
    budget.start_run('first', 'preflight', {})
    reserve(budget)
    with pytest.raises(RuntimeError, match='unfinished'):
        pb.PilotBudget(budget.path).start_run('restart', 'preflight', {})
    assert budget.snapshot()['reserved_attempts'] == 2


def test_real_execution_requires_explicit_existing_budget_before_any_other_work(tmp_path):
    with pytest.raises(SystemExit):
        runner.main(['--execute', '--output', str(tmp_path / 'run')])
    assert list(tmp_path.iterdir()) == []


def test_proxy_file_is_only_read_and_unknown_version_refused(tmp_path):
    source = tmp_path / 'proxy.py'
    source.write_text('# unreviewed')
    before = source.read_bytes()
    with pytest.raises(ValueError, match='not audited'):
        pl.proxy_profile(source, URL)
    assert source.read_bytes() == before


def test_dry_run_prepares_four_conditions_without_network_or_budget(tmp_path):
    result = runner.dry_run(tmp_path / 'dry', 'preflight', load_scenario(scenario_ids()[0]), 11, PROFILE)
    assert result['network_calls'] == 0 and result['model_calls'] == 0
    assert {p['condition'] for p in result['plans']} == set(MAIN_CONDITIONS)
    assert result['preflight_reserved_attempts_bound'] == 8
    assert result['preflight_reserved_tokens_bound'] < 5_000_000
    assert result['effective_settings']['model'] == 'gemini-3.8-flash-low'
    for plan in result['plans']:
        assert pb.sha(Path(plan['request_path']).read_bytes()) == plan['saved_sha256']


def test_missing_or_uncorrelated_proxy_logs_never_unlock_cohort(tmp_path):
    trial, budget = make_trial(tmp_path)
    log = tmp_path / 'proxy.log'
    log.write_text('before\n')
    cursor = pl.log_cursor(log)
    with log.open('a') as stream:
        stream.write('transient_429_retry retry_after=1s delay=2s\n')
    window = pl.log_window(cursor)
    assert len(window['events']) == 1 and window['correlated'] is False
    trial.run_adapter()
    snapshot = budget.snapshot()
    report = reconcile(snapshot)
    with pytest.raises(ValueError, match='incomplete'):
        require_preflight(snapshot, report, {})
    assert report['calls'][0]['upstream_attempts'] is None


def test_linked_upstream_evidence_reconciles_but_never_refunds(tmp_path):
    trial, budget = make_trial(tmp_path)
    trial.run_adapter()
    snapshot = budget.snapshot()
    row = snapshot['sends'][0]
    telemetry = {'reservation_id': row['reservation_id'], 'body_sha256': row['body_sha256'],
                 'proxy_request_id': 'captured-proxy-request', 'proxy_response_id': row['proxy_response_id'],
                 'upstream_attempts': [{'id': 'upstream-1', 'terminal': True, 'usage': USAGE}]}
    source = tmp_path / 'upstream.jsonl'
    source.write_text(json.dumps(telemetry) + '\n')
    telemetry['evidence'] = {'path': str(source), 'sha256': pb.sha(source.read_bytes())}
    report = reconcile(snapshot, [telemetry])
    assert report['complete'] and report['refunds'] == 0
    assert budget.snapshot()['reserved_attempts'] == 2
    source.write_text('{}\n')
    assert not reconcile(snapshot, [telemetry])['complete']


def test_offline_cli_preflight_records_chain_and_blocks_cohort_without_telemetry(tmp_path, monkeypatch):
    # Exercise the actual --execute branch with an injected wire; no sockets.
    # Only the coordinator may run it with the installed proxy.
    from types import SimpleNamespace
    monkeypatch.setattr(runner, 'proxy_profile', lambda *a: PROFILE)
    monkeypatch.setattr(runner, 'source_identity', lambda *a: IDENTITY)
    monkeypatch.setattr(runner, 'runtime_identity', lambda *a: {'pid': 0, 'offline_injection': True})
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=''))
    actual = pl.PilotSendLedger

    def ledger(**kwargs):
        condition = kwargs['context']['condition']
        def wire(request, *, timeout=None):
            body = json.loads(request.data)
            messages = body['messages']
            user = next(p['text'] for p in messages[-1]['content'] if p['type'] == 'text')
            actor = json.loads(user)['robot_id']
            raw = FixtureActor(actor, condition, 11).respond({
                'messages': [messages[0], {'role': 'user', 'content': user}]})
            response = json.loads(completion_body(raw, usage=USAGE))
            response['id'] = 'response-' + request.get_header('X-ugrp-call-id')
            return io.BytesIO(json.dumps(response).encode())
        kwargs['wire'] = wire
        return actual(**kwargs)
    monkeypatch.setattr(runner, 'PilotSendLedger', ledger)
    path = tmp_path / 'global.sqlite'
    budget = pb.PilotBudget.create(path, identity=IDENTITY)
    preflight = tmp_path / 'preflight'
    # Four successes still return 2 until per-upstream evidence exists.
    assert runner.main(['--execute', '--acknowledge-upstream-finish-limitation', '--budget-file', str(path), '--output', str(preflight)]) == 2
    manifest = json.loads((preflight / 'manifest.json').read_text())
    assert len(manifest['trials']) == 4
    assert [t['sent'] for t in manifest['trials']] == [1] * 4
    assert [t['successful_calls'] for t in manifest['trials']] == [1] * 4
    assert budget.snapshot()['reserved_attempts'] == 8
    with pytest.raises(ValueError, match='incomplete'):
        runner.main(['--execute', '--stage', 'cohort', '--budget-file', str(path),
                     '--output', str(tmp_path / 'cohort-blocked'),
                     '--preflight-manifest', str(preflight / 'manifest.json')])
    snapshot = budget.snapshot()
    rows = [{'reservation_id': r['reservation_id'], 'body_sha256': r['body_sha256'],
             'proxy_request_id': 'request-' + r['reservation_id'], 'proxy_response_id': r['proxy_response_id'],
             'upstream_attempts': [{'id': 'upstream-' + r['reservation_id'], 'terminal': True, 'usage': USAGE}]}
            for r in snapshot['sends']]
    raw = tmp_path / 'captured-upstream.jsonl'
    raw.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    evidence = {'path': str(raw), 'sha256': pb.sha(raw.read_bytes())}
    linked = [{**r, 'evidence': evidence} for r in rows]
    telemetry = tmp_path / 'telemetry.jsonl'
    telemetry.write_text(''.join(json.dumps(r) + '\n' for r in linked))
    require_preflight(snapshot, reconcile(snapshot, linked), manifest)
    assert runner.main(['--execute', '--stage', 'cohort', '--budget-file', str(path),
                        '--output', str(tmp_path / 'cohort'), '--upstream-telemetry', str(telemetry),
                        '--preflight-manifest', str(preflight / 'manifest.json')]) == 2
    after = pb.PilotBudget(path).snapshot()
    cohort = json.loads((tmp_path / 'cohort' / 'manifest.json').read_text())
    assert cohort['status'] == 'recorded'
    assert len(cohort['trials']) == 4
    assert [t['successful_calls'] for t in cohort['trials']] == [3] * 4
    assert after['reserved_attempts'] == 32  # 4 preflight + 12 cohort POSTs, all doubled
    assert after['reserved_tokens'] >= snapshot['reserved_tokens']
    assert after['reserved_tokens'] <= 5_000_000 and after['reserved_attempts'] <= 600


def test_proxy_retry_two_attempts_reconciles_with_nonbillable_429(tmp_path):
    trial, budget = make_trial(tmp_path)
    trial.run_adapter()
    row = budget.snapshot()['sends'][0]
    telemetry = {'reservation_id': row['reservation_id'], 'body_sha256': row['body_sha256'],
                 'proxy_request_id': 'proxy', 'proxy_response_id': row['proxy_response_id'],
                 'upstream_attempts': [
                     {'id': 'rate-limit', 'terminal': True, 'provider_confirmed_nonbillable': True,
                      'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}},
                     {'id': 'retry', 'terminal': True, 'usage': USAGE}]}
    raw = tmp_path / 'upstream.jsonl'
    raw.write_text(json.dumps(telemetry) + '\n')
    telemetry['evidence'] = {'path': str(raw), 'sha256': pb.sha(raw.read_bytes())}
    assert reconcile(budget.snapshot(), [telemetry])['complete']
    assert budget.snapshot()['reserved_attempts'] == 2


def test_empty_crash_recovery_preserves_budget_and_never_replays(tmp_path):
    budget = pb.PilotBudget.create(tmp_path / 'budget.sqlite', identity=IDENTITY)
    budget.start_run('interrupted-before-send', 'preflight', {})
    report = reconcile(budget.snapshot())
    saved = tmp_path / 'reconciliation.json'
    runner.write_new(saved, report)
    budget.recover_run('interrupted-before-send', report=report, report_path=saved)
    budget.start_run('restart', 'preflight', {})
    assert budget.snapshot()['reserved_tokens'] == 0
    assert budget.snapshot()['runs'][0]['status'] == 'recovered_without_actions'


@pytest.mark.parametrize('status', [301, 302, 303, 307, 308])
def test_all_redirect_statuses_are_refused_without_followup(tmp_path, monkeypatch, status):
    requests = []
    def http_open(self, req):
        requests.append(req.full_url)
        headers = Message()
        headers['Location'] = URL
        response = addinfourl(io.BytesIO(b'{}'), headers, req.full_url, status)
        response.msg = 'redirect'
        return response
    monkeypatch.setattr(HTTPHandler, 'http_open', http_open)
    ledger = live_send_ledger(store_dir=tmp_path)
    ledger.attach(lambda _: None, owner='offline')
    with pytest.raises(HTTPError):
        send(ledger.opener_for('call', 'r1'), url=URL)
    assert len(requests) == ledger.sends() == 1


def test_sim_horizon_late_reply_is_charged_but_never_delivered(tmp_path):
    trial, budget = make_trial(tmp_path)
    trial.horizon_s = .001
    result = trial.run_adapter()
    assert not result['actions'] and not result['messages']
    assert result['censored'] and budget.snapshot()['reserved_attempts'] == 2


def test_state_change_after_reconciliation_refuses_new_run(tmp_path):
    budget = pb.PilotBudget.create(tmp_path / 'budget.sqlite', identity=IDENTITY)
    before = budget.snapshot()
    reserve(budget)
    with pytest.raises(RuntimeError, match='state changed'):
        budget.start_run('raced', 'preflight', {},
                         expected_state=pb.sha(pb.canonical([before['sends'], before['runs']]).encode()))


def test_unbudgeted_live_model_transport_is_refused(tmp_path):
    from harness.zone_study_llm_transport import ModelCallTransport
    class Pipeline:
        def prepare_call(self, call):
            pass
        def finish_call(self, *args):
            pass
    with pytest.raises(ValueError, match='persistent'):
        ModelCallTransport(Pipeline(), send_ledger=live_send_ledger(store_dir=tmp_path), client_factory=lambda x: x)


def test_usage_over_reservation_latches_pilot_stop(tmp_path):
    budget = pb.PilotBudget.create(tmp_path / 'budget.sqlite', identity=IDENTITY)
    reserve(budget)
    row = budget.snapshot()['sends'][0]
    with pytest.raises(pb.BudgetExceeded, match='exceeds'):
        budget.settle(row['reservation_id'], status='response_received', provider_usage=USAGE)
    with pytest.raises(pb.BudgetExceeded, match='halted'):
        reserve(pb.PilotBudget(budget.path))


def test_positive_envelopes_required(tmp_path):
    budget = pb.PilotBudget.create(tmp_path / 'budget.sqlite', identity=IDENTITY)
    for tokens in (0, -10, True, 1.2):
        with pytest.raises(ValueError, match='positive'):
            budget.reserve({}, {'reserved_tokens': tokens, 'per_upstream_tokens': tokens})
