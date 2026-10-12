"""Small real Gemma latency/status check through the Mac proxy engine (no simulation).

Keys stay in the macOS Keychain; only status, latency and key *index* are written.
Usage: python3 -m scripts.gemma_latency_check REQUEST.json OUTPUT_DIR --calls 14 --threads 2 [--multi-key-v1]
"""
import argparse
import hashlib
import json
import statistics
import sys
import threading
import time
from pathlib import Path

from scripts.gemma_fallback_proxy import Gemma


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values)-1, int(round(q*(len(values)-1))))] if values else None


def summarize(rows):
    walls = [r['wall_s'] for r in rows]
    counts = {}
    for r in rows:
        counts[str(r['status'])] = counts.get(str(r['status']), 0)+1
    return dict(n=len(rows), status=counts, wall_median_s=statistics.median(walls) if walls else None,
                wall_p90_s=percentile(walls, .9), wall_max_s=max(walls, default=None),
                retried=sum(1 for r in rows if (r.get('retry_metrics') or {}).get('retry_count')),
                first_failure=sum(1 for r in rows if (r.get('retry_metrics') or {}).get('first_failure_count')),
                keys_used=sorted({a for r in rows for a in r.get('key_indexes', [])}))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('request', type=Path); p.add_argument('output', type=Path)
    p.add_argument('--calls', type=int, default=14); p.add_argument('--threads', type=int, default=2)
    p.add_argument('--multi-key-v1', action='store_true')
    a = p.parse_args(argv)
    if not 0 < a.calls <= 20: raise ValueError('finite <=20 calls')
    a.output.mkdir(parents=True, exist_ok=False)
    body = a.request.read_bytes()
    engine = Gemma(a.output/'state', expected_model='gemma-4-31b-it', standard=True,
                   expected_version='001', multi_key_v1=a.multi_key_v1)
    rows, lock, todo = [], threading.Lock(), list(range(a.calls))
    stamp = str(time.time())

    def worker():
        while True:
            with lock:
                if not todo: return
                i = todo.pop(0)
            key = hashlib.sha256(f'{stamp}:{i}'.encode()).hexdigest()
            began = time.time()
            status, raw, retry_after = engine.complete(body, f'latency-check:{i}', idempotency_key=key)
            try: reply = json.loads(raw)
            except ValueError: reply = {}
            attempts = reply.get('ugrp_key_attempts') or []
            with lock:
                rows.append(dict(i=i, started_unix=began, wall_s=time.time()-began, status=status,
                    retry_after=retry_after, error=reply.get('error'), usage=reply.get('usage'),
                    upstream_wall_s=reply.get('ugrp_upstream_wall_s'), thoughts=reply.get('ugrp_thoughts_tokens'),
                    key_indexes=[x['key_index'] for x in attempts] or ([reply['key_index']] if 'key_index' in reply else []),
                    attempt_status=[x['status'] for x in attempts], retry_metrics=reply.get('ugrp_retry_metrics')))
    threads = [threading.Thread(target=worker) for _ in range(a.threads)]
    [t.start() for t in threads]; [t.join() for t in threads]
    rows.sort(key=lambda r: r['i'])
    report = dict(multi_key_v1=a.multi_key_v1, threads=a.threads, request_sha256=hashlib.sha256(body).hexdigest(),
                  summary=summarize(rows), rows=rows)
    (a.output/'report.json').write_text(json.dumps(report, indent=1)+'\n')
    print(json.dumps(report['summary']))


if __name__ == '__main__':
    sys.exit(main())
