"""At most three diagnostic attempts, retained in the next run's 600/$0.08 ledger."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_task_planner_ling import frozen
from scripts.evaluate_task_planner_observed import key_remaining
from scripts.openrouter_upstream import OpenRouter
from harness.task_planner_model import LING


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    if a.root.exists():raise ValueError('NEW_DIAGNOSTIC_ROOT_REQUIRED')
    balance=key_remaining()
    if balance['limit_remaining']-.08<1.5:raise ValueError('KEY_REMAINING_FLOOR')
    model=OpenRouter(a.root,selection=LING,max_calls=3,max_attempts=1,max_usd=.08,rate_limit_policy='ling_rate_limit_v1')
    (a.root/'preflight.json').write_text(json.dumps(balance,indent=2)+'\n')
    rows,_=frozen()
    for i in range(3):
        request=rows[i]['audit'][0]['request']
        body=dict(model=LING.model,temperature=0,max_tokens=768,messages=[dict(role='system',content=request['system']),dict(role='user',content=json.dumps(request['input'],ensure_ascii=True))])
        status,raw,_=model.complete(json.dumps(body).encode(),f's4live1-ling-r2-diagnostic-{i}')
        data=json.loads(raw)
        print(json.dumps(dict(probe=i+1,status=status,error=data.get('upstream_error'),attempts=data.get('ugrp_openrouter',{}).get('attempts')),ensure_ascii=False),flush=True)
        if status==429:break  # One captured throttle is enough; do not provoke more.


if __name__=='__main__':main()
