"""Choose a viewing posture using only observed occluder geometry.

Finite candidate version of visibility-constrained visual servoing: retain
the existing calibrated FK family, but rank line-of-sight clearance before
centering the target. No simulator, rays or hidden object poses are read.
"""
import math
import numpy as np
from harness.visual_arm import PULSE_PER_DEGREE
from harness.visual_arm_v3 import MOUNT_X_M
from sim.grasp_act_gaze import compact_views,camera_extrinsics


def gaze_pose(target, previous, occluders=(), *, visible=False):
    # A measured clear view is stronger evidence than a coarse cylinder model.
    # Preserve it while it remains comfortably within the image, instead of
    # needlessly centering a partially visible band behind an occluder.
    origin,axes=camera_extrinsics(previous)
    optical=np.array(axes)@(np.array(target)-origin)
    if visible and optical[2]>0 and max(abs(np.arctan2(optical[:2],optical[2])))<=math.radians(18):
        return dict(previous)
    x,y,z=target
    pan=max(500,min(2500,round(1500+math.degrees(math.atan2(y,x-MOUNT_X_M))*PULSE_PER_DEGREE)))
    angle=math.radians((pan-1500)/PULSE_PER_DEGREE);c,s=math.cos(angle),math.sin(angle)
    def unpan(point):
        x,y,z=point
        return np.array([MOUNT_X_M+c*(x-MOUNT_X_M)+s*y,-s*(x-MOUNT_X_M)+c*y,z])
    point=unpan(target);poses,origins,axes=compact_views();delta=point-origins
    optical=np.einsum('nij,nj->ni',axes,delta)
    angular=np.arctan2(np.linalg.norm(optical[:,:2],axis=1),optical[:,2])
    # Keep a conservative 18 degree cone inside the calibrated image.
    in_view=angular<=math.radians(18)
    clearance=np.full(len(poses),1.)
    for obstacle in occluders:
        center=unpan([*obstacle['xy'],0.])
        u=np.clip(np.einsum('ij,ij->i',center[:2]-origins[:,:2],delta[:,:2]) /
                  np.maximum(np.einsum('ij,ij->i',delta[:,:2],delta[:,:2]),1e-10),0.,1.)
        nearest=origins+u[:,None]*delta
        horizontal=np.linalg.norm(nearest[:,:2]-center[:2],axis=1)-obstacle['radius']-.015
        vertical=nearest[:,2]-obstacle['top_z_bound_m']-.015
        # A ray clears a vertical cylinder either beside it or above it.
        margin=np.maximum(horizontal,vertical)
        margin=np.where((u>0)&(u<1),margin,1.)
        clearance=np.minimum(clearance,margin)
    penalty=np.maximum(0.,-clearance)*100.
    score=angular+np.array([abs(p[3]-previous[3])+abs(p[4]-previous[4]) for p in poses])*.00002
    score+=penalty+np.where(in_view,0.,100.)
    k=int(np.argmin(score));pose=dict(poses[k]);pose[6]=pan
    return pose
