"""Fixed saved own RGB/issued-command replay, never physics or provider calls.

Truth is loaded only by evaluate() after every controller output is finalized.
This measures a 60 SIM-second input window, not closed-loop task success.
"""
import argparse
import base64
import cProfile
from dataclasses import asdict
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

import cv2
import numpy as np

from harness.e2e_speed4 import Options, processing_due

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = dict(baseline={}, pixels={'render_half': True},
    map_budget={'rbpf_particles':50,'floor_ray_stride':2},
    moving={'moving_observation_stride':2}, vector={'vector_envelopes':True,'vector_door_pairs':True},
    combined={'render_half':True,'rbpf_particles':50,'floor_ray_stride':2,
              'moving_observation_stride':2,'vector_envelopes':True,'vector_door_pairs':True})


def read_rows(path):
    path = Path(path)
    data = (path.read_bytes() if path.exists() else
            subprocess.check_output(['zstd','-dc',str(path)+'.zst']))
    return [json.loads(line) for line in data.splitlines() if line]


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')


def resize_compat(rgb):
    return cv2.resize(cv2.resize(rgb,(320,240),interpolation=cv2.INTER_AREA),
                      (640,480),interpolation=cv2.INTER_LINEAR)


@lru_cache(maxsize=1)
def install_exact():
    from harness.controller_exact_speedups import install
    return install()


def build(options):
    from harness.e2e_live_mapping import Robot
    from harness.e2e_exact_speedups import Options as Exact
    from harness.e2e_stall_odometry import Options as Stall
    from harness.s4_event_policy import Options as Study
    install_exact()
    cov = json.loads((ROOT/'configs/e2e_nees_egomap70_dev_v1.json').read_text())
    exact = Exact(**{k:True for k in asdict(Exact())})
    return {rid:Robot(rid,61001+i,cov,Study(True,True,'en'),
        relook='on_v1',goal_geometry='e2e_b80_v1',exploration_progress='frontier_progress_v1',
        pose_fix='innovation',path_follow='rpp_v1',mapping_budget_s=1800.,
        stall_options=Stall('rgb_pulse_gate_v1','backup_replan_v1','amcl_alpha_v1'),
        exact_speedups=exact,speed4=options) for i,rid in enumerate(('r1','r2','r3'))}


def replay(raw, out, name, limit=300, functional_only=False):
    out.mkdir(parents=True,exist_ok=False)
    options=Options(**CANDIDATES[name]);robots=build(options)
    frames={r:read_rows(raw/f'robots/{r}/frames.jsonl')[:limit] for r in robots}
    commands={r:read_rows(raw/f'robots/{r}/commands.jsonl') for r in robots}
    origin=min(rows[0]['sim_time'] for rows in frames.values())
    cursor={r:0 for r in robots};rows=[];inputs=[];skips=0;stopped=set()
    prof=cProfile.Profile();wall=time.perf_counter();receive_s=0.
    for k in range(max(map(len,frames.values()))):
        for rid,robot in robots.items():
            if rid in stopped or k>=len(frames[rid]):continue
            frame=frames[rid][k];now=round(frame['sim_time']-origin,8)
            # At t=0 servo commands precede capture; movement at the same time
            # follows capture, so apply strict earlier commands for later frames.
            while cursor[rid]<len(commands[rid]):
                cmd=commands[rid][cursor[rid]]
                initial=cmd['kind'] in ('initial_servo_command','arm','look') and cmd['t']<=origin+1e-8
                if cmd['t']>=frame['sim_time']-1e-8 and not initial:break
                cursor[rid]+=1
                action={key:v for key,v in cmd.items() if key!='t'}
                if action['kind']=='initial_servo_command':continue
                robot.commanded(action,max(0.,round(cmd['t']-origin,8)))
            if not processing_due(robot,now,'mapping'):
                skips+=1;continue
            path=raw/frame['path'];jpeg=path.read_bytes()
            digest=hashlib.sha256(jpeg).hexdigest()
            if digest!=frame['sha256']:raise ValueError('INPUT_SHA_MISMATCH:'+str(path))
            rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_COLOR),cv2.COLOR_BGR2RGB)
            if options.render_half:
                rgb=resize_compat(rgb)
                jpeg=cv2.imencode('.jpg',cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,82])[1].tobytes()
                rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_COLOR),cv2.COLOR_BGR2RGB)
            obs=dict(frame_id=frame['frame_id'],sim_time=now,sha256=hashlib.sha256(jpeg).hexdigest(),
                     image=base64.b64encode(jpeg).decode())
            inputs.append(dict(robot=rid,frame=frame['frame_id'],path=frame['path'],
                               source_sha256=digest,input_sha256=obs['sha256']))
            started=time.perf_counter()
            if not functional_only:prof.enable()
            error=None
            try:robot.receive(obs,rgb)
            except Exception as exc:error=type(exc).__name__+':'+str(exc)
            finally:prof.disable()
            elapsed=time.perf_counter()-started;receive_s+=elapsed
            rows.append(dict(robot=rid,t=now,frame=frame['frame_id'],error=error,receive_s=elapsed,
                             pose=robot.goal.explorer.local_pose.tolist(),command=robot.nav_command,
                             wall_segments=len(robot.wall_segments)))
            if error:stopped.add(rid)
        if k%25==0:
            print(json.dumps(dict(candidate=name,frame=k+1,t=now,receives=len(rows),skips=skips)),flush=True)
    if not functional_only:prof.dump_stats(str(out/'receive.pstats'))
    if functional_only:
        for row in rows:row.pop('receive_s',None)
    write(out/'rows.json',rows);write(out/'inputs.json',inputs)
    result=dict(candidate=name,options=asdict(options),receives=len(rows),skips=skips,
                sim_window_s=max(r['t'] for r in rows)+.2,receive_s=None if functional_only else receive_s,
                wall_s=None if functional_only else time.perf_counter()-wall,loadavg=os.getloadavg(),errors=sum(r['error'] is not None for r in rows),
                source=str(raw),scope='fixed recorded commands and RGB, no physics/model')
    write(out/'summary.json',result)
    return result


def evaluate(raw, out):
    """Post hoc only: own-start SE(2) is anchored to initial evaluation pose."""
    rows=json.loads((out/'rows.json').read_text());errors=[]
    for rid in ('r1','r2','r3'):
        truth=read_rows(raw/f'eval_only/{rid}/trajectory.jsonl')
        first=truth[0];base=np.asarray(first['robot_xyz_m'][:2]);yaw=first['robot_yaw_rad']
        c,s=math.cos(yaw),math.sin(yaw);R=np.array([[c,s],[-s,c]])
        for row in rows:
            if row['robot']!=rid:continue
            nearest=min(truth,key=lambda x:abs(x['t']-first['t']-row['t']))
            if abs(nearest['t']-first['t']-row['t'])>.026:raise ValueError('EVAL_TIME_JOIN')
            xy=R@(np.asarray(nearest['robot_xyz_m'][:2])-base)
            dyaw=row['pose'][2]-(nearest['robot_yaw_rad']-yaw)
            errors.append(dict(robot=rid,t=row['t'],xy_m=float(np.linalg.norm(np.asarray(row['pose'][:2])-xy)),
                               yaw_rad=abs(math.atan2(math.sin(dyaw),math.cos(dyaw)))))
    result={rid:dict(n=sum(e['robot']==rid for e in errors),
        xy_rmse_m=float(np.sqrt(np.mean([e['xy_m']**2 for e in errors if e['robot']==rid]))),
        yaw_rmse_rad=float(np.sqrt(np.mean([e['yaw_rad']**2 for e in errors if e['robot']==rid]))))
        for rid in ('r1','r2','r3')}
    write(out/'evaluation.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--candidates',nargs='+',choices=CANDIDATES,default=list(CANDIDATES))
    p.add_argument('--frames',type=int,default=300)
    p.add_argument('--functional-only',action='store_true',help='No speed measurement or cProfile')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    results=[]
    for name in a.candidates:
        try:
            result=replay(a.raw,a.output/name,name,a.frames,a.functional_only)
            result['evaluation']=evaluate(a.raw,a.output/name)
        except Exception as exc:
            result=dict(candidate=name,status='HOST_ERROR',error=type(exc).__name__+':'+str(exc))
        results.append(result);write(a.output/'summary.json',results)
    print(json.dumps(results),flush=True)


if __name__=='__main__':main()
