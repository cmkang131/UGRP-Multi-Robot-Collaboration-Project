"""Finite s2v59 cohort, supervisor-authorized one concurrent pair under one lock."""
import argparse
import copy
import hashlib
import json
import os
import resource
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path

from harness import zone_s2_graduation59_contract as contract
from harness.zone_solo_cyan_rotation_envelope import attach
from harness.zone_final_pair_binding import bind
from scripts import run_s2_active_observation as previous
from scripts import agent_lock
from scripts.run_final_environment_checks import check_source,write

SUPERVISOR=Path('/private/tmp/claude-501/-Users-changmin/2eb0ff27-da4f-4484-8131-64ef091df6ae/scratchpad/supervisor-s2.md')


def runtime_factory(b,clouds,index):
    plain=copy.deepcopy(b);option=plain['options'].pop('active_rotation_guard')
    factory=previous.runtime_factory(plain,clouds,index)
    return lambda *a,**kw:attach(factory(*a,**kw),active_rotation_guard=option)


def run(b,out):
    return bind(previous.run,contract=contract,runtime_factory=runtime_factory)(b,out)


def cpu():
    return sum(q.ru_utime+q.ru_stime for q in (resource.getrusage(resource.RUSAGE_SELF),resource.getrusage(resource.RUSAGE_CHILDREN)))


def host():
    p=subprocess.run(['/usr/bin/memory_pressure','-Q'],capture_output=True,text=True,timeout=10)
    return dict(loadavg=list(os.getloadavg()),memory_pressure=p.stdout.strip(),
        nice=os.getpriority(os.PRIO_PROCESS,0),pid=os.getpid(),free_bytes=shutil.disk_usage(contract.ROOT).free)


def supervisor():
    text=SUPERVISOR.read_text()
    print(text,flush=True)
    return dict(path=str(SUPERVISOR),sha256=hashlib.sha256(text.encode()).hexdigest(),text=text)


def child(a):
    check_source(a.expected_source_sha)
    b=contract.bundle(a.expected_source_sha,a.seed,**{k:getattr(a,k) for k in contract.NEW_OPTIONS})
    contract.require_execution(b)
    if a.serial_check and a.seed!=json.loads(contract.PLAN.read_text())['concurrency']['serial_check_seed']:
        raise ValueError('only preregistered benchmark repeat allowed')
    held=agent_lock.status(agent_lock.DEFAULT_ROOT)
    if (held is None or held['pid']!=a.cohort_parent_pid or os.getppid()!=a.cohort_parent_pid or
        held['owner']!='codex' or held['branch']!='codex/s2-realism' or
        held['purpose']!='s2v59 preregistered six-seed DEV and one pair throughput'):
        raise ValueError('own live cohort parent lock required')
    if os.getpriority(os.PRIO_PROCESS,0)!=0:raise ValueError('nice must be zero; never renice')
    expected=agent_lock.DEFAULT_ROOT.parent/f's2-realism-{a.expected_source_sha[:8]}-s{a.seed}-v141-graduation'
    if a.serial_check:expected=expected.with_name(expected.name+'-serial-check')
    if not a.output.is_absolute() or a.output.resolve()!=expected.resolve() or a.output.exists():
        raise ValueError('new preregistered raw path required')
    from harness.zone_pair_highpose_exact_speedups import install
    start,work=time.monotonic(),cpu();initial=host();undo=None
    try:
        _,undo=install('v98-exact-v6')
        result=run(b,a.output)
        print(json.dumps({k:result.get(k) for k in ('status','failure','evaluation','wall_per_sim')}),flush=True)
    finally:
        if undo:undo()
        if a.output.exists():
            write(a.output/'resources.json',dict(host_start=initial,host_end=host(),
                wall_s=time.monotonic()-start,cpu_self_and_reaped_children_s=cpu()-work,
                parent_lock_pid=a.cohort_parent_pid,serial_check=a.serial_check,
                timing_sensitive=False,supervisor=supervisor()))


def cohort(a):
    check_source(a.expected_source_sha)
    if os.getpriority(os.PRIO_PROCESS,0)!=0:raise ValueError('nice must be zero')
    plan=json.loads(contract.PLAN.read_text())
    for s in plan['seeds']:contract.require_execution(contract.bundle(a.expected_source_sha,s,**contract.NEW_OPTIONS))
    if not a.output.is_absolute() or a.output.exists():raise ValueError('new absolute cohort record required')
    if a.output.parent.resolve()!=agent_lock.DEFAULT_ROOT.parent.resolve():raise ValueError('primary outputs required')
    note=supervisor()
    if '2개 동시 실행' not in note['text'] or '사용자가 승인' not in note['text']:
        raise ValueError('explicit supervised pair exception missing')
    held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s2-realism',
        purpose='s2v59 preregistered six-seed DEV and one pair throughput',pid=os.getpid(),
        expected_minutes=180,timing_sensitive=False)
    a.output.mkdir();write(a.output/'registration.json',plan);write(a.output/'supervisor-start.json',note)
    rows=[];live=[]
    try:
        groups=[[plan['seeds'][0]],[plan['seeds'][1]],plan['seeds'][2:4],[plan['seeds'][4]],[plan['seeds'][5]]]
        if plan['concurrency']['supplemental_serial_check']:groups.append([plan['seeds'][2]])
        for gi,seeds in enumerate(groups):
            note=supervisor();write(a.output/f'supervisor-group-{gi}.json',note)
            if shutil.disk_usage(a.output).free<10*1024**3:raise OSError(28,'ENOSPC preflight: less than 10 GiB')
            start=time.monotonic();before=host();live=[]
            repeat=gi==5
            for seed in seeds:
                out=a.output.parent/f's2-realism-{a.expected_source_sha[:8]}-s{seed}-v141-graduation'
                if repeat:out=out.with_name(out.name+'-serial-check')
                log=a.output/f's{seed}{"-serial-check" if repeat else ""}.log'
                stream=log.open('x')
                cmd=[sys.executable,'-m','scripts.run_s2_graduation59','--execute',
                    '--expected-source-sha',a.expected_source_sha,'--seed',str(seed),
                    '--cohort-parent-pid',str(os.getpid()),'--output',str(out)]
                for k,v in contract.NEW_OPTIONS.items():cmd.extend(['--'+k.replace('_','-'),v])
                if repeat:cmd.append('--serial-check')
                process=subprocess.Popen(cmd,stdout=stream,stderr=subprocess.STDOUT,cwd=contract.ROOT)
                live.append((process,stream,seed,out))
                print(json.dumps(dict(event='started',seed=seed,pid=process.pid,output=str(out),group=gi)),flush=True)
            completed=[]
            for process,stream,seed,out in live:
                code=process.wait(timeout=plan['limits']['wall_s']);stream.close()
                completed.append(dict(seed=seed,pid=process.pid,returncode=code,output=str(out)))
            live=[]
            row=dict(group=gi,seeds=seeds,serial_check=repeat,wall_s=time.monotonic()-start,
                host_start=before,host_end=host(),runs=completed)
            rows.append(row);write(a.output/'groups.json',rows)
            print(json.dumps(dict(event='group_finished',**row)),flush=True)
    finally:
        # Only this parent's direct cohort children are cleaned on interruption.
        for process,stream,_,_ in live:
            if process.poll() is None:process.terminate()
        for process,stream,_,_ in live:
            try:process.wait(timeout=30)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            stream.close()
        released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex')
        receipt=dict(acquired=held,released=released,status_after=agent_lock.status(agent_lock.DEFAULT_ROOT))
        write(a.output/'lock.json',receipt)
        for group in rows:
            for row in group['runs']:
                if Path(row['output']).exists():write(Path(row['output'])/'lock.json',receipt)


def main():
    def terminate(signum,frame):raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,terminate)
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true');p.add_argument('--cohort',action='store_true')
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--seed',type=int)
    p.add_argument('--cohort-parent-pid',type=int);p.add_argument('--serial-check',action='store_true')
    p.add_argument('--output',type=Path,required=True)
    for key,value in contract.NEW_OPTIONS.items():p.add_argument('--'+key.replace('_','-'),choices=('off',value),default='off')
    a=p.parse_args()
    if not a.execute:
        seed=a.seed or json.loads(contract.PLAN.read_text())['seeds'][0]
        b=contract.bundle(a.expected_source_sha,seed,**{k:getattr(a,k) for k in contract.NEW_OPTIONS})
        print(json.dumps(dict(execution_started=False,bundle=b['execution_bundle_id'],task=b['task'],options=b['options'])));return
    if a.cohort:cohort(a)
    else:child(a)

if __name__=='__main__':main()
