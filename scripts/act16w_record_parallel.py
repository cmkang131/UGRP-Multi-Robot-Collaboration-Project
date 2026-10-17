"""Continue the SAME40 records under the user's global<=40-world budget.

The original24-world limit was a worker scheduling choice. Pause only its
stateless dispatcher, preserve its two independently grouped GPU workers,
and submit the remaining16 with the EXACT same frozen813 recording wrapper.
Linux zombie exit_code retains the original workers' actual exit status.
No teacher, physics, camera, seed, action or SIM clock is changed/restarted.
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

B=Path('/home/ugrp/ugrp-sim');S=B/'src/813b9113b16e382712a00b911a9dcc7c06fbd77d';Q=B/'src/f0db6b1abb842ea65b71c433738210254f300a7c';T=B/'src/warp1-teacher-snapshot-6f057f7e';PY=B/'runs/simalt3/warp-env/bin/python'


def read(p):return json.loads(p.read_text())
def write(p,v):
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(v,indent=2)+'\n');tmp.replace(p)


def proc(pid):
    try:
        raw=Path(f'/proc/{pid}/stat').read_text();fields=raw.rsplit(')',1)[1].split()
        return dict(pid=pid,state=fields[0],ppid=int(fields[1]),pgid=int(fields[2]),start=int(fields[19]),exit_status=int(fields[49]),argv=Path(f'/proc/{pid}/cmdline').read_bytes().decode().strip('\0').split('\0'))
    except FileNotFoundError:return None


def identity(row,*,script,flag,root,parent=None):
    if not row or row['state']=='Z' or script not in row['argv'] or '--enabled' not in row['argv']:
        raise ValueError('not a live owned ACT16 dispatcher/worker')
    args=row['argv']
    index=args.index(flag) if args.count(flag)==1 else -1
    if index<0 or index+1>=len(args) or args[index+1]!=root or (parent is not None and (row['ppid']!=parent or row['pgid']!=row['pid'])):
        raise ValueError('foreign root/parent/process group cannot be adopted')
    return row


def main():
    p=argparse.ArgumentParser();p.add_argument('--enabled',action='store_true');p.add_argument('--preflight-only',action='store_true');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if not a.enabled:p.error('explicit owned-dispatch handoff opt-in required')
    host=require_gcp2(training=True);source=frozen_source(Path(__file__).resolve().parents[1]);frozen_source(S,S.name);frozen_source(Q,Q.name)
    root=B/'runs/act16w-resume2-data-r2';old_lease=B/'leases/act16w-record.json';own_lease=B/'leases/act16w-record-parallel.json';old=read(root/'summary.json');lease=read(old_lease);old_pid=lease['pid']
    if old['status']!='running' or own_lease.exists():raise ValueError('single live original dispatcher required')
    parent=identity(proc(old_pid),script=str(S/'scripts/act16w_record_batch.py'),flag='--root',root=str(root))
    active=[]
    for job in old['active']:
        folder=root/f'group-{job["group"]:02d}';row=identity(proc(job['pid']),script=str(S/'scripts/run_warp_act_record.py'),flag='--out',root=str(folder/'capture'),parent=old_pid)
        active.append(dict(group=job['group'],indices=job['indices'],pid=job['pid'],start=row['start'],root=folder,adopted=True,log=None,proc=None))
    gpu_pids={int(x.strip()) for x in subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).splitlines() if x.strip()}
    if old_pid in gpu_pids or not all(j['pid'] in gpu_pids for j in active):raise ValueError('dispatcher must have no GPU context; live worker identities required')
    deadline=datetime.fromisoformat(old['deadline']).timestamp();hard=datetime.fromisoformat('2026-10-16T13:47:00.019842+00:00').timestamp()
    if deadline>hard-90 or time.time()>=deadline:raise ValueError('original task8h cap required')
    a.out.mkdir(parents=True,exist_ok=False);preflight=dict(status='validated_no_handoff_yet',source_sha=source,host=host,parent=parent,workers=[{k:v for k,v in j.items() if k not in ('root','proc','log')} for j in active],old_summary_sha256=sha256(root/'summary.json'),original_deadline=old['deadline'],old_max_worlds=24,new_max_owned_worlds=38,global_max_worlds=40,teacher_physics_camera_seeds_unchanged=True)
    write(a.out/'preflight.json',preflight)
    if a.preflight_only:print(json.dumps(preflight));return
    pending=list(old['pending']);finished=list(old.get('finished',[]));running={j['group']:j for j in active};stopping={'requested':False,'cap_end':False};signal.signal(signal.SIGINT,lambda *_:stopping.update(requested=True));signal.signal(signal.SIGTERM,lambda *_:stopping.update(requested=True))
    report={**old,'source_sha':source,'original_dispatch_source':S.name,'coordinator_handoff_utc':datetime.now(timezone.utc).isoformat(),'original_dispatcher_pid':old_pid,'maximum_owned_worlds':38,'global_maximum_worlds':40,'complete':False,'rejection_table':str(a.out/'rejection_table.json'),'schedule_reason':'measured9-world first30 latency290.64 wall/SIM; launch remaining16 within user global40 and original task8h, no result-based seed changes'}
    write(a.out/'rejection_table.json',dict(funnel=[dict(gate='registered_starts',passed=40,rejected=0),dict(gate='completed_before_handoff',passed=2,rejected=0),dict(gate='running_before_handoff',passed=22,rejected=0),dict(gate='pending_before_handoff',passed=16,rejected=0)],rejections=[],raw=str(root),reproduce=__import__('sys').argv))
    write(a.out/'queue.json',dict(source_sha=source,capture_source=S.name,rejection_table=report['rejection_table'],deadline=old['deadline'],maximum_owned_worlds=38,global_maximum_worlds=40,speed_gate_override=old['speed_gate_override']))
    refs=B/'runs/act16w-resume2-record-references';inventory=read(refs/'inventory.json');approval=B/'runs/act16w-resume2-admission/recording-approval.json';started=time.monotonic();paused=False
    with own_lease.open('x') as f:json.dump(dict(task='act16w-record-parallel',pid=os.getpid(),start=report['coordinator_handoff_utc'],expected_end=old['deadline'],concurrency=0,original_dispatcher_paused=old_pid),f)
    def alive(job):
        if not job['adopted']:return job['proc'].poll() is None
        r=proc(job['pid'])
        if not r or r['start']!=job['start']:raise RuntimeError('adopted worker identity disappeared before exact exit observation')
        if r['state']=='Z':job['exit_code']=os.waitstatus_to_exitcode(r['exit_status']);return False
        return True
    def signal_owned(job,sig):
        r=proc(job['pid'])
        if (r and r['state']!='Z' and r['pgid']==job['pid'] and str(S/'scripts/run_warp_act_record.py') in r['argv']
                and str(job['root']/'capture') in r['argv'] and (not job['adopted'] or r['start']==job['start'])):os.killpg(job['pid'],sig)
    def foreign():
        try:
            receipt=read(B/'runs/act16w-capacity-receipt.json')
            if receipt['project_id']!='ugrp-sim-b-1014' or datetime.fromisoformat(receipt['valid_until_utc']).timestamp()<time.time():return 40
            count=int(receipt['foreign_cpu_worlds'])
            for f in own_lease.parent.glob('*.json'):
                if f not in (own_lease,old_lease):count+=int(read(f).get('concurrency',0))
            return count
        except (OSError,ValueError,KeyError):return 40
    try:
        # This affects only the verified dispatcher PID, never its worker PGIDs.
        current=identity(proc(old_pid),script=str(S/'scripts/act16w_record_batch.py'),flag='--root',root=str(root))
        if current['start']!=parent['start']:raise RuntimeError('dispatcher identity changed before handoff')
        os.kill(old_pid,signal.SIGSTOP)
        for _ in range(300):
            current=proc(old_pid)
            if current and current['state'] in ('T','t'):paused=True;break
            time.sleep(.01)
        else:
            os.kill(old_pid,signal.SIGCONT);raise RuntimeError('dispatcher did not stop; no new workers submitted')
        write(a.out/'original-summary.json',read(root/'summary.json'));write(a.out/'original-lease.json',read(old_lease))
        while pending or running:
            if time.time()>=deadline:stopping.update(requested=True,cap_end=True)
            for key,job in list(running.items()):
                if not alive(job):
                    code=job['exit_code'] if job['adopted'] else job['proc'].returncode
                    if job['log']:job['log'].close()
                    finished.append(dict(group=key,indices=job['indices'],raw=str(job['root']),exit_code=code,exit_method='Linux zombie exit_status; original dispatcher paused' if job['adopted'] else 'Popen.waitpid'));del running[key];continue
                if stopping['requested']:
                    if not job.get('signaled'):
                        marker=dict(category='cap_end' if stopping['cap_end'] else 'supervisor_stop',reason='act16w_task_budget8h' if stopping['cap_end'] else 'parallel_dispatch_supervisor_stop');write(job['root']/'SUPERVISOR_STOP.json',marker)
                        if (job['root']/'controller').exists():write(job['root']/'controller/SUPERVISOR_STOP.json',marker)
                        signal_owned(job,signal.SIGINT);job['signaled']=time.monotonic()
                    elif time.time()>=hard-30:signal_owned(job,signal.SIGKILL)
                    elif time.monotonic()-job['signaled']>60:signal_owned(job,signal.SIGTERM)
                progress=job['root']/'controller/progress.json'
                if progress.exists() and not (job['root']/'first30.json').exists():
                    try:
                        d=read(progress);sim=min(d['ticks'])*.1
                        if sim>=30:write(job['root']/'first30.json',dict(sim_s=sim,loop_wall_s=d['loop_wall_s'],world_latency_wall_per_SIM=d['loop_wall_s']/sim,aggregate_wall_per_world_SIM=d['loop_wall_s']/sum(d['ticks'])/.1,speed_gate_override=old['speed_gate_override']))
                    except (ValueError,KeyError):pass
            old_active=sum(len(j['indices']) for j in running.values() if j['adopted']);new_active=sum(len(j['indices']) for j in running.values() if not j['adopted'])
            write(old_lease,{**lease,'concurrency':old_active,'dispatcher_paused_by':os.getpid(),'deadline_supervised_by':'act16w-record-parallel','children':[{k:v for k,v in j.items() if k in ('group','indices','pid')} for j in running.values() if j['adopted']]})
            capacity=min(38-old_active-new_active,40-foreign()-old_active-new_active)
            if not stopping['requested']:
                for item in list(pending):
                    key,g=item['group'],item['indices']
                    if len(g)>capacity:continue
                    folder=root/f'group-{key:02d}';folder.mkdir();first=inventory[g[0]]
                    args=['--physics-backend','mjwarp_batch_v1','--teacher-source',str(T),'--plan',str(refs/'plans.json'),'--world-episodes',','.join(map(str,g)),'--nworld',str(len(g)),'--cap-s','90','--vm-hourly-usd','1.096','--scene-v5-v1','--numpy-teacher-v1','--batch-sleep-v1','--native-sleep-policy-compat-v1','--compiled-reference-v1',first['actuator'],'--compiled-geometry-312-v1',first['geometry'],'--per-world-model-references-v1',str(refs/'per-world-references.json'),'--out',str(folder/'controller')];write(folder/'runner-args.json',args)
                    cmd=[str(PY),'-u',str(S/'scripts/run_warp_act_record.py'),'--enabled','--act16w-host-schema-v1','--qualified-source',str(Q),'--teacher-source',str(T),'--qualification',str(B/'runs/warp3/teacher-gate-qualification-r1.json'),'--runner-args-json',str(folder/'runner-args.json'),'--stage','batch','--recording-approval',str(approval),'--out',str(folder/'capture')]
                    write(own_lease,dict(task='act16w-record-parallel',pid=os.getpid(),start=report['coordinator_handoff_utc'],expected_end=old['deadline'],concurrency=new_active+len(g),reservation_before_spawn=True))
                    log=(folder/'record.log').open('x');child=subprocess.Popen(cmd,cwd=Q,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'})
                    write(folder/'launch.json',dict(args=cmd,pid=child.pid,source_sha=S.name,scheduler_source_sha=source,world_indices=g));running[key]=dict(group=key,indices=g,pid=child.pid,root=folder,adopted=False,proc=child,log=log);pending.remove(item);capacity-=len(g);new_active+=len(g)
            report.update(status='running',active=[dict(group=k,pid=j['pid'],indices=j['indices']) for k,j in running.items()],pending=pending,finished=finished,handoff_wall_s=time.monotonic()-started)
            write(root/'summary.json',report);write(own_lease,dict(task='act16w-record-parallel',pid=os.getpid(),start=report['coordinator_handoff_utc'],expected_end=old['deadline'],concurrency=sum(len(j['indices']) for j in running.values() if not j['adopted']),children=report['active']))
            if stopping['requested'] and not running:break
            time.sleep(1)
        report.update(status='cap_end' if stopping['cap_end'] else 'supervisor_stop' if stopping['requested'] else 'HOST_ERROR' if any(j['exit_code'] for j in finished) else 'complete',complete=not pending and len(finished)==4 and all(j['exit_code']==0 for j in finished))
    except BaseException as error:
        report.update(status='HOST_ERROR',complete=False,error=repr(error));raise
    finally:
        if paused:
            for job in running.values():
                try:signal_owned(job,signal.SIGINT)
                except ProcessLookupError:pass
            limit=min(hard-15,time.time()+90)
            while running and time.time()<limit:
                for key,job in list(running.items()):
                    try:live=alive(job)
                    except RuntimeError as error:report['cleanup_identity_error']=str(error);live=False
                    if not live:
                        if job['log'] and not job['log'].closed:job['log'].close()
                        del running[key]
                if running:time.sleep(.2)
            for job in running.values():signal_owned(job,signal.SIGKILL)
            # Only the paused, GPU-free owned metadata PID is killed. Its GPU
            # workers have already ended or been explicitly drained above.
            row=proc(old_pid)
            if row and row['start']==parent['start']:os.kill(old_pid,signal.SIGKILL)
            report.update(vm_stop_attempted=False,original_workers_restarted=False,ended_utc=datetime.now(timezone.utc).isoformat());write(root/'summary.json',report);write(a.out/'summary.json',report)
            if old_lease.exists() and read(old_lease).get('pid')==old_pid:old_lease.unlink()
        if own_lease.exists() and read(own_lease).get('pid')==os.getpid():own_lease.unlink()


if __name__=='__main__':main()
