"""Static ACT16 new-start plans only: no simulator, policy or training."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from harness.grasp_act_data import read_json,write_json,sha256
from scripts.analyze_grasp_act_act16a import require_cpu
from scripts.prepare_grasp_act_act14 import sample
from scripts.run_grasp_act_recovery import dependency_modules


def fingerprint(plan):
    return hashlib.sha256(json.dumps(dict(scenario=plan['scenario_id'],item=plan['item_id'],spawns=plan['spawns']),sort_keys=True).encode()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','teacher','saved-act15-plans','output','rejection-table'):
        p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();host=require_cpu();a.output.mkdir(parents=True,exist_ok=False)
    old=[*read_json(a.source/'experiments/2026-10-15-act-train/act12-record-plan.json')['episodes'],
         *read_json(a.saved_act15_plans)['plans'].values()]
    old.extend(read_json(a.source/'experiments/2026-10-15-act-train/act14-plans'/f'{seed}.json') for seed in range(91420,91440))
    seen={fingerprint(plan) for plan in old}
    ledger=[];counts=Counter();plans=[]
    with dependency_modules(a.teacher):
        from scripts import make_solo_teacher_plan as frozen
        for j,seed in enumerate(range(91620,91660)):
            plan=sample(j//4,('cyan','red','green','yellow')[j%4],seed,frozen,ledger,counts)
            key=fingerprint(plan)
            if key in seen:raise ValueError('duplicate training/evaluation start')
            seen.add(key);plan['setup_fingerprint']=key;plans.append(plan)
    write_json(a.output/'eval-plans.json',dict(host=host,status='PLANNED_NOT_EXECUTED',training=False,
        rejection_table=str(a.rejection_table),known_previous_plans=len(old),new_unique_setups=len(plans),
        development_seeds=list(range(91620,91640)),confirmation_seeds=list(range(91640,91660)),episodes=plans))
    write_json(a.output/'setup-funnel.json',dict(counts=dict(counts),rejections=ledger,
        rejection_distribution=dict(Counter(r['category'] for r in ledger)),accepted=40,
        source_sha=__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=a.source,text=True).strip(),
        reproduction='python prepare_eval_plan.py --source SOURCE --teacher FROZEN --saved-act15-plans SAVED --output NEW_DIR --rejection-table TABLE',
        note='Frozen400 proposal/2000 parking-check computation bounds; static generation only, zero rollout/optimizer steps.'))


if __name__=='__main__':main()
