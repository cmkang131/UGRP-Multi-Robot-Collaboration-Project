"""Own-observation interface for public NavFn/frontier/pursuit stack, default off.

No scene/world/sensor-truth import is permitted here. Static baseline goal/map are
explicit caller-supplied authored inputs. See experiment README for adaptations.
"""
import math
import numpy as np

from .native import PublicCore
from .follower import follow_twist,projected_clear,command_from_twist


class PublicNavigator:
    def __init__(self):
        self.core = PublicCore()
        self.target = None
        self.heading = None
        self.frontier = None
        self.blacklist = []
        self.events = []
        self.best_distance = math.inf
        self.last_progress = 0.
        self.path = []

    def blocked(self,target,resolution):
        # explore.cpp::goalOnBlacklist: tolerance=5 cells, strict axis-wise comparison.
        return any(np.all(np.abs(np.asarray(target)-p)<5*resolution) for p in self.blacklist)

    def abort(self,t,reason):
        if self.frontier is not None:
            self.blacklist.append(self.frontier.copy())
        self.events.append(dict(t=float(t),reason=reason,target=None if self.target is None else self.target.tolist()))
        self.target,self.frontier,self.path = None,None,[]
        self.best_distance = math.inf

    def plan_to(self,costmap,pose,target):
        start,goal = costmap.world_to_map(pose[:2]),costmap.world_to_map(target)
        if start is None or goal is None or costmap.costs[goal[1],goal[0]]>=253:
            return []
        if start==goal:
            return [list(pose[:2]),list(target)] if costmap.sweep_clear(pose,[*target,pose[2]]) else []
        cells = self.core.plan(costmap.costs,start,goal)
        if not len(cells):
            return []
        centres = costmap.map_to_world(cells)
        # Preserve the connector from continuous pose to first grid centre (v2 omitted it).
        if not costmap.sweep_clear(pose,[*centres[0],pose[2]]):
            return []
        return np.vstack([pose[:2],centres,target]).tolist()

    def update(self,costmap,pose,t,static_goal=None):
        pose = np.asarray(pose,float)
        if self.target is not None:
            distance = np.linalg.norm(self.target-pose[:2])
            if distance<self.best_distance-1e-5:
                self.best_distance,self.last_progress = distance,t
            if t-self.last_progress>30.:
                self.abort(t,'progress_timeout')
        if static_goal is not None:
            # Authored baseline B centre. The camera/temporal detector still decides confirmation.
            self.target = np.array(static_goal,float)
            self.heading = math.atan2(self.target[1]-pose[1],self.target[0]-pose[0])
        if self.target is None:
            for f in self.core.frontiers(costmap.raw,costmap.origin,costmap.resolution,pose[:2]):
                centre = f[:2]
                if self.blocked(centre,costmap.resolution):
                    continue
                # Camera adaptation: frontier centroid is unknown, use reachable observed-free
                # standoff adjacent to it rather than admitting unknown traversal.
                yy,xx = np.nonzero(costmap.costs<253)
                points = costmap.map_to_world(np.column_stack([xx,yy]))
                order = np.argsort(np.linalg.norm(points-centre,axis=1),kind='stable')
                selected = None
                for idx in order:
                    if np.linalg.norm(points[idx]-centre)>.5:
                        break
                    path = self.plan_to(costmap,pose,points[idx])
                    if path:
                        selected=(points[idx],path)
                        break
                if selected is None:
                    self.blacklist.append(centre.copy())
                    self.events.append(dict(t=float(t),reason='ABORTED_unreachable',target=centre.tolist()))
                    continue
                self.target,self.path = selected
                self.frontier = centre.copy()
                self.heading = math.atan2(centre[1]-self.target[1],centre[0]-self.target[0])
                self.last_progress,self.best_distance = t,math.inf
                break
        if self.target is None:
            return dict(status='observe_rotation',path_m=[],heading_rad=float(pose[2]+math.radians(25)),doors=[])
        self.path = self.plan_to(costmap,pose,self.target)
        if not self.path:
            self.abort(t,'ABORTED_no_path')
            return dict(status='no_path',path_m=[],heading_rad=float(pose[2]+math.radians(25)),doors=[])
        return dict(status='public_static' if static_goal is not None else 'public_frontier',
                    path_m=self.path,heading_rad=float(self.heading),doors=[])

    def command(self,costmap,pose,plan,t):
        twist = follow_twist(plan['path_m'],pose,plan['heading_rad'])
        if not projected_clear(costmap,pose,twist):
            self.events.append(dict(t=float(t),reason='predicted_footprint_collision'))
            twist[:] = 0.
        return command_from_twist(twist,t)


def navigation_output(legacy,*,navigation='off',navigator=None,**kwargs):
    if navigation=='off':
        return legacy
    if navigation!='public_ros_v1':
        raise ValueError('UNKNOWN_PUBLIC_NAVIGATION_OPTION')
    if navigator is None:
        raise ValueError('PUBLIC_NAVIGATOR_REQUIRED')
    return navigator.update(**kwargs)
