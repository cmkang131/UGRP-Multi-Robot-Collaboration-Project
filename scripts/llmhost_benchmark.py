"""Replay 40 saved real decisions at 40/min, without physics or API credentials.

The same manifest must be used by llmalt. This measures format/serving only, never
robot/task accuracy. Dispatch is open-loop: 40 workers prevent client queuing from
silently reducing the offered rate. No retry or response-journal cache is used.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import statistics
import re
import time
from urllib.request import urlopen

from scripts.llmhost_common import check_alerts, digest, identity, images, loopback, write_json
from scripts.self_gcp_upstream import http_send, upstream_body

# User's llmalt comparison protocol, 2026-10-16 (not new acceptance constants).
N, RPM, SLOW_S = 40, 40, 8


def load_corpus(path):
    manifest = json.loads(Path(path).read_text())
    rows = manifest['requests']
    if len(rows) != N or not manifest.get('corpus_id'):
        raise ValueError('named_40_request_corpus_required')
    requests = []
    for row in rows:
        file = Path(row['path'])
        if not file.is_absolute(): file = Path(path).resolve().parent / file
        raw = file.read_bytes()
        if digest(raw) != row['sha256']: raise ValueError('corpus_hash_mismatch')
        body = json.loads(raw)
        if images(body) != row['image_sha256']: raise ValueError('corpus_image_hash_mismatch')
        requests.append((row, body))
    return manifest, requests


def prepare(paths, output, corpus_id):
    if len(paths) != N: raise ValueError('provide_exactly_40_paths_in_llmalt_order')
    rows = []
    for path in paths:
        raw = Path(path).read_bytes(); body = json.loads(raw)
        if body.get('model') != 'gemma-4-31b-it': raise ValueError('actual_gemma_decision_required')
        rows.append(dict(path=str(Path(path).resolve()), sha256=digest(raw), image_sha256=images(body)))
    write_json(output, dict(schema='ugrp.llmhost.corpus.v1', corpus_id=corpus_id,
                            requests=rows, preserve_order=True))


def judge(status, response):
    if status != 200: return 'http_' + str(status)
    try:
        choice = response['choices'][0]
        if choice.get('finish_reason') != 'stop': return 'non_stop_finish'
        message = choice['message']
        if message.get('refusal') or message.get('tool_calls'): return 'refusal_or_tool_call'
        content = message['content'].strip()
        # Same optional markdown fence removal as the existing format probe.
        if content.startswith('```') and content.endswith('```'):
            content = content.split('\n', 1)[1].rsplit('```', 1)[0]
        parsed = json.loads(content)
        if not isinstance(parsed, dict) or not parsed.get('act'): return 'missing_act'
    except (KeyError, IndexError, TypeError, ValueError, AttributeError): return 'invalid_act_json'
    return 'accepted'


def summarize(rows, elapsed, hourly_usd, allocation_s=None):
    walls = [r['wall_s'] for r in rows]
    accepted_walls = [r['wall_s'] for r in rows if r['reason_category'] == 'accepted']
    known = [r for r in rows if r.get('cached_tokens') is not None and r.get('prompt_tokens')]
    prompt = sum(r['prompt_tokens'] for r in known)
    return dict(n=len(rows), success=sum(r['reason_category'] == 'accepted' for r in rows),
        http_429=sum(r['status'] == 429 for r in rows),
        wall_median_s=statistics.median(walls) if walls else None,
        accepted_wall_median_s=statistics.median(accepted_walls) if accepted_walls else None,
        over_8s=sum(w > SLOW_S for w in walls),
        images_forwarded=sum(len(r['image_sha256']) == 1 for r in rows),
        image_scope='wire SHA verified; semantic image use not established',
        cache_ratio=sum(r['cached_tokens'] for r in known) / prompt if prompt else None,
        cache_usage_coverage=len(known), response_journal_cache=False,
        offered_rpm=RPM, completed_rpm=len(rows) * 60 / elapsed if elapsed else None,
        wall_s=elapsed, gpu_hours_benchmark=elapsed / 3600,
        vm_usd_per_hour=hourly_usd, benchmark_compute_usd=hourly_usd * elapsed / 3600,
        allocation_s=allocation_s,
        allocation_compute_usd=hourly_usd * allocation_s / 3600 if allocation_s is not None else None,
        cost_scope='whole G2 VM; disk/network/tax excluded; startup cost requires allocation_s',
        rejection_distribution=dict(Counter(r['reason_category'] for r in rows)))


def metrics_snapshot(endpoint):
    try:
        with urlopen(endpoint.rsplit('/v1/', 1)[0] + '/metrics', timeout=5) as response:
            return response.read().decode()
    except OSError:
        return None


def prefix_counts(raw):
    counts = {}
    for line in (raw or '').splitlines():
        m = re.match(r'(vllm:prefix_cache_(?:hits|queries)_total)(?:\{[^}]*\})? ([0-9.eE+-]+)', line)
        if m: counts[m[1]] = counts.get(m[1], 0) + float(m[2])
    return counts


def benchmark(corpus, output, candidate, hourly_usd, rate_source, *, send=http_send, allocation_s=None):
    check_alerts()
    manifest, requests = load_corpus(corpus)
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    cfg = identity(candidate); endpoint = loopback(cfg['endpoint'])
    before = metrics_snapshot(endpoint)
    started = time.monotonic()

    def one(index, row, original):
        delay = started + index * 60 / RPM - time.monotonic()
        if delay > 0: time.sleep(delay)  # offered traffic pacing, not robot planning
        began = time.monotonic(); body = upstream_body(original, candidate)
        status, raw, error = 0, b'{}', None
        try:
            check_alerts()
            status, raw, _ = send(body, endpoint)
            response = json.loads(raw)
            if not isinstance(response, dict): raise ValueError('response_not_object')
            category = judge(status, response)
            if status == 200 and response.get('model') != cfg['model']: category = 'served_model_mismatch'
        except Exception as exc:
            response = {}; category = 'HOST_ERROR'; error = type(exc).__name__
        wall = time.monotonic() - began
        usage = response.get('usage') or {}; details = usage.get('prompt_tokens_details') or {}
        result = dict(i=index, request_sha256=row['sha256'], wire_sha256=digest(json.dumps(body).encode()),
            image_sha256=images(body), response_sha256=digest(raw), status=status,
            wall_s=wall, dispatch_lag_s=began - (started + index * 60 / RPM),
            prompt_tokens=usage.get('prompt_tokens'), completion_tokens=usage.get('completion_tokens'),
            cached_tokens=details.get('cached_tokens'), usage=usage, error=error,
            reason_category=category, blocked_object='not_applicable_serving_probe',
            minimum_gap='not_measured_serving_probe', attempts=1)
        (output / f'{index:02d}-response.json').write_bytes(raw)
        write_json(output / f'{index:02d}-receipt.json', result)
        return result

    with ThreadPoolExecutor(max_workers=N) as pool:
        futures = [pool.submit(one, i, row, body) for i, (row, body) in enumerate(requests)]
        rows = sorted((f.result() for f in as_completed(futures)), key=lambda row: row['i'])
    elapsed = time.monotonic() - started
    summary = summarize(rows, elapsed, hourly_usd, allocation_s)
    after = metrics_snapshot(endpoint)
    for name, raw in [('before', before), ('after', after)]:
        if raw is not None: (output / f'metrics-{name}.txt').write_text(raw)
    b, e = prefix_counts(before), prefix_counts(after)
    hit_key, query_key = 'vllm:prefix_cache_hits_total', 'vllm:prefix_cache_queries_total'
    if all(k in b and k in e for k in (hit_key, query_key)):
        queries, hits = e[query_key] - b[query_key], e[hit_key] - b[hit_key]
        summary['server_prefix_cache_ratio'] = hits / queries if queries > 0 and 0 <= hits <= queries else None
    else: summary['server_prefix_cache_ratio'] = None
    report = dict(schema='ugrp.llmhost.benchmark.v1', research_result=False,
        corpus_id=manifest['corpus_id'], corpus_sha256=digest(Path(corpus).read_bytes()),
        identity=cfg, rate_source=rate_source, summary=summary, rows=rows)
    write_json(output / 'summary.json', report)
    funnel = []
    for name, test in [('http_200', lambda r: r['status'] == 200),
                       ('model_identity', lambda r: r['reason_category'] != 'served_model_mismatch'),
                       ('stop_and_act_json', lambda r: r['reason_category'] == 'accepted')]:
        eligible = rows if not funnel else eligible
        remaining = [r for r in eligible if test(r)]
        funnel.append(dict(gate=name, input=len(eligible), passed=len(remaining), rejected=len(eligible)-len(remaining)))
        eligible = remaining
    write_json(output / 'funnel.json', dict(cumulative=funnel, source=str(output.resolve()),
        reproduction=f'python3 -m scripts.llmhost_benchmark run --corpus {Path(corpus).resolve()} --candidate {candidate} --output NEW_OUTPUT --hourly-usd {hourly_usd} --rate-source {rate_source}'))
    print(json.dumps(summary, ensure_ascii=False))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='action', required=True)
    prep = sub.add_parser('prepare'); prep.add_argument('requests', nargs='+', type=Path)
    prep.add_argument('--corpus-id', required=True); prep.add_argument('--output', type=Path, required=True)
    run = sub.add_parser('run'); run.add_argument('--corpus', type=Path, required=True)
    run.add_argument('--candidate', choices=('31b_awq', '26b_a4b_awq'), required=True)
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--hourly-usd', type=float, required=True)
    run.add_argument('--rate-source', required=True); run.add_argument('--allocation-s', type=float)
    a = p.parse_args()
    if a.action == 'prepare': prepare(a.requests, a.output, a.corpus_id)
    else:
        if a.hourly_usd <= 0 or (a.allocation_s is not None and a.allocation_s <= 0): p.error('positive cost inputs required')
        benchmark(a.corpus, a.output, a.candidate, a.hourly_usd, a.rate_source, allocation_s=a.allocation_s)


if __name__ == '__main__': main()
