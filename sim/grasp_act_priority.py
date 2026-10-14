"""Serial approach with static reservations in the *observed* beam frame.

No peer trajectory/pose messages. The fixed schedule is blue parks, teal
approaches, blue approaches, joint pick. Only the existing READY/GO/ACK
barrier advances rounds. Reservations are geometry, not measured peer poses.
"""
import math
from sim.grasp_act_visible_route import constraints, free, segment_free
from sim.grasp_act_teacher import STATION_M
from scripts.zone_teacher import plan_path

MODE = 'prioritized_approach_v1'
PARK_Y = -.65
PARK_TOL = .025
# Existing .34 peer clearance + .03 READY tolerance + .007 axial choice.
RESERVED_RADIUS = .17 + .04 + .04


def require_baseline(stability, search, goals, handoff, progress, recovery):
    if (stability, search, goals, handoff, progress, recovery) != (
            'align_relook_v1', 'search_body_scan_v2', 'approach_goal_set_v1',
            'nominal_blocked_handoff_v1', 'approach_progress_v1', 'off'):
        raise ValueError('approach coordination requires the 86367b4b baseline profile; recovery off')


def beam_xy(world, xy):
    x, y, a = world['beam']['pose']; c, s = math.cos(a), math.sin(a)
    return c*(xy[0]-x)+s*(xy[1]-y), -s*(xy[0]-x)+c*(xy[1]-y)


def world_xy(world, xy):
    x, y, a = world['beam']['pose']; c, s = math.cos(a), math.sin(a)
    return x+c*xy[0]-s*xy[1], y+s*xy[0]+c*xy[1]


def reserved_constraints(world, rid, end, folded):
    radius, discs, rects = constraints(world, rid, folded)
    other_x = (.27+STATION_M)*(1 if end == 'teal' else -1)
    discs.append((*world_xy(world, (other_x, 0.)), RESERVED_RADIUS))
    # Separate transit on opposite long sides; final axial grasp is unchanged.
    # This is an extra keepout, never a reduction in a physical margin.
    sign = -1 if end == 'teal' else 1
    rects.append((*world_xy(world, (0., sign*10.)), .27, 10.20, world['beam']['pose'][2]))
    if end == 'teal':
        # Blue's parking READY guarantees y<=-.625. Teal's centre must stay
        # above -.25, leaving >=.375m even at the parking tolerance boundary.
        rects.append((*world_xy(world, (0., -20.)), 40., 19.62, world['beam']['pose'][2]))
    return radius, discs, rects


def checked_path(start, goal, bounds, constraint_set):
    radius, discs, rects = constraint_set
    x0, x1, y0, y1 = bounds
    if not (x0+radius <= goal[0] <= x1-radius and y0+radius <= goal[1] <= y1-radius):return []
    if not free(goal, discs, rects, radius):return []
    path = ([tuple(start), tuple(goal)] if segment_free(start, goal, discs, rects, radius)
            else plan_path(start, goal, bounds, discs, rects=rects, radius=radius))
    if not path:return []
    points = [tuple(start), *path, tuple(goal)]
    # Retain exact endpoints in both the runtime path and its static proof.
    points = [p for i,p in enumerate(points) if i==0 or p!=points[i-1]]
    return points if all(segment_free(a,b,discs,rects,radius) for a,b in zip(points,points[1:])) else []


class PriorityApproach:
    def __init__(self, end):
        self.end = end; self.round = 0; self.park_x = None
        self.path = []; self.next_plan = 0.; self.blocked_since = None
        self.events = []

    @property
    def waiting(self):
        return self.round == 0 or (self.round == 1 and self.end == 'blue')

    def park_goal(self, world, rid):
        if self.park_x is None:self.park_x = beam_xy(world, world['robots'][rid]['pose'])[0]
        return world_xy(world, (self.park_x, PARK_Y))

    def signal(self, teacher, world):
        if (teacher.outcome is not None or not teacher.folded_ready or world['beam'] is None
                or world['visibility'][teacher.rid]['visible_probes'] < 5):return False
        if self.round == 0 and self.end == 'teal':return True
        pose = world['robots'][teacher.rid]['pose']
        radius, discs, rects = constraints(world, teacher.rid, teacher.folded_ready)
        return (self.park_x is not None and math.dist(pose[:2], self.park_goal(world, teacher.rid)) <= PARK_TOL
                and free(pose[:2], discs, rects, radius))

    def advance(self, teacher, now):
        self.round += 1
        self.events.append({'t':now, 'event':'GO_ACK_received', 'round':self.round})
        teacher.path=[];teacher.path_goal=None;teacher.next_plan=now;teacher.progress.reset()
        teacher.approach_plan_valid=False

    def step_wait(self, teacher, world, now):
        """Called after own arm/gaze update, with a currently visible band."""
        if self.end == 'teal' or self.round == 1:return teacher._hold(now), False
        goal = self.park_goal(world, teacher.rid)
        pose = world['robots'][teacher.rid]['pose']
        cs = constraints(world, teacher.rid, teacher.folded_ready)
        if self.signal(teacher, world):return teacher._hold(now), False
        from sim.grasp_act_visible_route import waypoint, drive
        if now >= self.next_plan:
            self.path = checked_path(pose[:2], goal, teacher.bounds, cs)
            self.next_plan = now+1.;teacher.planner_calls+=1
            self.events.append({'t':now,'event':'parking_route','goal':goal,'path':self.path})
            self.blocked_since = None if self.path else (now if self.blocked_since is None else self.blocked_since)
        if self.blocked_since is not None and now-self.blocked_since >= 3.-1e-8:
            teacher.outcome='approach_blocked_handoff';return teacher._hold(now),False
        radius, discs, rects = cs
        target = waypoint(pose[:2], self.path, discs, rects, radius)
        if target is None:return teacher._hold(now),False
        return teacher._continuous(now, **drive(pose, goal, target, world['beam']['ends'][self.end])),False
