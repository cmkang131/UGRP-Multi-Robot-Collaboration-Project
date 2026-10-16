"""Finite, own-process-only CPU sharing governor for the active egomap72 batch."""
import pathlib,json,os,signal,time
ROOT=pathlib.Path.home()/'ugrp-sim'
RUN=ROOT/'runs/egomap72-b-return-29c0c169'
LOG=ROOT/'lifecycle/egomap72-resource-events.jsonl'
paused=set()
jobs=[]

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
  for j in live:
   state=pathlib.Path(f'/proc/{j["pid"]}/stat').read_text().split(') ')[1][0]
   if state=='T':paused.add(j['pid'])
  busy=set();others=[]
  for proc in pathlib.Path('/proc').iterdir():
   if not proc.name.isdigit() or int(proc.name) in ownpids:continue
   try:
    cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()
    mask=os.sched_getaffinity(int(proc.name))
    if '/ugrp-sim/src/' in cmd and len(mask)<=4 and ('python' in cmd or 'cc1plus' in cmd):
     busy.update(mask);others.append(dict(pid=int(proc.name),cpus=sorted(mask)))
   except (OSError,ProcessLookupError):pass
  groups=[[j for j in live if j['seed']==seed] for seed in sorted({j['seed'] for j in live})]
  used=set(busy);waiting=[]
  # Keep active groups stable; migrate only waiting groups to genuinely free CPUs.
  for group in groups:
   masks=[os.sched_getaffinity(j['pid']) for j in group]
   keep=all(j['pid'] not in paused for j in group) and all(len(m)==1 and not m&used for m in masks)
   if keep:
    for m in masks:used.update(m)
    continue
   waiting.append(group)
   for j in group:
    pid=j['pid']
    if pid not in paused:
     os.kill(pid,signal.SIGSTOP);paused.add(pid)
     event(action='pause_cpu_overlap',name=j['name'],pid=pid,cpu=j['cpu'],other_reservations=others)
  for group in waiting:
   available=sorted(set(range(os.cpu_count()))-used)
   expired=any(time.time()-j['started']>=6000 for j in group)
   if len(available)<len(group) and not expired:continue
   for j in group:
    pid=j['pid']
    if expired:
     os.kill(pid,signal.SIGALRM)
    else:
     cpu=available.pop(0);old=sorted(os.sched_getaffinity(pid))
     for thread in pathlib.Path(f'/proc/{pid}/task').iterdir():
      try:os.sched_setaffinity(int(thread.name),{cpu})
      except ProcessLookupError:pass
     used.add(cpu)
     if old!=[cpu]:event(action='migrate_free_cpu',name=j['name'],pid=pid,old_cpus=old,cpu=cpu)
    if pid in paused:
     os.kill(pid,signal.SIGCONT);paused.remove(pid)
     event(action='resume_for_host_deadline' if expired else 'resume_cpu_available',name=j['name'],pid=pid,cpus=sorted(os.sched_getaffinity(pid)))
  time.sleep(20)
finally:
 for j in jobs:
  if j.get('pid') in paused and own(j):
   os.kill(j['pid'],signal.SIGCONT)
   event(action='resume_governor_exit',name=j['name'],pid=j['pid'])
 event(action='governor_finished')
