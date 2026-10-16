"""Finite exact-model MJWarp student evaluation dispatcher; no teacher actions."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from act16w_runtime import require_gcp2,frozen_source,sha256,evaluation_seed_guard

B=Path('/home/ugrp/ugrp-sim');ROOT=Path(__file__).resolve().parents[1]
Q=B/'src/f0db6b1abb842ea65b71c433738210254f300a7c';T=B/'src/warp1-teacher-snapshot-6f057f7e';ACT=B/'src/3f99d58c5ada0862e669ef4065c0ba957f1b4547'
PY=B.parent/'ugrp-rl1b-act-env/bin/python';PHYSICS=B/'runs/simalt3/warp-env/bin/python'


def read(p):return json.loads(p.read_text())
def write(p,v):
    temp=p.with_suffix('.tmp');temp.write_text(json.dumps(v,indent=2)+'\n');temp.replace(p)


def main():
    p=argparse.ArgumentParser();p.add_argument('--enabled',action='store_true')
    for k in ('checkpoint','references-root','groups','protocol','capacity-receipt','out'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--split',choices=['validation','final'],required=True);p.add_argument('--selection',type=Path)
    p.add_argument('--name',required=True);p.add_argument('--max-worlds',type=int,default=24);p.add_argument('--speed-gate-override',default='')
    a=p.parse_args()
    if not a.enabled or not a.name.replace('-','').isalnum() or not 1<=a.max_worlds<=40:p.error('explicit opt-in, finite capacity and simple unique name required')
    host=require_gcp2(training=True);source=frozen_source(ROOT);protocol=read(a.protocol)
    requested=protocol['validation_seeds' if a.split=='validation' else 'final_evaluation_seeds']
    meta=read(a.checkpoint/'adapter.json');model_hash=sha256(a.checkpoint/'model.safetensors')
    evaluation_seed_guard(meta['provenance'],requested,split=a.split,protocol=protocol,model_sha256=model_hash,selection=read(a.selection) if a.selection else None)
    plans=read(a.references_root/'plans.json')['episodes'];inventory=read(a.references_root/'inventory.json');wanted=set(requested)
    groups=[(i,[x for x in g['indices'] if plans[x]['seed'] in wanted]) for i,g in enumerate(read(a.groups)['groups'])]
    pending=[(i,g) for i,g in groups if g];indices=[x for _,g in pending for x in g]
    if {plans[i]['seed'] for i in indices}!=wanted or len(indices)!=len(wanted):raise ValueError('exact unique requested seeds missing from reference groups')
    a.out.mkdir(parents=True,exist_ok=False);lease=B/'leases'/('act16w-eval-'+a.name+'.json');running={};finished=[];start=time.monotonic();stop={'requested':False}
    report=dict(status='running',complete=False,source_sha=source,host=host,started_utc=datetime.now(timezone.utc).isoformat(),split=a.split,checkpoint_sha256=model_hash,checkpoint_provenance=meta['provenance'],requested_seeds=requested,N_requested=len(requested),speed_gate_override=a.speed_gate_override or None,rejection_table=str(a.out/'rejection_table.json'))
    write(a.out/'rejection_table.json',dict(funnel=[dict(gate='requested',passed=len(requested),rejected=0),dict(gate='completed',passed=0,rejected=0,pending=len(requested))],rejections=[],raw=str(a.out),reproduce=['python3',*__import__('sys').argv]))
    write(a.out/'queue.json',dict(source_sha=source,checkpoint_sha256=model_hash,split=a.split,rejection_table=report['rejection_table'],wall_cap=None,planned_worlds=a.max_worlds,speed_gate_override=a.speed_gate_override or None))
    with lease.open('x') as f:json.dump(dict(task='act16w-eval-'+a.name,pid=os.getpid(),start=datetime.now(timezone.utc).isoformat(),expected_end='finite requested seeds x90SIM; no wall deadline',concurrency=0),f)
    signal.signal(signal.SIGINT,lambda *_:stop.update(requested=True));signal.signal(signal.SIGTERM,lambda *_:stop.update(requested=True))
    def foreign():
        try:
            r=read(a.capacity_receipt)
            if r['project_id']!='ugrp-sim-b-1014' or datetime.fromisoformat(r['valid_until_utc']).timestamp()<time.time():return 40
            count=int(r['foreign_cpu_worlds'])
            for l in lease.parent.glob('*.json'):
                if l!=lease:count+=int(read(l).get('concurrency',0))
            return count
        except (ValueError,KeyError,OSError):return 40
    try:
        while pending or running:
            for i,job in list(running.items()):
                code=job['proc'].poll()
                if code is not None:
                    job['log'].close();finished.append(dict(group=i,indices=job['indices'],exit_code=code,raw=str(job['out'])));del running[i]
                elif stop['requested'] and not job.get('signaled'):
                    os.killpg(job['proc'].pid,signal.SIGINT);job['signaled']=True
                elif (job['out']/'progress.json').exists() and not (job['out']/'first30.json').exists():
                    try:
                        progress=read(job['out']/'progress.json');sim=progress['elapsed_SIM']
                        if sim>=30:
                            latency=(time.monotonic()-job['started'])/sim;write(job['out']/'first30.json',dict(world_latency_wall_per_SIM=latency,aggregate_wall_per_world_SIM=latency/len(job['indices']),speed_gate_override=a.speed_gate_override or None))
                            if latency>6 and not a.speed_gate_override:report['submission_stopped']='SPEED_GATE_FAIL'
                    except (ValueError,KeyError):pass
            capacity=min(a.max_worlds,40-foreign())-sum(len(j['indices']) for j in running.values())
            if not stop['requested'] and not report.get('submission_stopped'):
                for i,g in list(pending):
                    if len(g)>capacity:continue
                    root=a.out/f'group-{i:02d}';root.mkdir();plan=root/'plans.json';write(plan,dict(episodes=[plans[x] for x in g]))
                    first=inventory[g[0]];out=root/'evaluation'
                    args=[str(PY),'-u',str(ROOT/'scripts/evaluate_act16w.py'),'--enabled','--full-evaluation','--physics-python',str(PHYSICS),'--qualified-source',str(Q),'--teacher-source',str(T),'--qualification',str(B/'runs/warp3/teacher-gate-qualification-r1.json'),'--references',str(a.references_root/'per-world-references.json'),'--compiled-reference',first['actuator'],'--compiled-geometry',first['geometry'],'--plans',str(plan),'--actor-source',str(ACT),'--checkpoint',str(a.checkpoint),'--out',str(out),'--protocol',str(a.protocol),'--split',a.split]
                    if a.selection:args+=['--selection',str(a.selection)]
                    log=(root/'evaluation.log').open('x');proc=subprocess.Popen(args,cwd=Q,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','LP_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'})
                    write(root/'launch.json',dict(pid=proc.pid,args=args,indices=g));running[i]=dict(proc=proc,log=log,indices=g,out=out,started=time.monotonic());pending.remove((i,g));capacity-=len(g)
            report.update(finished=finished,pending=[dict(group=i,indices=g) for i,g in pending],active=[dict(group=i,pid=j['proc'].pid,indices=j['indices']) for i,j in running.items()],wall_s=time.monotonic()-start)
            write(a.out/'summary.json',report);write(lease,dict(task='act16w-eval-'+a.name,pid=os.getpid(),start_utc=report.get('started_utc'),expected_end='finite requested seeds x90SIM; no wall deadline',concurrency=sum(len(j['indices']) for j in running.values()),children=report['active']))
            if not running and (stop['requested'] or report.get('submission_stopped')):break
            time.sleep(1)
        rows=[];errors=[]
        for job in finished:
            path=Path(job['raw'])/'summary.json';d=read(path) if path.exists() else {}
            if job['exit_code'] or d.get('status')=='HOST_ERROR':
                errors.append(dict(category='HOST_ERROR',count=len(job['indices']),reason=d.get('error') or 'evaluation child exited before summary',raw=job['raw'],blocking_object='not_applicable_host_runtime',minimum_gap_m=None,minimum_gap_status='not_applicable_non_geometric'));continue
            rows+=d.get('student_scores',[])
        complete=len(rows)==len(requested) and not errors and not pending and not report.get('resource_cap_end')
        eligible=list(rows);counts=[len(requested),len(rows)]
        # Per-run score reports are post-action only; this never selects actions.
        for key in ('issued_sequence_complete','lift_success','release_success','task_success'):
            eligible=[r for r in eligible if r[key]];counts.append(len(eligible))
        funnel=[dict(gate=gate,passed=n,rejected=(counts[i-1]-n if i>1 else 0),**({'unfinished':len(requested)-len(rows)} if i==1 else {})) for i,(gate,n) in enumerate(zip(['requested','scored_runs','sequence_done','stable_lift','stable_release','task_success'],counts))]
        table=dict(funnel=funnel,rejections=errors+[dict(seed=r['seed'],category='cap_end' if r['cap_end'] or r['resource_cap_end'] else 'student_task_failure',reason=r.get('failure_reason') or 'physical_or_sequence_gate_failed',raw=str(a.out),blocking_object='not_attributed_before_playback',minimum_gap_m=None,minimum_gap_status='not measured; no geometric cause claim') for r in rows if not r['task_success']],unfinished_seeds=sorted(wanted-{r['seed'] for r in rows}),raw=str(a.out),reproduce=__import__('sys').argv)
        write(a.out/'rejection_table.json',table)
        visibility=[x for job in finished for x in (read(Path(job['raw'])/'summary.json').get('initial_same_kind_visibility',{}).get('rows',[]) if (Path(job['raw'])/'summary.json').exists() else [])]
        report.update(status='complete' if complete else 'cap_end' if report.get('resource_cap_end') else 'HOST_ERROR' if errors else report.get('submission_stopped','incomplete'),complete=complete,n=sum(r['task_success'] for r in rows),N=len(rows),N_requested=len(requested),rows=rows,teacher_actions_executed=0,selection_tuning_performed=False)
        report.update(n_assigned=report['n'],n_any_same_kind=sum(r['any_same_kind_success'] for r in rows),
            SIM_cap_end_N=sum(r['cap_end'] for r in rows),
            resource_cap_end_N=sum(r['resource_cap_end'] for r in rows),
            initial_same_kind_visibility=dict(N=len(visibility),
                pixel_2plus_n=sum(x['pixel_visible_count']>=2 for x in visibility),
                any_probe_2plus_n=sum(x['any_probe_visible_count']>=2 for x in visibility),
                qualified_2plus_n=sum(x['qualified_visible_count']>=2 for x in visibility),rows=visibility,
                scope='native MJWarp start-frame instance pixels; existing geometric probe diagnostics also retained; evaluation only'))
    except BaseException as error:
        report.update(status='HOST_ERROR',complete=False,error=repr(error))
        write(a.out/'parent-failure.json',dict(category='HOST_ERROR',reason=repr(error),blocking_object='not_applicable_evaluation_dispatch',minimum_gap_m=None,minimum_gap_status='not_applicable_non_geometric'))
        raise
    finally:
        for job in running.values():
            if job['proc'].poll() is None:
                os.killpg(job['proc'].pid,signal.SIGINT)
                try:job['proc'].wait(timeout=30)
                except subprocess.TimeoutExpired:os.killpg(job['proc'].pid,signal.SIGKILL);job['proc'].wait()
            job['log'].close()
        report['wall_s']=time.monotonic()-start;write(a.out/'summary.json',report)
        if lease.exists() and read(lease).get('pid')==os.getpid():lease.unlink()


if __name__=='__main__':main()
