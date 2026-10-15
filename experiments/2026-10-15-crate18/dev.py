"""Run-first DEV6 on existing gcp1; runner outputs stay inside this worktree.

No cloud credentials/model calls are placed on the VM. Shared remote admission
uses the existing lock. Only this script's six reservations/leases are released.
"""
import argparse,hashlib,json,os,shlex,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; HERE=Path(__file__).parent
PROJECT='ugrp-act-train-1014'
sys.path.insert(0,str(ROOT))
from scripts import remote_run
remote_run.PRIMARY=ROOT  # original runner, scoped fetch/lifecycle destination

def call(a,**kw):return subprocess.run(a,check=True,**kw)
def ssh(code):
    r=call(['ssh','-o','BatchMode=yes','gcp1','python3 -'],input=code,text=True,capture_output=True)
    return json.loads(r.stdout)
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip()
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2)+'\n')
def payload(name,candidate,index):
    return ['.venv-sim/bin/python','-m','scripts.run_crate_teacher','--plan','experiments/2026-10-15-crate18/reproduction-plan.json','--episode',str(index),
        '--grasp-cap-s','60','--cap-s','27.5','--observe-mode','backoff_v3','--zone-slots','zone','--reach-mode','pad_window_v2',
        '--own-pose-source','commands','--held-object','hidden_v1','--setdown-lookaround','setdown_lookaround_own_v2',
        '--crate-scene','crate_mass_025_v1','--crate-lift-pose','crate_antipodal_grasp_v1','--rgb-lift','crate_rgb_lift_v3',
        '--teacher-stability','align_relook_v1','--teacher-search','search_reacquire_v1','--approach-goal-set','approach_goal_set_v1',
        '--crate-approach-recovery','crate_approach_recovery_v1','--crate-profile','crate17_v1' if candidate=='full' else 'crate17_no_clearance_v1',
        '--crate18','crate18_v1','--recording-mode','success_measurement','--execution-host','gcp1','--pr','500',
        '--out',f'/home/ugrp/ugrp-sim/runs/{name}/raw']

def safety(out):
    state=json.loads(subprocess.check_output(['gcloud','compute','instances','describe','ugrp-sim-gcp1','--zone','asia-northeast3-a','--project',PROJECT,'--format=json(status,machineType,scheduling,serviceAccounts)'],text=True))
    logs=json.loads(subprocess.check_output(['gcloud','logging','read','resource.labels.service_name="budget-stop" AND logName:"stdout"','--project',PROJECT,'--freshness=12h','--limit=100','--format=json(timestamp,jsonPayload,textPayload)'],text=True))
    save(out/'cost-safety.json',dict(instance=state,budget_logs=logs))
    if state['status']!='RUNNING' or state['machineType'].split('/')[-1]!='n4-highcpu-64':raise RuntimeError('existing RUNNING gcp1 required; do not restart after cost stop')
    if state.get('serviceAccounts') or state['scheduling'].get('maxRunDuration',{}).get('seconds')!='28800' or state['scheduling'].get('instanceTerminationAction')!='STOP':raise RuntimeError('VM guards/account mismatch')
    for e in logs:
        d=e.get('jsonPayload',{}); text=e.get('textPayload','').lower()
        if (d.get('budgetAmount',0)>0 and d.get('costAmount',0)>=d['budgetAmount']) or d.get('stopped') or d.get('stopping') or 'stopping vm' in text:
            raise RuntimeError('BUDGET_STOP: no new runs')

def reserve(names,sha):
    code='''import fcntl,json,pathlib,time,os
b=pathlib.Path.home()/'ugrp-sim'
names=NAMES;sha=SHA
with (b/'admission.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 active={}
 for p in (b/'admission-reservations').glob('*.json'):
  d=json.loads(p.read_text());name=d.get('run',p.stem)
  if d.get('status') in ('released','complete','completed','cancelled'):continue
  if (b/'runs'/name/'EXIT').exists():continue
  active[name]=int(d.get('slots',1))
 workers=[];uncovered=[]
 for p in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
  try:a=p.read_bytes().split(b'\\0');args=[s.decode(errors='replace') for s in a if s]
  except (OSError,PermissionError):continue
  if not args or 'python' not in args[0]:continue
  joined=' '.join(args)
  if not ('scripts.run_' in joined or 'from scripts.run_' in joined):continue
  workers.append(int(p.parent.name))
  if not any(name in joined for name in active):uncovered.append(int(p.parent.name))
 total=sum(active.values())+len(uncovered)
 if total+len(names)>40:raise RuntimeError('admission exceeds40: '+str((active,uncovered,total)))
 for name in names:
  p=b/'admission-reservations'/(name+'.json')
  with p.open('x') as f:json.dump(dict(run=name,owner='crate18-'+sha[:8],slots=1,sha=sha,status='reserved',at_unix=time.time()),f)
 print(json.dumps(dict(active=active,uncovered_workers=uncovered,worker_count=len(workers),before=total,with_new=total+len(names),names=names)))
'''.replace('NAMES',repr(names)).replace('SHA',repr(sha))
    return ssh(code)

def main():
    p=argparse.ArgumentParser();p.add_argument('--round',type=int,required=True);a=p.parse_args()
    if a.round not in (1,2,3):raise ValueError('max3 rounds')
    if git('status','--porcelain'):raise RuntimeError('commit all source before run')
    sha=git('rev-parse','HEAD');out=ROOT/'outputs/crate18'/f'round{a.round}-{sha[:8]}';out.mkdir(parents=True,exist_ok=False)
    safety(out)
    rows=[]
    for i,seed in enumerate((77990,79314,79317)):
        for candidate in ('full','no_clearance'):
            name=f'crate18-r{a.round}-{candidate}-{seed}-{sha[:8]}'
            rows.append(dict(name=name,seed=seed,candidate=candidate,sha=sha,payload=payload(name,candidate,i)))
    save(out/'admission.json',reserve([r['name'] for r in rows],sha));save(out/'plan.json',rows)
    for r in rows:
        # Every runner checks disk and available memory again. Detach does not stop others.
        args=['--host','gcp1','--detach','--class','dev','--pr','500','--per-run-mb','128',str(ROOT),r['name'],'--',*r['payload']]
        sys.argv=['scripts/remote_run.py',*args]
        with (out/(r['name']+'-submit.log')).open('w') as log:
            from contextlib import redirect_stdout,redirect_stderr
            with redirect_stdout(log),redirect_stderr(log):remote_run.main()
        print('submitted',r['name'],flush=True)
    print(out,flush=True)
if __name__=='__main__':main()
