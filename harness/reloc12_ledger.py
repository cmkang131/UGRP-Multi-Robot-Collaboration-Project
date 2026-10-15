"""Allowed-map route rejection context; finite geometric checks, never truth."""
import math
from harness.static_keepouts import rect_distance


def route_context(start, goal, discs, rects, radius, *, names=(), bounds=None):
    points=[(start[0]+(goal[0]-start[0])*i/100,start[1]+(goal[1]-start[1])*i/100) for i in range(101)]
    gaps=[]
    for i,rect in enumerate(rects):
        gaps.append((min(rect_distance(p,rect)-radius for p in points),names[i] if i<len(names) else f'static_rect:{i}'))
    for i,d in enumerate(discs):
        gaps.append((min(math.dist(p,d[:2])-d[2]-radius for p in points),f'own_rgb_obstacle:{i}'))
    if bounds:
        a,b,c,d=bounds
        gaps.append((min(min(p[0]-a,b-p[0],p[1]-c,d-p[1])-radius for p in points),'map_bounds'))
    gap,name=min(gaps,default=(None,'no_geometric_blocker_identified'))
    return dict(blocked_object=name,minimum_gap_m=gap,
                gap_scope='101 samples of requested straight corridor; not a proof that no detour exists',
                diagnostic_checks=101*len(gaps))


def segment_rejection_context(start, end, discs, rects, radius, *, names=(), disc_names=()):
    """Replay segment_free's exact escape limits and its existing 1cm samples."""
    from scripts.zone_teacher import _no_closer, _wall_limits
    dx,dy=end[0]-start[0],end[1]-start[1]; norm=dx*dx+dy*dy
    gaps=[]
    for i,(x,y,r) in enumerate(_no_closer(start,d,radius) for d in discs):
        u=max(0.,min(1.,((x-start[0])*dx+(y-start[1])*dy)/max(norm,1e-12)))
        gap=math.hypot(start[0]+u*dx-x,start[1]+u*dy-y)-r-radius
        gaps.append((gap,disc_names[i] if i<len(disc_names) else f'own_rgb_obstacle:{i}'))
    n=max(1,math.ceil(math.sqrt(norm)/.01))
    for i,(rect,limit) in enumerate(_wall_limits(start,rects,radius)):
        gap=min(rect_distance((start[0]+dx*j/n,start[1]+dy*j/n),rect)-limit for j in range(n+1))
        gaps.append((gap,names[i] if i<len(names) else f'static_rect:{i}'))
    gap,name=min(gaps,default=(None,'no_geometric_blocker_identified'))
    return dict(category='route',blocked_object=name,minimum_gap_m=gap,
                gap_scope='same margin-escape limits and wall samples as segment_free',
                blockers=[dict(blocked_object=name,minimum_gap_m=gap) for gap,name in sorted(gaps) if gap<0])
