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
