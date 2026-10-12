"""One immutable six-job batch; only admission exit 3 is retried."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import time
from scripts.run_s4_grip_dataset import ROOT, PLAN


def commands(sha):
    plan=json.loads(PLAN.read_text())
    assert plan['max_concurrent']==6 and plan['LP_NUM_THREADS']==4
    assert len(plan['runs'])==6
    return [(r['name'],[v.replace('<SOURCE_SHA>',sha) for v in r['argv']]) for r in plan['runs']]


def submit_one(runner, name, argv, invoke=subprocess.run, wait=time.sleep):
    for attempt in range(120):
        r=invoke([str(runner),str(ROOT),name,'--',*argv],env={**os.environ,'ORACLE_HOST':'oracle-x86','LP_NUM_THREADS':'4'},capture_output=True,text=True)
        if r.returncode!=3:
            return dict(name=name,argv=argv,admission_attempts=attempt+1,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
        if attempt<119:wait(30)
    return dict(name=name,argv=argv,returncode=3,admission_attempts=120,status='MEMORY_ADMISSION_BLOCKED')


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--oracle-runner',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--submit',action='store_true');a=p.parse_args(argv)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();rows=commands(sha)
    if not a.submit:print(json.dumps(rows,indent=2));return 0
    if not a.output or a.output.exists() or not a.oracle_runner or not a.oracle_runner.is_file():raise ValueError('runner and new output required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():raise ValueError('commit frozen batch first')
    for name,_ in rows:subprocess.run(['ssh','oracle-x86',f'test ! -e ~/ugrp-sim/runs/{name}'],check=True)
    # Reuse tested atomic archive staging, before concurrent oracle_run helpers.
    from scripts.submit_s4_pair_batch import stage_source
    stage_source(sha)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda row:submit_one(a.oracle_runner,*row),rows))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:json.dump(dict(source_sha=sha,plan=str(PLAN),admissions=results),f,indent=2)
    return int(any(r['returncode'] for r in results))


if __name__=='__main__':raise SystemExit(main())
