"""Default-off Nav2 current-footprint clearing and unknown-space policy.

Pinned BSD/Apache sources and explicit camera-grid adaptations are recorded in
experiments/2026-10-07-mapfree-unknown-footprint/REFERENCES.md. Own pose/sensor
inputs only. Clearing never predicts a future footprint or adds RGB coverage.
"""
import ctypes
import hashlib
import math
import subprocess
import numpy as np
from harness.public_navigation.native import PublicCore, ROOT, VENDOR, HERE
from harness.public_navigation.costmap import HALF, Costmap
from harness.public_navigation_persistent import PersistentNavigator, raytrace_cells
from harness.public_navigation_raytrace import RaytraceActor

OPTION = 'public_ros_v7'


def navigation_output_v7(legacy, *, navigation='off', navigator=None, **kwargs):
    if navigation == 'off':
        return legacy
    if navigation != OPTION or navigator is None:
        raise ValueError('EXPLICIT_PUBLIC_ROS_V7_REQUIRED')
    return navigator.update(**kwargs)


def build():
    sources = [VENDOR/'navigation/navfn/src/navfn.cpp',
               VENDOR/'m-explore/explore/src/frontier_search.cpp',
               ROOT/'harness/public_navigation_unknown.cpp']
    inputs = sources + [HERE/'bridge.cpp'] + sorted((HERE/'shim').rglob('*.h')) + list(VENDOR.rglob('*.h'))
    digest = hashlib.sha256(b''.join(p.read_bytes() for p in inputs)).hexdigest()[:16]
    target = ROOT/'outputs/mapfree-public-navigation-build'/f'unknown-{digest}.so'
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['c++','-std=c++17','-O2','-shared','-fPIC',
            '-I'+str(HERE/'shim'), '-I'+str(VENDOR/'navigation/navfn/include'),
            '-I'+str(VENDOR/'m-explore/explore/include'), *map(str,sources), '-o',str(target)],
            check=True, capture_output=True, text=True)
    return target


class UnknownCore(PublicCore):
    def __init__(self):
        self.lib = ctypes.CDLL(str(build()))
        array = np.ctypeslib.ndpointer(dtype=np.uint8, flags='C_CONTIGUOUS')
        self.lib.ugrp_navfn.argtypes = [array,*([ctypes.c_int]*6),
            np.ctypeslib.ndpointer(dtype=np.float32,flags='C_CONTIGUOUS'),ctypes.c_int]
        self.lib.ugrp_frontiers.argtypes = [array,ctypes.c_int,ctypes.c_int,*([ctypes.c_double]*5),
            np.ctypeslib.ndpointer(dtype=np.float64,flags='C_CONTIGUOUS'),ctypes.c_int]


def footprint_cells(grid, pose):
    """Costmap2D convexFillCells: outline Bresenham, then inclusive x-column fill.

    Unbounded own grid uses absolute cell tuples instead of unsigned local indices.
    Grouping the outline by x is equivalent to the source's x sort/min-max scan.
    """
    pose = np.asarray(pose, float)
    if pose.shape != (3,) or not np.isfinite(pose).all():
        raise ValueError('OWN_FINITE_POSE_REQUIRED')
    c,s = math.cos(pose[2]),math.sin(pose[2])
    polygon = (np.array([[-1,-1],[1,-1],[1,1],[-1,1]])*HALF) @ np.array([[c,s],[-s,c]]) + pose[:2]
    vertices = [grid.cell(p) for p in polygon]
    columns = {}
    for a,b in zip(vertices, vertices[1:]+vertices[:1]):
        for x,y in raytrace_cells(a,b):
            columns.setdefault(x,[]).append(y)
    return {(x,y) for x,ys in columns.items() for y in range(min(ys),max(ys)+1)}


def clear_current_footprint(grid, latest, static_hits, pose):
    cells = footprint_cells(grid, pose)-set(static_hits)
    for cell in cells:
        latest[cell] = False
        grid.odds[cell] = -max(1.,abs(grid.odds.get(cell,0.)))
    grid.support.update(cells)  # existing non-RGB body-support provenance
    # floor_frames deliberately unchanged: traversed support is not RGB evidence.
    return cells


class UnknownCostmap(Costmap):
    def pose_clear(self, pose):
        _,polygon = self.footprint_mask(np.asarray(pose,float))
        cells = [self.world_to_map(p) for p in polygon]
        if None in cells:
            return False  # explicit finite camera-map restriction
        footprint_cost = 0
        for a,b in zip(cells,cells[1:]+cells[:1]):
            for x,y in raytrace_cells(a,b):
                cost = int(self.costs[y,x])
                if cost == 254:
                    return False
                footprint_cost = max(footprint_cost,cost)
        # RPP: NO_INFORMATION + isTrackingUnknown permits this footprint.
        if footprint_cost == 255:
            return True
        return footprint_cost < 254


def from_observed_grid(grid, pose, latest, static_hits):
    state,lo = grid.dense(pose,pad_m=1.)
    raw = np.where(state==0,255,np.where(state>0,254,0)).astype(np.uint8)
    for cell,hit in latest.items():
        x,y = np.asarray(cell)-lo
        raw[y,x] = 254 if hit else 0
    for cell in static_hits:
        x,y = np.asarray(cell)-lo
        raw[y,x] = 254
    return UnknownCostmap(raw,lo*grid.resolution,grid.resolution)


class UnknownNavigator(PersistentNavigator):
    def __init__(self):
        super().__init__()
        self.core = UnknownCore()

    def plan_to(self, costmap, pose, target):
        start,goal = costmap.world_to_map(pose[:2]),costmap.world_to_map(target)
        if start is None or goal is None or costmap.costs[goal[1],goal[0]] in (253,254):
            return []
        if start == goal:
            return [list(pose[:2]),list(target)] if costmap.sweep_clear(pose,[*target,pose[2]]) else []
        cells = self.core.plan(costmap.costs,start,goal)
        if not len(cells):
            return []
        centres = costmap.map_to_world(cells)
        if not costmap.sweep_clear(pose,[*centres[0],pose[2]]):
            return []
        return np.vstack([pose[:2],centres,target]).tolist()

    def select_frontier(self, costmap, pose, t):
        # Original explore_lite centroid goal, unchanged progress/blacklist lifecycle.
        for f in self.core.frontiers(costmap.raw,costmap.origin,costmap.resolution,pose[:2]):
            centre = f[:2]
            if self.blocked(centre,costmap.resolution):
                continue
            same = self.frontier is not None and np.linalg.norm(centre-self.frontier) < .01
            if not same or self.best_distance > f[4]:
                self.best_distance,self.last_progress = f[4],t
            if t-self.last_progress > 30.:
                self.blacklist.append(centre.copy())
                self.event(t,'progress_timeout_blacklist',target=centre.tolist())
                self.target = self.frontier = None
                self.reset_action()
                continue
            if same:
                return
            path = self.plan_to(costmap,pose,centre)
            if path:
                self.reset_action()
                self.target,self.path,self.frontier = centre.copy(),path,centre.copy()
                self.heading = 0.  # explore.cpp goal.orientation.w = 1
                self.event(t,'frontier_selected',target=centre.tolist())
                return
            self.blacklist.append(centre.copy())
            self.event(t,'ABORTED_unreachable',target=centre.tolist())
        self.target = self.frontier = None
        self.finished = True
        self.event(t,'exploration_finished_no_frontier')


class UnknownActor(RaytraceActor):
    def __init__(self, condition, static_grid=None, static_goal=None, *, navigation='off'):
        if navigation != OPTION:
            raise ValueError('EXPLICIT_PUBLIC_ROS_V7_REQUIRED')
        super().__init__(condition,static_grid,static_goal,navigation='public_ros_v6')
        self.option,self.navigator = OPTION,UnknownNavigator()
        self.navigator.static_mode = static_goal is not None
        self.footprint_support = set()

    def clear_footprint(self):
        cleared = clear_current_footprint(self.grid,self.latest,self.static_hits,self.odom.pose)
        self.footprint_support.update(cleared)  # diagnostic provenance only
        return cleared

    def receive(self, observation, patches):
        result = super().receive(observation,patches)
        self.clear_footprint()  # upstream updateCosts, after raytrace + marking
        return result

    def make_costmap(self):
        self.clear_footprint()
        self.costmap = from_observed_grid(self.grid,self.odom.pose,self.latest,self.static_hits)
        return self.costmap

    def plan(self):
        if self.navigator.clear_requested:
            self.clear_obstacles()
        pose = np.asarray(self.odom.pose)
        self.make_costmap()
        plan = navigation_output_v7(None,navigation=self.option,navigator=self.navigator,
            costmap=self.costmap,pose=pose,t=self.t,static_goal=self.static_goal)
        if self.last_patches and not self.navigator.phase and not self.navigator.failed:
            target = np.asarray(self.last_patches[-1]['center_odom_m'])
            delta = target-pose[:2]
            point = pose[:2]+.12*delta/max(np.linalg.norm(delta),1e-9)
            path = self.navigator.plan_to(self.costmap,pose,point)
            if path:
                plan = dict(status='goal_reobserve',path_m=path,
                    heading_rad=math.atan2(delta[1],delta[0]),doors=[])
        plan['doors'] = self.doors.update(self.grid,pose)
        self.counts[plan['status']] = self.counts.get(plan['status'],0)+1
        return plan

    def command(self, plan):
        if self.navigator.clear_requested:
            plan = self.plan()
        else:
            self.make_costmap()  # current own pose at each 10Hz control tick
        return self.navigator.command(self.costmap,self.odom.pose,plan,self.t)
