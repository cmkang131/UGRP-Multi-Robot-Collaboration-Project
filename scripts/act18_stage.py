"""Finite TRAIN4/VAL8/FINAL40 stage; exact compiled references and raw recount."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256,ACT_SHA
from act17_data import read
from act17_v7 import ROOT,B,Q,T
from act18_diagnose import write
from act18_evaluate import allowed_seeds


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled',action='store_true')
    p.add_argument('--stage',choices=['train','validation','final'],required=True)
    p.add_argument('--baseline-act17',action='store_true')
    p.add_argument('--selection',type=Path)
    for key in ('checkpoint','references','protocol','native-gate','out','stack-values','prior-rejections'):
        p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    if not a.enabled:
        p.error('ACT18 stage is default OFF')
    host=require_gcp2(training=True);source=frozen_source(ROOT)
    protocol=read(a.protocol);meta=read(a.checkpoint/'adapter.json');digest=sha256(a.checkpoint/'model.safetensors')
    wanted=allowed_seeds(protocol,a.stage,read(a.selection) if a.selection else {},digest)
    plans=read(a.references/'plans.json')['episodes'];inventory=read(a.references/'inventory.json')
    if {p['seed'] for p in plans if p['seed'] in wanted}!=wanted:
        raise ValueError('exact stage reference seeds required')
    a.out.mkdir(parents=True,exist_ok=False)
    write(a.out/'rejection_table.json',dict(funnel=[dict(gate='requested',passed=len(wanted),rejected=0)],
        pending=len(wanted),prior=dict(path=str(a.prior_rejections),sha256=sha256(a.prior_rejections)),raw=str(a.out),reproduce=sys.argv))
    queue=dict(flow='act_eval',source_sha=source,host=host,stage=a.stage,
        checkpoint_sha256=digest,candidate=meta['provenance']['candidate'],
        stack_values=read(a.stack_values),rejection_table=str(a.out/'rejection_table.json'),
        requested_seeds=sorted(wanted),wall_cap=None,max_worlds=24,
        teacher_fallback=False,policy_privileged_inputs=0)
    write(a.out/'queue.json',queue)
    subprocess.run([sys.executable,str(ROOT/'scripts/check_current_stack.py'),str(a.out/'queue.json'),
        '--flow','act_eval','--output',str(a.out/'current-stack-check.json')],check=True)
    physics=B/'runs/simalt3/warp-env/bin/python'
    subprocess.run([str(physics),str(ROOT/'scripts/act16w_native_groups.py'),'--enabled',
        '--references',str(a.references),'--out',str(a.out/'exact-groups')],check=True)
    groups=[(i,[x for x in g['indices'] if plans[x]['seed'] in wanted])
        for i,g in enumerate(read(a.out/'exact-groups/model-groups.json')['groups'])]
    pending=[(i,g) for i,g in groups if g]
    if any(len(g)>24 for _,g in pending):
        pending=[(i*1000+j,g[j:j+24]) for i,g in pending for j in range(0,len(g),24)]
    lease=B/'leases'/('act18-eval-'+meta['provenance']['candidate']+'-'+a.stage+'.json')
    with lease.open('x') as f:
        json.dump(dict(task='act18',pid=os.getpid(),start=datetime.now(timezone.utc).isoformat(),
            expected_end='finite '+a.stage+'; no wall deadline',concurrency=0),f)
    running=[];finished=[];stop={'requested':False};started=time.monotonic()
    report=dict(status='running',complete=False,stage=a.stage,source_sha=source,host=host,
        candidate=meta['provenance']['candidate'],checkpoint_sha256=digest)
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:stop.update(requested=True))
    try:
        while pending or running:
            if stop['requested']:
                raise InterruptedError('supervisor stop')
            for job in list(running):
                rc=job['p'].poll()
                if rc is None:
                    continue
                job['log'].close();running.remove(job);finished.append(str(job['folder']/'evaluation'))
                if rc:
                    raise RuntimeError('evaluation child HOST_ERROR')
            foreign=sum(int(read(f).get('concurrency',0)) for f in lease.parent.glob('*.json') if f!=lease)
            capacity=min(24,40-foreign)-sum(len(j['indices']) for j in running)
            for group,indices in list(pending):
                if len(running)>=4 or len(indices)>capacity:
                    continue
                folder=a.out/f'group-{group:03d}';folder.mkdir();first=inventory[indices[0]]
                write(folder/'plans.json',dict(episodes=[plans[i] for i in indices]))
                cmd=[sys.executable,'-u',str(ROOT/'scripts/act18_evaluate.py'),'--act18-reference-v1',
                    '--stage',a.stage,'--enabled','--full-evaluation',
                    '--physics-python',str(physics),'--qualified-source',str(Q),'--teacher-source',str(T),
                    '--qualification',str(B/'runs/warp3/teacher-gate-qualification-r1.json'),
                    '--references',str(a.references/'per-world-references.json'),
                    '--compiled-reference',first['actuator'],'--compiled-geometry',first['geometry'],
                    '--plans',str(folder/'plans.json'),'--actor-source',str(B/'src'/ACT_SHA),
                    '--checkpoint',str(a.checkpoint),'--out',str(folder/'evaluation'),
                    '--protocol',str(a.protocol),'--split','final' if a.stage=='final' else 'validation']
                if a.baseline_act17:
                    cmd+=['--baseline-act17']
                if a.selection:
                    cmd+=['--fit-selection',str(a.selection)]
                log=(folder/'run.log').open('x')
                proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,cwd=Q,start_new_session=True,
                    env={**os.environ,'UGRP_ACT16W_NATIVE_GATE':str(a.native_gate),'MUJOCO_GL':'osmesa',
                        'LP_NUM_THREADS':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'})
                write(folder/'launch.json',dict(argv=cmd,pid=proc.pid,source_sha=source))
                running.append(dict(p=proc,log=log,indices=indices,folder=folder));pending.remove((group,indices));capacity-=len(indices)
            report.update(active=[dict(pid=j['p'].pid,indices=j['indices']) for j in running],pending=pending,
                finished=finished,wall_s=time.monotonic()-started)
            write(a.out/'summary.json',report)
            write(lease,dict(task='act18',pid=os.getpid(),expected_end='finite '+a.stage+', no wall cap',
                concurrency=sum(len(j['indices']) for j in running),children=report['active']))
            for job in running:
                progress=job['folder']/'evaluation/progress.json'
                dest=job['folder']/'first30.json'
                if progress.exists() and not dest.exists() and read(progress).get('elapsed_SIM',0)>=30:
                    value=read(progress)
                    owner=job['folder']/'evaluation/owner/progress.json'
                    timing=read(owner) if owner.exists() else {}
                    sim=min(timing['ticks'])*.1 if timing.get('ticks') else value['elapsed_SIM']
                    wall=timing.get('loop_wall_s')
                    write(dest,dict(**value,first30_observed=True,mode='record_only',source=str(progress),
                        raw_owner_timing=timing,wall_s=wall,sim_s=sim,nworld=len(job['indices']),
                        metric='wall_s/(sim_s*nworld)',metric_value=wall/(sim*len(job['indices'])) if wall is not None else None,
                        timing_status='observed' if wall is not None else 'not_available_in_owner_progress'))
            time.sleep(2)
        recount=a.out/'raw-recount.json'
        subprocess.run([sys.executable,str(ROOT/'scripts/act18_recount.py'),'--runs',*finished,
            '--stage',a.stage,'--checkpoint',str(a.checkpoint),'--out',str(recount)],check=True)
        actual=read(recount)
        if actual['N']!=len(wanted):
            raise ValueError('incomplete stage recount')
        report.update(status='PASS' if actual['n']==len(wanted) else 'NOT_READY',complete=True,
            n=actual['n'],N=actual['N'],raw_recount=dict(path=str(recount),sha256=sha256(recount)))
        write(a.out/'rejection_table-final.json',dict(funnel=actual['funnel'],
            rejections=[r for r in actual['rows'] if not r['success']],raw=actual['raw'],reproduce=sys.argv))
    except BaseException as error:
        report.update(status='SUPERVISOR_STOP' if isinstance(error,InterruptedError) else 'HOST_ERROR',error=repr(error),complete=False)
        raise
    finally:
        for job in running:
            if job['p'].poll() is None:
                os.killpg(job['p'].pid,signal.SIGINT);job['p'].wait()
            job['log'].close()
        report['wall_s']=time.monotonic()-started;write(a.out/'summary.json',report)
        if lease.exists() and read(lease).get('pid')==os.getpid():
            lease.unlink()


if __name__=='__main__':
    main()
