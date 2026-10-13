"""New seed/text/cost solo confirmation; prior 24 solo cases remain diagnostics."""
import argparse,hashlib,json,random,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from harness.task_planner import Planner,candidate,signature,strong_rule
from harness.task_planner_gemma import Gemma,Budget
from harness.task_planner_evidence_gate import apply
SEED=2026101303


def cases():
    rng=random.Random(SEED)
    for i in range(24):
        p=Planner('r1','no_comm',planner_evidence_gate='on_v1');menu=[]
        durations=rng.sample(range(8,80),8)
        for slot in ('B2','B4'):
            for route in ('inner_aisle','outer_aisle'):
                for approach in ('east','west'):
                    t=durations[len(menu)]
                    menu.append(candidate('carry',dict(cargo='sealed_box',to=slot,via=route,approach=approach,mode='solo'),
                        expected_s=t,distance_m=t*.08,blockage_risk='low',unloading_empty='yes',source='new seeded synthetic own travel estimate'))
        rng.shuffle(menu)
        ctx=p.context(now=0,orders=[dict(cargo='sealed_box',required_robots=1,destination_zone='B')],
            static_map=dict(slots=['B2','B4'],routes=['inner_aisle','outer_aisle'],approaches=['east','west']),
            own=dict(robot_id='r1',pose=dict(xy=[0,0],source='synthetic_own_estimate')),
            candidates=menu,task='Transport sealed_box alone into a vacant slot in zone B. Select the slot, aisle and approach with the shortest estimated completion time.')
        yield p,apply(ctx,'on_v1'),signature(min(menu,key=lambda c:c['preview']['expected_s']))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    budget=Budget(max_calls=48,max_usd=.03);model=Gemma(budget=budget) if a.execute else None
    rows=[]
    for i,(p,ctx,best) in enumerate(cases()):
        result=p.decide(ctx,model) if model else None
        rows.append(dict(id=f'new-solo-{SEED}-{i}',correct=bool(result and not result['fallback'] and signature(result['decision'])==best),
            effective_correct=bool(result and signature(result['decision'])==best),fallback=None if result is None else result['fallback'],
            rule_correct=signature(strong_rule(ctx))==best,audit=p.audit))
    summary=dict(seed=SEED,N=24,n=sum(r['correct'] for r in rows),rule_n=sum(r['rule_correct'] for r in rows),
        fallback=sum(r['fallback'] is True for r in rows),called=a.execute,budget=dict(calls=budget.calls,accounted_usd=budget.charged,unknown_cost_calls=budget.unknown),
        source='new authored synthetic destination/route/approach cases; not physical',source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    for name,data in [('scored.json',rows),('summary.json',summary),('RUN_META.json',dict(**{'class':'dev'},pr=473,sha=summary['source_sha'],batch='r3-new-solo-confirmation'))]:
        (a.out/name).write_text(json.dumps(data,indent=2)+'\n')
    (a.out/'EXIT').write_text('0\n');print(json.dumps(summary))

if __name__=='__main__':main()
