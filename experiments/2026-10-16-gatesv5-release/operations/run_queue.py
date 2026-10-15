"""Finite gcp2 CPU queue supervisor, owned process groups only."""
import datetime,hashlib,json,os,pathlib,signal,subprocess,sys,time,shutil,statistics
ROOT=pathlib.Path('/home/ugrp/ugrp-sim'); OPS=ROOT/'ops-reviews/gatesv5'; PY=str(ROOT/'ugrp/.venv-sim/bin/python')
def write(p,d):p.write_text(json.dumps(d,indent=2,default=str)+'\n')
def read(p):
 if p.exists():
  try:return json.loads(p.read_text())
  except (json.JSONDecodeError,FileNotFoundError):return None
 if pathlib.Path(str(p)+'.zst').exists():return json.loads(subprocess.check_output(['zstd','-qdc',str(p)+'.zst']))
 return None
def identity(p):
 try:return p.read_bytes().replace(b'\0',b' ').decode(errors='replace')
 except (FileNotFoundError,PermissionError):return ''
def process_count():
 return [dict(pid=int(p.parent.name),cmd=s[:500]) for p in pathlib.Path('/proc').glob('[0-9]*/cmdline') if (s:=identity(p)) and any(x in s.split(' ',1)[0] for x in ['python','mujoco','ffmpeg'])]
def run(cfg_path):
 cfg=read(pathlib.Path(cfg_path));kind=cfg['kind'];stage=cfg['stage'];sha=cfg['source_sha'];src=ROOT/'src'/sha
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=src,text=True).strip()==sha
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=src)
 if stage=='gate':
  assert cfg['status']=='APPROVED_PINNED' and cfg['ready'] and cfg['review_passed']
  assert pathlib.Path(cfg['rejection_table']).is_file()
  assert hashlib.sha256(pathlib.Path(cfg['rejection_table']).read_bytes()).hexdigest()==cfg['rejection_table_sha256']
 batch=OPS/(kind+'-'+stage+'-'+sha[:8]);batch.mkdir(exist_ok=False)
 write(batch/'RUN_META.json',dict(**{'class':'dev'},pr=522 if kind=='beampair' else 491,sha=sha,batch=batch.name,host='gcp2'))
 lease=ROOT/'leases'/('gatesv5-'+kind+'.json');write(lease,dict(task='gatesv5-'+kind,pid=os.getpid(),started=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end='finite queue; per-run8h cap',concurrency=cfg['max_parallel'],source_sha=sha))
 env={**os.environ,'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','LP_NUM_THREADS':'1','PYTHONPATH':str(src)}
 running=[];completed=[];stopped=False;pending=list(cfg['runs']);first_wave_passed=stage!='gate';started_N=0
 def stop(reason):
  nonlocal stopped
  if stopped:return
  stopped=True;record=dict(reason=reason,time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),remaining=len(pending))
  write(batch/'SUPERVISOR_STOP.json',record)
  for item in running:
   if item['p'].poll() is None:
    write(item['dir']/'SUPERVISOR_STOP.json',record)
    try:os.killpg(item['p'].pid,signal.SIGINT)
    except ProcessLookupError:pass
 def launch(r):
  nonlocal started_N
  processes=process_count();other_leases={p.name:read(p) for p in (ROOT/'leases').glob('*.json') if p.name not in ['gatesv5.json',lease.name]}
  reserved=sum(int(v.get('concurrency',0)) for v in other_leases.values())
  if len(processes)+1>40 or reserved+len(running)+1>40:raise RuntimeError('global40 capacity unavailable')
  assert shutil.disk_usage(ROOT).free>8*1024**3+(len(pending)+len(running)+1)*256*1024**2
  assert next(int(l.split()[1]) for l in pathlib.Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))>6*1024**2
  d=ROOT/'runs'/r['name'];d.mkdir(exist_ok=False)
  write(d/'RUN_META.json',dict(**{'class':'dev'},pr=522 if kind=='beampair' else 491,branch='codex/gatesv5-'+kind,sha=sha,batch=batch.name,host='gcp2'))
  common='import json,sys;from pathlib import Path;plan=json.loads(Path(sys.argv[1]).read_text())["episodes"][int(sys.argv[2])];'
  if kind=='beampair':
   code=common+'from scripts.run_beampair1 import run;run(plan,Path(sys.argv[3]),sys.argv[4],mode="beampair1_v1",candidate="baseline",cap_s=60,rendezvous="peer_rendezvous_v2",approach_repair="beampair_approach_v2",wall_layer="beampair_wall_clear_v1",failure_tail=True)'
   tail=[str(ROOT/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247')]
  else:
   code=common+"""
import time
from scripts import run_grasp_act_release as runner
original=runner.snapshot
at=time.monotonic();first_t=None;saved=False;ledger=None
def snapshot(world,*a,**kw):
 global first_t,saved,ledger
 value=original(world,*a,**kw)
 now=float(world.data.time)
 if ledger is None:ledger=(Path(sys.argv[3])/'evaluator-snapshots.jsonl').open('w',buffering=1)
 ledger.write(json.dumps(dict(t=now,truth=value,qpos=world.data.qpos.tolist()))+'\\n')
 if first_t is None:first_t=now
 elapsed=now-first_t
 if not saved and elapsed>=30-1e-7:
  saved=True;wall=time.monotonic()-at
  (Path(sys.argv[3]).parent/'FIRST30.json').write_text(json.dumps(dict(sim_s=elapsed,wall_s=wall,wall_per_sim=wall/elapsed,origin_world_t=first_t,scope='first30 SIM from initial evaluator snapshot, including model initialization wall time; recording wrapper only'))+'\\n')
 return value
runner.snapshot=snapshot
runner.run(plan,Path(sys.argv[3]),cap_s=180,**json.loads(sys.argv[4]))
"""
   tail=[json.dumps(r['profile'])]
  cmd=['timeout','--signal=INT','8h',PY,'-c',code,cfg['plan'],str(r['episode']),str(d/'raw'),*tail]
  log=(d/'log.txt').open('w');p=subprocess.Popen(cmd,cwd=src,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  write(d/'PROCESS.json',dict(pid=p.pid,command=cmd,source_sha=sha,config=r,started=time.time()))
  running.append(dict(p=p,dir=d,log=log,config=r,started=time.time()));started_N+=1
  write(batch/'admission-latest.json',dict(processes=processes,other_leases=other_leases,reserved=reserved,own=len(running),loadavg=os.getloadavg(),free_bytes=shutil.disk_usage(ROOT).free))
 try:
  while pending or running:
   while pending and len(running)<cfg['max_parallel'] and not stopped and (first_wave_passed or started_N<cfg['max_parallel']):launch(pending.pop(0))
   for item in running[:]:
    speed=item['dir']/'FIRST30.json'
    if not speed.exists():
     raw=item['dir']/'raw';report=read(raw/'result.json');progress=read(raw/'progress.json')
     exact=(report or {}).get('first30_speed')
     if exact:write(speed,exact)
     elif progress and progress.get('sim_s',0)>=30:write(speed,dict(**progress,wall_per_sim=progress['wall_s']/progress['sim_s'],scope='first polled progress at/after30 SIM seconds; exact sampled SIM retained'))
    code=item['p'].poll()
    if code is None:continue
    item['log'].close();d=item['dir'];result=read(d/'raw/result.json')
    success=bool(result and result.get('status')=='complete' and result.get('physical_success' if kind=='beampair' else 'release_success') and all((result.get('input_audit') or {}).get(k)==0 for k in ['invisible_measurements','held_world_reads']))
    if kind=='release':success=success and (result.get('input_audit') or {}).get('control_top_camera_reads')==0
    category=('success' if success else 'HOST_ERROR' if code and (not result or result.get('status')=='HOST_ERROR') else 'supervisor_stop' if (d/'SUPERVISOR_STOP.json').exists() else 'cap_end' if result and (result.get('cap_end') or result.get('termination_category')=='cap_end') else 'failure')
    row=dict(**item['config'],raw=str(d/'raw'),exit=code,category=category,wall_s=time.time()-item['started'],status=result.get('status') if result else 'missing_result')
    write(d/'EXIT.json',row);completed.append(row);running.remove(item)
    if not success and not stopped:stop(dict(run=d.name,category=category,result=result.get('release_outcome',result.get('end_reason')) if result else 'missing_result'))
   if stage=='gate' and not first_wave_passed and started_N>=cfg['max_parallel'] and not running:
    values=[]
    for row in completed:
     speed=read(pathlib.Path(row['raw']).parent/'FIRST30.json')
     report=read(pathlib.Path(row['raw'])/'result.json')
     if report and report.get('first30_speed'):speed=report['first30_speed']
     if speed:values.append(speed['wall_per_sim'])
    timing=dict(N=len(values),median=statistics.median(values) if values else None,values=values,threshold=6.0)
    write(batch/'first30-speed.json',timing)
    if not values or timing['median']>6.0:stop(dict(reason='first30_speed_block',timing=timing))
    else:first_wave_passed=True
   write(batch/'progress.json',dict(completed=completed,running=[x['dir'].name for x in running],not_started=[r['name'] for r in pending],stopped=stopped))
   if stopped and not running:break
   time.sleep(1)
 except BaseException as e:
  stop(dict(supervisor_exception=repr(e)))
  raise
 finally:
  for item in running:
   item['p'].wait();item['log'].close()
  write(batch/'DONE.json',dict(completed=completed,not_started=pending,stopped=stopped,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
  if lease.exists():lease.unlink()
if __name__=='__main__':run(sys.argv[1])
