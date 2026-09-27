"""Offline #222 counterexamples: no sockets, models, or simulator."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import socket
from zoneinfo import ZoneInfo

import pytest

from harness.zone_pilot_budget import PilotBudget, PROXY_SHA256, canonical, sha
from harness.zone_pilot_proxy_log import EVIDENCE_LEVEL, window_spec
from harness.zone_pilot_reconcile import reconcile, require_preflight
from scripts import build_proxy_log_telemetry as builder
from scripts import run_zone_study_pilot as runner

USAGE = {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 140}
POST = '2026-09-27 12:00:06 http "POST /v1/chat/completions HTTP/1.1" 200 -\n'
PREFIX = '2026-09-27 12:00:00 http "GET /v1/usage HTTP/1.1" 200 -\n'
SUFFIX = '2026-09-27 12:00:08 http "GET /v1/usage HTTP/1.1" 200 -\n'
RETRY = '2026-09-27 12:00:03 transient_429_retry retry_after=0s delay=1s\n'
ERROR = '2026-09-27 12:00:04 complete_exception TimeoutError: fixture\n'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('no network authorised in proxy-log tests')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket.socket, 'connect_ex', refuse)


def case(tmp_path, *, extra='', post=POST, usage=USAGE, legacy=False):
    wire = tmp_path / 'run' / 'no_comm' / 'wire'
    wire.mkdir(parents=True)
    request, response = wire / 'request.json', wire / 'response.json'
    request.write_bytes(b'{}')
    body = {'id': 'actual-response-id', 'choices': [{'message': {'content': '{}'}}]}
    if usage is not None:
        body['usage'] = usage
    response.write_text(json.dumps(body))
    epoch = int(datetime(2026, 9, 27, 12, 0, 0, tzinfo=ZoneInfo('Asia/Seoul')).timestamp())
    start, end = (epoch + 2) * 10**9 + 200_000_000, (epoch + 6) * 10**9 + 300_000_000
    for path, ns in ((request, start), (response, end)):
        os.utime(path, ns=(ns, ns))
    proxy_log = tmp_path / 'proxy.log'
    central = (extra + post).encode()
    proxy_log.write_bytes(PREFIX.encode() + central + SUFFIX.encode())
    cursor = {'available': True, 'correlated': False, 'path': str(proxy_log),
              'inode': proxy_log.stat().st_ino, 'offset': len(PREFIX.encode()),
              'end_offset': len(PREFIX.encode()) + len(central), 'sha256': sha(central)}
    budget = PilotBudget.create(tmp_path / 'budget.sqlite', identity={'source_head': 'offline-fixture'})
    reserved = budget.reserve({'request_path': str(request), 'body_sha256': sha(request.read_bytes()),
                               'call_id': 'call-1', 'trial_id': 'test-no-comm', 'run_id': 'run',
                               'ledger_seq': 1, 'proxy_source_sha256': PROXY_SHA256},
                              {'reserved_tokens': 2000, 'per_upstream_tokens': 1000})
    ledger = {'method': 'POST', 'response_path': response.name, 'provider_usage': usage}
    if not legacy:
        ledger.update(send_started_at_ns=start, response_received_at_ns=end)
    budget.settle(reserved['reservation_id'], status='completion_rejected', provider_usage=usage,
                  ledger=ledger, proxy_response_id=body['id'], proxy_log_window=cursor,
                  response_sha256=sha(response.read_bytes()))
    return budget, proxy_log


def build(tmp_path, budget, log):
    output = tmp_path / 'evidence'
    before = budget.snapshot()
    report = builder.build(before, log, output)
    rows = [json.loads(line) for line in (output / 'telemetry.jsonl').read_text().splitlines()]
    assert budget.snapshot() == before
    return report, rows, output


@pytest.mark.parametrize('legacy', [False, True])
def test_exact_single_post_get_separated_and_no_fake_ids(tmp_path, legacy):
    get = '2026-09-27 12:00:04 http "GET /v1/usage/antigravity HTTP/1.1" 200 -\n'
    budget, log = case(tmp_path, extra=get, legacy=legacy)
    report, rows, output = build(tmp_path, budget, log)
    row = rows[0]
    assert report['complete'] and report['evidence_levels'] == [EVIDENCE_LEVEL]
    assert row['post_count'] == row['other_http_request_count'] == row['actual_upstream_attempts'] == 1
    assert row['proxy_request_id'] is row['upstream_attempts'] is None
    assert row['usage_bound'] == 'exact' and row['provider_usage'] == USAGE
    assert row['window']['padding_seconds'] == 1
    assert ('mtime' in row['window']['time_source']) == legacy
    manifest = json.loads((output / 'manifest.json').read_text())
    assert manifest['evidence_level'] == EVIDENCE_LEVEL
    assert manifest['cohort_gate']['billing_evidence_levels'] == [EVIDENCE_LEVEL]
    assert manifest['cohort_gate']['admitted'] is False
    for name, digest in manifest['files_sha256'].items():
        assert sha((output / name).read_bytes()) == digest
    assert report['reserved_attempts'] == 2 and report['reserved_tokens'] == 2000 and report['refunds'] == 0
    # Billing completion does not rehabilitate a failed preflight.
    with pytest.raises(ValueError, match='four-condition'):
        require_preflight(budget.snapshot(), report, {})


@pytest.mark.parametrize('path', ['/v1/chat/completions', '/v1/embeddings', '/other'])
@pytest.mark.parametrize('second', ['01', '04', '07'])
def test_competing_post_including_padding_is_incomplete(tmp_path, path, second):
    other = f'2026-09-27 12:00:{second} http "POST {path} HTTP/1.1" 200 -\n'
    budget, log = case(tmp_path, extra=other if second < '06' else '', post=POST + (other if second > '06' else ''))
    report, _, _ = build(tmp_path, budget, log)
    assert not report['complete']
    assert 'proxy_post_window_not_exclusive' in report['calls'][0]['issues']
    with pytest.raises(ValueError, match='reconciliation incomplete'):
        require_preflight(budget.snapshot(), report, {})


@pytest.mark.parametrize('extra,attempts,complete', [(RETRY, 2, True), (ERROR, 2, True),
                                                   (RETRY + ERROR, 3, False), (RETRY * 2, 3, False)])
def test_retry_and_error_lines_consume_attempts_without_zero_usage(tmp_path, extra, attempts, complete):
    budget, log = case(tmp_path, extra=extra)
    report, rows, _ = build(tmp_path, budget, log)
    assert report['complete'] is complete
    assert rows[0]['actual_upstream_attempts'] == attempts
    assert rows[0]['usage_scope'] == 'final_proxy_response_only'
    assert rows[0]['provider_usage'] == USAGE
    assert report['reserved_attempts'] == 2 and report['refunds'] == 0


@pytest.mark.parametrize('damage', ['missing_file', 'missing_post', 'no_left_bracket', 'no_right_bracket',
                                    'broken_line', 'cursor_hash', 'rotated', 'partial_tail', 'wrong_path', 'http500'])
def test_missing_or_untrustworthy_logs_fail_closed(tmp_path, damage):
    budget, log = case(tmp_path, post='' if damage == 'missing_post' else POST)
    snapshot = budget.snapshot()
    if damage == 'missing_file':
        log.unlink()
    elif damage == 'no_left_bracket':
        log.write_text(POST + SUFFIX)
    elif damage == 'no_right_bracket':
        log.write_text(PREFIX + POST)
    elif damage == 'partial_tail':
        log.write_text(PREFIX + POST + SUFFIX.rstrip())
    elif damage == 'broken_line':
        log.write_text(PREFIX + 'unparseable POST\n' + POST + SUFFIX)
    elif damage == 'cursor_hash':
        snapshot['sends'][0]['proxy_log_window']['sha256'] = '0' * 64
    elif damage == 'rotated':
        snapshot['sends'][0]['proxy_log_window']['inode'] += 1
    elif damage == 'wrong_path':
        log.write_text(log.read_text().replace('/v1/chat/completions', '/other'))
    elif damage == 'http500':
        log.write_text(log.read_text().replace('POST /v1/chat/completions HTTP/1.1" 200',
                                              'POST /v1/chat/completions HTTP/1.1" 500'))
    report = builder.build(snapshot, log, tmp_path / 'evidence')
    assert not report['complete'] and report['calls'][0]['issues']


@pytest.mark.parametrize('usage', [None, {}, {'prompt_tokens': 100, 'completion_tokens': 20},
                                  {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
                                  {'prompt_tokens': True, 'completion_tokens': 20, 'total_tokens': 140},
                                  {**USAGE, 'total_tokens': 119}, {**USAGE, 'usage_bound': 'lower_bound'}])
def test_usage_absent_partial_or_inexact_never_passes(tmp_path, usage):
    budget, log = case(tmp_path, usage=usage)
    report, rows, _ = build(tmp_path, budget, log)
    assert not report['complete'] and rows[0]['usage_bound'] == 'unknown'


@pytest.mark.parametrize('damage', ['raw_hash', 'counter', 'window', 'fake_request_id', 'fake_attempt',
                                    'usage', 'unknown_grade', 'response_hash'])
def test_reconcile_revalidates_raw_and_claims(tmp_path, damage):
    budget, log = case(tmp_path)
    report, rows, _ = build(tmp_path, budget, log)
    assert report['complete']
    row = rows[0]
    if damage == 'raw_hash':
        Path(row['evidence']['path']).write_bytes(b'tampered\n')
    elif damage == 'counter':
        row['actual_upstream_attempts'] = 2
    elif damage == 'window':
        row['window']['padding_seconds'] = 0
    elif damage == 'fake_request_id':
        row['proxy_request_id'] = 'guessed'
    elif damage == 'fake_attempt':
        row['upstream_attempts'] = [{'id': 'guessed', 'terminal': True, 'usage': USAGE}]
    elif damage == 'usage':
        row['provider_usage']['total_tokens'] += 1
    elif damage == 'unknown_grade':
        row['evidence_level'] = 'guessed_window'
    else:
        Path(budget.snapshot()['sends'][0]['request_path']).with_name('response.json').write_text('{}')
    report = reconcile(budget.snapshot(), rows)
    assert not report['complete']
    with pytest.raises(ValueError, match='reconciliation incomplete'):
        require_preflight(budget.snapshot(), report, {})


def test_one_post_cannot_be_reused_for_two_sends(tmp_path):
    budget, log = case(tmp_path)
    _, rows, _ = build(tmp_path, budget, log)
    snapshot = budget.snapshot()
    duplicate = deepcopy(snapshot['sends'][0])
    duplicate['reservation_id'] = 'different-reservation'
    snapshot['sends'].append(duplicate)
    other = {**rows[0], 'reservation_id': duplicate['reservation_id']}
    report = reconcile(snapshot, [rows[0], other])
    assert not report['complete']
    assert 'proxy_log_post_reused_across_calls' in report['calls'][1]['issues']


def test_readonly_cli_and_reconcile_preserve_originals_and_refuse_overwrite(tmp_path, capsys):
    budget, log = case(tmp_path)
    before = sha(budget.path.read_bytes()), log.read_bytes(), budget.snapshot()
    output = tmp_path / 'cli'
    args = ['--budget-file', str(budget.path), '--proxy-log', str(log), '--output', str(output)]
    assert builder.main(args) == 0
    assert json.loads(capsys.readouterr().out)['evidence_levels'] == [EVIDENCE_LEVEL]
    assert runner.main(['--reconcile-only', '--budget-file', str(budget.path),
                        '--upstream-telemetry', str(output / 'telemetry.jsonl'),
                        '--output', str(tmp_path / 'reconciled')]) == 0
    assert json.loads(capsys.readouterr().out)['evidence_levels'] == [EVIDENCE_LEVEL]
    assert (sha(budget.path.read_bytes()), log.read_bytes(), budget.snapshot()) == before
    with pytest.raises(FileExistsError):
        builder.main(args)
    with pytest.raises(Exception, match='readonly'):
        PilotBudget(budget.path, read_only=True).start_run('forbidden', 'preflight', {})


def test_saved_call_partial_usage_rejected(tmp_path):
    budget, log = case(tmp_path)
    sent = budget.snapshot()['sends'][0]
    path = Path(sent['request_path']).parent.parent / 'trial.json'
    path.write_text(json.dumps({'trial_id': sent['trial_id'], 'calls': [{
        'request_id': sent['call_id'], 'cost_terms': {'provider_usage': USAGE,
        'usage_known': False, 'usage_bound': 'lower_bound'}}]}))
    report, _, _ = build(tmp_path, budget, log)
    assert not report['complete']
    assert 'call_usage_not_exact' in report['calls'][0]['issues']


def test_missing_half_of_wall_clock_pair_is_not_mtime_fallback(tmp_path):
    budget, _ = case(tmp_path)
    sent = budget.snapshot()['sends'][0]
    del sent['ledger']['response_received_at_ns']
    with pytest.raises(ValueError, match='times'):
        window_spec(sent, 'Asia/Seoul')


def test_proxy_evidence_sources_are_pinned_in_pilot_not_rgb_bundle(tmp_path):
    from harness.rgb_execution_bundle import source_closure, load_bundle, RUNNABLE_ID
    from tests.test_zone_study_review_r8 import PROFILE
    paths = {'harness/zone_pilot_budget.py', 'harness/zone_pilot_ledger.py',
             'harness/zone_pilot_reconcile.py', 'harness/zone_pilot_proxy_log.py',
             'scripts/run_zone_study_pilot.py', 'scripts/build_proxy_log_telemetry.py'}
    assert not paths.intersection(source_closure())
    load_bundle(RUNNABLE_ID)
    assert paths <= set(runner.source_identity(PROFILE)['files'])


def test_single_foreign_post_only_in_padding_is_not_our_send(tmp_path):
    budget, log = case(tmp_path)
    snapshot = budget.snapshot()
    cursor = snapshot['sends'][0]['proxy_log_window']
    # Contemporaneous capture contains just a GET; the lone POST is outside it.
    get = '2026-09-27 12:00:04 http "GET /v1/usage HTTP/1.1" 200 -\n'
    foreign = '2026-09-27 12:00:01 http "POST /v1/chat/completions HTTP/1.1" 200 -\n'
    log.write_text(PREFIX + foreign + get + SUFFIX)
    cursor.update(offset=len((PREFIX + foreign).encode()),
                  end_offset=len((PREFIX + foreign + get).encode()), sha256=sha(get.encode()))
    report = builder.build(snapshot, log, tmp_path / 'evidence')
    assert not report['complete']
    assert 'proxy_post_outside_sealed_send_window' in report['calls'][0]['issues']


def test_four_condition_window_gate_and_cohort_manifest(tmp_path, monkeypatch):
    import io
    from types import SimpleNamespace
    from harness import zone_pilot_ledger as pl
    from harness.zone_send_ledger import completion_body
    from harness.zone_study_offline import FixtureActor
    from tests.test_zone_study_review_r8 import PROFILE

    identity = {'source_head': 'offline-exclusive-window'}
    monkeypatch.setattr(runner, 'proxy_profile', lambda *a: PROFILE)
    monkeypatch.setattr(runner, 'source_identity', lambda *a: identity)
    monkeypatch.setattr(runner, 'runtime_identity', lambda *a: {'pid': 0, 'offline_injection': True})
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=''))
    log = tmp_path / 'proxy.log'
    log.write_text(PREFIX)
    epoch = int(datetime(2026, 9, 27, 12, tzinfo=ZoneInfo('Asia/Seoul')).timestamp())
    current = [epoch]
    monkeypatch.setattr(pl.time, 'time_ns', lambda: current[0] * 10**9 + 200_000_000)

    def log_at(second, method):
        stamp = datetime.fromtimestamp(second, ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
        with log.open('a') as stream:
            stream.write(f'{stamp} http "{method} HTTP/1.1" 200 -\n')

    actual = pl.PilotSendLedger
    def ledger(**kwargs):
        current[0] += 10  # non-overlapping padded send windows
        condition = kwargs['context']['condition']
        def wire(request, *, timeout=None):
            messages = json.loads(request.data)['messages']
            user = next(p['text'] for p in messages[-1]['content'] if p['type'] == 'text')
            actor = json.loads(user)['robot_id']
            reply = FixtureActor(actor, condition, 11).respond({
                'messages': [messages[0], {'role': 'user', 'content': user}]})
            response = json.loads(completion_body(reply, usage=USAGE))
            response['id'] = 'actual-fixture-' + request.get_header('X-ugrp-call-id')
            current[0] += 3
            log_at(current[0], 'POST /v1/chat/completions')
            return io.BytesIO(json.dumps(response).encode())
        kwargs.update(wire=wire, proxy_log=log)
        return actual(**kwargs)
    monkeypatch.setattr(runner, 'PilotSendLedger', ledger)
    budget = PilotBudget.create(tmp_path / 'budget.sqlite', identity=identity)
    preflight = tmp_path / 'preflight'
    args = ['--execute', '--budget-file', str(budget.path)]
    assert runner.main(args + ['--acknowledge-upstream-finish-limitation', '--output', str(preflight)]) == 2
    log_at(current[0] + 3, 'GET /v1/usage')  # prove coverage after the last padded window
    manifest = json.loads((preflight / 'manifest.json').read_text())
    report, rows, evidence = build(tmp_path, budget, log)
    assert report['complete'] and len(rows) == 4
    gate = require_preflight(budget.snapshot(), report, manifest)
    assert gate['admitted'] and gate['billing_evidence_levels'] == [EVIDENCE_LEVEL]
    with pytest.raises(ValueError, match='unsupported reconciliation evidence level'):
        require_preflight(budget.snapshot(), {**report, 'evidence_levels': ['guessed']}, manifest)
    cohort = tmp_path / 'cohort'
    assert runner.main(args + ['--stage', 'cohort', '--preflight-manifest', str(preflight / 'manifest.json'),
                               '--upstream-telemetry', str(evidence / 'telemetry.jsonl'),
                               '--output', str(cohort)]) == 2  # new sends still need new evidence
    saved = json.loads((cohort / 'manifest.json').read_text())
    assert saved['cohort_gate'] == gate
    assert EVIDENCE_LEVEL in saved['reconciliation_evidence_levels']
    assert 'unresolved' in saved['reconciliation_evidence_levels']
    assert all(link['evidence_level'] == 'unresolved' for link in saved['call_links'])
    assert saved['reconciliation_complete'] is False
