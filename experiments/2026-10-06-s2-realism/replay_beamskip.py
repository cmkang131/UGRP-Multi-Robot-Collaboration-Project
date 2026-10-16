"""s2v57 fixed own RGB/commands. Evaluation truth is never opened here."""
import argparse
import base64
import copy
import hashlib
import json
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

from harness import zone_solo_cyan_contract_v106 as c
from harness import zone_pair_highpose_frame_gate as gate
from harness.zone_pair_highpose_exact_speedups import install
from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_bias_tempering import closure,replace_cell
from harness.zone_solo_cyan_landmarks import landmark_likelihood,wall_likelihood
from scripts.run_s2_landmarks_dev import runtime_factory as prior_factory
from scripts.run_s2_unknown_start import runtime_factory as global_factory

HERE=Path(__file__).resolve().parent
OUTPUTS=Path('/Users/changmin/projects/ugrp/outputs')
RUNS={q['seed']:Path(q['raw']) for q in json.loads((HERE/'baseline-v52-result.json').read_text())['runs']}
RUNS.update({s:OUTPUTS/f's2-realism-329eb4b6-s{s}-v139-unknown-start' for s in (1059,1060,1061)})

def read(p):return json.loads(p.read_text())
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def posterior(prior,ll):
    w=prior*np.exp(ll-np.max(ll));return w/w.sum()


def instrument(runtime):
    pf=runtime.pose.provider.loc._pf;wrapper=pf.update_obs;selected=closure(wrapper)['selected']
    score=selected.__globals__['likelihood'];mapped=closure(score)['mapped']
    audit=[];clouds={}
    def likelihood(field,px,packet):
        value=score(field,px,packet)  # exact original value returned to filter
        old_parts=[np.log(wall_likelihood(field,px,packet.wall))]
        old_parts.extend(np.log(landmark_likelihood(mapped,px,[f])) for f in packet.features)
        key=f'm{len(audit):04d}';prior=pf._weights()
        clouds[key+'p']=px.copy();clouds[key+'w']=prior.copy()
        clouds[key+'f']=np.array(old_parts);clouds[key+'l']=np.log(value)
        clouds[key+'active']=getattr(runtime,'beamskip_components',np.array(old_parts)).copy()
        audit.append(dict(key=key,t=float(pf.t),wall_count=len(packet.wall),features=copy.deepcopy(packet.features),
            wall_points=packet.wall.tolist(),prior_ess=float(1/(prior@prior)),
            posterior_ess=float(1/np.sum(posterior(prior,np.log(value))**2)),
            legacy_score_ratio=float(np.exp(np.ptp(np.sum(old_parts,axis=0)))),
            active_score_ratio=float(np.exp(min(700.,np.ptp(np.log(value))))),
            particle_count=pf.n,resample_count_before=pf.stats['resamples']))
        return value
    selected=bind(selected,likelihood=likelihood)
    updated=replace_cell(wrapper,'selected',selected)
    def update(*args):
        n=len(audit);result=updated(*args)
        if len(audit)>n:
            q=audit[-1];q['resampled']=pf.stats['resamples']>q['resample_count_before']
            q['particles_after']=pf.n;q['unique_after']=len(np.unique(pf.px,axis=0))
            clouds[q['key']+'after']=pf.px.copy();clouds[q['key']+'aw']=pf._weights().copy()
        return result
    pf.update_obs=update
    return audit,clouds


def replay(seed,option,out,limit=None):
    dest=out/f's{seed}-{option}';dest.mkdir(parents=True,exist_ok=False)
    raw=RUNS[seed];b=read(raw/'bundle.json');old=read(raw/'student_record.json')
    frames=rows(raw/'robots/r3/frames.jsonl');frames=frames[:limit] if limit else frames
    commands={}
    for cmd in old['commands']:commands.setdefault(round(cmd['t'],6),[]).append(cmd)
    _,undo=install('v98-exact-v6')
    factory=global_factory if seed>=1059 else prior_factory
    runtime=factory(b)(c.hp.resolve(c.MAP_ID)[0],c.ROOT/c.CALIBRATION,c.CALIBRATION_SHA,**b['task'])
    if option!='baseline':
        from harness.zone_solo_cyan_beamskip import attach,OPTION
        runtime=attach(runtime,sensor_beamskip=OPTION if option=='on' else 'off')
    audit,clouds=instrument(runtime);pf=runtime.pose.provider.loc._pf
    initial=commands[round(frames[0]['sim_time'],6)].pop(0)
    runtime.initial_commands(initial['t'],{'r3':{int(k):v for k,v in initial['pulses'].items()}})
    reference={round(q['t'],6):q for q in old['poses']}
    fields=('t_est','x','y','yaw','std_xy_m','std_yaw_rad','last_fix_t')
    poses=[];periodic=[];last_bucket=-1;particles=hashlib.sha256();pose_bytes=hashlib.sha256();old_bytes=hashlib.sha256()
    maximum=0.;first=None;started=time.monotonic()
    try:
        for i,f in enumerate(frames):
            now=f['sim_time'];data=(raw/f['path']).read_bytes()
            if hashlib.sha256(data).hexdigest()!=f['sha256']:raise ValueError('RGB_CHANGED')
            rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),1),cv2.COLOR_BGR2RGB)
            verdict,_=gate.gate().assess({**f,'image':base64.b64encode(data).decode()},'r3',now,ob=False)
            p=runtime.pose.on_frame(now,rgb if verdict==gate.VALID else None)
            q=dict(t=now,t_est=p.t_est,x=p.x_m,y=p.y_m,yaw=p.yaw_rad,std_xy_m=p.std_xy_m,
                std_yaw_rad=p.std_yaw_rad,last_fix_t=p.last_fix_t,observation_quality=copy.deepcopy(p.observation_quality),cov=copy.deepcopy(p.cov))
            ref=reference[round(now,6)]
            a={k:q[k] for k in fields};z={k:ref[k] for k in fields}
            pose_bytes.update(json.dumps(a).encode());old_bytes.update(json.dumps(z).encode())
            delta=max(abs(a[k]-z[k]) if a[k] is not None and z[k] is not None else float(a[k]!=z[k]) for k in fields)
            maximum=max(maximum,delta)
            if delta>1e-9 and first is None:first=dict(t=now,delta=delta)
            poses.append(q);particles.update(pf.px.tobytes());particles.update(pf._weights().tobytes())
            if int(now)!=last_bucket:
                key=f'p{len(periodic):04d}';clouds[key]=pf.px.copy();clouds[key+'w']=pf._weights().copy()
                periodic.append(dict(key=key,t=float(pf.t)));last_bucket=int(now)
            for cmd in commands.get(round(now,6),[]):runtime.on_command('r3',now,{k:v for k,v in cmd.items() if k!='t'})
            if i%1000==0:print(seed,option,i,'/',len(frames),'max_delta',maximum,flush=True)
        result=dict(seed=seed,option=option,poses=poses,measurements=audit,periodic=periodic,
            beamskip=copy.deepcopy(getattr(runtime,'beamskip_audit',None)),amcl=copy.deepcopy(runtime.amcl_audit),
            max_delta=maximum,first_mismatch=first,particle_sha256=particles.hexdigest(),pose_fields_sha256=pose_bytes.hexdigest(),
            recorded_pose_fields_sha256=old_bytes.hexdigest(),partial=bool(limit),gt_inputs=False,physics_runs=0,
            wall_s=time.monotonic()-started,source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            replay_script_sha256=sha(Path(__file__)),input_hashes={k:sha(raw/k) for k in ('bundle.json','student_record.json','robots/r3/frames.jsonl')})
        np.savez_compressed(dest/'clouds.npz',**clouds)
        (dest/'prediction.json').write_text(json.dumps(result)+'\n')
    finally:runtime.close();undo()
    if option in ('baseline','off'):
        assert maximum<=1e-9,first
        assert pose_bytes.hexdigest()==old_bytes.hexdigest()
    print(seed,option,'SEALED',maximum,'wall',result['wall_s'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,choices=RUNS)
    p.add_argument('--option',choices=('baseline','off','on'),required=True);p.add_argument('--max-frames',type=int)
    a=p.parse_args()
    for seed in ([a.seed] if a.seed else [1060,1059,1061,1051,1053,1054,1056,1057,1058]):
        replay(seed,a.option,a.output,a.max_frames)
