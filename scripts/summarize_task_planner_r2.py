"""Recount saved rows and same-input strong rules; never calls a model/physics."""
import argparse,collections,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_task_planner import adapt,ARMS
from harness.task_planner import strong_rule,signature

def summarize(source,output):
    gold={r['case_id']:r for r in json.loads((source/'results_scored.json').read_text()) if r['model']=='rules' and r['condition']=='none'}
    public={(r['case_id'],r['condition']):r for r in json.loads((source/'cases_public.json').read_text())}
    rows=json.loads((output/'scored.json').read_text());calls=[json.loads(x) for x in (output/'calls.jsonl').read_text().splitlines()]
    raw={(r['case_id'],r['condition']):r for r in calls};rules=[];different=[]
    for row in rows:
        _,ctx,labels=adapt(public[row['case_id'],ARMS[row['condition']]],row['condition'])
        sent=next((a['request']['input'] for a in raw[row['case_id'],row['condition']]['audit'] if 'request' in a),None)
        if sent is not None and sent!=ctx:different.append([row['case_id'],row['condition']])
        chosen=labels[signature(strong_rule(ctx))]
        rules.append(dict(row,correct=chosen in gold[row['case_id']]['best_choices'],choice=chosen))
    def counts(rs):
        return dict(n=sum(r['correct'] for r in rs),N=len(rs))
    result=dict(adapter_changed_inputs=different,conditions={})
    for arm in ARMS:
        r=[r for r in rows if r['condition']==arm];main=[x for x in r if not x['ambiguous']]
        baseline=[r for r in rules if r['condition']==arm and not r['ambiguous']]
        result['conditions'][arm]=dict(model=counts(main),effective=dict(n=sum(x['effective_correct'] for x in main),N=len(main)),
            ambiguous=counts([x for x in r if x['ambiguous']]),same_input_rule=counts(baseline),
            subsets={q:dict(model=counts([x for x in main if x['quality']==q]),rule=counts([x for x in baseline if x['quality']==q])) for q in ('stale','wrong')},
            wait=counts([x for x in main if x['domain']=='wait']),help_uncertain=counts([x for x in main if x['domain']=='help' and x['quality']=='uncertain']),
            failures=sum(x['fallback'] for x in r))
    audits=[a for r in calls for a in r['audit']]+[a for r in json.loads((output/'solo.json').read_text()) for a in r['audit']]
    result['failures']=dict(collections.Counter(a['failure'] for a in audits if 'failure' in a))
    result['known_cost_usd']=sum((a.get('usage') or {}).get('cost',0) or 0 for a in audits)
    result['raw']={str(output/p):hashlib.sha256((output/p).read_bytes()).hexdigest() for p in ('scored.json','calls.jsonl','solo.json','summary.json','RUN_META.json')}
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    result=summarize(a.source,a.output);a.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='raw'},indent=2))
