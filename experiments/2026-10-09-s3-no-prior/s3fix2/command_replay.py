"""Replay the saved command-contract failures, own estimates/static goals only.

Counterfactual command projection; it is not counterfactual physical success.
No eval-only file is opened and original logs are never rewritten.
"""
import hashlib
import json
from pathlib import Path
from harness import zone_s3_no_prior_contract as contract
from harness import zone_s3_host as host
from harness.zone_final_pair_binding import bind
from harness.zone_s3_pair_heading import approach_proposal, moving
from harness.zone_solo_cyan_pulse_cal import profile_key

RAW=Path('/Users/changmin/projects/ugrp/outputs/s3-continue-0a690821-s14201-v147')
OUT=Path('/Users/changmin/projects/ugrp/outputs/s3fix2-20261009/command-replay.json')
b=json.loads((RAW/'bundle.json').read_text());record=json.loads((RAW/'student_record.json').read_text())
static=contract.hp.resolve(b['map_id'])[0]
order=next(o for o in contract.inputs()[2]['orders'] if o['kind']=='long_beam')
task=host.pair_task(static,order)
plan=bind(host.skill.make_plan,task=lambda _:task)(static,task['sheet'],task['target'])
profiles=b['controller_config']['pulse_calibration']['profiles'];rows=[]
for rid in ('r1','r2'):
    for command in map(json.loads,(RAW/f'robots/{rid}/commands.jsonl').read_text().splitlines()):
        if not moving(command):continue
        p=next(p for p in reversed(record['localizers'][rid]['poses']) if p['t']<=command['t']+1e-8)
        pose=(p['x'],p['y'],p['yaw']);goal=plan['prestations'][rid]
        try:before=profile_key(command,False)
        except ValueError as e:before=str(e)
        # Isolate the contract repair; use the static final approach goal as
        # carrot. The live driver supplies its collision-planned path carrot.
        action,profile,score=approach_proposal(profiles,pose,goal[:2],goal[:2],goal[2])
        rows.append(dict(robot=rid,t=command['t'],own_estimate=pose,static_goal=goal,
            saved=command,before=before,projected=action,after=profile_key(action,False),score=score))
result=dict(simulation_runs=0,gt_inputs=False,saved_motion_commands=len(rows),
    before_contract_errors=sum(r['before']=='calibrated motion requires one axis' for r in rows),
    after_contract_errors=0,counterfactual_goal_carrot=True,closed_loop_physics_verified=False,rows=rows,
    sources={str(RAW/name):hashlib.sha256((RAW/name).read_bytes()).hexdigest()
        for name in ('bundle.json','student_record.json','robots/r1/commands.jsonl','robots/r2/commands.jsonl')})
assert result['saved_motion_commands']==result['before_contract_errors']==2
OUT.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('rows','sources')}))
