"""Continuous static geometry bounds, without physics or ground truth.

Trace-only uncertainty uses sqrt(trace) as an upper bound on directional sigma;
it does NOT silently assume isotropy for clearance. Between saved estimates we
assume linear XY/shortest-yaw interpolation and the maximum endpoint sigma.
"""
import math

import numpy as np

RADIUS = .25
CORNERS = np.array([[-.15, -.15], [.20, -.15], [.20, .15], [-.15, .15]])


def cross(a, b):
    return a[0]*b[1]-a[1]*b[0]


def hull(points):
    p = sorted(set(map(tuple, points)))
    lo, hi = [], []
    for line, seq in ((lo, p), (hi, reversed(p))):
        for v in seq:
            while len(line) >= 2 and cross(np.subtract(line[-1], line[-2]), np.subtract(v, line[-1])) <= 0:
                line.pop()
            line.append(v)
    return np.array(lo[:-1]+hi[:-1])


def point_segment(p, a, b):
    d = b-a
    u = np.clip(np.dot(p-a, d)/np.dot(d, d), 0., 1.) if np.dot(d, d) else 0.
    return float(np.linalg.norm(p-a-u*d))


def segment_distance(a, b, c, d):
    v, w = b-a, d-c
    den = cross(v, w)
    if abs(den) > 1e-14:
        t, u = cross(c-a, w)/den, cross(c-a, v)/den
        if 0 <= t <= 1 and 0 <= u <= 1:
            return 0.
    return min(point_segment(a,c,d), point_segment(b,c,d), point_segment(c,a,b), point_segment(d,a,b))


def polygon_distance(p, q):
    # Separating axis theorem catches containment as well as crossings.
    separated = False
    for poly in (p, q):
        for a, b in zip(poly, np.roll(poly, -1, axis=0)):
            e = b-a; n = np.array([-e[1], e[0]])
            pp, qq = p@n, q@n
            if pp.max() < qq.min() or qq.max() < pp.min():
                separated = True
    if not separated:
        return 0.
    return min(segment_distance(a,b,c,d) for a,b in zip(p,np.roll(p,-1,axis=0))
               for c,d in zip(q,np.roll(q,-1,axis=0)))


def rectangle(rect):
    x,y,hx,hy = rect
    return np.array([[x-hx,y-hy],[x+hx,y-hy],[x+hx,y+hy],[x-hx,y+hy]])


def swept_clearance(start, end, rects):
    """Lower bound for every point of a rotating rectangular footprint's sweep.

    At constant yaw, convex hull of endpoint footprints is the exact sweep.
    With yaw varying, freeze yaw at each subsegment midpoint and subtract the
    maximum corner rotation displacement. This makes the whole bound continuous,
    unlike checking only trajectory samples. Negative bounds may be conservative.
    """
    p, q = np.asarray(start, float), np.asarray(end, float)
    if p.shape != (3,) or q.shape != (3,) or not np.isfinite([p,q]).all() or not len(rects):
        raise ValueError('finite poses and nonempty walls required')
    delta = math.atan2(math.sin(q[2]-p[2]), math.cos(q[2]-p[2]))
    n = max(1, math.ceil(abs(delta)/.004))  # <=0.25mm corner motion about mid-yaw
    walls = [rectangle(r) for r in rects]
    best = math.inf
    for j in range(n):
        u,v = j/n,(j+1)/n
        yaw = p[2]+delta*(u+v)/2
        c,s = math.cos(yaw),math.sin(yaw)
        corners = CORNERS @ np.array([[c,s],[-s,c]])
        a,b = p[:2]+(q[:2]-p[:2])*u,p[:2]+(q[:2]-p[:2])*v
        poly = hull(np.concatenate([corners+a,corners+b]))
        loss = 2*RADIUS*math.sin(abs(delta)/(4*n))
        # Bounding-box lower bounds safely prune distant walls.
        for wall in walls:
            gap = np.maximum(np.maximum(wall.min(0)-poly.max(0),poly.min(0)-wall.max(0)),0.)
            if np.linalg.norm(gap)-loss >= best:
                continue
            best = min(best, polygon_distance(poly,wall)-loss)
    disk = math.inf
    for wall in walls:
        if np.all(p[:2]>=wall.min(0)) and np.all(p[:2]<=wall.max(0)):
            dist = 0.
        elif np.all(q[:2]>=wall.min(0)) and np.all(q[:2]<=wall.max(0)):
            dist = 0.
        else:
            dist = min(segment_distance(p[:2],q[:2],a,b) for a,b in zip(wall,np.roll(wall,-1,axis=0)))
        disk = min(disk, dist-RADIUS)
    return {'footprint_lower_m': best, 'disk_lower_m': disk, 'rotation_subsegments': n}


def audit_segment(start, end, std_xy, std_yaw, rects):
    if not all(math.isfinite(v) and v>=0 for v in [std_xy,std_yaw]):
        raise ValueError('finite nonnegative uncertainty required')
    geom = swept_clearance(start,end,rects)
    budget = 3*std_xy+2*RADIUS*math.sin(min(math.pi,3*std_yaw)/2)+.015
    return {**geom, 'uncertainty_tracking_map_budget_m': budget,
            'adjusted_lower_m': geom['footprint_lower_m']-budget,
            'clearance_6cm': geom['footprint_lower_m']>=.06,
            'sigma_clearance_nonnegative': geom['footprint_lower_m']>=budget}
