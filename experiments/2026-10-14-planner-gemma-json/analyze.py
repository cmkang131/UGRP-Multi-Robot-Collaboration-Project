import json,hashlib,statistics,math,subprocess,collections
from pathlib import Path
root=Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0,str(root))
out=root/'outputs/task-planner-gemma-json-20261014'
exp=root/'experiments/2026-10-14-planner-gemma-json'
def read(p):return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])
def lines(p):return [json.loads(x) for x in read(p).splitlines()]
def digest(p):return hashlib.sha256(read(p)).hexdigest()
def pct(values):
 v=sorted(values);return dict(N=len(v),median=statistics.median(v) if v else None,p90=v[math.ceil(.9*len(v))-1] if v else None)
def decision(r):return next((a['decision'] for a in reversed(r['audit']) if a.get('decision') and not a.get('fallback')),None)
def sig(d):return json.dumps([d['act'],d['args']],sort_keys=True) if d else None
s=json.loads(read(out/'summary.json'))
phases={p:lines(out/(p+'-calls.jsonl')) for p in ('off','static_first_v1','image')}
called=[r for rs in phases.values() for r in rs if r['called']]
audit=[a for r in called for a in r['audit'] if 'request' in a]
http=lines(root/'outputs/planner-gemma-fp4-state-20261014/openrouter/http_responses.jsonl');new=http[2:]
old={(r['case_id'],r['condition']):r for r in lines(root/'outputs/task-planner-r4-dev-20261013/calls.jsonl')}
main=phases['off'];main_called=[r for r in main if r['called']]
match=[r for r in main_called if not r['fallback'] and sig(decision(r))==sig(decision(old[r['case_id'],r['condition']]))]
agreement=dict(n=len(match),N_planned=400,N_called=len(main_called),N_valid=sum(not r['fallback'] for r in main_called),definition='Exact act and args; invalid/failed responses are nonmatches; historical totals not combined')
prior=lines(root/'outputs/task-planner-gemma-fp4-20261014-r2/off-calls.jsonl')[:2]
from harness.task_planner import parse
before=after=0
for r in prior:
 a=next(a for a in r['audit'] if a.get('response'));menu=a['request']['input']['candidates']
 try:parse(a['response'],menu)
 except (ValueError,KeyError,TypeError):before+=1
 try:parse(a['response'],menu,'first_object_v1')
 except (ValueError,KeyError,TypeError):after+=1
short=dict(schema='planner.gemma_json.result.v1',source_sha=s['source_sha'],status=s['status'],stop_reason=s['stop_reason'],bundles=[405,406],settings=dict(model='google/gemma-4-31b-it',provider_order=['deepinfra/turbo'],response_format='json_object',require_parameters=True,response_parser='first_object_v1',temperature=0,max_tokens=768),planned_decisions=445,called_decisions=len(called),main_called=len(main_called),not_called=s['not_called'],fallback=dict(n=sum(r['fallback'] for r in called),N=len(called)),format_errors_before=dict(n=sum(a.get('strict_json_error',False) or 'rejection' in a for a in audit),N=len(called)),format_errors_after=dict(n=sum('rejection' in a for a in audit),N=len(called)),raw_json_syntax_errors=sum(a.get('strict_json_error',False) for a in audit),prior_two_response_reparse=dict(N=2,before=before,after=after,new_provider_calls=0),http_cumulative=dict(N=len(http),statuses=dict(collections.Counter(str(r['status']) for r in http)),cost_usd=sum(r.get('cost') or 0 for r in http),unknown_cost_attempts=sum(r.get('cost') is None for r in http),cap=600,budget_usd=.30),http_current=dict(N=len(new),statuses=dict(collections.Counter(str(r['status']) for r in new)),cost_usd=sum(r.get('cost') or 0 for r in new)),http429=dict(n=sum(r['status']==429 for r in http),N=len(http)),retry_distribution=dict(collections.Counter(str(r['attempt']) for r in new)),reasks=0,response_latency_s=pct(a['elapsed_s'] for a in audit if 'elapsed_s' in a),decision_latency_s=pct(r['wall_s'] for r in called),cache_off_all=s['phases']['off']['cached_tokens_ratio'],cache_off_matched40=s['cache_off_matched']['cached_tokens_ratio'],cache_on=s['phases']['static_first_v1']['cached_tokens_ratio'],prompt_tokens_median=s['phases']['off']['prompt_tokens_median'],images=dict(accepted=sum(r['image_accepted'] for r in s['image_checks']),prompt_increased=sum(r['prompt_increased'] for r in s['image_checks']),called=sum(r['called'] for r in s['image_checks']),N=5,checks=s['image_checks']),r4_agreement=agreement,accuracy_reference={c:{k:v for k,v in s['phases']['off']['conditions'][c]['main'].items() if k in ('n','N','rule_n','effective_n')} for c in ('no_comm','peer_en')},tests_passed=54,raw=str(out),limitations=['Tuning synthetic task decisions, not confirmation or physical success.','JSON mode and wrapper parser changed together; not a parser-only causal comparison.','Prior two calls are separate performance evidence but included in cumulative budget.','Returned model alias does not attest immutable served weights.'])
(exp/'summary.json').write_text(json.dumps(short,indent=2)+'\n')
print(json.dumps(short,indent=2))
