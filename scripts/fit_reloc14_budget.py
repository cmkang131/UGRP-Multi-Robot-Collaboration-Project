"""GCP-only v7 diagnostic fit. Proposal only; no runtime or simulation changes."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from scipy.optimize import linprog
from scripts.analyze_reloc11_selfmap import rows


def samples(folder):
    truth={round(r['t'],5):r for r in rows(folder/'raw/eval-only.jsonl')}
    values=[];closed_d=closed_a=0.;previous=None
    for r in rows(folder/'raw/teacher-commands.jsonl'):
        m=r.get('map_pose',{});gt=truth.get(round(r['t'],5),{})
        if not m or gt.get('map_pose_error_yaw_rad') is None:continue
        if previous:
            old=previous['map_pose']
            if m['rgb_fixes']!=old['rgb_fixes']:closed_d=closed_a=0.
            elif int(previous['command']['pwm']['1'])<=1600:
                closed_d+=max(0.,m['issued_distance_since_fix_m']-old['issued_distance_since_fix_m'])
                closed_a+=max(0.,m['issued_turn_since_fix_rad']-old['issued_turn_since_fix_rad'])
        age=m['command_only_age_s']
        values.append(dict(x=[1.,m['issued_distance_since_fix_m'],m['issued_turn_since_fix_rad'],closed_d,closed_a,age],
            xy_m=gt['map_pose_error_xy_m'],yaw_deg=abs(math.degrees(gt['map_pose_error_yaw_rad'])),t=r['t'],phase=r['phase']))
        previous=r
    return values


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('/home/ugrp/ugrp-sim/runs'));p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    paths=sorted(a.root.glob('reloc14-r3-carry-*'));by_run={p.name:samples(p) for p in paths}
    train=next(v for k,v in by_run.items() if '93315' in k);X=np.array([e['x'] for e in train]);fits={}
    for label,trigger in [('xy_m',.5),('yaw_deg',20)]: # existing carry task criteria
        y=np.array([e[label] for e in train]);f=linprog(X.sum(0),A_ub=-X,b_ub=-y,bounds=[(0,None)]*X.shape[1],method='highs')
        if not f.success:raise RuntimeError(f.message)
        scores=[]
        for run,es in by_run.items():
            pred=np.array([e['x'] for e in es])@f.x;truth=np.array([e[label] for e in es]);pos=truth>=trigger
            scores.append(dict(run=run,role='fit' if '93315' in run else 'out_of_fit_already_inspected',N=len(es),
                covered_N=int(np.count_nonzero(pred+1e-8>=truth)),positive_N=int(pos.sum()),
                trigger_recall=float(np.mean(pred[pos]>=trigger)) if pos.any() else None))
        fits[label]=dict(coefficients=f.x.tolist(),scores=scores)
    result=dict(schema='ugrp.reloc14.v7_budget_diagnostic.v1',analysis_host='gcp1',runtime_applied=False,
        physical_validation=False,ready=False,features=['intercept','issued_distance_m','issued_turn_rad',
            'issued_closed_gripper_distance_m','issued_closed_gripper_turn_rad','since_full_RGB_fix_SIM_s'],fits=fits,
        scope='93315 fit; 93266 out-of-fit but already inspected and interrupted; cannot claim blind holdout or closed-loop recall',
        partial_epoch='full-fix epoch retained; partial updates cannot erase correlated unobserved load error',
        sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for f in paths for p in
            (f/'raw/teacher-commands.jsonl.zst',f/'raw/eval-only.jsonl.zst') if p.exists()},
        reproduce='PYTHONPATH=. .venv-sim/bin/python /tmp/fit_reloc14_budget.py --output <file>')
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
