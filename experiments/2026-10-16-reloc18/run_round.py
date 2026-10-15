"""Finite GCP2-only run-first comparisons; committed source, no credentials."""
import argparse, datetime, json, os, platform, runpy, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
RUNS=Path('/home/ugrp/ugrp-sim/runs')
PY='/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python'

def instrument(command_only):
    import numpy as np
    from harness.natural_floor_slam import compose
    from sim.solo_carry_pose import CommandPose
    oldinit,oldissue,oldrecord=CommandPose.__init__,CommandPose.issue,CommandPose.record
    def init(self,*a,**kw):
        oldinit(self,*a,**kw);self.reloc18_shadow=np.asarray(self.pose).copy()
    def issue(self,*a,**kw):
        oldissue(self,*a,**kw);self.reloc18_shadow=compose(self.reloc18_shadow,self.last_delta)
    def record(self):return dict(oldrecord(self),reloc18_command_shadow=self.reloc18_shadow.tolist())
    CommandPose.__init__,CommandPose.issue,CommandPose.record=init,issue,record
    if not command_only:return
    old=CommandPose.observe_own
    def observe(self,*a,**kw):
        x,P=self.own.x.copy(),self.own.P.copy();old(self,*a,**kw)
        self.own.x,self.own.P=x,P
        if self.heading is not None:self.heading.last.update(status='reloc18_command_only',metric_fix_refreshed=False)
    CommandPose.observe_own=observe
    from sim.lookaround_localization import LookaroundLocalizer
    oldlook=LookaroundLocalizer.observe
    def look(self,*a,**kw):
        x,P=self.own.x.copy(),self.own.P.copy();rec=oldlook(self,*a,**kw)
        self.own.x,self.own.P=x,P
        rec['fix_acceptance']=dict(accepted=False,reason='reloc18_command_only_ablation')
        rec['partial_update']=dict(applied=False,reason='reloc18_command_only_ablation')
        return rec
    LookaroundLocalizer.observe=look

def worker(taskfile):
    assert platform.node().startswith('ugrp-sim-gcp2')
    t=json.loads(Path(taskfile).read_text());instrument(t['condition']=='command_only')
    sys.argv=[t['command'][2],*t['command'][3:]]
    runpy.run_module(t['command'][2],run_name='__main__')

def launch(n):
    assert platform.node().startswith('ugrp-sim-gcp2')
    assert n==1, 'later rounds must be defined after the preceding measured result'
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'])
    rejection=RUNS/'reloc18-audit/rejection-table.json';assert rejection.is_file()
    batch=RUNS/'reloc18-round1';batch.mkdir(exist_ok=False)
    prior=json.loads((RUNS/'reloc17-round2/queue.json').read_text())['runs'];tasks=[]
    for condition in ('visual','command_only'):
        for old in prior:
            if old['kind']!='carry':continue
            name=f"reloc18-r1-{condition}-{old['seed']}-{sha[:8]}";folder=RUNS/name;folder.mkdir()
            plan=json.loads(Path(old['command'][old['command'].index('--plan')+1]).read_text())
            plan['episodes'][0]['batch']='reloc18-r1';planpath=folder/'input-plan.json';planpath.write_text(json.dumps(plan,indent=2)+'\n')
            cmd=old['command'].copy();cmd[0]=PY
            for f,v in [('--plan',planpath),('--out',folder/'raw'),('--cap-s',300)]:cmd[cmd.index(f)+1]=str(v)
            env=dict(old['environment']);env['UGRP_SCENE_COLOUR_CALIBRATION']=str(ROOT/'experiments/2026-10-16-reloc16/colour-calibration.json')
            t=dict(name=name,kind='carry',condition=condition,seed=old['seed'],command=cmd,environment=env,source_sha=sha,raw=str(folder/'raw'),rejection_table=str(rejection))
            taskfile=folder/'task.json';taskfile.write_text(json.dumps(t,indent=2)+'\n');t['task_file']=str(taskfile);tasks.append(t)
            (folder/'RUN_META.json').write_text(json.dumps(dict(task='reloc18',branch='claude/reloc18',sha=sha,batch='round1',**{'class':'dev'})))
    lease=RUNS.parent/'leases/reloc18.json';l=json.loads(lease.read_text());l.update(pid=os.getpid(),concurrency=4,source_sha=sha,stage='round1',pids=[]);lease.write_text(json.dumps(l,indent=2)+'\n')
    leases=[json.loads(p.read_text()) for p in lease.parent.glob('*.json')];assert sum(x.get('concurrency',0) for x in leases)<=40
    available=int(next(s for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:')).split()[1])*1024
    free=os.statvfs(RUNS).f_bavail*os.statvfs(RUNS).f_frsize
    assert available>=6*1024**3 and free>=15*1024**3
    queue=dict(source_sha=sha,rejection_table=str(rejection),admission=dict(leases=leases,available_memory=available,disk_free=free,own_concurrency=4),runs=tasks)
    (batch/'queue.json').write_text(json.dumps(queue,indent=2)+'\n')
    ps=[]
    for t in tasks:
        env=dict(os.environ,MUJOCO_GL='osmesa',PYOPENGL_PLATFORM='osmesa',PYTHONPATH=str(ROOT),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',**t['environment'])
        with (RUNS/t['name']/'run.log').open('wb') as f:
            p=subprocess.Popen(['timeout','--signal=INT','--kill-after=60','3600',PY,str(Path(__file__).resolve()),'--worker',t['task_file']],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
        t['pid']=p.pid;ps.append(p)
    l['pids']=[p.pid for p in ps];lease.write_text(json.dumps(l,indent=2)+'\n');(batch/'queue.json').write_text(json.dumps(queue,indent=2)+'\n')
    for t,p in zip(tasks,ps):(RUNS/t['name']/'EXIT').write_text(str(p.wait())+'\n')
    (batch/'DONE').write_text(datetime.datetime.now(datetime.timezone.utc).isoformat()+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--round',type=int);p.add_argument('--worker');a=p.parse_args()
    if a.worker:worker(a.worker)
    else:launch(a.round)
