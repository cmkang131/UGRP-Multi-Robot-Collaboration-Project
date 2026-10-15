"""Bounded, CPU-only regeneration of missing ACT15 evidence on GCP2.

No training, tuning or cohort pooling. Each job independently retains its raw
rollout, observer-only labels, errors, return codes and offline inference output.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import time

from harness.grasp_act_data import write_json, sha256
from scripts.analyze_grasp_act_act16a import require_cpu


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','scene-source','output','plans','model','sim-python','actor-python','rejection-table'):
        p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--seeds',nargs='+',type=int,required=True)
    p.add_argument('--max-parallel',type=int,default=16)
    a=p.parse_args()
    if not 1<=a.max_parallel<=16:raise ValueError('ACT15 measured CPU concurrency limit 16')
    if not a.rejection_table.is_file():raise FileNotFoundError(a.rejection_table)
    host=require_cpu();a.output.mkdir(parents=True,exist_ok=False)
    env={**os.environ,'MUJOCO_GL':'osmesa','PYOPENGL_PLATFORM':'osmesa',
         **{k:'1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','LP_NUM_THREADS')}}
    source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.source,text=True).strip()
    commands=[]
    for seed in a.seeds:
        plan=(a.source/'experiments/2026-10-15-act-train/act14-plans'/f'{seed}.json') if seed<91500 else a.plans/f'{seed}.json'
        raw=Path('/home/ugrp/ugrp-sim/runs')/f'act16a-gcp2-{seed}-{source[:8]}'/'raw'
        rollout=[str(a.sim_python),'-m','scripts.analyze_grasp_act_act16a','student',
            '--plan',str(plan),'--model',str(a.model),'--scene-source',str(a.scene_source),
            '--actor-python',str(a.actor_python),'--output',str(raw)]
        if seed in (91427,91439):rollout.append('--overview')
        offline=[str(a.actor_python),'-m','scripts.analyze_grasp_act_act16a','offline',
                 '--run',str(raw),'--model',str(a.model),'--output',str(a.output/f'offline-{seed}')]
        commands.append(dict(seed=seed,plan=str(plan),plan_sha256=sha256(plan),raw=str(raw),rollout=rollout,offline=offline))
    queue=dict(schema='ugrp.act16a.analysis_queue.v1',host=host,source_sha=source,
        rejection_table=str(a.rejection_table.resolve()),training_authorized=False,optimizer_steps=0,
        user_authorization='ACT16a analysis request: regenerate missing evaluation evidence on GCP2 CPU only',
        max_parallel=a.max_parallel,global_max_parallel=40,pooling_with_gcp1=False,
        resource_watchdog_s=8*3600,action_selection_cap='90 SIM seconds, unchanged ACT15',runs=commands)
    write_json(a.output/'queue.json',queue)
    results=[]
    def execute(job):
        begin=time.monotonic();record={**job,'status':'running'}
        for phase in ('rollout','offline'):
            log=a.output/f'{phase}-{job["seed"]}.log'
            try:
                with log.open('x') as f:
                    r=subprocess.run(job[phase],cwd=a.source,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=8*3600)
                record[phase+'_returncode']=r.returncode
                record[phase+'_log']=str(log)
                if r.returncode:
                    record.update(status='HOST_ERROR',failed_phase=phase);break
            except Exception as exc:
                record.update(status='HOST_ERROR',failed_phase=phase,error=repr(exc));break
        else:record['status']='complete'
        record['wall_s']=time.monotonic()-begin
        return record
    with ThreadPoolExecutor(max_workers=a.max_parallel) as pool:
        for future in as_completed([pool.submit(execute,j) for j in commands]):
            record=future.result();results.append(record)
            write_json(a.output/'progress.json',{'finished':len(results),'requested':len(commands),'runs':results})
            print(json.dumps({'seed':record['seed'],'status':record['status'],'finished':len(results)},allow_nan=False),flush=True)
    write_json(a.output/'batch-summary.json',{'host':host,'source_sha':source,'all_jobs_finished':True,
        'complete':all(r['status']=='complete' for r in results),'results':results,
        'rejection_table':str(a.rejection_table.resolve()),'training_runs':0,'optimizer_steps':0})


if __name__=='__main__':main()
