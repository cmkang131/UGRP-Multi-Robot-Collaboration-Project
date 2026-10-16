"""gcp5-only, truth-free competing-mode audit BEFORE new correction design.

Modes use the inherited CSM .15m SE2 separation and .50 cost-gap definition.
Conditional +/-1 sigma windows are descriptive, never a fabricated world prior.
No eval-only/spawn data is opened. Full score arrays stay on gcp5.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root),str(a.vision)]
    import harness
    harness.__path__.append(str(a.vision/'harness'))
    import numpy as np
    from scipy.spatial import cKDTree
    from harness.mapbuild_static_registration import StaticRegistration,OPTION
    from harness.self_odom_grid import transform
    from harness.e2e_rgb_vo import compose
    def read(p):return json.loads(p.read_text())
    def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
    a.output.mkdir(parents=True,exist_ok=False)
    cases=[]
    for label in ('r2','r3'):
        recording=a.runs/'mapbuild6'/('recording-'+label);replay=a.runs/'mapbuild7'/('offline-v2-'+label)
        rows=read(replay/'trajectory.json');scans=read(replay/'scans.json');events=read(replay/'events.json')
        seg=[];origins=[];P=np.zeros((3,3));pose=np.zeros(3)
        for r,s,e in zip(rows,scans,events):
            delta=np.asarray(r['motion_delta']);c,ss=np.cos(pose[2]),np.sin(pose[2]);R=np.array([[c,-ss,0],[ss,c,0],[0,0,1]])
            d=R@delta;F=np.eye(3);F[:2,2]=[-d[1],d[0]];P=F@P@F.T+R@np.asarray(r['motion_covariance'])@R.T
            pose=compose(pose,delta)
            if e.get('inserted'):
                seg.extend([transform(x,pose).tolist() for x in s['segments']]);origins.extend([transform([s['camera']],pose)[0].tolist() for _ in s['segments']])
        cases.append((label,recording,seg,origins,P))
    recording=a.runs/'mapbuild7/recording-r2';ledger=read(recording/'wall-ledger.json');rows=read(recording/'online-trajectory.json')
    P=np.zeros((3,3));pose=np.zeros(3)
    for r in rows:
        delta=np.asarray(r['motion_delta']);c,s=np.cos(pose[2]),np.sin(pose[2]);R=np.array([[c,-s,0],[s,c,0],[0,0,1]])
        d=R@delta;F=np.eye(3);F[:2,2]=[-d[1],d[0]];P=F@P@F.T+R@np.asarray(r['motion_covariance'])@R.T;pose=compose(pose,delta)
    cases.append(('recording-r2-postpickup',recording,ledger['segments'],ledger['camera_origins'],P))
    results=[]
    for label,recording,segments,origins,P in cases:
        reg=StaticRegistration(read(recording/'static-map.json'),option=OPTION);detail={}
        def inspect(poses,cost,points,sigma):
            np.savez_compressed(a.output/(label+'-costs.npz'),poses=poses,cost=cost,points=points,sigma=sigma)
            best=int(cost.argmin());o=reg.options
            ids=np.flatnonzero(cost<cost[best]+o.mode_gap);order=ids[np.argsort(cost[ids],kind='stable')]
            # Exact inherited yaw-to-2m metric, circular angular wrap.
            xyz=poses[ids]*[1,1,2];period=4*np.pi
            cloud=np.concatenate([xyz,xyz+[0,0,period],xyz-[0,0,period]])
            tree=cKDTree(cloud);suppressed=set();modes=[];index={int(k):i for i,k in enumerate(ids)}
            for k in order:
                i=index[int(k)]
                if i in suppressed:continue
                modes.append(int(k));suppressed.update(j%len(ids) for j in tree.query_ball_point(xyz[i],o.mode_distance_m-1e-9))
            mp=poses[modes];mc=cost[modes];conditional=[]
            for center in mp:
                c,s=np.cos(center[2]),np.sin(center[2]);R=np.array([[c,-s,0],[s,c,0],[0,0,1]])
                sig=np.sqrt(np.maximum(0,np.diag(R@P@R.T)))
                d=mp-center;d[:,2]=np.arctan2(np.sin(d[:,2]),np.cos(d[:,2]))
                conditional.append(int(np.all(np.abs(d)<=sig+1e-12,axis=1).sum()))
            diff=poses-poses[best];diff[:,2]=np.arctan2(np.sin(diff[:,2]),np.cos(diff[:,2]))
            far=np.linalg.norm(diff*[1,1,2],axis=1)>=o.mode_distance_m-1e-9
            detail.update(competing_modes_n=len(modes),candidate_band_n=len(ids),second_gap=float(cost[far].min()-cost[best]),
                competing_modes=[dict(pose=poses[k].tolist(),cost_gap=float(cost[k]-cost[best]),conditional_one_sigma_modes=n) for k,n in zip(modes,conditional)],
                conditional_single_windows_n=sum(n==1 for n in conditional),conditional_multiple_windows_n=sum(n>1 for n in conditional),
                propagated_own_covariance=P.tolist(),one_sigma_own=np.sqrt(np.diag(P)).tolist(),
                valid_static_prior=False,actual_prior_window_unique=None,
                prior_status='unregistered: no accepted static-from-own anchor in these runs; conditional mode-centred windows are NOT a motion prior',
                definition='CSM .15m separated candidates within .50 sensor cost of optimum; may describe a continuous ridge, not independent Gaussian peaks')
        result=reg.register(segments,camera_origins=origins,diagnostic_callback=inspect)
        row=dict(case=label,raw=str(recording),registration=result,**detail);results.append(row);dump(a.output/(label+'.json'),row)
        print(json.dumps(dict(case=label,reason=result['reason'],**{k:v for k,v in detail.items() if k!='competing_modes'})),flush=True)
    dump(a.output/'summary.json',dict(cases=results,truth_inputs=0,scale=1,reproduction=sys.argv,
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),root/'harness/mapbuild_static_registration.py']},
        conclusion='A prior window cannot initialize unknown global gauge. Own-submap matching can use own-gauge motion prior; static matching needs a separately accepted visual anchor.'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('runs','vision','output'):p.add_argument('--'+k,type=Path,required=True)
    main(p.parse_args())
