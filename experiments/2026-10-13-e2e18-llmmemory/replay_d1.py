"""100 saved-scene d1 choices + Gemma speech via existing authorized Mac relay.

Original expectation labels are protocol-only, not visual-grip ground truth.
Every failure stays in the denominator. No retries, simulation, or peer synthesis.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time
from urllib.request import Request
from urllib.parse import urlsplit
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness import e2e_dialogue_decider as dd
from harness.zone_study_llm_transport import no_redirect_opener
from scripts.d1_dialogue_upstream import D1
from replay_memory import judge


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(source, out):
    out.mkdir(parents=True, exist_ok=False)
    manifest = []
    for entry in json.loads((source/'manifest.json').read_text()):
        src = source/entry['variants']['memory']['file']
        assert digest(src) == entry['variants']['memory']['sha256']
        req = json.loads(src.read_text()); user, _ = dd.unpack(req)
        user['dialogue_decider'] = dd.MODE
        for part in req['messages'][1]['content']:
            if part.get('type') == 'text' and part['text'].lstrip().startswith('{'):
                part['text'] = json.dumps(user, ensure_ascii=False, sort_keys=True)
        path = out/(entry['run']+'__'+entry['call_id']+'__d1.json')
        path.write_text(json.dumps(req, ensure_ascii=False)+'\n')
        dreq = dd.decision_request(req)
        # Exact outgoing d1 bytes, same attached camera; no expected label in input.
        dpath = path.with_name(path.stem+'-decision.json');dpath.write_text(json.dumps(dreq)+'\n')
        manifest.append({k: copy.deepcopy(entry[k]) for k in ('run','call_id','expected','view')} |
                        dict(file=path.name,sha256=digest(path),decision_file=dpath.name,decision_sha256=digest(dpath),
                             source_request_sha256=digest(src)))
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    sources = ['harness/e2e_dialogue_decider.py','scripts/d1_dialogue_upstream.py',str(Path(__file__).relative_to(Path.cwd()))]
    (out/'RUN_META.json').write_text(json.dumps(dict(**{'class':'dev'},pr=463,branch='claude/e2e18-llmmemory',
        sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),batch=out.name,
        source_sha256={p:digest(p) for p in sources},calls_planned=100,
        paid_path_authorized=True,scope='stored requests only; no VM/physics'),indent=2)+'\n')


def run(out, url, threads=4):
    address=urlsplit(url)
    if (address.scheme!='http' or address.hostname not in ('127.0.0.1','localhost')
            or address.path!='/v1/chat/completions' or address.username or address.password or address.query):
        raise ValueError('MAC_LOOPBACK_RELAY_REQUIRED')
    opener=no_redirect_opener()
    with opener.open(f'http://{address.netloc}/identity',timeout=10) as r:identity=json.load(r)
    cfg=identity.get('openrouter_v1',{})
    if (identity.get('driver_profile')!='study_gemma4_31b_v1' or not identity.get('single_model')
            or identity.get('upstream')!='openrouter_v1' or cfg.get('model')!='google/gemma-4-31b-it'
            or cfg.get('provider_order')!=['DeepInfra'] or cfg.get('allow_fallbacks') is not False
            or identity.get('dialogue_decider','gemma_v0')!='gemma_v0' or identity.get('decider','off')!='off'
            or time.time()>=identity['checked_unix']+identity['valid_for_s']):
        raise ValueError('AUTHORIZED_GEMMA_DEEPINFRA_RELAY_REQUIRED')
    (out/'relay-identity.json').write_text(json.dumps(identity,indent=2)+'\n')
    meta=json.loads((out/'RUN_META.json').read_text())
    if any(digest(p)!=h for p,h in meta['source_sha256'].items()):raise ValueError('REPLAY_SOURCE_CHANGED')
    manifest=json.loads((out/'manifest.json').read_text());results=out/'results.jsonl'
    done=set()
    if results.exists():done={(r['run'],r['call_id'],r['rep']) for r in map(json.loads,results.read_text().splitlines())}
    client=D1(out/'provider');lock=threading.Lock()
    def one(entry,rep):
        if (entry['run'],entry['call_id'],rep) in done:return
        path=out/entry['file']
        if digest(path)!=entry['sha256']:raise ValueError('INPUT_CHANGED')
        req=json.loads(path.read_text());dq=dd.decision_request(req)
        if dq!=json.loads((out/entry['decision_file']).read_text()):raise ValueError('D1_INPUT_CHANGED')
        call_id=f's4live1-{out.name}-{entry["run"]}-{entry["call_id"]}-{rep}'
        row=dict(run=entry['run'],call_id=entry['call_id'],rep=rep,expected=entry['expected'],
                 request_sha256=entry['sha256'],decision_request_sha256=entry['decision_sha256'])
        def speak(body):
            (out/(call_id+'-speech-request.json')).write_text(json.dumps(body,ensure_ascii=False)+'\n')
            start=time.perf_counter()
            post=Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',
                'X-UGRP-Call-ID':call_id,'X-UGRP-Idempotency-Key':call_id})
            try:
                with opener.open(post,timeout=120) as resp:status,raw=resp.status,resp.read(8_000_000)
            except HTTPError as exc:status,raw=exc.code,exc.read(8_000_000)
            row['speech_wall_s']=time.perf_counter()-start;row['speech_http_status']=status
            reply=json.loads(raw)
            (out/(call_id+'-speech-response.json')).write_text(json.dumps(reply,ensure_ascii=False)+'\n')
            row['gemma_usage']=reply.get('usage');row['gemma_provider']=reply.get('provider')
            row['gemma_finish_reason']=(reply.get('choices') or [{}])[0].get('finish_reason')
            if status!=200:raise ValueError('SPEECH_HTTP_ERROR')
            return reply
        began=time.perf_counter()
        try:
            response=client.complete(req,call_id,speak)
            (out/(call_id+'-response.json')).write_text(json.dumps(response,ensure_ascii=False)+'\n')
            receipt=response['ugrp_d1_dialogue']
            row.update(status='ok',selected=receipt['selected'],d1_wall_s=receipt['latency_s'],
                       d1_usage=receipt['usage'],gemma_text=receipt['gemma_message'],outcome=judge(response,entry['view'],False))
        except Exception as exc:
            row.update(status='error',error_type=type(exc).__name__,error_code=str(exc) if isinstance(exc,ValueError) else type(exc).__name__,outcome='error')
        row['wall_s']=time.perf_counter()-began
        row['correct']=row['outcome']==('continue' if entry['expected']=='continue' else 'accepted_'+entry['expected'])
        with lock,results.open('a') as f:
            f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
            print(entry['call_id'],rep,row['status'],row.get('selected'),flush=True)
    with ThreadPoolExecutor(max_workers=threads) as pool:
        jobs=[pool.submit(one,e,r) for r in range(10) for e in manifest]
        for job in jobs:job.result()


def report(out):
    rows=list(map(json.loads,(out/'results.jsonl').read_text().splitlines()))
    def stats(rs):
        return dict(n=len(rs),correct=sum(r['correct'] for r in rs),errors=sum(r['status']!='ok' for r in rs),
            decisions={v:sum(r.get('selected',{}).get('action')==v for r in rs) for v in dd.CRITERIA},
            d1_latency_median_s=statistics.median([r['d1_wall_s'] for r in rs if 'd1_wall_s' in r] or [0]),
            speech_latency_median_s=statistics.median([r['speech_wall_s'] for r in rs if 'speech_wall_s' in r] or [0]),
            pipeline_latency_median_s=statistics.median([r['wall_s'] for r in rs] or [0]))
    summary=dict(all=stats(rows),go=stats([r for r in rows if r['expected']=='GO']),
        call0021=stats([r for r in rows if r['call_id']=='call-0021-r1']),
        cases=[dict(run=e['run'],call_id=e['call_id'],expected=e['expected'],
                    **stats([r for r in rows if (r['run'],r['call_id'])==(e['run'],e['call_id'])]))
               for e in json.loads((out/'manifest.json').read_text())])
    # Provider audit includes decisions whose subsequent speech stage failed.
    d1rows=list(map(json.loads,(out/'provider/calls.jsonl').read_text().splitlines()))
    usages=[r['result'].get('body',{}).get('usage',{}) for r in d1rows]
    gu=[r.get('gemma_usage') or {} for r in rows]
    summary['cost']=dict(d1=sum(u.get('cost',0) for u in usages),d1_cost_reported=sum('cost' in u for u in usages),
        gemma=sum(u.get('cost',0) for u in gu),gemma_cost_reported=sum('cost' in u for u in gu))
    summary['scope']='Protocol expectation agreement; NOT image grip truth, ACK-positive cohort, live deadline or physics validation.'
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','run','report'));p.add_argument('out',type=Path)
    p.add_argument('--source',type=Path,default=Path('outputs/llmmemory-candidate-v3'))
    p.add_argument('--proxy-url',default='http://127.0.0.1:18424/v1/chat/completions')
    a=p.parse_args()
    if a.mode=='prepare':prepare(a.source,a.out)
    elif a.mode=='run':run(a.out,a.proxy_url)
    else:report(a.out)
