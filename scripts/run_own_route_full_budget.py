"""egomap64: one registered batch, same six checkpoints, two populations."""
from pathlib import Path
from functools import partial
import argparse,json,os,platform,shutil,subprocess,sys,time
from harness.active_camera import bind
from scripts import run_own_route_particle_round as previous
from scripts import run_own_route_particle_stages as old
from scripts.own_route_budget_schedule import OPTION,PLAN,admit_checkpoint

ROOT=Path(__file__).resolve().parents[1]
SEEDS=previous.SEEDS
PROFILES=('baseline','a')


def registration():return json.loads((ROOT/PLAN).read_text())


def bundle(seed,source,profile,mode):
    if profile not in PROFILES:raise ValueError('UNREGISTERED_PROFILE')
    b=previous.bundle(seed,source,profile,mode)
    b['case_cap_s']=8. if mode=='smoke_resume' else 540.
    b['execution_bundle_id']=f'egomap64-{mode}-{profile}-{seed}-v1'
    b['options']['stage_schedule']=OPTION
    b['phase_budgets_s']={'B_approach':270.,'return':270.}
    b['admission']='egomap64 preregistered same checkpoints, full original leg budgets'
    return b


def run(a):
    a.stage_schedule=OPTION
    return bind(old.run,bundle=bundle,server_slot=partial(old.server_slot,limit=10),install=previous.install)(a)


def plan(out):
    checkpoints={r['seed']:r for r in registration()['checkpoints']}
    jobs=[]
    for seed in SEEDS:
        for profile in PROFILES:
            cp=checkpoints[seed]
            output=Path(out)/f'stage-{seed}-{profile}'
            cmd=[sys.executable,'-m','scripts.run_own_route_full_budget','--mode','stage','--seed',str(seed),
                 '--profile',profile,'--output',str(output)]
            jobs.append(dict(name=f'egomap64-{seed}-{profile}',mode='stage',seed=seed,profile=profile,status='QUEUED',
                output=str(output),checkpoint=cp['path'],checkpoint_sha256=cp['sha256'],command=cmd))
    return jobs


def batch(a):
    if platform.system()!='Linux' or os.getenv('UGRP_EXECUTION_HOST')!='oracle-x86':raise RuntimeError('ORACLE_ONLY')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    jobs=plan(out)
    old.dump(out/'batch-plan.json',dict(source_sha=ROOT.name,checkpoint_source_sha=registration()['checkpoint_source_sha'],host='oracle-x86',jobs=jobs))
    # All 12 checkpoint admissions before first comparison. No prepare reruns.
    for j in jobs:
        try:admit_checkpoint(Path(j['checkpoint']),j['seed'],OPTION,ROOT)
        except Exception as e:j.update(status='BLOCKED_ADMISSION',failure=repr(e))
    running=[];queue=[j for j in jobs if j['status']=='QUEUED']
    while queue or running:
        disk=shutil.disk_usage(out).free/2**30
        while queue and len(running)<10 and previous.available_gib()>=6 and disk>=2:
            j=queue.pop(0);stream=(out/(j['name']+'.log')).open('x')
            p=subprocess.Popen(j['command'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
            j.update(status='RUNNING',pid=p.pid);running.append((j,p,stream))
        for j,p,stream in running.copy():
            if p.poll() is None:continue
            stream.close();j['exit_code']=p.returncode
            result=Path(j['output'])/'result.json'
            j['status']=json.loads(result.read_text())['status'] if result.exists() else 'HOST_INTERRUPTED' if p.returncode in (-15,143) else 'HOST_ERROR_NO_RESULT'
            running.remove((j,p,stream))
        if queue and not running and disk<2:
            for j in queue:j.update(status='BLOCKED_DISK_CAPACITY',free_gib=disk)
            queue=[]
        old.dump(out/'batch-status.json',jobs)
        if queue or running:time.sleep(2)
    # Scoring is strictly post-hoc after all physical jobs terminal.
    from scripts.score_own_route_full_budget import score
    reports=[]
    for j in jobs:
        try:r=score(Path(j['output'])) if not j['status'].startswith('BLOCKED') else dict(samples=0)
        except Exception as e:r=dict(samples=0,scoring_error=repr(e))
        reports.append({**{k:j[k] for k in ('seed','profile','status')},**r})
    old.dump(out/'scores.json',reports)
    return 0


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('stage','smoke','batch'),required=True)
    p.add_argument('--seed',type=int,choices=SEEDS,default=SEEDS[0]);p.add_argument('--profile',choices=PROFILES,default='baseline')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='batch':return batch(a)
    a.checkpoint=Path(next(c['path'] for c in registration()['checkpoints'] if c['seed']==a.seed))
    if a.mode=='smoke':a.mode='smoke_resume'
    result=run(a);print(json.dumps(result),flush=True)
    return 0 if result['status']=='RECORDED' else 1

if __name__=='__main__':raise SystemExit(main())
