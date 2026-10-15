"""Reconcile external VM stop; preserve every partial artifact, no overwrite.

Completed rollouts only repeat missing offline inference. Interrupted rollouts
get fresh retry paths and remain separate HOST_ERROR attempts in the ledger.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import subprocess

from harness.grasp_act_data import read_json,write_json,sha256
from scripts.analyze_grasp_act_act16a import require_cpu


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);a=p.parse_args();host=require_cpu()
    a.output.mkdir(parents=True,exist_ok=False)
    queue=read_json(a.batch/'queue.json');old=read_json(a.batch/'progress.json')['runs']
    ready={r['seed']:r for r in old if r['status']=='complete'}
    todo=[];interrupted=[]
    for job in queue['runs']:
        if job['seed'] in ready:continue
        job={**job,'rollout':job['rollout'].copy(),'offline':job['offline'].copy()}
        raw=Path(job['raw']);s=read_json(raw/'summary.json') if (raw/'summary.json').exists() else None
        complete=bool(s and s.get('complete') and s.get('status')=='complete')
        interrupted.append(dict(seed=job['seed'],raw=str(raw),last_saved_status=s.get('status') if s else 'not_started',
            classification='inference_interrupted' if complete else 'HOST_ERROR_external_VM_stop',
            rollout_complete=complete,first_batch_progress_entry=next((r for r in old if r['seed']==job['seed']),None),
            partial_files_sha256={str(f.relative_to(raw)):sha256(f) for f in raw.rglob('*') if f.is_file()}))
        if not complete:
            target=raw.parent.with_name(raw.parent.name+'-retry1')/'raw'
            job['rollout'][job['rollout'].index('--output')+1]=str(target)
            job['offline'][job['offline'].index('--run')+1]=str(target)
            job['raw']=str(target)
        job['offline'][-1]=str(a.output/f'offline-{job["seed"]}')
        job['resume_rollout_required']=not complete;todo.append(job)
    write_json(a.output/'interrupted-attempts.json',dict(host=host,reason='Mac CLI stop invocation6dbb229fb87045b795cfb48f002dd9d6; not budget function',
        first_batch=str(a.batch),completed_before_stop=len(ready),affected=interrupted))
    write_json(a.output/'queue.json',dict(host=host,rejection_table=queue['rejection_table'],
        training_authorized=False,pooling_with_gcp1=False,max_parallel=16,runs=todo))
    env={**os.environ,'MUJOCO_GL':'osmesa','PYOPENGL_PLATFORM':'osmesa',
         **{k:'1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','LP_NUM_THREADS')}}
    def run(job):
        record={**job}
        for phase in (['rollout','offline'] if job['resume_rollout_required'] else ['offline']):
            log=a.output/f'{phase}-{job["seed"]}.log'
            with log.open('x') as f:
                r=subprocess.run(job[phase],cwd=a.source,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=8*3600)
            record[phase+'_returncode']=r.returncode
            if r.returncode:return {**record,'status':'HOST_ERROR','failed_phase':phase}
        return {**record,'status':'complete'}
    with ThreadPoolExecutor(max_workers=16) as pool:
        for future in as_completed([pool.submit(run,j) for j in todo]):
            record=future.result();ready[record['seed']]=record
            write_json(a.output/'progress.json',dict(finished=len(ready),requested=40,runs=list(ready.values())))
            print(record['seed'],record['status'],'finished',len(ready),flush=True)
    write_json(a.output/'batch-summary.json',dict(host=host,all_jobs_finished=True,
        complete=len(ready)==40 and all(r['status']=='complete' for r in ready.values()),results=list(ready.values()),
        interrupted_attempts=str(a.output/'interrupted-attempts.json'),training_runs=0,optimizer_steps=0))


if __name__=='__main__':main()
