"""Default-off crate15 teacher geometry and issued-command servo, no simulator.

Full SE(2) chassis/peer footprints, authored crate parts, exact start connectors.
The 5 mm geometric pad is a design margin, not measured localization accuracy.
Other cargo retains the previous conservative circle constraint. Only admitted
visible geometry / issued pose enters; no evaluator state or measured joints.
"""
import heapq
import math
from harness.static_keepouts import polygon_at, rect_corners, _axes
from harness.grasp_act_visible_world import command_delta
from harness.grasp_act_contract import command, wheel_mix
from sim.crate_navigation_v12 import FOOTPRINT, PAD_M, HALF_X, HALF_Y

MODE = 'crate_motion_v15'
GRID_M = .05


def polygon_gap(a, b):
    """Signed separating-axis clearance (conservative lower bound if separate)."""
    return max(max(min(x*u+y*v for x,y in b)-max(x*u+y*v for x,y in a),
                   min(x*u+y*v for x,y in a)-max(x*u+y*v for x,y in b))
               for u,v in (*_axes(a), *_axes(b)))


class Navigation:
    def __init__(self, world, rid, folded, profile, bounds, end=None):
        self.pose = tuple(world['robots'][rid]['pose'])
        self.bounds = bounds
        self.rectangles = [('wall', tuple(r)) for r in world.get('walls', ())]
        self.peers = [('peer', polygon_at(v['pose'], FOOTPRINT))
                      for key,v in world['robots'].items() if key != rid]
        self.circles = []
        self.radius = .13 if folded else .17
        # The assigned lug must be CURRENTLY visible before using its inferred
        # rigid-body shape. A remembered/invisible lug grants no geometry here.
        beam = world['beam'] if world['visibility'][rid]['visible_probes'] >= 5 else None
        self.focus = (beam['ends'][end] if end is not None else
                      next(iter(beam['ends'].values())) if len(beam['ends'])==1 else None) if beam else None
        if self.focus is None and profile.item_id in world['visibility'][rid]['objects']:
            self.focus=world['objects'][profile.item_id]['xy']
        if beam is not None:
            x,y,a = beam['pose'];c,s=math.cos(a),math.sin(a)
            for d,hx,hy in ((0.,.07,.05),(-.09,.03,.02),(.09,.03,.02)):
                self.rectangles.append(('crate', (x+c*d,y+s*d,hx,hy,a)))
        for key,obj in world['objects'].items():
            if key == profile.item_id and beam is not None:
                continue
            pad = .005 if folded and obj.get('top_z_bound_m',math.inf) <= .1 else .02+(.17-self.radius)
            self.circles.append(('crate' if key==profile.item_id else 'other_cargo',
                                 (*obj['xy'],obj['radius']+pad)))
        # Same conservative non-crate circle constraint as crate14.

    def clearances(self, point, yaw):
        p=(*point[:2],yaw);own=polygon_at(p,FOOTPRINT)
        values=[(kind,polygon_gap(own,rect_corners(r,margin=PAD_M))) for kind,r in self.rectangles]
        # Grow both peer dimensions by the design pad, without reading joints.
        padded=[(-HALF_X-PAD_M,-HALF_Y-PAD_M),(HALF_X+PAD_M,-HALF_Y-PAD_M),
                (HALF_X+PAD_M,HALF_Y+PAD_M),(-HALF_X-PAD_M,HALF_Y+PAD_M)]
        # Stored peer polygons are expanded about their centre in their axes.
        for kind,peer in self.peers:
            cx=sum(v[0] for v in peer)/4;cy=sum(v[1] for v in peer)/4
            a=math.atan2(peer[1][1]-peer[0][1],peer[1][0]-peer[0][0])
            values.append((kind,polygon_gap(own,polygon_at((cx,cy,a),padded))))
        values += [(kind,math.dist(point,d[:2])-d[2]-self.radius) for kind,d in self.circles]
        x0,x1,y0,y1=self.bounds
        values.append(('bounds',min(min(x-x0,x1-x,y-y0,y1-y)-PAD_M for x,y in own)))
        return values

    def free(self, point, yaw):
        return all(v > 0. for _,v in self.clearances(point,yaw))

    def segment(self, a, b, ayaw, byaw):
        da=math.atan2(math.sin(byaw-ayaw),math.cos(byaw-ayaw))
        n=max(1,math.ceil(math.dist(a[:2],b[:2])/.002),math.ceil(abs(da)/math.radians(.5)))
        return all(self.free((a[0]+(b[0]-a[0])*i/n,a[1]+(b[1]-a[1])*i/n),ayaw+da*i/n)
                   for i in range(n+1))

    def heading_at(self, point, fallback):
        if self.focus is None:return fallback
        return math.atan2(self.focus[1]-point[1],self.focus[0]-point[0])

    def path(self, start, goal, heading):
        if not self.free(start,self.pose[2]) or not self.free(goal,heading):return None
        if self.segment(start,goal,self.pose[2],heading):return [tuple(start),tuple(goal)]
        # Actual start is a virtual node. Connect to safe nearby lattice nodes;
        # no mandatory snapped-start detour. Every edge gets the same SE(2) test.
        cell=lambda p:(round(p[0]/GRID_M),round(p[1]/GRID_M))
        point=lambda k:(k[0]*GRID_M,k[1]*GRID_M)
        sc=cell(start);front=[];cost={};came={};cache={}
        def free(k):
            if k not in cache:cache[k]=self.free(point(k),self.heading_at(point(k),heading))
            return cache[k]
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                k=(sc[0]+dx,sc[1]+dy);p=point(k)
                if free(k) and self.segment(start,p,self.pose[2],self.heading_at(p,heading)):
                    cost[k]=math.dist(start,p);came[k]=None
                    heapq.heappush(front,(cost[k]+math.dist(p,goal),k))
        final=None;steps=0
        while front and steps<4000:
            _,k=heapq.heappop(front);p=point(k);steps+=1
            if math.dist(p,goal)<=GRID_M*1.5 and self.segment(p,goal,self.heading_at(p,heading),heading):final=k;break
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    if not dx and not dy:continue
                    nxt=(k[0]+dx,k[1]+dy);q=point(nxt);new=cost[k]+math.dist(p,q)
                    if new>=cost.get(nxt,math.inf) or not free(nxt):continue
                    if not self.segment(p,q,self.heading_at(p,heading),self.heading_at(q,heading)):continue
                    cost[nxt]=new;came[nxt]=k
                    heapq.heappush(front,(new+math.dist(q,goal),nxt))
        if final is None:return None
        path=[tuple(goal)]
        while final is not None:path.append(point(final));final=came[final]
        return [tuple(start),*reversed(path)]

    def waypoint(self, start, path, target):
        if not path:return None
        nearest=min(range(len(path)),key=lambda i:math.dist(start,path[i]));best=None
        for p in path[nearest:]:
            dist=math.dist(start,p)
            if dist<.001:continue
            yaw=math.atan2(target[1]-p[1],target[0]-p[0])
            if self.segment(start,p,self.pose[2],yaw):
                best=p
                if dist>=.12:break
            elif best is not None:break
        return best

    def pulse_safe(self, value):
        if not any(value['wheels']):return True
        times=sorted({0.,.1,*(i*.005 for i in range(1,20)),*(min(.1,d) for d in value['duration_s'])})
        x,y,a=self.pose
        for ta,tb in zip(times,times[1:]):
            dx,dy,da=command_delta({**value,'duration_s':[max(0.,d-ta) for d in value['duration_s']]},tb-ta)
            c,s=math.cos(a+da/2),math.sin(a+da/2);end=(x+c*dx-s*dy,y+s*dx+c*dy)
            if not self.segment((x,y),end,a,a+da):return False
            x,y=end;a+=da
        return True


def alignment_pulse(hold, drive, errors):
    """Error-proportional duty; <= half remaining error in issued kinematics.

    One millisecond resolution is explicit. If that cannot fit, hold; never
    enlarge a sub-resolution request to 40ms. Readiness stays unchanged.
    """
    desired=wheel_mix([3*drive[0],3*drive[1],.65*drive[2]])
    scale=max(.35,max(map(abs,desired)));width=[.1*abs(v)/scale for v in desired]
    wheel=[math.copysign(.35,v) if v else 0. for v in desired]
    probe={**hold,'wheels':wheel,'duration_s':width};delta=command_delta(probe,.1)
    factor=min([1.]+[.5*abs(e)/abs(d) for e,d in zip(errors,delta) if abs(d)>1e-12])
    # Quantize to milliseconds; recheck the 1ms floor against the error bound.
    # The exact same command goes to collision checks and port.
    widths=[max(.001,math.floor(min(.1,d*factor)*1000+1e-9)/1000) if d else 0. for d in width]
    actual=command_delta({**hold,'wheels':wheel,'duration_s':widths},.1)
    if any(abs(d)>.5*abs(e)+1e-12 for e,d in zip(errors,actual)):
        return command(hold)
    return command({**hold,'wheels':[w if d>=.001 else 0. for w,d in zip(wheel,widths)],'duration_s':widths})
