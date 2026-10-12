"""Bounded E2E mapping CPU/physics profile with no model or dialogue claim.

Uses the live bundle builder, standard Scene/backend and Robot.receive. The
live provider-dependent E2E entry remains unchanged. This diagnostic has no
transport, dialogue or E2E acceptance result and registers no execution bundle.
"""
import argparse
import cProfile
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time
import traceback

from scripts.replay_e2e_speed4 import build, write
from harness.e2e_speed4 import Options, processing_due, record

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--speed4',type=json.loads,default={})
    a=p.parse_args()
    if platform.system()!='Linux' or platform.machine()!='x86_64' or os.environ.get('MUJOCO_GL')!='osmesa':
        raise ValueError('AZURE_X86_OSMESA_ONLY')
    if not a.output.resolve().is_relative_to(Path.home()/'ugrp-sim/runs'):
        raise ValueError('PERSISTENT_RUN_REQUIRED')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if sha!=a.expected_source_sha:raise ValueError('COMMITTED_SOURCE_REQUIRED')
    opt=Options(**a.speed4)
    from scripts.run_e2e_ownmap_live import bundle
    from harness.s4_event_policy import Options as Study
    from harness.e2e_exact_speedups import Options as Exact
    from harness.e2e_runtime_registration import require_current
    from sim.e2e_ownmap_live import PhysicsBackend
    b=bundle(sha,61001,'study_gemma4_31b_v1',enabled=True,dev_light=True,
        relook='on_v1',options=Study(True,True,'en'),exploration_progress='frontier_progress_v1',
        pose_fix='innovation',path_follow='rpp_v1',mapping_budget='case_cap_v1',
        stall_odometry='rgb_pulse_gate_v1',stall_recovery='backup_replan_v1',stall_noise='amcl_alpha_v1',
        runtime_registration='reviewed_v1',exact_speedups={k:True for k in vars(Exact())},speed4=a.speed4)
    require_current(b,ROOT)
    for name,digest in b['source_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('SOURCE_HASH_MISMATCH:'+name)
    a.output.mkdir(parents=True,exist_ok=False)
    write(a.output/'bundle.json',b);write(a.output/'speed4.json',record(opt))
    result=dict(status='HOST_ERROR',scope='60 SIM s mapping diagnostic; not live E2E or transport',
                source_sha=sha,seed=61001,model_calls=0,E2E_success=False,sim_s=0.,frames=0,
                loadavg_start=os.getloadavg(),options=vars(opt),initial_check=None)
    prof=cProfile.Profile();backend=None;start=time.perf_counter();cpu=time.process_time();origin=None
    try:
        robots=build(opt,install_controller=False)
        backend=PhysicsBackend(b,a.output,seed=61001);backend.reset(b['reset_cap_s'])
        origin=backend.now;backend.set_deadline(origin+60.)
        from harness.active_camera import SEARCH
        for rid,robot in robots.items():
            for sid,pwm in SEARCH.items():
                action=dict(kind='look',pan_pulse=pwm) if sid==6 else dict(kind='arm',servo_id=sid,pulse=pwm)
                backend.issue(rid,action);robot.commanded(action,0.)
        prof.enable()
        for tick in range(1200):
            now=round(backend.now-origin,8)
            if time.perf_counter()-start>1200:raise TimeoutError('PROFILE_WALL_CAP')
            backend.eval_sample()
            if tick%4==0:
                raw=backend.capture()
                for rid,robot in robots.items():
                    if not processing_due(robot,now,'mapping'):continue
                    obs,rgb=raw[rid]
                    own={k:obs[k] for k in ('frame_id','sim_time','sha256','image')};own['sim_time']=now
                    trace=robot.receive(own,rgb)
                    backend._append(f'robots/{rid}/ownmap.jsonl',dict(t=now,frame_id=obs['frame_id'],
                        pose=robot.goal.explorer.local_pose.tolist(),command=robot.nav_command,status=trace.get('status')))
                result['frames']+=1
                for rid in ('r1','r2'):
                    backend.issue(rid,robots[rid].nav_command);robots[rid].commanded(robots[rid].nav_command,now)
            if tick%20==0:
                progress=dict(sim_s=now,wall_s=time.perf_counter()-start,frames=result['frames'],phase='mapping',
                    robots={rid:dict(pose=r.goal.explorer.local_pose.tolist(),command=r.nav_command,
                                    translation_commands=r.translation_commands) for rid,r in robots.items()})
                write(a.output/'progress.json',progress);backend.flush()
                if now>=10 and result['initial_check'] is None:
                    result['initial_check']=progress;write(a.output/'initial-check.json',progress)
                print(json.dumps(progress),flush=True)
            backend.advance_to(origin+(tick+1)*.05)
        result['status']='PROFILE_COMPLETE'
    except BaseException as exc:
        result.update(error=type(exc).__name__+':'+str(exc),traceback=traceback.format_exc())
    finally:
        prof.disable();prof.dump_stats(str(a.output.parent/'cprofile.pstats'))
        if backend is not None:
            result['sim_s']=round(backend.now-origin,8) if origin is not None else 0.
            backend.close()
        result.update(wall_s=time.perf_counter()-start,cpu_s=time.process_time()-cpu,loadavg_end=os.getloadavg())
        write(a.output/'summary.json',result)
    print(json.dumps(result),flush=True)
    return int(result['status']!='PROFILE_COMPLETE')


if __name__=='__main__':raise SystemExit(main())
