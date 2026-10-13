"""Bounded DEV/full paired evaluation; safe key preflight before any model call."""
import argparse
import collections
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.evaluate_task_planner import ARMS, adapt, dump
from harness.task_planner import signature, strong_rule
from harness.task_planner_cost_rules import domain_of, extract_english, extract_fixed
from harness.task_planner_gemma import Budget, Gemma


def key_remaining():
    from scripts.openrouter_upstream import keychain_key
    from harness.zone_study_llm_transport import no_redirect_opener
    req=urllib.request.Request('https://openrouter.ai/api/v1/key',
        headers={'Authorization':'Bearer '+keychain_key()})
    with no_redirect_opener().open(req,timeout=15) as response:data=json.load(response)['data']
    return {k:data.get(k) for k in ('limit','limit_remaining','usage','usage_daily','is_free_tier')}


def summarize(rows):
    def count(rs):
        return dict(n=sum(r['correct'] for r in rs),N=len(rs),rule_n=sum(r['rule_correct'] for r in rs),
            effective_n=sum(r['effective_correct'] for r in rs),fallback=sum(r['fallback'] for r in rs),
            model_only_wins=sum(r['correct'] and not r['rule_correct'] for r in rs),
            rule_only_wins=sum(r['rule_correct'] and not r['correct'] for r in rs))
    out={}
    for arm in sorted({r['condition'] for r in rows}):
        rs=[r for r in rows if r['condition']==arm];main=[r for r in rs if not r['ambiguous']]
        no_own=[r for r in rs if not r['has_own_fact']]
        out[arm]=dict(main=count(main),ambiguous=count([r for r in rs if r['ambiguous']]),
            by_quality={q:count([r for r in main if r['quality']==q]) for q in sorted({r['quality'] for r in main})},
            parse_failures=dict(n=sum(r['parse_failed'] for r in rs),N=sum(r['message_present'] for r in rs)),
            no_own_verification=dict(n=sum(r['verification_offered'] for r in no_own),N=len(no_own),
                by_domain={d:dict(n=sum(r['verification_offered'] for r in no_own if r['domain']==d),N=sum(r['domain']==d for r in no_own)) for d in sorted({r['domain'] for r in no_own})}),
            conflicts=sum(r['conflict'] for r in rs),
            by_own={q:count([r for r in main if r['own_category']==q]) for q in sorted({r['own_category'] for r in main})})
    return out


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--dev',action='store_true');ap.add_argument('--execute',action='store_true')
    ap.add_argument('--max-usd',type=float,default=.3);ap.add_argument('--workers',type=int,default=4)
    ap.add_argument('--relay-url',default='http://127.0.0.1:18424');a=ap.parse_args()
    if a.out.exists():raise SystemExit('new output directory required')
    a.out.mkdir(parents=True)
    source=json.loads((a.source/'cases_public.json').read_text())
    gold={g['case_id']:g for g in json.loads((a.source/'eval_only.json').read_text())}
    obs={g['case_id']:g for g in json.loads((a.source/'observations_eval_only.json').read_text())}
    ids=set(json.loads((a.source/'dev_ids.json').read_text())) if a.dev else set(gold)
    arms=['no_comm','peer_en'] if a.dev else list(ARMS)
    jobs=[(r,arm) for arm in arms for r in source if r['condition']==ARMS[arm] and r['case_id'] in ids]
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    dump(a.out/'RUN_META.json',dict(**{'class':'dev'},pr=473,sha=sha,branch='claude/e2e18-gemma-planner',batch='r4-dev' if a.dev else 'r4-full'))
    # Reserve twice the nominal calls for a single validation repair. $.00045
    # is a conservative planning estimate from r3 plus the new own envelope.
    preflight=dict(decisions=len(jobs),expected_usd=len(jobs)*.00045,max_usd=a.max_usd,
        max_calls=len(jobs)*2,minimum_remaining_usd=1.5,
        sources_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.source.iterdir() if p.is_file()})
    if a.execute:
        safe=key_remaining();remaining=safe['limit_remaining']
        preflight.update(key=safe,projected_remaining_usd=None if remaining is None else remaining-a.max_usd)
        dump(a.out/'preflight.json',preflight)
        if remaining is None or remaining-a.max_usd<1.5:
            dump(a.out/'summary.json',dict(status='budget_stop',preflight=preflight));return
    else:dump(a.out/'preflight.json',preflight)
    budget=Budget(max_calls=len(jobs)*2,max_usd=a.max_usd)
    model=Gemma(url=a.relay_url,budget=budget) if a.execute else None
    lock=threading.Lock()
    def run(job):
        r,arm=job;cid=r['case_id'];g=gold[cid]
        p,ctx,labels=adapt(r,arm,'on_v1')
        baseline=labels.get(signature(strong_rule(ctx)))
        messages=r['input'].get('messages',[]) if arm!='no_comm' else []
        parsed=[]
        if messages:
            body=messages[-1]['body'];d=domain_of(r['input'])
            parsed=extract_fixed(d,body) if isinstance(body,dict) else extract_english(d,body)
        result=p.decide(ctx,model) if model else None
        decision=result['decision'] if result else None;label=labels.get(signature(decision)) if decision else None
        fallback=result['fallback'] if result else False
        record=dict(case_id=cid,condition=arm,domain=g['domain'],quality=g['quality'],ambiguous=g['ambiguous'],
            choice=label,rule_choice=baseline,correct=bool(result and not fallback and label in g['best_choices']),
            rule_correct=baseline in g['best_choices'],effective_correct=bool(result and label in g['best_choices']),
            fallback=fallback,status='not_called' if result is None else 'fallback' if fallback else 'ok',
            message_present=bool(messages),parse_failed=bool(messages and not parsed),
            has_own_fact=bool(ctx['own'].get('observed_facts')),own_category=obs[cid]['calibration_category'],
            # A question has no verification effect with no communication.
            verification_offered=any(c['act']=='search' or (arm!='no_comm' and c['preview']['candidate_evidence']['verification_action']) for c in ctx['candidates']),
            conflict=any(e['status']=='conflict' for e in ctx['evidence_gate']['archived_reports']),
            audit=p.audit)
        with lock:
            with (a.out/'calls.jsonl').open('a') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
        return {k:v for k,v in record.items() if k!='audit'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:rows=list(pool.map(run,jobs))
    summary=dict(schema='planner.r4.observed.v1',source_sha=sha,status='complete' if model else 'dry_run',
        synthetic=True,conditions=summarize(rows),budget=dict(calls=budget.calls,cost_usd=budget.charged,unknown_cost_calls=budget.unknown),
        limitation='Own categorical corruption is a geometric-error proxy from r80; this does not measure actual task perception accuracy or physical success.')
    dump(a.out/'scored.json',rows);dump(a.out/'summary.json',summary)
    dump(a.out/'EXIT.json',dict(exit_code=0,status=summary['status']))
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
