"""Finite gcp2 CPU run-first, <=6workers, all sources committed. No credentials."""
import argparse,concurrent.futures,datetime,importlib.util,json,os,platform,runpy,statistics,subprocess,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];RUNS=Path('/home/ugrp/ugrp-sim/runs');PY='/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python'

def worker(taskfile):
    assert platform.node().startswith('ugrp-sim-gcp2')
    t=json.loads(Path(taskfile).read_text())
    spec=importlib.util.spec_from_file_location('prior_instrument',ROOT/'experiments/2026-10-16-reloc18/run_round.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.instrument(False)
    sys.argv=[t['command'][2],*t['command'][3:]];runpy.run_module(t['command'][2],run_name='__main__')

def launch(n):
    assert platform.node().startswith('ugrp-sim-gcp2') and n in (1,2,3)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'])
    rejection=(ROOT/'experiments/2026-10-16-reloc19/prior-rejection-table.json' if n==1 else RUNS/f'reloc19-round{n-1}/rejection-table.json')
    assert rejection.is_file()
    if n>1:
        previous=RUNS/f'reloc19-round{n-1}'
        assert (previous/'DONE').exists()
        assert json.loads((previous/'speed-gate.json').read_text())['status']=='PASS'
    batch=RUNS/f'reloc19-round{n}';batch.mkdir(exist_ok=False)
    prior=json.loads((RUNS/'reloc18-round3/queue.json').read_text())['runs'];tasks=[]
    for old in prior:
        if old['condition'] not in ('candidate','map_odom'):continue
        for condition in (('A','AB') if old['kind']=='carry' else ('short_regression',)):
            kind=old['kind'];seed=old['seed'];name=f'reloc19-r{n}-{kind}-{condition}-{seed}-{sha[:8]}'
            folder=RUNS/name;folder.mkdir(exist_ok=False);cmd=old['command'].copy();cmd[0]=PY
            if kind=='carry':
                plan=json.loads(Path(cmd[cmd.index('--plan')+1]).read_text());ep=plan['episodes'][0]
                ep.update(batch=f'reloc19-r{n}',destination_visual_acquire_v1=True,carry_relocalize_v1=condition=='AB')
                p=folder/'input-plan.json';p.write_text(json.dumps(plan,indent=2)+'\n')
                cmd[cmd.index('--plan')+1]=str(p);cmd[cmd.index('--out')+1]=str(folder/'raw')
            else:
                cmd[cmd.index('--output')+1]=str(folder/'raw');cmd[cmd.index('--expected-source-sha')+1]=sha
            env=dict(old['environment']);env['UGRP_SCENE_COLOUR_CALIBRATION']=str(ROOT/'experiments/2026-10-16-reloc16/colour-calibration.json')
            t=dict(name=name,kind=kind,condition=condition,seed=seed,command=cmd,environment=env,source_sha=sha,raw=str(folder/'raw'),rejection_table=str(rejection))
            p=folder/'task.json';p.write_text(json.dumps(t,indent=2)+'\n');t['task_file']=str(p);tasks.append(t)
            (folder/'RUN_META.json').write_text(json.dumps(dict(task='reloc19',branch='claude/reloc19',sha=sha,batch=f'round{n}',**{'class':'dev'})))
    lease=RUNS.parent/'leases/reloc19.json';l=json.loads(lease.read_text());l.update(pid=os.getpid(),concurrency=6,source_sha=sha,stage=f'round{n}');lease.write_text(json.dumps(l,indent=2)+'\n')
    leases=[json.loads(p.read_text()) for p in lease.parent.glob('*.json')]
    assert sum(x.get('concurrency',0) for x in leases)<=40
    assert os.statvfs(RUNS).f_bavail*os.statvfs(RUNS).f_frsize>=15*1024**3
    queue=dict(round=n,source_sha=sha,rejection_table=str(rejection),admission=dict(leases=leases,own_concurrency=6),runs=tasks)
    (batch/'queue.json').write_text(json.dumps(queue,indent=2)+'\n');lock=threading.Lock()
    def execute(t):
        env=dict(os.environ,MUJOCO_GL='osmesa',PYOPENGL_PLATFORM='osmesa',PYTHONPATH=str(ROOT),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',**t['environment'])
        with (Path(t['raw']).parent/'run.log').open('wb') as f:
            p=subprocess.Popen(['timeout','--signal=INT','--kill-after=60','3600',PY,str(Path(__file__).resolve()),'--worker',t['task_file']],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
        with lock:
            t['pid']=p.pid;l['pids']=[x['pid'] for x in tasks if 'pid' in x];lease.write_text(json.dumps(l,indent=2)+'\n');(batch/'queue.json').write_text(json.dumps(queue,indent=2)+'\n')
        (Path(t['raw']).parent/'EXIT').write_text(str(p.wait())+'\n')
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for f in concurrent.futures.as_completed([pool.submit(execute,t) for t in tasks]):f.result()
    first=[];missing=[]
    for t in tasks:
        p=Path(t['raw'])/'first30.json'
        if p.exists():first.append(json.loads(p.read_text())['wall_per_sim'])
        else:missing.append(str(p))
    speed=dict(status='PASS' if not missing and statistics.median(first)<=6 else 'SPEED_GATE_FAIL',median=statistics.median(first) if first else None,values=first,missing=missing)
    (batch/'speed-gate.json').write_text(json.dumps(speed,indent=2)+'\n')
    (batch/'DONE').write_text(datetime.datetime.now(datetime.timezone.utc).isoformat()+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--round',type=int);p.add_argument('--worker');a=p.parse_args()
    if a.worker:worker(a.worker)
    else:launch(a.round)
