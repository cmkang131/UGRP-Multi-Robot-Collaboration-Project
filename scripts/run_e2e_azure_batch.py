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


def dedicated_verdict(cpus,idle,writers):
    if len(cpus)!=4 or len(set(cpus))!=4 or any(c not in idle for c in cpus):
        raise ValueError('FOUR_MEASURED_CPUS_REQUIRED')
    if len(writers)+4>18:raise ValueError('AZURE_CONCURRENT_LIMIT')
    if any(set(w['cpus'])&set(cpus) for w in writers):raise ValueError('RESERVED_CPU_OVERLAP')
    if min(idle[c] for c in cpus)<.8:raise ValueError('RESERVED_CPU_BUSY')
    return dict(mode='verified_dedicated_cpus',cpus=cpus,idle_fraction=idle,
        other_simulations=writers,estimated_cores=2.4,reserved_cores=4)


def dedicated_admission(cpus):
    def read():
        result={}
        for line in Path('/proc/stat').read_text().splitlines():
            r=line.split()
            if r[0] in {'cpu'+str(c) for c in cpus}:result[int(r[0][3:])]=list(map(int,r[1:9]))
        return result
    before=read();time.sleep(1);after=read();idle={}
    for c in cpus:
        delta=[b-a for a,b in zip(before[c],after[c])]
        if sum(delta)<=0:raise ValueError('CPU_MEASUREMENT_MISSING')
        idle[c]=delta[3]/sum(delta)  # iowait is deliberately not counted as free.
    writers=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            argv=(p/'cmdline').read_bytes().split(b'\0')
            if b'--execute' not in argv or b'/ugrp-sim/src/' not in argv[0]:continue
            if not Path(argv[0].decode()).name.startswith('python'):continue
            masks=[os.sched_getaffinity(int(t.name)) for t in (p/'task').iterdir()]
            writers.append(dict(pid=int(p.name),cpus=sorted(set().union(*masks))))
        except (FileNotFoundError,ProcessLookupError):continue
    return dedicated_verdict(cpus,idle,writers)


def main():
    p=argparse.ArgumentParser();p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--relay-root',type=Path,required=True)
    p.add_argument('--reserved-cpus',help='Default off: four otherwise unused Linux CPU IDs, rechecked at admission')
    a=p.parse_args();root=a.run_root.resolve()
    if not root.is_relative_to(Path.home()/'ugrp-sim/runs'):raise ValueError('PERSISTENT_RUN_REQUIRED')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=a.expected_source_sha:
        raise ValueError('FROZEN_SOURCE_REQUIRED')
    cpus=[int(x) for x in a.reserved_cpus.split(',')] if a.reserved_cpus else None
    resources=dict(mode='whole_vm_load',loadavg=list(os.getloadavg()))
    if cpus:
        if not set(cpus)<=os.sched_getaffinity(0):raise ValueError('CPU_OUTSIDE_ALLOWED_MASK')
        resources.update(dedicated_admission(cpus))
    elif os.getloadavg()[0]>=12.8:raise ValueError('AZURE_LOAD_ADMISSION')
    available=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))
    if available<6*1024**2+4*512*1024:raise ValueError('AZURE_MEMORY_ADMISSION')
    resources['memory_available_kib']=available;write(root/'resource-admission.json',resources)
    parent=json.loads((root/'RUN_META.json').read_text());jobs=[];reason=None
    def stop(*_):raise KeyboardInterrupt('TASK_STOP')
    signal.signal(signal.SIGTERM,stop)
    try:
        for index,(name,seed,model,profile) in enumerate(cells()):
            target=root/'cases'/name;target.mkdir(parents=True,exist_ok=False)
            write(target/'RUN_META.json',{**parent,'batch':root.name,'run':name,'class':'dev','pr':433})
            command=[sys.executable,'-m','scripts.sim_cli','workflow','run','e2e-ownmap-live-v185',
                '--timeout','12660','--','--expected-source-sha',a.expected_source_sha,
                '--output',str(target/'raw'),'--seed',str(seed),'--driver-profile',profile,
                '--relay-receipt',str(a.relay_root/(model+'-r1.json')),'--e2e-live','--event-driven-llm',
                '--compact-prompt','--setdown-only-when-relook','on_v1','--execute']
            log=(target/'log.txt').open('x')
            env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','LP_NUM_THREADS':'1'}
            selected_cpu=cpus[index] if cpus else None
            if selected_cpu is not None:command=['taskset','-c',str(selected_cpu),*command]
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=env)
            write(target/'PROCESS.json',dict(pid=process.pid,started_unix=time.time(),command=command,
                cpu=selected_cpu,thread_limits={k:env[k] for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','LP_NUM_THREADS')}))
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
