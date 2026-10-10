import json,pathlib,math,hashlib
from scripts.run_s2_heading import runtime_factory
from harness import zone_solo_cyan_contract_v106 as legacy
from harness.zone_color_boxes import _frame,_mask,OWN_ZONE_CYAN_HSV
import cv2,numpy as np
root=pathlib.Path('/Users/changmin/projects/ugrp/outputs')
allrows={}
for name, times in [('s2-realism-99d81d8c-s1068-v141-graduation',[63.25,85.,86.75,91.35,96.5]),('s2-heading-b60acdca-s1068-v143',[147.1,186.7,187.1,187.5,187.9,188.3,189.,191.5,269.8,898.])]:
 p=root/name; b=json.loads((p/'bundle.json').read_text()); d=json.loads((p/'student_record.json').read_text())
 rt=runtime_factory(b,{},[])(legacy.hp.resolve(legacy.MAP_ID)[0],legacy.ROOT/legacy.CALIBRATION,legacy.CALIBRATION_SHA,**b['task'])
 try:
  frames=[json.loads(x) for x in (p/'robots/r3/frames.jsonl').read_text().splitlines()]; rows=[]
  for t in times:
   f=min(frames,key=lambda f:abs(f['sim_time']-t)); pose=min(d['poses'],key=lambda r:abs(r['t']-f['sim_time']))
   servo={int(k):v for k,v in f['commanded_servo'].items()}; raw=(p/f['path']).read_bytes();obs=dict(image=raw)
   fits=rt.vision.detect(obs,servo); mask=_mask(cv2.cvtColor(_frame(raw),cv2.COLOR_BGR2HSV),OWN_ZONE_CYAN_HSV); y,x=np.nonzero(mask)
   c,s=math.cos(pose['yaw']),math.sin(pose['yaw']); det=[]
   for q in fits:
    bx,by=q['estimated_box_center_base_m'][:2];mx,my=pose['x']+c*bx-s*by,pose['y']+s*bx+c*by
    valid=rt.slot['x_range_m'][0]-.15<=mx<=rt.slot['x_range_m'][1]+.15 and rt.slot['y_range_m'][0]-.15<=my<=rt.slot['y_range_m'][1]+.15
    det.append(dict(body_xy=[bx,by],map_xy=[mx,my],slot_accept=bool(valid)))
   row=dict(t=f['sim_time'],frame_id=f['frame_id'],path=f['path'],frame_sha256=hashlib.sha256(raw).hexdigest(),mask_pixels=len(x),mask_bounds=None if len(x)==0 else [int(x.min()),int(y.min()),int(x.max()),int(y.max())],detections=det,own_pose={k:pose[k] for k in ['t','t_est','x','y','yaw','std_xy_m']},slot=rt.slot)
   rows.append(row);print(name,row,flush=True)
  allrows[name]=rows
 finally:rt.close()
pathlib.Path('experiments/2026-10-09-s2-heading/default-on/s1068-detections.json').write_text(json.dumps(allrows,indent=2)+'\n')
