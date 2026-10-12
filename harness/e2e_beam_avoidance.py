"""Planning-only obstacle from own observed beam pose and fixed catalogue size."""
import math
import cv2
import numpy as np
from harness.public_navigation_unknown import UnknownCostmap

OPTION='own_obstacle_v1'


def corners(center,yaw):
    c,s=math.cos(yaw),math.sin(yaw)
    return np.array([[-1,-1],[1,-1],[1,1],[-1,1]])*np.array([.30,.03])@np.array([[c,s],[-s,c]])+np.asarray(center)


def add(costmap,center,yaw):
    raw=costmap.raw.copy()
    poly=np.floor((corners(center,yaw)-costmap.origin)/costmap.resolution).astype(np.int32)
    cv2.fillConvexPoly(raw,poly,254)
    return UnknownCostmap(raw,costmap.origin.copy(),costmap.resolution)


def fallback(navigator,pose,target,center,yaw):
    """DEV unobserved-space retry retains the observed beam as an obstacle.

    This transient planning grid is never added to the RGB map or coverage.
    Existing known-wall projected checks still run on the returned command.
    """
    points=np.vstack([pose[:2],target,corners(center,yaw)])
    if not np.isfinite(points).all():return []
    res=.05;lo=np.floor((points.min(axis=0)-.8)/res)*res
    shape=np.ceil((points.max(axis=0)+.8-lo)/res).astype(int)
    if np.prod(shape)>1_000_000:return []
    cm=add(UnknownCostmap(np.zeros(tuple(shape[::-1]),np.uint8),lo,res),center,yaw)
    return navigator.plan_to(cm,pose,target)
