import sys,json,pathlib,bisect,math,hashlib
import numpy as np
from types import SimpleNamespace as NS
ROOT=pathlib.Path('/Users/changmin/projects/ugrp-wt/drive-friction');sys.path.insert(0,str(ROOT))
from harness import zone_s2_realism_contract_v121 as c
from harness.zone_solo_cyan_inhand import Runtime
from scripts.fit_s2_pulse_calibration import interpolate,training
BASE=pathlib.Path('/Users/changmin/projects/ugrp/outputs/s2-pulse-cal-20261007');raw=pathlib.Path('/Users/changmin/projects/ugrp/outputs/s2-realism-f0bb26e7-s1045-P1-2-place')
read=lambda p:json.loads(p.read_text());rows=[json.loads(s) for s in (BASE/'offline/pulses.jsonl').read_text().splitlines()]
model=read(ROOT/'configs/s2_motion_v7_pulse_cal_v1.json');b=c.bundle('a'*40,seed=1045,**c.NEW_OPTIONS)
r=Runtime(c.old.hp.resolve(c.old.MAP_ID)[0],c.ROOT/c.old.CALIBRATION,c.old.CALIBRATION_SHA,**{k:v for k,v in b['options'].items() if k not in ('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')},motion_model=b['motion_model'])
pf=r.pose.provider.loc._pf
actual_params={k:{f:pf.params[k].get(f) for f in ['gain','tau_axis_s','tau_s','tau_stop_s']} for k in ['motion','motion_loaded']}
pf.n=1;pf.rng=NS(normal=lambda size:np.zeros(size));pf.drift=pf.yaw_bias=pf.yaw_extra=None
comparisons={}
for key,p in model['profiles'].items():
 if not p['n']:continue
 pf.t=0.;pf.vel=np.zeros(3);pf.initialized=True;pf.px=np.zeros((1,3));pf.scale=np.ones((1,3));pf.logw=np.zeros(1);pf.load.loaded=p['loaded']
 a=dict(t=0.,kind='mecanum',forward=0.,left=0.,turn=0.,duration_s=p['duration_s']);a[p['axis']]=p['u'];pf.command(a)
 pf.predict_to(p['duration_s']);pf.command(dict(t=p['duration_s'],kind='hold'));pf.predict_to(p['times'][-1]);old=pf.px[0].copy()
 test=[row for row in rows if row['key']==key and not training(row)]
 values=np.array([interpolate(row,[p['times'][-1]])[0] for row in test]);new=np.array(p['mean_delta'])
 comparisons[key]=dict(n_train=p['n'],n_holdout=len(test),old_pf_prediction=old.tolist(),fitted_prediction=new.tolist(),
  old_rmse=np.sqrt(((values-old)**2).mean(0)).tolist() if test else None,new_rmse=np.sqrt(((values-new)**2).mean(0)).tolist() if test else None)
r.close()
s=read(raw/'student_record.json');poses=s['poses'];pt=[p['t'] for p in poses];events=[e for e in s['events'] if e['event']=='path'];ei=0;path=[];track=[]
def near(t):
 i=bisect.bisect_left(pt,t);return min(poses[max(0,i-1):i+1],key=lambda p:abs(p['t']-t))
for row in s['real_output']['transformations']:
 t=row['t'];r=near(t)
 while ei<len(events) and events[ei]['t']<=t+1e-8:
  path=events[ei]['plan']['waypoints_m'][1:] or [events[ei]['plan']['goal_m']];ei+=1
 while len(path)>1 and math.dist((r['x'],r['y']),path[0])<.035:path.pop(0)
 if t<87.95 or not path:continue
 co,si=math.cos(r['yaw']),math.sin(r['yaw']);error=np.array([[co,si],[-si,co]])@(np.array(path[0])-np.array([r['x'],r['y']]))
 actual=next((x for x in rows if x['seed']==1045 and x['t']==t),None)
 track.append(dict(t=t,left=row['issued']['left'],waypoint=path[0],body_error=error.tolist(),fix=r['last_fix_t'],actual=actual['delta'] if actual else None))
lat=[p for p in track if p['left']];reverse=[(a,b) for a,b in zip(lat,lat[1:]) if a['left']*b['left']<0]
same=[(a,b) for a,b in reverse if a['waypoint']==b['waypoint'] and a['fix']==b['fix']]
cross=[(a,b) for a,b in same if a['body_error'][1]*b['body_error'][1]<0]
overshoot=[(a,b) for a,b in cross if abs(a['body_error'][1])<abs(a['actual'][1])]
res=dict(scope='offline saved evidence and isolated actual predictor code path; no simulator, no online GT',actual_v121_params=actual_params,
 old_gain_1_56_is_active=False,previous_model=b['motion_model']['id'],comparisons=comparisons,
 oscillation=dict(lateral=len(lat),reversals=len(reverse),same_waypoint_and_no_new_fix=len(same),signed_waypoint_error_crossings=len(cross),actual_pulse_larger_than_initial_error=len(overshoot),
  examples=[dict(before=a,after=b) for a,b in overshoot[:5]],
  caveat='same waypoint/no new visual fix supports quantization oscillation, not isolated physics causality; delayed PF and true movement can differ'),
 source_model_sha256=hashlib.sha256((ROOT/'configs/s2_motion_v7_pulse_cal_v1.json').read_bytes()).hexdigest())
(BASE/'offline/model-audit.json').write_text(json.dumps(res,indent=2)+'\n')
print(json.dumps(dict(comparisons=comparisons,oscillation={k:v for k,v in res['oscillation'].items() if k!='examples'}),indent=2))
