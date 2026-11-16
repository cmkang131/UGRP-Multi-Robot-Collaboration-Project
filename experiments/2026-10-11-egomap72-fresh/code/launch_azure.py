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
import threading


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--worktree',type=Path,required=True)
    p.add_argument('--runner-root',type=Path,required=True)
    p.add_argument('--name',required=True)
    p.add_argument('--cpus',default='12,13,14,15')
    p.add_argument('--wall-budget-s',type=int,default=7200)
    p.add_argument('--task-budget-s',type=int,default=9000)
    args=p.parse_args()
    if not 1 <= args.wall_budget_s <= args.task_budget_s-1800 or args.task_budget_s>10800:
        raise ValueError('finite task budget with archival reserve required')
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
    heartbeat_stop=threading.Event()
    def heartbeat():
        while not heartbeat_stop.wait(30) and time.monotonic()-started<args.task_budget_s:
            try:remote.ssh('azure',f'touch {lease}',capture_output=True,timeout=20)
            except Exception as exc:print('LEASE_HEARTBEAT_ERROR',type(exc).__name__,flush=True)
    heartbeat_thread=threading.Thread(target=heartbeat,daemon=True)
    heartbeat_thread.start()
    evidence=args.worktree/'experiments/2026-10-11-egomap72-fresh'
    local=Path('/Users/changmin/projects/ugrp/outputs/egomap72-orchestration')
    local.mkdir(exist_ok=True)
    def ssh(command):
        return remote.ssh('azure',command,capture_output=True,text=True).stdout.strip()
    try:
        for host,alias,path,mb in [('x86','azure','~/ugrp-sim/runs',9216),('arm','oracle-codex','~/ugrp-archive/runs',6144),('mac',None,str(local),128)]:
            command=[sys.executable,str(args.runner_root/'scripts/storage_budget.py'),'--host',host,'--path',path,'--runs','1','--per-run-mb',str(mb)]
            if alias:command+=['--ssh',alias,'--reserved-mb','4096']
            subprocess.run(command,check=True)
        helpers=ssh('sha256sum /usr/local/lib/ugrp-storage/scripts/remote_run_finish.py /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py')
        resources=ssh('nproc; cat /proc/loadavg; df -B1 ~/ugrp-sim/runs; ls -l ~/ugrp-sim/leases')
        metadata={'class':'dev','pr':405,'branch':branch,'sha':sha,'batch':name,'vm_task_limit_s':args.task_budget_s,
                  'batch_limit_s':args.wall_budget_s,'runner':'azure-sim/scripts/remote_run.py APIs + existing live VM',
                  'mode':'fresh_continuous_paired', 'cpus':[int(c) for c in args.cpus.split(',')], 'storage_estimate':'12 x 512 MiB (3x observed full-run extrapolation) + 3072 MiB source + 4096 MiB sibling reserve; Mac lite 128 MiB',
                  'runner_sha256':hashlib.sha256((args.runner_root/'scripts/remote_run.py').read_bytes()).hexdigest(),
                  'installed_helpers_sha256':helpers,'resources_before':resources,'model_calls':0}
        (local/(name+'-submission.json')).write_text(json.dumps(metadata,indent=2)+'\n')
        remote.ship('azure',args.worktree,sha)
        # PythonRobotics imports pyplot even though animation is disabled.
        # Check the actual follower before admitting all twelve physical runs.
        ssh(f'cd ~/ugrp-sim/src/{sha} && MPLBACKEND=Agg .venv-sim/bin/python -c '+shlex.quote(
            'from harness.public_navigation.follower import pursuit; assert pursuit().show_animation is False'))
        command=['env','UGRP_EXECUTION_HOST=azure','MUJOCO_GL=osmesa','OMP_NUM_THREADS=1','OPENBLAS_NUM_THREADS=1','LP_NUM_THREADS=1','MPLBACKEND=Agg',
                 'timeout','-s','INT','-k','60',str(args.wall_budget_s+200),'.venv-sim/bin/python','-m','scripts.sim_cli','workflow','run',
                 'egomap-fresh-paired-dev','--timeout',str(args.wall_budget_s+150),'--','--mode','batch','--cpus',args.cpus,'--wall-budget-s',str(args.wall_budget_s),
                 '--output',f'/home/ugrp/ugrp-sim/runs/{name}/data']
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
        while time.monotonic()-started<args.wall_budget_s+300:
            state=ssh(f'touch {lease}; test ! -f {root}/EXIT || cat {root}/EXIT')
            status=ssh(f'test ! -f {root}/data/batch-status.json || python3 -c '+shlex.quote(
                'import json,collections;from pathlib import Path;p=Path.home()/"ugrp-sim/runs/'+name+'/data/batch-status.json";print(dict(collections.Counter(x["status"] for x in json.loads(p.read_text()))))'))
            if status!=last:print('STATUS',status,flush=True);last=status
            if state:break
            time.sleep(30)
        else:
            raise RuntimeError('own command deadline not observed; persistent raw and lease retained')
        print('EXIT',state,flush=True)
        print('COMPRESSION',ssh(f'cd ~; timeout 600 python3 /usr/local/lib/ugrp-storage/scripts/compress_json_traces.py {root} --execute'),flush=True)
        # Archive only our ended batch immediately with the lifecycle's full
        # inventory/hash verifier; never sweep or signal e2e/s3 work.
        ssh(f'touch {lease}; timeout 900 python3 /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py archive-one --run {name}')
        marker=json.loads(ssh(f'cat $HOME/ugrp-sim/lifecycle/archives/{name}.json'))
        if marker.get('verified') is not True:raise RuntimeError('ARM archive unverified')
        archived=True
        (local/(name+'-archive.json')).write_text(json.dumps(marker,indent=2)+'\n')
        print('ARCHIVED',marker['path'],flush=True)
        # Mac fetch-lite: summaries/receipts/text inventories, not large trace data.
        allowed={'RUN_META.json','SOURCE_SHA','COMMAND','EXIT','COMMAND_EXIT','HOST_ERROR.json',
                 'record-copy.json','summary.json','batch-plan.json','batch-status.json',
                 'result.json','bundle.json','preflight.json','runtime-bundle.json','v7-speedups.json',
                 'artifacts.sha256.json','SHA256SUMS','SHA256SUMS.tsv','ALL-hashes.tsv','COMPRESSED.jsonl'}
        selected=[key for key in marker['inventory'] if Path(key).name in allowed]
        listing=local/(name+'-fetch-files.txt');listing.write_text('\n'.join(selected)+'\n')
        target=Path('/Users/changmin/projects/ugrp/outputs/azure-runs')/name;target.mkdir(parents=True,exist_ok=True)
        subprocess.run(['rsync','-ac','--files-from='+str(listing),f'azure:ugrp-sim/runs/{name}/',str(target)+'/'],check=True)
        for key in selected:
            if hashlib.sha256((target/key).read_bytes()).hexdigest()!=marker['inventory'][key]['sha256']:
                raise RuntimeError('MAC_LITE_HASH_MISMATCH:'+key)
        print('FETCH_LITE_VERIFIED',len(selected),sum((target/key).stat().st_size for key in selected),flush=True)
    finally:
        heartbeat_stop.set();heartbeat_thread.join(timeout=25)
        if archived:
            ssh(f'rm -f {lease}')
        else:
            ssh(f'touch {lease}')
        # Existing azctl refuses other live leases and unarchived evidence.
        status=subprocess.run(['ssh','-o','BatchMode=yes','azure','python3 /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py status'],capture_output=True,text=True)
        if status.returncode not in (0,75):raise RuntimeError('LEASE_STATUS_FAILED')
        remaining=json.loads(status.stdout)
        all_leases=json.loads(ssh('python3 -c '+shlex.quote(
            'import json;from pathlib import Path;print(json.dumps([p.name for p in (Path.home()/"ugrp-sim/leases").iterdir()]))')))
        if all_leases:
            print('VM_RETAINED_OTHER_LEASES',all_leases,flush=True)
        else:
            subprocess.run([sys.executable,str(args.runner_root/'scripts/azctl.py'),'stop'],check=True)
        print('TASK_ELAPSED_SECONDS',round(time.monotonic()-started,2),flush=True)


if __name__=='__main__':main()
