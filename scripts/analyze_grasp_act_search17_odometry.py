"""Offline calibration/evaluation. Privileged labels never enter a controller.

Axis-wise least squares on disjoint episodes, with a fixed command-only model
at runtime. Not an encoder/UMBmark square-path experiment or physical replay.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import numpy as np
from scripts.replay_grasp_act_search17 import load
from harness.grasp_act_visible_world import command_delta, VisibleWorld


def analyze(root):
    rows=[];sources=[];case={}
    for ep in range(16,56):
        ev,led,res,plan=load(root,ep)
        d=root/f'cohort-{ep//16*16:03d}'/f'episode-{ep:03d}'/'raw'
        for stem in ('eval-only.jsonl','teacher-r1.jsonl','teacher-r2.jsonl','plan.json'):
            p=d/stem
            if not p.exists():p=Path(str(p)+'.zst')
            sources.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
        for r in led:
            X=[];Y=[];length=0.;commands=set()
            for i in range(1,len(ev)):
                prev,cur=ev[i-1],ev[i];dt=cur['t']-prev['t'];p=prev['robots'][r]['pose'];q=cur['robots'][r]['pose']
                dx,dy=q[0]-p[0],q[1]-p[1];c,s=math.cos(p[2]),math.sin(p[2])
                da=math.atan2(math.sin(q[2]-p[2]),math.cos(q[2]-p[2]))
                issued=led[r][i-1]['applied_command'];commands.update(issued['wheels'])
                X.append(command_delta(issued,dt));Y.append([c*dx+s*dy,-s*dx+c*dy,da]);length+=math.hypot(dx,dy)
            X=np.array(X);Y=np.array(Y)
            rows.append(dict(ep=ep,rid=r,success=res['physical_success'],gt_length=length,
                issued_length=float(np.linalg.norm(X[:,:2],axis=1).sum()),wheel_levels=sorted(commands),X=X,Y=Y))
        if ep==40:
            for mode in ('off','search17_fixed_v1'):
                model=VisibleWorld('r1',plan['roles']['r1'],odometry=mode)
                for i,e in enumerate(ev):
                    w=model.observe(e['visible_measurements']['r1'],e['t'])
                    if abs(e['t']-ev[0]['t']-17.1)<.01:
                        cyan=w['objects']['cyan_1']['xy'];point=w['beam']['ends'][plan['roles']['r1']]
                        # Compare a relative vector in each body frame; global issued yaw is unanchored.
                        def local_vector(a,b,yaw):
                            dx,dy=a[0]-b[0],a[1]-b[1];c,s=math.cos(yaw),math.sin(yaw)
                            return [c*dx+s*dy,-s*dx+c*dy]
                        v=local_vector(cyan,point,w['robots']['r1']['pose'][2])
                        gt=local_vector(e['objects']['cyan_1']['xy'],e['beam']['ends'][plan['roles']['r1']],e['robots']['r1']['pose'][2])
                        case[mode]={'sim_s':17.1,'cyan_to_end_vector_error_m':math.dist(v,gt),'estimated_body_vector':v,'evaluation_body_vector':gt}
                    model.issue(led['r1'][i]['applied_command'])
    train=[r for r in rows if r['success'] and r['ep']%2==0]
    test=[r for r in rows if not(r['success'] and r['ep']%2==0)]
    X=np.concatenate([r['X'] for r in train]);Y=np.concatenate([r['Y'] for r in train])
    gain=np.sum(X*Y,axis=0)/np.sum(X*X,axis=0);dc=(.35-1/12)/(1-1/12)/.35
    metrics={}
    for split,rs in [('fit',train),('heldout',test)]:
        x=np.concatenate([r['X'] for r in rs]);y=np.concatenate([r['Y'] for r in rs])
        rmse={label:np.sqrt(np.mean((x*g-y)**2,axis=0)).tolist() for label,g in [('nominal',1),('dc_only',dc),('fixed',gain)]}
        # A lagged linear predictor tests whether acceleration transients alone
        # can explain the mismatch; this diagnostic is NOT deployed.
        lagx=np.concatenate([np.vstack((np.zeros((1,3)),r['X'][:-1])) for r in rs])
        metrics[split]={'episodes':sorted(set(r['ep'] for r in rs)),'robots':len(rs),'rmse_dx_dy_dyaw_per_tick':rmse}
        if split=='fit':
            lagcoef=[np.linalg.lstsq(np.column_stack((x[:,k],lagx[:,k])),y[:,k],rcond=None)[0] for k in range(3)]
        lagpred=np.column_stack([x[:,k]*lagcoef[k][0]+lagx[:,k]*lagcoef[k][1] for k in range(3)])
        metrics[split]['lagged_diagnostic_rmse']=np.sqrt(np.mean((lagpred-y)**2,axis=0)).tolist()
    ratios=[r['issued_length']/r['gt_length'] for r in rows if r['gt_length']>.5]
    corrected=[float(np.linalg.norm(r['X'][:,:2]*gain[:2],axis=1).sum())/r['gt_length'] for r in rows if r['gt_length']>.5]
    for r in rows:r.pop('X');r.pop('Y')
    return {'scope':'offline fit/evaluation only; runtime uses issued commands and immutable gains',
        'base_sha':'752b0cbbe25fb97d908c661e6fd00b5d6a3e44f3','fit_split':'even-index successful episodes only (19)',
        'heldout_split':'odd successes plus all three failures (21); same source cohort, not new evidence',
        'gains_dx_dy_dyaw':gain.tolist(),'dc_no_load_factor_at_035':dc,'dc_only_overestimate_ratio':1/dc,
        'raw_path_ratio':{'N':len(ratios),'median':statistics.median(ratios),'min':min(ratios),'max':max(ratios)},
        'fixed_path_ratio_same_saved_commands':{'N':len(corrected),'median':statistics.median(corrected),'min':min(corrected),'max':max(corrected)},
        'metrics':metrics,'lagged_diagnostic_coefficients':np.array(lagcoef).tolist(),'ep40_memory':case,
        'cause_confirmed':'nominal PWM*150rpm integration omits v7 input kinetic friction and torque-speed law; native motor path, not body wrench',
        'cause_not_identified':'remaining directional/load/contact/slip/transient components cannot be individually identified from base pose and command logs; no measured shaft speed or force trace',
        'interpretation':'fixed offline calibration; coordinator interpretation, user unconfirmed; default off',
        'sources':sources,'rows':rows}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=analyze(a.root);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('sources','rows')},indent=2))

if __name__=='__main__':main()
