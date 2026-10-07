"""Actual own camera boundary columns and 1px IPM covariance, offline/on only."""
import math
import cv2
import numpy as np
from harness.active_wall_vision import modules
from harness.active_camera import transform as camera_transform
from harness.wall_projection_guard import filter_segments


def contact_points(rgb,servo):
    mp,hfw,ewm=modules()
    origin,rotation=camera_transform(servo)
    cm=mp.ColumnModel(tuple(sorted(servo.items())),0.,mp.column_positions(96,2),camera_transform=(origin,rotation))
    und=mp.undistort(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
    params={'floor_patch_max_m':.81,'run_step_window':3,'top_edge_px':4}
    scan=hfw.detect(und,cm,params=params,loaded=False)
    grey=cv2.cvtColor(und,cv2.COLOR_BGR2GRAY).astype(float)
    basis=rotation@np.linalg.inv(mp.K)
    collected={}
    for segment in hfw.link_segments(scan,params):
        r,a,s,b,_=ewm.segment_to_chassis(segment,cm.origin[:2],0.)
        ends=[[r*math.cos(a),r*math.sin(a)],[s*math.cos(b),s*math.sin(b)]]
        if np.linalg.norm(np.asarray(ends)-origin[:2],axis=1).max()>=4.:continue
        kept,_=filter_segments([ends],wall_projection_guard='positive_depth_v1',camera_origin=origin,camera_rotation=rotation)
        if not len(kept):continue
        for j in range(segment['col_first'],segment['col_last']+1):
            u,v=float(cm.columns[j]),float(scan['vb'][j,0])
            if not np.isfinite(v):continue
            ray=basis@np.array([u,v,1.])
            if ray[2]>=0:continue
            point=(origin-origin[2]*ray/ray[2])[:2]
            if np.linalg.norm(point-origin[:2])>=4.:continue
            jac=-origin[2]*(basis[:2,:2]*ray[2]-ray[:2,None]*basis[2,:2])/ray[2]**2
            vi=int(np.clip(round(v),1,mp.HEIGHT-2))
            gradient=abs(grey[vi+1,int(u)]-grey[vi-1,int(u)])
            contrast=segment['contrast_med']
            std=float(scan['s'][j,0])
            quality=.7*contrast**2/(contrast**2+std**2+36.)*gradient**2/(gradient**2+std**2+36.)
            covariance=(jac@jac.T)/max(quality,1e-12)+np.eye(2)*1e-12
            collected[j]=(point,covariance)
    return dict(points=[collected[j][0].tolist() for j in sorted(collected)],
        covariances=[collected[j][1].tolist() for j in sorted(collected)],
        columns=sorted(collected),camera=origin[:2].tolist())
