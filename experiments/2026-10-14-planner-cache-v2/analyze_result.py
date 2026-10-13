"""Reconcile every decision with actual upstream usage; abnormal output counts too."""
import json,subprocess,hashlib,statistics,math,collections,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from harness.task_planner import parse,signature
from scripts.check_task_planner_cache import same_decision
E=Path(__file__).parent
B=ROOT/'outputs/task-planner-gemma-json-20261014'
N=ROOT/'outputs/planner-cache-v2-20261014'
R=ROOT/'outputs/planner-cache-v2-r80-20261014'
H=ROOT/'outputs/planner-cache-v2-state-20261014/openrouter'
def read(p):return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])
def rows(p):return [json.loads(x) for x in read(p).splitlines()]
def decision(r):return next((a['decision'] for a in reversed(r['audit']) if a.get('decision') and not a.get('fallback')),None)
def percentile(v):
    v=sorted(v);return dict(N=len(v),median=statistics.median(v) if v else None,p90=v[math.ceil(.9*len(v))-1] if v else None)
def invalid(a):
    if 'response' not in a:return False
    try:parse(a['response'],a['request']['input']['candidates'],'first_object_v1')
    except (ValueError,KeyError,TypeError):return True
    return False

def metric(rs):
    aud=[a for r in rs for a in r['audit'] if 'request' in a]
    usage=[a['usage'] for a in aud if a.get('usage')]
    p=sum(u['prompt_tokens'] for u in usage);c=sum(u['prompt_tokens_details']['cached_tokens'] for u in usage)
    return dict(N=len(rs),called=sum(r.get('called',True) for r in rs),fallback=sum(r['fallback'] for r in rs),
        format_errors=sum(invalid(a) or 'rejection' in a for a in aud),
        malformed_json=sum(a.get('response') is not None and not raw_json(a['response']) for a in aud),
        nonnormal_finish=sum(a.get('finish_reason') not in (None,'stop') for a in aud),
        latency_s=percentile(r['wall_s'] for r in rs if r.get('called',True)),
        prompt_tokens=p,cached_tokens=c,cache_ratio=c/p,usage_N=len(usage),
        cost_usd=sum(u['cost'] for u in usage),input_cost_at_published_rates=p*.00000009-c*.00000004,
        accuracy={a:dict(n=sum(r['correct'] for r in rs if r['condition']==a),N=sum(r['condition']==a for r in rs)) for a in ('no_comm','peer_en')})
def raw_json(s):
    try:return isinstance(json.loads(s),dict)
    except (ValueError,TypeError):return False

def main():
    new=rows(N/'calls.jsonl');old=rows(B/'off-calls.jsonl');summ=json.loads(read(N/'summary.json'))
    assert len(new)==len(old)==400
    ref={(r['case_id'],r['condition']):r for r in old}
    matched=sum(same_decision(r,ref[r['case_id'],r['condition']]) for r in new)
    a,b=metric(old),metric(new);token=json.loads(read(E/'token-prefix-analysis.json'))
    ceiling=token['fixed400']['static_first_v2']['ratios']['all_past_prefix']
    http=rows(H/'http_responses.jsonl');attempts=rows(H/'http_attempts.jsonl')
    assert len(http)==len(attempts)<=600
    cost=sum(r.get('cost') or 0 for r in http);assert cost<=.25
    replay=rows(R/'calls.jsonl');rm={}
    for order in ('off','static_first_v2'):
        rs=[r for r in replay if r['order']==order];usage=[r['response']['usage'] for r in rs if r.get('response',{}).get('usage')]
        p=sum(u['prompt_tokens'] for u in usage);c=sum(u['prompt_tokens_details']['cached_tokens'] for u in usage)
        rm[order]=dict(N=len(rs),expected=27,accepted=len(usage),prompt_tokens=p,cached_tokens=c,ratio=c/p if p else None,
            cost=sum(u.get('cost',0) for u in usage),format_errors=sum(not r['format_valid'] for r in rs),latency_s=percentile(r['wall_s'] for r in rs))
    # Prefix comparison on the same 27-call replay subset, not all 735.
    from importlib.util import spec_from_file_location,module_from_spec
    # Stored token rows permit exact replay-subset ceiling without new inference.
    replay_bounds={}
    for order in rm:
        rs=[r for r in token['r80_actual_provider_speech'][order]['rows'] if r['run']=='e2e18-v379-s61006-r80' and r['robot'] in ('r1','r2')]
        replay_bounds[order]=sum(r['all_past_prefix'] for r in rs)/sum(r['tokens'] for r in rs)
    out=dict(schema='planner.cache_v2.result.v1',source_sha=summ['source_sha'],settings=summ['manifest']['model'],
        status=summ['status'],stop=summ['stop'],baseline_v405=a,static_first_v2=b,agreement=dict(n=matched,N=400),
        adoption_pass=summ['status']=='complete' and matched>=388 and b['fallback']<=a['fallback']+2 and b['format_errors']<=a['format_errors']+2,
        upper_bound=dict(fixed400_ideal_prefix_ratio=ceiling,achieved_fraction=b['cache_ratio']/ceiling,
            before_ideal=token['fixed400']['off']['ratios']['all_past_prefix'],
            tokenizer_vs_actual=token['validation'],interpretation='No eviction, all earlier prompts available; cross-run external cache warmth not modelled'),
        cost_change=dict(input_reduction_fraction=1-b['input_cost_at_published_rates']/a['input_cost_at_published_rates'],
            input_reduction_usd=a['input_cost_at_published_rates']-b['input_cost_at_published_rates'],
            actual_main_reduction_usd=a['cost_usd']-b['cost_usd'],cache_read_per_million=.05,uncached_input_per_million=.09),
        r80_speech_replay=dict(results=rm,ideal_prefix_ratios=replay_bounds,unit='Actual code-selected speech; not task-planner image decisions',
            order='27 chronological carrier requests off, then same27 v2; wall gaps accelerated; later arm can benefit from warming'),
        http=dict(N=len(http),statuses=dict(collections.Counter(str(r['status']) for r in http)),
            attempts_distribution=dict(collections.Counter(str(r['attempt']) for r in http)),cost_usd=cost,unknown_cost=sum(r.get('cost') is None for r in http),cap=600,budget=.25),
        tests_unique=35,raw=[str(N),str(R),str(H)],
        limitations=['DEV tuning set; no new confirmation or physical run.',
            'r80 retrieved actual provider traffic is code-selected speech with no image; 196 image decision source remains unconfirmed.',
            'A live new-planner per-robot sequential image cache ratio is not measured.',
            'Historical v405 comparison and sequential replay do not control provider backend cache eviction/warmth.',
            'Gemma cache minimum length/TTL/block contract and OpenRouter forwarding of DeepInfra prompt_cache_key remain unconfirmed.'])
    (E/'summary.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
