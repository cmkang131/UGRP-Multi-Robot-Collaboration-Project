"""Finite MJWarp recording dispatcher after two inspected full pilots.

Uses the unchanged qualified controller, exact compatibility groups, native
camera and external record API. No automatic data/training admission. The
optional speed exception is recorded; task8h and all quality gates remain.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from act16w_runtime import frozen_source,require_gcp2,sha256

B=Path('/home/ugrp/ugrp-sim');Q=B/'src/f0db6b1abb842ea65b71c433738210254f300a7c';T=B/'src/warp1-teacher-snapshot-6f057f7e';API=B/'src/0362037280c6cbc4677f70366db43b9892b23690';PY=B/'runs/simalt3/warp-env/bin/python';GATE=B/'runs/warp3/teacher-gate-qualification-r1.json'

def read(p):
    return json.loads(p.read_text()) if p.exists() else json.loads(subprocess.check_output(['zstd','-dc',str(p)+'.zst']))

def write(p,v):
    t=p.with_suffix('.tmp');t.write_text(json.dumps(v,indent=2)+'\n');t.replace(p)

def main():
    p=argparse.ArgumentParser();p.add_argument('--enabled',action='store_true')
    for k in ['root','references','groups','approval','capacity-receipt','selection']:p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--max-worlds',type=int,default=24);p.add_argument('--foreign-cpu-worlds',type=int,required=True)
    p.add_argument('--deadline-utc',required=True);p.add_argument('--speed-gate-override',default='');a=p.parse_args()
    if not a.enabled or not 1<=a.max_worlds<=40 or not 0<=a.foreign_cpu_worlds<=40:p.error('explicit opt-in and finite capacity required')
    host=require_gcp2()
    if host['instance']!='ugrp-act-l4-gcp2':raise ValueError('qualified L4 only')
    source=frozen_source(Path(__file__).resolve().parents[1]);proof=read(a.approval)
    if proof.get('approved') is not True or proof.get('source_sha')!=Q.name:raise ValueError('source-bound recording approval required')
    for item in proof['pilot_checks']:
        if sha256(item['path'])!=item['sha256']:raise ValueError('pilot check hash mismatch')
        audit=read(Path(item['path']))
        if not audit['passed'] or any(not w['physical_success'] or w['duration_sim_s']<30 or w['cap_end'] for w in audit['worlds']):raise ValueError('inspected complete successful native pilot required')
    a.root.mkdir(parents=True,exist_ok=False);inventory=read(a.references/'inventory.json');plans=read(a.references/'plans.json')
    selection=read(a.selection);selected=selection['selected_indices']
    if len(selected)!=len(set(selected)) or len(selected)<40 or not {1,2}<=set(selected):raise ValueError('unique predeclared >=40 recording starts required')
    groups=[[i for i in g['indices'] if i in selected and i not in (1,2)] for g in read(a.groups/'model-groups.json')['groups']]
    pending=sorted([(j,g) for j,g in enumerate(groups) if g],key=lambda x:(-len(x[1]),x[0]));running={};finished=[];start=time.monotonic();deadline=datetime.fromisoformat(a.deadline_utc).timestamp()
    # First task GPU use05:47Z; eight-hour user cap, regardless of VM reboot.
    if deadline>datetime.fromisoformat('2026-10-16T13:47:00.019842+00:00').timestamp():raise ValueError('task8h cap cannot be extended by reboot')
    lease=B/'leases/act16w-record.json';report=dict(status='running',source_sha=source,host=host,started_utc=datetime.now(timezone.utc).isoformat(),groups_total=len(pending),planned_fresh_seeds=len(selected),selection_sha256=sha256(a.selection),pilots_excluded_from_dispatch=[86821,86822],speed_gate_override=a.speed_gate_override or None,deadline=a.deadline_utc,complete=False)
    with lease.open('x') as f:json.dump(dict(task='act16w-record',pid=os.getpid(),start=datetime.now(timezone.utc).isoformat(),expected_end=a.deadline_utc,concurrency=0),f)
    stop={'requested':False,'cap_end':False};signal.signal(signal.SIGINT,lambda *_:stop.update(requested=True));signal.signal(signal.SIGTERM,lambda *_:stop.update(requested=True))
    def foreign():
        receipt=read(a.capacity_receipt)
        # Mac refreshes each45s; receipt expires after one missed refresh.
        if receipt.get('project_id')!='ugrp-sim-b-1014' or datetime.fromisoformat(receipt['valid_until_utc']).timestamp()<time.time():return 40
        count=max(a.foreign_cpu_worlds,int(receipt['foreign_cpu_worlds']))
        for item in lease.parent.glob('*.json'):
            if item.name.startswith('act16w'):continue
            try:count+=int(read(item).get('concurrency',0))
            except (ValueError,TypeError):count+=40
        return count
    try:
        while pending or running:
            if time.time()>=deadline:stop.update(requested=True,cap_end=True)
            if stop['requested']:
                for j,job in running.items():
                    if not job.get('signaled'):
                        marker=dict(category='cap_end' if stop['cap_end'] else 'supervisor_stop',reason='act16w_task_budget8h' if stop['cap_end'] else 'act16w_supervisor_stop')
                        write(job['root']/'SUPERVISOR_STOP.json',marker)
                        if (job['root']/'controller').exists():write(job['root']/'controller/SUPERVISOR_STOP.json',marker)
                        os.killpg(job['proc'].pid,signal.SIGINT);job['signaled']=time.monotonic()
                    elif time.monotonic()-job['signaled']>60:os.killpg(job['proc'].pid,signal.SIGTERM)
            for j,job in list(running.items()):
                result=job['proc'].poll()
                if result is not None:
                    job['log'].close();finished.append(dict(group=j,indices=job['indices'],raw=str(job['root']),exit_code=result));del running[j]
                    if result:report['last_error_group']=j
                else:
                    progress=job['root']/'controller/progress.json'
                    if progress.exists() and not (job['root']/'first30.json').exists():
                        try:
                            d=read(progress);sim=min(d['ticks'])*.1
                            if sim>=30:
                                value=dict(sim_s=sim,loop_wall_s=d['loop_wall_s'],world_latency_wall_per_SIM=d['loop_wall_s']/sim,aggregate_wall_per_world_SIM=d['loop_wall_s']/sum(d['ticks'])/.1,speed_gate_override=a.speed_gate_override or None)
                                write(job['root']/'first30.json',value)
                                if value['world_latency_wall_per_SIM']>6 and not a.speed_gate_override:report['submission_stopped']='SPEED_GATE_FAIL'
                        except (ValueError,KeyError):pass
            active=sum(len(x['indices']) for x in running.values());capacity=min(a.max_worlds,40-foreign())-active
            if not stop['requested'] and not report.get('submission_stopped'):
                for j,indices in list(pending):
                    if len(indices)>capacity:continue
                    root=a.root/f'group-{j:02d}';root.mkdir();first=inventory[indices[0]]
                    args=['--physics-backend','mjwarp_batch_v1','--teacher-source',str(T),'--plan',str(a.references/'plans.json'),'--world-episodes',','.join(map(str,indices)),'--nworld',str(len(indices)),'--cap-s','90','--vm-hourly-usd','1.096','--scene-v5-v1','--numpy-teacher-v1','--batch-sleep-v1','--native-sleep-policy-compat-v1','--compiled-reference-v1',first['actuator'],'--compiled-geometry-312-v1',first['geometry'],'--per-world-model-references-v1',str(a.references/'per-world-references.json'),'--out',str(root/'controller')]
                    write(root/'runner-args.json',args)
                    cmd=[str(PY),'-u',str(API/'scripts/run_warp_act_record.py'),'--enabled','--qualified-source',str(Q),'--teacher-source',str(T),'--qualification',str(GATE),'--runner-args-json',str(root/'runner-args.json'),'--stage','batch','--recording-approval',str(a.approval),'--out',str(root/'capture')]
                    log=(root/'record.log').open('x');proc=subprocess.Popen(cmd,cwd=Q,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
                    write(root/'launch.json',dict(args=cmd,pid=proc.pid,source_sha=source,world_indices=indices));running[j]=dict(proc=proc,root=root,indices=indices,log=log);pending.remove((j,indices));capacity-=len(indices)
            report.update(finished=finished,pending=[dict(group=j,indices=i) for j,i in pending],active=[dict(group=j,pid=x['proc'].pid,indices=x['indices']) for j,x in running.items()],wall_s=time.monotonic()-start)
            write(a.root/'summary.json',report);write(lease,dict(task='act16w-record',pid=os.getpid(),start=report['started_utc'],expected_end=a.deadline_utc,concurrency=sum(len(x['indices']) for x in running.values()),children=report['active']))
            if (stop['requested'] or report.get('submission_stopped')) and not running:break
            time.sleep(1)
        status='cap_end' if stop['cap_end'] else 'supervisor_stop' if stop['requested'] else report.get('submission_stopped') or ('HOST_ERROR' if any(x['exit_code'] for x in finished) else 'complete')
        report.update(status=status,complete=not pending and all(x['exit_code']==0 for x in finished))
    except BaseException as error:
        report.update(status='HOST_ERROR',error=repr(error),complete=False)
        for job in running.values():
            if job['proc'].poll() is None:
                marker=dict(category='supervisor_stop',reason='act16w_dispatcher_exception')
                write(job['root']/'SUPERVISOR_STOP.json',marker)
                if (job['root']/'controller').exists():write(job['root']/'controller/SUPERVISOR_STOP.json',marker)
                os.killpg(job['proc'].pid,signal.SIGINT)
                try:job['proc'].wait(timeout=45)
                except subprocess.TimeoutExpired:os.killpg(job['proc'].pid,signal.SIGTERM);job['proc'].wait(timeout=15)
            job['log'].close()
        running.clear();raise
    finally:
        report['wall_s']=time.monotonic()-start;write(a.root/'summary.json',report)
        if not running and lease.exists() and read(lease).get('pid')==os.getpid():lease.unlink()

if __name__=='__main__':main()
