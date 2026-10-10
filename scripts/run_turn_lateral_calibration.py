"""Clock-only independent calibration; measurement returned only after capture."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from scripts.run_active_wall_nav2 import dump, frozen_bundle
from scripts.run_own_route_references import server_slot, resources, rows
from scripts.run_wall_servo_stiffness import arm

ROOT = Path(__file__).resolve().parents[1]
SEEDS = tuple(range(70001,70006))


def schedule(seed):
    if seed not in SEEDS: raise ValueError('UNREGISTERED_CALIBRATION_SEED')
    tick = 40
    blocks, commands = [], {}
    def block(kind, axis, sign, n):
        nonlocal tick
        start = tick
        for j in range(n):
            commands[tick] = dict(kind='mecanum',forward=0.,left=0.,turn=0.,duration_s=.1)
            commands[tick][axis] = sign*(.35 if axis=='turn' else .3)
            tick += 4
            if kind=='isolated': tick += 36
        blocks.append(dict(kind=kind,axis=axis,sign=sign,n=n,start_tick=start,end_tick=tick))
        tick += 40
    signs = (1,-1) if seed%2 else (-1,1)
    for sign in signs:
        block('isolated','turn',sign,5)
        block('continuous','turn',sign,20)
    # Validation only: 20 forward pulses (~.26m) + 15 turns (~90deg).
    # Reduced square fits the fixed plant; no truth-based heading/endpoint stop.
    for sign in signs:
        for _ in range(4):
            block('square','forward',1,20)
            block('square','turn',sign,15)
    return blocks,commands,tick


def capture(a):
    from sim.pulse_rotation_audit import PhysicsBackend
    blocks,commands,ticks=schedule(a.seed)
    b=frozen_bundle('calibration',ROOT.name)
    b.update(execution_bundle_id=f'egomap70-calibration-{a.seed}',spawn=[3.5,1.1,0.],case_cap_s=ticks/20)
    b['task']['seed']=a.seed
    a.output.mkdir(parents=True,exist_ok=False)
    dump(a.output/'bundle.json',b);dump(a.output/'schedule.json',dict(blocks=blocks,commands=commands,ticks=ticks))
    result=dict(seed=a.seed,status='HOST_ERROR',host='oracle-x86',source_sha=ROOT.name,gt_feedback=False,model_calls=0)
    backend=None;wall=time.monotonic()
    try:
        with server_slot():
            backend=PhysicsBackend(b,a.output,seed=a.seed);backend.reset(5.)
            start=backend.now;backend.set_deadline(start+ticks/20)
            result['start_sim_s']=start
            for action in arm(b['initial_servo']):backend.issue('r3',action)
            for tick in range(ticks+1):
                # Record exact pulse-boundary truth BEFORE issue, write-only.
                backend.eval_sample()
                if tick in commands:backend.issue('r3',commands[tick])
                if tick%100==0:
                    backend.capture()
                    dump(a.output/'progress.json',dict(sim_s=tick/20,tick=tick))
                    print(a.seed,tick/20,flush=True)
                if time.monotonic()-wall>3600:raise TimeoutError('CALIBRATION_HOST_BUDGET')
                if tick<ticks:backend.advance_to(round(start+(tick+1)/20,9))
            result.update(status='RECORDED',sim_s=ticks/20,pulses=len(commands))
    except Exception as e:
        import traceback
        traceback.print_exc()
        result.update(status='PHYSICAL_FAILURE' if type(e).__name__=='PhysicalStop' else 'HOST_ERROR',error=repr(e))
    finally:
        if backend:backend.close()
        result['wall_s']=time.monotonic()-wall
        dump(a.output/'result.json',result)
        dump(a.output/'artifacts.sha256.json',{str(p.relative_to(a.output)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in a.output.rglob('*') if p.is_file() and p.name!='artifacts.sha256.json'})
    return result['status']=='RECORDED'


def samples(folder):
    result=json.loads((folder/'result.json').read_text())
    if result['status']!='RECORDED':raise ValueError('INCOMPLETE_CALIBRATION '+str(folder))
    truth={round(x['t'],6):x for x in rows(folder/'eval_only/trajectory.jsonl')}
    blocks,commands,_=schedule(result['seed']);out=[]
    for tick,cmd in commands.items():
        t=result['start_sim_s']+tick/20
        start=truth[round(t,6)];yaw=start['robot_yaw_rad'];c,s=math.cos(yaw),math.sin(yaw)
        R=np.array([[c,s],[-s,c]])
        curve=[]
        for dt in (0,.05,.1,.15,.2):
            now=truth[round(t+dt,6)]
            xy=R@(np.asarray(now['robot_xyz_m'][:2])-start['robot_xyz_m'][:2])
            angle=math.atan2(math.sin(now['robot_yaw_rad']-yaw),math.cos(now['robot_yaw_rad']-yaw))
            curve.append([*xy,float(angle)])
        block=next(b for b in blocks if b['start_tick']<=tick<b['end_tick'])
        out.append(dict(seed=result['seed'],t=t,kind=block['kind'],command=cmd,curve=curve))
    return out


def fit(folder):
    from harness.self_pulse_rotation import calibrated_model
    from harness.turn_lateral_calibration import OPTION,apply_model
    data=[s for seed in SEEDS for s in samples(folder/f'cal-{seed}')]
    artifact=dict(option=OPTION,fit_seeds=list(SEEDS[:3]),check_seeds=list(SEEDS[3:]),
        source='independent egomap70 rotations; square runs validation only',profiles={})
    baseline=calibrated_model()
    for sign in (1,-1):
        key=f'0:turn:{sign*.35:.2f}:0.10'
        train=[r for r in data if r['seed'] in SEEDS[:3] and r['kind'] in ('isolated','continuous') and r['command']['turn']==sign*.35]
        mean=np.mean([r['curve'] for r in train],axis=0)
        y=np.interp(baseline['profiles'][key]['times'],[0,.05,.1,.15,.2],mean[:,1])
        artifact['profiles'][key]=dict(lateral_curve_m=y.tolist(),n=len(train),mean_endpoint_m=float(y[-1]),
            endpoint_std_m=float(np.std([r['curve'][-1][1] for r in train],ddof=1)))
    model=apply_model(artifact);report=[]
    for sign in (1,-1):
        key=f'0:turn:{sign*.35:.2f}:0.10'
        for kind in ('isolated','continuous','square'):
            check=[r for r in data if r['seed'] in SEEDS[3:] and r['kind']==kind and r['command']['turn']==sign*.35]
            y=np.array([r['curve'][-1][1] for r in check])
            before=baseline['profiles'][key]['mean_delta'][1];after=model['profiles'][key]['mean_delta'][1]
            report.append(dict(direction=sign,kind=kind,n=len(y),actual_mean_m=float(y.mean()),old_m=before,new_m=after,
                old_rmse_m=float(np.sqrt(np.mean((y-before)**2))),new_rmse_m=float(np.sqrt(np.mean((y-after)**2)))))
    artifact['qualification']=dict(checks=report,gate=all(r['new_rmse_m']<=r['old_rmse_m'] for r in report),
        rule='heldout turn lateral RMSE does not increase, each sign x isolated/continuous/square',thresholds_changed=False)
    artifact['raw']=[dict(path=str(folder/f'cal-{s}'),manifest_sha256=hashlib.sha256((folder/f'cal-{s}'/'artifacts.sha256.json').read_bytes()).hexdigest()) for s in SEEDS]
    dump(folder/'calibration.json',artifact)
    return artifact


def batch(a):
    a.output.mkdir(parents=True,exist_ok=False);running=[];pending=list(SEEDS);checks=[];finished=[]
    while pending or running:
        load,memory=resources()
        if pending and load+2*len(running)<51 and memory>=6:
            seed=pending.pop(0);out=a.output/f'cal-{seed}';stream=(a.output/f'cal-{seed}.log').open('x')
            p=subprocess.Popen([sys.executable,'-m',__name__.replace('__main__','scripts.run_turn_lateral_calibration'),
                '--mode','capture','--seed',str(seed),'--output',str(out)],stdout=stream,stderr=subprocess.STDOUT)
            running.append((seed,p,stream,time.monotonic(),out))
        for record in running.copy():
            seed,p,stream,started,out=record;age=time.monotonic()-started
            if age>=180 and seed not in [x['seed'] for x in checks] and (out/'progress.json').exists():
                tr=rows(out/'eval_only/trajectory.jsonl')
                movement=max((math.dist(x['robot_xyz_m'][:2],tr[0]['robot_xyz_m'][:2]) for x in tr),default=0)
                check=dict(seed=seed,age_s=age,progress=json.loads((out/'progress.json').read_text()),displacement_m=movement,
                    log_exception='Traceback' in (a.output/f'cal-{seed}.log').read_text())
                checks.append(check);dump(a.output/'initial-check.json',checks)
            if p.poll() is not None:
                stream.close();(out/'EXIT').write_text(str(p.returncode)+'\n');running.remove(record);finished.append(dict(seed=seed,exit=p.returncode))
        dump(a.output/'status.json',dict(pending=pending,running=[x[0] for x in running],finished=finished))
        if pending or running:time.sleep(3)
    if any(x['exit'] for x in finished):return 1
    return 0 if fit(a.output)['qualification']['gate'] else 2


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('batch','capture','fit'),required=True)
    p.add_argument('--seed',type=int,choices=SEEDS);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if os.getenv('UGRP_EXECUTION_HOST')!='oracle-x86':raise RuntimeError('ORACLE_ONLY')
    if a.mode=='batch':return batch(a)
    if a.mode=='fit':fit(a.output);return 0
    return 0 if capture(a) else 1

if __name__=='__main__':raise SystemExit(main())
