import json,sys,socket,shutil,time
from pathlib import Path
root=Path.cwd();sys.path.insert(0,str(root))
import mujoco,pytest
record=root/'experiments/2026-09-28-zone-pair-v6/source-regression';record.mkdir(exist_ok=True)
calls={'physics':0,'network':0}
def physical(*a,**kw):
 calls['physics']+=1;raise AssertionError('MuJoCo step forbidden')
def network(*a,**kw):
 calls['network']+=1;raise AssertionError('network forbidden')
mujoco.mj_step=mujoco.mj_step1=mujoco.mj_step2=physical
socket.create_connection=network
patterns=['test_zone_start_dock.py','test_zone_pair*.py','test_owncam*.py','test_zone_study*.py','test_rgb_execution_bundle*.py','test_m1*.py','test_record_owncam*.py']
paths=sorted({str(p) for pattern in patterns for p in Path('tests').glob(pattern)})
print('Selected',len(paths),'test files')
class Tee:
 def __init__(self,out,log):self.out,self.log=out,log
 def write(self,s):self.out.write(s);self.log.write(s)
 def flush(self):self.out.flush();self.log.flush()
 def __getattr__(self,name):return getattr(self.out,name)
args=['-q','-p','no:cacheprovider','--basetemp=./.pytest_tmp',f'--junitxml={record}/pytest.xml',*paths]
started=time.time();old=sys.stdout
with (record/'pytest.log').open('w') as log:
 sys.stdout=Tee(old,log)
 try:
  code=pytest.main(args)
  print('CALL_SENTINELS',calls)
 finally:
  sys.stdout=old
  shutil.rmtree(root/'.pytest_tmp',ignore_errors=True)
(record/'test_execution.json').write_text(json.dumps({'pytest_args':args,'exit_code':int(code),'elapsed_wall_s':time.time()-started,'sentinels':calls,'physics_step_forbidden':True,'model_calls':0,'model_scope':'fake providers only; no model worker execution','temporary_directory_removed':not (root/'.pytest_tmp').exists()},indent=2)+'\n')
raise SystemExit(code)
