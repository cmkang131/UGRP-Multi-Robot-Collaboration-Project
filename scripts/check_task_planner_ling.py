"""Ling VL adoption check: frozen r4 DEV, bounded cache/image probes.

No full/confirmation mode. Gemma is read-only historical evidence. Failures
remain in N; a hard call/spending stop cancels further network work.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.task_planner import Planner, signature, strong_rule
from harness.task_planner_gemma import Gemma
from harness.task_planner_model import ModelSelection, ModelBudgetExceeded, MAX_TOKENS, LING
from scripts.evaluate_task_planner import dump
from scripts.evaluate_task_planner_observed import key_remaining, summarize

SOURCE = ROOT/'outputs/task-planner-r4-source-20261013'
BASELINE = ROOT/'outputs/task-planner-r4-dev-20261013'
PRICE_KEY = 'ling'
COHORT = 'ling_vl'
RATE_POLICY = "ling_rate_limit_v1"
MODEL = LING
PRICES = {'ling': (0.000000021, 0.0000000616)}
MAX_CALLS, MAX_REPAIRS, MAX_USD, MIN_REMAINING = 600, 0, .08, 1.5


def read(path):
    return path.read_bytes() if path.exists() else subprocess.check_output(['zstd', '-qdc', str(path)+'.zst'])


def read_ledger(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def frozen():
    raw = read(BASELINE/'calls.jsonl')
    rows = sorted([json.loads(line) for line in raw.splitlines()], key=lambda r:(r['case_id'], r['condition']))
    ids = json.loads(read(SOURCE/'dev_ids.json'))
    assert len(rows) == 400 and len(set(ids)) == 200
    assert {(r['case_id'], r['condition']) for r in rows} == {(i,a) for i in ids for a in ('no_comm','peer_en')}
    assert all(not r['ambiguous'] for r in rows)
    assert all(sum(r['quality']==q and r['condition']=='peer_en' for r in rows)==n for q,n in [('stale',54),('wrong',56)])
    requests = [r['audit'][0]['request'] for r in rows]
    # Freeze the actual initial model inputs, not a later reconstruction.
    manifest = dict(schema=f'planner.{COHORT}.check.v1', N=200, decisions_per_model=400,
        case_ids=sorted(ids), requests_sha256=digest(requests), baseline_calls_sha256=hashlib.sha256(raw).hexdigest(),
        gold_sha256=hashlib.sha256(read(SOURCE/'eval_only.json')).hexdigest(),
        max_calls_per_model=MAX_CALLS,max_repairs_per_model=MAX_REPAIRS,max_usd=MAX_USD,
        temperature=0,max_tokens=MAX_TOKENS,reasoning=MODEL.reasoning,
        model=vars(MODEL),prices=PRICES,
        dataset='r4 DEV tuning only; historical Gemma; no new confirmation seed')
    for r, req in zip(rows, requests):
        ctx=req['input'];labels={signature(c):c['preview']['public_cost_label'] for c in ctx['candidates']}
        assert labels.get(signature(strong_rule(ctx))) == r['rule_choice']
    usage=[a['usage'] for r in rows for a in r['audit'] if 'usage' in a]
    manifest['expected_usd_from_gemma_tokens']={k:sum(u['prompt_tokens']*p+u['completion_tokens']*c for u in usage)*600/len(usage) for k,(p,c) in PRICES.items()}
    return rows, manifest


class SharedBudget:
    def __init__(self, key_check=key_remaining):
        self.lock=threading.Lock();self.charged=0.;self.actual=0.;self.unknown=0;self.calls=0
        self.key_check=key_check;self.stopped=None;self.key_checks=[]

    def reserve(self, amount):
        with self.lock:
            if self.stopped: raise ModelBudgetExceeded(self.stopped)
            if self.calls % 50 == 0:
                safe=self.key_check();self.key_checks.append(safe)
                remaining=safe.get('limit_remaining')
                if remaining is None or remaining-(MAX_USD-self.actual)<MIN_REMAINING:
                    self.stopped='KEY_REMAINING_FLOOR';raise ModelBudgetExceeded(self.stopped)
            if self.charged+amount > MAX_USD:
                self.stopped='COMBINED_USD_LIMIT';raise ModelBudgetExceeded(self.stopped)
            self.charged+=amount;self.calls+=1

    def reconcile(self, amount, cost):
        with self.lock:
            if type(cost) not in (int,float) or not math.isfinite(cost) or cost<0:
                self.unknown+=1  # Keep the full reservation; never call it free.
            else:
                self.charged+=cost-amount;self.actual+=cost
                if cost>amount or self.charged>MAX_USD:
                    self.stopped='RESPONSE_COST_EXCEEDS_RESERVATION'


class ModelBudget:
    def __init__(self, shared, reserve):
        self.shared=shared;self.reserve_usd=reserve;self.calls=0;self.repairs=0
        self.lock=threading.Lock()

    def reserve(self):
        # This is immediately before the client's only HTTP request.
        with self.lock:
            if self.calls>=MAX_CALLS:raise ModelBudgetExceeded('MODEL_600_CALL_LIMIT')
            self.shared.reserve(self.reserve_usd);self.calls+=1

    def reconcile(self, cost):self.shared.reconcile(self.reserve_usd,cost)

    def repair(self):
        with self.lock:
            if self.repairs>=MAX_REPAIRS:raise ValueError('NO_REPAIR_ALLOWANCE')
            self.repairs+=1


def metrics(rows):
    attempts=[a for r in rows for a in r['audit'] if 'request' in a]
    usages=[a['usage'] for a in attempts if a.get('usage')]
    times=sorted(a['elapsed_s'] for a in attempts if 'elapsed_s' in a)
    prompts=[u['prompt_tokens'] for u in usages if isinstance(u.get('prompt_tokens'),int)]
    cached=[u.get('prompt_tokens_details',{}).get('cached_tokens') for u in usages]
    return dict(conditions=summarize(rows),
        format_errors=sum('rejection' in a for a in attempts),repair_attempts=sum(a.get('attempt',0)>0 for a in attempts),
        fallback=sum(r['fallback'] for r in rows),
        latency_s=dict(median=statistics.median(times) if times else None,p90=times[math.ceil(.9*len(times))-1] if times else None,N=len(times)),
        cost_usd=sum(u['cost'] for u in usages if type(u.get('cost')) in (float,int)),
        usage_known_calls=len(usages),prompt_tokens_median=statistics.median(prompts) if prompts else None,
        cached_tokens_ratio=sum(v for v in cached if isinstance(v,int))/sum(prompts) if prompts and all(isinstance(v,int) for v in cached) else None,
        cached_tokens_known_calls=sum(isinstance(v,int) for v in cached),
        actual_identities=sorted({(u.get('model'),u.get('provider')) for u in usages}))



def guard(rows):
    """Checked after every returned result; stop submitting new requests."""
    attempts=[a for r in rows for a in r['audit'] if 'request' in a]
    if attempts and sum('rejection' in a for a in attempts)/len(attempts)>.05:
        return 'FORMAT_ERROR_RATE_OVER_5_PERCENT'
    called=[r for r in rows if r.get('called')]
    if called and sum(r.get('fallback',False) for r in called)/len(called)>.05:
        return 'FALLBACK_RATE_OVER_5_PERCENT'
    times=[r['wall_s'] for r in called]
    if times and statistics.median(times)>8:return 'MEDIAN_LATENCY_OVER_8_SECONDS'
    return None


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--freeze',type=Path,required=True);ap.add_argument('--execute',action='store_true')
    ap.add_argument('--upstream-root',type=Path,required=True)
    ap.add_argument('--relay-url',default='http://127.0.0.1:18424')
    ap.add_argument('--cache-decisions',type=int,choices=(35,40),required=True)
    ap.add_argument('--main-only',action='store_true',help='Run only the authorized 400; probes await count clarification')
    ap.add_argument('--continue-from',type=Path,help='Continue cache/image probes using the same relay counter and paid ledger')
    ap.add_argument('--image',type=Path,required=True);ap.add_argument('--image-sha256',required=True)
    a=ap.parse_args();old,manifest=frozen()
    if not a.main_only and 400+a.cache_decisions+5>MAX_CALLS:raise ValueError('400_PLUS_CACHE_PLUS_5_EXCEEDS_600')
    image=a.image.read_bytes()
    if hashlib.sha256(image).hexdigest()!=a.image_sha256:raise ValueError('R80_IMAGE_HASH_MISMATCH')
    manifest.update(cache_decisions=a.cache_decisions,image_probes=5,image_sha256=a.image_sha256,
        main_only=a.main_only,
        cache_case_keys=[(r['case_id'],r['condition']) for r in old[:a.cache_decisions]],
        image_case_keys=[(r['case_id'],r['condition']) for r in old[:5]],reask=0)
    if not a.execute:
        a.freeze.parent.mkdir(parents=True,exist_ok=True);dump(a.freeze,manifest)
        print(json.dumps(dict(requests_sha256=manifest['requests_sha256'],expected_usd=manifest['expected_usd_from_gemma_tokens'])));return
    if json.loads(a.freeze.read_text())!=json.loads(json.dumps(manifest)):raise ValueError('FROZEN_INPUT_CHANGED')
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('COMMIT_BEFORE_INFERENCE')
    a.out.mkdir(parents=True,exist_ok=False)
    safe=key_remaining()
    dump(a.out/'preflight.json',dict(manifest=manifest,key=safe,projected_remaining=safe['limit_remaining']-MAX_USD))
    if safe['limit_remaining']-MAX_USD<MIN_REMAINING:raise ModelBudgetExceeded('KEY_REMAINING_FLOOR')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    dump(a.out/'RUN_META.json',dict(**{'class':'dev'},pr=473,sha=sha,branch='claude/e2e18-gemma-planner',batch=COHORT+'-r4-dev'))
    gold={g['case_id']:g for g in json.loads(read(SOURCE/'eval_only.json'))}
    shared=SharedBudget()
    # The upstream owns the HTTP-attempt cap and paid ledger, including the
    # diagnostic probes and every retry; the client is an additional guard.
    history=a.upstream_root/'http_responses.jsonl'
    if history.exists():
        for line in history.read_text().splitlines():
            entry=json.loads(line);shared.actual+=entry.get('cost') or 0;shared.charged+=entry['accounted_cost']
            shared.unknown+=entry.get('cost') is None

    # Uncached UTF-8 upper bound plus wrapper margin; image probes separately
    # reserve a full 16k image-token allowance (the saved r80 RGB is small).
    max_bytes=max(len(json.dumps(r['audit'][0]['request'],ensure_ascii=True).encode()) for r in old)+4096
    price,completion=PRICES[PRICE_KEY];budget=ModelBudget(shared,3*(max_bytes*price+MAX_TOKENS*completion))
    if a.continue_from:
        if a.main_only:raise ValueError('MAIN_ALREADY_EXECUTED')
        previous=json.loads((a.continue_from/'summary.json').read_text())
        if previous['stop_reason'] or previous['calls']!=400:raise ValueError('CANNOT_CONTINUE_STOPPED_OR_INCOMPLETE_MAIN')
        if previous['manifest']['requests_sha256']!=manifest['requests_sha256']:raise ValueError('RESUME_INPUT_CHANGED')
        shared.actual=previous['total_actual_cost_usd'];shared.charged=previous['conservative_accounted_usd']
        shared.unknown=previous['unknown_cost_calls'];shared.calls=budget.calls=previous['calls']
    client=Gemma(url=a.relay_url,selection=MODEL,budget=budget)
    cfg=client.identity['openrouter_v1']
    if cfg.get('max_calls')!=600 or cfg.get('max_attempts')!=3 or cfg.get('max_usd')!=MAX_USD or cfg.get('rate_limit_policy')!=RATE_POLICY:raise ValueError('ACTUAL_UPSTREAM_CAP_REQUIRED')
    dump(a.out/'identity.json',client.identity)
    results={'off':[],'static_first_v1':[],'image':[]};all_called=[];started=time.monotonic()
    if a.continue_from:
        results['off']=[json.loads(line) for line in read(a.continue_from/'off-calls.jsonl').splitlines()]
        all_called=list(results['off'])
        dump(a.out/'continued_from.json',dict(path=str(a.continue_from),summary_sha256=hashlib.sha256((a.continue_from/'summary.json').read_bytes()).hexdigest()))
    def run(previous,phase):
        request=copy.deepcopy(previous['audit'][0]['request']);ctx=request['input']
        if phase=='image':
            import base64
            ctx['own']['rgb'].update(image_b64=base64.b64encode(image).decode(),sha256=a.image_sha256)
        client.planner_prompt_order='static_first_v1' if phase=='static_first_v1' else 'off'
        p=Planner(ctx['robot_id'],ctx['condition'],planner_evidence_gate='on_v1')
        p.inbox.extend(copy.deepcopy(previous['audit'][0].get('channel_evidence_before_gate',[])))
        called=False;t0=time.monotonic()
        def call(req,*,timeout_s):
            nonlocal called
            if req!=request:raise ModelBudgetExceeded('INPUT_CHANGED')
            if shared.stopped:raise ModelBudgetExceeded(shared.stopped)
            called=True
            return client(req,timeout_s=timeout_s)
        try:result=p.decide(ctx,call,repair_budget=0)
        except ModelBudgetExceeded as exc:
            shared.stopped=str(exc);result=p._fallback(ctx,None,str(exc));p.audit.append(dict(budget_stop=str(exc)))
        wall=time.monotonic()-t0
        # Request text is permanent, image bytes are already stored at a hashed
        # source; keep the digest instead of duplicating base64 in the audit.
        for audit in p.audit:
            if 'request' in audit:
                audit['request']['input']['own'].get('rgb',{}).pop('image_b64',None)
        labels={signature(c):c['preview']['public_cost_label'] for c in ctx['candidates']}
        label=labels.get(signature(result['decision'])) if result['decision'] else None
        row={k:copy.deepcopy(v) for k,v in previous.items() if k!='audit'}
        row.update(choice=label,correct=not result['fallback'] and label in gold[row['case_id']]['best_choices'],
            effective_correct=label in gold[row['case_id']]['best_choices'],fallback=result['fallback'],
            status='not_called' if not called else 'fallback' if result['fallback'] else 'ok',
            audit=p.audit,wall_s=wall,called=called,phase=phase)
        with (a.out/(phase+'-calls.jsonl')).open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        if called:
            all_called.append(row)
            shared.stopped=shared.stopped or guard(all_called)
        return row
    # Sequential execution makes the user stop thresholds immediate, with no
    # queued requests after a failing observation and no hidden retries.
    phases=([('off',old)] if a.main_only else [('static_first_v1',old[:a.cache_decisions]),('image',old[:5])] if a.continue_from else [('off',old),('static_first_v1',old[:a.cache_decisions]),('image',old[:5])])
    for phase,cases in phases:
        if phase=='image':budget.reserve_usd+=3*16000*price
        for previous in cases:
            results[phase].append(run(previous,phase))
            if budget.calls and budget.calls%20==0:print(json.dumps(dict(phase=phase,decisions=len(results[phase]),calls=budget.calls,cost=shared.actual,stop=shared.stopped)),flush=True)
        if shared.stopped:print(json.dumps(dict(stopped=shared.stopped,phase=phase)),flush=True)
    http_rows=read_ledger(a.upstream_root/'http_responses.jsonl')
    attempt_rows=read_ledger(a.upstream_root/'http_attempts.jsonl')
    shared.actual=sum(r.get('cost') or 0 for r in http_rows)
    shared.charged=sum(r['accounted_cost'] for r in http_rows)
    shared.unknown=sum(r.get('cost') is None for r in http_rows)
    summary=dict(http_attempts=len(attempt_rows),http_responses=len(http_rows),
        http_statuses={str(status):sum(r['status']==status for r in http_rows) for status in sorted({r['status'] for r in http_rows})},
        total_retry_wait_s=sum(r.get('retry_wait_before_s',0) for r in http_rows),
        total_pacing_wait_s=sum(r.get('pacing_wait_s',0) for r in http_rows),
        schema=f'planner.{COHORT}.r4dev.v1',source_sha=sha,manifest=manifest,
        status='stopped' if shared.stopped else 'main_complete_probes_pending' if a.main_only else 'complete',stop_reason=shared.stopped,wall_s=time.monotonic()-started,
        total_actual_cost_usd=shared.actual,conservative_accounted_usd=shared.charged,unknown_cost_calls=shared.unknown,
        calls=budget.calls,repairs_dispatched=0,key_checks=shared.key_checks,
        phases={k:metrics(rs) for k,rs in results.items()},gemma_r4_dev=metrics(old),
        not_called={k:sum(not r['called'] for r in rs) for k,rs in results.items()},
        limitations=['Tuning synthetic dataset, not confirmation or physical success.','Gemma is historical reference only.','Alias and dated endpoint metadata do not attest immutable served weights.','No format reasks; 400+40+5 decisions plus diagnostics and bounded HTTP retries stay within 600 attempts.'])
    summary['cache_off_matched']=metrics(results['off'][:a.cache_decisions])
    image_checks=[]
    for before,after in zip(results['off'][:5],results['image']):
        def usage(r):return next((x['usage'] for x in r['audit'] if x.get('usage')), {})
        u,v=usage(before),usage(after)
        image_checks.append(dict(case_id=after['case_id'],condition=after['condition'],called=after['called'],
            without_image_prompt_tokens=u.get('prompt_tokens'),with_image_prompt_tokens=v.get('prompt_tokens'),
            image_accepted=bool(v),prompt_increased=bool(v and u and v['prompt_tokens']>u['prompt_tokens'])))
    summary['image_checks']=image_checks
    dump(a.out/'summary.json',summary);dump(a.out/'EXIT.json',dict(exit_code=0,status=summary['status']))
    print(json.dumps(dict(status=summary['status'],calls=budget.calls,cost_usd=shared.actual,stop_reason=shared.stopped)),flush=True)


if __name__=='__main__':main()
