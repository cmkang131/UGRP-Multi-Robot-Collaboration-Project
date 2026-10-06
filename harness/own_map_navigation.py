"""Default-off B/C/E modules. Only robot-private observed grids enter this API.

No map file, world bounds, goal location, simulator, peer map or pose truth loader.
See experiments/2026-10-07-mapfree-explore/README.md for evidence and limitations.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
import heapq
import math

import cv2
import numpy as np
from scipy.ndimage import binary_dilation, distance_transform_edt, label

from harness.self_odom_grid import transform


@dataclass(frozen=True)
class NavigationOptions:
    exploration: str = 'off'
    door_detection: str = 'off'
    partial_planning: str = 'off'
    resolution_m: float = .1
    range_m: float = 4.
    fov_deg: float = 54.5
    gain_weight: float = 1.
    travel_weight: float = .35
    repeat_weight: float = .75
    pose_margin_m: float = .02

    def __post_init__(self):
        for field, allowed in [('exploration', ('off','own_frontier_v1')),
                               ('door_detection', ('off','own_gap_v1')),
                               ('partial_planning', ('off','own_astar_v1'))]:
            if getattr(self, field) not in allowed:
                raise ValueError('UNKNOWN_NAVIGATION_OPTION: '+field)
        for k in ('resolution_m','range_m','fov_deg','gain_weight','travel_weight','repeat_weight','pose_margin_m'):
            v = getattr(self,k)
            if not math.isfinite(v) or v <= 0:
                raise ValueError('INVALID_NAVIGATION_OPTION: '+k)
        if self.exploration != 'off' and self.partial_planning == 'off':
            raise ValueError('FRONTIER_REQUIRES_OWN_ASTAR')

    @property
    def enabled(self):
        return any(getattr(self,k) != 'off' for k in ('exploration','door_detection','partial_planning'))


@dataclass(frozen=True)
class Footprint:
    half_length_m: float = .12
    half_width_m: float = .10

    def __post_init__(self):
        if not all(math.isfinite(v) and v > 0 for v in (self.half_length_m,self.half_width_m)):
            raise ValueError('INVALID_FOOTPRINT')

    @property
    def radius(self):
        return math.hypot(self.half_length_m,self.half_width_m)

    def cross_width(self, tangent, yaw):
        long = np.array([math.cos(yaw),math.sin(yaw)])
        side = np.array([-long[1],long[0]])
        return 2*(abs(np.dot(tangent,long))*self.half_length_m+
                  abs(np.dot(tangent,side))*self.half_width_m)


PAIR_FOOTPRINT = Footprint(.625,.20)  # pair_passage_plan.PAIR_ENVELOPE


class ObservedGrid:
    """Sparse, unbounded own frame. Free has separate observed-floor provenance.

    A wall endpoint never clears a ray. Duplicate observations cannot increase belief.
    Initial body support is distinct from observation and never counted as coverage.
    """
    def __init__(self, robot_id, resolution_m=.1):
        self.robot_id, self.resolution = robot_id, resolution_m
        self.odds, self.floor_frames, self.wall_frames = {}, {}, {}
        self.seen, self.revision = set(), 0
        self.view_poses = {}
        self.support = set()

    def cell(self, xy):
        return tuple(np.floor(np.asarray(xy)/self.resolution).astype(int))

    def point(self, cell):
        return (np.asarray(cell)+.5)*self.resolution

    def initial_support(self, footprint=Footprint()):
        n = math.ceil(footprint.radius/self.resolution)
        for x in range(-n,n+1):
            for y in range(-n,n+1):
                if np.linalg.norm(self.point((x,y))) <= footprint.radius+self.resolution*.71:
                    self.support.add((x,y))

    def observe(self, *, robot_id, frame_id, pose, floor_xy=(), wall_xy=(), floor_source='floor_visible'):
        if robot_id != self.robot_id:
            raise ValueError('NAV_PEER_INPUT_FORBIDDEN')
        if frame_id in self.seen:
            raise ValueError('NAV_DUPLICATE_FRAME')
        if floor_source != 'floor_visible':
            raise ValueError('NAV_FREE_REQUIRES_OBSERVED_FLOOR')
        pose = np.asarray(pose,float)
        if pose.shape != (3,) or not np.isfinite(pose).all():
            raise ValueError('NAV_INVALID_POSE')
        groups = []
        for points in (floor_xy,wall_xy):
            p = np.asarray(points,float).reshape(-1,2)
            if not np.isfinite(p).all():
                raise ValueError('NAV_INVALID_OBSERVATION')
            groups.append({self.cell(v) for v in transform(p,pose)})
        free, hit = groups
        for cells, delta, provenance in ((free-hit,math.log(.3/.7),self.floor_frames),
                                         (hit,math.log(.7/.3),self.wall_frames)):
            for c in cells:
                self.odds[c] = float(np.clip(self.odds.get(c,0.)+delta,-4.,4.))
                provenance.setdefault(c,set()).add(frame_id)
        self.seen.add(frame_id)
        self.view_poses[frame_id] = pose.copy()
        self.revision += 1

    def state(self, cell):
        value = self.odds.get(cell,0.)
        if value > 0:
            return 1
        if (value < 0 and cell in self.floor_frames) or cell in self.support:
            return -1
        return 0

    def dense(self, pose=(0,0,0), pad_m=.5):
        cells = list(self.odds)+list(self.support)+[self.cell(pose[:2])]
        xy = np.array(cells)
        pad = math.ceil(pad_m/self.resolution)
        lo, hi = xy.min(0)-pad,xy.max(0)+pad+1
        if np.prod(hi-lo) > 1_000_000:
            raise ValueError('NAV_GRID_RESOURCE_LIMIT')
        a = np.zeros(tuple((hi-lo)[::-1]),np.int8)
        for c in set(cells):
            x,y = np.array(c)-lo
            a[y,x] = self.state(c)
        return a,lo


MOVES = ((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1))


def footprint_clearance(grid, footprint, margin, yaw=None):
    """Minkowski sum with unknown/occupied; full cell extent conservatively included.

    yaw=None encloses every rotated pose (safe sweep); fixed yaw uses a box envelope.
    """
    state, lo = grid.dense()
    r = grid.resolution
    radius = footprint.radius+margin
    n = math.ceil(radius/r+.71)
    ys,xs = np.mgrid[-n:n+1,-n:n+1]*r
    if yaw is None:
        kernel = xs*xs+ys*ys <= (radius+r*.71)**2
    else:
        c,s = math.cos(yaw),math.sin(yaw)
        kernel = ((abs(c*xs+s*ys) <= footprint.half_length_m+margin+r*.71) &
                  (abs(-s*xs+c*ys) <= footprint.half_width_m+margin+r*.71))
    blocked = binary_dilation(state != -1,structure=kernel,border_value=1)
    return state, ~blocked, distance_transform_edt(state == -1)*r, lo


def astar(clear, start, target, resolution=.1, clearance=None):
    h,w = clear.shape
    def valid(c):
        return 0 <= c[0] < w and 0 <= c[1] < h and clear[c[1],c[0]]
    start,target = tuple(start),tuple(target)
    if not valid(start) or not valid(target):
        return None
    todo,cost,parent = [(0.,start)],{start:0.},{}
    while todo:
        _,cur = heapq.heappop(todo)
        if cur == target:
            out = [cur]
            while out[-1] != start:
                out.append(parent[out[-1]])
            return out[::-1]
        for dx,dy in MOVES:
            nxt = cur[0]+dx,cur[1]+dy
            if not valid(nxt) or (dx and dy and (not valid((cur[0]+dx,cur[1])) or not valid((cur[0],cur[1]+dy)))):
                continue
            extra = 0. if clearance is None else .15*math.exp(-clearance[nxt[1],nxt[0]]/.2)
            new = cost[cur]+math.hypot(dx,dy)*resolution*(1+extra)
            if new < cost.get(nxt,math.inf):
                cost[nxt],parent[nxt] = new,cur
                heapq.heappush(todo,(new+math.dist(nxt,target)*resolution,nxt))
    return None


def reachable(clear,start):
    x,y = start
    if not (0 <= y < clear.shape[0] and 0 <= x < clear.shape[1]) or not clear[y,x]:
        return np.zeros_like(clear)
    labels,_ = label(clear)  # 4 connectivity also rules out diagonal corner cuts
    return labels == labels[y,x]


def visible_unknown(grid, point, yaw, fov_deg, range_m):
    """Occlusion-aware area proxy, not Shannon information. Unknown never traversable."""
    cells = set()
    for a in np.linspace(yaw-math.radians(fov_deg)/2,yaw+math.radians(fov_deg)/2,25):
        direction = np.array([math.cos(a),math.sin(a)])
        for distance in np.arange(grid.resolution,range_m,grid.resolution):
            cell = grid.cell(np.asarray(point)+distance*direction)
            state = grid.state(cell)
            if state == 1:
                break
            if state == 0:
                cells.add(cell)
    return len(cells)*grid.resolution**2


def frontier_candidates(grid, pose, options, footprint=Footprint(), recent=()):
    state,clear,dist,lo = footprint_clearance(grid,footprint,options.pose_margin_m)
    start = np.asarray(grid.cell(pose[:2]))-lo
    reach = reachable(clear,tuple(start))
    # Actual frontier lies on raw free/unknown edge; viewpoint lies in eroded reachable free.
    edge = (state == -1) & binary_dilation(state == 0)
    clusters,n = label(edge,structure=np.ones((3,3)))
    ys,xs = np.nonzero(reach)
    if not len(xs):
        return []
    allowed = np.stack([xs,ys],axis=1)
    result = []
    for i in range(1,n+1):
        fy,fx = np.nonzero(clusters == i)
        # Spatially spread representative frontiers, no minimum-size deletion of narrow gaps.
        samples = np.stack([fx,fy],axis=1)[::max(1,len(fx)//4)]
        used = set()
        for target in samples:
            near = np.sum((allowed-target)**2,axis=1)
            idx = int(np.argmin(near))
            v = tuple(allowed[idx])
            if v in used:
                continue
            used.add(v)
            path = astar(clear,tuple(start),v,grid.resolution,dist)
            if path is None:
                continue
            xy = grid.point(np.array(v)+lo)
            towards = (target-np.array(v))*grid.resolution
            heading = math.atan2(towards[1],towards[0]) if np.linalg.norm(towards) else pose[2]
            gain = visible_unknown(grid,xy,heading,options.fov_deg,options.range_m)
            travel = sum(math.dist(a,b)*grid.resolution for a,b in zip(path,path[1:]))
            repeat = sum(math.dist(xy,p[:2]) < .3 and abs(wrap(heading-p[2])) < .5 for p in recent[-12:])
            score = options.gain_weight*gain-options.travel_weight*travel-options.repeat_weight*repeat
            result.append({'target_m':xy.tolist(),'heading_rad':heading,'gain_area_m2':gain,
                           'travel_m':travel,'score':score,'cluster_cells':len(fx),
                           'path_m':[grid.point(np.array(c)+lo).tolist() for c in path]})
    return sorted(result,key=lambda x:(-x['score'],x['travel_m'],x['target_m'],x['heading_rad']))


def wrap(x):
    return (x+math.pi)%(2*math.pi)-math.pi


class DoorMemory:
    """Observed collinear wall gaps. Candidate IDs are private and carry reasons."""
    def __init__(self,robot_id):
        self.robot_id,self.tracks = robot_id,[]

    def update(self,grid,pose,footprint=Footprint(),margin=.02):
        state,lo = grid.dense(pose)
        lines = cv2.HoughLinesP((state == 1).astype(np.uint8)*255,1,np.pi/180,3,
                               minLineLength=2,maxLineGap=1)
        candidates = []
        if lines is None:
            return []
        lines = np.asarray(lines).reshape(-1,2,2)  # OpenCV 4: Nx1x4; 5: Nx4
        for i,a in enumerate(lines):
            va = a[1]-a[0]
            va = va/np.linalg.norm(va)
            for b in lines[i+1:]:
                vb = b[1]-b[0]
                vb = vb/np.linalg.norm(vb)
                if abs(np.dot(va,vb)) < math.cos(math.radians(10)):
                    continue
                normal = np.array([-va[1],va[0]])
                if max(abs((b-a[0])@normal))*grid.resolution > .15:
                    continue
                aa,bb = sorted(a@va),sorted(b@va)
                if aa[1] < bb[0]:
                    left,right = a[np.argmax(a@va)],b[np.argmin(b@va)]
                elif bb[1] < aa[0]:
                    left,right = b[np.argmax(b@va)],a[np.argmin(a@va)]
                else:
                    continue
                gap = math.dist(left,right)*grid.resolution-grid.resolution
                if not .25 <= gap <= 1.5:
                    continue
                center = grid.point((left+right)/2+lo)
                if any(np.linalg.norm(center-np.array(c['center_m'])) < .2 for c in candidates):
                    continue
                width_lower = max(0.,gap-2*grid.resolution)
                jambs = [tuple(np.asarray(p,int)+lo) for p in (left,right)]
                def jamb_frames(p):
                    return set().union(*(grid.wall_frames.get((p[0]+dx,p[1]+dy),set())
                                         for dx in (-1,0,1) for dy in (-1,0,1)))
                def distinct_views(frames):
                    poses = [grid.view_poses[f] for f in frames if f in grid.view_poses]
                    return any(np.linalg.norm(a[:2]-b[:2])>=.05 or abs(wrap(a[2]-b[2]))>=math.radians(5)
                               for i,a in enumerate(poses) for b in poses[i+1:])
                corroborated = all(distinct_views(jamb_frames(p)) for p in jambs)
                required = footprint.cross_width(va,pose[2])+2*margin
                points = [center+normal*t+va*u for t in np.arange(-.4,.401,.05)
                          for u in np.arange(-required/2,required/2+.025,.05)]
                # Explicit observed-floor requirement: initial support does not count.
                connected = all(grid.state(grid.cell(p)) == -1 and grid.cell(p) in grid.floor_frames for p in points)
                reason = ('jamb_reobserve' if not corroborated else 'free_connection_unknown' if not connected
                          else 'footprint_too_wide' if width_lower < required else 'clearance_feasible')
                matches = [t for t in self.tracks if np.linalg.norm(center-np.array(t['center_m'])) < .25]
                tid = matches[0]['id'] if matches else f'{self.robot_id}:opening_{len(self.tracks)+1:03d}'
                row = dict(id=tid,center_m=center.tolist(),tangent=va.tolist(),width_m=gap,
                           width_lower_m=width_lower,required_width_m=required,reason=reason,
                           candidate_opening=True,free_connection_observed=connected,
                           payload_clearance_feasible=reason=='clearance_feasible',
                           visually_confirmed_passage=False,revision=grid.revision)
                if matches:
                    self.tracks[self.tracks.index(matches[0])] = row
                else:
                    self.tracks.append(row)
                candidates.append(row)
        return candidates


class OwnMapNavigator:
    def __init__(self,robot_id,options=None):
        self.robot_id,self.options = robot_id,options or NavigationOptions()
        self.doors,self.recent = DoorMemory(robot_id),[]
        self.last_revision = -1
        self.look_steps = 0

    def update(self,legacy_output,*,grid=None,pose=(0.,0.,0.),goal=None,footprint=Footprint(),carrying=False):
        """Explicit integration seam; off returns the very same legacy object/bytes.

        goal is a private floor-goal memory snapshot, never an authored B coordinate.
        Door-only mode annotates but does not issue movement. No static fallback on.
        """
        o = self.options
        if not o.enabled:
            return legacy_output
        if grid is None or grid.robot_id != self.robot_id:
            raise ValueError('NAV_REQUIRES_OWN_GRID')
        out = {'coordinate_frame':f'{self.robot_id}/own_odom','revision':grid.revision,
               'status':'observation_required','path_m':[],'doors':[]}
        if o.door_detection != 'off':
            out['doors'] = self.doors.update(grid,pose,footprint,o.pose_margin_m)
        if o.partial_planning == 'off':
            return out
        if carrying and o.exploration != 'off':
            return {**out,'status':'shared_carry_action_required'}
        if goal and goal.get('robot_id') != self.robot_id:
            raise ValueError('NAV_PEER_GOAL_FORBIDDEN')
        candidates = []
        if goal:
            candidates = [c for c in goal.get('candidates',[]) if c.get('state')=='locally_confirmed_region']
        if candidates:
            state,clear,dist,lo = footprint_clearance(grid,footprint,o.pose_margin_m)
            start = tuple(np.asarray(grid.cell(pose[:2]))-lo)
            target = np.asarray(candidates[0]['center_m'])
            yy,xx = np.nonzero(reachable(clear,start))
            if len(xx):
                pts = (np.stack([xx,yy],1)+lo+.5)*grid.resolution
                i = int(np.argmin(np.linalg.norm(pts-target,axis=1)))
                path = astar(clear,start,(xx[i],yy[i]),grid.resolution,dist)
                if path:
                    return {**out,'status':'goal_approach','path_m':[grid.point(np.array(c)+lo).tolist() for c in path]}
        # A directly seen B patch requests a translated re-observation, not a GT waypoint.
        if goal and o.exploration != 'off':
            seen = [c for c in goal.get('candidates',[]) if c.get('state')=='visually_seen']
            if seen:
                target = np.asarray(seen[-1]['center_m'])
                state,clear,dist,lo = footprint_clearance(grid,footprint,o.pose_margin_m)
                start = tuple(np.asarray(grid.cell(pose[:2]))-lo)
                yy,xx = np.nonzero(reachable(clear,start))
                if len(xx):
                    pts = (np.stack([xx,yy],1)+lo+.5)*grid.resolution
                    distance = np.linalg.norm(pts-np.asarray(pose[:2]),axis=1)
                    admissible = (distance >= .07)&(distance <= .25)
                    if admissible.any():
                        score = np.where(admissible,np.linalg.norm(pts-target,axis=1),np.inf)
                        i = int(np.argmin(score))
                        path = astar(clear,start,(xx[i],yy[i]),grid.resolution,dist)
                        if path:
                            delta = target-np.asarray(pose[:2])
                            return {**out,'status':'goal_reobserve','heading_rad':math.atan2(delta[1],delta[0]),
                                    'path_m':[grid.point(np.array(c)+lo).tolist() for c in path]}
        if o.exploration != 'off':
            ranked = frontier_candidates(grid,pose,o,footprint,self.recent)
            if ranked:
                best = ranked[0]
                self.recent.append((*best['target_m'],best['heading_rad']))
                return {**out,**best,'status':'frontier','candidate_count':len(ranked)}
        self.look_steps += 1
        return {**out,'status':'search_exhausted' if self.look_steps >= 24 else 'observation_required',
                'heading_rad':wrap(pose[2]+math.radians(25))}
