"""Round-2 exact receive-chain shortcuts (Refs #433); every path is default off.

Each helper returns the same values, in the same set/dict insertion order, as
the original per-element code, or ``None`` so the caller runs the original
code. No physics, camera, render cadence, threshold or evidence byte changes.

* vector_rays: ObservedGrid.cell for a whole (N, 2) float64 array, and the
  Nav2/Bresenham traversal of many integer rays in one closed-form pass
  (k-th minor step = floor((major//2 + i*minor)/major)). The concatenated
  cell order equals ``for start, end in rays for cell in raytrace_cells(...)``.
* shared_wall_frontend: the two per-frame wall-contact callers
  (active_wall_vision.observe, self_wall_segment_points.contact_points) run
  the same RGB->BGR, undistort, stateless contact detector and grey
  conversion on the same image and command FK. Only the original height-free
  detector (wall_detector='off') with a stateless contact rule is shared. The post-detector result is
  kept for the exact input bits and returned as owned copies.
* lazy_scan_path: e2e_own_inputs.scan builds the path string only when it
  raises; traversal order, checks and messages are unchanged.
* vector_costmap_writes: from_observed_grid's per-cell writes as one indexed
  assignment when every index is in range (no wrap/alias), else original.
* track_cell_tuples: floor_goal_v3 track cells inserted from two column
  iterators; same np.int64 elements, values and order as ``tuple(row)``.
"""
from collections import OrderedDict
import copy
import math

import numpy as np

_INT_LIMIT = 2**52
STATS = dict(frontend_hits=0, frontend_misses=0, frontend_bypass=0, cells_fast=0, cells_fallback=0,
             rays_fast=0, rays_fallback=0, costmap_fast=0, costmap_fallback=0)


def cells(grid, points):
    """Vectorized ObservedGrid.cell over rows of ``points`` or None."""
    from harness.own_map_navigation import ObservedGrid
    if type(grid).cell is not ObservedGrid.cell:
        return None
    resolution = grid.resolution
    if type(resolution) not in (float, int) or not resolution > 0:
        return None
    if type(points) is not np.ndarray or points.dtype != np.float64 or points.ndim != 2 or points.shape[1] != 2:
        return None
    q = np.floor(points/resolution)
    if not np.isfinite(q).all() or (len(q) and np.abs(q).max() >= _INT_LIMIT):
        STATS['cells_fallback'] += 1
        return None
    STATS['cells_fast'] += 1
    return list(map(tuple, q.astype(np.int64).tolist()))


def bresenham_cells(rays):
    """All cells of each (start, end) integer ray, concatenated in ray order.

    Returns two Python-int lists (x, y) or None when an endpoint is not a
    plain two-int pair (the caller then uses the original generator).
    """
    rows = []
    for start, end in rays:
        if (type(start) is not tuple or type(end) is not tuple or len(start) != 2 or len(end) != 2
                or any(type(v) is not int for v in (*start, *end))):
            STATS['rays_fallback'] += 1
            return None
        rows.append((start[0], start[1], end[0], end[1]))
    if not rows:
        return [], []
    r = np.array(rows, np.int64)
    if np.abs(r).max() >= 2**30:
        STATS['rays_fallback'] += 1
        return None
    STATS['rays_fast'] += 1
    x0, y0, x1, y1 = r.T
    dx, dy = x1-x0, y1-y0
    ax, ay = np.abs(dx), np.abs(dy)
    xmajor = ax >= ay
    major = np.where(xmajor, ax, ay)
    minor = np.where(xmajor, ay, ax)
    length = major+1
    rep = lambda v: np.repeat(v, length)
    i = np.arange(int(length.sum()), dtype=np.int64)-rep(np.cumsum(length)-length)
    M, m = rep(major), rep(minor)
    k = np.where(M > 0, (M//2+i*m)//np.maximum(M, 1), 0)
    sx, sy = rep(np.where(dx > 0, 1, -1)), rep(np.where(dy > 0, 1, -1))
    xm = rep(xmajor)
    x = rep(x0)+np.where(xm, sx*i, sx*k)
    y = rep(y0)+np.where(xm, sy*k, sy*i)
    return x.tolist(), y.tolist()


# ---- shared wall front end ------------------------------------------------

STATELESS_RULES = ('off', 'bottom_up_connected_v1')
_FRONTEND = OrderedDict()
_FRONTEND_MAX = 2


def _frontend_key(servo, origin, rotation, params, loaded, wall_detector, contact_rule, mp, hfw):
    try:
        servo_key = tuple(sorted(servo.items()))
        params_key = tuple(sorted(params.items()))
        hash((servo_key, params_key))
    except TypeError:
        return None
    o, r = np.asarray(origin), np.asarray(rotation)
    if o.dtype.hasobject or r.dtype.hasobject:
        return None
    return (servo_key, o.dtype.str, o.shape, o.tobytes(), r.dtype.str, r.shape, r.tobytes(), params_key,
            type(loaded), loaded, wall_detector, contact_rule, id(mp), id(hfw))


def wall_frontend(compute, rgb, *, servo, origin, rotation, params, loaded, wall_detector, contact_rule,
                  contact_state, mp, hfw):
    """Return (und, scan, grey) from ``compute()`` or an exact earlier result."""
    from harness.controller_exact_speedups import array_equal
    from harness.e2e_exact_speedups import wall_frontend_enabled
    if (not wall_frontend_enabled() or wall_detector != 'off' or contact_rule not in STATELESS_RULES
            or contact_state is not None or type(rgb) is not np.ndarray or rgb.dtype != np.uint8):
        STATS['frontend_bypass'] += 1
        return compute()
    key = _frontend_key(servo, origin, rotation, params, loaded, wall_detector, contact_rule, mp, hfw)
    if key is None:
        STATS['frontend_bypass'] += 1
        return compute()
    entry = _FRONTEND.get(key)
    if entry is not None and array_equal(entry[0], rgb):
        _FRONTEND.move_to_end(key)
        STATS['frontend_hits'] += 1
        und, scan, grey = entry[1]
        return und.copy(), copy.deepcopy(scan), grey.copy()
    und, scan, grey = compute()
    STATS['frontend_misses'] += 1
    _FRONTEND[key] = (rgb.copy(), (und.copy(), copy.deepcopy(scan), grey.copy()))
    _FRONTEND.move_to_end(key)
    while len(_FRONTEND) > _FRONTEND_MAX:
        _FRONTEND.popitem(last=False)
    return und, scan, grey


# ---- lazy scan path -------------------------------------------------------

def scan_lazy(value, path, *, forbidden, violation, original):
    stack = []

    def where():
        p = path
        for kind, item in stack:
            p = p+'.'+item if kind else f'{p}[{item}]'
        return p

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in forbidden:
                    raise violation(where()+'.'+key+': PRIVILEGED_INPUT')
                if type(key) is not str:
                    original(child, where()+'.'+key)  # same TypeError or subclass path
                    continue
                stack.append((True, key))
                walk(child)
                stack.pop()
        elif isinstance(value, (list, tuple)):
            for i, child in enumerate(value):
                t = type(child)
                if t is float:
                    if not math.isfinite(child):
                        stack.append((False, i))
                        raise violation(where()+': NONFINITE_INPUT')
                    continue
                if t is int or t is str or t is bool or child is None:
                    continue
                stack.append((False, i))
                walk(child)
                stack.pop()
        elif isinstance(value, float) and not math.isfinite(value):
            raise violation(where()+': NONFINITE_INPUT')

    walk(value)


# ---- costmap writes -------------------------------------------------------

def indexed_cells(cells_iterable, lo, shape):
    """(rows, cols) for integer cells all inside ``shape`` after ``-lo``, else None."""
    items = list(cells_iterable)
    if not items:
        return np.empty(0, np.intp), np.empty(0, np.intp)
    if any(type(c) is not tuple or len(c) != 2 or type(c[0]) is not int or type(c[1]) is not int for c in items):
        return None
    lo = np.asarray(lo)
    if lo.dtype.kind not in 'iu' or lo.shape != (2,):
        return None
    xy = np.array(items, np.int64)-lo
    if (xy < 0).any() or (xy[:, 0] >= shape[1]).any() or (xy[:, 1] >= shape[0]).any():
        return None
    return xy[:, 1], xy[:, 0]
