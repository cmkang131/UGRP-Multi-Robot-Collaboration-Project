"""Replay the actual r80 provider wire, explicitly code-selected speech, not planner."""
import sys,json,copy,time,argparse,hashlib,subprocess,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_task_planner_cache import preflight
from scripts.check_task_planner_ling import read_ledger,dump
from harness.task_planner_gemma import Gemma
from harness.task_planner_model import GEMMA_JSON,ordered_context,MAX_TOKENS
SOURCE=Path('/Users/changmin/projects/ugrp-wt/e2e18/outputs/e2e18-admin/protocol-relay-r17/code_v1-dialogue/speech.jsonl')
ENVELOPE=Path('outputs/planner-cache-v2-source-20261014/replay.json')

def load():
    env=json.loads(ENVELOPE.read_text());lookup={r['request_id']:r for r in env}
    rows=[]
    for line in SOURCE.open():
        r=json.loads(line)
        if r['call_id'].split(':')[0]!='e2e18-v379-s61006-r80':continue
        body=r['request'];ctx=json.loads(body['messages'][1]['content'])
        if ctx['robot_id'] not in ('r1','r2'):continue
        r.update(sim_s=lookup[ctx['request_id']]['sim_s'],robot=ctx['robot_id'])
        rows.append(r)
    rows.sort(key=lambda r:(r['sim_s'],int(r['call_id'].split(':')[1].split('-')[1])))
    assert len(rows)==27 and len({r['robot'] for r in rows})==2
    return rows

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--upstream-root',type=Path,required=True);p.add_argument('--relay-url',default='http://127.0.0.1:18426');a=p.parse_args()
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('COMMIT_BEFORE_REPLAY')
    rows=load();a.out.mkdir(parents=True,exist_ok=False)
    dump(a.out/'preflight.json',preflight());dump(a.out/'RUN_META.json',dict(**{'class':'dev'},pr=473,
         sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),branch='claude/e2e18-gemma-planner',batch='cache-v2-r80-speech-replay'))
    manifest=dict(N_per_order=27,source=str(SOURCE),source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        envelope_sha256=hashlib.sha256(ENVELOPE.read_bytes()).hexdigest(),
        unit='Actual r80 code_v1 speech provider input; NOT new task-planner decisions; no original provider images',
        schedule='Same chronological SIM order, both robots interleaved; sequential >=2s pacing, not original wall/SIM gaps',
        settings=dict(model=GEMMA_JSON.model,provider=GEMMA_JSON.provider,response_format='json_object',temperature=0,max_tokens=MAX_TOKENS),
        original_settings='historical speech temperature .2/max_tokens1600; both replay arms use the same current Gemma settings',
        caps=dict(shared_http_attempts=600,shared_usd=.25),requests=[dict(call_id=r['call_id'],sim_s=r['sim_s'],robot=r['robot']) for r in rows])
    dump(a.out/'manifest.json',manifest)
    client=Gemma(url=a.relay_url,selection=GEMMA_JSON)
    cfg=client.identity['openrouter_v1']
    if cfg.get('max_calls')!=600 or cfg.get('max_usd')!=.25:raise ValueError('SHARED_BUDGET_REQUIRED')
    results=[];stop=None
    for order in ('off','static_first_v2'):
        for i,r in enumerate(rows):
            body=copy.deepcopy(r['request']);ctx=json.loads(body['messages'][1]['content'])
            if order!='off':body['messages'][1]['content']=json.dumps(ordered_context(ctx,order),ensure_ascii=True)
            body.update(temperature=0,max_tokens=MAX_TOKENS,**GEMMA_JSON.request_options())
            raw=json.dumps(body).encode();request_hash=hashlib.sha256(raw).hexdigest()
            call=f's4live1-cache-r80-{order}-{i}';t=time.monotonic();error=None;data={};valid=False
            try:
                data=client._json('/v1/chat/completions',body=body,headers={'X-UGRP-Call-ID':call,'X-UGRP-Idempotency-Key':hashlib.sha256(call.encode()).hexdigest()},timeout=30)
                if data.get('model')!=GEMMA_JSON.model or data.get('provider')!='DeepInfra':raise ValueError('IDENTITY_MISMATCH')
                parsed=json.loads(data['choices'][0]['message']['content']);valid=isinstance(parsed,dict) and set(parsed)=={'text'} and isinstance(parsed['text'],str)
            except Exception as exc:error=type(exc).__name__
            result=dict(order=order,case=i,robot=r['robot'],sim_s=r['sim_s'],request=body,request_sha256=request_hash,
                response=data,error=error,format_valid=valid,wall_s=time.monotonic()-t)
            results.append(result)
            with (a.out/'calls.jsonl').open('a') as f:f.write(json.dumps(result)+'\n')
            http=read_ledger(a.upstream_root/'http_responses.jsonl')
            if len(http)>=5 and all(x['status']>=400 for x in http[-5:]):stop='FIVE_HTTP_ERRORS'
            if len(results)>=20 and sum(not x['format_valid'] for x in results)/len(results)>.05:stop='FORMAT_OR_RESPONSE_FAILURE_OVER_5_PERCENT'
            if statistics.median(x['wall_s'] for x in results)>8:stop='MEDIAN_OVER_8_SECONDS'
            if len(http)>=600 or sum(x['accounted_cost'] for x in http)>=.25:stop='SHARED_CAP'
            if stop:break
        print(json.dumps(dict(order=order,N=len(results),stop=stop)),flush=True)
        if stop:break
    dump(a.out/'summary.json',dict(status='stopped' if stop else 'complete',stop=stop,N=len(results),manifest=manifest))
    (a.out/'EXIT').write_text('stopped\n' if stop else 'complete\n')

if __name__=='__main__':main()
