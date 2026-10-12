"""ROS Costmap2D/InflationLayer formula port, with full rectangular footprint checks.

BSD originals and license retained in third_party/mapfree_navigation/navigation.
Unknown remains 255. Inflation does not fabricate free observations or coverage.
"""
import math

import cv2
import numpy as np
from scipy.ndimage import distance_transform_edt

RESOLUTION = .1
HALF = np.array([.12,.10]) + .02


class Costmap:
    def __init__(self,raw,origin,resolution=RESOLUTION):
        self.raw = np.asarray(raw,np.uint8)
        self.origin = np.asarray(origin,float)
        self.resolution = resolution
        self.costs = self.inflate()

    def world_to_map(self,xy):
        # ROS lower bound rejection must precede truncation, especially negative x/y.
        xy = np.asarray(xy,float)
        if np.any(xy < self.origin):
            return None
        cell = np.floor((xy-self.origin)/self.resolution).astype(int)
        if np.any(cell >= self.raw.shape[::-1]):
            return None
        return tuple(int(v) for v in cell)

    def map_to_world(self,cell):
        return self.origin+(np.asarray(cell,float)+.5)*self.resolution

    def inflate(self):
        # Exact computeCost distance rule, EDT replacing ROS priority-queue distance cache.
        distance = distance_transform_edt(self.raw!=254)*self.resolution
        costs = np.zeros(self.raw.shape,np.uint8)
        within = distance<=.5
        values = 252*np.exp(-10*np.maximum(0,distance-HALF.min()))
        costs[within] = values[within].astype(np.uint8)
        costs[distance<=HALF.min()] = 253
        costs[self.raw==254] = 254
        costs[self.raw==255] = 255
        return costs

    def footprint_mask(self,pose):
        c,s = math.cos(pose[2]),math.sin(pose[2])
        corners = np.array([[-1,-1],[1,-1],[1,1],[-1,1]])*HALF
        polygon = corners@np.array([[c,s],[-s,c]])+pose[:2]
        cells = np.floor((polygon-self.origin)/self.resolution).astype(np.int32)
        mask = np.zeros(self.raw.shape,np.uint8)
        cv2.fillConvexPoly(mask,cells,1)
        return mask.astype(bool),polygon

    def pose_clear(self,pose):
        mask,polygon = self.footprint_mask(np.asarray(pose,float))
        if any(self.world_to_map(p) is None for p in polygon):
            return False
        return not bool(np.any(self.raw[mask]>=254))

    def sweep_clear(self,start,end):
        start,end = np.asarray(start,float),np.asarray(end,float)
        turn = (end[2]-start[2]+math.pi)%(2*math.pi)-math.pi
        steps = max(1,math.ceil(np.linalg.norm(end[:2]-start[:2])/.025),math.ceil(abs(turn)/math.radians(5)))
        return all(self.pose_clear([*(start[:2]+u*(end[:2]-start[:2])),start[2]+u*turn])
                   for u in np.linspace(0,1,steps+1))


def from_grid(grid,pose,latest=None,static_hits=()):
    state,lo = grid.dense(pose,pad_m=1.)
    raw = np.where(state==0,255,np.where(state>0,254,0)).astype(np.uint8)
    for cell,hit in (latest or {}).items():
        x,y = np.asarray(cell)-lo
        raw[y,x] = 254 if hit else 0
    for cell in static_hits:
        x,y = np.asarray(cell)-lo
        raw[y,x] = 254
    result = Costmap(raw,lo*grid.resolution,grid.resolution)
    # ObstacleLayer footprint clearing: planning support only, never sensor/grid provenance.
    mask,_ = result.footprint_mask(np.asarray(pose,float))
    result.raw[mask] = 0
    result.costs = result.inflate()
    return result
