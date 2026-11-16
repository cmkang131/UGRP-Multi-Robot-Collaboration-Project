"""Evaluation-only classification of the 18 already completed s1050 updates."""
import sys,json,hashlib,cv2,numpy as np
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,'experiments/2026-10-06-s2-realism')
import audit_s1050_projection as a
folder=Path('/Users/changmin/projects/ugrp/outputs/s2-contact-audit-20261007')
replay=json.loads((folder/'replay-off-final.json').read_text());effects=json.loads((folder/'update-effects.json').read_text())
frames={round(f['sim_time'],6):f for f in (json.loads(s) for s in (a.RAW/'robots/r3/frames.jsonl').read_text().splitlines())}
gt={round(f['t'],6):f for f in (json.loads(s) for s in (a.RAW/'eval_only/trajectory.jsonl').read_text().splitlines())}
ca={round(f['t'],6):f for f in (json.loads(s) for s in (a.RAW/'eval_only/camera-pose.jsonl').read_text().splitlines())}
models=a.approximate(json.loads((a.c.ROOT/'configs/calibration/s2_camera_v3_unloaded_sag_v1.json').read_text()))
vl=a.vp.load_vis3()[0];cols=np.linspace(8,631,96).astype(int);static=a.c.hp.resolve(a.c.MAP_ID)[0];segments=a.geo.wall_segments(static)
reports=[]
for eff in effects['rows']:
 t=eff['t'];f=frames[round(t,6)];g=gt[round(t,6)];c=ca[round(t,6)];m=next(m for m in replay['measurements'] if m['t']==t)
 key=','.join(str(f['commanded_servo'][str(k)]) for k in (3,4,5,6));cm=a.measured_column_model(vl.mp,a.floor_camera(models['loaded'][key]),cols)
 points=np.c_[m['points_local_m'],np.zeros(len(m['points_local_m']))];opt=(points-cm.origin)@cm._rot
 uv=opt@a.geo.K.T;uv=uv[:,:2]/uv[:,2,None]
 rot=a.geo.rz(g['robot_yaw_rad']);base=np.r_[g['robot_xyz_m'][:2],0.]
 actual=NS(origin=rot.T@(np.array(c['camera_cached_xyz_m'])-base),_rot=rot.T@np.array(c['camera_cached_optical_rotation']),columns=uv[:,0])
 pose=np.r_[g['robot_xyz_m'][:2],g['robot_yaw_rad']];true,_,_=a.geo.bottom_projection(actual,pose,segments)
 floor=[]
 for offset in (-4,4):
  rays=a.geo.pixel_rays(actual,uv[:,0],uv[:,1]+offset);z=-actual.origin[2]/rays[:,2];w=a.geo.wall_depths(actual,pose,rays,static)
  floor.append((z>0)&(w>=z-1e-6))
 # Large-offset floor is the checker/paint region already manually reviewed.
 # Near true wall rows stay ambiguous; avoid semantic overclaim for edge strips.
 ff=floor[0]&floor[1]&(abs(uv[:,1]-true)>10)
 wall=~ff&(abs(uv[:,1]-true)<=4)
 reports.append(dict(t=t,points=len(uv),floor_color=int(ff.sum()),wall_bottom=int(wall.sum()),edge_ambiguous=int((~ff&~wall).sum()),
                     weighted_error_reduction_m=eff['weighted_mean_error_reduction_m'],resampled_error_reduction_m=eff['resampled_mean_error_reduction_m']))
out=dict(schema='ugrp.s2.update_contact_classes.v1',physics_runs=0,gt_usage='completed replay scoring only',rows=reports)
p=folder/'update-contact-classes.json';assert not p.exists();p.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(reports))
