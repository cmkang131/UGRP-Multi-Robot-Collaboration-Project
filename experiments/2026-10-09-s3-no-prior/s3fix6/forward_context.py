"""Evaluation-only pulse spacing/settling/posture context; no control imports."""
import argparse,json
from collections import Counter
from pathlib import Path
import numpy as np
RAW=Path('/Users/changmin/projects/ugrp/outputs')
CASES=[('v149',RAW/'s3-sweep-b73ce193-s14201-v149','r2',False),('55001',RAW/'goal-route-motion-audit-v1/seed55001','r3',True),('55002',RAW/'goal-route-motion-audit-v1/seed55002','r3',True)]
def rows(path):return [json.loads(s) for s in path.read_text().splitlines()]
def evaluate(pulses_dir):
    windows=[];postures=[];holds=[]
    for case,raw,rid,own in CASES:
        pulses=json.loads((pulses_dir/f'{case}-pulses.json').read_text())
        truth=rows(raw/('eval_only/trajectory.jsonl' if own else f'eval_only/{rid}/trajectory.jsonl'))
        times=np.array([r['t'] for r in truth]);xy=np.array([r['robot_xyz_m'][:2] for r in truth])
        commands=rows(raw/f'robots/{rid}/commands.jsonl')
        sequence=[c for c in commands if c.get('kind') in ('hold','drive','mecanum')]
        spans=Counter();early=[]
        for i,c in enumerate(sequence):
            if not c.get('forward'):continue
            end=c['t']+c['duration_s']
            if i+1<len(sequence):end=min(end,sequence[i+1]['t'])
            span=round(end-c['t'],8);spans[str(span)]+=1
            if span<c['duration_s']-1e-8:early.append(dict(t=c['t'],span=span))
        holds.append(dict(case=case,issued_interval_histogram=dict(spans),early_interruption=early,
            scope='issued command boundaries, not measured wheel motion'))
        moving=[c['t'] for c in commands if c['kind'] in ('drive','mecanum') and any(c.get(k,0) for k in ('forward','left','turn'))]
        def at(t):return np.array([np.interp(t,times,xy[:,i]) for i in (0,1)])
        for horizon in (.2,.3,.4):
            for group in ('all','no_contact'):
                selected=[r for r in pulses if group=='all' or not r['contact']]
                actual=sum(np.linalg.norm(at(min(r['t']+horizon,next((v for v in moving if v>r['t']+1e-8),times[-1])))-at(r['t'])) for r in selected)
                predicted=sum(np.linalg.norm(r['pred']) for r in selected)
                windows.append(dict(case=case,group=group,horizon=horizon,n=len(selected),predicted_m=predicted,actual_m=actual,ratio=predicted/actual))
        servo={};counts=Counter()
        for c in commands:
            if c['kind']=='initial_servo_command':servo.update(c['pulses'])
            if c['kind']=='arm':servo[str(c['servo_id'])]=c['pulse']
            if c['kind']=='look':servo['6']=c['pan_pulse']
            if c['kind'] in ('drive','mecanum') and c.get('forward'):counts[str(sorted(servo.items()))]+=1
        postures.append(dict(case=case,issued_servo_at_forward=dict(counts)))
    return dict(eval_only=True,method='Fixed calibration terminal mean; horizon clipped at next motion; contact labels from original 0.2s window',windows=windows,postures=postures,holds=holds)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pulses',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with a.output.open('x') as f:f.write(json.dumps(evaluate(a.pulses),indent=2)+'\n')
