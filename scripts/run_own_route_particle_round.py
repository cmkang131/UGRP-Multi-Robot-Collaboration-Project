"""Registered egomap63 dependency batch: prepare all, then all valid x profiles."""
from pathlib import Path
from functools import partial
from types import SimpleNamespace
import argparse,importlib.util,json,os,platform,subprocess,sys,time
from harness.active_camera import bind
from harness.goal_candidate_preemption import install as preempt,OPTION
from harness.rbpf_candidate_audit import install as audit
from scripts import run_own_route_particle_stages as old

ROOT=Path(__file__).resolve().parents[1]
SEEDS=tuple(range(63001,63007))


def bundle(seed,source,profile,mode):
    if seed not in SEEDS:raise ValueError('UNREGISTERED_SEED')
    b=old.bundle(60011 if seed%2 else 60012,source,profile,mode)
    b['task']['seed']=seed;b['execution_bundle_id']=f'egomap63-{mode}-{profile}-{seed}-v1'
    b['options']['goal_preemption']=OPTION;b['candidate_audit']=True
    b['admission']='egomap63 six new dev seeds; frozen thresholds'
    return b


def controller(explorer):
    c=old.continuous.controller(explorer)
    preempt(c.explorer.navigator,goal_preemption=OPTION)
    return c


def install(g,**kwargs):return audit(old.install(g,**kwargs))


def run(args):
    continuous=SimpleNamespace(**{**vars(old.continuous),'controller':controller})
    return bind(old.run,bundle=bundle,server_slot=partial(old.server_slot,limit=10),install=install,continuous=continuous)(args)


def plan(out):
    out=Path(out)
    return [dict(name=f'egomap63-{mode}-{seed}'+('' if mode=='prepare' else '-'+p),mode=mode,
                 seed=seed,profile=p,status='QUEUED',output=str(out/(f'prepare-{seed}' if mode=='prepare' else f'stage-{seed}-{p}')))
            for mode in ('prepare','stage') for seed in SEEDS for p in (('baseline',) if mode=='prepare' else tuple(old.PROFILES))]


def available_gib():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):return int(line.split()[1])/1048576
    raise RuntimeError('NO_MEMORY_ADMISSION_MEASUREMENT')


def command(job,checkpoint=None):
    cmd=[sys.executable,'-m','scripts.run_own_route_particle_round','--mode',job['mode'],'--seed',str(job['seed']),
         '--profile',job['profile'],'--output',job['output']]
    if checkpoint:cmd+=['--checkpoint',str(checkpoint)]
    return cmd


def pool(jobs,out):
    running=[];queue=list(jobs)
    while queue or running:
        while queue and len(running)<10 and available_gib()>=6:
            j=queue.pop(0);stream=(out/(j['name']+'.log')).open('x')
            process=subprocess.Popen(j['command'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
            j.update(status='RUNNING',pid=process.pid);running.append((j,process,stream))
        for j,p,stream in running.copy():
            if p.poll() is None:continue
            stream.close();j['exit_code']=p.returncode
            result=Path(j['output'])/'result.json'
            j['status']=json.loads(result.read_text())['status'] if result.exists() else 'HOST_INTERRUPTED' if p.returncode in (-15,143) else 'HOST_ERROR_NO_RESULT'
            running.remove((j,p,stream))
        old.dump(out/'batch-status.json',ALL_JOBS)
        if queue and not running and available_gib()<6:print('MEMORY_WAIT_6GiB',flush=True)
        if queue or running:time.sleep(2)


def score_batch(jobs,out):
    spec=importlib.util.spec_from_file_location('score',ROOT/'experiments/2026-10-10-own-route-particle-stages/code/score.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    reports=[]
    for j in jobs:
        if j['mode']!='stage':continue
        if j['status'].startswith('BLOCKED'):
            r=dict(seed=j['seed'],profile=j['profile'],status=j['status'],samples=0)
        else:
            try:r=m.score(Path(j['output']))
            except Exception as e:r=dict(seed=j['seed'],profile=j['profile'],status='SCORING_ERROR',error=repr(e),samples=0)
        reports.append(r)
    old.dump(out/'scores.json',reports)


def batch(args):
    global ALL_JOBS
    if platform.system()!='Linux' or os.getenv('UGRP_EXECUTION_HOST')!='oracle-x86':raise RuntimeError('ORACLE_ONLY')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    ALL_JOBS=plan(out)
    for j in ALL_JOBS:j['command']=command(j)
    old.dump(out/'batch-plan.json',dict(source_sha=ROOT.name,host='oracle-x86',max_concurrent=10,jobs=ALL_JOBS))
    pool([j for j in ALL_JOBS if j['mode']=='prepare'],out)
    stages=[]
    for j in ALL_JOBS:
        if j['mode']!='stage':continue
        prep=out/f'prepare-{j["seed"]}'/'result.json'
        r=json.loads(prep.read_text()) if prep.exists() else {'status':'HOST_ERROR_NO_RESULT'}
        if r['status']=='RECORDED' and 'saved_checkpoint' in r:
            cp=prep.parent/'checkpoints'/r['saved_checkpoint']['file']
            j['command']=command(j,cp);j['checkpoint_sha256']=r['saved_checkpoint']['sha256'];stages.append(j)
        else:j['status']='BLOCKED_'+r['status']
    # Entire paired batch is fixed before launching the first comparison.
    old.dump(out/'paired-plan.json',ALL_JOBS)
    pool(stages,out);score_batch(ALL_JOBS,out)
    return 0


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('prepare','stage','smoke','batch'),required=True)
    p.add_argument('--seed',type=int,choices=SEEDS,default=SEEDS[0]);p.add_argument('--profile',choices=old.PROFILES,default='baseline')
    p.add_argument('--checkpoint',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='batch':return batch(a)
    if a.mode=='smoke':
        root=a.output;a.output=root/'save';a.mode='smoke_save';saved=run(a)
        if saved['status']!='RECORDED' or 'saved_checkpoint' not in saved:return 1
        a.checkpoint=a.output/'checkpoints'/saved['saved_checkpoint']['file'];a.output=root/'resume';a.mode='smoke_resume'
        r=run(a);old.dump(root/'smoke-summary.json',dict(save=saved,resume=r,new_sim_s=8.))
    else:r=run(a)
    return 0 if r['status']=='RECORDED' else 1

if __name__=='__main__':raise SystemExit(main())
