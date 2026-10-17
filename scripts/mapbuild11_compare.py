"""Original-GCP5 paired R3 MC20 diagnostics. No physics/render/GT access.

Wrap only the resampling call to observe its input weights. Preserve all RNG,
filter parameters and returned poses. Compare to both sealed historical runs.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess

BASE=Path('/home/ugrp/ugrp-sim')


def raw(p):
    return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])


def read(p):return json.loads(raw(p))
def sha(p):return hashlib.sha256(raw(p)).hexdigest()


def case(job):
    import numpy as np
    from harness.mapbuild_amcl import StaticAMCL,OPTION,nav2
    trial,profile=job
    work=BASE/'runs/mapbuild10-mc20';own=read(work/'own-streams.json')
    s=next(s for s in own['streams'] if s['id']=='r3')
    prior=read(work/'priors.json')['streams']['r3'][trial]
    cal=read(BASE/'ops-reviews/mapbuild9/own-noise-command-r1-r2.json')
    req=read(Path(__file__).resolve().parents[1]/'experiments/2026-10-17-mapbuild8/requirements.json')
    m=StaticAMCL(s['static'],cal,req,option=OPTION,profile=profile,seed=2026101700+trial,
        initial_prior_option='start_zone_prior_v1',initial_prior=prior)
    original=nav2.resample;stats={}
    def observed(poses,weights,*args,**kwargs):
        stats.clear();stats.update(pre_n=len(weights),weight_min=float(weights.min()),weight_max=float(weights.max()),
            weight_p50=float(np.median(weights)),weight_p95=float(np.quantile(weights,.95)),
            entropy=float(-np.sum(weights*np.log(weights))),pre_ess=float(1/(weights@weights)))
        return original(poses,weights,*args,**kwargs)
    nav2.resample=observed
    rows=[];mismatch=[]
    prior_run=work if profile=='nav2_defaults_v1' else BASE/'runs/mapbuild10-rgb-field-legacy-v2'
    historical=read(prior_run/f'predictions/r3-coarse-{trial:03d}.json')['rows']
    try:
        from harness.e2e_rgb_vo import compose,between
        for f,old in zip(s['frames'],historical):
            e=m.step(f['t'],f['frame_id'],f['own_delta'],f['scan'],servo=f['servo'])
            candidate=compose(m.current['candidate_pose'],between(m.sensor_odom,m.odom)).tolist() if m.current else None
            if candidate!=old['candidate'] or e['converged']!=old['ready']:mismatch.append(f['frame_id'])
            if not e['attempted']:continue
            xy=e['xy_p95_m'];yaw=e['yaw_p95_rad'];r=req['handoff']
            coupled=yaw+math.atan2(xy,r['nominal_target_range_m']-xy)
            rows.append(dict(t=f['t'],frame_id=f['frame_id'],converged=e['converged'],xy95_m=xy,yaw95_deg=math.degrees(yaw),
                coupled95_deg=math.degrees(coupled),covariance=e['covariance'],post_n=e['samples'],**stats,
                xy_pass=xy<=r['position_error_m'],coupled_pass=coupled<=r['yaw_error_rad'],ess_pass=stats['pre_ess']>=stats['pre_n']/2,
                post_weights='uniform after standard resampling'))
    finally:nav2.resample=original
    return dict(trial=trial,profile=profile,rows=rows,historical_mismatch=mismatch,
        historical_prediction_sha256=sha(prior_run/f'predictions/r3-coarse-{trial:03d}.json'),
        inputs_sha256={str(p):sha(p) for p in [work/'own-streams.json',work/'priors.json']})


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('ORIGINAL_GCP5_ONLY')
    a.output.mkdir(exist_ok=False)
    jobs=[(i,p) for p in ('nav2_defaults_v1','nav2_rgb_field_v1') for i in range(20)]
    with ProcessPoolExecutor(max_workers=4) as pool:results=list(pool.map(case,jobs))
    import numpy as np
    summary=[]
    for profile in ('nav2_defaults_v1','nav2_rgb_field_v1'):
        cases=[c for c in results if c['profile']==profile];rows=[r for c in cases for r in c['rows']]
        summary.append(dict(profile=profile,trials=len(cases),converged=sum(any(r['converged'] for r in c['rows']) for c in cases),
            updates=len(rows),ready_updates=sum(r['converged'] for r in rows),
            failing_xy=sum(not r['xy_pass'] for r in rows),failing_coupled=sum(not r['coupled_pass'] for r in rows),
            failing_ess=sum(not r['ess_pass'] for r in rows),
            medians={k:float(np.median([r[k] for r in rows])) for k in ('xy95_m','yaw95_deg','coupled95_deg','pre_ess','pre_n','weight_max','weight_p95','entropy')},
            historical_mismatches=sum(len(c['historical_mismatch']) for c in cases)))
    for name,value in [('paired-frames.json',results),('summary.json',summary)]:
        (a.output/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
