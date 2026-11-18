"""Fit common floor normal across recorded own-floor homographies; no motors.

Malis/Vargas plane-induced H has two geometrical solutions. Select a common
normal across views, rather than forcing the unverified structural mount.
This is a DEV fit; the next independent capture must test the frozen profile.
"""
import argparse
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from green_wall_mapper import K,D,POSE


def fit(record):
    candidates=[]
    for v in record['views'][1:]:
        h=np.linalg.inv(v['to_anchor'])
        _,rs,ts,ns=cv2.decomposeHomographyMat(h,K)
        for r,t,n in zip(rs,ts,ns):
            n=n.ravel()
            angle=float(np.degrees(np.arccos(np.clip((np.trace(r)-1)/2,-1,1))))
            if n[1]>0 and angle<10 and np.linalg.norm(t)>.01:
                candidates.append((v['view'],n))
    if not candidates:raise ValueError('no translation-supported floor normals')
    best=[];hypotheses=[]
    # 10deg is an explicit DEV normal-cluster tolerance, not a calibrated CI.
    for _,seed in candidates:
        selected={}
        for view,n in candidates:
            score=float(seed@n)
            if score>np.cos(np.radians(10)) and (view not in selected or score>selected[view][0]):
                selected[view]=(score,n)
        chosen=[v[1] for v in selected.values()];hypotheses.append((seed,chosen))
        if len(chosen)>len(best):best=chosen
    if len(best)<3:raise ValueError('fewer than3 common-normal views')
    n=np.median(best,axis=0);n/=np.linalg.norm(n)
    for seed,chosen in hypotheses:
        if len(chosen)==len(best) and seed@n<np.cos(np.radians(20)):
            raise ValueError('equally supported distinct floor normals: collect another direction')
    errors=np.degrees(np.arccos(np.clip(np.array(best)@n,-1,1)))
    return dict(pose={str(k):v for k,v in POSE.items()},K=K.tolist(),D=D.tolist(),
                floor_normal_camera=n.tolist(),views_supporting=len(best),
                angular_residual_deg=errors.tolist(),source='own RGB floor homographies',
                metric_scale_verified=False,independent_validation='pending')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('record',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=a.record.read_bytes();result=fit(json.loads(raw));result['source_record']=str(a.record)
    result['source_record_sha256']=hashlib.sha256(raw).hexdigest()
    if a.output.exists():raise FileExistsError('do not overwrite a frozen profile')
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
