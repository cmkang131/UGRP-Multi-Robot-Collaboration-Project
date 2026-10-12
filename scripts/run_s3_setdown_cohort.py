"""One frozen ten-worker batch, with required live check at180 wall seconds."""
import argparse,concurrent.futures,json,math,os,platform,re,subprocess,sys,time
from pathlib import Path
from scripts.run_s3_x86_cohort import ROOT
PLAN=ROOT/'experiments/2026-10-10-s3-setdown/summary.json'

def commands(plan,sha):
 return [(r,[sys.executable,'-m','scripts.run_s3_setdown','--expected-source-sha',sha,'--output',f'outputs/{r["name"]}/raw','--case','pair','--condition',str(r['condition']),'--setdown',r['option'],'--execute']) for r in plan['preregistration']['runs']]

def live_rows(path):
 if not path.exists():return []
 return [json.loads(s) for s in path.read_text().splitlines() if s.endswith('}')]

def inspect(target):
 history=live_rows(target/'raw/progress.jsonl');result={}
 if (target/'raw/result.json').exists():result=json.loads((target/'raw/result.json').read_text())
 reasons=[]
 if result.get('status') in ('HOST_ERROR','EARLY_STOP'):reasons.append('execution exception')
 if len(history)<2 or history[-1]['t']<=history[0]['t'] or history[-1]['frame_count']<=history[0]['frame_count']:reasons.append('no advancing SIM/frame receipt')
 moved={};seen=sorted({v for row in history for v in row['states'].values()})
 for rid in ('r1','r2'):
  if history:
   origin=history[0]['robots'][rid]
   moved[rid]={key:max(math.dist(x['robots'][rid][key],origin[key]) for x in history) for key in ('base_xyz_m','finger_xyz_m')}
   if max(moved[rid].values())<.001:reasons.append(rid+' no measured chassis/arm motion')
 cmds={rid:live_rows(target/f'raw/robots/{rid}/commands.jsonl') for rid in ('r1','r2')}
 for rid,cc in cmds.items():
  mm=[c for c in cc if c.get('kind') in ('mecanum','drive') and any(c.get(k,0) for k in ('forward','left','turn'))]
  if any(sum(bool(c.get(k,0)) for k in ('forward','left','turn'))>1 or c.get('duration_s',0)<.1-1e-8 for c in mm):reasons.append(rid+' motor contract')
  if len(mm)>40 and all(c.get('turn',0) for c in mm[-40:]) and len(seen)<2:reasons.append(rid+' turn-only loop')
 if not any(s in ('pregrasp_descend','wait_close','grasp','lift','wait_carry','carry','wait_lower','lower','wait_open','cp_open') for s in seen):reasons.append('key grasp/lift phase not entered')
 report=dict(name=target.name,checked_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),pid=int((target/'PID').read_text()),completed=(target/'EXIT').exists() or (target/'raw/result.json').exists(),progress_samples=len(history),first_sim_s=history[0]['t'] if history else None,last_sim_s=history[-1]['t'] if history else None,frames=history[-1]['frame_count'] if history else 0,motion_m=moved,seen_states=seen,motor_commands={r:len(cc) for r,cc in cmds.items()},reasons=reasons,healthy=not reasons)
 if reasons and not report['completed']:(target/'STOP_REQUEST').write_text(json.dumps(report)+'\n')
 return report

def execute(item,out,sha):
 r,args=item;target=out/r['name'];target.mkdir(exist_ok=False)
 (target/'SOURCE_SHA').write_text(sha+'\n');(target/'COMMAND.json').write_text(json.dumps(args)+'\n')
 for link in (ROOT/'outputs'/r['name'],Path.home()/'ugrp-sim/runs'/r['name']):
  if link.exists() or link.is_symlink():raise FileExistsError(link)
  link.symlink_to(target.resolve(),target_is_directory=True)
 with (target/'log.txt').open('w') as log:
  process=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,MUJOCO_GL='osmesa',OMP_NUM_THREADS='1'))
  (target/'PID').write_text(str(process.pid)+'\n');start=time.monotonic()
  # Only this worker's known PID is observed. Cancellation is cooperative.
  while process.poll() is None and time.monotonic()-start<180:time.sleep(1)
  report=inspect(target);(target/'initial-check.json').write_text(json.dumps(report,indent=2)+'\n')
  code=process.wait()
 (target/'EXIT').write_text(str(code)+'\n')
 return dict(**r,exit_code=code,source_sha=sha,initial_check=report)

def main():
 p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
 plan=json.loads(PLAN.read_text());items=commands(plan,a.expected_source_sha)
 if not a.execute:print(json.dumps(items));return 0
 if platform.system()!='Linux' or platform.machine()!='x86_64' or ROOT.name!=a.expected_source_sha or not re.fullmatch('[a-f0-9]{40}',a.expected_source_sha) or os.getpriority(os.PRIO_PROCESS,0)!=0:raise ValueError('committed x86 archive and nice0 required')
 if len(items)!=10 or os.environ.get('LP_NUM_THREADS')!='4':raise ValueError('frozen10 workers / LP4 required')
 if a.output.is_absolute() or len(a.output.parts)!=3 or a.output.parts[0]!='outputs' or a.output.parts[-1]!='cohort':raise ValueError('outputs/<batch>/cohort required')
 if (a.output.resolve().parent/'SOURCE_SHA').read_text().strip()!=a.expected_source_sha:raise ValueError('source receipt mismatch')
 a.output.mkdir(parents=True,exist_ok=False)
 with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
  futures=[pool.submit(execute,item,a.output,a.expected_source_sha) for item in items];results=[f.result() for f in concurrent.futures.as_completed(futures)]
 (a.output/'cohort.json').write_text(json.dumps(sorted(results,key=lambda x:x['name']),indent=2)+'\n')
 return int(any(r['exit_code'] for r in results))
if __name__=='__main__':raise SystemExit(main())
