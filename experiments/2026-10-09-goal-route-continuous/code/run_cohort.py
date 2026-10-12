"""Explicitly started finite nine-slot cohort; no priority change or CI wait."""
from pathlib import Path
import argparse,json,os,subprocess,sys,time
ROOT=Path('/Users/changmin/projects/ugrp-wt/ego-wall-map')
RAW=Path('/Users/changmin/projects/ugrp/outputs/goal-route-continuous-v1')
SUPERVISOR=Path('/private/tmp/claude-501/-Users-changmin/2eb0ff27-da4f-4484-8131-64ef091df6ae/scratchpad/supervisor-ego.md')
sys.path.insert(0,str(ROOT))
from scripts.agent_lock import status,DEFAULT_ROOT
p=argparse.ArgumentParser();p.add_argument('--source',required=True);a=p.parse_args()
assert int(subprocess.check_output(['ps','-o','ni=','-p',str(os.getpid())]))==0,'NICE_MUST_BE_ZERO'
assert json.loads((RAW/'queue-admission.json').read_text())['s3_retest_completed']
initial=SUPERVISOR.read_bytes()
os.environ['UGRP_V7_EXACT_SPEEDUPS']='relay-cache-v1'
for seed in range(55001,55010):
 while status(DEFAULT_ROOT) is not None:
  if SUPERVISOR.read_bytes()!=initial:raise RuntimeError('SUPERVISOR_CHANGED_REVIEW_BEFORE_NEXT_SLOT')
  print('Waiting for shared physics lock',seed,flush=True);time.sleep(30)
 if SUPERVISOR.read_bytes()!=initial:raise RuntimeError('SUPERVISOR_CHANGED_REVIEW_BEFORE_NEXT_SLOT')
 out=RAW/f'seed{seed}';assert not out.exists()
 cmd=[sys.executable,'-m','scripts.run_goal_route_continuous','--seed',str(seed),'--expected-source-sha',a.source,'--output',str(out),'--execute']
 with (RAW/f'seed{seed}.log').open('x') as f:
  print('START',seed,flush=True);r=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
 print('FINISH',seed,'returncode',r.returncode,flush=True)
 if not (out/'result.json').exists():raise RuntimeError('NO_TERMINAL_ARTIFACT_REVIEW_REQUIRED')
 report=[sys.executable,str(ROOT/'experiments/2026-10-09-goal-route-continuous/code/report.py'),'--seed',str(seed),'--append-readme']
 with (RAW/f'seed{seed}-score.log').open('x') as f:subprocess.run(report,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
 (RAW/'cohort-progress.json').write_text(json.dumps({'last_finished_seed':seed,'source':a.source,'next_seed':seed+1 if seed<55009 else None})+'\n')
print('NINE_SLOTS_COMPLETE',flush=True)
