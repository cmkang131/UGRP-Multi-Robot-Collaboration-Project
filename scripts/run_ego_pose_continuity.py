"""Finite Azure DEV comparison using the existing fresh B/return adapter."""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
import numpy as np

from harness.active_camera import bind
from harness.ego_pose_continuity import Options, REP105, CLUSTER, MAHALANOBIS, install
from scripts import run_egomap_fresh_pair as base
from scripts.evaluate_ego_pose_continuity import jump_metrics
from scripts.evaluate_egomap_covariance import lines

ROOT=Path(__file__).resolve().parents[1]
CONDITIONS={'off':Options(), 'cluster':Options(pose_reporting=CLUSTER,pose_continuity=REP105),
            'innovation':Options(correction_gate=MAHALANOBIS,pose_continuity=REP105)}
dump=base.dump


def bundle(seed,condition,source):
    b=base.bundle(seed,'off',source)
    b.update(execution_bundle_id=f'egojump-{seed}-{condition}-v2',
             comparison='same fresh seed/Scene/schedule, registered pose toggles only')
    b['options'].update(asdict(CONDITIONS[condition]))
    return b


def run(args):
    condition=args.condition
    b=bundle(args.seed,condition,ROOT.name)
    def schedule(c):
        return install(base.install_fresh_schedule(c),CONDITIONS[condition])
    # Keep both older RGB/covariance toggles OFF in every condition.
    a=SimpleNamespace(**{**vars(args),'condition':'off'})
    result=bind(base.run,bundle=lambda *a:b,install_fresh_schedule=schedule)(a)
    result.update(condition=condition,pose_options=asdict(CONDITIONS[condition]))
    dump(args.output/'result.json',result)
    return result


def score(folder):
    record=base.score(folder)
    own,_=lines(folder/'own-controller.jsonl')
    truth,_=lines(folder/'eval_only/trajectory.jsonl')
    by_t={round(x['t'],6):x for x in truth}
    first=truth[0]; origin=np.asarray(first['robot_xyz_m'][:2]); angle=first['robot_yaw_rad']
    R=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
    poses=[r['local_pose'] for r in own]
    control=[r.get('pose_continuity',{}).get('control_pose',r['local_pose']) for r in own]
    errors=np.asarray(poses)[:,:2]-np.asarray([R.T@(np.asarray(by_t[round(r['t'],6)]['robot_xyz_m'][:2])-origin) for r in own])
    record.update(map_jumps=jump_metrics(poses),control_jumps=jump_metrics(control),
        xy_rmse_m=float(np.sqrt(np.mean(np.sum(errors**2,axis=1)))),final_error_m=float(np.linalg.norm(errors[-1])),
        continuity_trace_frames=sum('pose_continuity' in r for r in own),
        output_sha256=hashlib.sha256((folder/'own-controller.jsonl').read_bytes()).hexdigest())
    return record


def initial_check(folder,elapsed_s,log):
    """Read evaluation ONLY in this external supervisor, never in the policy."""
    def rows(path):
        if not path.exists():return []
        # Last writer row may still be incomplete.
        result=[]
        for raw in path.read_bytes().splitlines():
            try:result.append(json.loads(raw))
            except json.JSONDecodeError:pass
        return result
    own=rows(folder/'own-controller.jsonl');truth=rows(folder/'eval_only/trajectory.jsonl')
    cmds=Counter(('turn' if r['command'].get('turn') else 'translate' if
        r['command'].get('forward') or r['command'].get('left') else 'hold') for r in own)
    displacement=max((math.dist(r['robot_xyz_m'][:2],truth[0]['robot_xyz_m'][:2]) for r in truth),default=0.) if truth else 0.
    yaw_motion=max((abs(math.atan2(math.sin(r['robot_yaw_rad']-truth[0]['robot_yaw_rad']),
                      math.cos(r['robot_yaw_rad']-truth[0]['robot_yaw_rad']))) for r in truth),default=0.) if truth else 0.
    sim_span=own[-1]['t']-own[0]['t'] if len(own)>1 else 0.
    phases=sorted({r.get('stage','unknown') for r in own})
    exception='Traceback (most recent call last)' in log
    issues=[]
    if exception:issues.append('log_exception')
    if len(own)<10 or sim_span<2:issues.append('no_frame_or_sim_progress')
    if displacement<.001 and yaw_motion<.01:issues.append('no_physical_motion')
    # Frozen mapper deliberately turns for at most 20 SIM seconds to acquire
    # its first frontier. Do not label that registered bootstrap as a stall.
    if sim_span>20 and cmds.get('translate',0)==0:issues.append('rotation_or_hold_only')
    report=dict(wall_elapsed_s=elapsed_s,frames=len(own),sim_span_s=sim_span,
        xyz_displacement_m=displacement,yaw_motion_rad=yaw_motion,commands=dict(cmds),stages=phases,
        entered_key_stage=any(v in phases for v in ('approach','return','declared')),
        issues=issues,healthy=not issues,evaluation_used_only_by_supervisor=True)
    dump(folder/'initial-check.json',report)
    return report


def group(args):
    """One seed's OFF + two candidates, admitted and launched together."""
    with base.old.server_slot():
        cpus=[int(x) for x in args.cpus.split(',')]
        if len(cpus)!=3 or len(set(cpus))!=3 or not set(cpus)<=set(range(12)):
            raise ValueError('THREE_DISTINCT_CPUS_0_TO_11_REQUIRED')
        out=args.output;out.mkdir(parents=True,exist_ok=False)
        plan=[];running=[];started=time.monotonic();stop=False
        def interrupt(*_):
            nonlocal stop
            stop=True
        signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
        conditions=list(CONDITIONS) if args.seed%2 else list(reversed(CONDITIONS))
        for condition,cpu in zip(conditions,cpus):
            jobroot=out/f'{args.seed}-{condition}';jobroot.mkdir()
            job=dict(seed=args.seed,condition=condition,cpu=cpu,root=str(jobroot),output=str(jobroot/'data'),status='QUEUED')
            dump(jobroot/'RUN_META.json',dict(schema='ugrp.run-meta.v1',**{'class':'dev'},pr=405,
                branch='codex/ego-pose-continuity',sha=ROOT.name,batch=out.parent.name,
                keep=['data/own-controller.jsonl','data/initial-check.json']))
            plan.append(job)
        dump(out/'batch-plan.json',plan)
        # Parent CLI checked all storage hosts and remaining sibling writes.
        # Recheck instantaneous CPU/memory and reserve this group peak here.
        while os.getloadavg()[0]>=12.8 or base.old.ref.resources()[1]<6:
            if time.monotonic()-started>args.wall_budget_s or stop:
                raise TimeoutError('GROUP_RESOURCE_ADMISSION_TIMEOUT')
            time.sleep(5)
        if shutil.disk_usage(out).free-3*768*2**20<8*2**30:
            raise RuntimeError('HOST_STORAGE_BUDGET_GROUP_REFUSED')
        for j in plan:
            command=['taskset','-c',str(j['cpu']),sys.executable,'-m','scripts.run_ego_pose_continuity',
                '--mode','full','--seed',str(j['seed']),'--condition',j['condition'],'--output',j['output']]
            log=(Path(j['root'])/'process.log').open('x')
            process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            j.update(status='RUNNING',pid=process.pid,started=time.time(),command=command,loadavg=list(os.getloadavg()))
            running.append((j,process,log))
        while running:
            for j,p,log in running.copy():
                elapsed=time.time()-j['started'];folder=Path(j['output'])
                if p.poll() is None and elapsed>=180 and 'initial_check' not in j:
                    j['initial_check']=initial_check(folder,elapsed,(Path(j['root'])/'process.log').read_text())
                    if not j['initial_check']['healthy']:
                        j['interrupted_reason']='INITIAL_CHECK_ABNORMAL'
                        p.send_signal(signal.SIGALRM);j['signal_time']=time.monotonic()
                if (stop or time.monotonic()-started>=args.wall_budget_s) and p.poll() is None and 'signal_time' not in j:
                    j['interrupted_reason']='FINITE_GROUP_BUDGET';p.send_signal(signal.SIGALRM);j['signal_time']=time.monotonic()
                if 'signal_time' in j and time.monotonic()-j['signal_time']>60 and p.poll() is None:
                    os.killpg(p.pid,signal.SIGKILL)
                if p.poll() is None:continue
                log.close();j['exit_code']=p.returncode
                (Path(j['root'])/'EXIT').write_text(str(p.returncode)+'\n')
                r=base.old.read_result(folder);j['status']=r.get('status','HOST_ERROR_NO_RESULT')
                if 'initial_check' not in j and folder.exists():
                    j['initial_check']=initial_check(folder,elapsed,(Path(j['root'])/'process.log').read_text())
                if r.get('start_sim_s') is not None:
                    try:j['score']=score(folder)
                    except Exception as exc:j['scoring_error']=repr(exc)
                j['result']=r
                dump(Path(j['root'])/'summary.json',j)
                running.remove((j,p,log))
            dump(out/'batch-status.json',plan)
            time.sleep(2) if running else None
        dump(out/'summary.json',dict(registered=3,runs=plan,source_sha=ROOT.name,
            complete=sum(j['status']=='RECORDED' for j in plan),initial_checks=[j.get('initial_check') for j in plan]))
        return 0 if all(j['status']=='RECORDED' for j in plan) else 2


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('full','group'),required=True)
    p.add_argument('--seed',type=int,choices=base.SEEDS,required=True)
    p.add_argument('--condition',choices=CONDITIONS,default='off');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cpus',default='0,1,2');p.add_argument('--wall-budget-s',type=int,default=5400)
    a=p.parse_args()
    if not 1<=a.wall_budget_s<=7200:p.error('finite group budget <=7200 required')
    if a.mode=='group':return group(a)
    r=run(a);print(json.dumps(r),flush=True)
    return 0 if r['status']=='RECORDED' else 1


if __name__=='__main__':raise SystemExit(main())
