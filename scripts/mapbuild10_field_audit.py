"""Post-seal source-VM map-extent counterexample, never an estimator input."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('ORIGINAL_VM_ONLY')
    import numpy as np
    sys.path.insert(0,str(a.source))
    from harness.mapbuild_amcl import StaticField
    from harness.mapbuild_static_registration import wall_segments
    from harness.self_odom_grid import transform
    read=lambda p:json.loads(p.read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for n,h in read(a.prediction/'prediction-seal.json').items():
        if sha(a.input/n)!=h:raise ValueError('PREDICTION_INPUT_CHANGED')
    static=read(a.input/'static-map.json');old=StaticField(static);new=StaticField(static,full_wall_extent=True)
    np.testing.assert_array_equal(old.free,new.free)
    walls=np.asarray(wall_segments(static));u,v=walls[:,0],walls[:,1]-walls[:,0]
    def nearest(p):
        q=np.clip(np.einsum('nsi,si->ns',p[:,None]-u,v)/(v*v).sum(1),0,1)
        return np.linalg.norm(p[:,None]-(u+q[...,None]*v),axis=2).min(1)
    gt=read(a.input/'eval-only.json')['frames'];scans=read(a.input/'scans.json');tr=read(a.input/'online-trajectory.json')
    if not len(gt)==len(scans)==len(tr):raise ValueError('FRAME_JOIN_REQUIRED')
    rows=[]
    for f,g,r in zip(scans,gt,tr):
        if f['t']!=g['t'] or f['t']!=r['t']:raise ValueError('TIME_JOIN_REQUIRED')
        p=np.array([np.asarray(f['camera'])+c['range_m']*np.array([np.cos(c['bearing_rad']),np.sin(c['bearing_rad'])])
            for c in f['columns'] if c['status']=='hit'])
        if not len(p):continue
        world=transform(p,g['pose']);d=nearest(world);fd=old.distances(world);nd=new.distances(world)
        x0,x1,y0,y1=static['bounds_m'];outside=(world[:,0]<x0)|(world[:,0]>x1)|(world[:,1]<y0)|(world[:,1]>y1)
        rows.append(dict(t=r['t'],frame_id=r['frame_id'],attempted=r['map_event']['attempted'],n=len(p),outside=int(outside.sum()),
            nearest_p50_p95_m=np.percentile(d,[50,95]).tolist(),legacy_field_p50_p95_m=np.percentile(fd,[50,95]).tolist(),
            full_field_p50_p95_m=np.percentile(nd,[50,95]).tolist(),
            legacy_max2_nearest_within_sigma_n=int(((fd==2)&(d<=.2)).sum()),
            legacy_max2_points=int((fd==2).sum()),full_max2_points=int((nd==2).sum())))
    updates=[r for r in rows if r['attempted']];sel=sorted(rows,key=lambda r:r['nearest_p50_p95_m'][1])
    summary=dict(evaluation_only=True,truth_to_filter=0,threshold_fitting=0,physics_steps=0,render_calls=0,
        visible_frames=len(rows),updates=len(updates),points=sum(r['n'] for r in rows),outside_points=sum(r['outside'] for r in rows),
        legacy_max2_points=sum(r['legacy_max2_points'] for r in rows),full_max2_points=sum(r['full_max2_points'] for r in rows),
        legacy_max2_nearest_within_existing_sigma_points=sum(r['legacy_max2_nearest_within_sigma_n'] for r in rows),
        all_frame_nearest_p95_min_median_max=np.percentile([r['nearest_p50_p95_m'][1] for r in rows],[0,50,100]).tolist(),
        legacy_update_field_p95_is2_count=sum(r['legacy_field_p50_p95_m'][1]==2 for r in updates),
        full_update_field_p95_is2_count=sum(r['full_field_p50_p95_m'][1]==2 for r in updates),
        free_space_byte_identical=True,low_residual=sel[:2],high_residual=sel[-2:],
        raw=str(a.input),reproduction=sys.argv,script_sha256=sha(Path(__file__)),
        warning='same frozen poses/observations, descriptive adapter comparison only; not a new trajectory or causal success proof')
    a.output.mkdir(exist_ok=False)
    for n,x in [('rows.json',rows),('summary.json',summary)]:
        p=a.output/n;p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
        if p.stat().st_size>65536:
            h=sha(p);subprocess.run(['zstd','-q',str(p)],check=True)
            if hashlib.sha256(subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])).hexdigest()!=h:raise ValueError('ARCHIVAL_CHANGED')
            p.unlink()
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','input','prediction','output'):p.add_argument('--'+n,type=Path,required=True)
    main(p.parse_args())
