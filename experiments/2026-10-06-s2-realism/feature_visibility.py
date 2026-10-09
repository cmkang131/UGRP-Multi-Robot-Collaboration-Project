"""Posthoc feature availability; GT used only for geometric evaluation."""
import sys,json,math
from pathlib import Path
import numpy as np
sys.path.insert(0,'experiments/2026-10-06-s2-realism')
from analyze_visibility import old,lines,rz,NS,K,pixel_rays,bottom_projection,wall_segments,wall_depths
out=old.RAW/'s2-visibility-20261007';geo=json.loads((out/'geometry.json').read_text());static=old.contract.hp.resolve(old.contract.MAP_ID)[0]
seg=wall_segments(static);top=seg.copy();top[:,:,2]=static['wall_profile']['height_m']
door=static['passages'][0];x,y=door['center_m'];dx,dy=door['half_extents_m'];points=np.array([[xx,yy,z] for xx in (x-dx,x+dx) for yy in (y-dy,y+dy) for z in np.linspace(0,.4,101)])
results=[]
for seed,sha in old.RUNS.items():
 raw=old.RAW/f's2-realism-{sha}-s{seed}-P1-2-place';c={round(q['t'],6):q for q in lines(raw/'eval_only/camera-pose.jsonl')};g={round(q['t'],6):q for q in lines(raw/'eval_only/trajectory.jsonl')}
 selected=[q for q in geo['rows'] if q['seed']==seed];rows=[]
 for row in selected:
  ca=c[round(row['t'],6)];gt=g[round(row['t'],6)];r=rz(gt['robot_yaw_rad']);base=np.r_[gt['robot_xyz_m'][:2],0.];cm=NS(origin=r.T@(np.array(ca['camera_cached_xyz_m'])-base),_rot=r.T@np.array(ca['camera_cached_optical_rotation']),columns=np.linspace(8,631,96).astype(int));pose=np.r_[gt['robot_xyz_m'][:2],gt['robot_yaw_rad']]
  tr,_,_=bottom_projection(cm,pose,top);p=(points-base)@r;opt=(p-cm.origin)@cm._rot
  uv=(opt@K.T)[:,:2]/opt[:,2,None];ok=(opt[:,2]>0)&(uv[:,0]>=4)&(uv[:,0]<=635)&(uv[:,1]>=4)&(uv[:,1]<=470)
  rays=(p-cm.origin)/opt[:,2,None];d=wall_depths(cm,pose,rays,static);ok &= d>=opt[:,2]-1e-6
  rays=pixel_rays(cm,np.array([K[0,2],K[0,2]]),np.array([4.,470.]));floor=cm.origin+(-cm.origin[2]/rays[:,2,None])*rays
  rows.append(dict(t=row['t'],top_visible_columns=int(((tr>=4)&(tr<=470)).sum()),door_any=bool(ok.sum()>=2),floor_x_range=floor[:,0].tolist()))
 results.append(dict(seed=seed,sampled_frames=len(rows),top_visible_columns=sum(q['top_visible_columns'] for q in rows),top_total_columns=96*len(rows),door_jamb_potential_visible_frames=sum(q['door_any'] for q in rows),median_floor_x_range=np.median([q['floor_x_range'] for q in rows],axis=0).tolist()))
result=dict(scope='GT-only geometric feature availability, not image detection or localization; door lines sampled at 4mm intervals',physics_runs=0,rows=results)
dest=out/'feature-geometry.json'
if dest.exists():raise FileExistsError(dest)
dest.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
