from scripts.e2e_stage_pose_eval import *
from collections import Counter,defaultdict
stats=defaultdict(list); details=[]; modes=Counter();correction=Counter();cmdrows=[]
def quant(a):
 a=np.asarray(a,float);a=a[np.isfinite(a)]
 return dict(n=len(a),q=[float(x) for x in np.quantile(a,[0,.5,.9,.95,1])],sum=float(a.sum())) if len(a) else dict(n=0)
def metric(a,b):
 if len(a)<2:return None
 return align(np.asarray(a),np.asarray(b))
def between(a,b):
 c,s=np.cos(a[2]),np.sin(a[2]);d=np.asarray(b[:2])-a[:2];return np.array([c*d[0]+s*d[1],-s*d[0]+c*d[1],wrap(b[2]-a[2])])
for pattern in ['grasp1-stage-a1-*','stage-b-cohort2-*','stage-c-cohort3-*','stage-c-cohort4-*']:
 for run in sorted(Path('outputs/azure3-runs').glob(pattern)):
  result=read(run/'raw/result.json');route='-route-' in run.name;cutoff=read(Path('experiments/2026-10-13-e2e18-grasp1/checkpoints')/(result['source_run']+('-mapping30' if route else '')+'.json.zst'))['cutoff_s']
  for rid in ('r1','r2'):
   oo=read(run/f'raw/robots/{rid}/ownmap.jsonl',True);gg=read(run/f'raw/eval_only/{rid}/trajectory.jsonl',True);cc=read(run/f'raw/robots/{rid}/commands.jsonl',True)
   if len(oo)<2:continue
   ts=np.array([x['t'] for x in gg]);gp=np.array([[*x['robot_xyz_m'][:2],x['robot_yaw_rad']] for x in gg]);gp[:,2]=np.unwrap(gp[:,2])
   def truth(t):return np.array([np.interp(t,ts,gp[:,i]) for i in range(3)])
   tt=np.array([o['t']-cutoff+ts[0] for o in oo]);G=np.array([truth(t) for t in tt]);A=np.array([o['pose_own_m'] for o in oo]);D=np.array([o['pose_continuity']['odom_pose'] for o in oo]);C=np.array([o['stall_odometry'].get('command_delta',[0,0,0]) for o in oo]);F=np.array([o['stall_odometry'].get('applied_delta',o['stall_odometry'].get('fused_delta',[0,0,0])) for o in oo]);M=np.array([o['pose_continuity']['map_to_odom'] for o in oo])
   changes=np.array([between(a,b) for a,b in zip(A[:-1],A[1:])]);actual=np.array([between(a,b) for a,b in zip(G[:-1],G[1:])]);odomdelta=np.array([between(a,b) for a,b in zip(D[:-1],D[1:])]);own_steps=np.linalg.norm(changes[:,:2],axis=1);real_steps=np.linalg.norm(actual[:,:2],axis=1)
   for i in range(1,len(oo)):
    row=oo[i]['stall_odometry'];mode=row.get('fusion','unknown');modes[mode]+=1
    stats['cmd_xy_error_m'].append(np.linalg.norm(C[i,:2]-actual[i-1,:2]));stats['cmd_yaw_error_deg'].append(abs(np.degrees(wrap(C[i,2]-actual[i-1,2]))));stats['fused_xy_error_m'].append(np.linalg.norm(F[i,:2]-actual[i-1,:2]));stats['fused_yaw_error_deg'].append(abs(np.degrees(wrap(F[i,2]-actual[i-1,2]))))
    stats[mode+'_cmd_error_m'].append(np.linalg.norm(C[i,:2]-actual[i-1,:2]));stats[mode+'_fused_error_m'].append(np.linalg.norm(F[i,:2]-actual[i-1,:2]))
    stats['map_frame_jump_m'].append(own_steps[i-1]);stats['odom_frame_jump_m'].append(np.linalg.norm(odomdelta[i-1,:2]));stats['map_correction_translation_m'].append(np.linalg.norm(M[i,:2]-M[i-1,:2]));stats['map_correction_yaw_deg'].append(abs(np.degrees(wrap(M[i,2]-M[i-1,2]))))
    if row.get('status')=='measured':stats['visual_delta_error_m'].append(np.linalg.norm(np.asarray(row['delta'])[:2]-actual[i-1,:2]));stats['visual_delta_yaw_error_deg'].append(abs(np.degrees(wrap(row['delta'][2]-actual[i-1,2]))))
    correction[oo[i]['pose_continuity']['update'].get('reason')]+=1
    if real_steps[i-1]<.001 and abs(actual[i-1,2])<np.radians(.2):
     stats['GT_stationary_map_distance_m'].append(own_steps[i-1]);stats['GT_stationary_odom_distance_m'].append(np.linalg.norm(odomdelta[i-1,:2]));stats['GT_stationary_cmd_distance_m'].append(np.linalg.norm(C[i,:2]));stats['GT_stationary_fused_distance_m'].append(np.linalg.norm(F[i,:2]));stats['GT_stationary_real_distance_m'].append(real_steps[i-1])
    if real_steps[i-1]<.002 and abs(actual[i-1,2])>np.radians(1):stats['GT_rotate_map_distance_m'].append(own_steps[i-1]);stats['GT_rotate_real_distance_m'].append(real_steps[i-1])
   # Sampling-coarsening diagnostic, not a controller and not a claim that all lost length is jitter.
   lengths={}
   for sec in [.4,1.,2.,5.]:
    ids=[0]
    for j in range(1,len(tt)):
     if tt[j]-tt[ids[-1]]>=sec-1e-8:ids.append(j)
    lengths[str(sec)]=dict(own=float(np.linalg.norm(np.diff(A[ids,:2],axis=0),axis=1).sum()),actual=float(np.linalg.norm(np.diff(G[ids,:2],axis=0),axis=1).sum()))
   details.append(dict(run=run.name,robot=rid,route=route,coarsened_path_m=lengths,frame_path_own_m=float(own_steps.sum()),frame_path_actual_m=float(real_steps.sum()),map_vs_fused_increment_residual_m=float(np.linalg.norm(changes[:,:2]-F[1:,:2],axis=1).sum())))
   # Command-level calibration is evaluated only, never fitted back to runtime.
   from harness.self_pulse_odom import profile_key,response
   from harness.self_pulse_rotation import calibrated_model
   profiles=calibrated_model()['profiles'];servo={};drives=[c for c in cc if c['kind']=='mecanum']
   for j,c in enumerate(cc):
    if c['kind']=='initial_servo_command':servo={int(k):int(v) for k,v in c['pulses'].items()}
    elif c['kind']=='arm':servo[int(c['servo_id'])]=int(c['pulse'])
    if c['kind']!='mecanum' or not any(c.get(k,0) for k in ('forward','left','turn')):continue
    k=profile_key(c,servo.get(1,2000)<=1600)
    if k not in profiles:continue
    profile=profiles[k];end=min(c['t']+profile['times'][-1],ts[-1]);later=[d['t'] for d in drives if d['t']>c['t']+1e-8]
    if later:end=min(end,min(later))
    if end<=c['t']:continue
    act=between(truth(c['t']),truth(end));pred=response(profile,end-c['t']);axis=profile['axis'];index={'forward':0,'left':1,'turn':2}[axis]
    rec=dict(run=run.name,robot=rid,profile=k,start=c['t'],duration=end-c['t'],pred=pred.tolist(),actual=act.tolist(),gain_actual_over_pred=float(act[index]/pred[index]) if abs(pred[index])>1e-6 else None)
    cmdrows.append(rec);stats['profile_'+k+'_actual_over_pred'].append(rec['gain_actual_over_pred'] or 0.)
summary=dict(intervals=sum(modes.values()),fusion_modes=dict(modes),map_update_reasons=dict(correction),stats={k:quant(v) for k,v in stats.items()},runs=details)
root=Path('experiments/2026-10-14-e2e18-pose');(root/'decomposition.json').write_text(json.dumps(summary,indent=2)+'\n');(root/'command-evaluation.json').write_text(json.dumps(cmdrows,separators=(',',':'))+'\n')
print('intervals',summary['intervals'],dict(modes));print({k:summary['stats'][k] for k in ['cmd_xy_error_m','fused_xy_error_m','cmd_yaw_error_deg','fused_yaw_error_deg','visual_delta_error_m','visual_delta_yaw_error_deg','GT_stationary_map_distance_m','GT_stationary_real_distance_m']})
for k,v in summary['stats'].items():
 if k.startswith('profile'):print(k,v)
