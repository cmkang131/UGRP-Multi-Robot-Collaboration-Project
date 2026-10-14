"""Reuse zone A* with current-view segment checks and target-facing mecanum yaw.

Only the filtered visible/memorized world is accepted. This is teacher code,
not a hand-coded fallback for the independently executing ACT student.
"""
import math
from scripts.zone_teacher import PeerDisc,_no_closer,_wall_limits
from harness.static_keepouts import rect_distance


def constraints(world,rid,folded):
    radius=.13 if folded else .17;extra=.17-radius
    pose=world['robots'][rid]['pose']
    discs=[PeerDisc((*v['pose'][:2],.17+extra)) for r,v in world['robots'].items() if r!=rid]
    for key,o in world['objects'].items():
        if key=='beam_1':continue
        padding=.005 if folded and o.get('top_z_bound_m',math.inf)<=.1 else .02+extra
        discs.append((*o['xy'],o['radius']+padding))
    x,y,a=world['beam']['pose']
    discs += [(x+d*math.cos(a),y+d*math.sin(a),.02) for d in (-.27,-.135,0.,.135,.27)]
    rects=[(x,y,hx+extra,hy+extra,a) for x,y,hx,hy,a in world.get('walls',[])]
    return radius,discs,rects


def free(point,discs,rects,radius):
    return (all(math.dist(point,d[:2])>=d[2]+radius for d in discs)
            and all(rect_distance(point,rect)>=radius for rect in rects))


def segment_free(start,end,discs,rects,radius):
    # Match zone A*'s margin-escape rule for both peers and cargo. If fresh
    # visual localization puts the base inside an inflated margin, permit
    # retreat without getting closer. Otherwise the safety check rejects the
    # very escape path returned by the planner. Physical bodies stay intact.
    ds=[_no_closer(start,d,radius) for d in discs]
    walls=_wall_limits(start,rects,radius)
    # Analytic segment/disc test; grid cells alone do not prevent corner cuts.
    dx,dy=end[0]-start[0],end[1]-start[1];norm=dx*dx+dy*dy
    for x,y,r in ds:
        u=max(0.,min(1.,((x-start[0])*dx+(y-start[1])*dy)/max(norm,1e-12)))
        if math.hypot(start[0]+u*dx-x,start[1]+u*dy-y)<r+radius-1e-9:return False
    n=max(1,math.ceil(math.sqrt(norm)/.01))
    return all(rect_distance((start[0]+dx*i/n,start[1]+dy*i/n),rect)>=limit
               for i in range(n+1) for rect,limit in walls)


def waypoint(start,path,discs,rects,radius):
    # Choose a forward, directly reachable waypoint, without deleting the
    # corner solely because it is within the former 12 cm proximity band.
    if not path:return None
    closest=min(range(len(path)),key=lambda i:math.dist(start,path[i]))
    best=None
    for point in path[min(closest+1,len(path)-1):]:
        distance=math.dist(start,point)
        if distance<.005:continue
        if segment_free(start,point,discs,rects,radius):
            best=point
            if distance>=.12:break
        elif best is not None:break
    return best


def drive(pose,goal,target,end):
    x,y,yaw=pose;dx,dy=target[0]-x,target[1]-y
    norm=max(math.hypot(dx,dy),1e-9);speed=min(1.,math.dist(pose[:2],goal)/.25)
    vx,vy=dx/norm*speed,dy/norm*speed
    wanted=math.atan2(end[1]-y,end[0]-x);error=math.atan2(math.sin(wanted-yaw),math.cos(wanted-yaw))
    clip=lambda x,lo,hi:max(lo,min(hi,x))
    scale=1. if abs(error)<.5 else .3
    return {'forward':clip(.15*(math.cos(yaw)*vx+math.sin(yaw)*vy)*scale,-.05,.15),
            'left':clip(.10*(-math.sin(yaw)*vx+math.cos(yaw)*vy)*scale,-.10,.10),
            'turn':clip(.6*error,-.15,.15)}
