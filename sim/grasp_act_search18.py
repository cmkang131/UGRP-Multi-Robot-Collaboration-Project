"""Opt-in search18 planning from visible geometry and issued commands only.

Footprint checks follow oriented costmap footprints; the start connector is
continuous (not a cleared grid cell). This is a teacher diagnostic, not ACT.
"""
import heapq
import math
from functools import lru_cache

from harness.static_keepouts import rect_distance
from sim.grasp_act_visible_route import free, segment_free, waypoint
from scripts.zone_teacher import plan_path
from sim.masterpi_geometry_v3 import PHYSICAL_V3, CHASSIS_LENGTH_M

MODES = {'search18_footprint': 'search18_footprint_v1',
         'search18_start_plan': 'search18_start_plan_v1',
         'search18_free_space': 'search18_free_space_v1'}
REQUIRED_MARGIN_M = .065  # search17 corrected command odometry p90; never reduced to fit a scene
MARGIN_M = REQUIRED_MARGIN_M  # offline sweeps may lower this module value; no CLI/toggle does
ANALYSIS_OVERRIDE = False  # set only by scripts/replay_grasp_act_search18.py margin sweeps
# Wheel envelope is 183.8 x 159.9 mm. The 185 mm chassis extends 0.6 mm
# beyond its longitudinal half extent, so the enclosing footprint is 185 x 159.9.
HALF_X = max(CHASSIS_LENGTH_M/2, PHYSICAL_V3.wheelbase_m/2 + PHYSICAL_V3.wheel_radius_m)
HALF_Y = (PHYSICAL_V3.track_m + PHYSICAL_V3.wheel_width_m)/2


def corners(rect):
    x,y,hx,hy,a=rect; c,s=math.cos(a),math.sin(a)
    return [(x+c*u-s*v,y+s*u+c*v) for u,v in ((-hx,-hy),(hx,-hy),(hx,hy),(-hx,hy))]


def rectangles_overlap(a,b):
    """Separating-axis test includes containment and crossing edges."""
    aa,bb=corners(a),corners(b)
    for angle in (a[4],a[4]+math.pi/2,b[4],b[4]+math.pi/2):
        c,s=math.cos(angle),math.sin(angle)
        p=[x*c+y*s for x,y in aa];q=[x*c+y*s for x,y in bb]
        if max(p)<min(q) or max(q)<min(p):return False
    return True


def _rect_distance_to_rect(a,b):
    """Exact Euclidean gap between two oriented rectangles (0 when they touch)."""
    if rectangles_overlap(a,b):return 0.
    return min(min(rect_distance(c,b) for c in corners(a)),min(rect_distance(c,a) for c in corners(b)))


BODY_RADIUS_M = math.hypot(HALF_X, HALF_Y)


def body_clearance(pose,discs,rects,*,bounds=None,need=math.inf):
    """Smallest gap between the real 185x160 mm body and anything it must avoid.

    Exact Minkowski distance, so the position-uncertainty margin is a true
    Euclidean envelope (rounded corners), not a larger sharp-cornered box.
    Obstacles whose bounding circles are already farther than ``need`` are
    skipped; the returned value is then only a lower bound of ``need``.
    """
    box=(*pose[:2],HALF_X,HALF_Y,pose[2]);gap=math.inf
    if bounds is not None:
        x0,x1,y0,y1=bounds
        gap=min(min(x-x0,x1-x,y-y0,y1-y) for x,y in corners(box))
    for d in discs:
        if math.dist(pose[:2],d[:2])-d[2]-BODY_RADIUS_M>=need:continue
        gap=min(gap,rect_distance(d[:2],box)-d[2])
    for r in rects:
        if math.dist(pose[:2],r[:2])-math.hypot(r[2],r[3])-BODY_RADIUS_M>=need:continue
        gap=min(gap,_rect_distance_to_rect(box,r))
    return gap


def body_free(pose,discs,rects,*,margin=None,bounds=None):
    """True when the body keeps at least the uncertainty margin everywhere."""
    margin=MARGIN_M if margin is None else margin
    if margin<MARGIN_M:raise ValueError('search18 requires at least 65mm margin')
    return body_clearance(pose,discs,rects,bounds=bounds,need=margin)>=margin


def exact_start_path(start,goal,bounds,point_free,edge_free,*,grid=.05,budget=40000):
    """A* with a virtual actual-start node and checked connectors to 9 cells.

    Never clear an obstacle, accept an unchecked terminal edge, or use the
    snapped cell as the start. This is not an implementation of Theta*.
    """
    start,goal=tuple(start),tuple(goal)
    if not point_free(goal):return None
    if edge_free(start,goal):return [start,goal]
    x0,x1,y0,y1=bounds
    def point(k):return (x0+k[0]*grid,y0+k[1]*grid)
    @lru_cache(maxsize=None)
    def allowed(k):
        p=point(k)
        return x0<=p[0]<=x1 and y0<=p[1]<=y1 and point_free(p)
    cell=(round((start[0]-x0)/grid),round((start[1]-y0)/grid))
    queue=[];cost={};parent={};closed=set()
    for i in (-1,0,1):
        for j in (-1,0,1):
            k=(cell[0]+i,cell[1]+j);p=point(k)
            if allowed(k) and edge_free(start,p):
                g=math.dist(start,p);cost[k]=g;parent[k]=None
                heapq.heappush(queue,(g+math.dist(p,goal),g,k))
    while queue and len(closed)<budget:
        _,g,k=heapq.heappop(queue)
        if k in closed or g!=cost[k]:continue
        closed.add(k);p=point(k)
        if math.dist(p,goal)<=grid*1.5 and edge_free(p,goal):
            path=[goal,p]
            while parent[k] is not None:
                k=parent[k];path.append(point(k))
            return [start,*reversed(path)]
        for i,j in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
            n=(k[0]+i,k[1]+j);q=point(n);ng=g+grid*math.hypot(i,j)
            if n in closed or ng>=cost.get(n,math.inf) or not allowed(n):continue
            if not edge_free(p,q):continue
            cost[n]=ng;parent[n]=k;heapq.heappush(queue,(ng+math.dist(q,goal),ng,n))
    return None


class Navigation:
    def __init__(self,world,rid,end,pwm,bounds,*,rectangle=False,true_start=False):
        self.world=world;self.rid=rid;self.end=end;self.pwm=dict(pwm);self.bounds=bounds
        self.rectangle=rectangle;self.true_start=true_start
        self.pose=world['robots'][rid]['pose']
        self.target=world['beam']['ends'][end] if world['beam'] is not None else None
        self.discs=[];self.rects=world.get('walls',[])
        if rectangle:
            self.discs=[(*v['pose'][:2],.17) for r,v in world['robots'].items() if r!=rid]
            self.discs += [(*o['xy'],o['radius']+.005) for k,o in world['objects'].items() if k!='beam_1']
            if world['beam'] is not None:
                x,y,a=world['beam']['pose']
                self.discs += [(x+d*math.cos(a),y+d*math.sin(a),.02) for d in (-.27,-.135,0.,.135,.27)]

    def heading(self,p):
        return self.pose[2] if self.target is None else math.atan2(self.target[1]-p[1],self.target[0]-p[0])

    def free(self,p,discs,rects,radius,*,heading=None):
        if not self.rectangle:return free(p,discs,rects,radius)
        yaw=self.heading(p) if heading is None else heading
        return body_free((*p[:2],yaw),self.discs,self.rects,bounds=self.bounds)

    def pose_segment(self,a,b):
        """Check translation and rotation; sampling pad bounds between samples."""
        da=math.atan2(math.sin(b[2]-a[2]),math.cos(b[2]-a[2]))
        n=max(1,math.ceil(math.dist(a[:2],b[:2])/.002),math.ceil(abs(da)/math.radians(.5)))
        # Max displacement of any footprint point between samples is < 2mm.
        return all(body_free((a[0]+(b[0]-a[0])*i/n,a[1]+(b[1]-a[1])*i/n,a[2]+da*i/n),
                             self.discs,self.rects,margin=MARGIN_M+.002,bounds=self.bounds)
                   for i in range(n+1))

    def segment_free(self,a,b,discs,rects,radius):
        if not self.rectangle:
            if self.true_start:
                from sim.grasp_act_search17 import segment_free as strict_segment
                return strict_segment(a,b,discs,rects,radius)
            return segment_free(a,b,discs,rects,radius)
        yaw=self.pose[2] if math.dist(a,self.pose[:2])<1e-8 else self.heading(a)
        return self.pose_segment((*a,yaw),(*b,self.heading(b)))

    def waypoint(self,start,path,discs,rects,radius):
        if not self.rectangle and not self.true_start:return waypoint(start,path,discs,rects,radius)
        if not path:return None
        closest=min(range(len(path)),key=lambda i:math.dist(start,path[i]));best=None
        for p in path[closest:]:
            if math.dist(start,p)<.001:continue
            if self.segment_free(start,p,discs,rects,radius):
                best=p
                if math.dist(start,p)>=.12:break
            elif best is not None:break
        return best

    def plan_path(self,start,goal,bounds,discs,*,rects=(),radius=.13):
        if not self.rectangle and not self.true_start:
            return plan_path(start,goal,bounds,discs,rects=rects,radius=radius)
        return exact_start_path(start,goal,bounds,
            lambda p:self.free(p,discs,rects,radius),
            lambda a,b:self.segment_free(a,b,discs,rects,radius))

    def retained_path(self,start,path,goal,discs,rects,radius):
        """Revalidate goal, all remaining edges, and actual-pose connector."""
        if not path or goal is None or math.dist(path[-1],goal)>.001:return None
        if not self.free(goal,discs,rects,radius):return None
        nearest=min(range(len(path)),key=lambda i:math.dist(start,path[i]))
        for i in range(nearest,len(path)):
            remaining=[tuple(start),*path[i:]]
            if all(self.segment_free(a,b,discs,rects,radius) for a,b in zip(remaining,remaining[1:])):
                return remaining
        return None


def navigation(teacher,world):
    m=teacher.search15_modes
    if MARGIN_M!=REQUIRED_MARGIN_M and not ANALYSIS_OVERRIDE:raise ValueError('search18 margin changed outside offline analysis')
    return Navigation(world,teacher.rid,teacher.end,teacher.sink.pwm,teacher.bounds,
        rectangle=m['search18_footprint']!='off',true_start=m['search18_start_plan']!='off')


def checked_pulse(teacher,world,value,before):
    from harness.grasp_act_visible_world import command_delta
    from sim.grasp_act_pregrasp import issued_sweep_reason
    nav=teacher._navigation(world);pose=tuple(nav.pose)
    times=sorted({0.,.1,*(max(0.,min(.1,d)) for d in value['duration_s'])})
    for t0,t1 in zip(times,times[1:]):
        a=command_delta(value,t0,mode=teacher.search15_modes['search17_odometry'])
        b=command_delta(value,t1,mode=teacher.search15_modes['search17_odometry'])
        dx,dy,da=(y-x for x,y in zip(a,b));c,s=math.cos(pose[2]),math.sin(pose[2])
        si=math.sin(da)/da if abs(da)>1e-10 else 1.
        co=(1-math.cos(da))/da if abs(da)>1e-10 else 0.
        x,y=si*dx-co*dy,co*dx+si*dy
        end=(pose[0]+c*x-s*y,pose[1]+s*x+c*y,pose[2]+da)
        if any(value['wheels']) and not nav.pose_segment(pose,end):return 'body_uncertainty_envelope'
        # Preserve the authored arm/camera/finger check. The rectangle is not
        # assumed to contain an unfolded arm. Floor and intentional pick contact
        # retain their existing semantics; this guard runs before pick only.
        pa={k:before[k]+t0/.1*(teacher.sink.pwm[k]-before[k]) for k in before}
        pb={k:before[k]+t1/.1*(teacher.sink.pwm[k]-before[k]) for k in before}
        if any(value['wheels']) or pa!=pb:
            reason=issued_sweep_reason(world,teacher.rid,pose,pa,pb,(dx,dy,da))
            if reason:return reason
        pose=end
    return None
