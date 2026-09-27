"""Read-only reconciliation. Uncorrelated legacy proxy log windows never pass.

A telemetry JSONL file is evidence supplied by the coordinator, not an override:
its referenced raw trace file is hashed and must contain the very same row.
All attempted upstream generations (including failures) need terminal usage.
"""
from __future__ import annotations

import json
from pathlib import Path

from harness.zone_pilot_budget import sha, usage_total


def reconcile(snapshot, telemetry=()):
    indexed = {}
    problems = []
    for item in telemetry:
        key = item.get('reservation_id')
        if not key or key in indexed:
            problems.append('missing/duplicate telemetry reservation_id')
        indexed[key] = item
    rows = []
    upstream_ids, proxy_ids = set(), set()
    for sent in snapshot['sends']:
        issues = []
        key = sent['reservation_id']
        observed = indexed.pop(key, None)
        try:
            body = Path(sent['request_path']).read_bytes()
            if sha(body) != sent['body_sha256']:
                issues.append('stored_request_hash_mismatch')
            ledger = sent.get('ledger', {})
            if sent.get('response_sha256'):
                response = Path(sent['request_path']).parent / ledger['response_path']
                if sha(response.read_bytes()) != sent['response_sha256']:
                    issues.append('stored_response_hash_mismatch')
        except (OSError, KeyError):
            issues.append('missing_durable_request_or_response')
        if sent['status'] == 'usage_exceeds_reservation':
            issues.append('usage_exceeds_reservation')
        if observed is None:
            issues.append('proxy_request_and_upstream_attempts_unlinked')
            if usage_total(sent.get('provider_usage')) is None:
                issues.append('unknown_provider_usage')
        else:
            try:
                evidence = observed['evidence']
                raw = Path(evidence['path']).read_bytes()
                if sha(raw) != evidence['sha256']:
                    issues.append('upstream_evidence_hash_mismatch')
                record = {k: v for k, v in observed.items() if k != 'evidence'}
                if record not in [json.loads(line) for line in raw.splitlines() if line.strip()]:
                    issues.append('upstream_evidence_row_missing')
            except (OSError, KeyError, ValueError):
                issues.append('upstream_evidence_missing')
            if observed.get('body_sha256') != sent['body_sha256']:
                issues.append('body_sha256_mismatch')
            if sent.get('proxy_response_id') and observed.get('proxy_response_id') != sent['proxy_response_id']:
                issues.append('proxy_response_id_mismatch')
            if not observed.get('proxy_request_id'):
                issues.append('missing_proxy_request_id')
            elif observed['proxy_request_id'] in proxy_ids:
                issues.append('proxy_request_id_reused_across_calls')
            proxy_ids.add(observed.get('proxy_request_id'))
            attempts = observed.get('upstream_attempts', [])
            if not isinstance(attempts, list) or not 1 <= len(attempts) <= sent['reserved_attempts']:
                issues.append('upstream_attempt_count_unresolved')
                attempts = []
            ids = set()
            for attempt in attempts:
                if (not attempt.get('id') or attempt['id'] in ids
                        or attempt.get('terminal') is not True):
                    issues.append('upstream_id_or_terminal_state_unresolved')
                if attempt.get('id') in upstream_ids:
                    issues.append('upstream_id_reused_across_calls')
                ids.add(attempt.get('id'))
                upstream_ids.add(attempt.get('id'))
                total = usage_total(attempt.get('usage'))
                # A measured zero for a rejected request needs an explicit
                # provider non-billable assertion in the source evidence.
                zero = attempt.get('provider_confirmed_nonbillable') is True and attempt.get('usage') == {
                    'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
                if total is None and not zero:
                    issues.append('upstream_usage_unknown')
                if total is not None and total > sent['envelope']['per_upstream_tokens']:
                    issues.append('upstream_usage_exceeds_reservation')
            if attempts and sent.get('provider_usage') and attempts[-1].get('usage') != sent['provider_usage']:
                issues.append('last_upstream_usage_does_not_match_proxy_response')
        rows.append({'reservation_id': key, 'call_id': sent['call_id'], 'trial_id': sent['trial_id'],
                     'ledger_seq': sent['ledger_seq'], 'body_sha256': sent['body_sha256'],
                     'proxy_response_id': sent.get('proxy_response_id'),
                     'proxy_request_id': observed.get('proxy_request_id') if observed else None,
                     'upstream_attempts': observed.get('upstream_attempts') if observed else None,
                     'provider_usage': sent.get('provider_usage'),
                     'local_status': sent['status'], 'late': sent.get('late', False),
                     'reserved_attempts': sent['reserved_attempts'], 'reserved_tokens': sent['reserved_tokens'],
                     'issues': issues, 'reconciled': not issues})
    if indexed:
        problems.append('telemetry_without_ledger_reservation')
    return {'schema': 'ugrp.zone_pilot_reconciliation.v1', 'pilot_id': snapshot['meta']['pilot_id'],
            'complete': not problems and all(r['reconciled'] for r in rows),
            'reserved_attempts': snapshot['reserved_attempts'], 'reserved_tokens': snapshot['reserved_tokens'],
            'refunds': 0, 'problems': problems, 'calls': rows}


def require_preflight(snapshot, report, manifest):
    from harness.zone_study_contract import MAIN_CONDITIONS
    if not report['complete']:
        raise ValueError('preflight reconciliation incomplete; cohort expansion refused')
    if manifest.get('stage') != 'preflight' or manifest.get('mode') != 'real_adapter':
        raise ValueError('real four-condition preflight manifest required')
    if manifest.get('pilot_id') != snapshot['meta']['pilot_id']:
        raise ValueError('preflight belongs to a different global pilot budget')
    trials = manifest.get('trials', [])
    if (len(trials) != 4 or {t['condition'] for t in trials} != set(MAIN_CONDITIONS)
            or any(t['successful_calls'] != 1 or t['sent'] != 1 for t in trials)):
        raise ValueError('preflight requires exactly one successful call in each of four conditions')
    run = next((r for r in snapshot['runs'] if r['run_id'] == manifest['run_id']), None)
    raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n'
    if not run or run.get('manifest_sha256') != sha(raw) or run['status'] != 'recorded':
        raise ValueError('preflight manifest not bound to this budget (or interrupted)')
    preflight_ids = {s['trial_id'] for s in snapshot['sends'] if s['run_id'] == manifest['run_id']}
    if preflight_ids != {t['trial_id'] for t in trials}:
        raise ValueError('preflight trials missing from global budget')
