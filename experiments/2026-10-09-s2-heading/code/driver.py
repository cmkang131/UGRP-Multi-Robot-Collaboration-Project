"""One finite authorized queue wait followed by exactly three serial DEV attempts."""
import json,os,signal,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from scripts import agent_lock
from scripts.run_s2_heading import queue_receipt
from scripts.run_final_environment_checks import check_source,write
SHA='b60acdca6e1c0c477d650b47717b84edb3f08a06'
ROOT=Path('/Users/changmin/projects/ugrp-wt/s2-heading')
OUT=Path('/Users/changmin/projects/ugrp/outputs/s2-heading-b60acdca-cohort')
assert os.getpriority(os.PRIO_PROCESS,0)==0
check_source(SHA)
OUT.mkdir(exist_ok=False)
start=time.monotonic();last=None
while True:
    try:
        receipt=queue_receipt([json.loads(s) for s in (agent_lock.DEFAULT_ROOT/'released.jsonl').read_text().splitlines()])
        held=agent_lock.status(agent_lock.DEFAULT_ROOT)
        if held is None:break
        reason=held['purpose']
    except ValueError as e:reason=str(e)
    write(OUT/'queue.json',dict(status='WAITING',reason=reason,elapsed_s=time.monotonic()-start,nice=0))
    if reason!=last:print(json.dumps(dict(event='waiting',reason=reason)),flush=True);last=reason
    if time.monotonic()-start>6*3600:raise TimeoutError('finite queue wait expired, no simulation started')
    time.sleep(30)
write(OUT/'queue.json',dict(status='PREDECESSORS_RELEASED',receipt=receipt,elapsed_s=time.monotonic()-start))
rows=[]
for seed in (1066,1068,1065):
    check_source(SHA)
    raw=OUT.parent/f's2-heading-{SHA[:8]}-s{seed}-v143'
    cmd=[sys.executable,'-m','scripts.sim_cli','workflow','run','zone-s2-heading-v143','--timeout','10800','--',
         '--execute','--expected-source-sha',SHA,'--seed',str(seed),'--heading-mode','path_tangent_v1','--output',str(raw)]
    print(json.dumps(dict(event='start',seed=seed,command=cmd)),flush=True)
    with (OUT/f's{seed}.log').open('x') as f:
        p=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
    rows.append(dict(seed=seed,returncode=p.returncode,raw=str(raw)))
    write(OUT/'runs.json',rows)
    print(json.dumps(dict(event='finish',**rows[-1])),flush=True)
    if not (raw/'result.json').is_file():
        # A lock race or preflight refusal is not a physical comparison; do not
        # overtake or silently retry it under the three-run allowance.
        raise RuntimeError('run refused before result; requires foreground diagnosis')
print(json.dumps(dict(event='complete',runs=rows)),flush=True)
