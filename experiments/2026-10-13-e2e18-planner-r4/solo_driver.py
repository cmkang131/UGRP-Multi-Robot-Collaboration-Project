"""One replay of the original 24 solo diagnostics, conditional on DEV gate."""
import json
import subprocess
from pathlib import Path
from scripts.evaluate_task_planner import supplements, dump
from scripts.evaluate_task_planner_observed import key_remaining
from harness.task_planner import signature, strong_rule
from harness.task_planner_gemma import Gemma, Budget

out=Path('outputs/task-planner-r4-solo-20261013');out.mkdir(exist_ok=False)
dev=json.loads(Path('outputs/task-planner-r4-dev-20261013/summary.json').read_text())
assert dev['conditions']['peer_en']['by_quality']['wrong']['n']>0
key=key_remaining();dump(out/'preflight.json',dict(key=key,max_usd=.02,decisions=24))
assert key['limit_remaining']-.02>=1.5
budget=Budget(max_calls=48,max_usd=.02);model=Gemma(budget=budget);rows=[]
for i,(p,ctx,best) in enumerate(supplements('on_v1')):
    result=p.decide(ctx,model)
    rows.append(dict(id=i,correct=not result['fallback'] and signature(result['decision'])==best,
        effective_correct=signature(result['decision'])==best,fallback=result['fallback'],
        rule_correct=signature(strong_rule(ctx))==best,audit=p.audit))
summary=dict(n=sum(r['correct'] for r in rows),N=24,rule_n=sum(r['rule_correct'] for r in rows),
    fallback=sum(r['fallback'] for r in rows),calls=budget.calls,cost_usd=budget.charged,
    unknown_cost_calls=budget.unknown,scope='original 24 synthetic solo diagnostics; not fresh confirmation')
dump(out/'scored.json',rows);dump(out/'summary.json',summary)
dump(out/'RUN_META.json',dict(**{'class':'dev'},pr=473,batch='r4-solo',
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()))
(out/'EXIT').write_text('0\n');print(json.dumps(summary))
