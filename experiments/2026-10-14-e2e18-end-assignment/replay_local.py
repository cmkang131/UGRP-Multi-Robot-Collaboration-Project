"""Saved-input local-end choice; GT used AFTER choice only to score end identity."""
import sys,json,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.e2e_stage_pose_eval import read
from harness.e2e_end_assignment import Selector
folder=Path(__file__).parent;audit=read(folder/'audit.json')
checks={x['checkpoint_sha256']:x for p in (ROOT/'experiments/2026-10-13-e2e18-grasp1/checkpoints').glob('*.zst') for x in [read(p)]}
rows=[]
for run in audit['runs']:
 if run['relation']!='same':continue
 cp=checks[run['checkpoint']];raw=ROOT/'outputs/azure3-runs'/run['run']/'raw';choices={}
 for rid in ['r1','r2']:
  s=Selector(rid,'rgb_local_v3');own=read(raw/f'robots/{rid}/ownmap.jsonl',True)
  x=next((x for x in own if x.get('own_beam') and x['own_beam']['rgb']['frame_id']==x['frame_id']),None)
  if x is None:choices[rid]=dict(selected=None);continue
  # Controller input ends here. No world/beam/reference truth is passed.
  candidates=s.candidates(x['own_beam'],None,x['pose_own_m']);chosen,event=s.choose(candidates)
  # Separate evaluator maps the already selected grip into the true beam axis.
  gt=read(raw/f'eval_only/{rid}/trajectory.jsonl',True);t=x['t']-cp['cutoff_s']+gt[0]['t'];times=np.array([g['t'] for g in gt]);xy=np.array([g['robot_xyz_m'][:2] for g in gt]);yaw=np.unwrap([g['robot_yaw_rad'] for g in gt]);gxy=np.array([np.interp(t,times,xy[:,k]) for k in range(2)]);gy=np.interp(t,times,yaw)
  ang=gy-x['pose_own_m'][2];R=np.array([[math.cos(ang),-math.sin(ang)],[math.sin(ang),math.cos(ang)]]);world=gxy+R@(np.array(chosen['grip_own_m'])-x['pose_own_m'][:2]);b=cp['setup_only']['beam'];center=np.array([b['x'],b['y']]);u=np.array([math.cos(b['yaw']),math.sin(b['yaw'])]);u*=1 if (np.array([4.6,-2.1])-center)@u>=0 else -1
  choices[rid]=dict(t=x['t'],frame_id=x['frame_id'],rgb_sha256=x['sha256'],selected=event,grip_own_m=chosen['grip_own_m'],evaluation_projected_end=int((world-center)@u>=0),evaluation_grip_world=world.tolist(),B_available=bool(x.get('remembered_B')))
 ok=all('evaluation_projected_end' in c for c in choices.values());opposite=ok and choices['r1']['evaluation_projected_end']!=choices['r2']['evaluation_projected_end']
 rows.append(dict(run=run['run'],first_fresh_choices_opposite=opposite,robots=choices))
result=dict(scope='first fresh own beam per robot on saved trajectory; fixed fallback only, no model, no counterfactual movement; world scoring separate',N=len(rows),opposite_choices=sum(r['first_fresh_choices_opposite'] for r in rows),physical_separation_verified=False,runs=rows)
(folder/'local-choice-replay.json').write_text(json.dumps(result,indent=2)+'\n');print({k:v for k,v in result.items() if k!='runs'})
