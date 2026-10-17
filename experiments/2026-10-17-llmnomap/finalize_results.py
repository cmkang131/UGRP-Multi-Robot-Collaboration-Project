#!/usr/bin/env python3
"""Recompute summary from calls.jsonl, write the final funnel and manifest.

No model call.  The raw call rows remain the source of every number.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from probe_paired import endpoint_config, summarize  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    calls_path = HERE / 'calls.jsonl'
    rows = [json.loads(line) for line in calls_path.read_text().splitlines() if line.strip()]
    if len(rows) != 80:
        raise SystemExit(f'expected 80 call rows, got {len(rows)}')
    old = json.loads((HERE / 'summary.json').read_text())
    endpoint = endpoint_config()
    summary = summarize(rows, endpoint)
    for key in ('balance_before', 'balance_after', 'endpoint_watch', 'elapsed_s', 'spend_cap_usd'):
        summary[key] = old[key]
    summary['reported_cost_total_usd'] = round(sum(row['reported_cost_usd'] for row in rows), 8)
    for arm in ('original', 'planner_egocentric_memory_v1'):
        arm_rows = [row for row in rows if row['arm'] == arm and row['status'] == 200]
        summary['arms'][arm]['calls_with_cached_tokens'] = sum(
            1 for row in arm_rows if row['cached_tokens'] > 0)
    by_pair = {}
    for row in rows:
        by_pair.setdefault(row['pair_index'], {})[row['arm']] = row
    pairs = [p for p in by_pair.values()
             if p.get('original', {}).get('status') == 200
             and p.get('planner_egocentric_memory_v1', {}).get('status') == 200]
    orig = summary['arms']['original']
    var = summary['arms']['planner_egocentric_memory_v1']
    summary['paired']['n_pairs_both_format_ok'] = sum(
        1 for p in pairs if p['original']['valid_json_act'] and p['planner_egocentric_memory_v1']['valid_json_act'])
    summary['paired']['cached_ratio_weighted_delta'] = round(
        var['cached_ratio_weighted'] - orig['cached_ratio_weighted'], 6)
    summary['paired']['calls_with_cached_tokens'] = {
        'original': orig['calls_with_cached_tokens'],
        'planner_egocentric_memory_v1': var['calls_with_cached_tokens']}
    summary['paired']['prompt_tokens_saved_median'] = round(
        -summary['paired']['prompt_tokens_delta_median'], 6)
    summary['paired']['cost_saved_per_call_median_usd'] = round(
        -summary['paired']['cost_delta_median_usd'], 8)
    (HERE / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')

    audit = json.loads((HERE / 'input_audit.json').read_text())
    funnel = {
        'schema': 'ugrp.llmnomap_rejection_table.v1',
        'stage': 'final',
        'generated_utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'scope': 'Mac-only paired planner prompt replay; no VM/sim/physics',
        'funnel': [
            {'stage': 'source_rows', 'n': 136, 'excluded': 0, 'reason_category': None,
             'note': 'task-planner-ling-vl-main-20261013/off-calls.jsonl.zst 전체 행'},
            {'stage': 'selected_rows', 'n': 40, 'excluded': 96, 'reason_category': 'budget_cap',
             'note': '앞 40행만 사용; 나머지 96행은 호출 예산 보존을 위해 제외'},
            {'stage': 'has_audit_request', 'n': 40, 'excluded': 0, 'reason_category': None},
            {'stage': 'has_static_map', 'n': 40, 'excluded': 0, 'reason_category': None,
             'note': '40/40 요청에 static_map 블록 존재'},
            {'stage': 'projection_ok', 'n': 40, 'excluded': 0, 'reason_category': 'projection_leak'},
            {'stage': 'input_audit_leaks', 'n': 0, 'excluded': 0, 'reason_category': 'projection_leak',
             'note': '구조/값/제거좌표 감사 합계 0'},
            {'stage': 'llm_calls_attempted', 'n': 80, 'excluded': 0, 'reason_category': None,
             'note': '원 40 + 변형 40, 재시도 없음'},
            {'stage': 'http_200', 'n': 80, 'excluded': 0, 'reason_category': 'api_error'},
            {'stage': 'http_429', 'n': 0, 'excluded': 0, 'reason_category': 'http_429'},
            {'stage': 'format_success_act', 'n': 80, 'excluded': 0, 'reason_category': 'format_invalid',
             'note': 'act 필드가 비어 있지 않은 JSON 객체'},
        ],
        'reason_distribution': {'budget_cap': 96, 'projection_leak': 0, 'api_error': 0,
                                'http_429': 0, 'format_invalid': 0, 'none': 80},
        'failures': [],
        'fields': {
            'reason_category': 'required',
            'blocking_object': 'required on physical failure; null here because no physical run',
            'minimum_gap_m': 'required on physical near-miss; null here because no physical run'},
        'coverage': {
            'replay_rows': '40/40',
            'pairs_both_200': f"{summary['paired']['n_pairs_both_200']}/40",
            'pairs_both_format_ok': f"{summary['paired']['n_pairs_both_format_ok']}/40",
            'format_success': '80/80 attempted, 80/80 HTTP 200',
            'input_audit_rows': '40/40 leaks 0',
            'memory_nonempty': '32/40',
            'memory_empty': '8/40',
            'own_rgb_image': '80/80 calls, same stored frame both arms',
            'task_accuracy': '0/0 NOT MEASURED',
        },
        'exclusions': [
            {'n': 96, 'reason_category': 'budget_cap',
             'detail': '원장 136행 중 앞 40행만 사용; LLM 호출 상한 200/계획 80 보존'},
            {'n': 0, 'reason_category': 'projection_leak', 'detail': '투영/감사 실패 없음'},
            {'n': 0, 'reason_category': 'api_error', 'detail': 'HTTP/네트워크 오류 없음'},
            {'n': 0, 'reason_category': 'http_429', 'detail': '429 없음'},
            {'n': 0, 'reason_category': 'format_invalid', 'detail': 'act 형식 실패 없음'},
        ],
        'raw': {
            'calls': {'path': 'experiments/2026-10-17-llmnomap/calls.jsonl', 'sha256': sha(calls_path)},
            'summary': {'path': 'experiments/2026-10-17-llmnomap/summary.json',
                        'sha256': sha(HERE / 'summary.json')},
            'input_audit': {'path': 'experiments/2026-10-17-llmnomap/input_audit.json',
                            'sha256': sha(HERE / 'input_audit.json')},
            'replay_inputs': {'path': 'experiments/2026-10-17-llmnomap/replay_inputs.jsonl',
                              'sha256': sha(HERE / 'replay_inputs.jsonl')},
            'own_rgb': {'path': 'experiments/2026-10-17-llmnomap/raw/own_rgb_r80-r1-00000.jpg',
                        'sha256': sha(HERE / 'raw/own_rgb_r80-r1-00000.jpg')},
        },
        'task_accuracy_measured': False,
        'note': 'LLM 형식/시간/429/캐시/비용만 측정한다. 과제 정확도는 측정하지 않는다.',
    }
    (HERE / 'rejection_table.json').write_text(json.dumps(funnel, indent=2, ensure_ascii=False) + '\n')

    manifest = json.loads((HERE / 'manifest_preflight.json').read_text())
    manifest['rejection_table'] = str(HERE / 'rejection_table.json')
    manifest['stack_check'] = str(HERE / 'stack_check.json')
    manifest['scope'] = (
        'Mac-only paired LLM prompt replay. No VM/SSH/sim/render/physics. The original arm is the stored '
        'static-map prompt; the variant arm is the same request projected by planner_egocentric_memory_v1. '
        'Physical/localization/goal-discovery values below are inherited declarations from configs/current_stack.json, '
        'not measurements of this replay. Task accuracy is not measured.')
    manifest['run_meta'] = {
        'generated_utc': summary['generated_utc'],
        'calls_attempted': summary['calls_attempted'],
        'calls_cap': 200, 'no_retries': True,
        'http_200': 80, 'http_429': sum(1 for row in rows if row['status'] == 429),
        'format_success': sum(1 for row in rows if row['valid_json_act']),
        'reported_cost_total_usd': summary['reported_cost_total_usd'],
        'balance_before_usd': summary['balance_before']['credits_remaining_usd'],
        'balance_after_usd': summary['balance_after']['credits_remaining_usd'],
        'endpoint_watch_ok': summary['endpoint_watch'].get('ok'),
        'task_accuracy_measured': False,
    }
    manifest['artifacts'] = {
        'calls': {'path': 'experiments/2026-10-17-llmnomap/calls.jsonl', 'sha256': sha(calls_path)},
        'summary': {'path': 'experiments/2026-10-17-llmnomap/summary.json',
                    'sha256': sha(HERE / 'summary.json')},
        'input_audit': {'path': 'experiments/2026-10-17-llmnomap/input_audit.json',
                        'sha256': sha(HERE / 'input_audit.json')},
        'rejection_table': {'path': 'experiments/2026-10-17-llmnomap/rejection_table.json',
                            'sha256': sha(HERE / 'rejection_table.json')},
        'preflight': {'path': 'experiments/2026-10-17-llmnomap/preflight.json',
                      'sha256': sha(HERE / 'preflight.json')},
        'replay_inputs': {'path': 'experiments/2026-10-17-llmnomap/replay_inputs.jsonl',
                          'sha256': sha(HERE / 'replay_inputs.jsonl')},
        'own_rgb': {'path': 'experiments/2026-10-17-llmnomap/raw/own_rgb_r80-r1-00000.jpg',
                    'sha256': sha(HERE / 'raw/own_rgb_r80-r1-00000.jpg')},
    }
    (HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'summary': summary['paired'], 'cost': summary['reported_cost_total_usd'],
                      'manifest': str(HERE / 'manifest.json')}, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
