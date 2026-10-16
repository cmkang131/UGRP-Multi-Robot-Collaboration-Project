"""Manual smoke check: exactly three chat POSTs, no retry; Keychain only.

PYTHONPATH=. python experiments/2026-10-16-plannerswap/probe.py --execute --output <NEW-dir>
No simulation, rendering, GUI, or concurrent load test. Never prints request headers.
"""
import argparse
import base64
import datetime
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time
import urllib.error
import urllib.request

from scripts import openrouter_upstream as orp

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path('/Users/changmin/projects/ugrp-wt/e2e18-planner/outputs/task-planner-ling-vl-main-20261013/off-calls.jsonl')
IMAGE = Path('/Users/changmin/projects/ugrp-wt/e2e18-planner/outputs/task-planner-ling-vl-image/r80-r1-00000.jpg')
API = 'https://openrouter.ai/api/v1/'


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if not a.execute:
        p.error('--execute required (3 paid calls)')
    a.output.mkdir(parents=True, exist_ok=False)
    key = orp.keychain_key()
    image = IMAGE.read_bytes()
    image_sha = hashlib.sha256(image).hexdigest()
    with SOURCE.open() as f:
        rows = [json.loads(next(f)) for _ in range(3)]
    with urllib.request.urlopen(API + 'models/' + orp.MODEL + '/endpoints', timeout=30) as r:
        catalog = json.load(r)
    ep = next(e for e in catalog['data']['endpoints'] if e['tag'] == orp.config()['tag'])
    assert ep['provider_name'] == 'CoreWeave' and ep['quantization'] == 'fp4' and ep['status'] == 0
    save(a.output/'endpoint.json', ep)
    calls = []
    for i, row in enumerate(rows):
        request = row['audit'][0]['request']
        # Same stored own-RGB input and text method as #552, only three sequential calls.
        messages = json.loads(json.dumps(request['messages']))
        content = messages[-1]['content']
        if isinstance(content, str):
            messages[-1]['content'] = [{'type': 'text', 'text': content}]
        messages[-1]['content'].append({'type': 'image_url', 'image_url': {
            'url': 'data:image/jpeg;base64,' + base64.b64encode(image).decode()}})
        body = orp.upstream_body(dict(model=orp.REGISTERED_MODEL, messages=messages,
            temperature=0, max_tokens=300, response_format={'type': 'json_object'}))
        raw = json.dumps(body).encode()
        req = urllib.request.Request(orp.ENDPOINT, data=raw, headers={
            'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        started = time.monotonic()
        status, data, headers = 0, {}, {}
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                status, data = r.status, json.load(r)
                headers = {k: v for k, v in r.headers.items()
                           if any(s in k.lower() for s in ('provider', 'quantiz', 'request-id', 'generation'))}
        except urllib.error.HTTPError as exc:
            status, data = exc.code, json.loads(exc.read())
        except (OSError, ValueError) as exc:
            data = {'error_type': type(exc).__name__}
        wall = time.monotonic() - started
        generation = {}
        if data.get('id'):
            req = urllib.request.Request(API + 'generation?id=' + data['id'],
                headers={'Authorization': 'Bearer ' + key})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    generation = json.load(r)
            except (OSError, ValueError) as exc:
                generation = {'error_type': type(exc).__name__}
        try:
            decision = json.loads(data['choices'][0]['message']['content'])
            valid = isinstance(decision, dict) and bool(decision.get('act'))
        except (KeyError, IndexError, TypeError, ValueError):
            valid = False
        record = dict(index=i, case_id=row['case_id'], http_status=status, wall_s=wall,
            request_sha256=hashlib.sha256(raw).hexdigest(), image_sha256=image_sha,
            images_sent=1, provider_request=body['provider'], response_headers=headers,
            response=data, generation=generation, valid_json_act=valid)
        # Preserve all text, replacing only image data by its digest.
        messages[-1]['content'][-1]['image_url'] = {'sha256': image_sha, 'bytes': len(image)}
        record['request_without_image'] = dict(body, messages=messages)
        save(a.output/f'call-{i+1}.json', record)
        calls.append(record)
        print(json.dumps(dict(index=i, http_status=status, provider=data.get('provider'),
                              wall_s=round(wall, 3), valid_json_act=valid)), flush=True)
    summary = dict(source_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        checked_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), config=orp.config(),
        method='3 sequential chat POSTs; no retries; same own-RGB as #552; generation GETs for receipts',
        calls=3, http_200=sum(r['http_status'] == 200 for r in calls),
        coreweave=sum(r['response'].get('provider') == 'CoreWeave' for r in calls),
        valid_json_act=sum(r['valid_json_act'] for r in calls),
        rate_limits=sum(r['http_status'] == 429 for r in calls),
        median_wall_s=statistics.median(r['wall_s'] for r in calls),
        usage_cost_usd=sum((r['response'].get('usage') or {}).get('cost', 0) or 0 for r in calls),
        source_requests=str(SOURCE), source_requests_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        image_source=str(IMAGE), image_sha256=image_sha, image_bytes=len(image),
        raw_dir=str(a.output.resolve()), simulation_runs=0,
        todo='Coordinator: next E2E first 30 SIM s: format errors, latency, 429, cache ratio, image delivery')
    save(a.output/'summary.json', summary)
    return 0 if summary['http_200'] == summary['coreweave'] == summary['valid_json_act'] == 3 else 2


if __name__ == '__main__':
    raise SystemExit(main())
