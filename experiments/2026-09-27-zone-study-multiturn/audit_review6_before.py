"""Reproduce review6 against the unchanged HEAD; run from repository root."""
import builtins
import json
from pathlib import Path
import socket
import subprocess
import sys
import types
BASE_HEAD = '9fb47846b4bbb35be5692345843aadd896b6e3eb'
ROOT=Path.cwd()
sys.path.insert(0,str(ROOT));sys.modules['mujoco']=None
socket.socket.connect = socket.socket.connect_ex = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('network forbidden'))
import harness
from harness import zone_event_scheduler as current
from tests import test_zone_study_multiturn as fixture
from tests.test_zone_study_multiturn_review6 import run_review6
package=types.ModuleType('harness');package.__dict__.update(harness.__dict__)
modules={}
def imports(name, globals=None, locals=None, fromlist=(), level=0):
    if name in modules:return modules[name]
    if name=='harness':return package
    return builtins.__import__(name,globals,locals,fromlist,level)
for name in ('zone_event_scheduler','zone_study_decisions','zone_study_integration'):
    data=subprocess.check_output(['git','show',f'{BASE_HEAD}:harness/{name}.py'])
    m=types.ModuleType('_review6_before_'+name);m.__file__=str(ROOT/'harness'/f'{name}.py')
    m.__dict__['__builtins__']={**vars(builtins),'__import__':imports};sys.modules[m.__name__]=m
    exec(compile(data,m.__file__,'exec'),m.__dict__)
    modules['harness.'+name]=m;setattr(package,name,m)
    if name=='zone_event_scheduler':
        for dto in ('CallReply','TransportFailure','NotSent'):setattr(m,dto,getattr(current,dto))
class Before(m.IntegratedTrial):
    sim_output_tokens=fixture.TimingTrial.sim_output_tokens
make=fixture.make_trial
captured=[]
def capture(*args, **kwargs):
    out=make(*args,**kwargs);captured[:]=[out];return out
fixture.make_trial=capture
rows=[]
for case, times, conditions in (
 ('separate_roots',[5.4,5.5,5.6,5.7,5.8,5.9],('peer_ko','leader_ko','structured')),
 ('timer_reservation',[4.9,5.,5.1,5.2,5.3,5.4,5.5,5.6],('no_comm','peer_ko','leader_ko','structured')),
 ('refund_horizon',[5.5],('peer_ko','leader_ko','structured'))):
 for at in times:
  for condition in conditions:
   error=None
   try:run_review6(case,condition,trial_cls=Before,at=at)
   except AssertionError as exc:error=repr(exc)
   trial,_,_,requests=captured[0]
   rows.append(dict(case=case,at=at,condition=condition,failed=error is not None,error=error,
       sends=[(p['robot_id'],p['sim_time_s']) for p in requests],
       budget=trial.scheduler.budget.to_dict(),
       end_reason=trial.finish(trial.scheduler.now()).end_reason))
path=ROOT/'experiments/2026-09-27-zone-study-multiturn/review6-counterexamples-before.json'
path.write_text(json.dumps({'head':BASE_HEAD,
                          'model_calls':0,'physics_steps':0,'rows':rows},ensure_ascii=False,indent=2)+'\n')
for case in sorted({r['case'] for r in rows}):
 selected=[r for r in rows if r['case']==case]
 print(case,sum(r['failed'] for r in selected),'failed /',len(selected))
