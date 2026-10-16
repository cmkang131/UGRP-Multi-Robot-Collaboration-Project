"""Fit Nav2 alpha from own RGB interval residuals only, never GT files."""
import argparse
import json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from harness.zone_solo_cyan_consistency import covariance_basis,OPTION,BASE
from harness.zone_solo_cyan_pulse_cal import response
from harness.zone_solo_cyan_flow_fusion import rot
from harness.zone_solo_cyan_slip_detect import scale_delta,PARAMS
from harness.zone_final_pair_camera import floor_camera
from scripts.audit_s2_formal_stops import RUNS,OUTPUTS,read,sha
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent


def samples(seed):
    raw=OUTPUTS/RUNS[seed];record=read(raw/'student_record.json');bundle=read(raw/'bundle.json')
    geometry=floor_camera(bundle['look_ahead_calibration']['camera_models']['loaded'])
    cm=SimpleNamespace(origin=np.array(geometry['origin_m']),_rot=np.array(geometry['rotation']))
    out=[]
    for pulse in record['slip_detection']['rows']:
        valid=[q for q in pulse.get('intervals',[]) if q['status']=='measured']
        if not valid:continue
        # One earliest interval per pulse avoids treating shared images as iid.
        q=valid[0];p=record['pulse_motion_model']['model']['profiles'][pulse['key']]
        a=q['from_t']-pulse['t'];b=q['t']-pulse['t'];va,vb=response(p,a),response(p,b)
        transform=np.eye(3);transform[:2,:2]=rot(-va[2]);expected=transform@(vb-va)
        basis=np.array([transform@z@transform.T*(b-a)/p['times'][-1] for z in covariance_basis(p['mean_delta'])])
        observed=np.array(q['delta']);eps=PARAMS['finite_difference_rad']
        deriv=(scale_delta(q,cm,eps)-scale_delta(q,cm,-eps))/(2*eps)
        r=np.array(q['covariance'])+np.outer(deriv,deriv)*np.radians(PARAMS['pitch_scale_bound_deg'])**2/3
        out.append(dict(seed=seed,t=pulse['t'],profile=pulse['key'],interval=[q['from_t'],q['t']],
            error=(observed-expected).tolist(),R=r.tolist(),basis=basis.tolist(),
            expected=expected.tolist(),observed=observed.tolist()))
    return out


def fit(samples):
    if not samples:return dict(fit_admitted=False,reason='no_own_rgb_motion')
    basis=np.array([q['basis'] for q in samples]);r=np.array([q['R'] for q in samples]);e=np.array([q['error'] for q in samples])
    design=basis.transpose(0,2,3,1).reshape(-1,5);norm=np.linalg.norm(design,axis=0)
    rank=int(np.linalg.matrix_rank(design/np.maximum(norm,1e-300)))
    if rank!=5:return dict(fit_admitted=False,reason='unidentifiable_alpha',rank=rank)
    def objective(alpha):
        s=r+np.einsum('j,njkl->nkl',alpha,basis)
        sign,ld=np.linalg.slogdet(s)
        if not (sign>0).all():return float('inf'),np.zeros(5)
        inv=np.linalg.inv(s);v=np.einsum('nij,nj->ni',inv,e)
        value=.5*np.sum(ld+np.einsum('ni,ni->n',e,v))
        grad=.5*np.einsum('nkl,njlk->j',inv-np.einsum('ni,nj->nij',v,v),basis)
        return float(value),grad
    result=minimize(objective,np.full(5,.2),jac=True,method='L-BFGS-B',bounds=[(0,None)]*5,
        options=dict(maxiter=2000,ftol=1e-12,gtol=1e-8))
    return dict(fit_admitted=bool(result.success and np.isfinite(result.fun)),reason=str(result.message),
        rank=rank,alpha=result.x.tolist(),nll=float(result.fun),iterations=result.nit)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    data={s:samples(s) for s in RUNS};report=dict(gt_inputs=False,samples={str(s):len(v) for s,v in data.items()},folds=[],
        input_hashes={str(OUTPUTS/RUNS[s]/name):sha(OUTPUTS/RUNS[s]/name) for s in RUNS for name in ('student_record.json','bundle.json')})
    for holdout in RUNS:
        train=[s for s in RUNS if s!=holdout];sample=[q for s in train for q in data[s]];fitted=fit(sample)
        table=dict(option=OPTION,fit_seeds=train,holdout=holdout,fit_gt_inputs=False,base_sha256=sha(BASE),
            profiles=sorted({q['profile'] for q in sample}),samples=len(sample),**fitted)
        (a.output/f's{holdout}-calibration.json').write_text(json.dumps(table,indent=2)+'\n');report['folds'].append(table)
    (a.output/'samples.json').write_text(json.dumps(data,indent=2)+'\n')
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report['folds']),flush=True)


if __name__=='__main__':main()
