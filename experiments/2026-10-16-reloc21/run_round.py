"""Finite gcp2-only CPU queue, <=8 tasks and <=3 rounds; no model calls."""
import argparse
import concurrent.futures
import datetime
import importlib.util
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import threading

ROOT=Path(__file__).resolve().parents[2]
R=Path('/home/ugrp/ugrp-sim/runs')
PY='/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python'


def worker(taskfile):
    spec=importlib.util.spec_from_file_location('reloc20_runner',ROOT/'experiments/2026-10-16-reloc20/run_round.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.worker(taskfile)


def launch(n):
    assert platform.node().startswith('ugrp-sim-gcp2') and n == 1, 'CPU R2/R3 retired by coordinator user-decision handoff; localization continues in warp5/MJWarp'
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'])
    rejection=R/'reloc21-prior/rejection-table.json' if n==1 else R/f'reloc21-round{n-1}/rejection-table.json'
    if not rejection.exists():rejection=Path(str(rejection)+'.zst')
    assert rejection.is_file(),rejection
    if n>1:
        previous=R/f'reloc21-round{n-1}'
        assert (previous/'DONE').exists()
        speed=json.loads((previous/'speed-gate.json').read_text())
        assert speed['status']=='PASS',speed
    lease=R.parent/'leases/reloc21.json';l=json.loads(lease.read_text())
    leases=[json.loads(p.read_text()) for p in lease.parent.glob('*.json')]
    other=sum(x.get('concurrency',0) for x in leases if x.get('task')!='reloc21')
    ps=subprocess.check_output(['ps','-eo','pid,ppid,comm,args'],text=True)
    actual=sum(any(marker in x for marker in ('--worker','--execute','scripts.run_solo_grasp_act_teacher','scripts.run_self_map_diagnostic')) for x in ps.splitlines() if 'python' in x and '/home/ugrp/ugrp-sim/' in x)
    # User says beamact3 evaluation16 planned: reserve that capacity even
    # before its lease arrives; never stop/wait for another job's source.
    assert max(actual,other,16)+8<=40
    free=os.statvfs(R).f_bavail*os.statvfs(R).f_frsize
    mem=int(next(x for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')).split()[1])*1024
    assert free>=8*1024**3+8*512*1024**2 and mem>=6*1024**3
    batch=R/f'reloc21-round{n}';batch.mkdir(exist_ok=False)
    old=json.loads((R/'reloc20-round3/queue.json').read_text())['runs'];tasks=[]
    for prior in old:
        if prior['kind']=='carry' and prior['condition']!='candidate':continue
        for condition in (('baseline','progress','complete') if prior['kind']=='carry' else ('short_regression',)):
            kind=prior['kind'];seed=prior['seed'];name=f'reloc21-r{n}-{kind}-{condition}-{seed}-{sha[:8]}'
            folder=R/name;folder.mkdir(exist_ok=False);cmd=prior['command'].copy();cmd[0]=PY
            if kind=='carry':
                plan=json.loads(Path(cmd[cmd.index('--plan')+1]).read_text());ep=plan['episodes'][0]
                ep.update(batch=f'reloc21-r{n}',pr=547,reloc21_route_progress_v1=condition!='baseline',
                          reloc21_complete_plan_v1=condition=='complete',destination_visual_acquire_v1=True)
                p=folder/'input-plan.json';p.write_text(json.dumps(plan,indent=2)+'\n')
                cmd[cmd.index('--plan')+1]=str(p);cmd[cmd.index('--out')+1]=str(folder/'raw')
            else:
                cmd[cmd.index('--output')+1]=str(folder/'raw');cmd[cmd.index('--expected-source-sha')+1]=sha
            env=dict(prior['environment']);env['UGRP_SCENE_COLOUR_CALIBRATION']=str(ROOT/'experiments/2026-10-16-reloc16/colour-calibration.json')
            t=dict(name=name,kind=kind,condition=condition,seed=seed,command=cmd,environment=env,
                   source_sha=sha,raw=str(folder/'raw'),rejection_table=str(rejection))
            p=folder/'task.json';t['task_file']=str(p);p.write_text(json.dumps(t,indent=2)+'\n');tasks.append(t)
            (folder/'RUN_META.json').write_text(json.dumps(dict(task='reloc21',pr=547,branch='claude/reloc21',sha=sha,batch=f'round{n}',**{'class':'dev'})))
    assert len(tasks)==8
    l.update(pid=os.getpid(),concurrency=8,source_sha=sha,stage=f'round{n}',pids=[]);lease.write_text(json.dumps(l,indent=2)+'\n')
    queue=dict(round=n,source_sha=sha,rejection_table=str(rejection),admission=dict(leases=leases,
        actual_processes=actual,other_concurrency=other,beamact3_reserved=16,own_concurrency=8,
        disk_free_bytes=free,expected_write_bytes=8*512*1024**2,memory_available_bytes=mem,
        loadavg=Path('/proc/loadavg').read_text().strip()),runs=tasks)
    lock=threading.Lock();(batch/'queue.json').write_text(json.dumps(queue,indent=2)+'\n')
    def execute(t):
        env=dict(os.environ,MUJOCO_GL='osmesa',PYOPENGL_PLATFORM='osmesa',PYTHONPATH=str(ROOT),
                 OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',**t['environment'])
        with (Path(t['raw']).parent/'run.log').open('wb') as f:
            p=subprocess.Popen(['timeout','--signal=INT','--kill-after=60','3600',PY,str(Path(__file__).resolve()),'--worker',t['task_file']],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
        with lock:
            t['pid']=p.pid;l['pids'].append(p.pid);lease.write_text(json.dumps(l,indent=2)+'\n');(batch/'queue.json').write_text(json.dumps(queue,indent=2)+'\n')
        (Path(t['raw']).parent/'EXIT').write_text(str(p.wait())+'\n')
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for f in concurrent.futures.as_completed([pool.submit(execute,t) for t in tasks]):f.result()
    first=[];missing=[]
    for t in tasks:
        p=Path(t['raw'])/'first30.json'
        if p.exists():first.append(json.loads(p.read_text())['wall_per_sim'])
        else:missing.append(str(p))
    speed=dict(status='PASS' if not missing and statistics.median(first)<=6 else 'SPEED_GATE_FAIL',
               median=statistics.median(first) if first else None,values=first,missing=missing)
    (batch/'speed-gate.json').write_text(json.dumps(speed,indent=2)+'\n')
    (batch/'DONE').write_text(datetime.datetime.now(datetime.timezone.utc).isoformat()+'\n')
    l.update(stage=f'round{n}-done',concurrency=0,pids=[]);lease.write_text(json.dumps(l,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--round',type=int);p.add_argument('--worker');a=p.parse_args()
    if a.worker:worker(a.worker)
    else:launch(a.round)
