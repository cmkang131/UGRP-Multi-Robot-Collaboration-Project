"""Nonphysical full related suite; inherited tripwire covers Python children."""
import json, os, shutil, sys, time
from pathlib import Path
root=Path.cwd(); sys.path.insert(0,str(root))
import pytest
record=Path(__file__).resolve().parent
assert os.environ.get('OMP_NUM_THREADS')=='1'
patterns=['test_zone_start_dock*.py','test_zone_pair*.py','test_owncam*.py','test_zone_own*.py',
          'test_zone_study*.py','test_rgb_execution_bundle*.py','test_m1*.py','test_record_owncam*.py',
          'test_pair_owncam_approach.py','test_m2_pair_door_v3.py','test_pose_provider*.py']
paths=sorted({str(p) for pattern in patterns for p in Path('tests').glob(pattern)})
args=['-q','-p','no:cacheprovider','-p','tests.pose_provider_no_physics','--basetemp=./.pytest_tmp',
      f'--junitxml={record}/pytest.xml',*paths]
class Tee:
 def __init__(self,out,log): self.out,self.log=out,log
 def write(self,s): self.out.write(s);self.log.write(s)
 def flush(self): self.out.flush();self.log.flush()
 def __getattr__(self,k): return getattr(self.out,k)
started=time.time();old=sys.stdout
with (record/'pytest.log').open('w') as log:
 sys.stdout=Tee(old,log)
 try:
  code=pytest.main(args)
 finally:
  sys.stdout=old
  shutil.rmtree(root/'.pytest_tmp',ignore_errors=True)
from tests.pose_provider_no_physics import COUNTS
(record/'test_execution.json').write_text(json.dumps({
 'pytest_args':args,'exit_code':int(code),'test_files':len(paths),'elapsed_wall_s':time.time()-started,
 'suite_guards':COUNTS,'OMP_NUM_THREADS':os.environ['OMP_NUM_THREADS'],
 'physics_step_forbidden':True,'model_calls':0,'model_scope':'command response and fake providers only',
 'child_step_audit':os.environ.get('V6_STEP_AUDIT'),
 'temporary_directory_removed':not (root/'.pytest_tmp').exists()},indent=2)+'\n')
raise SystemExit(code)
