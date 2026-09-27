"""Same-file source migration with real SQLite transactions and offline wires."""
import json
import socket
import sqlite3
from types import SimpleNamespace

import pytest

from harness.zone_pilot_budget import PilotBudget, BudgetExceeded, canonical, sha
from harness.zone_pilot_reconcile import reconcile, require_preflight
from scripts import run_zone_study_pilot as runner
from test_zone_study_review_r9 import PROFILE, fixture_wire, run_mock_cli
from harness.zone_pilot_ledger import PilotSendLedger


def identity(version):
    return {'source_head': f'committed-v{version}', 'source_root': '/offline',
            'files': {'harness/llm_completion.py': str(version)},
            'rgb_execution_bundle': {'id': f'rgb-standard-dispatch-v{version}',
                                     'sha256': str(version), 'effective': {'unchanged': True}},
            'requested_settings': {'temperature': 0}, 'proxy': PROFILE}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('migration must never contact a model')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket.socket, 'connect_ex', refuse)


def review(budget):
    snapshot = budget.snapshot()
    return {'reason': 'PR #194: strict single JSON fence; v62 -> v63',
            'expected_identity_sha256': sha(canonical(snapshot['meta']['identity']).encode()),
            'expected_state_sha256': sha(canonical([snapshot['sends'], snapshot['runs']]).encode())}


def reserve(budget, tokens=235408):
    return budget.reserve({'run_id': 'preflight-01', 'trial_id': 'no_comm',
                           'call_id': 'call-0001-r1', 'ledger_seq': 1,
                           'request_path': '/missing-offline-request', 'body_sha256': 'unknown'},
                          {'reserved_tokens': tokens, 'per_upstream_tokens': tokens // 2})


def raw_history(path):
    with sqlite3.connect(path) as db:
        return {table: [list(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]
                for table in ('sends', 'runs')}


def test_legacy_db_migrates_in_place_without_changing_failed_or_unknown_spend(tmp_path):
    budget = PilotBudget.create(tmp_path / 'budget.sqlite', identity=identity(62))
    budget.start_run('preflight-01', 'preflight', {'output': '/unchanged'})
    sent = reserve(budget)
    budget.settle(sent['reservation_id'], status='completion_rejected',
                  provider_usage={'prompt_tokens': 10285, 'completion_tokens': 98, 'total_tokens': 10622})
    budget.finish_run('preflight-01', status='failed', manifest_sha256='original-manifest-sha')
    reserve(budget, tokens=100)  # unknown consumption remains reserved, never reset
    before, sql_before = budget.snapshot(), raw_history(budget.path)
    with pytest.raises(ValueError, match='frozen pilot source'):
        PilotBudget(budget.path, identity=identity(63))
    audit = budget.migrate_source(identity(63), **review(budget))
    reopened = PilotBudget(budget.path, identity=identity(63))
    after = reopened.snapshot()
    assert raw_history(budget.path) == sql_before
    assert after['sends'] == before['sends'] and after['runs'] == before['runs']
    assert after['reserved_attempts'] == before['reserved_attempts'] == 4
    assert after['reserved_tokens'] == before['reserved_tokens'] == 235508
    assert after['meta']['pilot_id'] == before['meta']['pilot_id']
    assert after['meta']['budget_path'] == str(budget.path)
    assert after['meta']['attempt_cap'] == 600 and after['meta']['token_cap'] == 5_000_000
    assert after['source_migrations'] == [audit]
    assert audit['from_meta'] == before['meta']
    assert audit['preserved_sql_history_sha256'] == sha(canonical(sql_before).encode())
    assert audit['refunds'] == 0 and after['meta']['source_revision'] == 1
    assert not reconcile(after)['complete']  # resealing cannot invent upstream evidence
    with pytest.raises(ValueError, match='frozen pilot source'):
        PilotBudget(budget.path, identity=identity(62))
    for mutation in (lambda: reserve(budget),
                     lambda: budget.start_run('stale', 'preflight', {}),
                     lambda: budget.finish_run('preflight-01', status='recorded', manifest_sha256='x'),
                     lambda: budget.settle(after['sends'][-1]['reservation_id'], status='failed')):
        with pytest.raises(ValueError, match='budget source changed'):
            mutation()
    assert raw_history(budget.path) == sql_before


@pytest.mark.parametrize('cap', ['tokens', 'attempts'])
def test_migration_does_not_restore_exhausted_capacity(tmp_path, cap):
    budget = PilotBudget.create(tmp_path / 'budget.sqlite', identity=identity(62))
    if cap == 'tokens':
        reserve(budget, tokens=5_000_000)
    else:
        for _ in range(300):
            reserve(budget, tokens=2)
    before = budget.snapshot()
    budget.migrate_source(identity(63), **review(budget))
    new = PilotBudget(budget.path, identity=identity(63))
    with pytest.raises(BudgetExceeded):
        reserve(new, tokens=2)
    assert new.snapshot()['reserved_tokens'] == before['reserved_tokens']
    assert new.snapshot()['reserved_attempts'] == before['reserved_attempts']


@pytest.mark.parametrize('problem', ['running', 'stale_state', 'wrong_identity', 'settings',
                                     'bundle_reuse', 'effective', 'no_reason', 'no_op', 'path_only'])
def test_migration_refusals_are_atomic(tmp_path, problem):
    budget = PilotBudget.create(tmp_path / 'budget.sqlite', identity=identity(62))
    target, options = identity(63), review(budget)
    if problem == 'running':
        budget.start_run('active', 'preflight', {})
        options = review(budget)
    elif problem == 'stale_state':
        reserve(budget)
    elif problem == 'wrong_identity':
        options['expected_identity_sha256'] = 'wrong'
    elif problem == 'settings':
        target['requested_settings']['temperature'] = 1
    elif problem == 'bundle_reuse':
        target['rgb_execution_bundle']['id'] = identity(62)['rgb_execution_bundle']['id']
    elif problem == 'effective':
        target['rgb_execution_bundle']['effective'] = {}
    elif problem == 'no_reason':
        options['reason'] = ' '
    elif problem in ('no_op', 'path_only'):
        target = identity(62)
        if problem == 'path_only':
            target['source_root'] = '/other-worktree'
    before = budget.snapshot()
    with pytest.raises(ValueError):
        budget.migrate_source(target, **options)
    assert budget.snapshot() == before


def test_second_migration_chains_and_detects_missing_or_corrupt_audit(tmp_path):
    budget = PilotBudget.create(tmp_path / 'budget.sqlite', identity=identity(62))
    budget.migrate_source(identity(63), **review(budget))
    budget = PilotBudget(budget.path, identity=identity(63))
    prior = budget.snapshot()['source_migrations'][0]
    second = budget.migrate_source(identity(64), **review(budget))
    current = PilotBudget(budget.path, identity=identity(64))
    assert current.snapshot()['source_migrations'] == [prior, second]
    assert second['from_meta']['source_migration_sha256'] == prior['sha256']
    with sqlite3.connect(budget.path) as db:
        db.execute("UPDATE source_migrations SET record='{}' WHERE revision=1")
    with pytest.raises(ValueError, match='audit chain'):
        PilotBudget(budget.path)


def test_r12_same_bundle_source_remigration_preserves_hash_chain_and_spend(tmp_path):
    budget = PilotBudget.create(tmp_path / 'budget.sqlite', identity=identity(62))
    reserve(budget)
    first = budget.migrate_source(identity(63), **review(budget))
    budget = PilotBudget(budget.path, identity=identity(63))
    before, history = budget.snapshot(), raw_history(budget.path)
    target = {**identity(63), 'source_head': 'review-r12',
              'files': {**identity(63)['files'], 'harness/zone_pilot_budget.py': 'r12'}}
    second = budget.migrate_source(target, **review(budget))
    after = PilotBudget(budget.path, identity=target).snapshot()
    assert after['source_migrations'] == [first, second]
    assert second['from_meta']['source_migration_sha256'] == first['sha256']
    assert second['from_meta'] == before['meta']
    assert after['meta']['source_migration_sha256'] == second['sha256']
    assert sha(canonical({k: v for k, v in second.items() if k != 'sha256'}).encode()) == second['sha256']
    assert after['meta']['identity']['rgb_execution_bundle'] == before['meta']['identity']['rgb_execution_bundle']
    assert raw_history(budget.path) == history
    assert after['sends'] == before['sends'] and after['runs'] == before['runs']
    assert (after['reserved_attempts'], after['reserved_tokens']) == (2, 235408)
    assert after['meta']['pilot_id'] == before['meta']['pilot_id']
    assert after['meta']['attempt_cap'] == 600 and after['meta']['token_cap'] == 5_000_000
    with pytest.raises(ValueError, match='budget source changed'):
        reserve(budget)
    assert not reconcile(after)['complete']
    with sqlite3.connect(budget.path) as db:
        db.execute("DELETE FROM source_migrations WHERE revision=1")
    with pytest.raises(ValueError, match='audit chain'):
        PilotBudget(budget.path)


def test_migration_db_transaction_rolls_back_if_seal_write_fails(tmp_path):
    budget = PilotBudget.create(tmp_path / 'budget.sqlite', identity=identity(62))
    before = budget.snapshot()
    with sqlite3.connect(budget.path) as db:
        db.execute("CREATE TRIGGER fail_meta BEFORE UPDATE ON meta BEGIN SELECT RAISE(ABORT, 'injected'); END")
    with pytest.raises(sqlite3.IntegrityError, match='injected'):
        budget.migrate_source(identity(63), **review(budget))
    assert budget.snapshot() == before


def test_old_successful_preflight_cannot_authorize_a_new_source(tmp_path, monkeypatch):
    budget, manifest = run_mock_cli(tmp_path, monkeypatch)
    require_preflight(budget.snapshot(), {'complete': True}, manifest)
    # Legacy minimal test identity has no bundle. This explicit source upgrade
    # retains its existing settings and adds a distinct bundle identity.
    target = {**budget.meta['identity'], 'source_head': 'new-source',
              'rgb_execution_bundle': {'id': 'rgb-standard-dispatch-v63', 'sha256': 'new'}}
    budget.migrate_source(target, **review(budget))
    current = PilotBudget(budget.path, identity=target)
    with pytest.raises(ValueError, match='new four-condition preflight'):
        require_preflight(current.snapshot(), {'complete': True}, manifest)
    assert current.snapshot()['runs'][0]['status'] == 'recorded'
    assert current.snapshot()['reserved_attempts'] == 8


def setup_cli(tmp_path, monkeypatch):
    budget = PilotBudget.create(tmp_path / 'budget.sqlite', identity=identity(62))
    reserve(budget)
    monkeypatch.setattr(runner, 'proxy_profile', lambda *a: PROFILE)
    monkeypatch.setattr(runner, 'source_identity', lambda *a: identity(63))
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=''))
    options = review(budget)
    args = ['--migrate-source', '--budget-file', str(budget.path), '--output', str(tmp_path / 'migration'),
            '--migration-reason', options['reason'],
            '--from-identity-sha256', options['expected_identity_sha256'],
            '--expected-state-sha256', options['expected_state_sha256']]
    return budget, args


def test_cli_migration_receipt_readback_and_unresolved_restart_gate(tmp_path, monkeypatch, capsys):
    budget, args = setup_cli(tmp_path, monkeypatch)
    assert runner.main(args) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed['network_calls'] == printed['refunds'] == 0
    after = PilotBudget(budget.path, identity=identity(63)).snapshot()
    assert json.loads((tmp_path / 'migration/source-migration.json').read_text()) == after['source_migrations'][0]
    assert printed['reserved_tokens'] == after['reserved_tokens'] == 235408
    with pytest.raises(ValueError, match='prior pilot sends unresolved'):
        runner.main(['--execute', '--budget-file', str(budget.path), '--output', str(tmp_path / 'retry')])
    assert not (tmp_path / 'retry').exists()


def test_committed_db_audit_survives_receipt_write_failure(tmp_path, monkeypatch):
    budget, args = setup_cli(tmp_path, monkeypatch)
    write = runner.write_new
    def fail_receipt(path, value):
        if path.name == 'source-migration.json':
            raise OSError('injected full disk after commit')
        return write(path, value)
    monkeypatch.setattr(runner, 'write_new', fail_receipt)
    with pytest.raises(OSError, match='injected'):
        runner.main(args)
    after = PilotBudget(budget.path, identity=identity(63)).snapshot()
    assert len(after['source_migrations']) == 1 and after['reserved_tokens'] == 235408
    assert (tmp_path / 'migration/migration-proposal.json').is_file()
    assert not (tmp_path / 'migration/source-migration.json').exists()
    assert runner.main(['--reconcile-only', '--budget-file', str(budget.path),
                        '--output', str(tmp_path / 'recovered-audit')]) == 2
    recovered = json.loads((tmp_path / 'recovered-audit/reconciliation.json').read_text())
    assert recovered['source_migrations'] == after['source_migrations']


def test_cli_dirty_source_cannot_migrate(tmp_path, monkeypatch):
    budget, args = setup_cli(tmp_path, monkeypatch)
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=' M source.py'))
    with pytest.raises(ValueError, match='commit reviewed source'):
        runner.main(args)
    assert not budget.snapshot()['source_migrations']


def test_failed_run_migrate_then_new_four_call_preflight_keeps_original_cost(tmp_path, monkeypatch):
    """Full CLI continuation with offline, explicitly synthetic billing evidence."""
    budget = PilotBudget.create(tmp_path / 'budget.sqlite', identity=identity(62))
    monkeypatch.setattr(runner, 'proxy_profile', lambda *a: PROFILE)
    monkeypatch.setattr(runner, 'source_identity', lambda *a: identity(62))
    monkeypatch.setattr(runner, 'runtime_identity', lambda *a: {'pid': 0, 'offline_injection': True})
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=''))
    def ledger(reason):
        def create(**kwargs):
            kwargs['wire'] = fixture_wire(kwargs['context']['condition'], reason)
            return PilotSendLedger(**kwargs)
        return create
    monkeypatch.setattr(runner, 'PilotSendLedger', ledger('length'))
    base = ['--execute', '--acknowledge-upstream-finish-limitation', '--budget-file', str(budget.path)]
    assert runner.main(base + ['--output', str(tmp_path / 'failed')]) == 2
    before = budget.snapshot()
    assert len(before['sends']) == 1 and before['runs'][0]['status'] == 'failed'
    sent = before['sends'][0]
    terminal = {'reservation_id': sent['reservation_id'], 'body_sha256': sent['body_sha256'],
                'proxy_request_id': 'offline-proxy-request', 'proxy_response_id': sent['proxy_response_id'],
                'upstream_attempts': [{'id': 'offline-upstream', 'terminal': True, 'usage': sent['provider_usage']}]}
    evidence_path = tmp_path / 'synthetic-upstream.jsonl'
    evidence_path.write_text(json.dumps(terminal) + '\n')
    terminal['evidence'] = {'path': str(evidence_path), 'sha256': sha(evidence_path.read_bytes())}
    telemetry = tmp_path / 'telemetry.jsonl'
    telemetry.write_text(json.dumps(terminal) + '\n')
    assert reconcile(before, [terminal])['complete']
    budget.migrate_source(identity(63), **review(budget))
    monkeypatch.setattr(runner, 'source_identity', lambda *a: identity(63))
    monkeypatch.setattr(runner, 'PilotSendLedger', ledger('stop'))
    assert runner.main(base + ['--output', str(tmp_path / 'new-preflight'),
                              '--upstream-telemetry', str(telemetry)]) == 2  # new calls need their own evidence
    current = PilotBudget(budget.path, identity=identity(63)).snapshot()
    manifest = json.loads((tmp_path / 'new-preflight/manifest.json').read_text())
    assert manifest['status'] == 'recorded' and manifest['source_revision'] == 1
    assert manifest['accepted_upstream_unverified_calls'] == 4
    assert current['sends'][0] == before['sends'][0] and current['runs'][0] == before['runs'][0]
    assert current['reserved_attempts'] == 10
    assert current['reserved_tokens'] == sum(s['reserved_tokens'] for s in current['sends'])
    assert current['reserved_tokens'] > before['reserved_tokens']
    require_preflight(current, {'complete': True}, manifest)  # verify source/call binding independently
    with pytest.raises(ValueError, match='reconciliation incomplete'):
        require_preflight(current, reconcile(current, [terminal]), manifest)
