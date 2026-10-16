"""gcp5 saved-frame AMCL, no eval-only file reads; seal predictions first."""
import argparse
from collections import Counter
import hashlib
import json
import platform
from pathlib import Path
import sys


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')


def run(a):
    if not platform.node().startswith(('ugrp-act-l4-gcp5','ugrp-act-l4-gcp3')):
        raise ValueError('SOURCE_VM_ONLY')
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
    from harness.mapbuild_amcl import StaticAMCL,OPTION,METHOD
    from harness.e2e_rgb_vo import compose,between
    import numpy as np
    q=read(a.queue)
    if not Path(q['rejection_table']).is_file():raise ValueError('PRIOR_FUNNEL_REQUIRED')
    check=read(a.stack_check)
    # check_current_stack uses status=pass for replay exceptions too.
    if check.get('ok') is not True:
        raise ValueError('CURRENT_STACK_CHECK_REQUIRED:'+str(check.get('status')))
    a.output.mkdir(parents=True,exist_ok=False)
    own=read(a.input/'own.json')['frames'];saved=read(a.saved/'trajectory.json');scan_path=a.saved/'scans.json' if (a.saved/'scans.json').is_file() else a.input/'scans.json';scans=read(scan_path)
    if len(saved)!=len(own) or len(scans)!=len(own):raise ValueError('FRAME_COUNT_MISMATCH')
    if [r['frame_id'] for r in saved]!=[f['frame_id'] for f in own]:raise ValueError('EXACT_FRAME_JOIN_REQUIRED')
    calibration=read(a.calibration);req=read(a.requirements)
    amcl=StaticAMCL(read(a.input/'static-map.json'),calibration,req,option=OPTION,seed=a.seed)
    from harness.mapbuild_command_prior import CommandPrior,OPTION as COMMAND
    from harness.selfmap_map_correction import SelfMapCorrection
    prior=CommandPrior(read(a.command_model),option=COMMAND)
    fused=SelfMapCorrection(read(a.input/'static-map.json'))
    commands=read(a.input/'commands.json');last_servo=None;motion_sources=Counter()
    rows=[];off=np.zeros(3)
    for k,(f,r,s) in enumerate(zip(own,saved,scans)):
        rgb=a.input/f['rgb']
        if sha(rgb)!=f['sha256']:raise ValueError('RGB_CHANGED')
        servo={int(k):v for k,v in f['servo'].items()}
        prediction=prior.predict(f['command_delta'],f['command_covariance'],commands[k-1] if k else None,
            servo,last_servo,round(f['t']-own[k-1]['t'],6) if k else 0.)
        _,motion=fused.step(f['t'],f['frame_id'],prediction['delta'],prediction['covariance'],r['lk'],dict(segments=[]))
        delta=np.asarray(motion['motion_delta']);off=compose(off,delta)
        motion_sources[prediction['source']]+=1;last_servo=servo
        event=amcl.step(f['t'],f['frame_id'],delta,s,servo=f['servo'])
        # Diagnostic global output between updates: same posterior mean +
        # accumulated own odometry. It remains unadopted until a fresh ready
        # measurement and NEVER becomes a substitute global initialization.
        candidate=(compose(amcl.current['candidate_pose'],between(amcl.sensor_odom,amcl.odom)).tolist()
                   if amcl.current else None)
        rows.append(dict(t=f['t'],frame_id=f['frame_id'],off_pose=off.tolist(),
            global_candidate=candidate,event=event,servo=f['servo']))
        if event['attempted']:print(json.dumps(dict(frame=f['frame_id'],t=f['t'],n=event['samples'],xy95=event['xy_p95_m'],yaw95=event['yaw_p95_rad'],ready=event['converged'])),flush=True)
    dump(a.output/'trajectory.json',rows);dump(a.output/'own-map.json',amcl.local_map)
    np.savez_compressed(a.output/'posterior.npz',particles=amcl.particles,weights=amcl.weights)
    attempts=[r for r in rows if r['event']['attempted']];ready=[r for r in attempts if r['event']['converged']]
    visible=sum(bool(s['segments']) for s in scans)
    stages=[dict(stage='recorded',cumulative_pass_n=len(rows),rejected_n=0),
        dict(stage='visible_wall',cumulative_pass_n=visible,rejected_n=len(rows)-visible),
        dict(stage='motion_or_camera_update',cumulative_pass_n=len(attempts),rejected_n=visible-len(attempts)),
        dict(stage='full_posterior_ready',cumulative_pass_n=len(ready),rejected_n=len(attempts)-len(ready))]
    reasons=Counter(r['event']['reason'] for r in rows)
    dump(a.output/'rejection_table.json',dict(stages=stages,source=str(a.input),reproduction=sys.argv,
        distribution=[dict(category='static_amcl',reason=k,n=v,blocked_object='observed_wall_or_global_ambiguity',minimum_gap_m=None,gap_status='not_measured') for k,v in reasons.items()]))
    sources=[a.input/'own.json',a.input/'static-map.json',a.saved/'trajectory.json',scan_path,a.command_model,a.input/'commands.json',a.calibration,a.requirements,a.queue,a.stack_check,root/'configs/current_stack.json',root/'harness/mapbuild_amcl.py',root/'harness/mapbuild_amcl_vendor/algorithms.py',Path(__file__)]
    dump(a.output/'prediction-seal.json',dict(input_sha256={str(p):sha(p) for p in sources},prediction_sha256={p.name:sha(p) for p in a.output.iterdir() if p.is_file()},truth_inputs=0,top_inputs=0,held_world_reads=0,spawn_inputs=0,seed=a.seed,scale=1))
    summary=dict(status='PREDICTIONS_SEALED_UNSCORED',raw=str(a.input),saved=str(a.saved),frames=len(rows),method=METHOD,map_correction=OPTION,
        measured_updates=len(attempts),ready_updates=len(ready),first_converged_sim_s=ready[0]['t'] if ready else None,
        motion_sources=dict(motion_sources),full_posterior=amcl.current,own_map_frames=len(amcl.local_map),rejection_table=str(a.output/'rejection_table.json'),truth_inputs=0,seed=a.seed)
    dump(a.output/'summary.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('input','saved','output','calibration','requirements','queue','stack-check','command-model'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--seed',type=int,default=20261017);run(p.parse_args())
