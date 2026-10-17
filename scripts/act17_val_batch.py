"""Finite matched ACT17 M/F/S VAL8, or separately frozen fresh FINAL40.

At most three actor processes and 24 physical worlds. Reference groups retain
exact compiled models. FINAL requires the actual completed VAL evidence.
"""
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
from act17_selection import validate_final_selection


def write(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enabled',action='store_true')
    for key in ['models-root','references','protocol','native-gate','out','stack','checker','stack-values','prior-rejections']:
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--split',choices=['validation','final'],default='validation')
    p.add_argument('--selection',type=Path)
    a=p.parse_args()
    if not a.enabled:p.error('ACT17 matched queue is default OFF')
    host=require_gcp2(training=True);source=frozen_source(ROOT);protocol=read(a.protocol);gate=read(a.native_gate)
    if gate.get('cohort')!='act17-v7-native' or not gate.get('passed') or gate.get('training_rgb') is not False:
        raise ValueError('new v7 camera-off native40 gate required')
    for receipt in gate['raw_results']:
        if sha256(receipt['path'])!=receipt['sha256']:raise ValueError('gate raw changed')
    wanted=set(protocol['validation8_seeds'] if a.split=='validation' else protocol['final_seeds']);plans=read(a.references/'plans.json')['episodes']
    inventory=read(a.references/'inventory.json');models={}
    for candidate in ['M','F','S']:
        folder=a.models_root/candidate/'actor';meta=read(folder/'adapter.json');provenance=meta['provenance']
        if (meta.get('schema')!='ugrp.act17.adapter.v1' or provenance.get('candidate')!=candidate or
                not provenance.get('training_complete') or provenance.get('step')!=protocol['training']['steps_round1'] or
                provenance.get('protocol_sha256')!=sha256(a.protocol)):
            raise ValueError('all matched complete M/F/S training required')
        models[candidate]=dict(path=str(folder),sha256=sha256(folder/'model.safetensors'))
    candidates=['M','F','S']
    if a.split=='final':
        if not a.selection:raise ValueError('frozen completed VAL evidence required')
        selection=read(a.selection);winner=selection['candidate']
        if winner not in models:raise ValueError('registered selected model required')
        validate_final_selection(selection,protocol,models[winner]['sha256']);candidates=[winner]
    requested=len(wanted)*len(candidates)
    purpose='matched3xVAL8 finite90SIM' if a.split=='validation' else 'frozen single-model FINAL40 finite90SIM'
    a.out.mkdir(parents=True,exist_ok=False)
    write(a.out/'rejection_table.json',dict(funnel=[dict(gate='requested_candidate_runs',passed=requested,rejected=0)],
        pending=requested,rejections=[],prior=dict(path=str(a.prior_rejections),sha256=sha256(a.prior_rejections)),raw=str(a.out),reproduce=sys.argv))
    queue=dict(flow='act_eval',cohort='act17-v7-native',source_sha=source,approved=True,
        stack_values=read(a.stack_values),models=models,split=a.split,requested_seeds=sorted(wanted),
        rejection_table=str(a.out/'rejection_table.json'),wall_cap=None,planned_worlds=24,teacher_fallback=False)
    queue.update(selected_candidates=candidates,selection=dict(path=str(a.selection),sha256=sha256(a.selection)) if a.selection else None)
    write(a.out/'queue.json',queue)
    physics=B/'runs/simalt3/warp-env/bin/python';python=B.parent/'ugrp-rl1b-act-env/bin/python'
    subprocess.run([str(physics),str(a.checker),str(a.out/'queue.json'),'--stack',str(a.stack),
        '--output',str(a.out/'current-stack-check.json')],check=True)
    subprocess.run([str(physics),str(ROOT/'scripts/act16w_native_groups.py'),'--enabled','--references',str(a.references),
        '--out',str(a.out/'exact-groups')],check=True)
    groups=[(i,[x for x in g['indices'] if plans[x]['seed'] in wanted])
            for i,g in enumerate(read(a.out/'exact-groups/model-groups.json')['groups'])]
    groups=[(i,g) for i,g in groups if g]
    if len([x for _,g in groups for x in g])!=len(wanted) or {plans[x]['seed'] for _,g in groups for x in g}!=wanted:
        raise ValueError('exact unique registered evaluation split required')
    if any(len(g)>24 for _,g in groups):groups=[(i*1000+j,g[j:j+24]) for i,g in groups for j in range(0,len(g),24)]
    pending=[(candidate,i,g) for i,g in groups for candidate in candidates]
    running=[];finished=[];stop={'requested':False};started=time.monotonic()
    lease=B/'leases'/('act17-'+a.split+'.json');start=datetime.now(timezone.utc).isoformat()
    with lease.open('x') as f:json.dump(dict(task='act17',pid=os.getpid(),start=start,expected_end=purpose,concurrency=0),f)
    for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,lambda *_:stop.update(requested=True))
    report=dict(status='running',complete=False,source_sha=source,cohort='act17-v7-native',host=host,models=models,
        split=a.split,N_requested=requested,started_utc=start,teacher_actions_executed=0,policy_privileged_inputs=0)
    try:
        while pending or running:
            if stop['requested']:raise InterruptedError('supervisor stop')
            for job in list(running):
                rc=job['process'].poll()
                if rc is not None:
                    job['log'].close();finished.append(dict(candidate=job['candidate'],indices=job['indices'],returncode=rc,out=str(job['out'])));running.remove(job)
                    if rc:raise RuntimeError('evaluation child HOST_ERROR; retain all unfinished starts')
                    subprocess.run([str(physics),str(ROOT/'scripts/act17_compact_records.py'),'--root',str(job['out']),
                        '--out',str(job['out'].parent/'storage-receipt.json')],check=True)
            foreign=sum(int(read(f).get('concurrency',0)) for f in lease.parent.glob('*.json') if f!=lease)
            capacity=min(24,40-foreign)-sum(len(j['indices']) for j in running)
            for candidate,i,g in list(pending):
                if len(running)>=3 or len(g)>capacity:continue
                folder=a.out/(candidate+'-'+str(i));folder.mkdir();out=folder/'evaluation'
                write(folder/'plans.json',dict(episodes=[plans[x] for x in g]));first=inventory[g[0]]
                command=[str(python),'-u',str(ROOT/'scripts/act17_evaluate_v7.py'),'--act17-v7','--enabled','--full-evaluation',
                    '--physics-python',str(physics),'--qualified-source',str(Q),'--teacher-source',str(T),
                    '--qualification',str(B/'runs/warp3/teacher-gate-qualification-r1.json'),
                    '--references',str(a.references/'per-world-references.json'),'--compiled-reference',first['actuator'],
                    '--compiled-geometry',first['geometry'],'--plans',str(folder/'plans.json'),'--actor-source',str(B/'src'/ACT_SHA),
                    '--checkpoint',models[candidate]['path'],'--out',str(out),'--protocol',str(a.protocol),'--split',a.split]
                if a.selection:command+=['--selection',str(a.selection)]
                log=(folder/'evaluation.log').open('x');proc=subprocess.Popen(command,cwd=Q,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
                    env={**os.environ,'UGRP_ACT16W_NATIVE_GATE':str(a.native_gate),'MUJOCO_GL':'osmesa',
                    'LP_NUM_THREADS':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'})
                write(folder/'launch.json',dict(argv=command,pid=proc.pid,source_sha=source))
                running.append(dict(candidate=candidate,indices=g,out=out,process=proc,log=log));pending.remove((candidate,i,g));capacity-=len(g)
            active=[dict(candidate=j['candidate'],pid=j['process'].pid,indices=j['indices']) for j in running]
            report.update(active=active,finished=finished,pending=pending,wall_s=time.monotonic()-started)
            write(a.out/'summary.json',report);write(lease,dict(task='act17',pid=os.getpid(),start=start,expected_end=purpose,
                concurrency=sum(len(j['indices']) for j in running),children=active));time.sleep(2)
        rows=[]
        for job in finished:
            value=read(Path(job['out'])/'summary.json')
            if not value.get('complete') or value.get('status') not in ['complete','cap_end']:raise ValueError('evaluation not fully observed')
            rows.extend(dict(candidate=job['candidate'],raw=job['out'],**row) for row in value['student_scores'])
        report.update(status='complete',complete=len(rows)==requested,rows=rows,candidates={c:dict(n=sum(r['task_success'] for r in rows if r['candidate']==c),
            N=sum(r['candidate']==c for r in rows)) for c in candidates})
        funnel=[]
        for c in candidates:
            eligible=[r for r in rows if r['candidate']==c];previous=len(wanted)
            for key in ['scored','issued_sequence_complete','lift_success','release_success','task_success']:
                if key!='scored':eligible=[r for r in eligible if r[key]]
                funnel.append(dict(candidate=c,gate=key,passed=len(eligible),rejected=previous-len(eligible)));previous=len(eligible)
        write(a.out/'rejection_table-final.json',dict(funnel=funnel,rejections=[dict(candidate=r['candidate'],seed=r['seed'],
            reason_category='cap_end' if r['cap_end'] else 'student_task_failure',reason=r.get('failure_reason') or 'physical_or_sequence_gate_failed',
            blocked_object='not_attributed_before_saved_frame_analysis',minimum_gap_m=None,minimum_gap_status='not_measured',raw=r['raw']) for r in rows if not r['task_success']],
            raw=str(a.out),reproduce=sys.argv))
    except BaseException as error:
        report.update(status='HOST_ERROR',complete=False,error=repr(error));raise
    finally:
        for job in running:
            if job['process'].poll() is None:
                os.killpg(job['process'].pid,signal.SIGINT)
                try:job['process'].wait(timeout=30)
                except subprocess.TimeoutExpired:os.killpg(job['process'].pid,signal.SIGKILL);job['process'].wait()
            job['log'].close()
        report['wall_s']=time.monotonic()-started;write(a.out/'summary.json',report)
        if lease.exists() and read(lease).get('pid')==os.getpid():lease.unlink()


if __name__=='__main__':main()
