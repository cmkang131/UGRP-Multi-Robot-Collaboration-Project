"""Finite20 student queue, <=16 own runs and <=40 total reserved runs."""
import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from harness.grasp_act_data import read_json, sha256, write_json
from scripts.beamact1_runtime import require_gcp2
from scripts.grasp_act_training_guard import ROOT, source_sha

BASE=Path('/home/ugrp/ugrp-sim')
PY=BASE/'ugrp/.venv-sim/bin/python'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    require_gcp2(training=False);source=source_sha()
    table=BASE/'ops-reviews/beamact1/rejection_table.json'
    if not table.is_file():raise ValueError('missing rejection_table')
    plan=BASE/'ops-reviews/beampair8/heldout-plan.json'
    episodes=read_json(plan)['episodes']
    if [e['seed'] for e in episodes]!=list(range(8329000,8329020)):
        raise ValueError('heldout20 plan mismatch')
    a.output.mkdir(parents=True,exist_ok=False)
    lease=BASE/'leases/beamact2.json'
    started=datetime.now(timezone.utc)
    def claim(n):
        write_json(lease,dict(task='beamact2',pid=os.getpid(),started=started.isoformat(),
            expected_end=(started+timedelta(hours=2)).isoformat(),source_sha=source,
            stage='heldout20 CPU C MuJoCo',concurrency=n))
    if lease.exists():raise ValueError('existing own lease')
    claim(0)
    queue=dict(status='APPROVED_PINNED',source_sha=source,plan=str(plan),plan_sha256=sha256(plan),
        model=str(a.model),model_sha256=sha256(a.model/'model.safetensors'),
        rejection_table=str(table),rejection_table_sha256=sha256(table),max_parallel=16,
        cap_sim_s=60,run_class='milestone',episodes=list(range(20)),host_total_limit=40,
        admission='explicit user beamact2 heldout20 after smoke/train/offline; no teacher corrections')
    write_json(a.output/'queue.json',queue)
    env={**os.environ,'PYTHONPATH':str(ROOT),'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1',
        'OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','LP_NUM_THREADS':'1'}
    pending=list(range(20));active=[];completed=[]
    stopped=False;first30=False
    def admission():
        others={q.name:read_json(q) for q in (BASE/'leases').glob('*.json') if q!=lease}
        reserved=sum(int(v.get('concurrency',0)) for v in others.values())
        available=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
        free=shutil.disk_usage(BASE).free
        record=dict(other_leases=others,other_reserved=reserved,own_requested=16,
            loadavg=os.getloadavg(),available_memory_bytes=available,free_bytes=free,
            per_run_reserved_bytes=256*1024**2,post_submission_floor_bytes=8*1024**3,
            checked_at=datetime.now(timezone.utc).isoformat())
        write_json(a.output/'admission.json',record)
        if free<8*1024**3+20*256*1024**2 or available<6*1024**3:
            raise RuntimeError('storage/memory admission failed')
        return reserved+16<=40
    try:
        while not admission():time.sleep(10)
        claim(16)
        while pending or active:
            while pending and len(active)<16 and not stopped and (first30 or len(completed)+len(active)<16):
                if not admission():break
                index=pending.pop(0);seed=episodes[index]['seed']
                out=a.output/f'seed-{seed}'
                command=[str(PY),'-m','scripts.sim_cli','workflow','run','beamact2-student',
                    '--input',str(plan),'--input',str(a.model),
                    '--input',str(BASE/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247'),'--',
                    '--plan',str(plan),'--episode',str(index),
                    '--dependency-root',str(BASE/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247'),
                    '--model',str(a.model),'--actor-python','/home/ugrp/ugrp-act-cpu-env/bin/python',
                    '--mode','beamact2_student_v1','--output',str(out)]
                log=(a.output/f'seed-{seed}.log').open('x')
                proc=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                active.append(dict(p=proc,log=log,path=out,seed=seed,command=command))
                write_json(a.output/f'seed-{seed}-PROCESS.json',dict(pid=proc.pid,command=command))
            for item in active[:]:
                code=item['p'].poll()
                if code is None:continue
                item['log'].close();out=item['path'];result=out/'result.json'
                data=read_json(result) if result.exists() else {}
                category='HOST_ERROR' if code or not data.get('complete') else 'cap_end' if data['cap_end'] else 'success' if data['physical_success'] else 'student_failure'
                completed.append(dict(seed=item['seed'],path=str(out),exit=code,category=category))
                (a.output/f'seed-{item["seed"]}-EXIT').write_text(str(code)+'\n')
                active.remove(item)
                if category=='HOST_ERROR':stopped=True
            if not first30:
                samples=[]
                for item in [*active,*completed]:
                    path=Path(item['path'])/'first30-speed.json'
                    if path.exists():samples.append(read_json(path))
                if len(samples)==16:
                    import statistics
                    median=statistics.median(x['wall_per_sim'] for x in samples)
                    write_json(a.output/'first30.json',dict(samples=samples,median_wall_per_sim=median,
                        warning=median>3.5,stop=median>6.,source='first full16 runs, no speed-only stage'))
                    first30=True
                    if median>6.:stopped=True
            write_json(a.output/'progress.json',dict(completed=completed,running=[x['seed'] for x in active],
                not_started=[episodes[i]['seed'] for i in pending],stopped=stopped))
            if stopped and not active:break
            if not first30 and len(completed)==16 and not active:
                raise RuntimeError('first30 incomplete/HOST_ERROR; remaining4 not admitted')
            time.sleep(5)
        write_json(a.output/'DONE.json',dict(completed=completed,not_started=[episodes[i]['seed'] for i in pending],
            stopped=stopped,source_sha=source,complete=len(completed)==20 and not pending))
    finally:
        # Only our child processes can be interrupted by this supervisor.
        for item in active:
            item['p'].terminate()
        for item in active:
            try:item['p'].wait(timeout=30)
            except subprocess.TimeoutExpired:item['p'].kill();item['p'].wait()
            item['log'].close()
        lease.unlink()
        write_json(a.output/'lease-released.json',dict(task='beamact2',own_active_children=0,
            other_leases=[p.name for p in (BASE/'leases').glob('*.json')],vm_stop_performed=False))


if __name__=='__main__':main()
