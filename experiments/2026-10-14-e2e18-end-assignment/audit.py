"""Evaluation only: end occupancy and own-frame assignment projected through current GT pose."""
import sys,json,math,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.e2e_stage_pose_eval import read,wrap
checks={d['checkpoint_sha256']:d for p in (ROOT/'experiments/2026-10-13-e2e18-grasp1/checkpoints').glob('*.zst') for d in [read(p)]}
out=[]
for p in sorted((ROOT/'outputs/azure3-runs').glob('stage-*-cohort*-*-grasp-*')):
 trace=read(p/'raw/transport-trace.json');key=next(x['checkpoint_sha256'] for x in trace if x['event']=='stage_probe_entry');cp=checks[key]
 beam=cp['setup_only']['beam'];center=np.array([beam['x'],beam['y']]);u=np.array([math.cos(beam['yaw']),math.sin(beam['yaw'])]);u*=1 if (np.array([4.6,-2.1])-center)@u>=0 else -1
 # Controller stance: 0.27m band offset + 0.2032m commanded arm reach.
 stations=np.array([center-.4732*u,center+.4732*u]);row=dict(run=p.name,checkpoint=key,robots={})
 for rid in ['r1','r2']:
  own=read(p/f'raw/robots/{rid}/ownmap.jsonl',True);gt=read(p/f'raw/eval_only/{rid}/trajectory.jsonl',True)
  times=np.array([x['t'] for x in gt]);pos=np.array([x['robot_xyz_m'][:2] for x in gt]);yaw=np.unwrap([x['robot_yaw_rad'] for x in gt]);dist=np.linalg.norm(pos[:,None,:]-stations[None,:,:],axis=2)
  nearest=np.argmin(dist.min(axis=0));rr=dict(min_stance_distance_m=dist.min(axis=0).tolist(),reached_end=int(nearest) if dist.min()<.25 else None,assignment_segments=[])
  prev=None
  for x in own:
   a=x.get('carrier_approach')or{}
   if 'basis_yaw_rad' not in a:continue
   t=x['t']-cp['cutoff_s']+times[0]; gxy=np.array([np.interp(t,times,pos[:,k]) for k in range(2)]);gy=np.interp(t,times,yaw)
   op=np.array(x['pose_own_m']);ang=gy-op[2];rot=np.array([[math.cos(ang),-math.sin(ang)],[math.sin(ang),math.cos(ang)]])
   basis_world=a['basis_yaw_rad']+ang;dot=float(np.array([math.cos(basis_world),math.sin(basis_world)])@u)
   assigned=(0 if rid=='r1' else 1) if dot>=0 else (1 if rid=='r1' else 0)
   gripworld=gxy+rot@(np.array(a['grip_own_m'])-op[:2]);stworld=gxy+rot@(np.array(a['station_own_m'][:2])-op[:2]);gtend=int((gripworld-center)@u>=0)
   typ=(assigned,gtend)
   if typ!=prev:
    rr['assignment_segments'].append(dict(own_t=x['t'],physical_t=t,status=a['status'],axis_dot=dot,axis_assigned_end=assigned,grip_projected_end=gtend,grip_world_m=gripworld.tolist(),station_world_m=stworld.tolist(),own_pose=op.tolist(),gt_pose=[*gxy,gy],basis_yaw=a['basis_yaw_rad'],remembered_B=x.get('remembered_B',{}).get('center_m'),frame_id=x['frame_id']))
    prev=typ
  rr['wait_partner_events']=sum(x.get('robot_id')==rid and 'wait' in x['event'] for x in trace)
  row['robots'][rid]=rr
 a,b=[row['robots'][r]['reached_end'] for r in ['r1','r2']];row['relation']='unreached' if a is None or b is None else 'same' if a==b else 'opposite';out.append(row)
summary=dict(schema='ugrp.end_assignment_audit.v1',scope='B cohort2 + C cohort3 + C cohort4, 24 grasp runs; nearest approach over entire run, not simultaneous occupancy',evaluation_only=True,stance_offset_m=.4732,threshold_m=.25,counts={k:sum(r['relation']==k for r in out) for k in ['same','opposite','unreached']},runs=out)
dest=Path(__file__).with_name('audit.json');dest.write_text(json.dumps(summary,indent=2)+'\n')
print(summary['counts'])
for r in out:print(r['run'],r['relation'],[(k,v['reached_end'],[round(z,3) for z in v['min_stance_distance_m']]) for k,v in r['robots'].items()])
