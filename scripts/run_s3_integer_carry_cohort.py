"""Frozen20 runs (10conditions xon/off), concurrent x86 admission and live receipts."""
import argparse,concurrent.futures,json,math,os,platform,re,subprocess,sys,threading,time
from pathlib import Path
from scripts.run_s3_x86_cohort import ROOT
from scripts.run_s3_setdown_cohort import live_rows
PLAN=ROOT/'experiments/2026-10-10-s3-integer-carry/summary.json'
ADMIT=threading.Lock()


def commands(plan,sha):
 return [(r,[sys.executable,'-m','scripts.run_s3_integer_carry','--expected-source-sha',sha,'--output',f'outputs/{r["name"]}/raw','--case',r['case'],'--condition',str(r['condition']),'--integer-carry',r['option'],'--execute']) for r in plan['preregistration']['runs']]


def inspect(target,case):
 raw=target/'raw';history=live_rows(raw/('cyan-progress.jsonl' if case=='cyan' else 'progress.jsonl'))
 result=json.loads((raw/'result.json').read_text()) if (raw/'result.json').exists() else {}
 reasons=[];robots=('r3',) if case=='cyan' else ('r1','r2');motion={}
 if result.get('status') in ('HOST_ERROR','EARLY_STOP'):reasons.append('execution exception')
 log=(target/'log.txt').read_text()
 if 'Traceback (most recent call last)' in log:reasons.append('log traceback')
 if len(history)<2 or history[-1]['t']<=history[0]['t'] or history[-1]['frame_count']<=history[0]['frame_count']:reasons.append('no advancing SIM/frame receipt')
 seen=sorted({v for row in history for v in row['states'].values()})
 for rid in robots:
  if history:
   origin=history[0]['robots'][rid];motion[rid]={k:max(math.dist(x['robots'][rid][k],origin[k]) for x in history) for k in ('base_xyz_m','finger_xyz_m')}
   if max(motion[rid].values())<.001:reasons.append(rid+' no actual base/arm motion')
  cc=live_rows(raw/f'robots/{rid}/commands.jsonl');mm=[c for c in cc if c.get('kind') in ('mecanum','drive') and any(c.get(k,0) for k in ('forward','left','turn'))]
  if any(sum(bool(c.get(k,0)) for k in ('forward','left','turn'))>1 or c.get('duration_s',0)<.1-1e-8 for c in mm):reasons.append(rid+' motor contract')
  if len(mm)>40 and all(c.get('turn') for c in mm[-40:]) and len(seen)<2:reasons.append(rid+' turn-only stuck')
 if not any(s in ('pregrasp_descend','wait_close','grasp','hover','blind_descent','lift','low_lift','raise_high','wait_carry','carry','wait_lower','lower','wait_open','cp_open') for s in seen):reasons.append('key grasp/lift stage absent')
 report=dict(name=target.name,host='oracle-x86',checked_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),progress_samples=len(history),sim_s=history[-1]['t'] if history else None,frames=history[-1]['frame_count'] if history else 0,motion_m=motion,seen_states=seen,healthy=not reasons,reasons=reasons,completed=bool(result))
 if reasons and not result:(target/'STOP_REQUEST').write_text(json.dumps(report)+'\n')
 return report


def admission():
 # User10/10: independent Oracle work is allowed; gate only live load/memory.
 while True:
  load=os.getloadavg();mem=int(next(s.split()[1] for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:')))*1024
  if load[0]<51 and mem>=6*1024**3:return dict(loadavg=load,mem_available_bytes=mem,utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
  time.sleep(5)


def execute(item,out,sha):
 r,args=item;target=out/r['name'];target.mkdir(exist_ok=False)
 (target/'SOURCE_SHA').write_text(sha+'\n');(target/'COMMAND.json').write_text(json.dumps(args)+'\n')
 for link in (ROOT/'outputs'/r['name'],Path.home()/'ugrp-sim/runs'/r['name']):
  if link.exists() or link.is_symlink():raise FileExistsError(link)
  link.symlink_to(target.resolve(),target_is_directory=True)
 with (target/'log.txt').open('w') as log:
  with ADMIT:
   receipt=admission();(target/'admission.json').write_text(json.dumps(receipt)+'\n')
   process=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,MUJOCO_GL='osmesa',OMP_NUM_THREADS='1',LP_NUM_THREADS='4'))
  (target/'PID').write_text(str(process.pid)+'\n');start=time.monotonic()
  while process.poll() is None and time.monotonic()-start<180:time.sleep(1)
  report=inspect(target,r['case']);report['elapsed_wall_s']=time.monotonic()-start
  (target/'initial-check.json').write_text(json.dumps(report,indent=2)+'\n');code=process.wait()
 (target/'EXIT').write_text(str(code)+'\n')
 return dict(**r,exit_code=code,source_sha=sha,admission=receipt,initial_check=report)


def main():
 p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
 plan=json.loads(PLAN.read_text());items=commands(plan,a.expected_source_sha)
 if not a.execute:print(json.dumps(items));return 0
 if platform.system()!='Linux' or platform.machine()!='x86_64' or ROOT.name!=a.expected_source_sha or not re.fullmatch('[a-f0-9]{40}',a.expected_source_sha) or os.getpriority(os.PRIO_PROCESS,0)!=0:raise ValueError('committed x86 archive and nice0 required')
 if len(items)!=20 or os.environ.get('LP_NUM_THREADS')!='4':raise ValueError('frozen20 worker/LP4 required')
 if a.output.is_absolute() or len(a.output.parts)!=3 or a.output.parts[0]!='outputs' or a.output.parts[-1]!='cohort':raise ValueError('new outputs/<batch>/cohort required')
 if (a.output.resolve().parent/'SOURCE_SHA').read_text().strip()!=a.expected_source_sha:raise ValueError('source receipt mismatch')
 a.output.mkdir(parents=True,exist_ok=False)
 with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
  fs=[pool.submit(execute,item,a.output,a.expected_source_sha) for item in items];results=[f.result() for f in concurrent.futures.as_completed(fs)]
 (a.output/'cohort.json').write_text(json.dumps(sorted(results,key=lambda x:x['name']),indent=2)+'\n')
 return int(any(r['exit_code'] for r in results))
if __name__=='__main__':raise SystemExit(main())
