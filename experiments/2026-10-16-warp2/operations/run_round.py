"""Finite gcp2 L4 coordinator. Only child process groups owned here may stop."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path('/home/ugrp/ugrp-sim')
SOURCE=ROOT/'src'/('warp2-'+sys.argv[1][:8])
ROUND=sys.argv[2]
OUT=ROOT/'runs'/'warp2'/ROUND
LEASE=ROOT/'leases'/'warp2.json'
LIMIT=10800  # user B: maximum three L4 hours, including this coordinator's setup


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n')


def command(*args):
    return subprocess.check_output(list(args),text=True).strip()


def processes():
    rows=[]
    for p in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            words=p.read_bytes().split(b'\0')
            if words and any(v in words[0] for v in (b'python',b'mujoco',b'ffmpeg')):
                rows.append(dict(pid=int(p.parent.name),executable=words[0].decode(errors='replace')))
        except (FileNotFoundError,PermissionError):pass
    return rows


assert not LEASE.exists(), 'own task lease already exists; inspect it'
OUT.mkdir(parents=True,exist_ok=False)
started=time.time();deadline=started+LIMIT
write(LEASE,dict(task='warp2',pid=os.getpid(),started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    expected_end=datetime.datetime.fromtimestamp(deadline,datetime.timezone.utc).isoformat(),source=sys.argv[1],round=ROUND))
env={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1','OMP_NUM_THREADS':'1',
     'OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','PYTHONPATH':str(SOURCE)}
base=[str(SOURCE/'scripts/run_warp_flow_teacher.py'),'--adapter-source',str(ROOT/'src/warp2-08f12921'),
      '--teacher-source',str(ROOT/'src/warp2-26f84d0f'),'--plan',
      str(ROOT/'src/warp2-08f12921/experiments/2026-10-16-beampair6/short6-plan.json'),
      '--vm-hourly-usd','1.096']  # inherited estimate, not verified billing
jobs=[];active_child=None
try:
    admission=dict(processes=processes(),leases={p.name:p.read_text() for p in LEASE.parent.glob('*.json')},
        memory=Path('/proc/meminfo').read_text(),disk=command('df','-B1',str(ROOT)),
        gpu=command('nvidia-smi','--query-gpu=memory.total,memory.used,utilization.gpu','--format=csv,noheader'),
        source=sys.argv[1],max_wall_s=LIMIT,disk_budget_bytes=6*1024**3)
    write(OUT/'admission.json',admission)
    assert len(admission['processes'])<40
    def run(name,python,args):
        global active_child
        remaining=deadline-time.time()
        if remaining<=0:raise TimeoutError('user_L4_3h_cap')
        target=OUT/name
        cmd=[str(python),*base,'--out',str(target),*args]
        entry=dict(name=name,command=cmd,started=time.time(),out=str(target))
        jobs.append(entry);write(OUT/'jobs.json',jobs)
        with (OUT/(name+'.log')).open('w') as log:
            active_child=subprocess.Popen(cmd,cwd=SOURCE,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            entry['pid']=active_child.pid;write(OUT/'jobs.json',jobs)
            last_sample=0
            while active_child.poll() is None:
                now=time.time()
                if now>=deadline:
                    entry['supervisor_stop']='user_L4_3h_cap'
                    os.killpg(active_child.pid,signal.SIGINT)
                    break
                if now-last_sample>=30:
                    progress=target/'progress.json'
                    sample=dict(at=now,job=name,gpu=command('nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader'),
                        memory=Path('/proc/meminfo').read_text(),progress=json.loads(progress.read_text()) if progress.exists() else None)
                    with (OUT/'resource-samples.jsonl').open('a') as stream:stream.write(json.dumps(sample)+'\n')
                    last_sample=now
                time.sleep(5)
            try:code=active_child.wait(timeout=60)
            except subprocess.TimeoutExpired:
                os.killpg(active_child.pid,signal.SIGTERM);code=active_child.wait(timeout=30)
            active_child=None
        entry.update(exit=code,ended=time.time());write(OUT/'jobs.json',jobs)
        if code:raise RuntimeError('job_failed:'+name)
        result=json.loads((target/'summary.json').read_text())
        entry['summary_sha256']=hashlib.sha256((target/'summary.json').read_bytes()).hexdigest()
        write(OUT/'jobs.json',jobs)
        return result
    c=ROOT/'runs/simalt3/c-env/bin/python'
    w=ROOT/'runs/simalt3/warp-env/bin/python'
    run('export',c,['--physics-backend','c_pilot_v1','--export-compiled-only','--nworld','1'])
    compiled=['--compiled-reference-v1',str(OUT/'export/compiled-312.json'),
              '--compiled-geometry-312-v1',str(OUT/'export/compiled-geometry312.npz')]
    for n in (1,16,64,256):
        result=run('n'+str(n),w,['--physics-backend','mjwarp_batch_v1','--nworld',str(n),
            '--cap-s','60' if n<=16 else '30',*(['--mix-known-six'] if n==16 else []),*compiled])
        if n<=16 and result['counts']['physical_success']!=n:
            write(OUT/'STOP.json',dict(reason_category='teacher_probe_failed',blocked_object='frozen_beampair6',min_gap_m=None,
                gap_scope='requires candidate ledger and playback; no geometric attribution yet',nworld=n))
            break
    write(OUT/'DONE.json',dict(jobs=jobs,completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
except BaseException as error:
    write(OUT/'ERROR.json',dict(type=type(error).__name__,error=str(error),jobs=jobs))
    raise
finally:
    if active_child is not None and active_child.poll() is None:
        os.killpg(active_child.pid,signal.SIGINT)
        try:active_child.wait(timeout=60)
        except subprocess.TimeoutExpired:
            os.killpg(active_child.pid,signal.SIGTERM);active_child.wait(timeout=30)
    audit=dict(leases_before_release={p.name:p.read_text() for p in LEASE.parent.glob('*.json')},
        processes=processes(),own_child_remaining=False,vm_stop_attempted=False,
        reason='leave shared VM running; other task leases/processes may remain',wall_s=time.time()-started)
    write(OUT/'cleanup.json',audit)
    LEASE.unlink()
