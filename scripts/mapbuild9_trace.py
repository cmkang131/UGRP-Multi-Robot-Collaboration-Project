"""Own-input exact replay with observational posterior snapshots; GT later."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
from types import SimpleNamespace


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    sys.path[:0]=[str(a.source),str(a.source/'scripts')]
    import numpy as np
    from harness.mapbuild_amcl_vendor import algorithms as nav2
    import mapbuild9_replay
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    def read(p):return json.loads(p.read_text())
    if a.stage=='predict':
        trace=a.output.parent/(a.output.name+'-snapshots');trace.mkdir(exist_ok=False)
        original=nav2.resample;calls=[]
        def observed(poses,weights,*args,**kwargs):
            index=len(calls)
            # Six is the inherited initial-panorama review size, a RECORDING
            # bound only; it never gates filter behavior or convergence.
            if index<6:np.savez_compressed(trace/f'{index:02d}-pre.npz',particles=poses,weights=weights)
            result=original(poses,weights,*args,**kwargs)
            if index<6:np.savez_compressed(trace/f'{index:02d}-post.npz',particles=result[0])
            calls.append(index);return result
        nav2.resample=observed
        base=Path('/home/ugrp/ugrp-sim');ops=base/'ops-reviews/mapbuild9'
        args=SimpleNamespace(input=base/'runs/mapbuild8/recording-r3',saved=base/'runs/mapbuild8/executed-r3',output=a.output,
            scan_source=None,queue=ops/'r3-likelihood_product_v1-slots-queue.json',stack_check=ops/'r3-likelihood_product_v1-slots-stack.json',
            calibration=ops/'own-noise-command-r1-r2.json',requirements=a.source/'experiments/2026-10-17-mapbuild8/requirements.json',
            command_model=a.source/'experiments/2026-10-17-mapbuild8/calibration/own-command-calibration-r2.json',seed=20261017,profile='likelihood_product_v1')
        try:mapbuild9_replay.run(args)
        finally:nav2.resample=original
        rows=read(a.output/'trajectory.json');events=[r for r in rows if r['event']['attempted']]
        equal=sha(a.output/'trajectory.json')==sha(a.original/'trajectory.json')
        if not equal:raise ValueError('TRACE_CHANGED_TRAJECTORY')
        (trace/'seal.json').write_text(json.dumps(dict(times=[r['t'] for r in events[:6]],frame_ids=[r['frame_id'] for r in events[:6]],
            files={p.name:sha(p) for p in trace.glob('*.npz')},trajectory_identical=True,trajectory_sha256=sha(a.output/'trajectory.json'),
            original=str(a.original),truth_inputs=0,reproduction=sys.argv),indent=2)+'\n')
        print(json.dumps(dict(trace=str(trace),trajectory_identical=equal)))
    else:
        trace=a.output.parent/(a.output.name+'-snapshots');seal=read(trace/'seal.json')
        for n,h in seal['files'].items():
            if sha(trace/n)!=h:raise ValueError('TRACE_CHANGED')
        gt=read(Path('/home/ugrp/ugrp-sim/runs/mapbuild8/recording-r3/eval-only.json'))['frames']
        req=read(a.source/'experiments/2026-10-17-mapbuild8/requirements.json')['handoff'];result=[]
        for j,(t,frame_id) in enumerate(zip(seal['times'],seal['frame_ids'])):
            truth=np.asarray(next(f['pose'] for f in gt if f['frame_id']==frame_id));row=dict(t=t,frame_id=frame_id)
            for phase in ('pre','post'):
                arrays=np.load(trace/f'{j:02d}-{phase}.npz');p=arrays['particles'];w=arrays['weights'] if phase=='pre' else np.ones(len(p))/len(p)
                d=p-truth;xy=np.linalg.norm(d[:,:2],axis=1);yaw=abs(np.arctan2(np.sin(d[:,2]),np.cos(d[:,2])))
                coupled=yaw+np.arctan2(xy,req['nominal_target_range_m']-xy)
                inside=(xy<=req['position_error_m'])&(coupled<=req['yaw_error_rad'])
                row[phase]=dict(particles=len(p),within_handoff_n=int(inside.sum()),uniform_count_fraction=float(inside.mean()),posterior_mass=float(w[inside].sum()),
                    nearest_xy_m=float(xy.min()),best_joint_budget_ratio=float(np.min(np.maximum(xy/req['position_error_m'],coupled/req['yaw_error_rad']))))
            result.append(row)
        report=dict(scope='post-seal first six updates; truth never supplied to filter; handoff region from frozen requirement only',rows=result,trajectory_identical=seal['trajectory_identical'],reproduction=sys.argv)
        (trace/'evaluation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['predict','score'],required=True)
    for k in ('source','output','original'):p.add_argument('--'+k,type=Path,required=True)
    main(p.parse_args())
