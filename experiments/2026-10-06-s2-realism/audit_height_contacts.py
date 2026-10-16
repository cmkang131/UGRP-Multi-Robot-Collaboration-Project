"""Evaluate the frozen height candidate at the 27 original s1051 update frames."""
import json,hashlib,sys
from pathlib import Path
from types import SimpleNamespace as NS
import cv2,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_s1050_projection as a
from harness.zone_solo_cyan_visibility import Visibility
from harness.zone_solo_cyan_observed_amcl import install as observed
from harness.zone_solo_cyan_floor_contact import install as appearance
from harness.zone_solo_cyan_load_height import install_height,wall_height_support
from harness.zone_solo_cyan_likelihood_field import endpoints

def main(out):
 criteria=json.loads(Path(__file__).with_name('load-height-criteria.json').read_text());raw=Path(criteria['evaluation']['raw']);read=lambda f:json.loads((raw/f).read_text());lines=lambda f:[json.loads(l) for l in (raw/f).read_text().splitlines()]
 b=read('bundle.json');rec=read('student_record.json');lo,hi=criteria['evaluation']['carry_window_sim_s']
 frames={round(f['sim_time'],6):f for f in lines('robots/r3/frames.jsonl')}
 truth={round(g['t'],6):g for g in lines('eval_only/trajectory.jsonl')};cameras={round(g['t'],6):g for g in lines('eval_only/camera-pose.jsonl')}
 vl=a.vp.load_vis3()[0];cols=vl.column_positions(96,2);static=a.c.hp.resolve(a.c.MAP_ID)[0];seg=a.geo.wall_segments(static);models=a.approximate(b['extrinsic_calibration'])
 baseline=Visibility();observed(baseline);appearance(baseline,b['floor_appearance'])
 candidate=Visibility();observed(candidate);audit=install_height(candidate)
 rows=[];images=[];allpoints=[]
 for q in rec['amcl_update']['rows']:
  if not (lo<=q['t']<hi and q['visual_weight_update']):continue
  t=q['t'];f=frames[round(t,6)];servo={int(k):v for k,v in f['commanded_servo'].items()};key=','.join(str(servo[k]) for k in (3,4,5,6))
  cm=a.measured_column_model(vl.mp,a.floor_camera(models['loaded'][key]),cols);bgr=cv2.imread(str(raw/f['path']));rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
  ob=a.observations(vl,bgr,cm,a.own_image_gates()['values']);pf=NS(column_model_for=lambda pose:cm)
  baseline.on_rgb(rgb);candidate.on_rgb(rgb);base=baseline.apply(pf,ob,servo,t);new=candidate.apply(pf,ob,servo,t)
  assert int((base.b_kind==1).sum())==q['columns']
  bm=base.b_kind==1;nm=(new.b_kind==1) if new is not None else np.zeros(len(cols),bool)
  # Prediction is complete before evaluation GT is read below.
  g=truth[round(t,6)];cam=cameras[round(t,6)];rot=a.geo.rz(g['robot_yaw_rad']);origin=np.r_[g['robot_xyz_m'][:2],0.]
  actual=NS(origin=rot.T@(np.array(cam['camera_cached_xyz_m'])-origin),_rot=rot.T@np.array(cam['camera_cached_optical_rotation']),columns=cols)
  pose=np.r_[g['robot_xyz_m'][:2],g['robot_yaw_rad']];true,_,_=a.geo.bottom_projection(actual,pose,seg)
  floor=[]
  for offset in (-4,4):
   rays=a.geo.pixel_rays(actual,cols,ob.b_lo+offset);z=-actual.origin[2]/rays[:,2];wall=a.geo.wall_depths(actual,pose,rays,static);floor.append((z>0)&(wall>=z-1e-6))
  ff=floor[0]&floor[1]&(abs(ob.b_lo-true)>10);ww=~ff&(abs(ob.b_lo-true)<=4)
  classify=lambda m:dict(total=int(m.sum()),floor=int((m&ff).sum()),wall=int((m&ww).sum()),ambiguous=int((m&~ff&~ww).sum()))
  rows.append(dict(t=t,baseline=classify(bm),height=classify(nm),retained_baseline=classify(bm&nm),height_audit=audit['rows'][-1]))
  und=vl.mp.undistort(bgr);_,tops,_=wall_height_support(cm,ob,np.zeros((480,640),np.uint8))
  for j in np.flatnonzero(bm|nm):
   uv=(int(cols[j]),int(round(ob.b_lo[j])));color=(0,0,255) if ff[j] else ((0,255,0) if ww[j] else (0,255,255))
   cv2.circle(und,uv,4,color,1 if not nm[j] else -1)
   if np.isfinite(tops[j]).all() and np.all(tops[j]>0) and tops[j,0]<640 and tops[j,1]<480:cv2.drawMarker(und,tuple(np.rint(tops[j]).astype(int)),color,cv2.MARKER_CROSS,8,1)
   allpoints.append(dict(t=t,u=int(cols[j]),v=float(ob.b_lo[j]),baseline=bool(bm[j]),height=bool(nm[j]),label='floor' if ff[j] else ('wall' if ww[j] else 'ambiguous'),top=tops[j].tolist()))
  cv2.putText(und,f'{t:.2f}s old{bm.sum()} height{nm.sum()}',(8,470),0,.65,(255,255,255),2);images.append(cv2.resize(und,(320,240)))
 for i in range(0,len(images),12):
  batch=images[i:i+12]+[np.zeros_like(images[0])]*(12-len(images[i:i+12]));cv2.imwrite(str(out/f'height-sheet-{i//12}.jpg'),np.vstack([np.hstack(batch[j:j+4]) for j in range(0,12,4)]))
 sums={k:{label:sum(r[k][label] for r in rows) for label in ['total','floor','wall','ambiguous']} for k in ['baseline','height','retained_baseline']}
 sums['baseline_floor_fraction']=sums['baseline']['floor']/sums['baseline']['total'];sums['height_floor_fraction']=sums['height']['floor']/sums['height']['total'] if sums['height']['total'] else None
 sums['true_wall_retention']=sums['retained_baseline']['wall']/sums['baseline']['wall']
 report=dict(schema='ugrp.s2.wall_height.audit.v1',physics_runs=0,model_calls=0,gt_usage='scoring only, not passed to filter',rows=rows,summary=sums,
  interpretation='Original 27 update opportunities; replays have different update schedules. B replaces the floor histogram, no filter stack. Border/semantic labels inherit prior audited geometric evaluation, no new dense semantic GT.')
 for name,data in [('height-contact-summary.json',report),('height-points.json',allpoints)]:
  with (out/name).open('x') as f:f.write(json.dumps(data,indent=2)+'\n')
 print(json.dumps(sums,indent=2))
if __name__=='__main__':main(Path(sys.argv[1]))
