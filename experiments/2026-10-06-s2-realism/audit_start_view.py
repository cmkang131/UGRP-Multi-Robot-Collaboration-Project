"""Saved RGB and separate GT geometry audit; no simulator or control mutation."""
import sys,json,copy,hashlib,argparse,importlib.util
from pathlib import Path
import numpy as np
import cv2
from harness import vision_loc_protocol as vp
from harness import zone_solo_cyan_contract_v106 as c
from harness.zone_solo_cyan_augmented_start import Runtime
from harness.opencv_wall_observation import DETECTOR,observations
from harness.vision_pose_source_final import measured_column_model
R=Path('/Users/changmin/projects/ugrp/outputs/s2-realism-18e5e42e-s1052-P1-2-place')
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--pr405-copy',type=Path,required=True);args=parser.parse_args()
O=args.output;ROOT=Path(__file__).resolve().parents[2]
if O.exists(): raise ValueError('new output directory required')
O.mkdir(parents=True)
b=json.loads((R/'bundle.json').read_text());opts={k:v for k,v in b['options'].items() if k not in ('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')}
opts.update(motion_model=b['motion_model'],pulse_calibration=b['pulse_calibration'],extrinsic_calibration=b['extrinsic_calibration'],floor_appearance=b['floor_appearance'])
r=Runtime(c.hp.resolve(c.MAP_ID)[0],ROOT/c.CALIBRATION,c.CALIBRATION_SHA,seed=1052,**opts);pf=r.pose.provider.loc._pf;vl=vp.load_vis3()[0]
read=lambda p:[json.loads(l) for l in (R/p).read_text().splitlines()]
frames=read('robots/r3/frames.jsonl');truth={round(x['t'],6):x for x in read('eval_only/trajectory.jsonl')};cams={round(x['t'],6):x for x in read('eval_only/camera-pose.jsonl')}
result=[];samples=[]
for t in (2.25,3.75,5.25,6.75,8.25,11.60):
 f=min(frames,key=lambda x:abs(x['sim_time']-t));pose={int(k):v for k,v in f['commanded_servo'].items()};cm=pf.column_model_for(pose)
 und=vl.mp.undistort(cv2.imread(str(R/f['path'])));box={}
 def traced(frame,event,arg):
  if frame.f_code is vl.mp.detect_boundaries.__code__ and event=='return':box.update(frame.f_locals)
 sys.setprofile(traced)
 try:scan=vl.mp.detect_boundaries(und,cm,DETECTOR)
 finally:sys.setprofile(None)
 p=box['p'];checks=dict(geometry=box['ok'],band_rows=box['band_rows']>=2,below=box['c_below']>=p['min_contrast_below'],uniform=box['std']<=p['max_band_std'],above=np.where(box['top_visible'],box['c_above']>=p['min_contrast_above'],box['band_rows']>=p['min_open_band_px']))
 cumulative=np.ones_like(box['ok']);counts=[]
 for name,value in checks.items():
  cumulative&=value;counts.append(dict(gate=name,candidate_pixels=int(cumulative.sum()),columns=int(cumulative.any(0).sum())))
 leave_one={}
 for name in checks:
  accepted=np.logical_and.reduce([v for k,v in checks.items() if k!=name]);leave_one[name]=int(accepted.any(0).sum())
 gt=truth[round(t,6)];cam=cams[round(t,6)];angle=gt['robot_yaw_rad'];co,si=np.cos(angle),np.sin(angle);rz=np.array([[co,-si,0],[si,co,0],[0,0,1]])
 origin=rz.T@(np.array(cam['camera_cached_xyz_m'])-np.r_[gt['robot_xyz_m'][:2],0.]);rot=rz.T@np.array(cam['camera_cached_optical_rotation'])
 actual=measured_column_model(vl.mp,dict(origin_m=origin,rotation=rot),cm.columns)
 variants={}
 for name,org,rr in [('origin_only',origin,cm._rot),('rotation_only',cm.origin,rot)]:
  model=measured_column_model(vl.mp,dict(origin_m=org,rotation=rr),cm.columns)
  ob=observations(vl,cv2.imread(str(R/f['path'])),model,r.pose.provider.gates['values'])
  variants[name]=int((ob.b_kind==1).sum())
 dp=np.arcsin(rot[2,2])-np.arcsin(cm._rot[2,2]);co,si=np.cos(dp),np.sin(dp)
 pr=cm._rot@np.array([[1,0,0],[0,co,-si],[0,si,co]])
 pm=measured_column_model(vl.mp,dict(origin_m=cm.origin,rotation=pr),cm.columns)
 variants['pitch_only']=int((observations(vl,cv2.imread(str(R/f['path'])),pm,r.pose.provider.gates['values']).b_kind==1).sum())
 eval_box={}
 def eval_traced(frame,event,arg):
  if frame.f_code is vl.mp.detect_boundaries.__code__ and event=='return':eval_box.update(frame.f_locals)
 sys.setprofile(eval_traced)
 try: eval_scan=vl.mp.detect_boundaries(und,actual,DETECTOR)
 finally: sys.setprofile(None)
 eval_obs=observations(vl,cv2.imread(str(R/f['path'])),actual,r.pose.provider.gates['values'])
 expected,_=vl.expected_rows(pf.geometry,np.array([[*gt['robot_xyz_m'][:2],angle]]),actual);bottom=expected[0]
 trow=actual.t_of_row(bottom[None,:]);distance=actual.range_bearing(trow)[0][0]
 idx=np.clip(np.rint(478-bottom).astype(int),0,box['vb'].shape[0]-1);cols=np.arange(len(bottom));valid=np.isfinite(bottom)&(bottom>=4)&(bottom<=470)
 values={name:value[idx,cols] for name,value in checks.items()}
 row=dict(t=t,path=f['path'],pose=pose,actual_pitch_deg=cam['cached_pitch_deg'],fixed_pitch_deg=float(np.degrees(np.arcsin(cm._rot[2,2]))),
  eval_only_ablation_columns=variants,actual_camera_height_m=float(origin[2]),eval_camera_raw_columns=int(np.isfinite(eval_scan.vb).any(1).sum()),eval_camera_final_columns=int((eval_obs.b_kind==1).sum()),eval_camera_median_std_at_true_bottom=float(np.median(eval_box['std'][idx[valid],cols[valid]])),visible_true_bottom=int(valid.sum()),expected_bottom_px=np.quantile(bottom[np.isfinite(bottom)],[0,.5,1]).tolist(),
  true_wall_range_m=np.quantile(distance[np.isfinite(distance)],[0,.5,1]).tolist(),raw_candidate_columns=int(np.isfinite(scan.vb).any(1).sum()),
  final_columns=int((observations(vl,cv2.imread(str(R/f['path'])),cm,r.pose.provider.gates['values']).b_kind==1).sum()),
  stages=counts,leave_one_gate_out_columns=leave_one,gt_bottom_gate_pass={k:int(v[valid].sum()) for k,v in values.items()},
  gt_bottom_std_quantiles=np.quantile(box['std'][idx[valid],cols[valid]],[0,.5,1]).tolist(),
  gt_bottom_below_quantiles=np.quantile(box['c_below'][idx[valid],cols[valid]],[0,.5,1]).tolist(),
  gt_bottom_above_quantiles=np.quantile(box['c_above'][idx[valid],cols[valid]],[0,.5,1]).tolist())
 result.append(row)
 for j in range(len(bottom)):
  samples.append(dict(t=t,u=int(cm.columns[j]),true_bottom=float(bottom[j]),distance=float(distance[j]),
   band_std=float(box['std'][idx[j],j]),contrast_below=float(box['c_below'][idx[j],j]),contrast_above=float(box['c_above'][idx[j],j]),
   inferred_top=float(box['vt'][idx[j],j]),band_top=int(box['band_top'][idx[j],j]),top_visible=bool(box['top_visible'][idx[j],j]),
   passes={k:bool(v[j]) for k,v in values.items()}))
out=dict(scope='GT evaluation only; detector unchanged, no controller inputs',rows=result,samples=samples,parameters=p,
 hashes={str(R/x):hashlib.sha256((R/x).read_bytes()).hexdigest() for x in ['bundle.json','robots/r3/frames.jsonl','eval_only/trajectory.jsonl','eval_only/camera-pose.jsonl']})
(O/'camera-component-ablation.json').write_text(json.dumps(out,indent=2)+'\n')

fkpath=args.pr405_copy/'harness/servo_camera_fk.py'
spec=importlib.util.spec_from_file_location('readonly_fk',fkpath);fk=importlib.util.module_from_spec(spec);spec.loader.exec_module(fk)
rows=[]
for old in json.loads((O/'camera-component-ablation.json').read_text())['rows']:
 pose={int(k):v for k,v in old['pose'].items()};tr,status=fk.transform_from_commands(pose,camera_pose='servo_fk_v1')
 org,rot=tr;cm=measured_column_model(vl.mp,dict(origin_m=org,rotation=rot),pf.columns)
 g=truth[round(old['t'],6)];bottom,_=vl.expected_rows(pf.geometry,np.array([[*g['robot_xyz_m'][:2],g['robot_yaw_rad']]]),cm)
 rows.append(dict(t=old['t'],pose=pose,nominal_fk_pitch_deg=float(np.degrees(np.arcsin(rot[2,2]))),nominal_height_m=float(org[2]),nominal_visible_columns=int(np.count_nonzero((bottom>=4)&(bottom<=470))),nominal_rows_px=np.quantile(bottom,[0,.5,1]).tolist(),measured_off_pitch_deg=old['actual_pitch_deg'],fixed_table_pitch_deg=old['fixed_pitch_deg'],scope='fixed CAD nominal geometry, not stiffness-on observation'))
search=[];inputs={}
for mode in ('static-off','static-on'):
 p=Path('/Users/changmin/projects/ugrp/outputs/servo-stiffness-v1')/mode/'eval_only/camera.jsonl'
 data=[json.loads(l) for l in p.read_text().splitlines()];data=[q for q in data if 5.3<=q['t']<7.3]
 inp=[];bottoms=[];pitches=[]
 g=truth[11.6]
 for q in data:
  br=np.array(q['body_rotation']).reshape(3,3);yaw=np.arctan2(br[1,0],br[0,0]);co,si=np.cos(yaw),np.sin(yaw);rz=np.array([[co,-si,0],[si,co,0],[0,0,1]])
  rot=rz.T@np.array(q['camera_rotation']).reshape(3,3)@np.diag([1,-1,-1]);org=rz.T@(np.array(q['camera_xyz'])-np.r_[q['body_xyz'][:2],0.])
  cm=measured_column_model(vl.mp,dict(origin_m=org,rotation=rot),pf.columns)
  bottom,_=vl.expected_rows(pf.geometry,np.array([[*g['robot_xyz_m'][:2],g['robot_yaw_rad']]]),cm);bottoms.append(bottom)
  pitches.append(float(np.degrees(np.arcsin(rot[2,2]))))
  inp.append(dict(t=q['t'],origin_m=org.tolist(),rotation=rot.tolist()))
 search.append(dict(source=mode,n=len(data),pitch_median_deg=float(np.median(pitches)),rows_px=np.quantile(bottoms,[0,.5,1]).tolist(),visible_fraction=float(np.mean((np.array(bottoms)>=4)&(np.array(bottoms)<=470))),scope='measured PR405 SEARCH transforms projected at s1052 chassis pose; no new RGB'))
 inputs[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
r.close()
result=dict(rows=rows,search_counterfactual=search,inputs=inputs,gt_scope='evaluation only; no PF updates or controller decisions',look_p20_stiffness_on_measured=False,physics_runs=0)
(O/'stiffness-visibility.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(audit=str(O),views=6,gt_use='evaluation only',physics_runs=0)))
