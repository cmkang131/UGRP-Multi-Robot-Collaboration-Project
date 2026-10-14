"""Post-run predicate/visibility audit. Evaluation poses never enter control."""
import json,sys,bisect,math,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.e2e_stage_pose_eval import read
base=Path(__file__).parent;out=[]
for p in sorted((ROOT/'outputs/azure3-runs').glob('stage-approach-cohort1-*')):
 cp=read(ROOT/read(p/'STAGE_PLAN.json')['checkpoint']);cut=cp['cutoff_s'];item=dict(name=p.name,robots={})
 for rid in ['r1','r2']:
  own=read(p/f'raw/robots/{rid}/ownmap.jsonl',True);gt=read(p/f'raw/eval_only/{rid}/trajectory.jsonl',True)
  times=[r['t'] for r in own];anchor=None;maxstill=0.
  for row in gt:
   now=row['t']-1.3+cut;i=bisect.bisect_right(times,now)-1
   scan=i>=0 and (own[i].get('carrier_approach') or {}).get('status')=='acquire_scan'
   if not scan:anchor=None;continue
   if anchor is None or math.dist(row['robot_xyz_m'],anchor['robot_xyz_m'])>.002 or abs(math.atan2(math.sin(row['robot_yaw_rad']-anchor['robot_yaw_rad']),math.cos(row['robot_yaw_rad']-anchor['robot_yaw_rad'])))>.004:anchor=row
   maxstill=max(maxstill,row['t']-anchor['t'])
  obs=[(r.get('own_beam_observation') or {}).get('result',{}) for r in own]
  item['robots'][rid]=dict(frames=len(own),max_stationary_acquire_scan_s=maxstill,body_visible=sum(bool(o.get('visible')) for o in obs),end_visible=sum(bool(o.get('end_visible')) for o in obs),observation_reasons=dict(collections.Counter(o.get('reason') for o in obs)))
 out.append(item)
result=dict(evaluation_only=True,N=len(out),scan_deadlock_over20_N=sum(any(x['max_stationary_acquire_scan_s']>=20 for x in r['robots'].values()) for r in out),max_stationary_scan_s=max(x['max_stationary_acquire_scan_s'] for r in out for x in r['robots'].values()),runs=out,next_hypothesis='body RGB can be visible while assigned band is absent: Robot._receive only publishes beam when end_visible. Test body-only gaze/search guidance without granting end identity or grasp readiness; not implemented or proven here.')
(base/'recovery-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='runs'}))
