"""Finite v7 gate/record owner, <=24 worlds, native0, immutable shared sources.

Current-stack declarations are checked before rollout. Original per-world Score,
input audits and native options are recounted afterwards. Recording is a separate
external JPEG sink and is never enabled during gate success measurement.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time

from act16w_runtime import require_gcp2,frozen_source,sha256
from act17_open_loop import read
from act17_v7 import ROOT,B,Q,T


def write(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['gate','record'],required=True)
    for name in ['protocol','references','out','stack','checker','stack-values','prior-rejections']:
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--native-gate',type=Path)
    p.add_argument('--indices',help='explicit subset, e.g. recording pilots0,1,2,3')
    a=p.parse_args();host=require_gcp2(training=True);source=frozen_source(ROOT)
    # Existing AGENTS host resource floors; these are not policy tolerances.
    memory={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()}
    if memory['MemAvailable']<6*1024**3 or shutil.disk_usage(B).free<8*1024**3:
        raise RuntimeError('existing host floors require available RAM6GiB and disk8GiB')
    protocol=read(a.protocol);plans=read(a.references/'plans.json')['episodes']
    if [v['seed'] for v in plans]!=protocol[a.stage+'_seeds']:
        raise ValueError('exact ordered v7 protocol starts required')
    indices=list(map(int,a.indices.split(','))) if a.indices else list(range(len(plans)))
    if len(set(indices))!=len(indices) or any(not 0<=i<len(plans) for i in indices):
        raise ValueError('unique valid requested indices required')
    gate=None
    if a.stage=='record':
        gate=read(a.native_gate) if a.native_gate else {}
        if not gate.get('passed') or gate.get('n',0)<38 or gate.get('N')!=40 or gate.get('training_rgb') is not False or gate.get('cohort')!='act17-v7-native':
            raise ValueError('new camera-off v7 native40 gate required before recording')
        for receipt in gate['raw_results']:
            if sha256(receipt['path'])!=receipt['sha256']:
                raise ValueError('v7 gate raw evidence changed')
    inventory=read(a.references/'inventory.json')
    a.out.mkdir(parents=True,exist_ok=False)
    write(a.out/'rejection_table.json',dict(funnel=[dict(gate='requested',passed=len(indices),rejected=0),
        dict(gate='compiled_references',passed=len(indices),rejected=0)],pending=len(indices),
        prior_analysis=dict(path=str(a.prior_rejections),sha256=sha256(a.prior_rejections)),raw=str(a.out),reproduce=sys.argv))
    # Legacy backend gate binder checks its own immutable SHA. The separate
    # adapter SHA/checker bind the new scene and user-authorized v7 cohort.
    queue=dict(flow='teacher_gate' if a.stage=='gate' else 'record',status='APPROVED_PINNED',approved=True,
        source_sha=Q.name,adapter_source_sha=source,cohort='act17-v7-native',
        review_detail='REVIEW_SKIPPED_BY_USER (10/15 run-first rule)',
        approval_evidence='AGENTS dev run-first; coordinator ops-alert v7 gate40 -> record -> train, no v4 exception',
        plan_sha256=sha256(a.references/'plans.json'),references_sha256=sha256(a.references/'per-world-references.json'),
        rejection_table=str(a.out/'rejection_table.json'),rejection_table_sha256=sha256(a.out/'rejection_table.json'),
        approved_episode_indices=indices,required_success_rate=.95,minimum_independent_episodes=40,
        stack_values=read(a.stack_values),wall_cap=None,training_rgb=a.stage=='record')
    write(a.out/'queue.json',queue)
    py=B/'runs/simalt3/warp-env/bin/python'
    subprocess.run([str(py),str(a.checker),str(a.out/'queue.json'),'--stack',str(a.stack),
        '--output',str(a.out/'current-stack-check.json')],check=True)
    groups_output=a.out/'exact-groups'
    subprocess.run([str(py),str(ROOT/'scripts/act16w_native_groups.py'),'--enabled','--references',str(a.references),
        '--out',str(groups_output)],check=True)
    groups=[(i,[x for x in g['indices'] if x in indices]) for i,g in enumerate(read(groups_output/'model-groups.json')['groups'])]
    pending=[(i,g) for i,g in groups if g]
    if any(len(g)>24 for _,g in pending):
        pending=[(1000*i+j,g[j:j+24]) for i,g in pending for j in range(0,len(g),24)]
    lease=B/'leases/act17.json'
    if lease.exists():
        old=read(lease)
        if old.get('task')!='act17':raise ValueError('foreign lease name collision')
    else:write(lease,dict(task='act17',pid=os.getpid()))
    stop={'requested':False}
    for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,lambda *_:stop.update(requested=True))
    running={};finished=[];start=time.monotonic()
    report=dict(status='running',complete=False,source_sha=source,cohort='act17-v7-native',host=host,
        stage=a.stage,N_requested=len(indices),requested_seeds=[plans[i]['seed'] for i in indices],
        contact_profile='warp_native_contact_v1',training_rgb=a.stage=='record',wall_cap=None,
        started_utc=datetime.now(timezone.utc).isoformat())
    def publish():
        report.update(active=[dict(group=i,pid=v['p'].pid,indices=v['indices']) for i,v in running.items()],
            finished=finished,pending=[dict(group=i,indices=g) for i,g in pending],wall_s=time.monotonic()-start)
        write(a.out/'summary.json',report)
        write(lease,dict(task='act17',pid=os.getpid(),start=report['started_utc'],expected_end='finite v7 '+a.stage+', no wall deadline',
            concurrency=sum(len(v['indices']) for v in running.values()),children=report['active']))
    try:
        while pending or running:
            if stop['requested']:raise InterruptedError('explicit supervisor stop')
            for i,job in list(running.items()):
                if job['p'].poll() is not None:
                    job['log'].close();finished.append(dict(group=i,indices=job['indices'],returncode=job['p'].returncode,raw=str(job['folder'])));del running[i]
                    if job['p'].returncode:stop['requested']=True
            foreign=0
            for f in lease.parent.glob('*.json'):
                if f!=lease:foreign+=int(read(f).get('concurrency',0))
            capacity=min(24,40-foreign)-sum(len(v['indices']) for v in running.values())
            for i,g in list(pending):
                if len(g)>capacity:continue
                folder=a.out/f'group-{i:03d}';folder.mkdir();controller=folder/'controller';first=inventory[g[0]]
                runner=['--physics-backend','mjwarp_batch_v1','--teacher-source',str(T),
                    '--plan',str(a.references/'plans.json'),'--episode',str(g[0]),'--world-episodes',','.join(map(str,g)),
                    '--nworld',str(len(g)),'--cap-s','90','--compiled-reference-v1',first['actuator'],
                    '--compiled-geometry-312-v1',first['geometry'],'--per-world-model-references-v1',str(a.references/'per-world-references.json'),
                    '--scene-v5-v1','--numpy-teacher-v1','--batch-sleep-v1','--native-sleep-policy-compat-v1',
                    '--vm-hourly-usd','1.096','--out',str(controller)]
                cmd=[str(py),'-u',str(ROOT/'scripts/act17_v7.py'),'--enabled','--action','launch','--','--enabled','--mode',
                    'teacher' if a.stage=='gate' else 'record']
                if a.stage=='gate':runner+=['--teacher-gate-queue',str(a.out/'queue.json')]
                else:
                    cmd+=['--native-gate',str(a.native_gate)]
                    write(folder/'runner-args.json',runner)
                    runner=['--enabled','--qualified-source',str(Q),'--teacher-source',str(T),'--qualification',
                        str(B/'runs/warp3/teacher-gate-qualification-r1.json'),'--runner-args-json',str(folder/'runner-args.json'),
                        '--stage','pilot','--out',str(folder/'capture')]
                cmd+=['--',*runner]
                log=(folder/'run.log').open('x')
                proc=subprocess.Popen(cmd,cwd=Q,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
                    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1'})
                write(folder/'launch.json',dict(argv=cmd,pid=proc.pid,source_sha=source))
                running[i]=dict(p=proc,log=log,indices=g,folder=folder);pending.remove((i,g));capacity-=len(g)
            publish();time.sleep(2)
        rows=[];raw=[];profiles=[]
        for job in finished:
            folder=Path(job['raw'])/'controller'
            native=read(folder/'native-contact.json')
            if native['gpu_noslip']!=0 or any(native['cpu_noslip']):raise ValueError('native0 runtime lost')
            profiles.append(dict(path=str(folder/'native-contact.json'),sha256=sha256(folder/'native-contact.json')))
            for wi,index in enumerate(job['indices']):
                path=folder/f'world-{wi:03d}/result.json';value=read(path);actual=path if path.exists() else Path(str(path)+'.zst')
                audit=value['input_audit'];ok=value['status']=='complete' and value['physical_success'] and not value['cap_end'] and all(audit[k]==0 for k in ['invisible_measurements','held_world_reads'])
                rows.append(dict(seed=plans[index]['seed'],kind=plans[index]['kind'],success=bool(ok),
                    lift_success=value.get('lift_success',False),release_success=value.get('release_success',False),cap_end=value.get('cap_end',False),
                    input_audit=audit,reason='success' if ok else value.get('reason') or value.get('teacher',{}).get('command_result') or 'teacher_physical_or_input_failure',raw=str(actual)))
                raw.append(dict(path=str(actual),sha256=sha256(actual)))
        n=sum(x['success'] for x in rows);N=len(rows)
        report.update(status='PASS' if N==len(indices) and n/N>=.95 else 'FAIL',complete=N==len(indices),n=n,N=N,
            passed=N==len(indices) and n/N>=.95,rows=rows,raw_results=raw,runtime_profiles=profiles,
            input_audit_violations=sum(sum(r['input_audit'][k] for k in ['invisible_measurements','held_world_reads']) for r in rows))
        funnel=[dict(gate='requested',passed=len(indices),rejected=0),dict(gate='raw_results',passed=N,rejected=len(indices)-N)]
        eligible=rows
        for key in ['lift_success','release_success','success']:
            previous=len(eligible);eligible=[r for r in eligible if r[key]];funnel.append(dict(gate=key,passed=len(eligible),rejected=previous-len(eligible)))
        write(a.out/'rejection_table-final.json',dict(funnel=funnel,rejections=[dict(reason_category='cap_end' if r['cap_end'] else 'teacher_failure',reason=r['reason'],seed=r['seed'],blocked_object='not_attributed_before_saved_frame_analysis',minimum_gap_m=None,minimum_gap_status='not_measured',raw=r['raw']) for r in rows if not r['success']],raw=str(a.out),reproduce=sys.argv))
        write(a.out/'gate-recount.json',report)
    except BaseException as error:
        report.update(status='HOST_ERROR',complete=False,error=repr(error));raise
    finally:
        for job in running.values():
            if job['p'].poll() is None:
                os.killpg(job['p'].pid,signal.SIGINT)
                try:job['p'].wait(timeout=30)
                except subprocess.TimeoutExpired:os.killpg(job['p'].pid,signal.SIGTERM);job['p'].wait()
            job['log'].close()
        report['wall_s']=time.monotonic()-start;write(a.out/'summary.json',report)
        if lease.exists() and read(lease).get('pid')==os.getpid():lease.unlink()


if __name__=='__main__':main()
