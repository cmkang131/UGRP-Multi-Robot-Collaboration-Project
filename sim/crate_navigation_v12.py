"""Opt-in crate wall footprint and denser antipodal stance search; no simulator.

Walls use the authored chassis + wheel envelope (185 x 162 mm), with 5 mm
padding. Cargo/peer discs keep their original margins. Paths are checked at
actual orientation; an A* proposal alone never grants an executable pulse.
"""
import math
from harness.static_keepouts import pose_clear, swept_clear
from sim.grasp_act_visible_route import constraints, free, segment_free
from scripts.zone_teacher import plan_path

WALL_MODE = 'crate_footprint_v1'
STANCE_MODE = 'crate_stances_v1'
PAD_M = .005
HALF_X, HALF_Y = .185/2, .162/2
FOOTPRINT = [(-HALF_X,-HALF_Y),(HALF_X,-HALF_Y),(HALF_X,HALF_Y),(-HALF_X,HALF_Y)]
# Wider than the previous surviving 0/+/-15; the SAME aperture, finger/body,
# descent IK and load gates still reject every invalid candidate.
ANGLES_DEG = (0,-5,5,-10,10,-15,15,-17.5,17.5,-20,20,-25,25,-30,30,-45,45,-60,60,-75,75,-89,89)
DISTANCES_M = (.180,.184,.188,.192,.1962,.200,.204,.208,.212,.216,.220)


class WallFootprint:
    def __init__(self, world, rid, folded, profile, bounds):
        self.radius, self.discs, _ = constraints(world, rid, folded, profile)
        self.rects = list(world.get('walls', ()))  # no extra circular inflation
        self.pose = tuple(world['robots'][rid]['pose'])
        self.bounds = bounds

    def free(self, point, yaw):
        return (free(point, self.discs, [], self.radius)
                and pose_clear((*point[:2],yaw), FOOTPRINT, self.rects, bounds=self.bounds, margin=PAD_M))

    def segment(self, a, b, ayaw, byaw):
        return (segment_free(a,b,self.discs,[],self.radius)
                and swept_clear((*a[:2],ayaw),(*b[:2],byaw),FOOTPRINT,self.rects,
                                bounds=self.bounds,margin=PAD_M,step_m=.002,step_rad=math.radians(.5)))

    def path(self, start, goal, heading):
        # The circle planner is a proposal using an inscribed wall radius;
        # it keeps the original cargo/peer clearance by adjusting disc radii.
        if self.segment(start,goal,self.pose[2],heading):return [tuple(start),goal]
        r = min(HALF_X,HALF_Y)+PAD_M
        ds = [type(d)((d[0],d[1],d[2]+self.radius-r)) if isinstance(d,tuple) else
              (d[0],d[1],d[2]+self.radius-r) for d in self.discs]
        path = plan_path(start,goal,self.bounds,ds,rects=self.rects,radius=r)
        if not path:return None
        pts = [tuple(start),*path,tuple(goal)]
        yaws = [self.pose[2]]+[heading]*(len(pts)-1)
        if not all(self.segment(a,b,ya,yb) for a,b,ya,yb in zip(pts,pts[1:],yaws,yaws[1:])):return None
        return pts

    def waypoint(self, start, path, target):
        if not path:return None
        nearest = min(range(len(path)),key=lambda i:math.dist(start,path[i]))
        best = None
        for p in path[nearest:]:
            dist = math.dist(start,p)
            if dist < .001:continue
            yaw = math.atan2(target[1]-p[1],target[0]-p[0])
            if self.segment(start,p,self.pose[2],yaw):
                best=p
                if dist >= .12:break
            elif best is not None:break
        return best


def stance_grasp_valid(world,rid,end,pose):
    from sim.crate_antipodal import visible_grasp
    from sim.grasp_act_teacher import local
    if not visible_grasp(world,rid,end,pose=pose)['valid']:return False
    p=world['beam']['ends'][end]
    x,y=local(pose,p)
    return lift_reachable(round(x,7),round(y,7),round(p[2],7))


from functools import lru_cache
@lru_cache(maxsize=1024)
def lift_reachable(x,y,z):
    from harness.visual_arm_v3 import solve_grip_site_ik
    from sim.crate_cartesian_lift import plan_lift
    try:return plan_lift({1:1500,**solve_grip_site_ik((x,y,z))})[0] is not None
    except ValueError:return False
