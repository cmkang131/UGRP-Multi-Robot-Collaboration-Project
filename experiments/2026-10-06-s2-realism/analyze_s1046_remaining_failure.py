import json,pathlib,math,bisect,numpy as np
R=pathlib.Path('/Users/changmin/projects/ugrp/outputs/s2-realism-e619ee57-s1046-P1-2-place');D=pathlib.Path('/Users/changmin/projects/ugrp/outputs/s2-realism-e619ee57-analysis')
r=lambda p:json.loads(p.read_text());s=r(R/'student_record.json');tr=[json.loads(x) for x in (R/'eval_only/trajectory.jsonl').read_text().splitlines()];ts=np.array([a['t'] for a in tr]);v=np.array([[*a['robot_xyz_m'][:2],a['robot_yaw_rad']] for a in tr]);v[:,2]=np.unwrap(v[:,2])
def gt(t):return np.array([np.interp(t,ts,v[:,j]) for j in range(3)])
def wrap(x):return (x+math.pi)%(2*math.pi)-math.pi
series=[]
for p in s['poses']:
 g=gt(p['t_est']);series.append(dict(t=p['t'],estimate_t=p['t_est'],xy=[p['x'],p['y']],actual=g.tolist(),error_m=math.dist([p['x'],p['y']],g[:2]),yaw_error_deg=math.degrees(wrap(p['yaw']-g[2])),est_yaw_deg=math.degrees(p['yaw']),last_fix_t=p['last_fix_t'],std_xy_m=p['std_xy_m']))
carry=[p for p in series if p['t']>=67.5]
first={}
for threshold in [.1,.2,.5,1.,2.,3.]:first['position_'+str(threshold)]=next((p for p in carry if p['error_m']>=threshold),None)
for threshold in [5,10,20,45,80]:first['yaw_'+str(threshold)]=next((p for p in carry if abs(p['yaw_error_deg'])>=threshold),None)
checkpoints=[]
for e in s['events']:
 if e['event']=='carry_checkpoint':checkpoints.append(dict(event=e,comparison=min(series,key=lambda p:abs(p['t']-e['t']))))
pulses=r(D/'s1046-pulse-eval.json');bad=[p for p in pulses if abs(p['residual'][2])>math.radians(5) or (abs(p['predicted'][1])>.15 and abs(p['actual'][1])<.05)]
for p in bad:p['start_eval']=gt(p['t']).tolist();p['end_eval']=gt(p['t']+r(R/'bundle.json')['pulse_calibration']['profiles'][p['key']]['times'][-1]).tolist()
# Fresh-run fit quality is separated at a static evaluation condition: chassis
# x<1.8m is west of the doorway and wall; never used by the running controller.
groups={}
for label,ps in [('west_of_door',[p for p in pulses if gt(p['t'])[0]<1.8]),('door_or_later',[p for p in pulses if gt(p['t'])[0]>=1.8])]:
 groups[label]={}
 for key in sorted({p['key'] for p in ps}):
  q=[p for p in ps if p['key']==key];a=np.array([p['actual'] for p in q]);e=np.array([p['residual'] for p in q]);groups[label][key]=dict(n=len(q),actual_median=np.median(a,axis=0).tolist(),mean_error=e.mean(0).tolist(),rmse=np.sqrt((e**2).mean(0)).tolist())
out=dict(scope='completed new seed eval only, no refit or rerun',first_divergence=first,checkpoints=checkpoints,large_residual_pulses=bad,regions=groups,summary='Finite-pulse quantization improved, but command-only prediction cannot infer blocked chassis/contact or correct wrong wall-image localization. Wall obstruction is a geometric inference; wall contact impulses were not logged.',final=series[-1],final_cyan=tr[-1]['cyan_xyz_m'])
(D/'s1046-failure-analysis.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
