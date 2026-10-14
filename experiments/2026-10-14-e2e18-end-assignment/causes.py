import sys,json,math,collections
from pathlib import Path
import numpy as np
sys.path.insert(0,'.');from scripts.e2e_stage_pose_eval import read
folder=Path('experiments/2026-10-14-e2e18-end-assignment');audit=read(folder/'audit.json');rows=[]
for run in audit['runs']:
 if run['relation']!='same':continue
 wrong='r2' if run['robots']['r1']['reached_end']==0 else 'r1';segs=run['robots'][wrong]['assignment_segments'];baseline=0 if wrong=='r1' else 1
 p=Path('outputs/azure3-runs')/run['run'];own=read(p/f'raw/robots/{wrong}/ownmap.jsonl',True)
 bad=next((s for s in segs if s['axis_assigned_end']!=baseline),None)
 cause='no_assigned_approach_incidental_B_search' if not segs else 'initial_basis_reversed' if segs[0]['axis_assigned_end']!=baseline else 'basis_reassigned_during_approach'
 row=dict(run=run['run'],robot=wrong,cause=cause,first_wrong=bad,approach_status_counts=dict(collections.Counter((x.get('carrier_approach')or{}).get('status','none') for x in own)))
 if bad:
  x=min(own,key=lambda x:abs(x['t']-bad['own_t']));op=np.array(x['pose_own_m']);ang=bad['gt_pose'][2]-op[2];rot=np.array([[math.cos(ang),-math.sin(ang)],[math.sin(ang),math.cos(ang)]]);B=x['remembered_B']['center_m'];row['B_world_evaluation_m']=(np.array(bad['gt_pose'][:2])+rot@(np.array(B)-op[:2])).tolist();row['B_position_error_m']=math.dist(row['B_world_evaluation_m'],[4.6,-2.1]);row['own_B']=B;row['own_beam']=x.get('own_beam')
 rows.append(row)
summary=dict(counts=dict(collections.Counter(r['cause'] for r in rows)),runs=rows,scope='assignment diagnostic only; near stance anywhere in trajectory does not establish intentional grasp or simultaneous occupancy')
(folder/'causes.json').write_text(json.dumps(summary,indent=2)+'\n');print(summary['counts'])
for r in rows:print(r['run'],r['robot'],r['cause'],round(r.get('B_position_error_m',0),3),r.get('B_world_evaluation_m'))
