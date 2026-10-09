"""Offline calibration on preregistered s1050 only; s1051 never enters fit."""
import copy,hashlib,json,sys
from pathlib import Path
import numpy as np
from scipy.optimize import nnls
from scripts.analyze_s2_pulse_calibration import extract
from scripts.fit_s2_pulse_calibration import interpolate
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]


def fit(rows,base):
    model=copy.deepcopy(base);profiles=model['profiles'];used=[]
    for key,p in profiles.items():
        group=[r for r in rows if r['key']==key and r['times'][-1]>=p['times'][-1]-1e-8]
        if len(group)<3:
            p['load_refit']=dict(n=len(group),updated=False,reason='fewer than preregistered 3; old fixed mean retained');continue
        values=np.array([interpolate(r,p['times']) for r in group]);mean=values.mean(0)
        p.update(mean_curve=mean.tolist(),mean_delta=mean[-1].tolist(),n=len(group),source_seeds=[1050],transfer=None,
            residual_variance=((values[:,-1]-mean[-1])**2).mean(0).tolist(),load_refit=dict(n=len(group),updated=True))
        used.extend(group)
    alphas={};counts={}
    for loaded in (False,True):
        x=[];y=[]
        group=[r for r in used if r['loaded']==loaded]
        for row in group:
            p=profiles[row['key']];d=np.array(p['mean_delta']);e=interpolate(row,[p['times'][-1]])[0]-d
            length=np.linalg.norm(d[:2]);bearing=np.arctan2(d[1],d[0]);co,si=np.cos(bearing),np.sin(bearing)
            parallel=co*e[0]+si*e[1];strafe=si*e[0]-co*e[1];t2,r2=length**2,d[2]**2
            x.extend([[r2,t2,0,0,0],[0,0,t2,r2,0],[0,0,0,r2,t2]])
            y.extend([e[2]**2,parallel**2,strafe**2])
        if not group:raise ValueError('both load states need calibration data')
        alphas[str(int(loaded))]=nnls(np.array(x),np.array(y))[0].tolist();counts[str(int(loaded))]=len(group)
        a1,a2,a3,a4,a5=alphas[str(int(loaded))]
        for p in profiles.values():
            if p['loaded']!=loaded:continue
            d=np.array(p['mean_delta']);t2=d[:2]@d[:2];r2=d[2]**2;bearing=np.arctan2(d[1],d[0]);co,si=np.cos(bearing),np.sin(bearing)
            vpar=a3*t2+a4*r2;vperp=a5*t2+a4*r2;vr=a1*r2+a2*t2
            p['prediction_variance']=[float(max(co*co*vpar+si*si*vperp,.0005**2)),float(max(si*si*vpar+co*co*vperp,.0005**2)),float(max(vr,.001**2))]
    model.update(id='s2-v7-load-conditioned-v1',load_motion_option='load_conditioned_v1',noise_model='nav2_omni_v1',
        noise_alpha_1_to_5=alphas,fit_counts=counts,fit_seed=1050,heldout={},train_rule='s1050 only, predeclared completed pulses, >=3 per profile',
        holdout_rule='s1051 evaluation only, no constant fitting',method='profile OLS response mean; shared nonnegative Omni alpha1..5 by commanded load; existing response horizons',
        runtime_inputs='own commands, elapsed time, commanded load; fixed constants only',runtime_gt=False)
    return model


def describe(rows,model):
    groups={};allerrors={}
    for key in sorted({r['key'] for r in rows}):
        p=model['profiles'].get(key)
        if p is None:continue
        group=[r for r in rows if r['key']==key and r['times'][-1]>=p['times'][-1]-1e-8]
        if not group:continue
        delta=np.array([interpolate(r,[p['times'][-1]])[0] for r in group]);prediction=np.array(p['mean_delta']);err=delta-prediction
        tail=np.array([r['delta']-interpolate(r,[p['times'][-1]])[0] for r in group])
        groups[key]=dict(n=len(group),states=sorted({r['state'] for r in group}),prediction=prediction.tolist(),
            actual_mean=delta.mean(0).tolist(),actual_quantiles=np.quantile(delta,[.05,.5,.95],axis=0).tolist(),
            signed_error_mean=err.mean(0).tolist(),endpoint_xy_rmse_m=float(np.sqrt(np.mean(np.sum(err[:,:2]**2,axis=1)))),
            endpoint_yaw_rmse_deg=float(np.degrees(np.sqrt(np.mean(err[:,2]**2)))),
            beyond_horizon_xy_mean_m=float(np.mean(np.linalg.norm(tail[:,:2],axis=1))),beyond_horizon_yaw_mean_deg=float(np.degrees(np.mean(tail[:,2]))))
        for r,e in zip(group,err):allerrors.setdefault('loaded' if r['loaded'] else 'unloaded',[]).append(e)
    scores={}
    for k,e in allerrors.items():
        e=np.array(e);scores[k]=dict(n=len(e),xy_rmse_m=float(np.sqrt(np.mean(np.sum(e[:,:2]**2,axis=1)))),yaw_rmse_deg=float(np.degrees(np.sqrt(np.mean(e[:,2]**2)))),mean_error=e.mean(0).tolist(),sum_local_xy_error_m=float(np.linalg.norm(e[:,:2],axis=1).sum()))
    return dict(groups=groups,load_scores=scores)


def main(folder):
    folder.mkdir(parents=True,exist_ok=True);criteria=json.loads((HERE/'load-height-criteria.json').read_text())
    base=json.loads((ROOT/'configs/s2_motion_v7_pulse_cal_v1.json').read_text())
    training,source=extract(Path(criteria['train']['raw']))
    assert all(r['seed']==1050 for r in training)
    model=fit(training,base);model['source']=source;model['criteria_sha256']=hashlib.sha256((HERE/'load-height-criteria.json').read_bytes()).hexdigest()
    target=ROOT/'configs/s2_motion_load_conditioned_v1.json';assert not target.exists();target.write_text(json.dumps(model,indent=2)+'\n')
    # Calibration file closed/frozen before evaluating the held-out run.
    test,evalsource=extract(Path(criteria['evaluation']['raw']))
    for name,rows in [('train',training),('eval',test)]:
        with (folder/f'{name}-pulses.jsonl').open('x') as f:f.write(''.join(json.dumps(r)+'\n' for r in rows))
    report=dict(schema='ugrp.s2.load_motion.fit.v1',physics_runs=0,model_calls=0,train_seed=1050,eval_seed=1051,
        baseline=describe(test,base),candidate=describe(test,model),train=describe(training,model),
        old_provenance={k:{x:p[x] for x in ['n','source_seeds','transfer']} for k,p in base['profiles'].items()},
        alpha=model['noise_alpha_1_to_5'],source=source,eval_source=evalsource,
        model_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),criteria_sha256=model['criteria_sha256'])
    with (folder/'motion-summary.json').open('x') as f:f.write(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k]['load_scores'] for k in ['baseline','candidate','train']},indent=2))
if __name__=='__main__':main(Path(sys.argv[1]))
