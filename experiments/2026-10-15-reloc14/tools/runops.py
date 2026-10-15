import sys,json,subprocess,shlex,time,os
from pathlib import Path
ROOT=Path('/Users/changmin/projects/ugrp-wt/map-selfmap');OUT=ROOT/'outputs/reloc14'
def ssh(code,*args):
 r=subprocess.run(['ssh','gcp1','python3 - '+shlex.join(map(str,args))],input=code,text=True,capture_output=True)
 if r.returncode:raise RuntimeError(r.stderr+r.stdout)
 return r.stdout
RESERVE='''
from pathlib import Path
import json,fcntl,sys,time,os
R=Path('/home/ugrp/ugrp-sim'); name,sha=sys.argv[1:]; D=R/'admission-reservations'
with (R/'admission.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 held={p.name:json.loads(p.read_text()) for p in D.glob('*.json') if json.loads(p.read_text()).get('status')=='held'}
 active=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   if b'libmujoco' in (p/'maps').read_bytes():active.append(dict(pid=int(p.name),command=(p/'cmdline').read_bytes().replace(b'\\0',b' ').decode()))
  except (OSError,PermissionError):pass
 upper=len(active)+sum(r['slots'] for r in held.values())+1
 assert upper<=40,(upper,held)
 own=sum(r['slots'] for r in held.values() if r.get('owner')=='reloc14');assert own<16
 record=dict(run=name,owner='reloc14',sha=sha,slots=1,status='held',at_unix=time.time(),active_N=len(active),conservative_upper_bound=upper,other_held={k:v['slots'] for k,v in held.items()})
 target=D/(name+'.json')
 if target.exists():
  assert json.loads(target.read_text()).get('status')=='released' and not (R/'runs'/name).exists()
  record['previous_reservation']=json.loads(target.read_text())
 with target.open('w') as f:json.dump(record,f)
 print(json.dumps(record))
'''
def command(kind,seed,scene,sha,round):
 name=f'reloc14-r{round}-{kind}-{scene}-{seed}-{sha[:8]}'+os.environ.get('UGRP_RUN_SUFFIX','')
 if kind=='selfmap':
  old=json.loads((ROOT/'experiments/2026-10-15-reloc12/gcp-commands.json').read_text())[2]['command'];cmd=old[old.index('--')+1:]
  cmd[cmd.index('--output')+1]=f'/home/ugrp/ugrp-sim/runs/{name}/raw'
  cmd[cmd.index('--expected-source-sha')+1]=sha;cmd[cmd.index('--seed')+1]=str(seed)
  cmd[cmd.index('--render-profile')+1]='floor_light_textured_v1' if scene=='texture' else 'floor_light_v1'
  cmd+=['--reloc13-execution-cov-v1','--reloc13-execution-frame-v1','--reloc13-live-r7-v1','--reloc14-continuous-tracking-v1','--reloc14-compute-budget-v1']
  cmd[cmd.index('--cap-s')+1]=os.environ.get('UGRP_RELOC14_CAP','90')
 else:
  plan=json.loads((ROOT/'experiments/2026-10-15-reloc14/carry-texture-v7-plan.json').read_text());i=next(i for i,e in enumerate(plan['episodes']) if e['seed']==seed and e['reloc10_candidate']=='rotation_wall_search')
  cmd=['.venv-sim/bin/python','-m','scripts.run_solo_grasp_act_teacher','--plan','experiments/2026-10-15-reloc14/carry-texture-v7-plan.json','--episode',str(i),'--out',f'/home/ugrp/ugrp-sim/runs/{name}/raw','--execution-host','gcp1','--teacher-profile','solo_visible_only_v1','--held-object-hidden-v1','--setdown-lookaround-v1','--teacher-stability','align_relook_v1','--reach-mode','pad_window_v2','--rgb-lift-mode','solo_lift_lookback_v1','--solo-lift-lookback-margin-v1','--solo-truth-free-lookaround-v1','--solo-carry-to-zone-v1','--cap-s','300']
 if kind=='carry' and round>=2:
  cmd=[x.replace('carry-texture-v7-plan.json','carry-texture-v7-plan-r2.json') for x in cmd]
 return name,cmd
if sys.argv[1]=='submit':
 assert 1<=int(sys.argv[2])<=3
 assert len(json.loads(sys.argv[3])) in (4,5,6)
 source=Path(os.environ.get('UGRP_RELOC14_SOURCE',str(ROOT)));sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip();rnd=int(sys.argv[2]);runlist=json.loads(sys.argv[3]);ledger=json.loads((OUT/f'round{rnd}-submission.json').read_text()) if (OUT/f'round{rnd}-submission.json').exists() else []
 for kind,seed,scene in runlist:
  name,cmd=command(kind,seed,scene,sha,rnd);reserve=json.loads(ssh(RESERVE,name,sha))
  call=['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','506','--per-run-mb','1024',str(source),name,'--',*cmd]
  with (OUT/(name+'-submit.log')).open('w') as f:p=subprocess.run(call,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
  row=dict(name=name,kind=kind,seed=seed,scene=scene,source_sha=sha,command=call,admission=reserve,returncode=p.returncode);ledger.append(row)
  (OUT/f'round{rnd}-submission.json').write_text(json.dumps(ledger,indent=2)+'\n')
  print(json.dumps(dict(run=name,submitted=p.returncode==0,upper=reserve['conservative_upper_bound'])),flush=True)
  if p.returncode:raise RuntimeError((OUT/(name+'-submit.log')).read_text()[-4000:])
