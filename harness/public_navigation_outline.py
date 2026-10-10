"""Default-off Nav2 footprint edge port; unchanged v3 navigation/recovery.

Source: pinned Nav2 FootprintCollisionChecker::footprintCost/lineCost and
LineIterator, recorded in experiments/2026-10-07-mapfree-stop-geometry/REFERENCES.md.
Camera constraint: unobserved/out-of-map cells remain forbidden. No GT inputs.
"""
import math
import numpy as np
from harness.public_navigation.costmap import Costmap,from_grid
from harness.public_navigation_persistent import PersistentActor,raytrace_cells

OPTION='public_ros_v4'


class OutlineCostmap(Costmap):
    def pose_clear(self,pose):
        # Same padded polygon/worldToMap. Nav2 walks its edges, not filled cells.
        _,polygon=self.footprint_mask(np.asarray(pose,float))
        cells=[self.world_to_map(p) for p in polygon]
        if None in cells:return False
        footprint_cost=0
        for begin,end in zip(cells,cells[1:]+cells[:1]):
            line_cost=0
            for x,y in raytrace_cells(begin,end):
                point_cost=int(self.costs[y,x])
                if point_cost==254:return False  # upstream lethal early return
                line_cost=max(line_cost,point_cost)
            footprint_cost=max(footprint_cost,line_cost)
        # Upstream RPP can permit unknown; own-camera contract forbids it.
        return footprint_cost<254


def navigation_output_v4(legacy,*,navigation='off',navigator=None,**kwargs):
    if navigation=='off':return legacy
    if navigation!=OPTION or navigator is None:raise ValueError('EXPLICIT_PUBLIC_ROS_V4_REQUIRED')
    return navigator.update(**kwargs)


class OutlineActor(PersistentActor):
    def __init__(self,condition,static_grid=None,static_goal=None,*,navigation='off'):
        if navigation!=OPTION:raise ValueError('EXPLICIT_PUBLIC_ROS_V4_REQUIRED')
        super().__init__(condition,static_grid,static_goal,navigation='public_ros_v3')
        self.option=OPTION

    def plan(self):
        if self.navigator.clear_requested:self.clear_obstacles()
        pose=np.asarray(self.odom.pose)
        original=from_grid(self.grid,pose,self.latest,self.static_hits)
        # Unchanged v3 footprint clearing and restoration of authored static layer.
        for cell in self.static_hits:
            ij=original.world_to_map(self.grid.point(cell))
            if ij is not None:original.raw[ij[1],ij[0]]=254
        self.costmap=OutlineCostmap(original.raw,original.origin,original.resolution)
        plan=navigation_output_v4(None,navigation=self.option,navigator=self.navigator,
            costmap=self.costmap,pose=pose,t=self.t,static_goal=self.static_goal)
        if self.last_patches and not self.navigator.phase and not self.navigator.failed:
            target=np.asarray(self.last_patches[-1]['center_odom_m'])
            delta=target-pose[:2]
            point=pose[:2]+.12*delta/max(np.linalg.norm(delta),1e-9)
            path=self.navigator.plan_to(self.costmap,pose,point)
            if path:
                plan=dict(status='goal_reobserve',path_m=path,
                    heading_rad=math.atan2(delta[1],delta[0]),doors=[])
        plan['doors']=self.doors.update(self.grid,pose)
        self.counts[plan['status']]=self.counts.get(plan['status'],0)+1
        return plan
