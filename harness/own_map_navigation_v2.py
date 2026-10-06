"""Opt-in ROS-style footprint clearing and polygon raster clearance.

Only the commanded own pose and private observations enter this module. Unknown
outside the padded footprint stays unknown. Body clearing is a planning-layer
assumption, never camera evidence or evaluation coverage.
"""
import copy
import math

import cv2
import numpy as np
from scipy.ndimage import binary_dilation, distance_transform_edt

from harness.own_map_navigation import Footprint, OwnMapNavigator
from harness.self_odom_grid import transform


def footprint_cells(grid, pose, footprint=Footprint(), margin=.02):
    """ROS setConvexPolygonCost: rasterized boundary plus filled polygon."""
    half = np.array([footprint.half_length_m,footprint.half_width_m])+margin
    corners = transform(np.array([[-1,-1],[1,-1],[1,1],[-1,1]])*half,pose)
    vertices = np.floor(corners/grid.resolution).astype(np.int32)
    lo,hi = vertices.min(0),vertices.max(0)
    mask = np.zeros(tuple((hi-lo+1)[::-1]),np.uint8)
    cv2.fillConvexPoly(mask,vertices-lo,1)
    yy,xx = np.nonzero(mask)
    return {(int(x+lo[0]),int(y+lo[1])) for x,y in zip(xx,yy)}


def polygon_clearance(grid, footprint, margin, yaw=None):
    state,lo = grid.dense()
    r = grid.resolution
    if yaw is None:
        n = math.ceil((footprint.radius+margin)/r+.5)
        yy,xx = np.mgrid[-n:n+1,-n:n+1]*r
        kernel = np.maximum(abs(xx)-r/2,0)**2+np.maximum(abs(yy)-r/2,0)**2 <= (footprint.radius+margin)**2
    else:
        cells = footprint_cells(grid,(*grid.point((0,0)),yaw),footprint,margin)
        n = max(max(abs(x),abs(y)) for x,y in cells)
        kernel = np.zeros((2*n+1,2*n+1),bool)
        for x,y in cells:
            kernel[y+n,x+n] = True
    blocked = binary_dilation(state != -1,structure=kernel,border_value=1)
    return state,~blocked,distance_transform_edt(state == -1)*r,lo


def pose_clear(grid, pose, footprint=Footprint(), margin=.02):
    return all(grid.state(c)==-1 for c in footprint_cells(grid,pose,footprint,margin))


def segment_clear(grid, start, end, footprint=Footprint(), margin=.02):
    """Check actual subcell translation and rotation, not a snapped full-turn circle."""
    start,end = np.asarray(start,float),np.asarray(end,float)
    count = max(1,math.ceil(np.linalg.norm(end[:2]-start[:2])/.025),math.ceil(abs(end[2]-start[2])/math.radians(5)))
    return all(pose_clear(grid,start+(end-start)*u,footprint,margin) for u in np.linspace(0,1,count+1))


class OwnMapNavigatorV2(OwnMapNavigator):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.body_support = set()
        self.last_grid = None

    def prepare_grid(self,grid,pose,footprint=Footprint()):
        current = footprint_cells(grid,pose,footprint,self.options.pose_margin_m)
        self.body_support.update(current)
        view = copy.copy(grid)
        # No legacy circumscribed initial disk: only previously occupied body polygons.
        view.support = self.body_support.copy()
        view.odds = dict(grid.odds)
        # ROS obstacle layer: an observed hit marks the costmap until later clearing.
        # Do not require five hits to overcome the authored static free prior (-4).
        order = {frame:i for i,frame in enumerate(grid.view_poses)}
        for cell,frames in grid.wall_frames.items():
            hit = max((order.get(f,-1) for f in frames),default=-1)
            free = max((order.get(f,-1) for f in grid.floor_frames.get(cell,())),default=-1)
            if hit >= 0 and hit >= free:
                view.odds[cell] = 4.
        for c in current:
            view.odds[c] = -4.
        view._polygon_clearance_v2 = True
        self.last_grid = view
        return view

    def update(self,legacy_output,*,grid=None,pose=(0.,0.,0.),goal=None,footprint=Footprint(),carrying=False):
        if not self.options.enabled:
            return legacy_output
        if grid is None or grid.robot_id != self.robot_id:
            raise ValueError('NAV_REQUIRES_OWN_GRID')
        view = self.prepare_grid(grid,pose,footprint)
        result = super().update(legacy_output,grid=view,pose=pose,goal=goal,footprint=footprint,carrying=carrying)
        return {**result,'body_support_cells':len(self.body_support),'free_policy':'padded_footprint_polygon_v2'}
