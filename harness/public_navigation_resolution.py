"""Opt-in Nav2 bringup 0.05m costmap; unchanged v4 navigation semantics.

Authored baseline map only. No live geometry/truth inputs. Source and camera
adaptations: experiments/2026-10-07-mapfree-s4-final/REFERENCES.md.
"""
import numpy as np
from harness.own_map_navigation import ObservedGrid
from harness.public_navigation_outline import OutlineActor
from harness.self_odom_grid import transform

OPTION='public_ros_v5'
RESOLUTION=.05  # pinned Nav2 bringup local/global YAML, not library default .1


def navigation_output_v5(legacy,*,navigation='off',navigator=None,**kwargs):
    if navigation=='off':return legacy
    if navigation!=OPTION or navigator is None:raise ValueError('EXPLICIT_PUBLIC_ROS_V5_REQUIRED')
    return navigator.update(**kwargs)


def authored_inputs(static,alignment):
    """Same baseline raster rule at the configured cell size; half-cell margin.

    StaticLayer consumes a map's declared resolution; it does not shrink an
    existing coarse cell. Rasterization here is the authored vector-map adapter,
    not Nav2 code. Keep its existing half-cell margin scaled with resolution.
    """
    res=RESOLUTION
    grid=ObservedGrid('r1',resolution_m=res)
    x0,x1,y0,y1=static['bounds_m']
    yaw=alignment[2]
    c,s=np.cos(yaw),np.sin(yaw)
    def inverse(points):
        return (np.asarray(points)-alignment[:2])@np.array([[c,-s],[s,c]])
    corners=inverse([[x0,y0],[x0,y1],[x1,y0],[x1,y1]])
    lo,hi=np.floor(corners.min(0)/res).astype(int),np.ceil(corners.max(0)/res).astype(int)
    xx,yy=np.meshgrid(np.arange(lo[0],hi[0]),np.arange(lo[1],hi[1]))
    cells=np.stack([xx.ravel(),yy.ravel()],1)
    points=transform((cells+.5)*res,alignment)
    occupied=np.zeros(len(points),bool)
    for o in static['obstacles']:
        # Same authored, axis-aligned obstacle schema as the frozen baseline.
        if o.get('yaw_rad',0.)!=0.:raise ValueError('ROTATED_AUTHORED_MAP_UNSUPPORTED')
        occupied|=(np.abs(points-np.asarray(o['center_m']))<=np.asarray(o['half_extents_m'])+res/2).all(axis=1)
    inside=(points[:,0]>=x0)&(points[:,0]<=x1)&(points[:,1]>=y0)&(points[:,1]<=y1)
    for cell,hit,keep in zip(cells,occupied,inside):
        if not keep:continue
        cell=tuple(int(v) for v in cell)
        grid.odds[cell]=4. if hit else -4.
        (grid.wall_frames if hit else grid.floor_frames)[cell]={'authored_static'}
    goal=inverse([static['regions']['zone_B']['center_m']])[0].tolist()
    return grid,goal


class ResolutionActor(OutlineActor):
    def __init__(self,condition,static_grid=None,static_goal=None,*,navigation='off'):
        if navigation!=OPTION:raise ValueError('EXPLICIT_PUBLIC_ROS_V5_REQUIRED')
        if static_grid is None:static_grid=ObservedGrid('r1',resolution_m=RESOLUTION)
        if static_grid.resolution!=RESOLUTION:raise ValueError('V5_REQUIRES_NATIVE_005_MAP')
        super().__init__(condition,static_grid,static_goal,navigation='public_ros_v4')
        # v4 methods keep their exact option dispatch. v5 composes that implementation.
        self.resolution_profile=OPTION
