"""Offline diagnostic ONLY. Original budget is never opened for writing.

The production constructor intentionally refuses a copied budget. This local
test binds the unchanged SQLite snapshot to a temporary copy, without editing
its meta, source-migration chain, sends, runs or original evidence paths.
No production copy override is introduced; this is not a runnable pilot DB.
"""
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

from harness.zone_pilot_budget import PilotBudget, sha
from harness.zone_pilot_reconcile import reconcile
from harness.rgb_execution_bundle import source_closure, load_bundle, RUNNABLE_ID
from scripts.run_zone_study_pilot import write_new


SOURCE = Path('/Users/changmin/projects/ugrp/outputs/zone-study-adapter-pilot-r10/budget.sqlite')
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent


def fingerprint(path):
    stat = path.stat()
    return {'sha256': sha(path.read_bytes()), 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def main():
    assert not any(Path(str(SOURCE) + suffix).exists() for suffix in ('-wal', '-journal'))
    original = fingerprint(SOURCE)
    directory = Path(tempfile.mkdtemp(prefix='ugrp-budget-settlement-')).resolve()
    copy = directory / 'budget.sqlite'
    shutil.copy2(SOURCE, copy)
    assert fingerprint(copy) == original
    with sqlite3.connect(copy) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    # Isolated test binding: all inherited methods connect to `copy` only.
    budget = object.__new__(PilotBudget)
    budget.path, budget.read_only = copy, False
    before = budget.snapshot()
    budget.meta = before['meta']
    assert budget.meta['budget_path'] == str(SOURCE) and copy != SOURCE
    try:
        PilotBudget(copy)
    except ValueError as exc:
        assert 'path mismatch' in str(exc)
    else:
        raise AssertionError('production must reject copied budget')
    preferred = SOURCE.parent / 'log-evidence-v63-05/telemetry.jsonl'
    telemetry = preferred if preferred.exists() else SOURCE.parent / 'log-evidence-v63-04/telemetry.jsonl'
    rows = [json.loads(line) for line in telemetry.read_text().splitlines() if line.strip()]
    evidence = {SOURCE, telemetry}
    for sent in before['sends']:
        request = Path(sent['request_path'])
        evidence.update((request, request.parent / sent['ledger']['response_path'], request.parent.parent / 'trial.json'))
    evidence.update(Path(run['output']) / 'manifest.json' for run in before['runs'])
    evidence.update(Path(row['evidence']['path']) for row in rows if row.get('evidence', {}).get('path'))
    originals = {str(path): fingerprint(path) for path in sorted(evidence)}
    report = reconcile(before, rows)
    report_path = OUT / 'reconciliation.json'
    report_sha = write_new(report_path, report)
    args = {'report_path': report_path, 'telemetry_path': telemetry,
            'expected_report_sha256': report_sha, 'expected_state_sha256': report['state_sha256']}
    raw_copy = copy.read_bytes()
    dry = budget.settle_reconciled(**args, dry_run=True)
    assert copy.read_bytes() == raw_copy and budget.snapshot() == before
    write_new(OUT / 'dry-run.json', dry)
    applied = budget.settle_reconciled(**args)
    after = budget.snapshot()
    assert after['sends'] == before['sends'] and after['runs'] == before['runs']
    assert after['meta'] == before['meta'] and after['source_migrations'] == before['source_migrations']
    assert applied['after'] == dry['after']
    assert after['charged_tokens'] == dry['after']['tokens']
    assert after['charged_attempts'] == dry['after']['attempts']
    assert len(after['budget_settlements']) == len(dry['eligible'])
    write_new(OUT / 'copy-applied.json', applied)
    try:
        budget.settle_reconciled(**args)
    except ValueError as exc:
        assert 'state changed' in str(exc)
    else:
        raise AssertionError('replayed settlement must fail')
    assert originals == {str(path): fingerprint(path) for path in sorted(evidence)}
    assert fingerprint(SOURCE) == original
    changed = set(subprocess.check_output(['git', 'diff', '--name-only'], text=True).splitlines())
    changed.update(('harness/zone_pilot_settlement.py', 'tests/test_zone_pilot_settlement.py'))
    closure = source_closure()
    _, bundle_sha = load_bundle(RUNNABLE_ID)
    overlap = sorted(changed & closure)
    assert not overlap
    summary = {'base_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
               'original_database': str(SOURCE), 'original_fingerprint_before_and_after': original,
               'original_files_verified': len(originals), 'originals_unchanged': True,
               'copy_database': str(copy), 'copy_sha256_after_settlement': sha(copy.read_bytes()),
               'copy_binding': 'test_only; original meta/path/chain preserved; production rejects copy',
               'telemetry': str(telemetry), 'telemetry_sha256': sha(telemetry.read_bytes()),
               'preferred_v63_05_present': preferred.exists(),
               'sends': len(before['sends']), 'report_complete': report['complete'],
               'reconciled_sends': sum(c['reconciled'] for c in report['calls']),
               'usage_total_all_responses': sum(s['provider_usage']['total_tokens'] for s in before['sends']),
               'usage_total_reconciled_responses': sum(c['provider_usage']['total_tokens'] for c in report['calls'] if c['reconciled']),
               'eligible': len(dry['eligible']), 'skipped': dry['skipped'],
               'before': dry['before'], 'after': dry['after'], 'released': dry['released'],
               'remaining_after': {'attempts': 600 - dry['after']['attempts'], 'tokens': 5_000_000 - dry['after']['tokens']},
               'copy_applied_and_audits_verified': True, 'duplicate_settlement_refused': True,
               'limits': {'attempts': 600, 'tokens': 5_000_000},
               'rgb_bundle': {'id': RUNNABLE_ID, 'sha256': bundle_sha,
                              'closure_count': len(closure), 'changed_files_in_closure': overlap},
               'source_hashes': {p: sha(Path(p).read_bytes()) for p in sorted(changed) if Path(p).is_file()},
               'model_calls': 0, 'physical_runs': 0, 'original_files': originals}
    write_new(OUT / 'verification.json', summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in ('original_files', 'source_hashes')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
