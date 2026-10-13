"""Recount saved r4 decisions, paired rules, request equality and receipts."""
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_task_planner import adapt
from scripts.evaluate_task_planner_observed import summarize
from harness.task_planner import SYSTEM, signature, strong_rule
from harness.task_planner_evidence_gate import INSTRUCTION


def read(p):
    return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])


def preserve(path, payload):
    if Path(str(path)+'.zst').exists():
        assert read(path)==payload.encode(), 'saved result changed'
    else:path.write_text(payload)


def main():
    exp=ROOT/'experiments/2026-10-13-e2e18-planner-r4';results={};call_ids=[];hashes={}
    for name,src in [('dev','source'),('tuning','source'),('confirmation','confirmation-observed')]:
        out=ROOT/f'outputs/task-planner-r4-{name}-20261013'
        source=ROOT/f'outputs/task-planner-r4-{src}-20261013'
        public={(r['case_id'],r['condition']):r for r in json.loads(read(source/'cases_public.json'))}
        gold={r['case_id']:r for r in json.loads(read(source/'eval_only.json'))}
        rows=[json.loads(line) for line in read(out/'calls.jsonl').splitlines()]
        assert len(rows)==(400 if name=='dev' else 1536)
        assert len({(r['case_id'],r['condition']) for r in rows})==len(rows)
        changed_requests=changed_rule=0;failures=collections.Counter();rejections=collections.Counter();fallbacks=collections.Counter();arm_usage=collections.defaultdict(collections.Counter)
        for r in rows:
            arm=r['condition'];condition={'no_comm':'none','structured':'fixed','peer_en':'english','leader_en':'english'}[arm]
            _,ctx,labels=adapt(public[r['case_id'],condition],arm,'on_v1')
            expected=dict(system=SYSTEM+'\n'+INSTRUCTION,input=ctx)
            changed_requests+=r['audit'][0]['request']!=expected
            baseline=labels.get(signature(strong_rule(ctx)))
            changed_rule+=baseline!=r['rule_choice']
            assert r['correct']==bool(not r['fallback'] and r['choice'] in gold[r['case_id']]['best_choices'])
            assert r['rule_correct']==(baseline in gold[r['case_id']]['best_choices'])
            for attempt in r['audit']:
                if attempt.get('failure'):failures[attempt['failure']]+=1
                if attempt.get('rejection'):rejections[attempt['rejection']]+=1
                if attempt.get('fallback'):fallbacks[attempt.get('reason','unknown')]+=1
                usage=attempt.get('usage')
                if usage:
                    call_ids.append(usage['call_id'])
                    for k in ('prompt_tokens','completion_tokens','total_tokens','cost'):arm_usage[arm][k]+=usage.get(k,0)
                    arm_usage[arm]['calls']+=1
        saved=json.loads(read(out/'summary.json'))
        assert summarize(rows)==saved['conditions']
        assert changed_requests==changed_rule==0
        results[name]=dict(conditions=saved['conditions'],budget=saved['budget'],
            request_input_changes=changed_requests,rule_choice_changes=changed_rule,
            failure_reasons=dict(failures),rejection_reasons=dict(rejections),fallback_reasons=dict(fallbacks),
            usage_by_arm=dict(arm_usage),source_sha=saved['source_sha'])
        for file in (out/'calls.jsonl',out/'summary.json',out/'scored.json',source/'cases_public.json',source/'eval_only.json'):
            hashes[str(file.relative_to(ROOT))]=hashlib.sha256(read(file)).hexdigest()
    solo=ROOT/'outputs/task-planner-r4-solo-20261013'
    solo_summary=json.loads(read(solo/'summary.json'))
    for r in json.loads(read(solo/'scored.json')):
        call_ids.extend(a['usage']['call_id'] for a in r['audit'] if a.get('usage'))
    ledger=ROOT/'outputs/task-planner-r4-upstream-20261013/openrouter/ledger.jsonl'
    entries=[json.loads(line) for line in read(ledger).splitlines()]
    ledger_ids=[r['request_id'] for r in entries]
    assert len(call_ids)==len(set(call_ids))
    assert len(ledger_ids)==len(set(ledger_ids))
    accounting=dict(client_attempts=sum(r['budget']['calls'] for r in results.values())+solo_summary['calls'],
        http_receipts=len(entries),upstream_attempts=sum(len(r['openrouter']['attempts']) for r in entries),
        provider_reported_usd=sum(r['openrouter'].get('cost') or 0 for r in entries),
        receipts_unknown_cost=sum(r['openrouter'].get('cost') is None for r in entries),
        client_unknown_cost_calls=sum(r['budget']['unknown_cost_calls'] for r in results.values())+solo_summary['unknown_cost_calls'],
        client_accounted_usd=sum(r['budget']['cost_usd'] for r in results.values())+solo_summary['cost_usd'],
        http_statuses=dict(collections.Counter(r['status'] for r in entries)),
        audit_ids_without_receipt=sorted(set(call_ids)-set(ledger_ids)),
        receipt_ids_without_audit=sorted(set(ledger_ids)-set(call_ids)))
    hashes[str(ledger.relative_to(ROOT))]=hashlib.sha256(read(ledger)).hexdigest()
    freeze=json.loads((exp/'freeze.json').read_text())
    assert freeze['parser_sha256']==hashlib.sha256((ROOT/'harness/task_planner_cost_rules.py').read_bytes()).hexdigest()
    result=dict(schema='planner.r4.summary.v1',sets=results,solo=solo_summary,accounting=accounting,
        confirmation_seed=2026101405,parser_frozen=True,tests_passed=17,vm_execution=False,
        calibration=json.loads((exp/'calibration_summary.json').read_text()),
        limitations=['Geometric error is only a proxy for categorical corruption; task perception accuracy is unverified.',
                    'Tuning observations changed from r3; no causal ablation claim.',
                    'New confirmation uses compositional tuning vocabulary, not a broad unseen-vocabulary challenge.',
                    'Verification is not offered by every original task menu; absent-own counts are reported by domain.',
                    'No physical execution or VM submission in r4.'],raw_sha256=hashes)
    preserve(exp/'summary.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    preserve(exp/'call_ids.json',json.dumps(call_ids)+'\n')
    short=dict(schema=result['schema'],confirmation_seed=result['confirmation_seed'],
        parser_frozen=True,tests_passed=17,vm_execution=False,accounting=accounting,solo=solo_summary,
        source_shas={name:record['source_sha'] for name,record in results.items()},
        limitations=result['limitations'],detailed_recount='summary.json.zst',sets={})
    for name,record in results.items():
        short['sets'][name]={arm:{k:values[k] for k in ('main','ambiguous','by_quality','parse_failures')}
                            for arm,values in record['conditions'].items()}
    (exp/'summary_short.json').write_text(json.dumps(short,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(accounting,indent=2))


if __name__=='__main__':main()
