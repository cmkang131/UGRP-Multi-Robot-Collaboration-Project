"""Closed s1051 evaluation: motion/heading contributions, never a controller input."""
import json,sys,math
from pathlib import Path
import numpy as np
from scripts.fit_s2_pulse_calibration import interpolate
from harness import zone_solo_cyan_contract_v106 as c
sys.path.insert(0,str(Path(__file__).resolve().parent))
from analyze_visibility import wall_segments

def main(folder):
 criteria=json.loads(Path(__file__).with_name('load-height-criteria.json').read_text());raw=Path(criteria['evaluation']['raw'])
 record=json.loads((raw/'student_record.json').read_text());gt=[json.loads(l) for l in (raw/'eval_only/trajectory.jsonl').read_text().splitlines()]
 pulses=[json.loads(l) for l in (folder/'eval-pulses.jsonl').read_text().splitlines()]
 model=json.loads(Path('configs/s2_motion_v7_pulse_cal_v1.json').read_text());new=json.loads(Path('configs/s2_motion_load_conditioned_v1.json').read_text())
 times=np.array([r['t'] for r in gt]);values=np.array([[*r['robot_xyz_m'][:2],r['robot_yaw_rad']] for r in gt]);values[:,2]=np.unwrap(values[:,2])
 pt=np.array([r['t_est'] for r in record['poses']]);yaw=np.unwrap([r['yaw'] for r in record['poses']]);lo,hi=criteria['evaluation']['carry_window_sim_s']
 pose=lambda t:np.array([np.interp(t,times,values[:,i]) for i in range(3)])
 rot=lambda y:np.array([[np.cos(y),-np.sin(y)],[np.sin(y),np.cos(y)]])
 seg=wall_segments(c.hp.resolve(c.MAP_ID)[0])[:,:,:2];dv=seg[:,1]-seg[:,0]
 def wall_distance(xy):
  u=np.clip(((xy-seg[:,0])*dv).sum(1)/(dv*dv).sum(1),0,1)
  return float(np.linalg.norm(xy-(seg[:,0]+u[:,None]*dv),axis=1).min())
 rows=[]
 for row in pulses:
  if not lo<=row['t']<hi:continue
  p=model['profiles'][row['key']];t=row['t'];end=t+p['times'][-1];start=pose(t);actual=pose(end);pred=np.array(p['mean_delta']);local=interpolate(row,[p['times'][-1]])[0]
  true_r=rot(start[2]);est_yaw=float(np.interp(t,pt,yaw));est_r=rot(est_yaw)
  command_error=true_r@(pred[:2]-local[:2]);heading_error=(est_r-true_r)@pred[:2];total=command_error+heading_error
  contribution=(float(command_error@command_error+command_error@heading_error),float(heading_error@heading_error+command_error@heading_error))
  rows.append(dict(t=t,key=row['key'],loaded=row['loaded'],predicted_delta=pred.tolist(),actual_delta=local.tolist(),
   old_endpoint_xy_error_m=float(np.linalg.norm(pred[:2]-local[:2])),new_endpoint_xy_error_m=float(np.linalg.norm(np.array(new['profiles'][row['key']]['mean_delta'])[:2]-local[:2])),
   nominal_direction_progress_ratio=float(local[:2]@pred[:2]/(pred[:2]@pred[:2])) if np.linalg.norm(pred[:2])>.003 else None,
   yaw_error_deg=float(np.degrees(math.atan2(math.sin(est_yaw-start[2]),math.cos(est_yaw-start[2])))),
   command_error_world=command_error.tolist(),heading_error_world=heading_error.tolist(),total_world_increment_error=total.tolist(),
   symmetric_squared_error_contributions=list(contribution),start_wall_center_distance_m=wall_distance(start[:2]),
   start_xy=start[:2].tolist(),end_xy=actual[:2].tolist()))
 sums=np.sum([r['symmetric_squared_error_contributions'] for r in rows],axis=0)
 stalled=[r for r in rows if r['nominal_direction_progress_ratio'] is not None and r['nominal_direction_progress_ratio']<.25]
 groups={}
 for k in sorted({r['key'] for r in rows}):
  group=[r for r in rows if r['key']==k];d=np.array([r['actual_delta'] for r in group]);e=np.array([r['old_endpoint_xy_error_m'] for r in group])
  groups[k]=dict(n=len(group),actual_quantiles=np.quantile(d,[.05,.5,.95],axis=0).tolist(),xy_sse_m2=float(e@e),xy_rmse_m=float(np.sqrt(np.mean(e*e))),stalled=sum(r in stalled for r in group))
 report=dict(schema='ugrp.s2.load_drift.v1',physics_runs=0,model_calls=0,gt_usage='completed s1051 evaluation only',carry_window=[lo,hi],n=len(rows),
  local_motion_sse_by_profile=groups,world_increment_sse_contribution=dict(command_bias_and_slip=float(sums[0]),heading=float(sums[1]),fraction=(sums/sums.sum()).tolist()),
  contribution_method='For each fixed command horizon, e=R(true)*(pred-actual_body)+(R(estimate)-R(true))*pred; split cross term equally. Descriptive signed SSE, not causal attribution of global trajectory RMSE.',
  slow_pulses=dict(n=len(stalled),definition='actual progress along nominal translation <25%; evaluator only',wall_center_distance_median_m=float(np.median([r['start_wall_center_distance_m'] for r in stalled])) if stalled else None,rows=stalled),rows=rows)
 with (folder/'drift-decomposition.json').open('x') as f:f.write(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ['rows','slow_pulses','local_motion_sse_by_profile']},indent=2));print(json.dumps(groups,indent=2))
if __name__=='__main__':main(Path(sys.argv[1]))
