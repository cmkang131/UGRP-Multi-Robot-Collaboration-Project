"""One frozen Azure batch, lease heartbeat, finite lifetime and per-run early checks."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from scripts.run_s3_continuous_distance import ROOT,PLAN
from scripts.run_s3_integer_carry_cohort import inspect


def commands(plan,sha):
    return [(r,[sys.executable,'-m','scripts.run_s3_continuous_distance',
        '--expected-source-sha',sha,'--output',f'outputs/{r["name"]}/raw',
        '--distance',str(r['distance_m']),'--seed',str(r['seed']),'--execute']) for r in plan['runs']]


def execute(item,out,sha,deadline):
    r,args=item;target=out/r['name'];target.mkdir()
    (target/'SOURCE_SHA').write_text(sha+'\n')
    (target/'COMMAND.json').write_text(json.dumps(args)+'\n')
    (target/'RUN_META.json').write_text(json.dumps(dict(**{'class':'dev'},pr=416,
        sha=sha,branch='codex/s3-no-prior-smoke',batch=out.parent.name))+'\n')
    link=ROOT/'outputs'/r['name'];link.symlink_to(target.resolve(),target_is_directory=True)
    while os.getloadavg()[0]>=os.cpu_count()*.8:
        if time.monotonic()>deadline:raise TimeoutError('batch admission deadline')
        time.sleep(5)
    mem=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
    if mem<6*2**30 or shutil.disk_usage(out).free<8*2**30:raise OSError('resource admission HOST_ERROR')
    (target/'admission.json').write_text(json.dumps(dict(loadavg=os.getloadavg(),mem_available_bytes=mem,
        free_disk_bytes=shutil.disk_usage(out).free,logical_cpus=os.cpu_count()))+'\n')
    with (target/'log.txt').open('w') as log:
        proc=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        (target/'PID').write_text(str(proc.pid)+'\n');start=time.monotonic()
        while proc.poll() is None and time.monotonic()-start<180:time.sleep(1)
        check=inspect(target,'pair');check['host']='ugrp-sim-azure'
        check['elapsed_wall_s']=time.monotonic()-start
        (target/'initial-check.json').write_text(json.dumps(check,indent=2)+'\n')
        while proc.poll() is None and time.monotonic()<deadline:time.sleep(2)
        if proc.poll() is None:
            (target/'STOP_REQUEST').write_text('VM_TASK_TWO_HOUR_CAP\n')
            import signal
            os.killpg(proc.pid,signal.SIGINT)
        code=proc.wait()
    (target/'EXIT').write_text(str(code)+'\n')
    return dict(**r,exit_code=code,initial_check=check)


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    plan=json.loads((ROOT/PLAN).read_text());items=commands(plan,a.expected_source_sha)
    if not a.execute:print(json.dumps(items));return 0
    if (os.uname().nodename!='ugrp-sim-azure' or ROOT.name!=a.expected_source_sha
            or not a.output.resolve().is_relative_to(Path.home()/'ugrp-sim/runs')):
        raise ValueError('Azure immutable source + persistent output required')
    a.output.mkdir(parents=True);stop=threading.Event()
    lease=Path.home()/'ugrp-sim/leases'/a.output.parent.name
    def heartbeat():
        while not stop.wait(30):lease.touch()
    threading.Thread(target=heartbeat,daemon=True).start();deadline=time.monotonic()+6600
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            fs=[pool.submit(execute,item,a.output,a.expected_source_sha,deadline) for item in items]
            results=[f.result() for f in concurrent.futures.as_completed(fs)]
        (a.output/'cohort.json').write_text(json.dumps(results,indent=2)+'\n')
        # Evaluation runs on the execution host; full raw never goes to Mac.
        subprocess.run([sys.executable,'-m','scripts.evaluate_s3_continuous_distance',
            '--cohort',str(a.output),'--output',str(a.output.parent/'summary.json')],check=True)
    finally:stop.set();lease.touch()
    return int(any(r['exit_code'] for r in results))


if __name__=='__main__':raise SystemExit(main())
