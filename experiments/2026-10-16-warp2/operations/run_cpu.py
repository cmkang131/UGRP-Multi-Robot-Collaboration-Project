"""Matching finite C backend batch on gcp2 n4; truthful CPU identity and lease."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

r=Path('/home/ugrp/ugrp-sim');s=r/'src/warp2-70553d2f'
fixed_episode=int(sys.argv[1]) if len(sys.argv)>1 else None
assert fixed_episode is None or 0<=fixed_episode<6
out=r/'runs'/('warp2-cpu-r1-70553d2f'+('' if fixed_episode is None else '-seed'+str(fixed_episode)))
lease=r/'leases/warp2.json';assert not lease.exists()
out.mkdir(exist_ok=False);start=time.time();children=[]
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def process_count():
 n=0
 for p in Path('/proc').glob('[0-9]*/cmdline'):
  try:n+=bool(p.read_bytes().split(b'\0')[0].find(b'python')>=0)
  except (FileNotFoundError,PermissionError):pass
 return n
try:
 leases={p.name:p.read_text() for p in lease.parent.glob('*.json')}
 existing=process_count();assert existing+16<=40, 'global CPU execution capacity unavailable'
 write(lease,dict(task='warp2',pid=os.getpid(),started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
  expected_end=datetime.datetime.fromtimestamp(start+1800,datetime.timezone.utc).isoformat(),concurrency=16,source='70553d2f4235b28648c188b26f9b2a03fa32a19d'))
 write(out/'admission.json',dict(leases=leases,existing_python=existing,concurrency=16,total_limit=40,loadavg=os.getloadavg()))
 for i in range(16):
  d=out/f'p{i:02d}';log=(out/f'p{i:02d}.log').open('w')
  cmd=[str(r/'ugrp/.venv-sim/bin/python'),str(s/'scripts/run_warp_flow_teacher.py'),
   '--physics-backend','c_pilot_v1','--adapter-source',str(r/'src/08f129213031255dd188e20df832bb6714dfca9a'),
   '--teacher-source',str(r/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247'),
   '--plan',str(r/'src/08f129213031255dd188e20df832bb6714dfca9a/experiments/2026-10-16-beampair6/short6-plan.json'),
   '--episode',str(i%6 if fixed_episode is None else fixed_episode),'--out',str(d),'--vm-hourly-usd','3.1454']
  env={**os.environ,'MUJOCO_GL':'osmesa','PYTHONPATH':str(s),'OMP_NUM_THREADS':'1','LP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
  p=subprocess.Popen(cmd,cwd=s,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  children.append((p,log,d));write(out/'processes.json',[dict(pid=p.pid,out=str(d)) for p,_,d in children])
 while any(p.poll() is None for p,_,_ in children):
  if time.time()-start>=1800:raise TimeoutError('finite_CPU_host_cap')
  if any(p.poll() not in (None,0) for p,_,_ in children):raise RuntimeError('CPU_worker_HOST_ERROR')
  time.sleep(5)
 records=[json.loads((d/'summary.json').read_text()) for _,_,d in children]
 write(out/'summary.json',dict(status='complete',physics_backend='c_pilot_v1',host='gcp2/n4-highcpu-64',
  concurrency=16,records=records,wall_s=time.time()-start,
  aggregate_completed_sim_s=sum(x['aggregate_completed_sim_s'] for x in records),
  physical_success=sum(x['counts']['physical_success'] for x in records),
  cap_end=sum(x['counts']['cap_end'] for x in records),
  price_hourly_usd=3.1454,price_basis='historical unverified regional estimate; billing not measured'))
except BaseException as e:
 write(out/'ERROR.json',dict(type=type(e).__name__,error=str(e)))
 raise
finally:
 for p,log,d in children:
  if p.poll() is None:os.killpg(p.pid,signal.SIGINT)
 for p,log,d in children:
  try:p.wait(timeout=60)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=30)
  log.close()
 write(out/'cleanup.json',dict(own_exits=[dict(pid=p.pid,exit=p.returncode) for p,_,_ in children],
  other_leases={p.name:p.read_text() for p in lease.parent.glob('*.json') if p!=lease},
  vm_stop_attempted=False,reason='shared CPU VM: leave running'))
 if lease.exists() and json.loads(lease.read_text()).get('pid')==os.getpid():lease.unlink()
