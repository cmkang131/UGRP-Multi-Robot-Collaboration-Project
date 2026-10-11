"""Own finite lease; committed source; group budgets; immediate ARM archive.

Uses remote_run.ship/ssh on an already running VM. Never starts or stops a VM.
Run separately from the frozen worker source; all data is under persistent runs.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys
import threading
import time


def measured_terminal(job):
    """A measured physical failure is an outcome, not a host admission error."""
    return (job.get('status') in ('RECORDED','PHYSICAL_FAILURE')
            and bool(job.get('score')) and not job.get('scoring_error')
            and not job.get('interrupted_reason'))


def main():
    p=argparse.ArgumentParser();p.add_argument('--worktree',type=Path,required=True)
    p.add_argument('--runner-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker-sha',help='reuse an explicitly frozen committed worker source')
    p.add_argument('--attempt',type=int,default=1,help='new output suffix; never overwrite prior failures')
    p.add_argument('--seeds',default='63001,63002,63003,63004,63005,63006')
    p.add_argument('--cpus',default='1,2,3',help='three distinct worker CPUs within 0..11')
    p.add_argument('--resume-existing',action='store_true',help='attach to exact own existing group without resubmission')
    p.add_argument('--task-budget-s',type=int,default=10800);a=p.parse_args()
    if not 600<=a.task_budget_s<=21600:raise ValueError('FINITE_TASK_BUDGET_REQUIRED')
    seeds=[int(s) for s in a.seeds.split(',')];cpus=[int(c) for c in a.cpus.split(',')]
    if not seeds or len(set(seeds))!=len(seeds) or not set(seeds)<=set(range(63001,63007)):
        raise ValueError('REGISTERED_UNIQUE_SEEDS_REQUIRED')
    if len(cpus)!=3 or len(set(cpus))!=3 or not set(cpus)<=set(range(12)):
        raise ValueError('THREE_DISTINCT_CPUS_0_TO_11_REQUIRED')
    spec=importlib.util.spec_from_file_location('ego_remote',a.runner_root/'scripts/remote_run.py')
    remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)
    launcher_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.worktree,text=True).strip()
    sha=subprocess.check_output(['git','rev-parse',a.worker_sha or 'HEAD'],cwd=a.worktree,text=True).strip()
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('EXACT_WORKER_COMMIT_REQUIRED')
    if subprocess.check_output(['git','status','--porcelain'],cwd=a.worktree).strip():
        raise ValueError('COMMITTED_CLEAN_SOURCE_REQUIRED')
    a.output.mkdir(parents=True,exist_ok=False)
    lease=f'$HOME/ugrp-sim/leases/egojump-{sha[:8]}'
    def ssh(cmd,timeout=120):
        return remote.ssh('azure',cmd,capture_output=True,text=True,timeout=timeout).stdout.strip()
    def save(name,data):
        (a.output/name).write_text(json.dumps(data,indent=2)+'\n')
    def budget(seed,shipping=False):
        reports=[]
        for host,alias,path,runs,mb,reserved in (
            ('x86','azure','~/ugrp-sim/runs',3,768,2560 if shipping else 1024),
            ('arm','oracle-codex','~/ugrp-archive/runs',3,768,1024),
            ('mac',None,str(a.output),3,5,128)):
            command=[sys.executable,str(a.runner_root/'scripts/storage_budget.py'),'--host',host,
                     '--path',path,'--runs',str(runs),'--per-run-mb',str(mb),'--reserved-mb',str(reserved)]
            if alias:command+=['--ssh',alias]
            r=subprocess.run(command,capture_output=True,text=True)
            reports.append(dict(host=host,exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr))
        save(f'budget-{seed}.json',reports)
        if any(r['exit_code'] for r in reports):raise RuntimeError('STORAGE_BUDGET_REFUSED')
    # Successful SSH is the only VM-state check. No start/stop API is called.
    ssh('python3 /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py admit')
    already_shipped=ssh(f'test ! -f ~/ugrp-sim/src/{sha}/.git/ugrp-source-complete || cat ~/ugrp-sim/src/{sha}/.git/ugrp-source-complete')==sha
    budget('source',shipping=not already_shipped)
    save('source.json',dict(worker_sha=sha,launcher_sha=launcher_sha,reused_source=already_shipped,seeds=seeds,cpus=cpus))
    ssh(f'mkdir -p ~/ugrp-sim/leases; test ! -e {lease}; touch {lease}')
    started=time.monotonic();stop=threading.Event();records=[]
    def heartbeat():
        while not stop.wait(25) and time.monotonic()-started<a.task_budget_s:
            try:ssh(f'touch {lease}',timeout=20)
            except Exception as e:print('HEARTBEAT',type(e).__name__,flush=True)
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    pending=[]
    try:
        remote.ship('azure',a.worktree,sha)
        # XML/hash admission catches missing sparse runtime assets without
        # constructing MuJoCo or submitting a whole failed group.
        check='from scripts.run_ego_pose_continuity import bundle; from sim.goal_route_assets import xml_preflight; [xml_preflight(bundle(s,"off","'+sha+'"),s) for s in range(63001,63007)]; print("ASSET_PREFLIGHT_6_OK")'
        print(ssh(f'cd ~/ugrp-sim/src/{sha} && taskset -c 0-11 .venv-sim/bin/python -c '+shlex.quote(check)),flush=True)
        for seed in seeds:
            remaining=a.task_budget_s-(time.monotonic()-started)
            if remaining<900:raise TimeoutError('TASK_ARCHIVE_RESERVE')
            name=f'egojump-{seed}-{sha[:8]}-r{a.attempt}';root=f'$HOME/ugrp-sim/runs/{name}'
            exists=ssh(f'test ! -d {root} || cat {root}/SOURCE_SHA')
            attach=a.resume_existing and exists==sha
            if exists and not attach:raise RuntimeError('EXISTING_RUN_REQUIRES_EXPLICIT_RESUME')
            if not attach:budget(seed)
            wall=min(5400,int(remaining-900))
            command=['systemd-run','--user','--scope','--quiet','--unit='+name,
                '--property=AllowedCPUs=0-11','env','UGRP_EXECUTION_HOST=azure','MUJOCO_GL=osmesa','MPLBACKEND=Agg',
                'OMP_NUM_THREADS=1','OPENBLAS_NUM_THREADS=1','LP_NUM_THREADS=1',
                'timeout','-s','INT','-k','90',str(wall+120),'taskset','-c','0-11','.venv-sim/bin/python','-m','scripts.sim_cli',
                'workflow','run','ego-pose-continuity-dev','--timeout',str(wall+60),'--',
                '--mode','group','--seed',str(seed),'--cpus',a.cpus,'--wall-budget-s',str(wall),
                '--output',f'/home/ugrp/ugrp-sim/runs/{name}/data']
            line=shlex.join(command)
            metadata=dict(schema='ugrp.run-meta.v1',**{'class':'dev'},pr=405,
                branch='codex/ego-pose-continuity',sha=sha,batch=name,cpus=cpus,
                group_wall_budget_s=wall,task_budget_s=a.task_budget_s,
                storage='3 x 768MiB peak plus 1024MiB existing/temporary writes; future groups unadmitted',
                keep=['summary.json','data/summary.json'],model_calls=0)
            script=f'''#!/bin/bash
set -eu
cd "$HOME/ugrp-sim/src/{sha}"
exec python3 /usr/local/lib/ugrp-storage/scripts/remote_run_finish.py --source "$PWD" --run "$HOME/ugrp-sim/runs/{name}" -- {line}
'''
            if not attach:
                ssh(f'test ! -e {root} && mkdir {root} && printf %s {shlex.quote(json.dumps(metadata))} > {root}/RUN_META.json && '
                    f'printf %s {sha} > {root}/SOURCE_SHA && printf %s {shlex.quote(line)} > {root}/COMMAND && '
                    f'printf %s {shlex.quote(script)} > {root}/run_wrapper.sh && cat /proc/loadavg > {root}/LOADAVG && '
                    f'setsid -f bash {root}/run_wrapper.sh </dev/null >{root}/wrapper.log 2>&1')
            pending.append(name);print('ATTACHED' if attach else 'STARTED',name,sha,flush=True)
            previous=None;archived_jobs=set()
            while True:
                state=ssh(f'test ! -f {root}/EXIT || cat {root}/EXIT')
                status=ssh(f'test ! -f {root}/data/batch-status.json || cat {root}/data/batch-status.json')
                if status:
                    rows=json.loads(status)
                    compact=[{k:r.get(k) for k in ('condition','status','initial_check')} for r in rows]
                    if compact!=previous:print('PROGRESS',json.dumps(compact),flush=True);previous=compact
                    for job in rows:
                        if 'exit_code' not in job or job['condition'] in archived_jobs:continue
                        jobname=Path(job['root']).name
                        result=remote.ssh('azure',f'taskset -c 0-11 python3 - {name} {jobname}',
                            input=(a.worktree/'scripts/archive_ego_pose_job.py').read_text(),
                            capture_output=True,text=True,timeout=900)
                        receipt=json.loads(result.stdout.splitlines()[-1])
                        marker_bytes=ssh(f'cat {root}/per-run-archives/{jobname}.json')+'\n'
                        marker=json.loads(marker_bytes)
                        summary_bytes=ssh(f'cat {root}/data/{jobname}/summary.json')+'\n'
                        if hashlib.sha256(summary_bytes.encode()).hexdigest()!=marker['inventory']['summary.json']['sha256']:
                            raise RuntimeError('JOB_FETCH_LITE_HASH_MISMATCH')
                        packed=subprocess.check_output(['zstd','-q','-3'],input=marker_bytes.encode())
                        if subprocess.check_output(['zstd','-qdc'],input=packed)!=marker_bytes.encode():
                            raise RuntimeError('JOB_INVENTORY_ROUNDTRIP')
                        (a.output/(name+'-'+jobname+'-archive.json.zst')).write_bytes(packed)
                        save(name+'-'+jobname+'-summary.json',dict(job=job,archive=receipt))
                        archived_jobs.add(job['condition'])
                        print('CONDITION_ARCHIVED_AND_LITE_VERIFIED',name,job['condition'],flush=True)
                if state:break
                if time.monotonic()-started>a.task_budget_s-600:
                    raise TimeoutError('TASK_DEADLINE_WORKER_HAS_FINITE_TIMEOUT')
                time.sleep(20)
            summary=ssh(f'test ! -f {root}/data/summary.json || cat {root}/data/summary.json')
            record=dict(name=name,exit_code=state,raw=f'azure:/home/ugrp/ugrp-sim/runs/{name}',
                summary=json.loads(summary) if summary else None)
            save(name+'-summary.json',record)
            print('FINISHED',name,'exit',state,flush=True)
            ssh(f'timeout 600 python3 /usr/local/lib/ugrp-storage/scripts/compress_json_traces.py {root} --execute',timeout=650)
            ssh(f'touch {lease}; timeout 900 python3 /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py archive-one --run {name}',timeout=950)
            marker=json.loads(ssh(f'cat $HOME/ugrp-sim/lifecycle/archives/{name}.json',timeout=120))
            if marker.get('verified') is not True:raise RuntimeError('UNVERIFIED_ARM_ARCHIVE')
            # The hash inventory is permanent evidence, compressed for Mac.
            raw=json.dumps(marker,sort_keys=True).encode()
            packed=subprocess.check_output(['zstd','-q','-3'],input=raw)
            if hashlib.sha256(subprocess.check_output(['zstd','-qdc'],input=packed)).digest()!=hashlib.sha256(raw).digest():
                raise RuntimeError('INVENTORY_COMPRESSION_HASH')
            (a.output/(name+'-archive.json.zst')).write_bytes(packed)
            record['archive']={k:v for k,v in marker.items() if k!='inventory'}
            record['archive']['inventory_sha256']=hashlib.sha256(raw).hexdigest()
            # Verify retrieved summary bytes against the remote archive inventory.
            source_bytes=ssh(f'cat {root}/data/summary.json')+'\n' if summary else None
            if source_bytes is not None:
                expected=marker['inventory']['data/summary.json']['sha256']
                if hashlib.sha256(source_bytes.encode()).hexdigest()!=expected:
                    raise RuntimeError('FETCH_LITE_SUMMARY_HASH_MISMATCH')
            records.append(record);pending.remove(name)
            save('summary.json',dict(source_sha=sha,registered=18,groups=records,pending=pending,elapsed_s=time.monotonic()-started))
            print('ARCHIVED_AND_LITE_VERIFIED',name,marker['path'],flush=True)
            if record['summary'] is None or not all(measured_terminal(j) for j in record['summary']['runs']):
                raise RuntimeError('GROUP_FAILED_FIX_BEFORE_NEXT_SEED')
    finally:
        stop.set();thread.join(timeout=25)
        # Never stop the VM. Keep any incomplete archive explicit in local record.
        save('lease-release.json',dict(lease=lease,pending=pending,elapsed_s=time.monotonic()-started,
            vm_start_stop_called=False,source_sha=sha))
        ssh(f'rm -f {lease}')
        print('LEASE_RELEASED',lease,'PENDING',pending,flush=True)


if __name__=='__main__':main()
