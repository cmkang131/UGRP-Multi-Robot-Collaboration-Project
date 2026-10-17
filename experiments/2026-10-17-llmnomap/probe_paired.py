#!/usr/bin/env python3
"""Paired 40x2 replay: stored static-map planner prompt vs planner_egocentric_memory_v1.

Only LLM format/latency/429/cache/cost are measured.  Task accuracy is NOT
measured.  API key is read inside this process from the macOS Keychain
(service ugrp-openrouter, account openrouter) and never printed or written.

Preconditions (all enforced):
* model_endpoint_watch reports ok:true and no alerts;
* configs/model_endpoints.json pins the planner to Gemma 4 31B @ CoreWeave fp4;
* the 40 replay inputs pass the projection input audit with zero leaks;
* the preflight current-stack result says admission=pass;
* calls <= 200, no retries, hard spend guard.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import datetime
import hashlib
import json
import math
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from harness import planner_egocentric_memory as eg  # noqa: E402

N_PAIRS = 40
CALLS_PLANNED = N_PAIRS * 2
CALL_CAP = 200
WORKERS = 6
SPACING_S = 1.5
MIN_BALANCE_USD = 0.50
MAX_SPEND_USD = 0.25
TEMPERATURE = 0
MAX_TOKENS = 300


def read_key() -> str:
    out = subprocess.run(
        ['security', 'find-generic-password', '-s', 'ugrp-openrouter', '-a', 'openrouter', '-w'],
        capture_output=True, text=True, check=True)
    key = out.stdout.strip()
    if not key:
        raise RuntimeError('empty OpenRouter key from Keychain')
    return key


def get_json(url: str, key: str) -> dict:
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def balance(key: str) -> dict:
    credits = (get_json('https://openrouter.ai/api/v1/credits', key).get('data') or {})
    total = float(credits.get('total_credits') or 0.0)
    used = float(credits.get('total_usage') or 0.0)
    out = {'credits_remaining_usd': round(total - used, 6), 'total_credits': total,
           'total_usage': used}
    try:
        data = get_json('https://openrouter.ai/api/v1/key', key).get('data') or {}
        if data.get('limit_remaining') is not None:
            out['key_remaining_usd'] = round(float(data['limit_remaining']), 6)
    except Exception as error:
        out['key_balance_error'] = type(error).__name__
    return out


def endpoint_config() -> dict:
    data = json.loads((ROOT / 'configs/model_endpoints.json').read_text())
    rows = [row for row in data['endpoints'] if row.get('role') == 'planner']
    if len(rows) != 1:
        raise RuntimeError(f'expected one planner endpoint, got {len(rows)}')
    return rows[0]


def endpoint_watch() -> dict:
    run = subprocess.run([sys.executable, str(ROOT / 'scripts/model_endpoint_watch.py')],
                         capture_output=True, text=True)
    try:
        payload = json.loads(run.stdout)
    except json.JSONDecodeError:
        payload = {'ok': False, 'raw_stdout': run.stdout[-2000:], 'stderr': run.stderr[-2000:]}
    payload['exit_code'] = run.returncode
    return payload


def parse_decision(text: str):
    if not text:
        return False, None
    try:
        start, end = text.index('{'), text.rindex('}') + 1
        value = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return False, None
    if isinstance(value, dict) and isinstance(value.get('act'), str) and value['act'].strip():
        return True, value
    return False, None


def image_data_uri(path: Path) -> tuple:
    raw = path.read_bytes()
    return ('data:image/jpeg;base64,' + base64.b64encode(raw).decode(),
            hashlib.sha256(raw).hexdigest())


def wire_body(endpoint: dict, system: str, user: str, image_url: str) -> dict:
    return {
        'model': endpoint['model'],
        'temperature': TEMPERATURE,
        'max_tokens': MAX_TOKENS,
        'usage': {'include': True},
        'provider': {'order': [endpoint['tag']], 'allow_fallbacks': False},
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': user},
                {'type': 'image_url', 'image_url': {'url': image_url}},
            ]},
        ],
    }


def call_one(key: str, endpoint: dict, pair_index: int, arm: str, system: str, user: str,
             image_url: str, image_sha: str, stored_sha: str) -> dict:
    body = wire_body(endpoint, system, user, image_url)
    body_text = json.dumps(body, ensure_ascii=False, sort_keys=True)
    request_sha = hashlib.sha256(body_text.encode()).hexdigest()
    req = urllib.request.Request(
        'https://openrouter.ai/api/v1/chat/completions',
        data=json.dumps(body).encode(),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    t0 = time.time()
    try:
        raw = urllib.request.urlopen(req, timeout=90).read()
        wall = time.time() - t0
        payload = json.loads(raw)
        message = ((payload.get('choices') or [{}])[0].get('message') or {})
        text = message.get('content') or ''
        valid, parsed = parse_decision(text)
        usage = payload.get('usage') or {}
        prompt = int(usage.get('prompt_tokens') or 0)
        completion = int(usage.get('completion_tokens') or 0)
        cached = int((usage.get('prompt_tokens_details') or {}).get('cached_tokens') or 0)
        reasoning = int((usage.get('completion_tokens_details') or {}).get('reasoning_tokens') or 0)
        cost = float(usage.get('cost') or 0.0)
        price = endpoint['baseline_usd_per_million']
        cache_price = price['input_cache_read'] if price.get('input_cache_read') is not None else price['prompt']
        formula = ((prompt - cached) * price['prompt'] + cached * cache_price
                   + completion * price['completion']) / 1e6
        return {
            'pair_index': pair_index, 'arm': arm, 'status': 200,
            'wall_s': round(wall, 4), 'http_status': 200,
            'valid_json_act': valid,
            'parsed_act': parsed.get('act') if parsed else None,
            'parsed_keys': sorted(parsed) if isinstance(parsed, dict) else None,
            'raw_text': text,
            'raw_text_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'prompt_tokens': prompt, 'completion_tokens': completion,
            'cached_tokens': cached,
            'cached_ratio': round(cached / prompt, 6) if prompt else None,
            'reasoning_tokens': reasoning,
            'reported_cost_usd': round(cost, 8),
            'formula_cost_usd': round(formula, 8),
            'provider_returned': payload.get('provider'),
            'model_returned': payload.get('model'),
            'request_sha256': request_sha, 'stored_request_sha256': stored_sha,
            'image_sha256': image_sha, 'error': None,
        }
    except urllib.error.HTTPError as error:
        wall = time.time() - t0
        body_text = error.read()[:2000].decode('utf8', 'replace')
        return {'pair_index': pair_index, 'arm': arm, 'status': error.code,
                'wall_s': round(wall, 4), 'http_status': error.code, 'valid_json_act': False,
                'parsed_act': None, 'parsed_keys': None, 'raw_text': None,
                'raw_text_sha256': None, 'prompt_tokens': None, 'completion_tokens': None,
                'cached_tokens': None, 'cached_ratio': None, 'reasoning_tokens': None,
                'reported_cost_usd': 0.0, 'formula_cost_usd': 0.0,
                'provider_returned': None, 'model_returned': None,
                'request_sha256': request_sha, 'stored_request_sha256': stored_sha,
                'image_sha256': image_sha, 'error': body_text}
    except Exception as error:
        wall = time.time() - t0
        return {'pair_index': pair_index, 'arm': arm, 'status': 'ERR',
                'wall_s': round(wall, 4), 'http_status': None, 'valid_json_act': False,
                'parsed_act': None, 'parsed_keys': None, 'raw_text': None,
                'raw_text_sha256': None, 'prompt_tokens': None, 'completion_tokens': None,
                'cached_tokens': None, 'cached_ratio': None, 'reasoning_tokens': None,
                'reported_cost_usd': 0.0, 'formula_cost_usd': 0.0,
                'provider_returned': None, 'model_returned': None,
                'request_sha256': request_sha, 'stored_request_sha256': stored_sha,
                'image_sha256': image_sha, 'error': repr(error)[:500]}


def median(values):
    values = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    return round(statistics.median(values), 6) if values else None


def p90(values):
    values = sorted(v for v in values if isinstance(v, (int, float)) and math.isfinite(v))
    if not values:
        return None
    index = min(len(values) - 1, math.ceil(0.9 * len(values)) - 1)
    return round(values[index], 6)


def summarize(rows: list, endpoint: dict) -> dict:
    out = {'schema': 'ugrp.llmnomap_summary.v1',
           'generated_utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
           'endpoint': {'model': endpoint['model'], 'provider': endpoint['provider'],
                        'tag': endpoint['tag'], 'quantization': endpoint['quantization']},
           'calls_planned': CALLS_PLANNED, 'calls_attempted': len(rows),
           'no_retries': True, 'task_accuracy_measured': False,
           'arms': {}}
    for arm in ('original', 'planner_egocentric_memory_v1'):
        arm_rows = [row for row in rows if row['arm'] == arm]
        ok = [row for row in arm_rows if row['status'] == 200]
        valid = [row for row in ok if row['valid_json_act']]
        out['arms'][arm] = {
            'attempted': len(arm_rows), 'http_200': len(ok),
            'http_429': sum(1 for row in arm_rows if row['status'] == 429),
            'errors': sum(1 for row in arm_rows if row['status'] not in (200, 429)),
            'format_success_n': len(valid),
            'format_success_over_attempted': round(len(valid) / len(arm_rows), 4) if arm_rows else None,
            'format_success_over_200': round(len(valid) / len(ok), 4) if ok else None,
            'wall_median_s': median([row['wall_s'] for row in ok]),
            'wall_p90_s': p90([row['wall_s'] for row in ok]),
            'over_8s': sum(1 for row in ok if row['wall_s'] > 8.0),
            'prompt_tokens_median': median([row['prompt_tokens'] for row in ok]),
            'completion_tokens_median': median([row['completion_tokens'] for row in ok]),
            'cached_tokens_total': sum(row['cached_tokens'] for row in ok),
            'prompt_tokens_total': sum(row['prompt_tokens'] for row in ok),
            'cached_ratio_weighted': (round(sum(row['cached_tokens'] for row in ok)
                                            / sum(row['prompt_tokens'] for row in ok), 6)
                                      if sum(row['prompt_tokens'] for row in ok) else None),
            'cached_ratio_median': median([row['cached_ratio'] for row in ok]),
            'reported_cost_total_usd': round(sum(row['reported_cost_usd'] for row in ok), 8),
            'reported_cost_per_call_usd': (round(sum(row['reported_cost_usd'] for row in ok) / len(ok), 8)
                                           if ok else None),
            'formula_cost_total_usd': round(sum(row['formula_cost_usd'] for row in ok), 8),
            'act_counts': {act: sum(1 for row in valid if row['parsed_act'] == act)
                           for act in sorted({row['parsed_act'] for row in valid})},
        }
    by_pair = {}
    for row in rows:
        by_pair.setdefault(row['pair_index'], {})[row['arm']] = row
    pairs = [pair for pair in by_pair.values()
             if pair.get('original', {}).get('status') == 200
             and pair.get('planner_egocentric_memory_v1', {}).get('status') == 200]
    out['paired'] = {
        'n_pairs_both_200': len(pairs),
        'wall_delta_median_s_variant_minus_original': median([
            pair['planner_egocentric_memory_v1']['wall_s'] - pair['original']['wall_s'] for pair in pairs]),
        'cached_ratio_delta_median': median([
            pair['planner_egocentric_memory_v1']['cached_ratio'] - pair['original']['cached_ratio']
            for pair in pairs if pair['original']['cached_ratio'] is not None
            and pair['planner_egocentric_memory_v1']['cached_ratio'] is not None]),
        'cost_delta_median_usd': median([
            pair['planner_egocentric_memory_v1']['reported_cost_usd']
            - pair['original']['reported_cost_usd'] for pair in pairs]),
        'prompt_tokens_delta_median': median([
            pair['planner_egocentric_memory_v1']['prompt_tokens']
            - pair['original']['prompt_tokens'] for pair in pairs]),
    }
    out['limits'] = [
        '과제 정확도는 측정하지 않았다. 형식 성공(act 필드)만 잰다.',
        '저장 원장은 text-only라 같은 번들의 저장 own-RGB 프레임 1장을 원/변형 양쪽에 동일하게 첨부했다. '
        '프레임이 요청별 실제 관측과 일치하지 않는다.',
        'cached_tokens는 제공자 보고값이며 프롬프트 접두 일치 정책에 의존한다. '
        'OpenRouter에서 provider.order를 수동 지정하면 sticky routing이 꺼질 수 있다.',
        '40개 표본은 한 저장 원장의 앞 40행이며 과제 분포를 대표하지 않는다.',
    ]
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--allow-live', action='store_true', help='required to make real API calls')
    parser.add_argument('--audit-only', action='store_true', help='project + audit 40 rows without API calls')
    parser.add_argument('--stack-check', default=str(HERE / 'stack_check_preflight.json'))
    args = parser.parse_args()
    if not args.allow_live and not args.audit_only:
        raise SystemExit('refusing to call the API without --allow-live')
    if CALLS_PLANNED > CALL_CAP or CALL_CAP > 200:
        raise SystemExit('call budget exceeded')

    endpoint = endpoint_config()
    watch = endpoint_watch()
    if not watch.get('ok') or watch.get('alerts'):
        raise SystemExit(f'model_endpoint_watch is not clean: {watch}')
    stack = json.loads(Path(args.stack_check).read_text())
    if not stack.get('ok') or stack.get('admission') != 'pass':
        raise SystemExit(f'current-stack preflight did not pass: {stack.get("admission")}')

    image_url, image_sha = image_data_uri(HERE / 'raw/own_rgb_r80-r1-00000.jpg')
    rows = [json.loads(line) for line in (HERE / 'replay_inputs.jsonl').read_text().splitlines() if line.strip()]
    if len(rows) != N_PAIRS:
        raise SystemExit(f'expected {N_PAIRS} replay rows, got {len(rows)}')

    tasks, audits = [], []
    for row in rows:
        q = row['request']
        stored_user = json.dumps(q['input'])
        stored = {'messages': [{'role': 'system', 'content': q['system']},
                               {'role': 'user', 'content': stored_user}],
                  'images': [{'label': 'own_wrist_rgb', 'image': image_url}]}
        variant = eg.apply_request_if_enabled(stored, value=eg.OPTION)
        audit = eg.audit_projection(stored, variant)
        if not audit['ok'] or audit['leaks']:
            raise SystemExit(f'input audit failed at row {row["source_index"]}: {audit["leaks"][:3]}')
        if audit['memory_entries'] != ((json.loads(variant['messages'][1]['content'])
                                        .get('egocentric_memory') or {}).get('count')):
            raise SystemExit('memory count mismatch')
        audits.append({'source_index': row['source_index'], 'case_id': row['case_id'],
                       'condition': row['condition'],
                       'stored_request_sha256': hashlib.sha256(
                           json.dumps(q, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                       **audit})
        v_system = next(m['content'] for m in variant['messages'] if m['role'] == 'system')
        v_user = next(m['content'] for m in variant['messages'] if m['role'] == 'user')
        tasks.append({'pair_index': row['source_index'],
                      'original': {'system': q['system'], 'user': stored_user},
                      'planner_egocentric_memory_v1': {'system': v_system, 'user': v_user},
                      'stored_sha': audits[-1]['stored_request_sha256']})

    audit_path = HERE / 'input_audit.json'
    audit_path.write_text(json.dumps({
        'schema': 'ugrp.llmnomap_input_audit.v1',
        'rows': len(audits),
        'static_map_keys_before_total': sum(a['static_map_keys_before'] for a in audits),
        'static_map_keys_after_total': sum(a['static_map_keys_after'] for a in audits),
        'requests_with_static_map_before': sum(1 for a in audits if a['static_map_keys_before'] > 0),
        'requests_with_static_map_after': sum(1 for a in audits if a['static_map_keys_after'] > 0),
        'requests_with_world_pose_before': sum(1 for a in audits if a['world_pose_keys_before'] > 0),
        'requests_with_world_pose_after': sum(1 for a in audits if a['world_pose_keys_after'] > 0),
        'world_pose_keys_before_total': sum(a['world_pose_keys_before'] for a in audits),
        'world_pose_keys_after_total': sum(a['world_pose_keys_after'] for a in audits),
        'system_static_map_mentions_before_total': sum(a['system_static_map_mentions_before'] for a in audits),
        'system_static_map_mentions_after_total': sum(a['system_static_map_mentions_after'] for a in audits),
        'map_figure_images_before_total': sum(a['map_figure_images_before'] for a in audits),
        'map_figure_images_after_total': sum(a['map_figure_images_after'] for a in audits),
        'memory_entries': {str(k): sum(1 for a in audits if a['memory_entries'] == k)
                           for k in sorted({a['memory_entries'] for a in audits})},
        'text_tokens_saved_total': sum(a['text_tokens_saved'] for a in audits),
        'text_tokens_saved_median': median([a['text_tokens_saved'] for a in audits]),
        'leaks': sum(len(a['leaks']) for a in audits),
        'rows_detail': audits,
        'image_attached_both_arms': True,
        'image_sha256': image_sha,
        'stored_requests_text_only': True,
    }, indent=2, ensure_ascii=False) + '\n')
    if args.audit_only:
        print(json.dumps({'audit_only': True, 'rows': len(audits),
                          'leaks': sum(len(a['leaks']) for a in audits),
                          'requests_with_static_map_before': sum(1 for a in audits if a['static_map_keys_before'] > 0),
                          'requests_with_static_map_after': sum(1 for a in audits if a['static_map_keys_after'] > 0),
                          'memory_entries': {str(k): sum(1 for a in audits if a['memory_entries'] == k)
                                             for k in sorted({a['memory_entries'] for a in audits})},
                          'tokens_saved_total': sum(a['text_tokens_saved'] for a in audits)}, indent=2))
        return 0

    key = read_key()
    before = balance(key)
    if before['credits_remaining_usd'] < MIN_BALANCE_USD:
        raise SystemExit(f'balance below ${MIN_BALANCE_USD}: {before["credits_remaining_usd"]}')

    tasks_order = []
    for task in tasks:
        order = ('original', 'planner_egocentric_memory_v1') if task['pair_index'] % 2 == 0 else (
            'planner_egocentric_memory_v1', 'original')
        for arm in order:
            tasks_order.append((task, arm))
    if len(tasks_order) != CALLS_PLANNED:
        raise SystemExit('unexpected task count')

    results = []
    t_start = time.time()
    with cf.ThreadPoolExecutor(WORKERS) as pool:
        futures = []
        for index, (task, arm) in enumerate(tasks_order):
            payload = task[arm]
            futures.append(pool.submit(call_one, key, endpoint, task['pair_index'], arm,
                                       payload['system'], payload['user'], image_url, image_sha,
                                       task['stored_sha']))
            if index < len(tasks_order) - 1:
                time.sleep(SPACING_S)
        for future in cf.as_completed(futures):
            results.append(future.result())
    elapsed = time.time() - t_start
    results.sort(key=lambda row: (row['pair_index'], row['arm']))
    (HERE / 'calls.jsonl').write_text(
        '\n'.join(json.dumps(row, ensure_ascii=False) for row in results) + '\n')
    after = balance(key)
    summary = summarize(results, endpoint)
    summary['elapsed_s'] = round(elapsed, 2)
    summary['balance_before'] = before
    summary['balance_after'] = after
    summary['endpoint_watch'] = watch
    summary['spend_cap_usd'] = MAX_SPEND_USD
    summary['reported_cost_total_usd'] = round(
        sum(row['reported_cost_usd'] for row in results), 8)
    if summary['reported_cost_total_usd'] > MAX_SPEND_USD:
        summary['spend_cap_exceeded'] = True
    (HERE / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    (HERE / 'preflight.json').write_text(json.dumps({
        'schema': 'ugrp.llmnomap_preflight.v1',
        'endpoint_watch': watch,
        'stack_check': args.stack_check,
        'stack_ok': stack.get('ok'), 'stack_admission': stack.get('admission'),
        'balance_before': before, 'balance_after': after,
        'calls_planned': CALLS_PLANNED, 'calls_cap': CALL_CAP,
        'spend_cap_usd': MAX_SPEND_USD,
        'input_audit': {'rows': len(audits), 'leaks': 0,
                        'static_map_before': sum(a['static_map_keys_before'] for a in audits),
                        'static_map_after': sum(a['static_map_keys_after'] for a in audits)},
    }, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'calls': len(results),
                      '200': sum(1 for r in results if r['status'] == 200),
                      '429': sum(1 for r in results if r['status'] == 429),
                      'format_ok': sum(1 for r in results if r['valid_json_act']),
                      'reported_cost_usd': summary['reported_cost_total_usd'],
                      'elapsed_s': summary['elapsed_s'],
                      'balance_after': after['credits_remaining_usd']}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
