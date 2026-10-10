"""Post-run timeline audit; no controller imports or feedback, no gate change."""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--replays',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
root=Path('/Users/changmin/projects/ugrp/outputs');raws={'v149':root/'s3-sweep-b73ce193-s14201-v149','v150':root/'s3-odometry-4c9eb3aa-s14201-v150'}
rows=[];sources={}
def read(path,lines=False):
 sources[str(path.resolve())]=hashlib.sha256(path.read_bytes()).hexdigest()
 return [json.loads(x) for x in path.read_text().splitlines()] if lines else json.loads(path.read_text())
for case,raw in raws.items():
 state=read(a.replays/(case+'-off')/'state.json')
 for rid,loc in state.items():
  poses=loc['poses'];last=poses[-1];gate=last['last_scan_gate'];assert gate['visual_weight_update'] and gate['accepted']
  point=next(p for p in poses if p['t_est']>=gate['t'])
  gt=read(raw/f'eval_only/{rid}/trajectory.jsonl',True);times=[v['t'] for v in gt];xy=np.array([v['robot_xyz_m'][:2] for v in gt])
  def actual(t):return np.array([np.interp(t,times,xy[:,j]) for j in (0,1)])
  commands=read(raw/f'robots/{rid}/commands.jsonl',True)
  moving=[c for c in commands if c.get('kind') in ('drive','mecanum') and any(c.get(k,0) for k in ('forward','left','turn'))]
  rows.append(dict(case=case,robot=rid,last_visual_weight_update_s=gate['t'],first_report_after_update_estimate_s=point['t_est'],last_drive_t=moving[-1]['t'] if moving else None,
   error_after_last_update_m=float(np.linalg.norm(np.array([point['x'],point['y']])-actual(point['t_est']))),sigma_after_last_update_m=point['std_xy_m'],
   final_error_m=float(np.linalg.norm(np.array([last['x'],last['y']])-actual(last['t_est']))),final_sigma_m=last['std_xy_m'],
   actual_displacement_after_last_update_m=float(np.linalg.norm(actual(last['t_est'])-actual(point['t_est']))),estimated_displacement_after_last_update_m=math.dist([last['x'],last['y']],[point['x'],point['y']])))
result=dict(gt_evaluation_only=True,selection_rule_changed=False,input_sha256=sources,rows=rows,
 scope='End-to-end displacement, not path length or a causal intervention. Error is already present immediately after the latest scored update; this does not establish its unique cause.')
with a.output.open('x') as f:f.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps(dict(rows=len(rows),output=str(a.output))))
