"""One guarded Azure lease, four independently recorded managed workflows.

The host runner calls boot recovery at admission. Submit this single batch so
recovery never attempts to archive a sibling which is still running.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from scripts.run_e2e_ownmap_live import write


def cells():
    return [(f'e2eaz1-{model}-s{seed}-on-r1',seed,model,profile)
        for seed in (61001,61002)
        for model,profile in (('gemma','study_gemma4_31b_v1'),('gemini','main_study_gemini_v1'))]


def main():
    p=argparse.ArgumentParser();p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--relay-root',type=Path,required=True)
    a=p.parse_args();root=a.run_root.resolve()
    if not root.is_relative_to(Path.home()/'ugrp-sim/runs'):raise ValueError('PERSISTENT_RUN_REQUIRED')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=a.expected_source_sha:
        raise ValueError('FROZEN_SOURCE_REQUIRED')
    if os.getloadavg()[0]>=12.8:raise ValueError('AZURE_LOAD_ADMISSION')
    available=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))
    if available<6*1024**2+4*512*1024:raise ValueError('AZURE_MEMORY_ADMISSION')
    parent=json.loads((root/'RUN_META.json').read_text());jobs=[];reason=None
    def stop(*_):raise KeyboardInterrupt('TASK_STOP')
    signal.signal(signal.SIGTERM,stop)
    try:
        for name,seed,model,profile in cells():
            target=root/'cases'/name;target.mkdir(parents=True,exist_ok=False)
            write(target/'RUN_META.json',{**parent,'batch':root.name,'run':name,'class':'dev','pr':433})
            command=[sys.executable,'-m','scripts.sim_cli','workflow','run','e2e-ownmap-live-v185',
                '--timeout','12660','--','--expected-source-sha',a.expected_source_sha,
                '--output',str(target/'raw'),'--seed',str(seed),'--driver-profile',profile,
                '--relay-receipt',str(a.relay_root/(model+'-r1.json')),'--e2e-live','--event-driven-llm',
                '--compact-prompt','--setdown-only-when-relook','on_v1','--execute']
            log=(target/'log.txt').open('x')
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            write(target/'PROCESS.json',dict(pid=process.pid,started_unix=time.time(),command=command))
            jobs.append((target,process,log,time.monotonic()))
        while any(proc.poll() is None for _,proc,_,_ in jobs):
            for target,proc,log,started in jobs:
                if proc.poll() not in (None,0):reason='INITIAL_BATCH_MEMBER_FAILED';break
                if time.monotonic()-started>=285:
                    check=target/'raw/initial-check.json'
                    if not check.exists() or not json.loads(check.read_text()).get('passed'):
                        reason='INITIAL_HEALTH_DEADLINE';break
            if reason:break
            time.sleep(2)
    except (Exception,KeyboardInterrupt) as exc:
        reason=type(exc).__name__+':'+str(exc)
    finally:
        for _,proc,_,_ in jobs:
            if proc.poll() is None:os.killpg(proc.pid,signal.SIGINT)
        for target,proc,log,started in jobs:
            try:code=proc.wait(timeout=45)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL);code=proc.wait()
            log.close();(target/'EXIT').write_text(str(code)+'\n')
            if code and not (target/'raw/result.json').exists():
                write(target/'HOST_ERROR.json',dict(reason=reason or 'CHILD_FAILED',exit=code))
            hashes={}
            for f in target.rglob('*'):
                if f.is_file():
                    with f.open('rb') as stream:hashes[str(f.relative_to(target))]=hashlib.file_digest(stream,'sha256').hexdigest()
            write(target/'sha256.json',hashes)
            # The outer standard supervisor preserves each child's manifest.
            for line in (target/'log.txt').read_text().splitlines():
                if line.startswith('Simulation record: '):print(line,flush=True)
        write(root/'batch-result.json',dict(status='STOPPED' if reason else 'FINISHED',reason=reason,
            runs=[dict(name=t.name,exit=p.returncode) for t,p,_,_ in jobs],expansion_admitted=False))
    return int(bool(reason))


if __name__=='__main__':raise SystemExit(main())
