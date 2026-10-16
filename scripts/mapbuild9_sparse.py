"""gcp3 warp8f 418 saved views: identical standard AMCL, no physics/render."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys


def read(p):
    return json.loads(p.read_text() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst']))
def sha(p):
    return hashlib.sha256(p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')


def setup(a):
    root=Path(__file__).resolve().parents[1]
    sys.path[:0]=[str(root),str(root/'scripts'),str(a.owner),str(a.owner/'scripts')]
    import harness,sim
    harness.__path__.append(str(a.owner/'harness'));sim.__path__.append(str(a.owner/'sim'))
    return root


def predict_robot(job):
    a,w,rid,frames=job;root=setup(a)
    import cv2
    import numpy as np
    from harness.mapbuild_amcl import StaticAMCL,OPTION
    from harness.mapbuild_camera import adapters
    from harness.servo_camera_fk import CARRY_OPTION
    from harness.scene_colour_boundary import ColourBoundaryState,RELOC16_OPTION
    from harness.e2e_rgb_vo import between,PARAMS,compose
    cv2.setNumThreads(1)
    calibration=a.owner/'experiments/2026-10-16-reloc16/colour-calibration.json'
    if sha(calibration)!='a37cf96551abbfb8b38df3efc1cd61f3f357ac9eb3a1dcd0b4d9947242e4e24f':raise ValueError('FROZEN_COLOR_REQUIRED')
    state=ColourBoundaryState('walls_floor_contrast_v5_indigo110_s80',read(calibration),option=RELOC16_OPTION)
    pair,scan=adapters(CARRY_OPTION)
    amcl=StaticAMCL(read(a.input/w['static']),read(a.calibration),read(a.requirements),option=OPTION,seed=20261017)
    previous=None;servo_old=None;old_t=None;command_old=frames[0]['command_pose'];rows=[];scans=[];off=np.zeros(3)
    folder=a.output/f"world-{w['world']:03d}-{rid}";folder.mkdir()
    for f in frames:
        file=a.input/f['rgb']
        if sha(file)!=f['rgb_sha256'] or f['rgb_sha256']!=f['recorded_rgb_sha256']:raise ValueError('RGB_CHANGED')
        servo={int(k):int(v) for k,v in f['servo'].items()}
        if servo[1]<=1600:raise ValueError('SPARSE_OPEN_ONLY_NOT_CARRY')
        rgb=cv2.cvtColor(cv2.imread(str(file)),cv2.COLOR_BGR2RGB)
        reason=('bootstrap' if previous is None else 'unknown_servo_change' if servo!=servo_old else
                'unknown_pair_gap' if f['t']-old_t>PARAMS['max_pair_gap_s'] else None)
        flow=dict(status=reason) if reason else pair(previous,rgb,servo)
        delta=flow['delta'] if flow['status']=='measured' else between(command_old,f['command_pose'])
        off=compose(off,delta);view=scan(rgb,servo,state)
        # Views were saved after .8s/1s own-command wait (original metadata).
        # This is a settled sparse scan, not a fabricated adjacent-frame LK.
        event=amcl.step(f['t'],len(rows),delta,view,servo=f['servo'])
        candidate=(compose(amcl.current['candidate_pose'],between(amcl.sensor_odom,amcl.odom)).tolist() if amcl.current else None)
        rows.append(dict(t=f['t'],frame_id=len(rows),off_pose=off.tolist(),global_candidate=candidate,event=event,lk=flow))
        scans.append(view);previous=rgb;servo_old=servo;old_t=f['t'];command_old=f['command_pose']
    dump(folder/'trajectory.json',rows);dump(folder/'scans.json',scans);dump(folder/'own-map.json',amcl.local_map)
    np.savez_compressed(folder/'posterior.npz',particles=amcl.particles,weights=amcl.weights)
    ready=[r for r in rows if r['event']['converged']]
    summary=dict(world=w['world'],rid=rid,seed=w['seed'],frames=len(rows),visible=sum(bool(s['segments']) for s in scans),
        attempted=sum(r['event']['attempted'] for r in rows),ready_n=len(ready),first_ready_sim_s=ready[0]['t'] if ready else None,
        motion_status=dict(Counter(r['lk']['status'] for r in rows)),reasons=dict(Counter(r['event']['reason'] for r in rows)),
        loaded_camera_frames=0,physics_steps=0,truth_inputs=0,full_posterior=amcl.current)
    dump(folder/'summary.json',summary);print(json.dumps({k:v for k,v in summary.items() if k!='full_posterior'}),flush=True)
    return summary


def predict(a):
    root=setup(a)
    if not Path(read(a.queue)['rejection_table']).is_file() or not read(a.stack_check).get('ok'):raise ValueError('PREFLIGHT_REQUIRED')
    a.output.mkdir(parents=True,exist_ok=False);inputs=read(a.input/'own-inputs.json')
    jobs=[(a,w,r,f) for w in inputs['worlds'] for r,f in w['robots'].items()]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:result=list(pool.map(predict_robot,jobs))
    dump(a.output/'predictions.json',result)
    visible=sum(r['visible'] for r in result);attempted=sum(r['attempted'] for r in result);ready=sum(r['ready_n'] for r in result);total=sum(r['frames'] for r in result)
    reasons=Counter()
    for r in result:reasons.update(r['reasons'])
    dump(a.output/'rejection_table.json',dict(source=str(a.input),reproduction=sys.argv,stages=[
        dict(stage='saved_views',cumulative_pass_n=total,rejected_n=0),dict(stage='visible_wall',cumulative_pass_n=visible,rejected_n=total-visible),
        dict(stage='sensor_update',cumulative_pass_n=attempted,rejected_n=visible-attempted),dict(stage='full_posterior_ready',cumulative_pass_n=ready,rejected_n=attempted-ready)],
        distribution=[dict(category='static_amcl',reason=k,n=v,blocked_object='sparse_own_wall_observations',minimum_gap_m=None,gap_status='not_measured') for k,v in reasons.items()]))
    sources=[a.input/'own-inputs.json',a.calibration,a.requirements,a.queue,a.stack_check,root/'harness/mapbuild_amcl.py',root/'harness/mapbuild_amcl_vendor/algorithms.py',Path(__file__)]
    # Own RGB hashes are checked per stream and recorded by original manifest.
    dump(a.output/'prediction-seal.json',dict(input_sha256={str(p):sha(p) for p in sources},
        prediction_sha256={str(p.relative_to(a.output)):sha(p) for p in a.output.rglob('*') if p.is_file()},
        truth_inputs=0,spawn_inputs=0,scale=1,physics_steps=0,owner_source=str(a.owner)))


def score(a):
    setup(a)
    import numpy as np
    from harness.e2e_rgb_vo import compose
    seal=read(a.output/'prediction-seal.json')
    for p,h in seal['input_sha256'].items():
        if sha(Path(p))!=h:raise ValueError('INPUT_CHANGED:'+p)
    for p,h in seal['prediction_sha256'].items():
        if sha(a.output/p)!=h:raise ValueError('PREDICTION_CHANGED:'+p)
    truth=read(a.input/'eval-only.json')['rows'];pred=read(a.output/'predictions.json');req=read(a.requirements)['handoff'];scores=[]
    def metrics(rows,ev):
        result=[]
        for r,e in zip(rows,ev):
            def err(p):
                xy=math.dist(p[:2],e['truth_pose'][:2]);yaw=abs(math.atan2(math.sin(p[2]-e['truth_pose'][2]),math.cos(p[2]-e['truth_pose'][2])))
                coupled=yaw+math.atan2(xy,req['nominal_target_range_m']-xy)
                return dict(xy_m=xy,yaw_deg=math.degrees(yaw),direction_coupled_deg=math.degrees(coupled),handoff_pass=xy<=req['position_error_m'] and coupled<=req['yaw_error_rad'])
            off=err(compose(ev[0]['truth_pose'],r['off_pose']));amcl=err(r['global_candidate']) if r['global_candidate'] is not None else None
            result.append(dict(t=r['t'],off=off,amcl=amcl,ready=r['event']['converged'],wrong_ready=bool(r['event']['converged'] and not amcl['handoff_pass'])))
        return result
    for p in pred:
        rows=read(a.output/f"world-{p['world']:03d}-{p['rid']}"/'trajectory.json')
        ev=[e for e in truth if e['world']==p['world'] and e['rid']==p['rid']]
        if len(ev)!=len(rows) or [e['t'] for e in ev]!=[r['t'] for r in rows]:raise ValueError('EXACT_TIME_JOIN_REQUIRED')
        values=metrics(rows,ev);ready=[r for r in values if r['ready']];first=next((i for i,r in enumerate(values) if r['ready']),None)
        after=values[first:] if first is not None else []
        off_rmse=math.sqrt(np.mean([r['off']['xy_m']**2 for r in after])) if after else None
        amcl_rmse=math.sqrt(np.mean([r['amcl']['xy_m']**2 for r in after])) if after else None
        scores.append(dict(world=p['world'],rid=p['rid'],frames=len(rows),ready_updates=len(ready),
            wrong_ready_updates=sum(r['wrong_ready'] for r in values),first_converged_sim_s=ready[0]['t'] if ready else None,
            off_xy_rmse_after_m=off_rmse,amcl_xy_rmse_after_m=amcl_rmse,
            offline_pass=bool(after and all(r['amcl']['handoff_pass'] for r in after) and amcl_rmse<off_rmse),
            final=values[-1],timeline=values))
    summary=dict(status='OFFLINE_PASS' if all(r['offline_pass'] for r in scores) else 'NOT_READY',host='gcp3',streams=len(scores),views=sum(r['frames'] for r in scores),
        streams_converged=sum(r['ready_updates']>0 for r in scores),streams_wrong_converged=sum(r['wrong_ready_updates']>0 for r in scores),wrong_converged_updates=sum(r['wrong_ready_updates'] for r in scores),
        streams_improved_and_within_requirements=sum(r['offline_pass'] for r in scores),physical_release_success=False,physics_steps=0,
        scope='sparse open-camera only; no carried travel qualification; no pooling with gcp5',
        prediction_seal_sha256=sha(a.output/'prediction-seal.json'),requirements_sha256=sha(a.requirements),source=str(a.input),reproduction=sys.argv)
    dump(a.output/'evaluation.json',dict(summary=summary,streams=scores));print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['predict','score'],required=True)
    for k in ('input','owner','output','calibration','requirements','queue','stack-check'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--workers',type=int,default=4)
    a=p.parse_args()
    if not platform.node().startswith('ugrp-act-l4-gcp3'):raise ValueError('GCP3_ONLY')
    (predict if a.stage=='predict' else score)(a)
