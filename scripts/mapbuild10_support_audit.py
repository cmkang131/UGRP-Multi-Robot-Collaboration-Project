"""Post-seal counterfactual weights on mapbuild9's unchanged saved particles.

This never runs a filter or chooses a pose; truth labels the frozen handoff
region only. Counterfactuals are NOT new estimator trajectories.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import sys


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):
        raise ValueError('SOURCE_VM_ONLY')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import numpy as np
    from harness.mapbuild_amcl import StaticField
    from harness.mapbuild_amcl_vendor import algorithms as nav2
    read=lambda p:json.loads(p.read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    seal=read(a.trace/'seal.json')
    for name,h in seal['files'].items():
        if sha(a.trace/name)!=h:raise ValueError('SNAPSHOT_CHANGED')
    truth=read(a.input/'eval-only.json')['frames'];scans=read(a.input/'scans.json')
    field=StaticField(read(a.input/'static-map.json'));req=read(a.requirements)['handoff']
    rows=[]
    for j,frame in enumerate(seal['frame_ids']):
        gt=np.asarray(truth[frame]['pose']);scan=scans[frame]
        camera=np.asarray(scan['camera'])
        points=np.array([camera+c['range_m']*np.array([math.cos(c['bearing_rad']),math.sin(c['bearing_rad'])])
                         if c['status']=='hit' else [np.nan,np.nan] for c in scan['columns']])
        arrays=np.load(a.trace/f'{j:02d}-pre.npz');p=arrays['particles'];old=arrays['weights']
        d=p-gt;xy=np.linalg.norm(d[:,:2],axis=1);yaw=abs(nav2.wrap(d[:,2]))
        coupled=yaw+np.arctan2(xy,req['nominal_target_range_m']-xy)
        inside=(xy<=req['position_error_m'])&(coupled<=req['yaw_error_rad'])
        original=nav2.likelihood_product(field,p,points,.0202)
        # Undo ONLY this frame's known weighting, preserving previous posterior.
        before=old/original;before/=before.sum()
        row=dict(t=seal['times'][j],frame_id=frame,particles=len(p),within_handoff_n=int(inside.sum()),
                 prior_support_mass=float(before[inside].sum()),models={})
        for name,fn,sigma in [('product_0202',nav2.likelihood_product,.0202),
                              ('product_200',nav2.likelihood_product,.2),
                              ('additive_0202',nav2.likelihood,.0202),
                              ('nav2_default_additive_200',nav2.likelihood,.2)]:
            values=fn(field,p,points,sigma)
            w=before*values;w/=w.sum()
            logs=np.log(values[inside])
            row['models'][name]=dict(support_mass=float(w[inside].sum()),
                expected_surviving_particles=float(len(p)*w[inside].sum()),
                log_likelihood_at_exact_evaluation_pose=float(np.log(fn(field,gt[None],points,sigma)[0])),
                support_log_likelihood_range=[float(logs.min()),float(np.median(logs)),float(logs.max())] if len(logs) else None,
                best_all_log_likelihood=float(np.log(values.max())),ess=float(1/np.sum(w*w)))
        if inside.any():
            c,s=np.cos(p[inside,2,None]),np.sin(p[inside,2,None])
            q=points[np.isfinite(points).all(1)]
            x=p[inside,0,None]+c*q[None,:,0]-s*q[None,:,1]
            y=p[inside,1,None]+s*q[None,:,0]+c*q[None,:,1]
            residual=field.distances(np.stack((x,y),axis=-1))
            row['support_point_field_distance_p05_p50_p95_m']=np.percentile(residual,[5,50,95]).tolist()
            row['support_pose_xy_p05_p50_p95_m']=np.percentile(xy[inside],[5,50,95]).tolist()
            row['support_pose_yaw_abs_p05_p50_p95_deg']=np.degrees(np.percentile(yaw[inside],[5,50,95])).tolist()
        rows.append(row)
    output=dict(scope=__doc__,rows=rows,threshold_fitting=0,truth_to_estimator=0,
        note='Later counterfactuals cannot restore support already lost by the original trajectory.',
        sources={str(p):sha(p) for p in [a.trace/'seal.json',a.input/'eval-only.json',a.input/'scans.json',a.requirements,Path(__file__)]},reproduction=sys.argv)
    with a.output.open('x') as f:json.dump(output,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(rows[0]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('input','trace','requirements','output'):p.add_argument('--'+name,type=Path,required=True)
    main(p.parse_args())
