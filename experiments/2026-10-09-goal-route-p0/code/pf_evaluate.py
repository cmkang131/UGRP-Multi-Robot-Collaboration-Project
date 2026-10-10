"""Post-seal P0-2 score, no estimation or runtime import."""
from map_replay import *
from harness.self_pose_graph import wrap
FIELDS=('t_est','x','y','yaw','std_xy_m','std_yaw_rad','last_fix_t')
def main():
 plan=load(Path('/Users/changmin/projects/ugrp-wt/ownmap-s2/experiments/2026-10-09-ownmap-s2/registration-v2.json'));results=[]
 for p in plan['pairs']:
  truth=rows(Path(p['raw'])/'eval_only/trajectory.jsonl');ts=np.array([r['t'] for r in truth]);xy=np.array([r['robot_xyz_m'][:2] for r in truth]);yaw=np.unwrap([r['robot_yaw_rad'] for r in truth])
  reference={round(r['t'],6):r for r in load(Path(p['raw'])/'student_record.json')['poses']}
  result=dict(pair=p['id'])
  for mode in ['off','two_doors_static_v1']:
   dest=OUT/'pf'/p['id']/mode;receipt=load(dest/'prediction.json');assert sha(dest/'poses.json')==receipt['prediction_sha256']
   poses=load(dest/'poses.json');first=next((q for q in poses if q.get('initialized',True) and q['std_xy_m']<=.05),None)
   if first:
    t=first['t_est'];covered=bool(ts[0]<=t<=ts[-1]);actual=np.array([np.interp(t,ts,xy[:,0]),np.interp(t,ts,xy[:,1]),np.interp(t,ts,yaw)])
    error=float(np.linalg.norm(np.array([first['x'],first['y']])-actual[:2]));angle=abs(math.degrees(float(wrap(first['yaw']-actual[2]))))
   else:covered=False;error=angle=None
   identical=all(json.dumps({k:q[k] for k in FIELDS}).encode()==json.dumps({k:reference[round(q['t'],6)][k] for k in FIELDS}).encode() for q in poses) if mode=='off' else None
   result[mode]=dict(first_t=None if first is None else first['t'],xy_error_m=error,yaw_error_deg=angle,correct=bool(covered and error<=.25 and angle<=15),missing_truth=bool(first and not covered),converged=first is not None,frames=len(poses),available_frames=receipt['available_frames'],prefix_bytes_identical=identical,source_sha=receipt['source_sha'],map_id=receipt['map_id'])
  results.append(result)
 n=sum(r['two_doors_static_v1']['correct'] for r in results)
 summary=dict(pairs=results,registered=7,scored=len(results),excluded=[],off_correct=sum(r['off']['correct'] for r in results),other_map_correct=n,
  off_prefixes_byte_identical=sum(r['off']['prefix_bytes_identical'] for r in results),
  decision='same_arena_rebuild_required' if n<=4 else 'arena_mismatch_not_primary' if n>=6 else 'undetermined',physics=0)
 dump(EXP/'results/pf.json',summary);print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
