"""Score all frozen predictors; the runtime/replay never loads these truth rows."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent

def main(out):
 criteria=json.loads((HERE/'load-height-criteria.json').read_text());raw=Path(criteria['evaluation']['raw']);lo,hi=criteria['evaluation']['carry_window_sim_s']
 gt=[json.loads(l) for l in (raw/'eval_only/trajectory.jsonl').read_text().splitlines()];tt=[r['t'] for r in gt];xy=np.array([r['robot_xyz_m'][:2] for r in gt]);results=[]
 for name in criteria['factorial']:
  path=out/f'replay-{name}.json';d=json.loads(path.read_text());assert d['frames']==5202 and not d['gt_inputs'] and not d['physics_runs']
  error=[];stationary=[]
  for row in d['poses']:
   pos=[np.interp(row['t_est'],tt,xy[:,i]) for i in (0,1)];e=float(np.linalg.norm(np.array([row['x'],row['y']])-pos))
   if lo<=row['t']<hi:error.append(e)
   if row['t_est']<12:stationary.append(e)
  fixes=sorted({r['t'] for r in d['amcl']['rows'] if lo<=r['t']<hi and r['visual_weight_update']})
  results.append(dict(option=name,carry_rmse_m=float(np.sqrt(np.mean(np.square(error)))),end_error_m=error[-1],
   carry_updates=len(fixes),max_update_gap_sim_s=float(max(np.diff([lo,*fixes,hi]))),initial_stationary_max_m=max(stationary),
   max_off_difference=d['baseline_max_delta'],source_sha=d['source_sha'],path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
 assert abs(results[0]['carry_rmse_m']-criteria['evaluation']['baseline_rmse_m'])<1e-12
 motion=json.loads((out/'motion-summary.json').read_text());height=json.loads((out/'height-contact-summary.json').read_text())['summary']
 old=motion['baseline']['load_scores']['loaded'];new=motion['candidate']['load_scores']['loaded'];rmse=results[0]['carry_rmse_m']
 gates=dict(off_exact=results[0]['max_off_difference']==0.,load_endpoint_xy=new['xy_rmse_m']<old['xy_rmse_m'],load_endpoint_yaw=new['yaw_rmse_deg']<=old['yaw_rmse_deg'],
  height_floor_fraction=height['height_floor_fraction'] is not None and height['height_floor_fraction']<height['baseline_floor_fraction'],height_wall_retention=height['true_wall_retention']>=.9)
 for r in results[1:]:
  gates[r['option']+'_rmse']=r['carry_rmse_m']<rmse
  gates[r['option']+'_updates']=r['carry_updates']>=1
  gates[r['option']+'_stationary']=r['initial_stationary_max_m']<=.5
 report=dict(schema='ugrp.s2.load_height.summary.v1',admission_pass=all(gates.values()),gates=gates,results=results,
  physics_runs=0,model_calls=0,new_seed=None,new_execution_bundle=None,full_dev='NOT_RUN_CRITERIA_FAILED' if not all(gates.values()) else 'ADMITTED_NOT_YET_RUN',
  criteria_sha256=hashlib.sha256((HERE/'load-height-criteria.json').read_bytes()).hexdigest(),motion_scores=dict(baseline=old,candidate=new),height_scores=height,
  limits='Exploratory frozen-command replay; no new physical lifted/inside/visibility/B distance/wall-SIM metrics. No outcome-driven tuning or additional candidate.')
 with (out/'summary.json').open('x') as f:f.write(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main(Path(sys.argv[1]))
