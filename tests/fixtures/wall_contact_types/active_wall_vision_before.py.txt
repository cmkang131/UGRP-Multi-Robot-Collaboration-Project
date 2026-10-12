"""Own RGB -> frozen wall contacts and finite observed floor rays. No file/GT input."""
from functools import lru_cache
from pathlib import Path
import sys
import math
import cv2
import numpy as np
from harness.active_camera import transform as camera_transform
from harness.wall_projection_guard import filter_segments


@lru_cache(maxsize=1)
def modules():
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/'experiments/2026-10-05-ego-wall-map-probe/code'))
    sys.path.insert(0,str(root/'experiments/2026-09-26-markerless-probe'))
    import markerless_probe as mp
    import height_free_wall as hfw
    import ego_wall_map as ewm
    return mp,hfw,ewm


def observe(rgb,servo,*,body_settling=1.):
    mp,hfw,ewm=modules()
    origin,rotation=camera_transform(servo)
    cm=mp.ColumnModel(tuple(sorted(servo.items())),0.,mp.column_positions(96,2),camera_transform=(origin,rotation))
    und=mp.undistort(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
    params={'floor_patch_max_m':.81,'run_step_window':3,'top_edge_px':4}
    scan=hfw.detect(und,cm,params=params,loaded=False)
    grey=cv2.cvtColor(und,cv2.COLOR_BGR2GRAY).astype(float)
    segments,features=[],[]
    for segment in hfw.link_segments(scan,params):
        r,a,s,b,_=ewm.segment_to_chassis(segment,cm.origin[:2],0.)
        seg=[[r*math.cos(a),r*math.sin(a)],[s*math.cos(b),s*math.sin(b)]]
        if np.linalg.norm(np.asarray(seg)-origin[:2],axis=1).max()>=4.:
            continue
        ix=np.arange(segment['col_first'],segment['col_last']+1)
        v=np.rint(scan['vb'][ix,0]).astype(int).clip(1,mp.HEIGHT-2)
        u=cm.columns[ix].astype(int)
        segments.append(seg)
        features.append(dict(height_m=float(origin[2]),fy=mp.FY,contrast=segment['contrast_med'],
            band_std=float(np.median(scan['s'][ix,0])),sharpness=float(np.median(abs(grey[v+1,u]-grey[v-1,u]))),
            body_settling=float(body_settling)))
    valid,guard=filter_segments(segments if segments else np.empty((0,2,2)),wall_projection_guard='positive_depth_v1',
        camera_origin=origin,camera_rotation=rotation)
    ids=[e['segment'] for e in guard['segments'] if e['accepted']]
    features=[features[i] for i in ids]
    # Free is supported ONLY below an observed wall contact in that image column,
    # and only by actual low-saturation floor-colour pixels. No extrapolation beyond returns.
    hsv=cv2.cvtColor(und,cv2.COLOR_BGR2HSV)
    pixels=[]
    for j,u in enumerate(cm.columns.astype(int)):
        vb=scan['vb'][j,0]
        if not np.isfinite(vb):
            continue
        for v in range(max(0,int(math.ceil(vb))+3),mp.HEIGHT-4,12):
            if hsv[v,u,1]<=128 and hsv[v,u,2]>=30:
                pixels.append([u,v,1.])
    floor=np.empty((0,2))
    if pixels:
        rays=np.asarray(pixels)@np.linalg.inv(mp.K).T@rotation.T
        with np.errstate(divide='ignore',invalid='ignore'):
            depths=-origin[2]/rays[:,2]
            points=origin+rays*depths[:,None]
        keep=(depths>0)&np.isfinite(points).all(1)&(np.linalg.norm(points-origin,axis=1)<4.)
        floor=points[keep,:2]
    return dict(segments=np.asarray(valid).reshape(-1,2,2).tolist(),features=features,
                floor_xy=floor.tolist(),camera=origin[:2].tolist(),camera_origin=origin.tolist(),
                camera_rotation=rotation.tolist(),guard=guard)
