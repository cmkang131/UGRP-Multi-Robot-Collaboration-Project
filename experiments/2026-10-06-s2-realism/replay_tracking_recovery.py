"""s2v55 frozen own-RGB replay. Ground truth is opened by score(), never replay()."""
import argparse
import base64
import copy
import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np

from harness import zone_solo_cyan_contract_v106 as c
from harness import zone_pair_highpose_frame_gate as gate
from harness.zone_pair_highpose_exact_speedups import install
from scripts.run_s2_unknown_start import runtime_factory

ROOT = Path('/Users/changmin/projects/ugrp/outputs')
RAW = ROOT/'s2-realism-329eb4b6-s1060-v139-unknown-start'
HERE = Path(__file__).resolve().parent

def read(p): return json.loads(p.read_text())
def rows(p): return [json.loads(x) for x in p.read_text().splitlines()]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def replay(out, option, limit=None):
    out.mkdir(parents=True, exist_ok=True)
    dest=out/option; dest.mkdir(exist_ok=False)
    b=read(RAW/'bundle.json');old=read(RAW/'student_record.json')
    frames=rows(RAW/'robots/r3/frames.jsonl'); frames=frames[:limit] if limit else frames
    commands={}
    for q in old['commands']:commands.setdefault(round(q['t'],6),[]).append(q)
    _,undo=install('v98-exact-v6')
    runtime=runtime_factory(b)(c.hp.resolve(c.MAP_ID)[0],c.ROOT/c.CALIBRATION,c.CALIBRATION_SHA,**b['task'])
    if option!='baseline':
        from harness.zone_solo_cyan_tracking_recovery import attach, OPTION
        runtime=attach(runtime,localization_recovery=OPTION if option=='on' else 'off')
    pf=runtime.pose.provider.loc._pf
    snapshots=[]; updates=[]; arrays={}; last_bucket=-1
    def snapshot(label,t,weights=None):
        key=f'p{len(snapshots):04d}'
        arrays[key]=pf.px.copy();arrays[key+'w']=pf._weights().copy() if weights is None else weights.copy()
        snapshots.append(dict(key=key,kind=label,t=float(t),n=pf.n))
    gains=pf._gains
    def audit_gain(prior,posterior):
        snapshot('pre_observation',pf.t,prior);snapshot('post_observation',pf.t,posterior)
        updates.append(dict(t=float(pf.t),ess_prior=float(1/sum(prior**2)),ess_posterior=float(1/sum(posterior**2))))
        return gains(prior,posterior)
    pf._gains=audit_gain
    initial=commands[round(frames[0]['sim_time'],6)].pop(0)
    runtime.initial_commands(initial['t'],{'r3':{int(k):v for k,v in initial['pulses'].items()}})
    reference={round(p['t'],6):p for p in old['poses']}
    fields=('t_est','x','y','yaw','std_xy_m','std_yaw_rad','last_fix_t')
    pred=[];cloud=hashlib.sha256();max_delta=0.; first=None; started=time.monotonic()
    try:
        for i,f in enumerate(frames):
            now=f['sim_time'];data=(RAW/f['path']).read_bytes()
            assert hashlib.sha256(data).hexdigest()==f['sha256']
            rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),1),cv2.COLOR_BGR2RGB)
            verdict,_=gate.gate().assess({**f,'image':base64.b64encode(data).decode()},'r3',now,ob=False)
            p=runtime.pose.on_frame(now,rgb if verdict==gate.VALID else None)
            q=dict(t=now,t_est=p.t_est,x=p.x_m,y=p.y_m,yaw=p.yaw_rad,std_xy_m=p.std_xy_m,
                   std_yaw_rad=p.std_yaw_rad,last_fix_t=p.last_fix_t,observation_quality=copy.deepcopy(p.observation_quality))
            pred.append(q);ref=reference[round(now,6)]
            delta=max(abs(q[k]-ref[k]) if q[k] is not None and ref[k] is not None else float(q[k]!=ref[k]) for k in fields)
            max_delta=max(max_delta,delta)
            if delta>1e-9 and first is None:first=dict(t=now,delta=delta)
            cloud.update(pf.px.tobytes());cloud.update(pf._weights().tobytes())
            if int(now)!=last_bucket:snapshot('periodic',pf.t);last_bucket=int(now)
            for cmd in commands.get(round(now,6),[]):runtime.on_command('r3',now,{k:v for k,v in cmd.items() if k!='t'})
            if i%500==0:print(option,i,'/',len(frames),'delta',max_delta,flush=True)
        result=dict(option=option,poses=pred,amcl=copy.deepcopy(runtime.amcl_audit),
            recovery=copy.deepcopy(getattr(runtime,'tracking_recovery_audit',None)),updates=updates,
            snapshots=snapshots,cloud_sha256=cloud.hexdigest(),max_delta=max_delta,first_mismatch=first,
            wall_s=time.monotonic()-started,partial=bool(limit),gt_inputs=False,commands_fixed=True,
            physics_runs=0,input_hashes={k:sha(RAW/k) for k in ('bundle.json','student_record.json','robots/r3/frames.jsonl')})
        np.savez_compressed(dest/'clouds.npz',**arrays)
        (dest/'prediction.json').write_text(json.dumps(result)+'\n')
    finally:runtime.close();undo()
    if option in ('baseline','off'):assert max_delta<=1e-9,first
    print(option,'SEALED',max_delta,'seconds',result['wall_s'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--option',choices=('baseline','off','on'),required=True);p.add_argument('--max-frames',type=int)
    a=p.parse_args();replay(a.output,a.option,a.max_frames)
