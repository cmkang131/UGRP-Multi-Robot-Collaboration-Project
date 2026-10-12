"""Evaluate sealed frontend predictions only; no import into any controller."""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
from harness.pf_observation_consistency import OPTIONS
RAW=Path('/Users/changmin/projects/ugrp/outputs')
S3={'v149':RAW/'s3-sweep-b73ce193-s14201-v149','v150':RAW/'s3-odometry-4c9eb3aa-s14201-v150'}

def read(p):return json.loads(p.read_text())
def rows(p):return [json.loads(s) for s in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def statistics(error,sigma,cov=None,delta=None):
    good=np.isfinite(error)&np.isfinite(sigma)
    if not good.all():raise ValueError('nonfinite evaluated prediction')
    out=dict(frames=len(error),invalid_frames=int(sum(~good)),xy_rmse_m=float(np.sqrt(np.mean(error**2))),
        final_error_m=float(error[-1]),final_sigma_m=float(sigma[-1]),sigma_rms_m=float(np.sqrt(np.mean(sigma**2))),
        over_3sigma=int(np.sum(error>3*sigma)),over_3sigma_fraction=float(np.mean(error>3*sigma)))
    if cov is not None:
        nees=np.einsum('ni,nij,nj->n',delta,np.linalg.inv(cov),delta)
        out.update(xy_nees_mean=float(np.mean(nees)),xy_nees_gt_11_829_fraction=float(np.mean(nees>11.829)))
    return out

def s3(path,raw,rid):
    receipt=read(path/'result.json');assert receipt['error'] is None
    poses=read(path/'state.json')[rid]['poses'];poses=[p for p in poses if p['t_est']>=13.34-1e-8]
    gt=rows(raw/f'eval_only/{rid}/trajectory.jsonl');ts=[r['t'] for r in gt]
    at=np.array([p['t_est'] for p in poses]);xy=np.array([r['robot_xyz_m'][:2] for r in gt])
    actual=np.column_stack([np.interp(at,ts,xy[:,i]) for i in range(2)])
    est=np.array([[p['x'],p['y']] for p in poses]);error=np.linalg.norm(est-actual,axis=1)
    sigma=np.array([p['std_xy_m'] for p in poses]);out=statistics(error,sigma)
    yaw=np.unwrap([r['robot_yaw_rad'] for r in gt]);ye=abs((np.array([p['yaw'] for p in poses])-np.interp(at,ts,yaw)+np.pi)%(2*np.pi)-np.pi)
    out.update(prediction_sha256=sha(path/'state.json'),truth_sha256=sha(raw/f'eval_only/{rid}/trajectory.jsonl'),
        false_certificates=sum(bool(p['convergence_certificate']['qualified'] and (e>.25 or y>np.deg2rad(15))) for p,e,y in zip(poses,error,ye)),
        sigma_definition='sqrt(trace(XY covariance)); original S3 definition')
    return out

def own(path,raw):
    receipt=read(path/'result.json');assert receipt['failure'] is None and receipt['frames']==receipt['expected_frames']
    poses=rows(path/'frontend-covariances.jsonl');gt=rows(raw/'eval_only/trajectory.jsonl');by_t={round(r['t'],6):r for r in gt}
    origin=np.array(gt[0]['robot_xyz_m'][:2]);yaw=gt[0]['robot_yaw_rad'];co,si=math.cos(yaw),math.sin(yaw);rot=np.array([[co,-si],[si,co]])
    actual=np.array([rot.T@(np.array(by_t[round(p['t'],6)]['robot_xyz_m'][:2])-origin) for p in poses])
    est=np.array([p['pose'][:2] for p in poses]);cov=np.array([p['covariance'] for p in poses])[:,:2,:2]
    delta=est-actual;error=np.linalg.norm(delta,axis=1);sigma=np.sqrt(np.linalg.eigvalsh(cov)[:,-1]);out=statistics(error,sigma,cov,delta)
    out.update(prediction_sha256=sha(path/'frontend-covariances.jsonl'),truth_sha256=sha(raw/'eval_only/trajectory.jsonl'),
        sigma_definition='sqrt(max eigenvalue(XY covariance)); original own-map definition',gauge='initial truth only; evaluation transform, no trajectory alignment')
    return out

def evaluate(base):
    table={}
    for option in OPTIONS:
        table[option]={}
        for case,raw in S3.items():
            for rid in ('r1','r2','r3'):table[option][case+'/'+rid]=s3(base/(case+'-'+option),raw,rid)
        for seed in (55001,55002):table[option][str(seed)+'/r3']=own(base/(str(seed)+'-'+option),RAW/f'goal-route-motion-audit-v1/seed{seed}')
    baseline=table['off'];eligible=[];checks={}
    for option in OPTIONS[1:]:
        current=table[option];failures=[]
        for key,v in current.items():
            b=baseline[key]
            for metric in ('xy_rmse_m','final_error_m'):
                if v[metric]>b[metric]+1e-9:failures.append(dict(trajectory=key,metric=metric,before=b[metric],after=v[metric]))
            if v['frames']!=b['frames'] or v['invalid_frames']:failures.append(dict(trajectory=key,metric='frame_coverage'))
            if v['over_3sigma_fraction']>b['over_3sigma_fraction']:failures.append(dict(trajectory=key,metric='over_3sigma_fraction',before=b['over_3sigma_fraction'],after=v['over_3sigma_fraction']))
        pooled=lambda d:sum(r['over_3sigma'] for r in d.values())/sum(r['frames'] for r in d.values())
        if pooled(current)>=pooled(baseline):failures.append(dict(metric='pooled_strict_improvement',before=pooled(baseline),after=pooled(current)))
        checks[option]=dict(eligible=not failures,failures=failures,pooled_over_3sigma=pooled(current))
        if not failures:eligible.append(option)
    selected=min(eligible,key=lambda op:(checks[op]['pooled_over_3sigma'],sum(r['xy_rmse_m'] for r in table[op].values()),OPTIONS.index(op))) if eligible else 'off'
    return dict(gt_evaluation_only=True,table=table,selection=checks,smoke_option=selected,preregistered_rule_unchanged=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();value=evaluate(a.input)
    with a.output.open('x') as f:f.write(json.dumps(value,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(smoke_option=value['smoke_option'],selection=value['selection']),indent=2))
