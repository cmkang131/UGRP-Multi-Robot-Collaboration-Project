from scripts.e2e_stage_pose_eval import *
from harness.e2e_vo_innovation import select_increment,OPTIONS
from harness.e2e_rgb_vo import compose
from collections import Counter
rows=[]
for pattern in ['grasp1-stage-a1-*','stage-b-cohort2-*','stage-c-cohort3-*','stage-c-cohort4-*']:
 for run in sorted(Path('outputs/azure3-runs').glob(pattern)):
  res=read(run/'raw/result.json');route='-route-' in run.name;cutoff=read(Path('experiments/2026-10-13-e2e18-grasp1/checkpoints')/(res['source_run']+('-mapping30' if route else '')+'.json.zst'))['cutoff_s']
  for rid in ('r1','r2'):
   oo=read(run/f'raw/robots/{rid}/ownmap.jsonl',True);gg=read(run/f'raw/eval_only/{rid}/trajectory.jsonl',True)
   if len(oo)<2:continue
   ts=np.array([x['t'] for x in gg]);target=np.array([x['t']-cutoff+ts[0] for x in oo]);gt=np.array([[*x['robot_xyz_m'][:2],x['robot_yaw_rad']] for x in gg]);gt[:,2]=np.unwrap(gt[:,2]);truth=np.column_stack([np.interp(target,ts,gt[:,i]) for i in range(3)])
   for option in [*OPTIONS,'command_only']:
    pose=np.array(oo[0]['pose_continuity']['odom_pose']);traj=[pose.copy()];decisions=Counter()
    for o in oo[1:]:
     r=o['stall_odometry']
     if option=='command_only':delta=np.array(r['command_delta']);why='command_only'
     else:delta,why=select_increment(r,option=option)
     # Same original no-substep rule: a camera observation cannot inject a
     # visual delta when the original runtime had no integration steps.
     if not r.get('command_substeps'):delta=np.zeros(3)
     pose=compose(pose,delta);traj.append(pose.copy());decisions[why]+=1
    actual=np.array([o['pose_continuity']['odom_pose'] for o in oo]);repro=float(np.max(np.abs(np.asarray(traj)-actual))) if option=='off' else None
    m=align(np.asarray(traj),truth);rows.append(dict(run=run.name,robot=rid,route=route,option=option,metrics=m,off_reproduction_max_abs=repro,decisions=dict(decisions),passed=m['xy_median_m']<=.05 and m['yaw_median_deg']<=5 and .9<=m['path_ratio']<=1.1))
out=dict(scope='Frozen own-RGB increment/issued-command replay, not full PF/map/controller rerun; GT used only after trajectories produced for rigid SE2 evaluation.',rows=rows)
Path('experiments/2026-10-14-e2e18-pose/innovation-replay.json').write_text(json.dumps(out,indent=2)+'\n')
for option in [*OPTIONS,'command_only']:
 rr=[r for r in rows if r['option']==option and not r['route']];print(option,'pass',sum(r['passed'] for r in rr),'/',len(rr),{k:float(np.median([r['metrics'][k] for r in rr])) for k in ['xy_median_m','yaw_median_deg','path_ratio']})
print('off max reproduction',max(r['off_reproduction_max_abs'] for r in rows if r['option']=='off'))
