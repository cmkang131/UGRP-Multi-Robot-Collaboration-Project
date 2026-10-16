"""Explicit budget settlement counterexamples; no physical/model execution."""
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import sqlite3

import pytest

from harness.llm_completion import assess_completion
from harness.zone_pilot_budget import BudgetExceeded, PilotBudget, canonical, sha, state_sha256
from harness.zone_pilot_reconcile import reconcile, require_preflight
from harness.zone_pilot_ledger import PilotSendLedger
from scripts import run_zone_study_pilot as runner
from test_zone_pilot_proxy_log import case, build, RETRY, USAGE
from test_zone_study_review_r9 import PROFILE, fixture_wire, run_mock_cli


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('settlement must never call a model or socket')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket.socket, 'connect_ex', refuse)
    monkeypatch.setattr(runner, 'proxy_profile', refuse)


def update_sent(budget, **updates):
    with sqlite3.connect(budget.path) as db:
        sent = json.loads(db.execute('SELECT record FROM sends').fetchone()[0])
        sent.update(updates)
        db.execute('UPDATE sends SET record=?', (canonical(sent),))
    return sent


def fixture(tmp_path, *, retry=False, status='ok', bound='exact', send_status='response_received'):
    budget, log = case(tmp_path, extra=RETRY if retry else '')
    completion = assess_completion({'choices': [{'finish_reason': 'stop', 'message': {'content': '{}'}}]})
    sent = update_sent(budget, status=send_status, completion=completion)
    wire = Path(sent['request_path']).parent
    trial = {'trial_id': sent['trial_id'], 'calls': [{'request_id': sent['call_id'], 'status': status,
             'cost_terms': {'usage_known': True, 'usage_bound': bound,
                            'provider_usage': USAGE, 'completion': completion}}]}
    trial_path = wire.parent / 'trial.json'
    trial_path.write_text(canonical(trial))
    manifest = {'run_id': 'run', 'pilot_id': budget.meta['pilot_id'],
                'trials': [{'trial_id': sent['trial_id'], 'trial_path': str(trial_path),
                            'trial_sha256': sha(trial_path.read_bytes())}]}
    output = wire.parent.parent
    budget.start_run('run', 'preflight', {'output': str(output)})
    manifest_sha = runner.write_new(output / 'manifest.json', manifest)
    budget.finish_run('run', status='recorded', manifest_sha256=manifest_sha)
    _, _, evidence = build(tmp_path, budget, log)
    return budget, evidence / 'telemetry.jsonl'


def review(tmp_path, budget, telemetry, *, name='review.json'):
    rows = [json.loads(line) for line in telemetry.read_text().splitlines()]
    report = reconcile(budget.snapshot(), rows)
    path = tmp_path / name
    digest = runner.write_new(path, report)
    return {'report_path': path, 'telemetry_path': telemetry, 'expected_report_sha256': digest,
            'expected_state_sha256': report['state_sha256']}


def test_dry_run_then_explicit_settlement_preserves_history_and_uses_total_tokens(tmp_path):
    budget, telemetry = fixture(tmp_path)
    before, raw = budget.snapshot(), budget.path.read_bytes()
    args = review(tmp_path, budget, telemetry)
    plan = budget.settle_reconciled(**args, dry_run=True)
    assert budget.path.read_bytes() == raw and budget.snapshot() == before
    assert plan['before'] == {'attempts': 2, 'tokens': 2000}
    assert plan['after'] == {'attempts': 1, 'tokens': 140}  # prompt+completion is only 120
    assert not plan['audits'] and len(plan['eligible']) == 1
    receipt = budget.settle_reconciled(**args)
    after = PilotBudget(budget.path).snapshot()
    assert after['sends'] == before['sends'] and after['runs'] == before['runs']
    assert after['meta'] == before['meta'] and after['reserved_tokens'] == 2000
    assert after['charged_attempts'] == 1 and after['charged_tokens'] == 140
    assert state_sha256(after) != state_sha256(before)
    audit = after['budget_settlements'][0]
    assert receipt['audits'] == [audit]
    assert audit['telemetry_sha256'] == sha(telemetry.read_bytes())
    assert audit['report_sha256'] == args['expected_report_sha256']
    assert audit['before'] == plan['before'] and audit['after'] == plan['after']
    assert audit['evidence']['sha256'] and audit['trial_sha256'] and audit['manifest_sha256']


def test_duplicate_settlement_old_and_fresh_review_cannot_release_twice(tmp_path):
    budget, telemetry = fixture(tmp_path)
    args = review(tmp_path, budget, telemetry)
    budget.settle_reconciled(**args)
    before = budget.path.read_bytes()
    with pytest.raises(ValueError, match='state changed'):
        budget.settle_reconciled(**args)
    args = review(tmp_path, budget, telemetry, name='fresh.json')
    key = budget.snapshot()['sends'][0]['reservation_id']
    with pytest.raises(ValueError, match='already_settled'):
        budget.settle_reconciled(**args, reservation_ids=[key])
    receipt = budget.settle_reconciled(**args)
    assert not receipt['eligible'] and receipt['before'] == receipt['after']
    assert budget.path.read_bytes() == before


@pytest.mark.parametrize('damage', ['report_hash', 'state_hash', 'state_race', 'report_forged',
                                   'telemetry_hash', 'log_hash', 'response_hash', 'trial_hash', 'manifest_hash'])
def test_review_or_evidence_hash_mismatch_never_releases_budget(tmp_path, damage):
    budget, telemetry = fixture(tmp_path)
    args = review(tmp_path, budget, telemetry)
    if damage == 'report_hash':
        args['report_path'].write_text('{}')
    elif damage == 'state_hash':
        args['expected_state_sha256'] = '0' * 64
    elif damage == 'state_race':
        budget.reserve({}, {'reserved_tokens': 10, 'per_upstream_tokens': 5})
    elif damage == 'report_forged':
        report = json.loads(args['report_path'].read_text())
        report['calls'][0]['actual_upstream_attempts'] = 0
        args['report_path'].write_text(canonical(report))
        args['expected_report_sha256'] = sha(args['report_path'].read_bytes())
    elif damage == 'telemetry_hash':
        rows = [json.loads(line) for line in telemetry.read_text().splitlines()]
        rows[0]['evidence']['sha256'] = '0' * 64
        telemetry.write_text(canonical(rows[0]) + '\n')
    elif damage == 'log_hash':
        (tmp_path / 'proxy.log').write_text('changed\n')
    else:
        path = {'response_hash': tmp_path / 'run/no_comm/wire/response.json',
                'trial_hash': tmp_path / 'run/no_comm/trial.json',
                'manifest_hash': tmp_path / 'run/manifest.json'}[damage]
        path.write_text(path.read_text() + ' ')
    raw = budget.path.read_bytes()
    key = budget.snapshot()['sends'][0]['reservation_id']
    with pytest.raises(ValueError):
        budget.settle_reconciled(**args, reservation_ids=[key])
    assert budget.path.read_bytes() == raw
    assert budget.snapshot()['charged_tokens'] >= 2000


@pytest.mark.parametrize('kind', ['unreconciled', 'unknown', 'failed', 'protocol_failed', 'partial',
                                 'no_usage', 'usage_excess', 'retry', 'running', 'missing_trial'])
def test_ineligible_explicit_selection_is_refused_and_keeps_full_reservation(tmp_path, kind):
    budget, telemetry = fixture(tmp_path, retry=kind == 'retry',
                                status='parse_error' if kind == 'protocol_failed' else 'ok',
                                bound='lower_bound' if kind == 'partial' else 'exact',
                                send_status='failed' if kind == 'failed' else 'response_received')
    if kind == 'unreconciled':
        telemetry.write_text('')
    elif kind == 'unknown':
        update_sent(budget, status='reserved_unknown')
    elif kind == 'no_usage':
        update_sent(budget, provider_usage=None)
    elif kind == 'usage_excess':
        update_sent(budget, provider_usage={**USAGE, 'total_tokens': 1001})
    elif kind == 'running':
        budget.start_run('unfinished', 'cohort', {})
    elif kind == 'missing_trial':
        (tmp_path / 'run/no_comm/trial.json').unlink()
    args = review(tmp_path, budget, telemetry)
    raw = budget.path.read_bytes()
    key = budget.snapshot()['sends'][0]['reservation_id']
    with pytest.raises(ValueError):
        budget.settle_reconciled(**args, reservation_ids=[key])
    assert budget.path.read_bytes() == raw
    assert budget.snapshot()['charged_tokens'] == 2000


def test_partial_report_only_settles_eligible_sends(tmp_path):
    budget, telemetry = fixture(tmp_path)
    other = budget.reserve({'call_id': 'unknown', 'trial_id': 'unknown', 'ledger_seq': 2,
                            'request_path': '/absent', 'body_sha256': 'unknown'},
                           {'reserved_tokens': 400, 'per_upstream_tokens': 200})
    args = review(tmp_path, budget, telemetry)
    assert not json.loads(args['report_path'].read_text())['complete']
    result = budget.settle_reconciled(**args)
    assert len(result['eligible']) == len(result['skipped']) == 1
    assert result['skipped'][0]['reservation_id'] == other['reservation_id']
    assert result['after'] == {'attempts': 3, 'tokens': 540}


def id_evidence(tmp_path, budget, usages):
    sent = budget.snapshot()['sends'][0]
    row = {'reservation_id': sent['reservation_id'], 'body_sha256': sent['body_sha256'],
           'proxy_request_id': 'real-id', 'proxy_response_id': sent['proxy_response_id'],
           'upstream_attempts': [{'id': f'up-{i}', 'terminal': True, 'usage': usage}
                                 for i, usage in enumerate(usages)]}
    raw = tmp_path / 'id-evidence.jsonl'
    raw.write_text(canonical(row) + '\n')
    row['evidence'] = {'path': str(raw), 'sha256': sha(raw.read_bytes())}
    telemetry = tmp_path / 'id-telemetry.jsonl'
    telemetry.write_text(canonical(row) + '\n')
    return telemetry


@pytest.mark.parametrize('kind', ['exact', 'excess', 'partial', 'too_many_attempts'])
def test_id_evidence_sums_all_provider_totals_and_rejects_excess(tmp_path, kind):
    budget, _ = fixture(tmp_path)
    first = {**USAGE, 'total_tokens': 1001 if kind == 'excess' else 180}
    if kind == 'partial':
        first['usage_bound'] = 'lower_bound'
    usages = [first, USAGE] if kind != 'too_many_attempts' else [USAGE] * 3
    telemetry = id_evidence(tmp_path, budget, usages)
    args = review(tmp_path, budget, telemetry)
    key = budget.snapshot()['sends'][0]['reservation_id']
    if kind == 'exact':
        result = budget.settle_reconciled(**args)
        assert result['after'] == {'attempts': 2, 'tokens': 320}
    else:
        with pytest.raises(ValueError):
            budget.settle_reconciled(**args, reservation_ids=[key])
        assert budget.snapshot()['charged_tokens'] == 2000


def test_new_reservations_use_net_debit_without_raising_caps(tmp_path):
    budget, telemetry = fixture(tmp_path)
    budget.settle_reconciled(**review(tmp_path, budget, telemetry))
    # Would exceed 5M if the original 2000 were still used for admission.
    budget.reserve({}, {'reserved_tokens': 4_999_860, 'per_upstream_tokens': 2_499_930})
    assert budget.snapshot()['charged_tokens'] == 5_000_000
    with pytest.raises(BudgetExceeded):
        budget.reserve({}, {'reserved_tokens': 2, 'per_upstream_tokens': 1})
    assert budget.meta['token_cap'] == 5_000_000 and budget.meta['attempt_cap'] == 600


@pytest.mark.parametrize('damage', ['audit_hash', 'sql_debit', 'delete_audit'])
def test_corrupt_audit_cannot_authorize_new_spend(tmp_path, damage):
    budget, telemetry = fixture(tmp_path)
    budget.settle_reconciled(**review(tmp_path, budget, telemetry))
    with sqlite3.connect(budget.path) as db:
        if damage == 'audit_hash':
            db.execute("UPDATE budget_settlements SET sha256='bad'")
        elif damage == 'sql_debit':
            db.execute('UPDATE sends SET tokens=1')
        else:
            db.execute('DELETE FROM budget_settlements')
    with pytest.raises(ValueError):
        budget.reserve({}, {'reserved_tokens': 2, 'per_upstream_tokens': 1})


def test_cli_dry_run_settlement_and_receipt_write_recovery(tmp_path, monkeypatch):
    budget, telemetry = fixture(tmp_path)
    args = review(tmp_path, budget, telemetry)
    cli = ['--settle-reconciled', '--budget-file', str(budget.path),
           '--upstream-telemetry', str(telemetry), '--reconciliation-report', str(args['report_path']),
           '--expected-report-sha256', args['expected_report_sha256'],
           '--expected-state-sha256', args['expected_state_sha256']]
    raw = budget.path.read_bytes()
    assert runner.main(cli + ['--dry-run', '--output', str(tmp_path / 'dry')]) == 0
    assert budget.path.read_bytes() == raw
    original = runner.write_new
    def fail_receipt(path, value):
        if path.name == 'budget-settlement.json':
            raise OSError('receipt disk full after commit')
        return original(path, value)
    monkeypatch.setattr(runner, 'write_new', fail_receipt)
    with pytest.raises(OSError, match='after commit'):
        runner.main(cli + ['--output', str(tmp_path / 'apply')])
    out = tmp_path / 'recover'
    assert runner.main(['--reconcile-only', '--budget-file', str(budget.path),
                        '--upstream-telemetry', str(telemetry), '--output', str(out)]) == 0
    recovered = json.loads((out / 'reconciliation.json').read_text())
    assert len(recovered['budget_settlements']) == 1 and recovered['charged_tokens'] == 140


def test_settlement_rolls_back_audit_and_debit_together(tmp_path):
    budget, telemetry = fixture(tmp_path)
    args = review(tmp_path, budget, telemetry)
    with sqlite3.connect(budget.path) as db:
        db.execute("CREATE TRIGGER fail_debit BEFORE UPDATE OF tokens ON sends "
                   "BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    raw = budget.path.read_bytes()
    with pytest.raises(sqlite3.IntegrityError, match='injected failure'):
        budget.settle_reconciled(**args)
    assert budget.path.read_bytes() == raw
    assert not budget.snapshot()['budget_settlements']


def test_state_and_report_checks_run_inside_begin_immediate(tmp_path, monkeypatch):
    budget, telemetry = fixture(tmp_path)
    args = review(tmp_path, budget, telemetry)
    connect, statements = budget._connect, []
    def traced():
        db = connect()
        db.set_trace_callback(statements.append)
        return db
    monkeypatch.setattr(budget, '_connect', traced)
    budget.settle_reconciled(**args, dry_run=True)
    assert statements[0] == 'BEGIN IMMEDIATE'
    assert statements[-1] == 'COMMIT'
    assert not any(s.startswith(('UPDATE', 'INSERT', 'CREATE')) for s in statements)


def test_settlement_invalidates_run_review_and_survives_source_migration(tmp_path):
    budget, telemetry = fixture(tmp_path)
    args = review(tmp_path, budget, telemetry)
    budget.settle_reconciled(**args)
    with pytest.raises(RuntimeError, match='state changed'):
        budget.start_run('stale-review', 'cohort', {}, expected_state=args['expected_state_sha256'])
    before = budget.snapshot()
    identity = {**budget.meta['identity'], 'source_head': 'new-reviewed-head',
                'rgb_execution_bundle': {'id': 'rgb-standard-dispatch-v63', 'sha256': 'fixture'}}
    budget.migrate_source(identity, reason='offline source migration after settlement',
                          expected_identity_sha256=sha(canonical(budget.meta['identity']).encode()),
                          expected_state_sha256=state_sha256(before))
    after = PilotBudget(budget.path, identity=identity).snapshot()
    assert after['budget_settlements'] == before['budget_settlements']
    assert after['charged_tokens'] == 140 and after['charged_attempts'] == 1


def test_attempt_cap_uses_settled_count_and_stays_at_600(tmp_path):
    budget, telemetry = fixture(tmp_path)
    budget.settle_reconciled(**review(tmp_path, budget, telemetry))
    for _ in range(299):
        budget.reserve({}, {'reserved_tokens': 2, 'per_upstream_tokens': 1})
    assert budget.snapshot()['charged_attempts'] == 599
    with pytest.raises(BudgetExceeded):
        budget.reserve({}, {'reserved_tokens': 2, 'per_upstream_tokens': 1})


def synthetic_telemetry(tmp_path, snapshot):
    rows = [{'reservation_id': sent['reservation_id'], 'body_sha256': sent['body_sha256'],
             'proxy_request_id': f'offline-proxy-{i}', 'proxy_response_id': sent['proxy_response_id'],
             'upstream_attempts': [{'id': f'offline-upstream-{i}', 'terminal': True,
                                    'usage': sent['provider_usage']}]}
            for i, sent in enumerate(snapshot['sends'])]
    raw = tmp_path / 'synthetic-upstream.jsonl'
    raw.write_text(''.join(canonical(row) + '\n' for row in rows))
    evidence = {'path': str(raw), 'sha256': sha(raw.read_bytes())}
    telemetry = tmp_path / 'synthetic-telemetry.jsonl'
    telemetry.write_text(''.join(canonical({**row, 'evidence': evidence}) + '\n' for row in rows))
    return telemetry


def fingerprint(path):
    stat = path.stat()
    return {'sha256': sha(path.read_bytes()), 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


@pytest.fixture(params=['synthetic', 'real_memory'])
def cli_history(request, tmp_path, monkeypatch):
    """The optional real-data regression writes ONLY to an in-memory clone."""
    if request.param == 'synthetic':
        budget, manifest = run_mock_cli(tmp_path, monkeypatch)
        telemetry = synthetic_telemetry(tmp_path, budget.snapshot())
        yield budget, telemetry, manifest
        return

    root = os.environ.get('UGRP_ZONE_PILOT_REGRESSION_ROOT')
    if root is None:
        pytest.skip('set UGRP_ZONE_PILOT_REGRESSION_ROOT for the read-only real DB regression')
    source = Path(root).resolve() / 'budget.sqlite'
    telemetry = source.parent / 'log-evidence-v63-05/telemetry.jsonl'
    sidecars = [Path(str(source) + suffix) for suffix in ('-wal', '-shm', '-journal')]
    assert not any(path.exists() for path in sidecars), 'immutable backup requires a quiescent DB'
    original = fingerprint(source)
    originals = {source: original, telemetry: fingerprint(telemetry)}
    with closing(sqlite3.connect(':memory:')) as memory:
        try:
            # immutable+ro prevents even journal/SHM creation on the original.
            with closing(sqlite3.connect(source.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
                db.backup(memory)
                before = PilotBudget._snapshot(db)
            assert memory.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'

            class MemoryBudget(PilotBudget):
                def _connect(self):
                    return memory

            # Keep the original meta/path/source chain; only the test's connection
            # is replaced. The production copy/path guard remains unchanged.
            monkeypatch.setattr(runner, 'PilotBudget', MemoryBudget)
            budget = MemoryBudget(source)
            assert budget.snapshot() == before
            rows = [json.loads(line) for line in telemetry.read_text().splitlines() if line.strip()]
            evidence = set(originals)
            for sent in before['sends']:
                wire = Path(sent['request_path']).parent
                evidence.update((Path(sent['request_path']), wire / sent['ledger']['response_path'],
                                 wire.parent / 'trial.json'))
            evidence.update(Path(run['output']) / 'manifest.json' for run in before['runs'])
            evidence.update(Path(row['evidence']['path']) for row in rows)
            originals.update({path: fingerprint(path) for path in evidence if path not in originals})
            report = reconcile(before, rows)
            assert report['complete']
            run = next(run for run in reversed(before['runs'])
                       if run['stage'] == 'preflight' and run['status'] == 'recorded'
                       and run.get('source_revision', 0) == before['meta'].get('source_revision', 0))
            manifest = json.loads((Path(run['output']) / 'manifest.json').read_text())
            assert require_preflight(before, report, manifest)['admitted']
            yield budget, telemetry, manifest
        finally:
            assert {path: fingerprint(path) for path in originals} == originals
            assert not any(path.exists() for path in sidecars)
            print(canonical({'real_database_unchanged': original, 'original_files_verified': len(originals)}))


@pytest.mark.parametrize('stage', ['preflight', 'cohort', 'migrated_preflight'])
def test_cli_starts_after_settlement(cli_history, tmp_path, monkeypatch, stage):
    budget, telemetry, preflight = cli_history
    before = budget.snapshot()
    receipt = budget.settle_reconciled(**review(tmp_path, budget, telemetry))
    settled = budget.snapshot()
    assert receipt['eligible'] and receipt['audits']
    assert settled['sends'] == before['sends'] and settled['runs'] == before['runs']
    assert settled['meta'] == before['meta'] and settled['source_migrations'] == before['source_migrations']
    assert state_sha256(settled) != state_sha256(before)
    assert receipt['after_state_sha256'] == state_sha256(settled)
    print(canonical({'stage': stage, 'settled_calls': len(receipt['eligible']),
                     'skipped_calls': len(receipt['skipped']),
                     'charged_before': receipt['before'], 'charged_after': receipt['after']}))

    if stage == 'migrated_preflight':
        identity = {**budget.meta['identity'], 'source_head': 'offline-r14-reviewed-source',
                    'rgb_execution_bundle': budget.meta['identity'].get(
                        'rgb_execution_bundle', {'id': 'offline-fixture', 'sha256': 'fixture'})}
        budget.migrate_source(identity, reason='offline R14 continuation test',
                              expected_identity_sha256=sha(canonical(budget.meta['identity']).encode()),
                              expected_state_sha256=state_sha256(settled))
        budget = type(budget)(budget.path, identity=identity)
        with pytest.raises(ValueError, match='new four-condition preflight'):
            require_preflight(budget.snapshot(), {'complete': True}, preflight)
        stage = 'preflight'

    monkeypatch.setattr(runner, 'proxy_profile', lambda *a: PROFILE)
    monkeypatch.setattr(runner, 'source_identity', lambda *a: budget.meta['identity'])
    monkeypatch.setattr(runner, 'require_committed_source', lambda *a: None)
    monkeypatch.setattr(runner, 'runtime_identity', lambda *a: {'pid': 0, 'offline_injection': True})

    def ledger(**kwargs):
        kwargs['wire'] = fixture_wire(kwargs['context']['condition'], 'stop')
        return PilotSendLedger(**kwargs)

    monkeypatch.setattr(runner, 'PilotSendLedger', ledger)
    out = tmp_path / ('after-settlement-' + stage)
    cli = ['--execute', '--acknowledge-upstream-finish-limitation', '--stage', stage,
           '--budget-file', str(budget.path), '--upstream-telemetry', str(telemetry), '--output', str(out)]
    if stage == 'cohort':
        path = tmp_path / 'preflight-manifest.json'
        runner.write_new(path, preflight)
        cli += ['--preflight-manifest', str(path)]
    # All calls use a fixture wire. New synthetic sends intentionally lack
    # upstream evidence, so the existing reconciliation gate still returns 2.
    assert runner.main(cli) == 2
    manifest = json.loads((out / 'manifest.json').read_text())
    after = budget.snapshot()
    count = 4 if stage == 'preflight' else 12
    assert manifest['status'] == after['runs'][-1]['status'] == 'recorded'
    assert manifest['stage'] == after['runs'][-1]['stage'] == stage
    assert manifest['source_revision'] == budget.meta.get('source_revision', 0)
    assert manifest['accepted_upstream_unverified_calls'] == len(manifest['call_links']) == count
    assert not manifest['reconciliation_complete']
    if stage == 'cohort':
        assert manifest['cohort_gate']['admitted']
    assert after['sends'][:len(before['sends'])] == before['sends']
    assert after['runs'][:-1] == before['runs']
    assert after['budget_settlements'] == settled['budget_settlements']
    assert after['charged_attempts'] == settled['charged_attempts'] + 2 * count
    assert after['charged_tokens'] == settled['charged_tokens'] + sum(
        sent['reserved_tokens'] for sent in after['sends'][len(before['sends']):])
