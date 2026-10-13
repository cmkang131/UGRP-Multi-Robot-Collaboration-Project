"""Saved-input decision replay only; changed motion is not simulated."""
import sys,json,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.e2e_stage_pose_eval import read
from harness.e2e_end_assignment import Selector
folder=Path(__file__).parent;manifest=read(folder/'replay-input-manifest.json');audit=read(folder/'audit.json');out=[]
for run in audit['runs']:
 if run['relation']!='same':continue
 for rid in ['r1','r2']:
  raw=ROOT/'outputs/azure3-runs'/run['run']/'raw';own=read(raw/f'robots/{rid}/ownmap.jsonl',True);ownby={x['sha256']:x for x in own}
  for mode in ['lock_v1','rgb_rule_v1']:
   selector=Selector(rid,mode);rows=[]
   for f in [f for f in manifest if f['run']==run['run'] and f['rid']==rid]:
    x=ownby[f['sha256']];a=x.get('carrier_approach')or{};B=x.get('remembered_B')
    if not B or 'basis_yaw_rad' not in a:continue
    yaw=a['basis_yaw_rad'];sign=-1 if rid=='r1' else 1;u=np.array([math.cos(yaw),math.sin(yaw)])
    center=np.array(a['grip_own_m'])-sign*.27*u
    beam=dict(pose_own_m=[*center.tolist(),yaw],rgb=dict(robot_id=rid,frame_id=x['frame_id'],t_sim=x['t'],sha256=x['sha256']))
    pose=x['pose_own_m'];c=selector.candidates(beam,B['center_m'],pose)
    occ=selector.observe_occupancy(c,pose,f['servo'],(ROOT/f['path']).read_bytes(),f['frame_id'],x['t'],x['t'])
    selected,event=selector.choose(c)
    # Compare planned stance to original planned stance, not GT control.
    rows.append(dict(t=x['t'],frame_id=x['frame_id'],rgb_sha256=x['sha256'],source_path=f['path'],
      selected=event,occupancy=occ,changed_original_stance=selected is not None and math.dist(selected['station_own_m'][:2],a['station_own_m'][:2])>.3,
      proposed_station=selected['station_own_m'] if selected else None,original_station=a['station_own_m'],candidates=c))
   out.append(dict(run=run['run'],robot=rid,mode=mode,frames=len(rows),changed_frames=sum(r['changed_original_stance'] for r in rows),occupied_frames=sum(bool(r['occupancy'].get('blocked')) for r in rows),rows=rows))
summary=dict(scope='sparse saved own RGB at 13 evenly spaced times/robot; no counterfactual motion; path cost unmeasured offline',
 records=len(out),evaluated_rgb_frames=sum(r['frames'] for r in out if r['mode']=='rgb_rule_v1'),
 changed_runs={mode:sorted({r['run'] for r in out if r['mode']==mode and r['changed_frames']}) for mode in ['lock_v1','rgb_rule_v1']},
 occupancy_runs=sorted({r['run'] for r in out if r['occupied_frames']}),physical_separation_verified=False,results=out)
(folder/'replay.json').write_text(json.dumps(summary,separators=(',',':'))+'\n')
print({k:v for k,v in summary.items() if k!='results'})
