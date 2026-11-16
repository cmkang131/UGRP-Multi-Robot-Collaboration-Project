"""Finish the one unstarted, already authorized seed after a lock race."""
import json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from scripts import agent_lock
from scripts.run_s2_heading import queue_receipt
from scripts.run_final_environment_checks import check_source,write
SHA='b60acdca6e1c0c477d650b47717b84edb3f08a06'
BASE=Path('/Users/changmin/projects/ugrp/outputs')
OUT=BASE/'s2-heading-b60acdca-cohort'
RAW=BASE/'s2-heading-b60acdca-s1065-v143'
assert os.getpriority(os.PRIO_PROCESS,0)==0
assert not RAW.exists()
check_source(SHA)
queue_receipt([json.loads(s) for s in (agent_lock.DEFAULT_ROOT/'released.jsonl').read_text().splitlines()])
start=time.monotonic()
while agent_lock.status(agent_lock.DEFAULT_ROOT) is not None:
    write(OUT/'resume-queue.json',dict(status='WAITING',seed=1065,elapsed_s=time.monotonic()-start,
        holder=agent_lock.status(agent_lock.DEFAULT_ROOT)))
    if time.monotonic()-start>6*3600:raise TimeoutError('finite queue wait expired')
    time.sleep(10)
check_source(SHA)
cmd=[sys.executable,'-m','scripts.sim_cli','workflow','run','zone-s2-heading-v143','--timeout','10800','--',
     '--execute','--expected-source-sha',SHA,'--seed','1065','--heading-mode','path_tangent_v1','--output',str(RAW)]
print(json.dumps(dict(event='start',seed=1065)),flush=True)
with (OUT/'s1065-resume.log').open('x') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
if not (RAW/'result.json').is_file():raise RuntimeError('no result; foreground diagnosis required')
rows=json.loads((OUT/'runs-before-lock-race-resume.json').read_text())[:2]
rows.append(dict(seed=1065,returncode=p.returncode,raw=str(RAW),preflight_refusal='preflight-refusal.json'))
write(OUT/'runs.json',rows)
write(OUT/'resume-queue.json',dict(status='COMPLETE',seed=1065,returncode=p.returncode))
print(json.dumps(dict(event='complete',runs=rows)),flush=True)
