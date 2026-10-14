"""Privileged teacher gaze targets through unchanged, real servo commands.

Reuses the command-space camera FK. Joint targets change; mount/intrinsics do
not. The sampled compact wrist/elbow family stays above low floor cargo.
"""
import math
from functools import lru_cache
import numpy as np
from harness.visual_arm_v3 import camera_extrinsics,MOUNT_X_M
from harness.visual_arm import PULSE_PER_DEGREE
from scripts.zone_teacher import FOLDED


@lru_cache(maxsize=1)
def compact_views():
    poses=[{**FOLDED,3:w,4:e} for w in range(500,961,20) for e in range(2320,2501,20)]
    fk=[camera_extrinsics(p) for p in poses]
    return poses,np.array([x[0] for x in fk]),np.array([x[1] for x in fk])


def gaze_pose(local_target,previous):
    x,y,z=local_target
    yaw=math.atan2(y,x-MOUNT_X_M)
    pan=max(500,min(2500,round(1500+math.degrees(yaw)*PULSE_PER_DEGREE)))
    angle=math.radians((pan-1500)/PULSE_PER_DEGREE);c,s=math.cos(angle),math.sin(angle)
    target=np.array([MOUNT_X_M+c*(x-MOUNT_X_M)+s*y,-s*(x-MOUNT_X_M)+c*y,z])
    poses,origins,axes=compact_views();delta=target-origins
    optical=np.einsum('nij,nj->ni',axes,delta)
    angular=np.arctan2(np.linalg.norm(optical[:,:2],axis=1),optical[:,2])
    # Prefer a small servo change among equally good viewing directions.
    score=angular+np.array([abs(p[3]-previous[3])+abs(p[4]-previous[4]) for p in poses])*.00002
    pose=dict(poses[int(np.argmin(score))]);pose[6]=pan
    return pose


def slew(previous,target,limit=60):
    return {k:int(previous[k]+max(-limit,min(limit,target[k]-previous[k]))) for k in target}
