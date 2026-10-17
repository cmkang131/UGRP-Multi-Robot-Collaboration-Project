"""Fresh40 gate -> verified dataset -> matched A/B training, no wall deadline.

2026-10-16 user via coordinator: remove worker wall/VM8h caps; retain idle20
and budget-stop. Optimizer steps and scientific SIM horizons remain fixed.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from act16w_runtime import require_gcp2,frozen_source,sha256

B=Path('/home/ugrp/ugrp-sim');ROOT=Path(__file__).resolve().parents[1]
PY=B.parent/'ugrp-rl1b-act-env/bin/python';ACT=B/'src/3f99d58c5ada0862e669ef4065c0ba957f1b4547'


def read(p):return json.loads(p.read_text())
def write(p,v):
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(v,indent=2)+'\n');tmp.replace(p)


def main():
    p=argparse.ArgumentParser();p.add_argument('--enabled',action='store_true')
    for k in ('batch','out'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--dataset-root',type=Path);a=p.parse_args()
    if not a.enabled:p.error('pipeline default OFF')
    host=require_gcp2(training=True);source=frozen_source(ROOT)
    if host['instance']!='ugrp-act-l4-gcp2':raise ValueError('owned L4 only')
    a.out.mkdir(parents=True,exist_ok=False)
    lease=B/'leases/act16w-train-pipeline.json';children=[]
    report=dict(status='WAIT_RECORDS',complete=False,source_sha=source,host=host,
        started_utc=datetime.now(timezone.utc).isoformat(),wall_cap=None,
        cap_decision='coordinator21:17: user removed all worker wall/VM8h caps; idle20/budget-stop retained',research_steps=0)
    with lease.open('x') as f:json.dump(dict(task='act16w-train-pipeline',pid=os.getpid(),start=report['started_utc'],expected_end='pending measured optimizer throughput; finite10000 steps per arm',concurrency=0,gpu_shared=False),f)
    write(B/'runs/act16w-active-training.json',dict(root=str(a.out),source_sha=source,pid=os.getpid()))
    stop={'requested':False};signal.signal(signal.SIGINT,lambda *_:stop.update(requested=True));signal.signal(signal.SIGTERM,lambda *_:stop.update(requested=True))
    def publish():write(a.out/'summary.json',report)
    def launch(name,args):
        if stop['requested']:raise InterruptedError('supervisor stop before '+name)
        log=(a.out/(name+'.log')).open('x')
        proc=subprocess.Popen([str(PY),'-u',*map(str,args)],cwd=B/'src/f0db6b1abb842ea65b71c433738210254f300a7c',stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','LP_NUM_THREADS':'1'})
        child=dict(name=name,proc=proc,log=log);children.append(child)
        write(a.out/(name+'-launch.json'),dict(pid=proc.pid,args=list(map(str,args)),source_sha=source));return child
    def wait(jobs):
        while any(j['proc'].poll() is None for j in jobs):
            if stop['requested']:
                for j in jobs:
                    if j['proc'].poll() is None and not j.get('signaled'):
                        os.killpg(j['proc'].pid,signal.SIGINT);j['signaled']=time.monotonic()
            report['active_children']=[dict(name=j['name'],pid=j['proc'].pid) for j in jobs if j['proc'].poll() is None];publish();time.sleep(2)
        for j in jobs:
            j['log'].close()
            if j['proc'].returncode:raise RuntimeError(j['name']+' failed; immutable log retained')
        if stop['requested']:raise InterruptedError('supervisor stop after children')
    try:
        publish()
        while True:
            if stop['requested']:raise InterruptedError('supervisor stop waiting records')
            batch=read(a.batch/'summary.json')
            if batch['status']!='running':break
            report['record_progress']=dict(finished=len(batch.get('finished',[])),active=batch.get('active',[]));publish();time.sleep(5)
        if not batch['complete']:raise ValueError('record dispatch incomplete: '+batch['status'])
        E=ROOT/'experiments/2026-10-16-act16w/resume2';records=a.dataset_root or a.out/'recorded-dataset'
        report.update(status='DATASET_AUDIT',dataset_root=str(records));publish()
        if a.dataset_root:
            manifest_path=records/'dataset/manifest.json';manifest=read(manifest_path)
            if not manifest['complete']:raise ValueError('existing dataset not complete')
            checked=0
            for name,digest in manifest['files'].items():
                path=(records/'dataset'/name).resolve()
                if not path.is_relative_to((records/'dataset').resolve()) or sha256(path)!=digest:raise ValueError('existing dataset hash mismatch '+name)
                checked+=1
            write(a.out/'reused-dataset-verification.json',dict(passed=True,files=checked,manifest_sha256=sha256(manifest_path),original_dataset_source=manifest.get('source_sha'),source_sha=source,scope='complete pre-restart dataset; all manifest file hashes verified; no re-recording'))
        else:
            wait([launch('dataset',[ROOT/'scripts/act16w_dataset.py','--enabled','--root',records,'--batch',a.batch,'--selection',E/'record-selection.json','--protocol',E/'comparison-protocol-v2.json','--act-source',ACT])])
        gate=read(records/'fresh-recording-gate.json');report['fresh_teacher']=dict(n=gate['n'],N=gate['N'])
        admission=a.out/'data-admission'
        wait([launch('admit',[ROOT/'scripts/act16w_admit_dataset.py','--approve-reviewed-records','--dataset-root',records,'--record-plans',B/'runs/act16w-resume2-record-references/plans.json','--out',admission])])
        common=[ROOT/'scripts/train_act16w.py','--act-source',ACT,'--dataset',records/'dataset','--admission',admission/'training-admission.json','--schedule-steps','10000','--seed','20261015']
        report['status']='SMOKE_A_B';publish();jobs=[]
        for arm,mode in [('A','off'),('B','wheel_pulse_train_mean')]:
            jobs.append(launch('smoke-'+arm,[*common,'--output',a.out/f'{arm}-smoke','--stage','smoke','--steps','300','--history-causal-split-v1',mode]))
        wait(jobs)
        for arm in ('A','B'):
            smoke=read(a.out/f'{arm}-smoke/summary.json')
            if not smoke['complete'] or not smoke['readback_verified']:raise ValueError('matching smoke not complete '+arm)
        report['status']='MAIN_A_B';publish();jobs=[]
        for arm,mode in [('A','off'),('B','wheel_pulse_train_mean')]:
            smoke_path=a.out/f'{arm}-smoke/summary.json';smoke=read(smoke_path)
            jobs.append(launch('main-'+arm,[*common,'--output',a.out/f'{arm}-main','--stage','main','--steps','10000','--history-causal-split-v1',mode,'--smoke-summary',smoke_path,'--resume',smoke['last_checkpoint']]))
        wait(jobs)
        arms={arm:read(a.out/f'{arm}-main/summary.json') for arm in ('A','B')}
        report.update(status='A_B_TRAINED' if all(x['complete'] for x in arms.values()) else 'A_B_INCOMPLETE',complete=all(x['complete'] for x in arms.values()),arms={k:dict(steps=v['steps_completed'],complete=v['complete'],checkpoint=v.get('last_checkpoint')) for k,v in arms.items()},next='validation5 -> C curriculum -> DAgger -> frozen final40; no physical student success inferred')
    except BaseException as error:
        report.update(status='SUPERVISOR_STOP' if isinstance(error,InterruptedError) else 'HOST_ERROR',complete=False,error=repr(error))
        if not isinstance(error,InterruptedError):raise
    finally:
        for j in children:
            if j['proc'].poll() is None:
                os.killpg(j['proc'].pid,signal.SIGINT)
                try:j['proc'].wait(timeout=90)
                except subprocess.TimeoutExpired:os.killpg(j['proc'].pid,signal.SIGKILL);j['proc'].wait()
            if not j['log'].closed:j['log'].close()
        report['actual_arms']={}
        for arm in ('A','B'):
            for stage in ('smoke','main'):
                path=a.out/f'{arm}-{stage}/summary.json'
                if path.exists():
                    row=read(path);old=report['actual_arms'].get(arm,{})
                    report['actual_arms'][arm]=dict(stage=stage,steps=max(row['steps_completed'],old.get('steps',0)),complete=row['complete'],status=row['status'],checkpoint=row.get('last_checkpoint'))
        report['research_steps']=sum(r['steps'] for r in report['actual_arms'].values());report['ended_utc']=datetime.now(timezone.utc).isoformat();report['vm_stop_attempted']=False;publish()
        if lease.exists() and read(lease).get('pid')==os.getpid():lease.unlink()


if __name__=='__main__':main()
