"""Continuous real RGB + held measured checkpoint cm distances, no interpolation."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import cv2
import numpy as np
from green_wall_mapper import Mapper,masks,floor_tracks

p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args()
record=json.loads((a.run/'result.json').read_text())
rows=[json.loads(v) for v in (a.run/'frames.jsonl').read_text().splitlines()]
checkpoints=record['checkpoints']
if not rows or not checkpoints:raise ValueError('no real frames/checkpoints')
mapper=Mapper(record['floor_profile']);render=a.run/'render';render.mkdir(exist_ok=False)
height=record['scale']['camera_height_cm'];previous=None;previous_floor=None
index=-1;lo=min(v['wall_gap_cm'] for v in checkpoints)-1;hi=max(v['wall_gap_cm'] for v in checkpoints)+1
def map_image(cp):
    out=np.full((480,480,3),25,np.uint8)
    cv2.putText(out,'CAMERA-CENTRED DISTANCE MAP',(12,22),0,.57,(255,255,255),1)
    cv2.putText(out,'Design height %.2f cm; accuracy unmeasured'%height,(12,42),0,.41,(220,220,220),1)
    if cp is None:return out
    gap=cp['wall_gap_cm'];delta=gap-checkpoints[0]['wall_gap_cm']
    cv2.putText(out,'Wall gap: %.2f cm'%gap,(12,76),0,.83,(0,210,255),2)
    cv2.putText(out,'Change: %+.2f cm   %s'%(delta,cp['phase']),(12,99),0,.56,(255,255,255),1)
    cv2.putText(out,'Latest measured checkpoint t=%.2fs'%cp['t'],(12,117),0,.40,(220,220,220),1)
    yaw=math.radians(cp['yaw_deg']);r=np.array([[math.cos(yaw),math.sin(yaw)],[-math.sin(yaw),math.cos(yaw)]])
    def xy(v):
        v=r@np.asarray(v);return int(240-v[1]*7),int(335-v[0]*7)
    for d in range(0,31,5):
        y=335-d*7
        if y>=125:
            cv2.line(out,(30,y),(465,y),(55,55,55),1)
            cv2.putText(out,str(d)+'cm',(2,y+4),0,.32,(180,180,180),1)
    for v in cp['contact_points_cm']:
        x,y=xy(v)
        if 0<=x<480 and 125<=y<350:cv2.circle(out,(x,y),2,(0,180,255),-1)
    end=xy(cp['nearest_wall_cm'])
    cv2.arrowedLine(out,(240,335),end,(0,210,255),2,tipLength=.06)
    cv2.drawMarker(out,(240,335),(255,255,255),cv2.MARKER_TRIANGLE_UP,14,2)
    cv2.putText(out,'0,0 = camera ground projection',(90,355),0,.40,(255,255,255),1)
    cv2.putText(out,'Observed gap history (design cm)',(12,377),0,.43,(255,255,255),1)
    current=[v for v in checkpoints if v['t']<=cp['t']]
    def chart(v):return int(25+v['t']/max(checkpoints[-1]['t'],.01)*425),int(452-(v['wall_gap_cm']-lo)/(hi-lo)*62)
    for before,after in zip(current,current[1:]):cv2.line(out,chart(before),chart(after),(0,210,255),2)
    for v in current:cv2.circle(out,chart(v),3,(255,255,255),-1)
    cv2.putText(out,'Not chassis bumper clearance / not surveyed distance',(8,476),0,.36,(0,200,255),1)
    return out
concat=[]
for i,row in enumerate(rows):
    while index+1<len(checkpoints) and checkpoints[index+1]['t']<=row['t']+1e-6:index+=1
    cp=checkpoints[index] if index>=0 else None
    raw=cv2.imread(str(a.run/row['image']));image=cv2.remap(raw,*mapper.maps,cv2.INTER_LINEAR)
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY);_,floor,contact=masks(image)
    if previous is not None:
        found,_=floor_tracks(previous,gray,previous_floor,floor)
        if found is not None:
            _,start,end=found
            for u,v in zip(start[::10],end[::10]):
                cv2.arrowedLine(image,tuple(np.rint(u).astype(int)),tuple(np.rint(v).astype(int)),(255,210,0),1,tipLength=.3)
    for u,v in contact[::5].astype(int):cv2.circle(image,(u,v),2,(0,180,255),-1)
    active=[v for v in record['commands'] if v['t_start']<=row['t']<=v.get('t_stop',v['t_start'])]
    text=active[-1]['phase']+' CHASSIS MOVING' if active else 'CHASSIS STOPPED'
    cv2.putText(image,'ARM COMMANDS FIXED / 0 SERVO WRITES',(8,24),0,.52,(255,255,255),1)
    cv2.putText(image,'t=%.2fs  '%row['t']+text,(8,47),0,.48,(255,255,255),1)
    frame=np.hstack([image,map_image(cp)]);name='render/'+row['image'];cv2.imwrite(str(a.run/name),frame)
    duration=rows[i+1]['t']-row['t'] if i+1<len(rows) else .5
    concat.extend(["file '"+name+"'",'duration %.6f'%duration])
    previous=gray;previous_floor=floor
    if i==len(rows)-1:cv2.imwrite(str(a.run/'distance-map-final.jpg'),frame)
concat.append("file 'render/"+rows[-1]['image']+"'")
(a.run/'video-input.txt').write_text('\n'.join(concat)+'\n')
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-f','concat','-safe','0','-i',str(a.run/'video-input.txt'),'-fps_mode','vfr','-c:v','libx264','-preset','ultrafast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',str(a.run/'distance-map-continuous.mp4')],check=True)
print(json.dumps(dict(real_frames=len(rows),checkpoints=len(checkpoints),source_timing_preserved=True,pose_interpolation=False)))
