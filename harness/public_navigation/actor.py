"""One robot's public navigation stack, own commands and camera measurements only."""
import copy
import json
import math

import numpy as np

from harness.own_map_navigation import ObservedGrid,DoorMemory
from harness.floor_goal_v3 import FloorGoalMemoryV3
from harness.self_map_prob import V7CommandOdometry
from harness.self_odom_grid import transform
from .native import ROOT
from .costmap import from_grid
from .stack import PublicNavigator,navigation_output

SEARCH = {1:2000,3:740,4:2320,5:1320,6:1500}


class MeasurementMemory(FloorGoalMemoryV3):
    def add(self,patches,t,frame,pose):
        self.detector = lambda *_a,**_k:(copy.deepcopy(patches),None,{})
        return self.observe(None,robot_id='r1',frame_id=frame,t=t,pose=pose,servo=SEARCH,
                            profile='camera_v3',settled=True)[0]


class PublicActor:
    def __init__(self,condition,static_grid=None,static_goal=None,*,navigation='off'):
        if navigation!='public_ros_v1':
            raise ValueError('PUBLIC_ACTOR_REQUIRES_EXPLICIT_OPT_IN')
        self.option = navigation
        self.condition = condition
        self.grid = static_grid if static_grid is not None else ObservedGrid('r1')
        self.static_hits = {c for c,v in self.grid.odds.items() if v>0}
        self.latest = {}
        self.static_goal = static_goal
        self.odom = V7CommandOdometry()
        self.navigator = PublicNavigator()
        options = json.loads((ROOT/'experiments/2026-10-07-mapfree-goal-floor/v3-selection.json').read_text())['selected']['options']
        self.goal = MeasurementMemory('r1',options=options)
        self.doors = DoorMemory('r1')
        self.t,self.steps = 0.,0
        self.counts = {}
        self.last_patches = []

    def receive(self,observation,patches):
        self.grid.observe(**observation,pose=self.odom.pose)
        for field,hit in [('floor_xy',False),('wall_xy',True)]:
            points = np.asarray(observation[field],float).reshape(-1,2)
            for point in transform(points,self.odom.pose):
                self.latest[self.grid.cell(point)] = hit
        self.last_patches = self.goal.add(patches,self.t,self.steps,self.odom.pose)
        return self.last_patches

    def plan(self):
        pose = np.asarray(self.odom.pose)
        self.costmap = from_grid(self.grid,pose,self.latest,self.static_hits)
        plan = navigation_output(None,navigation=self.option,navigator=self.navigator,
                                 costmap=self.costmap,pose=pose,t=self.t,static_goal=self.static_goal)
        # Same task rule as old BCE: a recent, unconfirmed own patch requests translation.
        # No patch truth or authored B is supplied to exploration.
        if self.condition=='own_frontier' and self.last_patches:
            target = np.asarray(self.last_patches[-1]['center_odom_m'])
            delta = target-pose[:2]
            heading = math.atan2(delta[1],delta[0])
            point = pose[:2]+.12*delta/max(np.linalg.norm(delta),1e-9)
            path = self.navigator.plan_to(self.costmap,pose,point)
            if path:
                plan = dict(status='goal_reobserve',path_m=path,heading_rad=heading,doors=[])
        plan['doors'] = self.doors.update(self.grid,pose)
        self.counts[plan['status']] = self.counts.get(plan['status'],0)+1
        return plan

    def command(self,plan):
        return self.navigator.command(self.costmap,self.odom.pose,plan,self.t)
