"""Explicit #222 budget settlement. No wire, model, or automatic refunds."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from harness.llm_completion import normal_completion, successful_call
from harness.zone_pilot_budget import canonical, sha, state_sha256, usage_total
from harness.zone_pilot_proxy_log import EVIDENCE_LEVEL, _usage


def accounting_snapshot(db, sql_sends):
    """Validate current SQL debits against immutable reservations + audit chain."""
    audits, by_id = [], {}
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='budget_settlements'").fetchone():
        for revision, key, raw, checksum in db.execute(
                'SELECT revision, reservation_id, record, sha256 FROM budget_settlements ORDER BY revision'):
            row = json.loads(raw)
            previous = audits[-1]['sha256'] if audits else None
            if (revision != len(audits) + 1 or row['revision'] != revision
                    or row['reservation_id'] != key or key in by_id
                    or sha(raw.encode()) != checksum or row['previous_sha256'] != previous):
                raise ValueError('budget settlement audit chain mismatch')
            by_id[key] = row
            audits.append({**row, 'sha256': checksum})
    charged = {'attempts': 0, 'tokens': 0}
    for key, tokens, attempts, raw in sql_sends:
        sent = json.loads(raw)
        original = {'attempts': sent['reserved_attempts'], 'tokens': sent['reserved_tokens']}
        audit = by_id.pop(key, None)
        expected = original if audit is None else audit['after']
        if (key != sent['reservation_id'] or (audit and audit['before'] != original)
                or expected != {'attempts': attempts, 'tokens': tokens}
                or any(type(expected[k]) is not int or not 0 < expected[k] <= original[k]
                       for k in original)):
            raise ValueError('budget debit does not match reservation/settlement audit')
        charged['attempts'] += attempts
        charged['tokens'] += tokens
    if by_id:
        raise ValueError('budget settlement without reservation')
    return {'charged_attempts': charged['attempts'], 'charged_tokens': charged['tokens'],
            'budget_settlements': audits}


def _successful_exact_call(snapshot, sent):
    """A response_received row can still fail protocol parsing after the wire."""
    if (sent['status'] != 'response_received' or sent.get('late') or sent.get('wire_error')
            or not normal_completion(sent.get('completion'))):
        raise ValueError('failed_or_unknown_send')
    usage = _usage(sent)  # rehash request/response and check all exact-usage flags
    run = next((r for r in snapshot['runs'] if r['run_id'] == sent['run_id']), None)
    if not run or run['status'] not in ('recorded', 'failed'):
        raise ValueError('missing_terminal_run')
    manifest_path = Path(run['output']) / 'manifest.json'
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if (sha(raw) != run.get('manifest_sha256') or manifest.get('run_id') != run['run_id']
            or manifest.get('pilot_id') != snapshot['meta']['pilot_id']):
        raise ValueError('run_manifest_hash_or_identity_mismatch')
    trials = [t for t in manifest['trials'] if t['trial_id'] == sent['trial_id']]
    if len(trials) != 1:
        raise ValueError('missing_unique_trial')
    trial_path = Path(sent['request_path']).parent.parent / 'trial.json'
    raw = trial_path.read_bytes()
    if Path(trials[0]['trial_path']).resolve() != trial_path.resolve() or sha(raw) != trials[0]['trial_sha256']:
        raise ValueError('trial_hash_mismatch')
    trial = json.loads(raw)
    ids = {sent['call_id']}
    ids.update(a['request_id'] for a in trial.get('request_archive', [])
               if a.get('call_id') == sent['call_id'] and a.get('request_id'))
    calls = [c for c in trial['calls'] if c.get('request_id') in ids]
    if trial['trial_id'] != sent['trial_id'] or len(calls) != 1 or not successful_call(calls[0]):
        raise ValueError('failed_or_unknown_call')
    cost = calls[0]['cost_terms']
    if (cost.get('usage_known') is not True or cost.get('usage_bound') != 'exact'
            or cost.get('provider_usage') != usage or cost.get('completion') != sent['completion']):
        raise ValueError('call_usage_not_exact')
    return {'trial_sha256': sha(raw), 'manifest_sha256': run['manifest_sha256']}


def _candidate(snapshot, sent, call):
    if not call['reconciled'] or call['issues']:
        raise ValueError('send_reconciliation_incomplete')
    proof = _successful_exact_call(snapshot, sent)
    attempts = call['actual_upstream_attempts']
    if type(attempts) is not int or not 1 <= attempts <= sent['reserved_attempts']:
        raise ValueError('actual_attempts_exceed_reservation_or_unknown')
    if call['evidence_level'] == EVIDENCE_LEVEL:
        # This grade only proves the final response's usage. Never invent zero
        # tokens for retries/errors hidden behind a successful proxy response.
        if attempts != 1:
            raise ValueError('retry_usage_unknown')
        tokens = usage_total(sent['provider_usage'])
    else:
        tokens = 0
        for attempt in call['upstream_attempts']:
            usage = attempt['usage']
            if usage.get('usage_known', True) is not True or usage.get('usage_bound', 'exact') != 'exact':
                raise ValueError('upstream_usage_not_exact')
            total = usage_total(usage)
            if total is None:
                if attempt.get('provider_confirmed_nonbillable') is not True or usage != {
                        'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}:
                    raise ValueError('upstream_usage_unknown')
                total = 0
            if total > sent['envelope']['per_upstream_tokens']:
                raise ValueError('upstream_usage_exceeds_reservation')
            tokens += total
    if type(tokens) is not int or not 0 < tokens <= sent['reserved_tokens']:
        raise ValueError('usage_exceeds_reservation_or_unknown')
    return {'reservation_id': sent['reservation_id'], 'trial_id': sent['trial_id'],
            'call_id': sent['call_id'],
            'before': {'attempts': sent['reserved_attempts'], 'tokens': sent['reserved_tokens']},
            'after': {'attempts': attempts, 'tokens': tokens},
            'evidence_level': call['evidence_level'], 'evidence': call['evidence'],
            'response_sha256': sent['response_sha256'], **proof}


def settlement_plan(snapshot, report, reservation_ids=None):
    selected = set(reservation_ids) if reservation_ids is not None else None
    sends = {s['reservation_id']: s for s in snapshot['sends']}
    if selected is not None and (not selected or selected - sends.keys()
                                 or len(selected) != len(reservation_ids)):
        raise ValueError('unknown/duplicate/empty settlement selection')
    settled = {r['reservation_id'] for r in snapshot['budget_settlements']}
    eligible, skipped = [], []
    for call in report['calls']:
        key = call['reservation_id']
        if selected is not None and key not in selected:
            continue
        try:
            if key in settled:
                raise ValueError('send_already_settled')
            if report['problems']:
                raise ValueError('reconciliation_report_has_global_problems')
            eligible.append(_candidate(snapshot, sends[key], call))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else 'missing_or_invalid_call_evidence'
            if selected is not None:
                raise ValueError(f'settlement refused for {key}: {reason}') from exc
            skipped.append({'reservation_id': key, 'trial_id': sends[key]['trial_id'], 'reason': reason})
    before = {'attempts': snapshot['charged_attempts'], 'tokens': snapshot['charged_tokens']}
    after = {k: before[k] - sum(r['before'][k] - r['after'][k] for r in eligible) for k in before}
    return {'eligible': eligible, 'skipped': skipped, 'before': before, 'after': after,
            'released': {k: before[k] - after[k] for k in before}}


def settle_reconciled(budget, *, report_path, telemetry_path, expected_report_sha256,
                      expected_state_sha256, dry_run=False, reservation_ids=None):
    """Check reviewed files/state and revalidate raw evidence under the write lock.

    Each send is unique in the append-only audit table. A stale/replayed review
    fails atomically. Dry-run computes the identical plan without SQL mutations.
    """
    from harness.zone_pilot_reconcile import reconcile
    with budget._connect() as db:
        db.execute('BEGIN IMMEDIATE')
        budget._require_current_source(db)
        before = budget._snapshot(db)
        raw = Path(report_path).read_bytes()
        if sha(raw) != expected_report_sha256:
            raise ValueError('reviewed reconciliation report hash mismatch')
        if state_sha256(before) != expected_state_sha256:
            raise ValueError('pilot state changed since settlement review')
        if any(r['status'] == 'running' for r in before['runs']):
            raise ValueError('stop/reconcile unfinished runs before budget settlement')
        telemetry_raw = Path(telemetry_path).read_bytes()
        telemetry = [json.loads(line) for line in telemetry_raw.splitlines() if line.strip()]
        report = json.loads(raw)
        if (report.get('state_sha256') != expected_state_sha256
                or report != reconcile(before, telemetry)):
            raise ValueError('reviewed reconciliation no longer matches state/evidence')
        plan = settlement_plan(before, report, reservation_ids)
        common = {'schema': 'ugrp.zone_pilot_budget_settlement.v1',
                  'pilot_id': before['meta']['pilot_id'], 'report_path': str(Path(report_path).resolve()),
                  'report_sha256': expected_report_sha256, 'before_state_sha256': expected_state_sha256,
                  'source_identity_sha256': report['source_identity_sha256'],
                  'telemetry_path': str(Path(telemetry_path).resolve()), 'telemetry_sha256': sha(telemetry_raw)}
        audits = []
        if not dry_run and plan['eligible']:
            db.execute('CREATE TABLE IF NOT EXISTS budget_settlements '
                       '(revision INTEGER PRIMARY KEY, reservation_id TEXT UNIQUE NOT NULL, '
                       'record TEXT NOT NULL, sha256 TEXT NOT NULL)')
            history = before['budget_settlements']
            for candidate in plan['eligible']:
                row = {**common, **candidate, 'revision': len(history) + 1,
                       'created_at_utc': datetime.now(timezone.utc).isoformat(),
                       'previous_sha256': history[-1]['sha256'] if history else None}
                raw = canonical(row)
                audit = {**row, 'sha256': sha(raw.encode())}
                db.execute('INSERT INTO budget_settlements VALUES (?,?,?,?)',
                           (row['revision'], row['reservation_id'], raw, audit['sha256']))
                db.execute('UPDATE sends SET attempts=?, tokens=? WHERE id=?',
                           (row['after']['attempts'], row['after']['tokens'], row['reservation_id']))
                history.append(audit)
                audits.append(audit)
        after = budget._snapshot(db)
        return {**common, **plan, 'dry_run': dry_run, 'audits': audits,
                'after_state_sha256': state_sha256(after), 'network_calls': 0}
