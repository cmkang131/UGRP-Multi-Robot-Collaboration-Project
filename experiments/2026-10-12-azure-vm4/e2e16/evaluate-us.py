"""Evaluation-only alignment of range ZUPT decisions with saved robot trajectories."""
from pathlib import Path
import json,sys,bisect,math,statistics,hashlib
root=Path(sys.argv[1]);raw=root/'raw'
def rows(p):
 if not p.exists():return []
 result=[]
 for l in p.read_text().splitlines():
  try:result.append(json.loads(l))
  except ValueError:pass
 return result
robots={}
for rid in ('r1','r2','r3'):
 own=rows(raw/f'robots/{rid}/ownmap.jsonl');frames=rows(raw/f'robots/{rid}/frames.jsonl');truth=rows(raw/f'eval_only/{rid}/trajectory.jsonl')
 byframe={x['frame_id']:x for x in frames};ts=[x['t'] for x in truth];events=[];previous=None
 def match(t):
  if not ts:return None
  i=min(bisect.bisect_left(ts,t),len(ts)-1);i=min((i,max(0,i-1)),key=lambda j:abs(ts[j]-t))
  return truth[i] if abs(ts[i]-t)<=1e-6 else None
 for x in own:
  vo=x.get('stall_odometry') or {};vo=vo.get('vo',vo);f=byframe.get(x['frame_id']);state=match(f['sim_time']) if f else None
  if vo.get('fusion')=='us_zero':
   events.append(dict(t=x['t'],frame_id=x['frame_id'],truth_aligned=state is not None and previous is not None,actual_displacement_m=math.dist(state['robot_xyz_m'][:2],previous['robot_xyz_m'][:2]) if state and previous else None,actual_dt_s=state['t']-previous['t'] if state and previous else None,command_delta=vo.get('command_delta'),fused_delta=vo.get('fused_delta'),ultrasonic=vo.get('ultrasonic')))
  previous=state
 v=[e['actual_displacement_m'] for e in events if e['actual_displacement_m'] is not None]
 robots[rid]=dict(own_frames=len(own),zupt_applied=len(events),aligned_events=len(v),actual_displacement_m=dict(max=max(v,default=None),median=statistics.median(v) if v else None),events=events)
print(json.dumps(dict(schema='ugrp.e2e16.zupt-evaluation.v1',run=root.name,evaluation_only=True,feedback_to_controller=False,interpretation='Measured displacement per decision interval; no retrospective correctness threshold invented.',robots=robots),ensure_ascii=False,indent=2))
