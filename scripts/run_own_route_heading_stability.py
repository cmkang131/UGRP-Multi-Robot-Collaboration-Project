"""egomap65: all 24 frozen checkpoints x populations x heading, oracle only."""
import argparse,json,math,os,platform,shutil,signal,subprocess,sys,time
from pathlib import Path
from functools import partial
from types import SimpleNamespace
from harness.active_camera import bind
from harness.path_heading_stability import OPTION,PARAMETERS,install
from scripts import run_own_route_full_budget as previous
from scripts import run_own_route_particle_stages as old
from scripts.own_route_budget_schedule import OPTION as SCHEDULE,admit_checkpoint

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'experiments/2026-10-10-own-route-heading-stability/batch-plan.json'
SEEDS=previous.SEEDS

def registration():return json.loads(PLAN.read_text())

def alarm_seconds(budget=540.):
    p=registration()['host_budget']
    return math.ceil(budget*p['measured_max_wall_per_sim']*p['margin']+p['overhead_s'])

def bundle(seed,source,profile,mode,*,heading_stability='off'):
    b=previous.bundle(seed,source,profile,mode)
    b['execution_bundle_id']=f'egomap65-{mode}-{profile}-{heading_stability}-{seed}-v1'
    b['options']['heading_stability']=heading_stability
    b['heading_stability_parameters']=dict(PARAMETERS) if heading_stability!= 'off' else None
    b['host_alarm_s']=alarm_seconds(b['case_cap_s'])
    b['admission']='egomap65 preregistered factorial DEV, same six checkpoints'
    return b

def run(a):
    a.stage_schedule=SCHEDULE
    def load(path,out):
        backend,c,start,tick,cp=old.checkpoint_load(path,out)
        install(c.heading_host,heading_stability=a.heading_stability)
        return backend,c,start,tick,cp
    b=bundle(a.seed,ROOT.name,a.profile,a.mode,heading_stability=a.heading_stability)
    # Private alarm adapter: old runner/code/off branch remain byte-identical.
    def alarm(n):return signal.alarm(b['host_alarm_s'] if n else 0)
    result=bind(old.run,bundle=lambda *args:b,checkpoint_load=load,
        server_slot=partial(old.server_slot,limit=10),install=previous.previous.install,
        signal=SimpleNamespace(**{**vars(signal),'alarm':alarm}))(a)
    return result

def plan(out):
    out=Path(out);jobs=[];cps={c['seed']:c for c in registration()['checkpoints']}
    for r in registration()['jobs']:
        j={k:r[k] for k in ('name','seed','profile','heading_stability')}
        j.update(status='QUEUED',output=str(out/j['name']),checkpoint=cps[j['seed']]['path'])
        j['command']=[sys.executable,'-m','scripts.run_own_route_heading_stability','--mode','stage',
            '--seed',str(j['seed']),'--profile',j['profile'],'--heading-stability',j['heading_stability'],'--output',j['output']]
        jobs.append(j)
    return jobs

def score_batch(jobs,out):
    from scripts.score_own_route_full_budget import score
    reports=[]
    for j in jobs:
        try:r=score(Path(j['output'])) if not j['status'].startswith('BLOCKED') else dict(samples=0)
        except Exception as e:r=dict(samples=0,scoring_error=repr(e))
        reports.append({**{k:j[k] for k in ('seed','profile','status','heading_stability')},**r})
    old.dump(out/'scores.json',reports)

def batch(a):
    if platform.system()!='Linux' or os.getenv('UGRP_EXECUTION_HOST')!='oracle-x86':raise RuntimeError('ORACLE_ONLY')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);jobs=plan(out)
    old.dump(out/'batch-plan.json',dict(source_sha=ROOT.name,host='oracle-x86',checkpoint_source_sha=registration()['checkpoint_source_sha'],
        max_concurrent=10,host_alarm_s=alarm_seconds(),jobs=jobs))
    for j in jobs:
        try:admit_checkpoint(Path(j['checkpoint']),j['seed'],SCHEDULE,ROOT)
        except Exception as e:j.update(status='BLOCKED_ADMISSION',failure=repr(e))
    running=[];queue=[j for j in jobs if j['status']=='QUEUED']
    while queue or running:
        disk=shutil.disk_usage(out).free/2**30
        while queue and len(running)<10 and previous.previous.available_gib()>=6 and disk>=2:
            j=queue.pop(0);stream=(out/(j['name']+'.log')).open('x')
            p=subprocess.Popen(j['command'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
            j.update(status='RUNNING',pid=p.pid);running.append((j,p,stream))
        for j,p,stream in running.copy():
            if p.poll() is None:continue
            stream.close();j['exit_code']=p.returncode;path=Path(j['output'])/'result.json'
            j['status']=json.loads(path.read_text())['status'] if path.exists() else 'HOST_INTERRUPTED' if p.returncode in (-15,143) else 'HOST_ERROR_NO_RESULT'
            running.remove((j,p,stream))
        if queue and not running and disk<2:
            for j in queue:j.update(status='BLOCKED_DISK_CAPACITY',free_gib=disk)
            queue=[]
        old.dump(out/'batch-status.json',jobs)
        if queue or running:time.sleep(2)
    score_batch(jobs,out)
    return 0

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('stage','smoke','batch'),required=True)
    p.add_argument('--seed',type=int,choices=SEEDS,default=SEEDS[0]);p.add_argument('--profile',choices=('baseline','a'),default='baseline')
    p.add_argument('--heading-stability',choices=('off',OPTION),default='off');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.mode=='batch':return batch(a)
    a.checkpoint=Path(next(c['path'] for c in registration()['checkpoints'] if c['seed']==a.seed))
    if a.mode=='smoke':a.mode='smoke_resume'
    r=run(a);print(json.dumps(r),flush=True)
    return 0 if r['status']=='RECORDED' else 1
if __name__=='__main__':raise SystemExit(main())
