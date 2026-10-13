"""Burst probe: N planner requests per (model, provider) at ~40/min, record 429s, latency, cost, JSON validity.

Key is read in-process from the macOS keychain and never printed. Hard cap: 40 calls per target.
"""
import base64, json, subprocess, sys, time, urllib.request, urllib.error, statistics, concurrent.futures as cf

SRC = sys.argv[1]          # off-calls.jsonl with stored requests
IMG = sys.argv[2]          # stored own-RGB jpg
OUT = sys.argv[3]
TARGETS = [tuple(x.split('@')) for x in sys.argv[4].split(',')] if len(sys.argv) > 4 else [('inclusionai/ling-3.0-flash-vl', 'DeepInfra'), ('google/gemma-4-26b-a4b-it', 'DeepInfra'),
           ('google/gemma-4-31b-it', 'DeepInfra'), ('inclusionai/ling-3.0-flash-vl', 'Novita')]
N, WORKERS, SPACING = 40, 6, 1.5   # one submit every 1.5 s => 40/min

key = subprocess.run(['security', 'find-generic-password', '-s', 'ugrp-openrouter', '-a', 'openrouter', '-w'],
                     capture_output=True, text=True).stdout.strip()
img = 'data:image/jpeg;base64,' + base64.b64encode(open(IMG, 'rb').read()).decode()
reqs = []
for line in open(SRC):
    a = json.loads(line)['audit'][0]['request']
    reqs.append(a)
    if len(reqs) == N: break


def call(model, provider, q):
    body = dict(model=model, temperature=0, max_tokens=300,
                provider=dict(order=[provider], allow_fallbacks=False),
                messages=[dict(role='system', content=q['system']),
                          dict(role='user', content=[dict(type='text', text=json.dumps(q['input'])),
                                                     dict(type='image_url', image_url=dict(url=img))])])
    if 'ling' in model: body['reasoning'] = dict(enabled=False)
    r = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions', data=json.dumps(body).encode(),
                               headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    t = time.time()
    try:
        d = json.loads(urllib.request.urlopen(r, timeout=60).read())
        txt = d['choices'][0]['message'].get('content') or ''
        try:
            s = txt[txt.index('{'):txt.rindex('}') + 1]; ok = 'act' in json.loads(s)
        except Exception:
            ok = False
        u = d.get('usage', {})
        return dict(status=200, wall=time.time() - t, valid=ok, cost=u.get('cost') or 0,
                    prompt=u.get('prompt_tokens'), cached=(u.get('prompt_tokens_details') or {}).get('cached_tokens'),
                    out=u.get('completion_tokens'), provider=d.get('provider'))
    except urllib.error.HTTPError as e:
        return dict(status=e.code, wall=time.time() - t, body=e.read()[:300].decode('utf8', 'replace'))
    except Exception as e:
        return dict(status='ERR', wall=time.time() - t, body=repr(e)[:200])


summary = []
with open(OUT, 'w') as f:
    for model, provider in TARGETS:
        futs = []
        with cf.ThreadPoolExecutor(WORKERS) as ex:
            for q in reqs:
                futs.append(ex.submit(call, model, provider, q)); time.sleep(SPACING)
            res = [x.result() for x in futs]
        for x in res: f.write(json.dumps(dict(model=model, provider_pin=provider, **x)) + '\n')
        ok = [x for x in res if x['status'] == 200]
        s = dict(model=model, provider=provider, n=len(res), ok=len(ok),
                 http429=sum(x['status'] == 429 for x in res), other_err=sum(x['status'] not in (200, 429) for x in res),
                 valid_json=sum(x['valid'] for x in ok),
                 latency_med=round(statistics.median([x['wall'] for x in ok]), 2) if ok else None,
                 latency_max=round(max([x['wall'] for x in ok]), 2) if ok else None,
                 cost=round(sum(x['cost'] for x in ok), 5),
                 prompt_med=statistics.median([x['prompt'] for x in ok if x['prompt']]) if ok else None,
                 cache_ratio=round(sum(x['cached'] or 0 for x in ok) / max(1, sum(x['prompt'] or 0 for x in ok)), 3),
                 err_sample=next((x.get('body') for x in res if x['status'] != 200), None))
        summary.append(s); print(json.dumps(s, ensure_ascii=False), flush=True)
json.dump(summary, open(OUT + '.summary.json', 'w'), indent=1, ensure_ascii=False)
