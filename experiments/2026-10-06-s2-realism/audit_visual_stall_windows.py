import sys,json,pathlib,copy,hashlib,collections,cv2,numpy as np
sys.path.insert(0,'/Users/changmin/projects/ugrp-wt/drive-friction')
from harness.zone_solo_cyan_visual_fix import Runtime,Previous,flow_pair,FLOW
ROOT=pathlib.Path('/Users/changmin/projects/ugrp/outputs');WORK=ROOT/'s2-visual-fix-20261007'
# Use the actual monitor methods on a recorded-input-only object. The inherited
# controller/provider calls are suppressed; commands come exclusively from raw.
Previous.on_command=lambda *a:None
Previous.on_frames=lambda *a:None
allrows=[];summary={}
for seed,sha in [(1045,'f0bb26e7'),(1046,'e619ee57')]:
 run=ROOT/f's2-realism-{sha}-s{seed}-P1-2-place';raw=json.loads((run/'student_record.json').read_text());frames=[json.loads(l) for l in (run/'robots/r3/frames.jsonl').read_text().splitlines()];traj=[json.loads(l) for l in (run/'eval_only/trajectory.jsonl').read_text().splitlines()];tt=np.array([x['t'] for x in traj])
 r=object.__new__(Runtime);r.robot_id='r3';r.visual_stall='lk_pulse_v1';r.flow_pending=None;r.flow_frame=None;r.flow_frame_t=None;r.flow_streak=0;r.flow_rows=[];r.soft=lambda *a:None;r.pulse_profiles=json.loads(pathlib.Path('configs/s2_motion_v7_pulse_cal_v1.json').read_text())['profiles']
 events=[e for e in raw['events'] if e['event']=='state'];commands={}
 for cmd in raw['commands']:commands.setdefault(round(cmd['t'],6),[]).append(cmd)
 state='scan';events=iter(events);event=next(events,None)
 for f in frames:
  now=f['sim_time']
  while event and now>=event['t']:
   state=event['state'];event=next(events,None)
  r.state=state;r.servo={int(k):v for k,v in f['commanded_servo'].items()}
  if state!='carry':r.flow_pending=None;r.flow_frame=None;continue
  data=(run/f['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256']
  rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),1),cv2.COLOR_BGR2RGB)
  r.on_frames(now,{'r3':(f,rgb)})
  for cmd in commands.get(round(now,6),[]):
   if cmd['kind']=='mecanum' and any(cmd.get(k,0) for k in ('forward','left','turn')):
    from harness.zone_solo_cyan_pulse_cal import profile_key
    if profile_key(cmd,True) not in r.pulse_profiles:continue
   r.on_command('r3',now,{k:v for k,v in cmd.items() if k!='t'})
 for row in r.flow_rows:
  a=traj[int(np.argmin(abs(tt-row['before_t'])))];b=traj[int(np.argmin(abs(tt-row['after_t'])))];dy=(b['robot_yaw_rad']-a['robot_yaw_rad']+np.pi)%(2*np.pi)-np.pi
  row.update(seed=seed,eval_only=dict(distance_m=float(np.linalg.norm(np.array(b['robot_xyz_m'][:2])-a['robot_xyz_m'][:2])),yaw_deg=float(np.degrees(dy))))
 allrows+=r.flow_rows
 summary[str(seed)]=dict(windows=len(r.flow_rows),counts=dict(collections.Counter(x['status'] for x in r.flow_rows)),would_stop=[x for x in r.flow_rows if x['would_stop']])
 print(seed,len(r.flow_rows),summary[str(seed)]['counts'],flush=True)
(WORK/'flow-windows.json').write_text(json.dumps(allrows,indent=1)+'\n');(WORK/'flow-window-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
