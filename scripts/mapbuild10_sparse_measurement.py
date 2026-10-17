"""gcp3 post-seal measurement audit of the original 418 views; no new filter.

This keeps sparse-view diagnostics separate from the R1-R3 cohort. A missing
coarse-start region is recorded as missing, never reconstructed from truth.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys


def raw(p):
    return p.read_bytes() if p.exists() else subprocess.check_output(['zstd', '-qdc', str(p)+'.zst'])


def read(p):
    return json.loads(raw(p))


def sha(p):
    return hashlib.sha256(raw(p)).hexdigest()


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp3'):
        raise ValueError('GCP3_ONLY')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import numpy as np
    from harness.mapbuild_amcl import StaticField
    from harness.mapbuild_amcl_vendor import algorithms as nav2
    seal=read(a.prediction/'prediction-seal.json')
    mismatches=[]
    for p,h in seal['input_sha256'].items():
        if sha(Path(p))!=h:mismatches.append(p)
    for p,h in seal['prediction_sha256'].items():
        if sha(a.prediction/p)!=h:mismatches.append(p)
    if mismatches:raise ValueError('SEAL_CHANGED:'+str(mismatches))
    inputs=read(a.input/'own-inputs.json');truth=read(a.input/'eval-only.json')['rows']
    rows=[];streams=[]
    def stats(v):
        return dict(n=len(v),p05=float(np.percentile(v,5)),p50=float(np.median(v)),p95=float(np.percentile(v,95)),max=float(np.max(v))) if len(v) else dict(n=0)
    for world in inputs['worlds']:
        static=read(a.input/world['static']);field=StaticField(static)
        for rid,frames in world['robots'].items():
            folder=a.prediction/f"world-{world['world']:03d}-{rid}"
            scans=read(folder/'scans.json');pred=read(folder/'trajectory.json')
            gt=[v for v in truth if v['world']==world['world'] and v['rid']==rid]
            if not len(scans)==len(pred)==len(gt)==len(frames):raise ValueError('EXACT_STREAM_JOIN_REQUIRED')
            start=len(rows)
            for f,scan,r,g in zip(frames,scans,pred,gt):
                if not f['t']==r['t']==g['t']:raise ValueError('EXACT_TIME_JOIN_REQUIRED')
                camera=np.asarray(scan['camera']);points=np.array([
                    camera+v['range_m']*np.array([math.cos(v['bearing_rad']),math.sin(v['bearing_rad'])])
                    if v['status']=='hit' else [np.nan,np.nan] for v in scan['columns']])
                pose=np.asarray(g['truth_pose']);c,s=np.cos(pose[2]),np.sin(pose[2]);valid=np.isfinite(points).all(1)
                xy=points[valid]@np.array([[c,s],[-s,c]])+pose[:2];d=field.distances(xy)
                b=static['bounds_m'];outside=int(((xy[:,0]<b[0])|(xy[:,0]>b[1])|(xy[:,1]<b[2])|(xy[:,1]>b[3])).sum())
                row=dict(world=world['world'],rid=rid,t=f['t'],hits=int(valid.sum()),
                    wall_visible=bool(scan['segments']),sensor_updated=r['event']['attempted'],
                    field_distance_at_evaluation_pose_m=stats(d),outside_map_n=outside,farther_than_nav2_sigma_n=int((d>.2).sum()),
                    log_product_0202_at_evaluation_pose=float(np.log(nav2.likelihood_product(field,pose[None],points,.0202)[0])),
                    log_product_200_at_evaluation_pose=float(np.log(nav2.likelihood_product(field,pose[None],points,.2)[0])),
                    log_nav2_additive_200_at_evaluation_pose=float(np.log(nav2.likelihood(field,pose[None],points,.2)[0])),
                    reason_category='sparse_measurement_audit',blocked_object='authored_static_wall_nearest_only',minimum_gap_m=None,gap_status='not_measured')
                rows.append(row)
            rr=rows[start:]
            streams.append(dict(world=world['world'],rid=rid,views=len(rr),visible=sum(x['wall_visible'] for x in rr),
                updated=sum(x['sensor_updated'] for x in rr),authored_start_zones_available=bool(static.get('start_zones') or static.get('start_zone')),
                declared_start_zone_id=frames[0].get('start_zone_id'),static_map_sha256=sha(a.input/world['static'])))
    a.output.mkdir(exist_ok=False,parents=True)
    (a.output/'frame-table.json').write_text(json.dumps(dict(rows=rows),indent=2,allow_nan=False)+'\n')
    result=dict(status='MEASUREMENT_AUDIT_ONLY',views=len(rows),streams=streams,truth_to_estimator=0,new_filter_replays=0,
        physics_steps=0,render_calls=0,model_calls=0,seal_mismatches=mismatches,
        input=str(a.input),prediction=str(a.prediction),frame_table_sha256=sha(a.output/'frame-table.json'),
        scope=__doc__,reproduction=sys.argv)
    (a.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    visible=sum(r['wall_visible'] for r in rows);updates=sum(r['sensor_updated'] for r in rows)
    table=dict(source=str(a.input),reproduction=sys.argv,stages=[
        dict(stage='saved_views',cumulative_pass_n=len(rows),rejected_n=0),
        dict(stage='wall_visible',cumulative_pass_n=visible,rejected_n=len(rows)-visible),
        dict(stage='old_sensor_updates',cumulative_pass_n=updates,rejected_n=visible-updates)],
        stream_stages=[dict(stage='streams',cumulative_pass_n=len(streams),rejected_n=0),
            dict(stage='external_or_authored_coarse_prior',cumulative_pass_n=0,rejected_n=len(streams))],
        distribution=[dict(reason_category='coarse_start_prior_missing',reason='No operator region/rough heading supplied; static fields inventoried separately',n=len(streams),blocked_object='not_observed',minimum_gap_m=None,gap_status='not_measured')])
    (a.output/'rejection_table.json').write_text(json.dumps(table,indent=2)+'\n')
    print(json.dumps(dict(views=len(rows),streams=len(streams),visible=visible,updated=updates,seal_mismatches=mismatches)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('input','prediction','output'):p.add_argument('--'+name,type=Path,required=True)
    main(p.parse_args())
