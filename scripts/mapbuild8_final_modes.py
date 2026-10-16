"""Reconstruct executed global input exactly; inspect modes with no truth reads."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import numpy as np
    from scipy.spatial import cKDTree
    from harness.self_odom_grid import transform
    from harness.e2e_rgb_vo import compose
    from harness.mapbuild_static_registration import StaticRegistration,OPTION
    def read(p):return json.loads(p.read_text())
    def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
    a.output.mkdir(parents=True,exist_ok=False)
    rows=read(a.input/'online-trajectory.json');scans=read(a.input/'scans.json');events=read(a.input/'events.json')
    reg=StaticRegistration(read(a.input/'static-map.json'),option=OPTION);seg=[];origins=[];body=[];cov=[]
    for r,s in zip(rows,scans):
        e=r['map_event']
        if not e['attempted']:continue
        pose=np.asarray(r['corrected_pose']);local=np.asarray(s['segments']).reshape(-1,2,2)
        seg.extend(transform(local.reshape(-1,2),pose).reshape(-1,2,2).tolist());origin=transform([s['camera']],pose)[0].tolist()
        origins.extend([origin for _ in local]);body.extend([pose[:2].tolist() for _ in local]);cov.extend([e['covariance'] for _ in local])
    P=np.asarray(rows[-1]['map_event'].get('covariance',rows[-1]['map_event']['prior_covariance']));current=np.asarray(rows[-1]['corrected_pose']);detail={}
    def inspect(poses,cost,points,sigma):
        np.savez_compressed(a.output/'global-costs.npz',poses=poses,cost=cost,points=points,sigma=sigma)
        o=reg.options;best=cost.argmin();ids=np.flatnonzero(cost<cost[best]+o.mode_gap);order=ids[np.argsort(cost[ids],kind='stable')]
        xyz=poses[ids]*[1,1,2];period=4*np.pi;tree=cKDTree(np.concatenate([xyz,xyz+[0,0,period],xyz-[0,0,period]]))
        suppressed=set();modes=[];index={int(k):i for i,k in enumerate(ids)}
        for k in order:
            i=index[int(k)]
            if i in suppressed:continue
            modes.append(int(k));suppressed.update(j%len(ids) for j in tree.query_ball_point(xyz[i],o.mode_distance_m-1e-9))
        body_modes=np.array([compose(poses[k],current) for k in modes]);records=[]
        for i,k in enumerate(modes):
            c,s=np.cos(poses[k,2]),np.sin(poses[k,2]);R=np.array([[c,-s,0],[s,c,0],[0,0,1]])
            sigma=np.sqrt(np.diag(R@P@R.T));d=body_modes-body_modes[i];d[:,2]=np.arctan2(np.sin(d[:,2]),np.cos(d[:,2]));inside=np.all(np.abs(d)<=sigma+1e-12,axis=1)
            records.append(dict(static_from_own_candidate=poses[k].tolist(),current_body_candidate=body_modes[i].tolist(),cost_gap=float(cost[k]-cost[best]),
                conditional_one_sigma_modes_n=int(inside.sum()),one_sigma_current_body=sigma.tolist()))
        detail.update(competing_modes_n=len(modes),candidate_band_n=len(ids),modes=records,
            conditional_single_windows_n=sum(r['conditional_one_sigma_modes_n']==1 for r in records),
            conditional_multiple_windows_n=sum(r['conditional_one_sigma_modes_n']>1 for r in records),valid_static_prior=False,
            actual_prior_window_unique=None,definition='inherited .15m-separated SE2 candidates inside .50 sensor-cost band; conditional body-pose +/-1sigma, NOT an invented global prior')
    result=reg.register(seg,camera_origins=origins,pose_covariances=cov,body_origins=body,diagnostic_callback=inspect)
    recorded=next(e for e in reversed(events) if e['event']=='rescan')
    equal={k:recorded[k]==result[k] for k in ('points','best_candidate','residual_m','second_sensor_gap','observable_rank','sensor_sigma_min_max_m')}
    summary=dict(raw=str(a.input),registration=result,exact_executed_comparison=equal,**detail,truth_inputs=0,
        source_sha256={str(a.input/n):hashlib.sha256((a.input/n).read_bytes()).hexdigest() for n in ('online-trajectory.json','scans.json','events.json','static-map.json')},reproduction=sys.argv)
    dump(a.output/'summary.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('input','output'):p.add_argument('--'+k,type=Path,required=True)
    main(p.parse_args())
