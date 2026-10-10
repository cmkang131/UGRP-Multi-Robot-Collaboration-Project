"""Evaluation-only source geometry and mixed-wall diagnostic; never imported by replay."""
import json,hashlib,sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from harness.ownmap_s2 import GridField
from harness.zone_solo_cyan_likelihood_field import Field
from harness.zone_solo_cyan_amcl_sensor import likelihood
from scripts.evaluate_ownmap_s2 import to_world,to_own,TreeField,truth_arrays,interpolate
from scripts.replay_ownmap_s2 import read,rows,sha,write


def occupied(field):
 yy,xx=np.nonzero(field.dist==0)
 return field.origin+np.c_[xx,yy]*field.res


def evaluate(raw,evaluation,registration):
 result=read(evaluation/'result.json');plan=read(registration);summaries=[]
 for pair,outcome in zip(plan['pairs'],result['pairs']):
  assert pair['id']==outcome['pair_id']
  map_root=Path(pair['map_raw']);s2_root=Path(pair['raw'])
  source_path=map_root/'inputs/static_map.json';target_path=s2_root/'inputs/static_map.json'
  source,target=read(source_path),read(target_path);sf,tf=Field(source),Field(target)
  walls=lambda m: sorted((json.dumps(w,sort_keys=True) for w in m["obstacles"] if w.get("kind")=="wall"))
  same_walls=walls(source)==walls(target)
  sp,tp=occupied(sf),occupied(tf)
  map_truth=rows(map_root/'eval_only/trajectory.jsonl')[0]
  anchor=np.r_[map_truth['robot_xyz_m'][:2],map_truth['robot_yaw_rad']]
  own=read(raw/pair['id']/'own_grid_v1/own-map.json');g=np.array(own['occupancy_grid']['cells'])
  points=to_world((g[g[:,2]>0,:2]+.5)*own['occupancy_grid']['resolution_m'],anchor)
  ot=cKDTree(points);st=cKDTree(sp);tt=cKDTree(tp)
  target_to_source=st.query(tp)[0];common=tp[target_to_source<=.011]
  common_dist=ot.query(common)[0]
  source_error=st.query(points)[0];target_error=tt.query(points)[0]
  target_dist=ot.query(tp)[0]
  supported=TreeField(tp[target_dist<=.4]);ownfield=GridField(own)
  class Mixed:
   def distances(self,ps):
    return np.minimum(ownfield.distances(to_own(ps,anchor)),supported.distances(ps))
  truth=truth_arrays(rows(s2_root/'eval_only/trajectory.jsonl'))
  # Evaluation-only support along the recorded physical trajectory. No prior
  # or localization update is derived from these labels.
  ij=np.floor(to_own(truth[1],anchor)/ownfield.grid_resolution).astype(int)-ownfield.lo
  inside=(ij[:,0]>=0)&(ij[:,1]>=0)&(ij[:,0]<ownfield.raw.shape[1])&(ij[:,1]<ownfield.raw.shape[0])
  states=np.full(len(ij),255);states[inside]=ownfield.raw[ij[inside,1],ij[inside,0]]
  support_counts={name:int(np.sum(states==value)) for name,value in [('free',0),('occupied',254),('unknown',255)]}
  support_counts.update(samples=len(states),first_gt_cell={0:'free',254:'occupied',255:'unknown'}[int(states[0])],scope='mapping-frame labels at original S2 GT trajectory samples; evaluation only')
  measurements=read(s2_root/'student_record.json')['sensor_landmarks']['rows'];oracles=[]
  for packet in measurements:
   t=packet['t']
   if not truth[0][0]<=t<=truth[0][-1]:continue
   pose=interpolate(truth,[t])[0];local=np.r_[to_own(pose[:2],anchor),pose[2]-anchor[2]]
   pts=np.asarray(packet['wall_points'],float).reshape(-1,2)
   a=float(likelihood(ownfield,local[None],pts)[0]);b=float(likelihood(Mixed(),pose[None],pts)[0]);c=float(likelihood(tf,pose[None],pts)[0])
   assert b>=a-1e-10
   oracles.append(dict(t=t,own=a,own_plus_supported_gt=b,full_gt=c,gt_use='EVALUATION_ONLY'))
  ds=read(evaluation/(pair['id']+'-diagnostic.json'))['oracle_rows']
  actual_packets={}
  for option in ('off','own_grid_v1'):
   packets=read(raw/pair['id']/option/'measurements.json')['rows']
   actual_packets[option]=dict(packets=len(packets),wall_endpoints=sum(q['wall_count'] for q in packets),floor_features=sum(f['kind']=='floor_line' for q in packets for f in q['features']),door_features=sum(f['kind']=='door' for q in packets for f in q['features']))
  summary=dict(pair_id=pair['id'],map_seed=outcome['map_seed'],
   same_static_wall_geometry=same_walls,source_map_id=source['map_id'],target_map_id=target['map_id'],
   source_files={str(p):sha(p) for p in (source_path,target_path,map_root/'scene.xml',s2_root/'scene.xml')},
   original_median_wall_distance_is_truncated_at_m=2.,
   own_to_mapping_world_wall_uncapped_m={k:float(v) for k,v in zip(['median','p90','max'],np.quantile(source_error,[.5,.9,1]))},
   own_to_s2_world_wall_uncapped_m={k:float(v) for k,v in zip(['median','p90','max'],np.quantile(target_error,[.5,.9,1]))},
   target_wall_absent_in_mapping_world_fraction=float(np.mean(target_to_source>.011)),
   common_wall_coverage_20cm=float(np.mean(common_dist<=.2)),common_wall_coverage_40cm=float(np.mean(common_dist<=.4)),
   observed_floor_edges=len(own['observed_floor_edges']),observed_doors=len(own['observed_doors']),
   original_gt_trajectory_map_support=support_counts,actual_replay_sensor_counts=actual_packets,
   oracle_samples=len(oracles),mean_log_wall_score_gain_mixed_gt=float(np.mean([np.log(q['own_plus_supported_gt']/q['own']) for q in oracles])) if oracles else None,
   mean_log_wall_score_gain_full_gt=float(np.mean([np.log(q['full_gt']/q['own']) for q in oracles])) if oracles else None,
   mean_log_landmark_score_own_minus_gt=float(np.mean([q['own_landmark_log_score']-q['full_gt_landmark_log_score'] for q in ds])) if ds else None,
   scope='evaluation only, fixed true poses and shared original sensor packets; no PF run, correction, tuning or causal-success claim')
  summaries.append(summary)
  write(evaluation/(pair['id']+'-mixed-wall-oracle.json'),oracles)
 write(evaluation/'source-diagnostics.json',dict(gt_use='EVALUATION_ONLY',pairs=summaries))
 return summaries

if __name__=='__main__':
 print(json.dumps(evaluate(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3])),indent=2))
