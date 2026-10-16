import sys,json,math,pathlib
import cv2,numpy as np
sys.path.insert(0,'/Users/changmin/projects/ugrp-wt/drive-friction')
from harness import zone_solo_cyan_contract_v106 as c, zone_solo_cyan_camera_v3 as v3, vision_loc_protocol as vp
from harness.vision_pose_source_final import measured_column_model
from harness.opencv_wall_observation import observations
src=v3.build_provider(c.hp.resolve(c.MAP_ID)[0],c.ROOT/c.CALIBRATION,c.CALIBRATION_SHA,1046);inner=src.provider;pf=inner.loc._pf;vl=vp.load_vis3()[0]
allrows=[]
for seed,sha in [(1045,'f0bb26e7'),(1046,'e619ee57')]:
 run=pathlib.Path(f'/Users/changmin/projects/ugrp/outputs/s2-realism-{sha}-s{seed}-P1-2-place')
 def lines(f):return [json.loads(l) for l in (run/f).read_text().splitlines()]
 frames=lines('robots/r3/frames.jsonl');tr=lines('eval_only/trajectory.jsonl');cams=lines('eval_only/camera-pose.jsonl')
 st=json.loads((run/'student_record.json').read_text())
 for t in [30,68,90,100,120,160,180,200,215,224,250,290,296]:
  f=min(frames,key=lambda x:abs(x['sim_time']-t));t=f['sim_time'];g=min(tr,key=lambda x:abs(x['t']-t));ca=min(cams,key=lambda x:abs(x['t']-t));p=min(st['poses'],key=lambda x:abs(x['t']-t));servo={int(k):v for k,v in f['commanded_servo'].items()}
  if tuple(servo[k] for k in (3,4,5))!=(896,2035,1894):continue
  pf.load.loaded=True;inner.servo=servo
  nom=pf.column_model_for(servo);y=g['robot_yaw_rad'];co,si=math.cos(y),math.sin(y);rz=np.array([[co,si,0],[-si,co,0],[0,0,1]])
  rec=dict(origin_m=rz@(np.array(ca['camera_cached_xyz_m'])-np.r_[g['robot_xyz_m'][:2],0]),rotation=rz@np.array(ca['camera_cached_optical_rotation']))
  act=measured_column_model(vl.mp,rec,pf.columns);im=cv2.imread(str(run/f['path']));obs=observations(vl,im,nom,inner.gates['values']);oact=observations(vl,im,act,inner.gates['values'])
  row=dict(seed=seed,t=t,frame=f['path'],nom_pitch_deg=float(np.degrees(np.arcsin(nom._rot[2,2]))),actual_pitch_deg=ca['cached_pitch_deg'],nom_origin=nom.origin.tolist(),actual_origin=rec['origin_m'].tolist(),columns=int(obs.informative.sum()),actual_geometry_columns=int(oact.informative.sum()),gate=p['last_scan_gate'])
  xy=np.r_[g['robot_xyz_m'][:2],y][None,:]
  for key,cm,ob in [('nominal',nom,obs),('actual_eval',act,obs),('actual_detector_eval',act,oact)]:
   exp=vl.expected_rows(pf.geometry,xy,cm)[0][0];valid=ob.b_kind==vl.EDGE;diff=exp[valid]-ob.b_lo[valid]
   prob=vl.interval_prob(exp[None,:],ob.b_kind,ob.b_lo,ob.b_hi,pf.measurement['sigma_px'])[0,valid]
   row[key]=dict(residual_median_px=float(np.median(diff)) if len(diff) else None,residual_abs_median_px=float(np.median(abs(diff))) if len(diff) else None,inlier_fraction=float(np.mean(prob>pf.measurement['outlier_prob']/(1-pf.measurement['outlier_prob']))) if len(diff) else None,observed_median_row=float(np.median(ob.b_lo[valid])) if valid.any() else None,expected_median_row=float(np.median(exp[valid])) if valid.any() else None)
  allrows.append(row);print(seed,t,row['columns'],row['nom_pitch_deg'],row['actual_pitch_deg'],row['nominal'],row['actual_eval'],flush=True)
pathlib.Path('/Users/changmin/projects/ugrp/outputs/s2-visual-fix-20261007/geometry-audit.json').write_text(json.dumps(allrows,indent=2)+'\n');src.close()
