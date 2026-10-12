"""Finite, own-process-only CPU sharing governor for the active egomap72 batch."""
import pathlib,json,os,signal,time
ROOT=pathlib.Path.home()/'ugrp-sim'
RUN=ROOT/'runs/egomap72-b-return-29c0c169'
LOG=ROOT/'lifecycle/egomap72-resource-events.jsonl'
paused=set()

def event(**row):
 with LOG.open('a') as f:f.write(json.dumps(dict(utc_epoch=time.time(),**row))+'\n')

def own(j):
 try:
  cmd=pathlib.Path(f'/proc/{j["pid"]}/cmdline').read_bytes().replace(b'\0',b' ').decode()
  return 'scripts.run_egomap_fresh_pair --mode full' in cmd and j['output'] in cmd
 except OSError:return False

try:
 while True:
  jobs=json.loads((RUN/'data/batch-status.json').read_text())
  live=[j for j in jobs if j['status']=='RUNNING' and own(j)]
  if not live:break
  ownpids={j['pid'] for j in jobs if 'pid' in j}
  busy=set();others=[]
  for proc in pathlib.Path('/proc').iterdir():
   if not proc.name.isdigit() or int(proc.name) in ownpids:continue
   try:
    cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()
    mask=os.sched_getaffinity(int(proc.name))
    if '/ugrp-sim/src/' in cmd and len(mask)<=4 and ('python' in cmd or 'cc1plus' in cmd):
     busy.update(mask);others.append(dict(pid=int(proc.name),cpus=sorted(mask)))
   except (OSError,ProcessLookupError):pass
  for seed in sorted({j['seed'] for j in live}):
   group=[j for j in live if j['seed']==seed]
   block=any(j['cpu'] in busy for j in group)
   for j in group:
    pid=j['pid'];expired=time.time()-j['started']>=6000
    if expired and pid in paused:
     os.kill(pid,signal.SIGALRM);os.kill(pid,signal.SIGCONT);paused.remove(pid)
     event(action='resume_for_host_deadline',name=j['name'],pid=pid)
    elif block and not expired and pid not in paused:
     os.kill(pid,signal.SIGSTOP);paused.add(pid)
     event(action='pause_cpu_overlap',name=j['name'],pid=pid,cpu=j['cpu'],other_reservations=others)
    elif not block and pid in paused:
     os.kill(pid,signal.SIGCONT);paused.remove(pid)
     event(action='resume_cpu_available',name=j['name'],pid=pid,cpu=j['cpu'])
  time.sleep(20)
finally:
 for j in jobs:
  if j.get('pid') in paused and own(j):
   os.kill(j['pid'],signal.SIGCONT)
   event(action='resume_governor_exit',name=j['name'],pid=j['pid'])
 event(action='governor_finished')
