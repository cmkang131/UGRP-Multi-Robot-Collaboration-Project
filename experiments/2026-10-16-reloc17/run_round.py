"""Finite run-first candidate, GCP2 CPU only, own concurrency four."""
import argparse,datetime,json,os,platform,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
RUNS=Path('/home/ugrp/ugrp-sim/runs')
PY='/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python'

def main(n):
    assert platform.node().startswith('ugrp-sim-gcp2')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'])
    assert (ROOT/'experiments/2026-10-16-reloc17/investigation-complete.md').is_file()
    previous=RUNS/('reloc17-decomposition' if n==1 else f'reloc17-round{n-1}')
    rejection=previous/'rejection-table.json';assert rejection.is_file()
    if n>1:
        summary=json.loads((previous/'summary.json').read_text());assert len(summary['runs'])==4
        assert (previous/'speed-gate.json').is_file()
        assert json.loads((previous/'speed-gate.json').read_text())['status']=='PASS'
    # R1 differs from reloc16 R3 only by servo-wait scheduling; R2 measures
    # the SAME scheduling repair on reloc16 R2's retained color observation.
    baseline=json.loads((RUNS/f'reloc16-round{3 if n==1 else 2}/queue.json').read_text())['runs']
    batch=RUNS/f'reloc17-round{n}';batch.mkdir(exist_ok=False);tasks=[]
    lease=RUNS.parent/'leases/reloc17.json';l=json.loads(lease.read_text());l.update(pid=os.getpid(),concurrency=4,source_sha=sha,stage=f'round{n}');lease.write_text(json.dumps(l,indent=2)+'\n')
    leases=[dict(path=str(p),**json.loads(p.read_text())) for p in lease.parent.glob('*.json')];assert sum(x.get('concurrency',0) for x in leases)<=40
    available=int(next(l for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')).split()[1])*1024
    assert available>=6*1024**3 and os.statvfs(RUNS).f_bavail*os.statvfs(RUNS).f_frsize>=20*1024**3
    for old in baseline:
        folder=RUNS/f"reloc17-r{n}-{old['kind']}-{old['seed']}-{sha[:8]}";folder.mkdir(exist_ok=False);raw=folder/'raw'
        cmd=old['command'].copy();cmd[0]=PY
        env=dict(old['environment']);env['UGRP_SCENE_COLOUR_CALIBRATION']=str(ROOT/'experiments/2026-10-16-reloc16/colour-calibration.json')
        if old['kind']=='selfmap':
            for flag,value in [('--output',raw),('--expected-source-sha',sha)]:cmd[cmd.index(flag)+1]=str(value)
            cmd+=['--reloc17-servo-wait-v1']
        else:
            plan=json.loads(Path(cmd[cmd.index('--plan')+1]).read_text());plan['episodes'][0]['batch']=f'reloc17-r{n}'
            p=folder/'input-plan.json';p.write_text(json.dumps(plan,indent=2)+'\n');cmd[cmd.index('--plan')+1]=str(p);cmd[cmd.index('--out')+1]=str(raw)
        t=dict(name=folder.name,kind=old['kind'],seed=old['seed'],condition=('servo_wait_wall_field' if n==1 else 'servo_wait_landmarks') if old['kind']=='selfmap' else 'unchanged_carry_regression',command=cmd,environment=env,source_sha=sha,raw=str(raw),rejection_table=str(rejection),dev_only=True)
        (folder/'task.json').write_text(json.dumps(t,indent=2)+'\n');(folder/'RUN_META.json').write_text(json.dumps(dict(task='reloc17',branch='claude/reloc17',sha=sha,batch=f'round{n}',**{'class':'dev'})))
        tasks.append(t)
    queue=dict(source_sha=sha,rejection_table=str(rejection),admission=dict(leases=leases,own_concurrency=4,available_memory=available),runs=tasks)
    (batch/'queue.json').write_text(json.dumps(queue,indent=2)+'\n')
    procs=[]
    for t in tasks:
        env=dict(os.environ,MUJOCO_GL='osmesa',PYOPENGL_PLATFORM='osmesa',PYTHONPATH=str(ROOT),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',**t['environment'])
        with (RUNS/t['name']/'run.log').open('wb') as f:p=subprocess.Popen(['timeout','--signal=INT','--kill-after=60','3600',*t['command']],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
        t['pid']=p.pid;procs.append(p)
    l['pids']=[p.pid for p in procs];lease.write_text(json.dumps(l,indent=2)+'\n');(batch/'queue.json').write_text(json.dumps(queue,indent=2)+'\n')
    for t,p in zip(tasks,procs):(RUNS/t['name']/'EXIT').write_text(str(p.wait())+'\n')
    (batch/'DONE').write_text(datetime.datetime.now(datetime.timezone.utc).isoformat()+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--round',type=int,choices=(1,2,3),required=True);a=p.parse_args();main(a.round)
