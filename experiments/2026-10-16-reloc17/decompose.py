"""Finite GCP2 investigation runner. No production controller changes."""
import argparse,concurrent.futures,datetime,hashlib,json,os,platform,runpy,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
RUNS=Path('/home/ugrp/ugrp-sim/runs')
PY='/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python'
PROFILE='walls_floor_contrast_v5_indigo110_s80'

def command_only():
    # An explicitly selected ablation: no plane-flow, map pose delivery, or ORB
    # corrections. Map/perception/decision diagnostics still run. No truth read.
    from harness import selfmap4_geometry as g
    from harness.selfmap6_safety import PreMutationGate
    from harness.natural_floor_slam import Observation
    import numpy as np
    g.PlaneFlow.step=lambda self,rgb,servo,t,settled,delta,covariance:(delta,covariance,dict(status='reloc17_command_only_ablation'))
    oldreg=g.StaticRegistration.step
    def registration(self,*a,**kw):
        oldreg(self,*a,**kw)
        self.map_from_own=None;self.execution_r7_admitted=False
        self.last.update(registered=False,execution_r7_admitted=False)
        return None
    g.StaticRegistration.step=registration
    oldstep=PreMutationGate.guarded_step
    def prediction(self,observation,**kw):
        blank=Observation(observation.frame_id,observation.t,np.empty((0,2)),np.empty((0,32),np.uint8),observation.sha256)
        kw['pose_override']=None
        return oldstep(self,blank,**kw)
    PreMutationGate.guarded_step=prediction

def worker(taskfile):
    assert platform.node().startswith('ugrp-sim-gcp2')
    task=json.loads(Path(taskfile).read_text())
    if task['condition']=='a_command_only':command_only()
    sys.argv=['scripts.run_self_map_diagnostic',*task['command'][3:]]
    runpy.run_module('scripts.run_self_map_diagnostic',run_name='__main__')

def launch():
    assert platform.node().startswith('ugrp-sim-gcp2')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'])
    batch=RUNS/'reloc17-decomposition';batch.mkdir(exist_ok=False)
    rejection=RUNS/'reloc17-investigation/rejection-table.json';assert rejection.is_file()
    legacy=json.loads((RUNS/'reloc16-round1/queue.json').read_text())['runs']
    final=json.loads((RUNS/'reloc16-round3/queue.json').read_text())['runs']
    tasks=[]
    for condition in ('a_command_only','b_old_reloc15','c_new_reloc15','d_new_reloc16'):
        for seed in (93584,93583):
            baseline=next(t for t in (final if condition=='d_new_reloc16' else legacy) if t['kind']=='selfmap' and t['seed']==seed and (condition=='d_new_reloc16' or t['scene']=='v1'))
            cmd=baseline['command'].copy();name=f'reloc17-decomp-{condition}-{seed}-{sha[:8]}'
            folder=RUNS/name;folder.mkdir(exist_ok=False);raw=folder/'raw'
            cmd[0]=PY
            for flag,value in [('--output',raw),('--expected-source-sha',sha),('--render-profile','floor_light_textured_v1' if condition=='b_old_reloc15' else PROFILE)]:cmd[cmd.index(flag)+1]=str(value)
            env={k:v for k,v in baseline['environment'].items()}
            if condition=='d_new_reloc16':env['UGRP_SCENE_COLOUR_CALIBRATION']=str(ROOT/'experiments/2026-10-16-reloc16/colour-calibration.json')
            else:env={'UGRP_SCENE_COLOUR_BOUNDARY':'off'}
            t=dict(name=name,kind='selfmap',condition=condition,seed=seed,source_sha=sha,raw=str(raw),command=cmd,environment=env,rejection_table=str(rejection),dev_only=True)
            taskfile=folder/'task.json';taskfile.write_text(json.dumps(t,indent=2)+'\n');t['task_file']=str(taskfile);tasks.append(t)
            (folder/'RUN_META.json').write_text(json.dumps(dict(task='reloc17',branch='claude/reloc17',sha=sha,batch='decomposition',**{'class':'dev'})))
    queue=dict(source_sha=sha,rejection_table=str(rejection),conditions='a disables all local visual correction; global registration cannot authorize drive. Also score command-only replay on each b/c/d executed trajectory.',runs=tasks)
    (batch/'queue.json').write_text(json.dumps(queue,indent=2)+'\n')
    lease=RUNS.parent/'leases/reloc17.json';l=json.loads(lease.read_text());l.update(pid=os.getpid(),source_sha=sha,stage='decomposition',pids=[]);lease.write_text(json.dumps(l,indent=2)+'\n')
    capacity=sum(json.loads(p.read_text()).get('concurrency',0) for p in lease.parent.glob('*.json'));assert capacity<=40,capacity
    available=int(next(l for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')).split()[1])*1024
    assert available>=6*1024**3 and os.statvfs(RUNS).f_bavail*os.statvfs(RUNS).f_frsize>=20*1024**3
    (batch/'admission.json').write_text(json.dumps(dict(lease_capacity=capacity,available_memory=available,storage_budget_bytes=5*1024**3,at=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2)+'\n')
    processes=[]
    for t in tasks:
        env=dict(os.environ,MUJOCO_GL='osmesa',PYOPENGL_PLATFORM='osmesa',PYTHONPATH=str(ROOT),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',**t['environment'])
        with (RUNS/t['name']/'run.log').open('wb') as f:
            p=subprocess.Popen(['timeout','--signal=INT','--kill-after=60','3600',PY,str(Path(__file__).resolve()),'--worker',t['task_file']],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
        t['pid']=p.pid;processes.append(p)
    l['pids']=[p.pid for p in processes];lease.write_text(json.dumps(l,indent=2)+'\n');(batch/'queue.json').write_text(json.dumps(queue,indent=2)+'\n')
    for t,p in zip(tasks,processes):(RUNS/t['name']/'EXIT').write_text(str(p.wait())+'\n')
    (batch/'DONE').write_text(datetime.datetime.now(datetime.timezone.utc).isoformat()+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--launch',action='store_true');p.add_argument('--worker');a=p.parse_args()
    if a.worker:worker(a.worker)
    elif a.launch:launch()
