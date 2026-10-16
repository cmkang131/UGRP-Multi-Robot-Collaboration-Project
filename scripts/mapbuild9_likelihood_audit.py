"""Post-seal observation-likelihood audit. Ground truth is evaluation only."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import sys


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import numpy as np
    from harness.mapbuild_amcl import StaticField
    from harness.mapbuild_amcl_vendor.algorithms import likelihood
    def read(p):return json.loads(p.read_text())
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    seal=read(a.prediction/'prediction-seal.json')
    for p,h in seal['input_sha256'].items():
        if sha(Path(p))!=h:raise ValueError('SEALED_INPUT_CHANGED')
    for p,h in seal['prediction_sha256'].items():
        if sha(a.prediction/p)!=h:raise ValueError('PREDICTION_CHANGED')
    rows=read(a.prediction/'trajectory.json');scans=read(a.input/'scans.json');gt=read(a.input/'eval-only.json')['frames']
    field=StaticField(read(a.input/'static-map.json'));result=[]
    if [r['frame_id'] for r in rows]!=[r['frame_id'] for r in gt]:raise ValueError('FRAME_JOIN_REQUIRED')
    for i,r in enumerate(rows):
        if not r['event']['attempted']:continue
        s=scans[i];origin=np.asarray(s['camera'])
        pts=np.array([origin+v['range_m']*np.array([math.cos(v['bearing_rad']),math.sin(v['bearing_rad'])])
            for v in s['columns'] if v.get('status')=='hit'])
        scores=likelihood(field,np.array([gt[i]['pose'],r['global_candidate']]),pts,a.sigma)
        e=r['event']
        result.append(dict(t=r['t'],points=len(pts),truth_likelihood=float(scores[0]),candidate_likelihood=float(scores[1]),
            truth_pose=gt[i]['pose'],candidate=r['global_candidate'],xy95=e['xy_p95_m'],yaw95=e['yaw_p95_rad'],ready=e['converged'],
            recovery=e['recovery_probability'],n=e['samples'],ess=e['pre_resample_ess']))
    output=dict(scope='sealed posthoc likelihood diagnostic only; no values returned to filter',rows=result,
        sigma=a.sigma,reproduction=sys.argv,prediction_seal_sha256=sha(a.prediction/'prediction-seal.json'),
        eval_only_sha256=sha(a.input/'eval-only.json'),truth_to_control=0)
    with a.output.open('x') as f:json.dump(output,f,indent=2);f.write('\n')
    print(json.dumps(dict(updates=len(result),ready_n=sum(r['ready'] for r in result),
        ready_likelihoods=[r for r in result if r['ready']])))
    if a.figure:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
        item=next((r for r in result if r['ready']),result[-1]);k=min(range(len(rows)),key=lambda k:abs(rows[k]['t']-item['t']))
        f,axes=plt.subplots(1,2,figsize=(10,4.5))
        local=np.asarray(scans[k]['segments']).reshape(-1,2)
        static=read(a.input/'static-map.json')
        for ax,name,pose in zip(axes,['Evaluation reference','AMCL candidate'],[item['truth_pose'],item['candidate']]):
            for o in static['obstacles']:
                if 'wall' not in o['id']:continue
                x,y=o['center_m'];dx,dy=o['half_extents_m'];ax.add_patch(Rectangle((x-dx,y-dy),2*dx,2*dy,color='.35'))
            c,s=math.cos(pose[2]),math.sin(pose[2]);p=local@np.array([[c,s],[-s,c]])+pose[:2]
            ax.scatter(p[:,0],p[:,1],s=6,c='#21918c',label='Own RGB wall contacts')
            ax.plot(*pose[:2],'ro',ms=5);ax.arrow(*pose[:2],.3*c,.3*s,width=.01,color='r')
            ax.set_title(name);ax.set_aspect('equal');ax.set_xlim(static['bounds_m'][:2]);ax.set_ylim(static['bounds_m'][2:]);ax.set_xlabel('x (m)');ax.set_ylabel('y (m)')
        f.suptitle(f"R3 t={item['t']:.1f}s: EVALUATION ONLY, no control input")
        f.tight_layout();f.savefig(a.figure,dpi=140);plt.close(f)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('input','prediction','output'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--sigma',type=float,default=.0202);p.add_argument('--figure',type=Path);main(p.parse_args())
