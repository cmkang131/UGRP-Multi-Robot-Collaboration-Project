"""Saved-ledger counterfactual, not a physical or closed-loop success."""
import json,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.e2e_stage_pose_eval import read
from harness.e2e_acquire_recovery import failed_view
from harness.owncam_pair_beam_v2 import pose_of
base=Path(__file__).parent;rows=[]
for name in ['stage-color-cohort2-03-v425','stage-color-cohort2-09-v423','stage-color-cohort2-10-v424']:
 p=ROOT/'outputs/azure3-runs'/name;events=read(p/'raw/transport-trace.json');frames=read(p/'raw/robots/r1/frames.jsonl',True)
 plan=read(p/'STAGE_PLAN.json');cp=read(ROOT/plan['checkpoint']);cut=cp['cutoff_s']
 cancel=[e for e in events if e.get('event')=='own_arm_clearance_scan_abandoned' and e.get('robot_id')=='r1'][-1]
 view=[e for e in events if e.get('event')=='own_pregrasp_acquisition_view' and e.get('robot_id')=='r1' and e['t']<=cancel['t']][-1]
 pose=pose_of(view['camera']);pose[6]=view['pan_pulse'];a=dict(view=1,view_pose=pose);rejected=[]
 r=SimpleNamespace(camera_settle_until=-1.)
 tr=SimpleNamespace(acquire_recovery='cancel_v1',robots={'r1':r},event=lambda t,e,**k:rejected.append(dict(t=t,event=e,**k)))
 tested=0
 for f in frames:
  now=cut+f['sim_time']-1.3
  if now<=cancel['t']:continue
  r.last_obs={'frame_id':f['frame_id']};r.servo={int(k):v for k,v in f['commanded_servo'].items()}
  tested+=1
  if failed_view(tr,'r1',now,a,False):break
 assert rejected and tested==3,(name,tested)
 rows.append(dict(name=name,raw=str(p/'raw'),cancel_t=cancel['t'],new_rejection_t=rejected[0]['t'],delay_s=rejected[0]['t']-cancel['t'],distinct_frames=tested,physical_recovery_proven=False,event=rejected[0]))
out=dict(scope='counterfactual failed-view predicate over actual post-cancellation issued poses and frames; closed-loop navigation not replayed',n=3,N=3,runs=rows)
(base/'cancelled-view-replay.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
