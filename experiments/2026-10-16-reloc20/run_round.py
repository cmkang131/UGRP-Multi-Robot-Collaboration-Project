"""Finite gcp2 CPU run-first, <=6workers, all sources committed. No credentials."""
import argparse,concurrent.futures,datetime,importlib.util,json,os,platform,runpy,statistics,subprocess,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];RUNS=Path('/home/ugrp/ugrp-sim/runs');PY='/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python'

def worker(taskfile):
    assert platform.node().startswith('ugrp-sim-gcp2')
    t=json.loads(Path(taskfile).read_text())
    spec=importlib.util.spec_from_file_location('prior_instrument',ROOT/'experiments/2026-10-16-reloc18/run_round.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.instrument(False)
    # The ungated predictor is a separate command-only comparison, not the
    # suppressed control posterior. Keep the raw shadow alive after stall.
    from sim.solo_carry_pose import CommandPose
    from harness.natural_floor_slam import compose
    oldissue=CommandPose.issue
    def issue(self,*a,**kw):
        before=self.reloc18_shadow.copy();oldissue(self,*a,**kw)
        self.reloc18_shadow=compose(before,getattr(self,'last_nominal_delta',self.last_delta))
    CommandPose.issue=issue
    sys.argv=[t['command'][2],*t['command'][3:]];runpy.run_module(t['command'][2],run_name='__main__')

def launch(n):
    assert platform.node().startswith('ugrp-sim-gcp2') and n in (1,2,3)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'])
    rejection=(RUNS/'reloc20-prior/rejection-table.json' if n==1 else RUNS/f'reloc20-round{n-1}/rejection-table.json')
    if not rejection.is_file():rejection=Path(str(rejection)+'.zst')
    assert rejection.is_file()
    if n>1:
        previous=RUNS/f'reloc20-round{n-1}'
        assert (previous/'DONE').exists()
        speed=json.loads((previous/'speed-gate.json').read_text())
        if speed['status']!='PASS':
            resolution=json.loads((previous/'host-error-resolution.json').read_text())
            assert resolution['resolved'] is True and speed['median'] is not None and speed['median']<=6
            assert sorted(resolution['missing_first30_resolved'])==sorted(speed['missing'])
    batch=RUNS/f'reloc20-round{n}';batch.mkdir(exist_ok=False)
    prior=json.loads((RUNS/'reloc19-round3/queue.json').read_text())['runs'];tasks=[]
    for old in prior:
        if old['kind']=='carry' and old['condition']!='A_pan':continue
        for condition in ((('baseline','candidate') if n==1 else ('candidate','density') if n==3 else ('candidate',)) if old['kind']=='carry' else ('short_regression',)):
            kind=old['kind'];seed=old['seed'];name=f'reloc20-r{n}-{kind}-{condition}-{seed}-{sha[:8]}'
            folder=RUNS/name;folder.mkdir(exist_ok=False);cmd=old['command'].copy();cmd[0]=PY
            if kind=='carry':
                plan=json.loads(Path(cmd[cmd.index('--plan')+1]).read_text());ep=plan['episodes'][0]
                ep.update(batch=f'reloc20-r{n}',destination_visual_acquire_v1=True,carry_relocalize_v1=False,destination_camera_pan_v1=True)
                candidate=condition in ('candidate','density')
                ep.update({key:candidate for key in ('reloc20_heading_forward_v1','reloc20_loaded_footprint_v1','reloc20_visual_stall_v1','reloc20_contact_ode_v1','destination_direction_preserve_v1','destination_search_replan_v1','reloc20_obstacle_wall_mask_v1')})
                ep['pr']=543
                ep['reloc20_drive_eval_v1']=True
                ep['reloc20_obstacle_wall_component_v1']=candidate and n==3
                ep['reloc20_turn_density_v1']=condition=='density'
                ep['reloc20_rotation_stall_v1']=candidate and n==3
                p=folder/'input-plan.json';p.write_text(json.dumps(plan,indent=2)+'\n')
                cmd[cmd.index('--plan')+1]=str(p);cmd[cmd.index('--out')+1]=str(folder/'raw')
            else:
                cmd[cmd.index('--output')+1]=str(folder/'raw');cmd[cmd.index('--expected-source-sha')+1]=sha
            env=dict(old['environment']);env['UGRP_SCENE_COLOUR_CALIBRATION']=str(ROOT/'experiments/2026-10-16-reloc16/colour-calibration.json')
            t=dict(name=name,kind=kind,condition=condition,seed=seed,command=cmd,environment=env,source_sha=sha,raw=str(folder/'raw'),rejection_table=str(rejection))
            p=folder/'task.json';p.write_text(json.dumps(t,indent=2)+'\n');t['task_file']=str(p);tasks.append(t)
            (folder/'RUN_META.json').write_text(json.dumps(dict(task='reloc20',branch='claude/reloc20',sha=sha,batch=f'round{n}',**{'class':'dev'})))
    lease=RUNS.parent/'leases/reloc20.json';l=json.loads(lease.read_text());l.update(pid=os.getpid(),concurrency=6,source_sha=sha,stage=f'round{n}');lease.write_text(json.dumps(l,indent=2)+'\n')
    leases=[json.loads(p.read_text()) for p in lease.parent.glob('*.json')]
    assert sum(x.get('concurrency',0) for x in leases)<=40
    assert os.statvfs(RUNS).f_bavail*os.statvfs(RUNS).f_frsize>=15*1024**3
    available=int(next(x for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')).split()[1])*1024
    assert available>=6*1024**3
    processes=subprocess.check_output(['ps','-eo','pid,ppid,comm,args'],text=True)
    actual=sum(any(marker in x for marker in ('--worker','--execute','scripts.run_solo_grasp_act_teacher','scripts.run_self_map_diagnostic')) for x in processes.splitlines() if 'python' in x and '/home/ugrp/ugrp-sim/' in x)
    assert max(actual,sum(x.get('concurrency',0) for x in leases if x.get('task')!='reloc20'))+6<=40
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
