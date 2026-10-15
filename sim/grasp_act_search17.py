"""Opt-in visible-teacher recovery geometry; no simulator state or execution.

NavFn clears an occupied start cell. Here we retain every obstacle and choose
the nearest reachable free cell with nondecreasing clearance instead.
"""
import math
from harness.static_keepouts import rect_distance
from sim.grasp_act_visible_route import free

MODES = {'search17_candidates': 'search17_candidates_v1',
         'search17_escape': 'search17_escape_v1',
         'search17_odometry': 'search17_fixed_v1'}


def segment_free(start, end, discs, rects, radius):
    dx, dy = end[0]-start[0], end[1]-start[1]
    norm = dx*dx+dy*dy
    for x, y, r in discs:
        initial = math.hypot(start[0]-x, start[1]-y)
        dot = (start[0]-x)*dx+(start[1]-y)*dy
        if initial < r+radius and dot < -1e-12:
            return False
        u = max(0., min(1., -dot/max(norm, 1e-12)))
        if math.hypot(start[0]+u*dx-x, start[1]+u*dy-y) < min(initial, r+radius)-1e-10:
            return False
    # Distance to a convex rectangle is convex along a segment. Check its
    # initial directional derivative when already inside the inflated margin;
    # outside it, retain the ordinary full segment check at 1mm resolution.
    n = max(1, math.ceil(math.sqrt(norm)/.001))
    for rect in rects:
        initial = rect_distance(start, rect)
        if initial < radius:
            # Work in the rectangle frame: squared distance derivative to the
            # nearest point must be nonnegative. Reject starts inside the body.
            x,y,hx,hy,a = rect; c,s = math.cos(a),math.sin(a)
            px,py = c*(start[0]-x)+s*(start[1]-y), -s*(start[0]-x)+c*(start[1]-y)
            rx,ry = px-max(-hx,min(hx,px)), py-max(-hy,min(hy,py))
            if initial <= 1e-10 or rx*(c*dx+s*dy)+ry*(-s*dx+c*dy) < -1e-12:
                return False
        if any(rect_distance((start[0]+dx*i/n,start[1]+dy*i/n),rect) < min(initial,radius)-1e-10
               for i in range(n+1)):
            return False
    return True


def nearest_free(start, bounds, discs, rects, radius, *, excluded=()):
    """Nearest 1cm grid cell within 20cm with a checked continuous connector."""
    x0,x1,y0,y1 = bounds
    ix,iy = round(start[0]/.01),round(start[1]/.01)
    points = [((ix+i)*.01,(iy+j)*.01) for i in range(-20,21) for j in range(-20,21)]
    for p in sorted(points,key=lambda p:(math.dist(start,p),p)):
        if math.dist(start,p) > .2 or any(math.dist(p,q)<.005 for q in excluded):continue
        if not (x0+radius<=p[0]<=x1-radius and y0+radius<=p[1]<=y1-radius):continue
        if free(p,discs,rects,radius) and segment_free(start,p,discs,rects,radius):return p
    return None


def pulse_free(pose,value,discs,rects,radius,*,mode='off'):
    """Check each wheel-deadline segment, not only the net pulse endpoint."""
    from harness.grasp_act_visible_world import command_delta
    times=sorted({0.,.1,*(max(0.,min(.1,d)) for d in value['duration_s'])})
    current=tuple(pose)
    for a,b in zip(times,times[1:]):
        before=command_delta(value,a,mode=mode);after=command_delta(value,b,mode=mode)
        dx,dy,da=(y-x for x,y in zip(before,after))
        # Constant body twist for this command phase, exact planar integration.
        si=math.sin(da)/da if abs(da)>1e-10 else 1.
        co=(1-math.cos(da))/da if abs(da)>1e-10 else 0.
        x,y=si*dx-co*dy,co*dx+si*dy
        c,s=math.cos(current[2]),math.sin(current[2])
        end=(current[0]+c*x-s*y,current[1]+s*x+c*y,current[2]+da)
        if not segment_free(current[:2],end[:2],discs,rects,radius):return False
        current=end
    return True


def escape_command(teacher, world, now):
    """Bounded escape before the progress handoff, including actual pulse check."""
    if teacher.search15_modes['search17_escape']=='off' or world['beam'] is None:return None
    pose=world['robots'][teacher.rid]['pose'];radius,discs,rects=teacher._constraints(world)
    state=teacher.search17_escape_state
    if free(pose[:2],discs,rects,radius):
        if state is not None:
            teacher.search17_log.append({'t':now,'event':'escape_clear'})
            teacher.path=[];teacher.path_goal=None;teacher.next_plan=now
            teacher.search17_escape_state=None
        return None
    if state is None:
        state={'start':now,'excluded':[],'point':None,'distance':None,'unchanged':0}
        teacher.search17_escape_state=state
        teacher.search17_log.append({'t':now,'event':'start_in_margin_escape'})
    if now-state['start']>=1.5:return None  # original finite progress debt remains
    excluded=list(state['excluded'])
    c,s=math.cos(pose[2]),math.sin(pose[2])
    for _ in range(12):
        p=nearest_free(pose[:2],teacher.bounds,discs,rects,radius,excluded=excluded)
        if p is None:return None
        distance=math.dist(pose[:2],p);dx,dy=p[0]-pose[0],p[1]-pose[1]
        # Common scale preserves bearing; legacy forward/lateral gains differ.
        speed=min(.05,distance/.3)
        value=teacher._continuous(now,speed*(c*dx+s*dy)/distance,speed*(-s*dx+c*dy)/distance,0.)
        if all(pulse_free(pose,value,discs,rects,radius,mode=mode)
               for mode in ('off',teacher.search15_modes['search17_odometry'])):break
        excluded.append(p)
    else:return None
    distance=math.dist(pose[:2],p)
    state['unchanged']=(state['unchanged']+1 if p==state['point'] and state['distance']-distance<.0001 else 0)
    if state['unchanged']>=3:
        state['excluded'].append(p);state['point']=None
        teacher.search17_log.append({'t':now,'event':'escape_candidate_removed','goal':p})
        return teacher._hold(now)
    state['point']=p;state['distance']=distance
    teacher.search17_log.append({'t':now,'event':'escape_pulse','goal':p})
    return value


def expanded_choices():
    # Denser angles up to the existing physical jaw bound, plus wider tests
    # which remain subject to exactly the same jaw/IK/sweep/visibility checks.
    return [(math.radians(a),d) for a in (-10,10,-20,20,-25,25,-30,30)
            for d in (.190,.194,.198,.203,.208,.212)]
