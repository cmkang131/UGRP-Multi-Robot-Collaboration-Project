"""Saved s1042 RGB/commands/eval geometry only; never construct a simulator."""
import argparse
import base64
import copy
import json
import runpy
from pathlib import Path
import cv2
import numpy as np
from harness.zone_solo_cyan_scene_change import cyan, lens_valid
from harness.zone_solo_cyan_vision_v106 import CyanVision
from harness.zone_solo_cyan_camera_v3 import camera_calibration
from harness.zone_solo_cyan_contract_v106 import CALIBRATION
from harness.zone_pair_highpose_contract import camera_record


def region(bbox):
    x,y,w,h=map(int,bbox)
    x0,y0,x1,y1=x-w//2,y-h//2,x+w+w//2,y+h+h//2
    canvas=np.zeros((480,640),bool)
    canvas[max(0,y0):min(480,y1),max(0,x0):min(640,x1)]=True
    total=(x1-x0)*(y1-y0)
    return dict(requested_xyxy=[x0,y0,x1,y1],requested_pixels=total,
        outside_canvas_pixels=total-int(canvas.sum()),
        invalid_lens_pixels_on_canvas=int((canvas&~lens_valid()).sum()),
        valid_pixels=int((canvas&lens_valid()).sum())),canvas


def audit(raw):
    geom=runpy.run_path(str(Path(__file__).with_name('analyze_hover_projection.py')))
    rows,read,sha=geom['rows'],geom['read'],geom['sha']
    frames=rows(raw/'robots/r3/frames.jsonl');trace=rows(raw/'eval_only/trajectory.jsonl')
    record=read(raw/'student_record.json');cal=read(Path(CALIBRATION));v3=camera_calibration(cal)
    nearest=lambda rs,k,t:min(rs,key=lambda r:abs(r[k]-t))
    before_t=next(e['t'] for e in record['events'] if e['event']=='cyan_scene_reference_unavailable')
    original=nearest(trace,'t',before_t)
    result=[]
    for label,t,state in [('before',before_t,'unloaded'),('after_lift',120.15,'loaded')]:
        f=nearest(frames,'sim_time',t);path=raw/f['path'];assert sha(path)==f['sha256']
        servo={int(k):v for k,v in f['commanded_servo'].items()}
        image=cv2.imread(str(path));mask=cyan(image);ys,xs=np.nonzero(mask)
        tr=copy.deepcopy(nearest(trace,'t',t))
        # Projection of the original floor site, not the lifted object's current pose.
        tr['cyan_xyz_m']=original['cyan_xyz_m'];tr['cyan_rotation']=original['cyan_rotation']
        variants={}
        for name,table in [('previous',cal),('v3',v3)]:
            cam=camera_record(table,state,servo);p=geom['project'](tr,cam)
            p['optical_pitch_deg']=float(np.degrees(np.arctan2(p['optical_forward_floor_heading'][2],np.linalg.norm(p['optical_forward_floor_heading'][:2]))))
            p['camera_to_original_center_m']=float(np.linalg.norm(np.array(p['block_center_floor_heading_m'])-p['camera_origin_floor_heading_m']))
            if p['valid_bbox_xyxy']:
                x0,y0,x1,y1=p['valid_bbox_xyxy'];p['hypothetical_expanded_roi']=region([x0,y0,x1-x0+1,y1-y0+1])[0]
            variants[name]=p
        row=dict(label=label,t=f['sim_time'],image=str(path),sha256=f['sha256'],servo=servo,
            cyan_area_px=len(xs),cyan_bbox_xyxy=[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if len(xs) else None,
            cyan_outside_lens_pixels=int((mask&~lens_valid()).sum()),projection_original_floor_site=variants)
        if label=='before':
            obs={**f,'image':base64.b64encode(path.read_bytes()).decode()}
            fits=CyanVision(v3).detect(obs,servo);assert len(fits)==1
            roi,canvas=region(fits[0]['pixel_bbox']);row['fit']=fits[0];row['requested_roi']=roi
            gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
            excluded=cv2.dilate((canvas|mask).astype(np.uint8),np.ones((25,25),np.uint8))>0
            background=~excluded&lens_valid()&(gray>30)
            background[:12]=background[-12:]=False;background[:,:12]=background[:,-12:]=False
            row['unchanged_ecc_background_std']=float(np.std(gray[background]))
            row['background_pixels']=int(background.sum())
            row['target_distance_to_lens_edge_px_min']=float(cv2.distanceTransform(lens_valid().astype(np.uint8),cv2.DIST_L2,5)[mask].min())
        result.append(row)
    return dict(schema='ugrp.s1042_site_roi_offline.v1',source_sha=read(raw/'result.json')['source_sha'],
        scope='offline saved evidence; no simulation or control feedback',rows=result,
        actual_check=record['scene_grasp_check']['checks'][0],
        cause='reference rejected before pickup: artificial half-box padding crosses image/lens; no post-pick repeat view or comparison was attempted',
        limits='settled-command calibration, not measured joints; original-site projection ignores scene occlusion; no saved post-pick reference-pose image exists',
        source_sha256={n:sha(raw/n) for n in ('student_record.json','result.json','robots/r3/frames.jsonl','eval_only/trajectory.jsonl')})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();value=audit(a.raw)
    with a.output.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps([dict(label=r['label'],area=r['cyan_area_px'],roi=r.get('requested_roi'),background_std=r.get('unchanged_ecc_background_std')) for r in value['rows']],indent=2))
