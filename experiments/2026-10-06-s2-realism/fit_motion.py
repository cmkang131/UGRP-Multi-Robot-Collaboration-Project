"""Offline least squares on three exploratory pulses; exact 50 ms PF recursion.

Same first-order command/stop-lag method as scripts/fit_loaded_gain_calibration.py.
No diagnostic state is read by the mission controller. This is training fit,
not held-out validation, and loaded/reverse transfer is not measured here.
"""
import hashlib,json,math,sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares


def predict(gain,tau,tau_stop,command,times):
    pos=np.zeros(3);velocity=np.zeros(3);out=[pos.copy()]
    u=np.array([command[k] for k in ('forward','left','turn')])
    for a,b in zip(times,times[1:]):
        active=a < command['duration_s']-1e-8
        dt=b-a;target=gain@u if active else np.zeros(3)
        alpha=1-np.exp(-dt/(tau if active else tau_stop))
        velocity+=alpha*(target-velocity)
        c,s=np.cos(pos[2]),np.sin(pos[2])
        pos+=dt*np.array([c*velocity[0]-s*velocity[1],s*velocity[0]+c*velocity[1],velocity[2]])
        out.append(pos.copy())
    return np.asarray(out)


def main(raw,output):
    raw=Path(raw);output=Path(output)
    if output.exists():raise FileExistsError(output)
    allrows=json.loads((raw/'result.json').read_text());assert allrows['status']=='COMPLETED_DIAGNOSTIC'
    cases=[];g0=np.zeros((3,3));references=[]
    for summary in allrows['runs']:
        folder=raw/f"s{summary['seed']}-{summary['case']}"
        path=folder/'trajectory.jsonl'
        trace=[json.loads(x) for x in path.read_text().splitlines()][::5]
        times=np.array([r['t'] for r in trace]);times-=times[0]
        assert np.allclose(np.diff(times),.05,atol=1e-7)
        yaw=np.unwrap([r['yaw'] for r in trace]);xy=np.array([r['xyz'][:2] for r in trace]);xy-=xy[0]
        c,s=np.cos(yaw[0]),np.sin(yaw[0]);xy=xy@np.array([[c,-s],[s,c]])
        obs=np.column_stack((xy,yaw-yaw[0]));command=summary['command']
        idx=('forward','left','turn').index(summary['case'])
        g0[:,idx]=obs[-1]/(command[summary['case']]*command['duration_s'])
        cases.append(dict(summary=summary,times=times,observed=obs,command=command))
        references.extend(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (path,folder/'result.json'))
    def residual(p):
        gain=p[:9].reshape(3,3);tau=p[9:12];stop=p[12]
        return np.concatenate([((predict(gain,tau,stop,x['command'],x['times'])-x['observed'])*[1,1,.15]).ravel() for x in cases])
    lo=np.array([-10.]*9+[.005]*4);hi=np.array([10.]*9+[2.]*4)
    fits=[least_squares(residual,np.r_[g0.ravel(),[t]*3,t],bounds=(lo,hi),x_scale='jac',max_nfev=250) for t in (.03,.1,.3)]
    fit=min(fits,key=lambda r:float(r.cost));g=fit.x[:9].reshape(3,3);tau=fit.x[9:12];stop=fit.x[12]
    assert fit.success and abs(np.linalg.det(g))>1e-8
    rows=[]
    for x in cases:
        predicted=predict(g,tau,stop,x['command'],x['times']);err=predicted-x['observed']
        rows.append(dict(seed=x['summary']['seed'],case=x['summary']['case'],observed=x['observed'][-1].tolist(),predicted=predicted[-1].tolist(),
          endpoint_error=err[-1].tolist(),max_xy_error_m=float(np.linalg.norm(err[:,:2],axis=1).max()),max_yaw_error_rad=float(abs(err[:,2]).max())))
    result=dict(id='s2-v7-real-primitive-diag-v1',option='v7_diag_v1',gain=g.tolist(),tau_s=float(np.mean(tau)),
        tau_axis_s=tau.tolist(),tau_stop_s=float(stop),fit_source_sha=allrows['source_sha'],diagnostic_bundle=allrows['execution_bundle_id'],
        source_records=references,training_replay=rows,converged=bool(fit.success),weighted_rms=float(np.sqrt(np.mean(residual(fit.x)**2))),
        near_bound=[i for i,v in enumerate(fit.x) if min(v-lo[i],hi[i]-v)<.001],condition_number=float(np.linalg.cond(g)),
        qualification='EXPLORATORY FIT ONLY; one positive pulse per axis; no heldout, loaded, negative, or longer-pulse qualification',
        loaded_use='same fixed coefficients as an explicit unqualified 30g proxy; no live load or GT adaptation',
        method='bounded batch least-squares of 3x3 gain + per-output spin-up lag + stop lag; owncam 50ms recursion')
    output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['gain','tau_axis_s','tau_stop_s','weighted_rms','near_bound','training_replay']}))


if __name__=='__main__':main(*sys.argv[1:])
