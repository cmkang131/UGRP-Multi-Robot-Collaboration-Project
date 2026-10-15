"""Opt-in speed profiles for the actual AMCL data recording controller.

The existing batch path keeps every float64 operation and reduction order.
exact_v1 reuses exact geometry/front-end/ray kernels; squared_v1 additionally
changes floating-point evaluation order, with unchanged samples and thresholds.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import math
import numpy as np

ACTIVE = ContextVar('map_recording_rectangle_batch', default=False)
PROFILE = ContextVar('map_recording_controller_profile', default='off')
PROFILES = ('off', 'exact_v1', 'squared_v1')


@contextmanager
def controller_profile(profile):
    if profile not in PROFILES:
        raise ValueError('UNKNOWN_RECORDING_CONTROLLER_PROFILE')
    token = PROFILE.set(profile)
    try:
        yield
    finally:
        PROFILE.reset(token)


def configure(robot, profile='off'):
    """Reuse the existing exact kernels; never change other robot instances."""
    if profile not in PROFILES:
        raise ValueError('UNKNOWN_RECORDING_CONTROLLER_PROFILE')
    if profile != 'off':
        from harness.e2e_exact_speedups import Options
        robot.exact_speedups = Options(
            provenance_index=True, sha_validation_cache=True, omit_discarded_copy=True,
            scalar_cells=True, geometry_cache=True, vector_rays=True,
            shared_wall_frontend=True, lazy_scan_path=True,
            vector_costmap_writes=True, track_cell_tuples=True)
    return robot


def squared_grid_cost(points, centers, yaw, half, trunc, *, interior=False):
    """Reuse the existing float64 squared-distance kernel in bounded blocks.

    Algebraically equivalent, but rotated coordinates change float rounding.
    This is explicitly a result-changing, default-off profile. Keep all points,
    grid poses, thresholds and robust refinement, unlike speed5 lean sampling.
    """
    from harness.e2e_speed5 import rectangle_grid_cost, using as speed5_using
    costs = np.empty(len(centers), dtype=np.float64)
    with speed5_using('lean_v2'):
        for start in range(0, len(centers), 128):
            costs[start:start+128] = rectangle_grid_cost(
                points, centers[start:start+128], yaw, half, trunc, interior=interior)
    return costs


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
