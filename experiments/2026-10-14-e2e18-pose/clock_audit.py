from scripts.e2e_stage_pose_eval import *

rows=[]
for pattern in ['grasp1-stage-a1-*','stage-b-cohort2-*','stage-c-cohort3-*','stage-c-cohort4-*']:
 for run in sorted(Path('outputs/azure3-runs').glob(pattern)):
  result=read(run/'raw/result.json');route='-route-' in run.name
  cp=Path('experiments/2026-10-13-e2e18-grasp1/checkpoints')/(result['source_run']+('-mapping30' if route else '')+'.json.zst');cutoff=read(cp)['cutoff_s']
  for rid in ('r1','r2'):
   oo=read(run/f'raw/robots/{rid}/ownmap.jsonl',True);gg=read(run/f'raw/eval_only/{rid}/trajectory.jsonl',True)
   if len(oo)<2:continue
   ts=np.array([x['t'] for x in gg]);target=np.array([x['t']-cutoff+ts[0] for x in oo]);assert target.min()>=ts[0]-1e-6 and target.max()<=ts[-1]+.051,(run,target.min(),target.max(),ts[-1])
   g=np.array([[*x['robot_xyz_m'][:2],x['robot_yaw_rad']] for x in gg]);g[:,2]=np.unwrap(g[:,2]);truth=np.column_stack([np.interp(target,ts,g[:,i]) for i in range(3)])
   own=np.array([x['pose_own_m'] for x in oo]);odom=np.array([x['pose_continuity']['odom_pose'] for x in oo]);raw=np.array([x['pose_continuity']['raw_selected_pose'] for x in oo]);oldtarget=np.array([x['t'] for x in oo]);oldidx=np.minimum(np.searchsorted(ts,oldtarget),len(ts)-1)
   d=dict(run=run.name,robot=rid,condition=result['condition'],route=route,cutoff_s=cutoff,physics_start_s=float(ts[0]),N=len(oo),map=align(own,truth),continuous_fused_odom=align(odom,truth),raw_selected=align(raw,truth),old_unshifted=align(own,g[oldidx]))
   rows.append(d)
out=Path('experiments/2026-10-14-e2e18-pose/clock-corrected-audit.json');out.write_text(json.dumps(dict(rows=rows),indent=2)+'\n')
for key in ['map','continuous_fused_odom','raw_selected','old_unshifted']:
 rr=[r for r in rows if not r['route']];print(key,len(rr),{m:[round(float(x),4) for x in np.quantile([r[key][m] for r in rr if r[key][m] is not None],[0,.5,1])] for m in ['xy_median_m','yaw_median_deg','yaw_demeaned_median_deg','path_ratio']})
print('PASS per robot',sum(r['map']['xy_median_m']<=.05 and r['map']['yaw_median_deg']<=5 and .9<=r['map']['path_ratio']<=1.1 for r in rows if not r['route']))
