"""Separate saved-truth evaluator; all estimator outputs are sealed first."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys


def main(a):
    if not platform.node().startswith(('ugrp-act-l4-gcp5','ugrp-act-l4-gcp3')):raise ValueError('SOURCE_VM_ONLY')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import numpy as np
    from harness.e2e_rgb_vo import between,compose
    def read(p):return json.loads(p.read_text())
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
    seal=read(a.prediction/'prediction-seal.json')
    for p,h in seal['input_sha256'].items():
        if sha(Path(p))!=h:raise ValueError('INPUT_SEAL_CHANGED:'+p)
    for p,h in seal['prediction_sha256'].items():
        if sha(a.prediction/p)!=h:raise ValueError('PREDICTION_SEAL_CHANGED:'+p)
    a.output.mkdir(parents=True,exist_ok=False)
    rows=read(a.prediction/'trajectory.json');truth=read(a.input/'eval-only.json')['frames'];req=read(a.requirements)['handoff']
    if [r['frame_id'] for r in rows]!=[r['frame_id'] for r in truth]:raise ValueError('FRAME_JOIN_REQUIRED')
    world=np.array([r['pose'] for r in truth]);times=np.array([r['t'] for r in rows]);off=np.array([compose(world[0],r['off_pose']) for r in rows])
    candidate=np.array([r['global_candidate'] if r['global_candidate'] is not None else [np.nan]*3 for r in rows])
    ready=np.array([r['event']['converged'] for r in rows]);attempted=np.array([r['event']['attempted'] for r in rows]);has=np.isfinite(candidate).all(1)
    def errors(pred):
        d=pred-world;xy=np.linalg.norm(d[:,:2],axis=1);yaw=abs(np.arctan2(np.sin(d[:,2]),np.cos(d[:,2])))
        coupled=yaw+np.arctan2(xy,req['nominal_target_range_m']-xy)
        return xy,yaw,coupled
    oe=errors(off);ae=errors(candidate)
    def metrics(err,mask):
        ix=np.flatnonzero(mask)
        if not len(ix):return dict(frames=0,status='not_recorded')
        xy,yaw,coupled=err;k=ix[-1]
        return dict(frames=len(ix),xy_rmse_m=float(np.sqrt(np.mean(xy[ix]**2))),xy_p95_m=float(np.percentile(xy[ix],95)),
            yaw_p95_deg=float(np.degrees(np.percentile(yaw[ix],95))),final_xy_m=float(xy[k]),final_yaw_deg=float(np.degrees(yaw[k])),
            handoff_pass_n=int(np.sum((xy[ix]<=req['position_error_m'])&(coupled[ix]<=req['yaw_error_rad']))))
    first=np.flatnonzero(ready);since=(times>=times[first[0]]) if len(first) else np.zeros(len(rows),bool)
    within=(ae[0]<=req['position_error_m'])&(ae[2]<=req['yaw_error_rad'])
    wrong=ready&~within
    path=np.r_[0,np.cumsum(np.linalg.norm(np.diff(world[:,:2],axis=0),axis=1))]
    ownpath=np.r_[0,np.cumsum([np.linalg.norm(between(rows[k-1]['off_pose'],rows[k]['off_pose'])[:2]) for k in range(1,len(rows))])]
    phases=[]
    for start in np.arange(0,times[-1]+1e-6,10.):
        mask=(times>=start)&(times<start+10)
        phases.append(dict(start_sim_s=float(start),end_sim_s=float(min(start+10,times[-1])),off=metrics(oe,mask),amcl_candidate_absolute=metrics(ae,mask&has),ready_n=int(ready[mask].sum()),wrong_ready_n=int(wrong[mask].sum())))
    # Readiness is an estimator decision; truth evaluates wrong episodes only.
    episodes=[]
    for i in np.flatnonzero(ready):
        episodes.append(dict(t=rows[i]['t'],frame_id=rows[i]['frame_id'],xy_m=float(ae[0][i]),yaw_deg=float(np.degrees(ae[1][i])),
            direction_coupled_deg=float(np.degrees(ae[2][i])),wrong_convergence=bool(wrong[i])))
    after_off=metrics(oe,since);after_amcl=metrics(ae,since&has)
    passed=bool(len(first) and not wrong.any() and after_amcl['xy_rmse_m']<after_off['xy_rmse_m'] and np.all(within[since&has]))
    result=dict(status='OFFLINE_PASS' if passed else 'NOT_READY',raw=str(a.input),prediction=str(a.prediction),
        physical_success=False,new_physical_runs=0,frames=len(rows),reference='OFF start-only SE2/scale1; AMCL true static frame, no alignment or scale fit',
        off_all=metrics(oe,np.ones(len(rows),bool)),amcl_candidate_absolute_all=metrics(ae,has),
        since_first_convergence=dict(off=after_off,amcl=after_amcl),ready_updates=int(ready.sum()),attempted_updates=int(attempted.sum()),
        wrong_convergence_updates=int(wrong.sum()),wrong_convergence_episodes=sum(e['wrong_convergence'] and (j==0 or not episodes[j-1]['wrong_convergence']) for j,e in enumerate(episodes)),
        convergence_sim_s=float(times[first[0]]) if len(first) else None,
        convergence_own_estimated_path_m=float(ownpath[first[0]]) if len(first) else None,
        convergence_evaluation_path_m=float(path[first[0]]) if len(first) else None,
        total_evaluation_path_m=float(path[-1]),phases=phases,convergence_events=episodes,
        commanded_closed_frames=sum(int(r['servo']['1'])<=1600 for r in rows),
        carried_transport_verified=False,requirements_sha256=sha(a.requirements),prediction_seal_sha256=sha(a.prediction/'prediction-seal.json'),
        gt_to_estimator=0,spawn_inputs=0,scale_fitting=0,reproduction=sys.argv)
    dump(a.output/'summary.json',result)
    dump(a.output/'frame-errors.json',[dict(t=r['t'],off_xy_m=float(oe[0][i]),amcl_xy_m=float(ae[0][i]) if has[i] else None,ready=bool(ready[i])) for i,r in enumerate(rows)])
    print(json.dumps({k:v for k,v in result.items() if k not in ('phases','convergence_events')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('input','prediction','output','requirements'):p.add_argument('--'+k,type=Path,required=True)
    main(p.parse_args())
