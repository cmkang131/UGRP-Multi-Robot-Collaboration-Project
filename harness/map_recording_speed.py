"""Exact bounded rectangle work for the opt-in AMCL recording only.

Keep every point, candidate and float64 operation. Chunk only independent
candidate rows; point order and row reductions remain the same.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import math
import numpy as np

ACTIVE = ContextVar('map_recording_rectangle_batch', default=False)


@contextmanager
def using(enabled):
    if type(enabled) is not bool:
        raise ValueError('BOOLEAN_RECTANGLE_BATCH_REQUIRED')
    token = ACTIVE.set(enabled)
    try:
        yield
    finally:
        ACTIVE.reset(token)


def rect_sd(points, center, yaw, half):
    """Same operation order as e2e_b_partial.rect_sd, smaller temporaries."""
    c, s = math.cos(yaw), math.sin(yaw)
    d = np.asarray(points, float)-center
    ex = np.abs(c*d[..., 0]+s*d[..., 1])-half[0]
    ey = np.abs(-s*d[..., 0]+c*d[..., 1])-half[1]
    return np.hypot(np.maximum(ex, 0), np.maximum(ey, 0))+np.minimum(np.maximum(ex, ey), 0)


def grid_cost(points, centers, yaw, half, trunc, *, interior=False):
    costs = np.empty(len(centers), dtype=np.float64)
    for start in range(0, len(centers), 64):
        distances = rect_sd(points[None], centers[start:start+64, None], yaw, half)
        residual = np.maximum(distances, 0) if interior else np.abs(distances)
        costs[start:start+64] = (np.minimum(residual, trunc)**2).mean(axis=1)
    return costs
