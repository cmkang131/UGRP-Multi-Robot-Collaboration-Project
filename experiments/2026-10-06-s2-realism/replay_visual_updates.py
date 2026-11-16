import sys,json,pathlib,hashlib,base64,copy,time
import numpy as np,cv2
sys.path.insert(0,'/Users/changmin/projects/ugrp-wt/drive-friction')
from harness import zone_s2_realism_contract_v122 as c,zone_pair_highpose_frame_gate as gate
from harness.zone_solo_cyan_visual_fix import Runtime
from harness.zone_pair_highpose_exact_speedups import install
work=pathlib.Path('/Users/changmin/projects/ugrp/outputs/s2-visual-fix-20261007')
run=pathlib.Path('/Users/changmin/projects/ugrp/outputs/s2-realism-e619ee57-s1046-P1-2-place')
option=sys.argv[1];_,undo=install('v98-exact-v6')
b=c.bundle('a'*40,seed=1046,**c.NEW_OPTIONS)
kwargs={k:v for k,v in b['options'].items() if k not in ('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')}
r=Runtime(c.old.hp.resolve(c.old.MAP_ID)[0],c.ROOT/c.old.CALIBRATION,c.old.CALIBRATION_SHA,seed=1046,
 **kwargs,motion_model=b['motion_model'],pulse_calibration=b['pulse_calibration'],visual_update=option)
raw=json.loads((run/'student_record.json').read_text());frames=[json.loads(l) for l in (run/'robots/r3/frames.jsonl').read_text().splitlines()]
provider=r.pose;commands={}
for cmd in raw['commands']:commands.setdefault(round(cmd['t'],6),[]).append(cmd)
provider.on_command(commands[round(frames[0]['sim_time'],6)].pop(0))
rows=[];maxerr=0.;mismatch=0
try:
 for i,(f,p) in enumerate(zip(frames,raw['poses'])):
  now=f['sim_time'];data=(run/f['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256']
  rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),1),cv2.COLOR_BGR2RGB)
  verdict,_=gate.gate().assess({**f,'image':base64.b64encode(data).decode()},'r3',now,ob=False)
  report=provider.on_frame(now,rgb if verdict==gate.VALID else None)
  err=max(abs(report.x_m-p['x']),abs(report.y_m-p['y']),abs(report.yaw_rad-p['yaw']));maxerr=max(err,maxerr);mismatch+=err>1e-12
  rows.append(dict(t=now,x=report.x_m,y=report.y_m,yaw=report.yaw_rad,last_fix_t=report.last_fix_t,std_xy=report.std_xy_m,gate=copy.deepcopy(getattr(provider.provider.loc._pf,'partial_fix_last',None))))
  for cmd in commands.get(round(now,6),[]):provider.on_command(cmd)
  if i%1000==0:print(option,i,now,maxerr,flush=True)
 (work/f'replay-{option}.json').write_text(json.dumps(dict(option=option,fixed_recorded_commands=True,physics_runs=0,model_calls=0,poses=len(rows),max_difference_from_saved=maxerr,mismatches=mismatch,stats=getattr(r,'visual_stats',None),rows=rows)))
 print(option,'done',len(rows),maxerr,mismatch,flush=True)
finally:r.close();undo()
