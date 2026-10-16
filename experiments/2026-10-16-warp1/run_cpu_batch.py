"""Finite CPU baseline orchestrator; run only on gcp2, never Mac physics."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True);p.add_argument('--teacher-source',type=Path,required=True)
    p.add_argument('--python',required=True);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--count',type=int,default=16)
    p.add_argument('--cap-s',type=float,default=4.);p.add_argument('--episode',type=int,default=0)
    a=p.parse_args()
    import platform
    if platform.system()!='Linux':p.error('Linux gcp2 only')
    import sys
    sys.path.insert(0,str(a.source/'scripts'))
    from simalt_host import gcp2_identity
    if gcp2_identity()['instance']!='ugrp-sim-gcp2':p.error('n4 gcp2 required')
    if a.count not in (1,16) or not 0<a.cap_s<=60:p.error('bounded requested workload required')
    a.out.mkdir(parents=True,exist_ok=False)
    children=[];start=time.perf_counter()
    env={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
    try:
        for i in range(a.count):
            out=a.out/f'worker-{i:02d}';log=(a.out/f'worker-{i:02d}.log').open('x')
            cmd=[a.python,'-u',str(a.source/'scripts/run_warp_act_teacher.py'),
                 '--physics-backend','c_pilot_v1','--teacher-source',str(a.teacher_source),
                 '--plan',str(a.plan),'--episode',str(a.episode),'--out',str(out),
                 '--cap-s',str(a.cap_s),'--vm-hourly-usd','3.145']
            child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
            children.append((child,log,out,cmd))
        # This is a resource watchdog only, not a planning or teacher time budget.
        for child,log,out,cmd in children:child.wait(timeout=max(1,1800-(time.perf_counter()-start)))
    finally:
        for child,log,out,cmd in children:
            if child.poll() is None:os.killpg(child.pid,signal.SIGINT)
        for child,log,out,cmd in children:
            if child.poll() is None:child.wait(timeout=30)
            log.close()
        elapsed=time.perf_counter()-start
        rows=[]
        for child,log,out,cmd in children:
            file=out/'summary.json'
            rows.append({'exit_code':child.returncode,'raw':str(out),'command':cmd,
                'summary':json.loads(file.read_text()) if file.exists() else {'status':'HOST_ERROR','error':'missing summary'}})
        completed=[r['summary'] for r in rows if r['summary']['status']=='complete']
        sim=sum(r['aggregate_completed_sim_s'] for r in completed)
        report=dict(backend='C MuJoCo3.12 frozen teacher on n4-highcpu-64',n=a.count,cap_s=a.cap_s,
            elapsed_s=elapsed,vm_hourly_usd=3.145,cost_estimate_usd=elapsed*3.145/3600,
            aggregate_sim_s=sim,cold_sim_s_per_wall_s=sim/elapsed,
            cold_sim_s_per_usd=sim/(elapsed*3.145/3600),completed=len(completed),
            HOST_ERROR=a.count-len(completed),cap_end=sum(r.get('cap_end',0) for r in completed),
            scope='same live teacher + native RGB; cap_end is prefix timing, not teacher-success failure',rows=rows)
        (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))


if __name__=='__main__':main()
