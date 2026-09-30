"""Wall geometry from PR #347 (eaeaaff0), shared design for v88 acquisition.

Pure geometry only. The physics owner enforces these bounds at every substep
and may only abort. There is no command correction or student GT channel.
"""
import math

def rectangles(static):
    """Reject unsupported geometry instead of treating it as free space."""
    bounds = static['bounds_m']
    if len(bounds) != 4 or not all(math.isfinite(v) for v in bounds):
        raise ValueError('invalid static bounds')
    if bounds[0] >= bounds[1] or bounds[2] >= bounds[3] or static.get('terrain'):
        raise ValueError('unsupported floor geometry')
    result = []
    if not static['obstacles']:
        raise ValueError('missing static walls')
    for obstacle in static['obstacles']:
        if obstacle.get('kind') != 'wall' or obstacle.get('yaw_rad', 0) != 0:
            raise ValueError('unsupported static obstacle')
        x, y = obstacle['center_m']
        hx, hy = obstacle['half_extents_m']
        if not all(math.isfinite(v) for v in (x, y, hx, hy)) or min(hx, hy) <= 0:
            raise ValueError('invalid static obstacle')
        result.append((x - hx, x + hx, y - hy, y + hy))
    return result


def free_floor_area(static):
    """Exact union of clipped, axis-aligned wall rectangles (square metres)."""
    x0, x1, y0, y1 = static['bounds_m']
    rects = [(max(x0, a), min(x1, b), max(y0, c), min(y1, d)) for a, b, c, d in rectangles(static)]
    rects = [r for r in rects if r[0] < r[1] and r[2] < r[3]]
    xs = sorted({x0, x1, *(v for r in rects for v in r[:2])})
    blocked = 0.
    for a, b in zip(xs, xs[1:]):
        intervals = sorted((c, d) for l, r, c, d in rects if l < (a + b) / 2 < r)
        end, height = y0, 0.
        for c, d in intervals:
            height += max(0., d - max(c, end))
            end = max(end, d)
        blocked += (b - a) * height
    return (x1 - x0) * (y1 - y0) - blocked


def clearance(static, xy, radius):
    """Distance from a conservative robot disc to walls and map boundary."""
    x, y = xy
    if not all(math.isfinite(v) for v in (x, y, radius)) or radius <= 0:
        raise ValueError('missing/non-finite clearance measurement')
    x0, x1, y0, y1 = static['bounds_m']
    distances = [x - x0, x1 - x, y - y0, y1 - y]
    for a, b, c, d in rectangles(static):
        distances.append(math.hypot(max(a - x, 0., x - b), max(c - y, 0., y - d)))
    return min(distances) - radius


def require_clearance(static, xy, plan):
    safety = plan['clearance']
    gap = clearance(static, xy, safety['robot_radius_bound_m'])
    if gap < safety['minimum_m'] + safety['abort_buffer_m'] - 1e-10:
        raise ValueError('CLEARANCE_ABORT: static-map wall margin not available')
    return gap


def sphere_clearances(static, xy, radii):
    """Vectorized version for every robot/arm/beam geom at each substep."""
    import numpy as np
    xy, radii = np.asarray(xy, float), np.asarray(radii, float)
    if (xy.ndim != 2 or xy.shape[1] != 2 or radii.shape != (len(xy),) or not len(xy)
            or not np.isfinite(xy).all() or not np.isfinite(radii).all() or np.any(radii <= 0)):
        raise ValueError('missing/non-finite clearance geometry')
    rects = rectangles(static)
    x0, x1, y0, y1 = static['bounds_m']
    x, y = xy.T
    gaps = np.minimum.reduce((x-x0, x1-x, y-y0, y1-y))
    for a, b, c, d in rects:
        gaps = np.minimum(gaps, np.hypot(np.maximum.reduce((a-x, x-b, np.zeros(len(x)))),
                                        np.maximum.reduce((c-y, y-d, np.zeros(len(y))))))
    return gaps-radii
