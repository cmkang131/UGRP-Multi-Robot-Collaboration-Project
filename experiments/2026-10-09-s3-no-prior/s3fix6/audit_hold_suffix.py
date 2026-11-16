"""Post-run diagnostic only: reported-belief error before final hold proposals.

This does not alter the preregistered full-stream candidate selection.
A hold-only suffix is not by itself proof of the controller's terminal flag.
"""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
from harness.pf_observation_consistency import OPTIONS
RAW=Path('/Users/changmin/projects/ugrp/outputs')
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def audit(base):
    output=[]
    for seed in (55001,55002):
        truth=RAW/f'goal-route-motion-audit-v1/seed{seed}/eval_only/trajectory.jsonl'
        gt=rows(truth);lookup={round(q['t'],6):q for q in gt}
        origin=np.array(gt[0]['robot_xyz_m'][:2]);yaw=gt[0]['robot_yaw_rad'];co,si=math.cos(yaw),math.sin(yaw);rot=np.array([[co,-si],[si,co]])
        for option in OPTIONS[1:]:
            path=base/f'{seed}-{option}';commands=json.loads((path/'commands.json').read_text())
            last=max((i for i,c in enumerate(commands) if c['kind']!='hold'),default=-1);stop=last+1
            result=dict(seed=seed,option=option,last_nonhold_t=commands[last]['t'] if stop else None,
                hold_only_suffix_frames=len(commands)-stop,selection_window_changed=False,
                terminal_flag_inferred=False,commands_sha256=sha(path/'commands.json'),truth_sha256=sha(truth),prefix={})
            for current in ('off',option):
                source=base/f'{seed}-{current}'/'frontend-covariances.jsonl';points=rows(source)[:stop]
                if not points:
                    result['prefix'][current]=dict(frames=0,metrics=None);continue
                actual=np.array([rot.T@(np.array(lookup[round(q['t'],6)]['robot_xyz_m'][:2])-origin) for q in points])
                estimate=np.array([q['pose'][:2] for q in points]);e=np.linalg.norm(estimate-actual,axis=1)
                sigma=np.sqrt(np.linalg.eigvalsh(np.array([q['covariance'] for q in points])[:,:2,:2])[:,-1])
                result['prefix'][current]=dict(frames=len(points),xy_rmse_m=float(np.sqrt(np.mean(e**2))),
                    final_error_m=float(e[-1]),over_3sigma_fraction=float(np.mean(e>3*sigma)),prediction_sha256=sha(source))
            output.append(result)
    return dict(eval_only=True,selection_rule_changed=False,scope='Diagnostic prefix only; full-controller reported belief, not proof of fresh RGB assimilation on every row',rows=output)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with a.output.open('x') as f:f.write(json.dumps(audit(a.input),indent=2,allow_nan=False)+'\n')
