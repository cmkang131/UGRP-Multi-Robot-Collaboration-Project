"""Bounded original-VM MC20 replay instrumentation, not a tuned candidate."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import numpy as np


def read(p):
    return json.loads(p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst']))


def main(a):
    if not platform.node().startswith('ugrp-act-l4-'+a.host):raise ValueError('ORIGINAL_VM_ONLY')
    sys.path.insert(0,str(a.source))
    from harness.mapbuild_amcl import StaticAMCL,OPTION
    from harness.e2e_rgb_vo import between,compose
    own=read(a.work/'own-streams.json');counts=[]
    for s in own['streams']:
        hits=[sum(v.get('status')=='hit' for v in f['scan'].get('columns',[])) for f in s['frames']]
        counts.append(dict(stream=s['id'],frames=len(hits),zero=sum(n==0 for n in hits),
            hits_min_median_p90_max=np.percentile(hits,[0,50,90,100]).tolist(),
            visible_frames=sum(bool(f['scan']['segments']) for f in s['frames'])))
    result=dict(host=a.host,wall_observations=counts,physics_steps=0,render_calls=0,truth_to_filter=0)
    if a.host=='gcp5':
        s=next(s for s in own['streams'] if s['id']=='r3');prior=read(a.work/'priors.json')['streams']['r3'][0]
        m=StaticAMCL(s['static'],read(a.calibration),read(a.requirements),option=OPTION,
            profile='nav2_defaults_v1',seed=2026101700,initial_prior_option='start_zone_prior_v1',initial_prior=prior)
        old=read(a.work/'predictions/r3-coarse-000.json')['rows'];updates=[];max_diff=0.;last=None
        for f,sealed in zip(s['frames'],old):
            acc=between(m.sensor_odom,compose(m.odom,f['own_delta']))
            e=m.step(f['t'],f['frame_id'],f['own_delta'],f['scan'],servo=f['servo'])
            p=compose(m.current['candidate_pose'],between(m.sensor_odom,m.odom)).tolist() if m.current else None
            if p is not None:max_diff=max(max_diff,float(np.max(abs(np.array(p)-sealed['candidate']))))
            if e['attempted']:
                tr=math.hypot(acc[0],acc[1]);r1=0. if tr<.01 else math.atan2(acc[1],acc[0]);r2=math.atan2(math.sin(acc[2]-r1),math.cos(acc[2]-r1))
                n=[min(abs(v),abs(math.atan2(math.sin(v-math.pi),math.cos(v-math.pi)))) for v in (r1,r2)]
                a1,a2,a3,a4=m.alphas
                updates.append(dict(t=f['t'],since_last_sim_s=None if last is None else f['t']-last,delta=acc.tolist(),
                    trans_m=tr,rot1_rad=r1,rot2_rad=r2,
                    model_sd_rot1_rot2_rad=[math.sqrt(a1*n[0]**2+a2*tr**2),math.sqrt(a1*n[1]**2+a2*tr**2)],
                    model_sd_translation_m=math.sqrt(a3*tr**2+a4*(n[0]**2+n[1]**2)),
                    samples_before=e['work']['particles'],samples_after=e['samples'],ess=e['ess']))
                last=f['t']
        if max_diff>0:raise ValueError('INSTRUMENTATION_CHANGED_PREDICTION')
        result.update(r3_exact_sealed_replay_max_abs=max_diff,updates=updates,
            population_min_median_max=np.percentile([u['samples_after'] for u in updates],[0,50,100]).tolist(),
            update_interval_median_p90_max_s=np.percentile([u['since_last_sim_s'] for u in updates[1:]],[50,90,100]).tolist(),
            alpha_own=m.alphas.tolist(),alpha_nav2_default=[.2]*4)
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('updates','wall_observations')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','work','calibration','requirements','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--host',choices=['gcp3','gcp5'],required=True);main(p.parse_args())
