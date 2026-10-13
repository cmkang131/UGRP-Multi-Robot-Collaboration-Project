import json,sys,collections,hashlib,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.summarize_task_planner_r2 import summarize,read
from scripts.evaluate_task_planner import adapt,ARMS
from harness.task_planner import strong_rule,signature

def paired(source,output):
    result=summarize(source,output)
    gold={r['case_id']:r for r in json.loads(read(source/'results_scored.json')) if r['model']=='rules' and r['condition']=='none'}
    public={(r['case_id'],r['condition']):r for r in json.loads(read(source/'cases_public.json'))}
    rows=json.loads(read(output/'scored.json'))
    comparisons=[]
    for row in rows:
        record=dict(row)
        for mode in ('off','on_v1'):
            _,ctx,labels=adapt(public[row['case_id'],ARMS[row['condition']]],row['condition'],mode)
            decision=labels[signature(strong_rule(ctx))]
            record['rule_'+mode]=decision in gold[row['case_id']]['best_choices']
        comparisons.append(record)
    for arm,rec in result['conditions'].items():
        main=[r for r in comparisons if r['condition']==arm and not r['ambiguous']]
        amb=[r for r in comparisons if r['condition']==arm and r['ambiguous']]
        rec['rule_off']=dict(n=sum(r['rule_off'] for r in main),N=len(main))
        rec['rule_ambiguous']=dict(n=sum(r['rule_on_v1'] for r in amb),N=len(amb))
        rec['paired']={label:sum((r['correct'],r['rule_on_v1'])==flags for r in main) for label,flags in dict(both_correct=(True,True),model_only=(True,False),rule_only=(False,True),both_incorrect=(False,False)).items()}
        rec['failures_by_quality']=dict(collections.Counter(r['quality'] for r in comparisons if r['condition']==arm and r['fallback']))
    from scripts.evaluate_task_planner import supplements
    from harness.task_planner import SYSTEM
    from harness.task_planner_evidence_gate import apply,INSTRUCTION
    expected_system=SYSTEM+'\n'+INSTRUCTION
    result['system_differences']=sum(a['request']['system']!=expected_system for r in [json.loads(x) for x in read(output/'calls.jsonl').splitlines()] for a in r['audit'] if 'request' in a)
    solo_rows=json.loads(read(output/'solo.json'))
    result['solo_input_differences']=sum(r['audit'][0]['request']!={'system':expected_system,'input':apply(ctx,'on_v1')} for r,(_,ctx,_) in zip(solo_rows,supplements('on_v1')))
    result['evaluation_summary']=json.loads(read(output/'summary.json'))
    calls=[json.loads(x) for x in read(output/'calls.jsonl').splitlines()]
    audits=[a for r in calls for a in r['audit']]+[a for r in json.loads(read(output/'solo.json')) for a in r['audit']]
    from harness.task_planner_cost_rules import domain_of,extract_english
    english=[r for (cid,arm),r in public.items() if arm=='english']
    parsed=sum(bool(extract_english(domain_of(r['input']),max(r['input']['messages'],key=lambda m:m['observation_time_s'])['body'])) for r in english)
    result['frozen_rule_english_parser']=dict(parsed=parsed,unparsed=len(english)-parsed)
    result['request_attempts']=sum('request' in a for a in audits)
    result['usage_totals']={k:sum((a.get('usage') or {}).get(k,0) or 0 for a in audits) for k in ('prompt_tokens','completion_tokens','total_tokens')}
    result['call_ids']=[a['usage']['call_id'] for a in audits if (a.get('usage') or {}).get('call_id')]
    result['refusals']=dict(collections.Counter(a.get('rejection') for a in audits if a.get('rejection')))
    return result

if __name__=='__main__':
    exp=ROOT/'experiments/2026-10-13-e2e18-planner-r3'
    all_results={}
    for label,source,out in [('tuning','task-planner-v357-source-20261013','task-planner-r3-tuning-20261013'),('confirmation','task-planner-r3-confirmation-source-20261013','task-planner-r3-confirmation-20261013')]:
        r=paired(ROOT/'outputs'/source,ROOT/'outputs'/out)
        # Preserve complete call-id mapping separately; keep summary small.
        ids=r.pop('call_ids');(exp/(label+'-call-ids.json')).write_text(json.dumps(ids)+'\n')
        (exp/(label+'-recount.json')).write_text(json.dumps(r,indent=2)+'\n');all_results[label]=r
    ledger=ROOT/'outputs/task-planner-r3-upstream-20261013/openrouter/ledger.jsonl'
    entries=[json.loads(x) for x in read(ledger).splitlines()]
    accounting=dict(http_requests=len(entries),upstream_attempts=sum(len((r.get('openrouter') or {}).get('attempts',[])) for r in entries),
        http_statuses=dict(collections.Counter(r['status'] for r in entries)),
        known_usd=sum((r.get('openrouter') or {}).get('cost',0) or 0 for r in entries),
        unknown_cost_calls=sum((r.get('openrouter') or {}).get('cost') is None for r in entries),
        path=str(ledger),sha256=hashlib.sha256(read(ledger)).hexdigest())
    result=dict(schema='ugrp.task_planner.evidence_gate.r3',gate='on_v1',default='off',source_sha='961a4947',confirmation_seed=2026101303,
        tuning_set_reused=True,confirmation_independent_physical_data=False,bundles=[387,388],vm='not_submitted; after PR475/476',conditions={},accounting=accounting,
        tests=dict(passed=27,physics=False),limitations=['No own observations in coordinator synthetic source; fresh wrong reports cannot be disproved.','Confirmation uses new seed/new phrases but same synthetic algebra and latent-state cycle.','Native execution is unverified.'])
    for label,r in all_results.items():
        result['conditions'][label]=dict(arms=r['conditions'],solo=r['evaluation_summary']['synthetic_solo'],requests=r['request_attempts'],budget=r['evaluation_summary']['budget'],usage=r['usage_totals'],changed_inputs=len(r['adapter_changed_inputs']),changed_systems=r['system_differences'],changed_solo_inputs=r['solo_input_differences'],frozen_rule_english_parser=r['frozen_rule_english_parser'])
    (exp/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
