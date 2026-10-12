"""Task-specific orchestration of existing azctl/remote_run APIs on a shared VM.

Reuse a live VM without azctl.start's boot recovery sweep over other active jobs.
Source shipping, lite fetch and SSH use the requested azure-sim remote_run module.
Never stop a VM with another lease/unarchived run; own budget includes archival.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--worktree',type=Path,required=True)
    p.add_argument('--runner-root',type=Path,required=True)
    p.add_argument('--name',required=True)
    p.add_argument('--offline-replay',action='store_true',help='Bounded historical RGB replay, no simulation')
    args=p.parse_args()
    if not args.name.replace('-','').isalnum(): raise ValueError('unsafe name')
    sys.path.insert(0,str(args.runner_root))
    from scripts import remote_run as remote
    from scripts.azure_api import SUB, RG, VM
    if not SUB.startswith('88b7ee7f-'): raise ValueError('wrong subscription')
    view=json.loads(subprocess.check_output(['az','vm','get-instance-view','--subscription',SUB,'-g',RG,'-n',VM,'--query','instanceView.statuses','-o','json']))
    if not any(s['code']=='PowerState/running' for s in view):
        subprocess.run([sys.executable,str(args.runner_root/'scripts/azctl.py'),'start'],check=True)
    # Never ship worktree bytes: remote.ship sends exactly this Git object tree.
    if subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=args.worktree).strip():
        raise RuntimeError('uncommitted tracked source')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.worktree,text=True).strip()
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=args.worktree,text=True).strip()
    name=args.name; root=f'$HOME/ugrp-sim/runs/{name}';lease=f'$HOME/ugrp-sim/leases/{name}'
    remote.ssh('azure','python3 /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py admit')
    remote.ssh('azure',f'mkdir -p ~/ugrp-sim/leases; test ! -e {root} && touch {lease}')
    started=time.monotonic();archived=False
    evidence=args.worktree/'experiments/2026-10-11-egomap-reconfirmation'
    local=Path('/Users/changmin/projects/ugrp/outputs/egomap71-orchestration')
    local.mkdir(exist_ok=True)
    def ssh(command):
        return remote.ssh('azure',command,capture_output=True,text=True).stdout.strip()
    try:
        for host,alias,path,mb in [('x86','azure','~/ugrp-sim/runs',8000),('arm','oracle-codex','~/ugrp-archive/runs',8000),('mac',None,str(local),256)]:
            command=[sys.executable,str(args.runner_root/'scripts/storage_budget.py'),'--host',host,'--path',path,'--runs','1','--per-run-mb',str(mb)]
            if alias:command+=['--ssh',alias]
            subprocess.run(command,check=True)
        helpers=ssh('sha256sum /usr/local/lib/ugrp-storage/scripts/remote_run_finish.py /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py')
        resources=ssh('nproc; cat /proc/loadavg; df -B1 ~/ugrp-sim/runs; ls -l ~/ugrp-sim/leases')
        metadata={'class':'dev','pr':405,'branch':branch,'sha':sha,'batch':name,'vm_task_limit_s':7200,
                  'batch_limit_s':300 if args.offline_replay else 5400,'runner':'azure-sim/scripts/remote_run.py APIs + existing live VM',
                  'mode':'historical_rgb_replay' if args.offline_replay else 'paired_simulation',
                  'runner_sha256':hashlib.sha256((args.runner_root/'scripts/remote_run.py').read_bytes()).hexdigest(),
                  'installed_helpers_sha256':helpers,'resources_before':resources,'model_calls':0}
        (local/(name+'-submission.json')).write_text(json.dumps(metadata,indent=2)+'\n')
        remote.ship('azure',args.worktree,sha)
        command=['env','UGRP_EXECUTION_HOST=azure','MUJOCO_GL=osmesa','OMP_NUM_THREADS=1','OPENBLAS_NUM_THREADS=1','LP_NUM_THREADS=1',
                 'timeout','-s','INT','-k','60','5500','.venv-sim/bin/python','-m','scripts.sim_cli','workflow','run',
                 'egomap-reconfirmation-dev','--timeout','5450','--','--mode','batch','--workers','3','--wall-budget-s','5400',
                 '--output',f'/home/ugrp/ugrp-sim/runs/{name}/data']
        if args.offline_replay:
            command=['env','OMP_NUM_THREADS=1','OPENBLAS_NUM_THREADS=1',
                     'timeout','-s','INT','-k','15','300','.venv-sim/bin/python',
                     'experiments/2026-10-11-egomap-reconfirmation/code/replay_rgb_gate.py',
                     '--archive','/home/ugrp/ugrp-sim/arm','--source-root',f'/home/ugrp/ugrp-sim/src/{sha}',
                     '--output',f'/home/ugrp/ugrp-sim/runs/{name}/data/summary.json']
        line=shlex.join(command)
        script=f'''#!/bin/bash
set -eu
cd "$HOME/ugrp-sim/src/{sha}"
mkdir -p outputs
ln -s "$HOME/ugrp-sim/runs/{name}" "outputs/{name}"
exec python3 /usr/local/lib/ugrp-storage/scripts/remote_run_finish.py --source "$PWD" --run "$HOME/ugrp-sim/runs/{name}" -- {line}
'''
        ssh(f'mkdir {root} && printf %s {shlex.quote(json.dumps(metadata))} > {root}/RUN_META.json && '
            f'printf %s {sha} > {root}/SOURCE_SHA && printf %s {shlex.quote(line)} > {root}/COMMAND && '
            f'printf %s {shlex.quote(script)} > {root}/run_wrapper.sh && cat /proc/loadavg > {root}/LOADAVG && '
            f'setsid -f bash {root}/run_wrapper.sh </dev/null >/dev/null 2>&1')
        print(f'STARTED {name} {sha}',flush=True)
        last=''
        while time.monotonic()-started<(480 if args.offline_replay else 5700):
            state=ssh(f'touch {lease}; test ! -f {root}/EXIT || cat {root}/EXIT')
            status=ssh(f'test ! -f {root}/data/batch-status.json || python3 -c '+shlex.quote(
                'import json,collections;from pathlib import Path;p=Path.home()/"ugrp-sim/runs/'+name+'/data/batch-status.json";print(dict(collections.Counter(x["status"] for x in json.loads(p.read_text()))))'))
            if status!=last:print('STATUS',status,flush=True);last=status
            if state:break
            time.sleep(30)
        else:
            raise RuntimeError('own command deadline not observed; persistent raw and lease retained')
        print('EXIT',state,'FETCH',remote.fetch('azure',name),flush=True)
        # Archive only our ended batch immediately with the lifecycle's full
        # inventory/hash verifier; never sweep or signal e2e/s3 work.
        ssh(f'touch {lease}; python3 /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py archive-one --run {name}')
        marker=json.loads(ssh(f'cat $HOME/ugrp-sim/lifecycle/archives/{name}.json'))
        if marker.get('verified') is not True:raise RuntimeError('ARM archive unverified')
        archived=True
        (local/(name+'-archive.json')).write_text(json.dumps(marker,indent=2)+'\n')
        print('ARCHIVED',marker['path'],'FETCH',remote.fetch('azure',name),flush=True)
    finally:
        if archived:
            ssh(f'rm -f {lease}')
        else:
            ssh(f'touch {lease}')
        # Existing azctl refuses other live leases and unarchived evidence.
        subprocess.run([sys.executable,str(args.runner_root/'scripts/azctl.py'),'stop'],check=True)
        print('TASK_ELAPSED_SECONDS',round(time.monotonic()-started,2),flush=True)


if __name__=='__main__':main()
