"""Render recorded RGB overlays and stored poses in the current robot frame.

No motor imports/actions or new motion/pose inference. Video is a sequence of
settled observations, not continuous real-time footage.
"""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from green_wall_mapper import Mapper

p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args()
record=json.loads((a.run/'result.json').read_text());mapper=Mapper(record['floor_profile'])
cap=cv2.VideoCapture(str(a.run/'overlay-map.avi'))
writer=cv2.VideoWriter(str(a.run/'overlay-map-egocentric.avi'),cv2.VideoWriter_fourcc(*'MJPG'),2,(1120,480))
if not writer.isOpened():raise RuntimeError('summary video encoder unavailable')
poses=[record['poses'][0]];index=0
try:
    while True:
        ok,image=cap.read()
        if not ok:break
        row=record['frames'][index];pose=row['tracking'].get('pose')
        if pose is not None:poses.append(pose)
        mapper.pose_history=poses
        mapper.boundaries=[np.asarray(v['boundary_points']) for v in record['views'] if v['view']<=index]
        frame=np.hstack([image[:,:640],mapper.canvas()])
        cv2.putText(frame,'SETTLED OBSERVATIONS - playback slowed; not real-time',(9,460),0,.45,(255,255,255),1)
        writer.write(frame);index+=1
        cv2.imwrite(str(a.run/'final-overlay-egocentric.jpg'),frame)
    cv2.imwrite(str(a.run/'map-egocentric.png'),mapper.canvas())
finally:
    cap.release();writer.release()
if index!=len(record['frames']):raise RuntimeError('source video/frame ledger count mismatch')
print(json.dumps(dict(frames=index,pose_successes=len(poses)-1,source=str(a.run),inference_recomputed=False)))
