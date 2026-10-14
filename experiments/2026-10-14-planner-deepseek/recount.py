import sys,json,subprocess,statistics,math,collections,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from harness.task_planner import signature,parse
OUT=ROOT/'outputs/task-planner-deepseek-20261014';EXP=ROOT/'experiments/2026-10-14-planner-deepseek'
def read(p):
    return p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)
def rows(p):return [json.loads(x) for x in read(p).splitlines()]
def dist(v):
    v=sorted(v);return dict(N=len(v),median=statistics.median(v) if v else None,p90=v[math.ceil(.9*len(v))-1] if v else None)
def decision(r):return next((a['decision'] for a in reversed(r['audit']) if a.get('decision') and not a.get('fallback')),None)
def matches(a,b):
    x,y=decision(a),decision(b)
    return not a['fallback'] and not b['fallback'] and x is not None and y is not None and signature(x)==signature(y)
def invalid(a):
    if 'rejection' in a:return True
    if 'response' not in a:return False
    try:parse(a['response'],a['request']['input']['candidates'],'first_object_v1')
    except (ValueError,KeyError,TypeError):return True
    return False
def metrics(rs):
    aa=[a for r in rs for a in r['audit'] if 'request' in a];uu=[a['usage'] for a in aa if a.get('usage')]
    pp=sum(u['prompt_tokens'] for u in uu);cc=sum(u.get('prompt_tokens_details',{}).get('cached_tokens',0) for u in uu)
    return dict(N=len(rs),correct=sum(r['correct'] for r in rs),effective_correct=sum(r['effective_correct'] for r in rs),rule_correct=sum(r['rule_correct'] for r in rs),called=sum(r.get('called',True) for r in rs),fallback=sum(r['fallback'] for r in rs),format_errors=sum(invalid(a) for a in aa),repair_attempts=sum(a.get('attempt',0)>0 for a in aa),latency_s=dist([r['wall_s'] for r in rs if r.get('called',True)]),provider_latency_s=dist([u['transport']['latency_s'] for u in uu if u.get('transport',{}).get('latency_s') is not None]),prompt_tokens=pp,prompt_tokens_median=statistics.median(u['prompt_tokens'] for u in uu) if uu else None,cached_tokens=cc,cache_ratio=cc/pp if pp else None,cost_usd=sum(u.get('cost',0) or 0 for u in uu),reasoning_tokens=sum(u.get('completion_tokens_details',{}).get('reasoning_tokens',0) or 0 for u in uu),conditions={c:dict(n=sum(r['correct'] for r in rs if r['condition']==c),N=sum(r['condition']==c for r in rs),rule_n=sum(r['rule_correct'] for r in rs if r['condition']==c),quality={q:dict(n=sum(r['correct'] for r in rs if r['condition']==c and r['quality']==q),N=sum(r['condition']==c and r['quality']==q for r in rs)) for q in ['stale','wrong']}) for c in ['no_comm','peer_en']})
def main():
    summary=json.loads(read(OUT/'summary.json'));off=rows(OUT/'off-calls.jsonl');v2=rows(OUT/'static_first_v2-calls.jsonl');im=rows(OUT/'image-calls.jsonl');old=rows(ROOT/'outputs/task-planner-gemma-json-20261014/off-calls.jsonl');ref={(r['case_id'],r['condition']):r for r in old};http=rows(ROOT/'outputs/planner-deepseek-state-20261014/openrouter/http_responses.jsonl');attempt=rows(ROOT/'outputs/planner-deepseek-state-20261014/openrouter/http_attempts.jsonl')
    pairs=[(r,ref[r['case_id'],r['condition']]) for r in off]
    assert len(off)==400 and len(ref)==400
    assert all(r['audit'][0]['request']==b['audit'][0]['request'] for r,b in pairs)
    cost=sum(r.get('cost') or 0 for r in http)
    result=dict(schema='planner.deepseek_fp8.result.v1',source_sha=summary['source_sha'],status=summary['status'],stop_reason=summary['stop_reason'],settings=dict(model='deepseek/deepseek-v4.1-flash',provider_order=['deepinfra/fp8'],reasoning_enabled=False,response_format='json_object',temperature=0,max_tokens=768,bundles=['e2e18-v432','e2e18-v433'],default='e2e18-v405'),deepseek=metrics(off),gemma_v405=metrics(old),static_first_v2=metrics(v2),off_matched40=metrics(off[:40]),image=metrics(im),all_decisions=metrics(off+v2+im),image_checks=summary['image_checks'],paired=dict(N=len(pairs),agreement=sum(matches(r,b) for r,b in pairs),gemma_only_correct=sum(b['correct'] and not r['correct'] for r,b in pairs),deepseek_only_correct=sum(r['correct'] and not b['correct'] for r,b in pairs),both_correct=sum(r['correct'] and b['correct'] for r,b in pairs),neither_correct=sum(not r['correct'] and not b['correct'] for r,b in pairs)),http=dict(attempts=len(attempt),responses=len(http),statuses=dict(collections.Counter(str(r['status']) for r in http)),retry_attempt_distribution=dict(collections.Counter(str(r['attempt']) for r in http)),cost_usd=cost,cost_per_http_attempt=cost/len(attempt),cost_per_decision=cost/445,unknown_cost=sum(r.get('cost') is None for r in http),actual_models=dict(collections.Counter(r.get('model') for r in http)),actual_providers=dict(collections.Counter(r.get('provider') for r in http))),limitations=['Tuning DEV synthetic inputs; not confirmation or physical success.','Historical Gemma baseline; no new Gemma calls.','Cache order and warming/time effects are not isolated.','Five repeated saved-image probes verify input acceptance, not visual accuracy.','API alias and dated endpoint name do not attest immutable served weights.'],raw_root=str(OUT))
    (EXP/'paired-decisions.json').write_text(json.dumps([dict(case_id=r['case_id'],condition=r['condition'],quality=r['quality'],deepseek_choice=r['choice'],gemma_choice=b['choice'],deepseek_correct=r['correct'],gemma_correct=b['correct'],rule_correct=r['rule_correct'],same_act_args=matches(r,b)) for r,b in pairs],ensure_ascii=False,separators=(',',':'))+'\n')
    (EXP/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
