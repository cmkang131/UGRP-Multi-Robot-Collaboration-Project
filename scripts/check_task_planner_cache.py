"""One frozen v405 paired check; persistent upstream owns 600 HTTP/$0.25 cap."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,copy,json,subprocess,time,urllib.request
from scripts import check_task_planner_ling as core
from scripts.check_task_planner_gemma_json import configure
from harness.task_planner import Planner,signature
from harness.task_planner_gemma import Gemma
from harness.task_planner_model import GEMMA_JSON,ModelBudgetExceeded

configure()
core.MAX_USD=.25
core.COHORT='gemma_cache_v2'
BASE=core.ROOT/'outputs/task-planner-gemma-json-20261014'


def preflight():
    from scripts.openrouter_upstream import keychain_key
    from harness.zone_study_llm_transport import no_redirect_opener
    key=core.key_remaining()
    req=urllib.request.Request('https://openrouter.ai/api/v1/credits',headers={'Authorization':'Bearer '+keychain_key()})
    with no_redirect_opener().open(req,timeout=15) as response:credits=json.load(response)['data']
    balance=credits['total_credits']-credits['total_usage']
    safe=dict(key=key,account_balance=balance,budget=.25)
    if key['limit_remaining']-.25<1.5 or balance-.25<1.5:raise ModelBudgetExceeded('BALANCE_OR_KEY_FLOOR')
    return safe


def decision(row):
    return next((a['decision'] for a in reversed(row['audit']) if a.get('decision') and not a.get('fallback')),None)


def same_decision(row, reference):
    a,b=decision(row),decision(reference)
    return not row['fallback'] and a is not None and b is not None and signature(a)==signature(b)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--upstream-root',type=Path,required=True);ap.add_argument('--relay-url',default='http://127.0.0.1:18426')
    ap.add_argument('--freeze',type=Path,required=True);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
    old,manifest=core.frozen()
    baseline=[json.loads(x) for x in core.read(BASE/'off-calls.jsonl').splitlines()]
    ref={(r['case_id'],r['condition']):r for r in baseline}
    manifest.update(reference='v405',reference_sha256=core.digest(baseline),order='static_first_v2',
        total_http_cap=600,total_usd_cap=.25,main_decisions=400,reasks=0,
        adoption=dict(agreement_at_least=388,fallback_max=sum(r['fallback'] for r in baseline)+2,
                      format_max=core.metrics(baseline)['format_errors']+2))
    if not a.execute:
        core.dump(a.freeze,manifest);print(json.dumps({'N':400,'hash':manifest['requests_sha256']}));return
    if json.loads(a.freeze.read_text())!=json.loads(json.dumps(manifest)):raise ValueError('FREEZE_CHANGED')
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('COMMIT_BEFORE_CALLS')
    a.out.mkdir(parents=True,exist_ok=False);core.dump(a.out/'preflight.json',preflight())
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    core.dump(a.out/'RUN_META.json',dict(**{'class':'dev'},pr=473,sha=sha,branch='claude/e2e18-gemma-planner',batch='cache-v2'))
    shared=core.SharedBudget();budget=core.ModelBudget(shared,.008)
    client=Gemma(url=a.relay_url,selection=GEMMA_JSON,budget=budget,planner_prompt_order='static_first_v2')
    cfg=client.identity['openrouter_v1']
    if any(cfg.get(k)!=v for k,v in dict(max_calls=600,max_usd=.25,max_attempts=3,rate_limit_policy='planner_rate_limit_v1').items()):raise ValueError('UPSTREAM_CAP_REQUIRED')
    core.dump(a.out/'identity.json',client.identity)
    gold={g['case_id']:g for g in json.loads(core.read(core.SOURCE/'eval_only.json'))}
    rows=[]
    for previous in old:
        req=copy.deepcopy(previous['audit'][0]['request']);ctx=req['input']
        p=Planner(ctx['robot_id'],ctx['condition'],planner_evidence_gate='on_v1',response_parser='first_object_v1')
        p.inbox.extend(copy.deepcopy(previous['audit'][0].get('channel_evidence_before_gate',[])))
        called=False;t=time.monotonic()
        def invoke(request,*,timeout_s):
            nonlocal called
            if request!=req:raise ModelBudgetExceeded('INPUT_CHANGED')
            if shared.stopped:raise ModelBudgetExceeded(shared.stopped)
            called=True;return client(request,timeout_s=timeout_s)
        try:result=p.decide(ctx,invoke,repair_budget=0)
        except ModelBudgetExceeded as exc:
            shared.stopped=str(exc);result=p._fallback(ctx,None,str(exc));p.audit.append({'budget_stop':str(exc)})
        labels={signature(c):c['preview']['public_cost_label'] for c in ctx['candidates']}
        label=labels.get(signature(result['decision'])) if result['decision'] else None
        row={k:copy.deepcopy(v) for k,v in previous.items() if k!='audit'}
        row.update(choice=label,correct=not result['fallback'] and label in gold[row['case_id']]['best_choices'],
                   effective_correct=label in gold[row['case_id']]['best_choices'],fallback=result['fallback'],
                   called=called,audit=p.audit,wall_s=time.monotonic()-t,phase='static_first_v2')
        rows.append(row)
        with (a.out/'calls.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        shared.stopped=shared.stopped or core.guard(rows)
        if len(rows)%20==0:print(json.dumps(dict(N=len(rows),calls=budget.calls,cost=shared.actual,stop=shared.stopped)),flush=True)
    http=core.read_ledger(a.upstream_root/'http_responses.jsonl')
    metrics=core.metrics(rows)
    matches=sum(same_decision(r,ref[r['case_id'],r['condition']]) for r in rows)
    gate=manifest['adoption'];adopt=not shared.stopped and matches>=gate['agreement_at_least'] and metrics['fallback']<=gate['fallback_max'] and metrics['format_errors']<=gate['format_max']
    summary=dict(source_sha=sha,status='stopped' if shared.stopped else 'complete',stop=shared.stopped,
                 manifest=manifest,metrics=metrics,baseline=core.metrics(baseline),agreement=dict(n=matches,N=400),
                 adoption_pass=adopt,http_attempts=len(http),http_cost=sum(r.get('cost') or 0 for r in http),
                 unknown_cost=sum(r.get('cost') is None for r in http),http429=sum(r['status']==429 for r in http))
    core.dump(a.out/'summary.json',summary);(a.out/'EXIT').write_text(summary['status']+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('manifest','metrics','baseline')}),flush=True)

if __name__=='__main__':main()
