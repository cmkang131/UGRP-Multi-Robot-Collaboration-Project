#!/usr/bin/env python3
"""Build ID-less exclusive-window telemetry offline from a read-only budget/log.

Exit 0 only if all sends reconcile; otherwise preserve diagnostics and exit 2.
Never sends requests, edits the installed proxy, migrates or copies a budget.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.zone_pilot_budget import PilotBudget, canonical, sha
from harness.zone_pilot_proxy_log import EVIDENCE_LEVEL, LIMITATION, extract_window, inspect_window, window_spec
from harness.zone_pilot_reconcile import reconcile


def save(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)
    if path.read_bytes() != raw:
        raise OSError('telemetry artifact read-back mismatch')
    return sha(raw)


def save_json(path, value):
    return save(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode())


def build(snapshot, proxy_log, output, *, log_timezone='Asia/Seoul'):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    proxy_log = Path(proxy_log).resolve()
    rows, files = [], {}
    try:
        with proxy_log.open('rb') as stream:
            import os
            stat = os.fstat(stream.fileno())
            raw = stream.read(stat.st_size)  # fixed prefix of an append-only log
        log_error = None
    except OSError:
        raw, stat, log_error = b'', None, 'proxy_log_missing'
    for index, sent in enumerate(snapshot['sends'], 1):
        row = {'evidence_level': EVIDENCE_LEVEL, 'reservation_id': sent['reservation_id'],
               'body_sha256': sent['body_sha256'], 'proxy_response_id': sent.get('proxy_response_id'),
               'proxy_request_id': None, 'upstream_attempts': None}
        try:
            if log_error:
                raise ValueError(log_error)
            window = window_spec(sent, log_timezone)
            row['window'] = window
            start, end, excerpt = extract_window(raw, window)
            path = output / f'{index:06d}-proxy-window.log'
            digest = save(path, excerpt)
            files[path.name] = digest
            evidence = {'path': str(path), 'sha256': digest, 'source_path': str(proxy_log),
                        'source_inode': stat.st_ino, 'offset': start, 'end_offset': end,
                        'source_size_at_capture': stat.st_size,
                        'includes_boundary_context': True}
            row['evidence'] = evidence
            row.update(inspect_window(sent, excerpt, evidence, window))
        except (OSError, KeyError, ValueError, TypeError) as exc:
            row.update(complete=False, issues=[str(exc)], actual_upstream_attempts=None)
        rows.append(row)
    files['telemetry.jsonl'] = save(output / 'telemetry.jsonl',
                                   ''.join(canonical(r) + '\n' for r in rows).encode())
    report = reconcile(snapshot, rows)
    files['reconciliation.json'] = save_json(output / 'reconciliation.json', report)
    manifest = {'schema': 'ugrp.proxy_log_telemetry.v1', 'evidence_level': EVIDENCE_LEVEL,
                'evidence_levels': report['evidence_levels'], 'limitation': LIMITATION,
                'pilot_id': snapshot['meta']['pilot_id'], 'budget_file': snapshot['meta']['budget_path'],
                'state_sha256': report['state_sha256'], 'complete': report['complete'],
                'reserved_attempts': snapshot['reserved_attempts'],
                'reserved_tokens': snapshot['reserved_tokens'], 'refunds': 0,
                'network_calls': 0, 'physical_runs': 0, 'files_sha256': files,
                'cohort_gate': {'billing_evidence_levels': report['evidence_levels'],
                                'billing_complete': report['complete'],
                                'admitted': False,
                                'remaining': 'current_source_four_condition_preflight_and_completion_checks'}}
    save_json(output / 'manifest.json', manifest)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--budget-file', type=Path, required=True)
    parser.add_argument('--proxy-log', type=Path,
                        default=Path.home() / '.hermes/logs/gemini-subscription-proxy.log')
    parser.add_argument('--log-timezone', default='Asia/Seoul', help='timezone of the naive proxy timestamps')
    parser.add_argument('--output', type=Path, required=True, help='new directory only')
    args = parser.parse_args(argv)
    snapshot = PilotBudget(args.budget_file, read_only=True).snapshot()
    report = build(snapshot, args.proxy_log, args.output, log_timezone=args.log_timezone)
    print(json.dumps({'complete': report['complete'], 'evidence_levels': report['evidence_levels'],
                      'calls': len(report['calls']), 'output': str(args.output.resolve()),
                      'network_calls': 0, 'refunds': 0}))
    return 0 if report['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
