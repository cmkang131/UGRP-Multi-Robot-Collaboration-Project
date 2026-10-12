"""Default-off Nav2 ObstacleLayer 2D clear-before-mark observation adapter.

Uses the pinned BSD-3 Bresenham port; original notices and line comparison:
experiments/2026-10-07-mapfree-raytrace/REFERENCES.md. Own sensor XY origins,
endpoints and own pose only. No scene, hidden object or peer-map input.
"""
import numpy as np
from harness.public_navigation_persistent import raytrace_cells
from harness.public_navigation_resolution import ResolutionActor
from harness.self_odom_grid import transform

OPTION = 'public_ros_v6'


def navigation_output_v6(legacy, *, navigation='off', navigator=None, **kwargs):
    if navigation == 'off':
        return legacy
    if navigation != OPTION or navigator is None:
        raise ValueError('EXPLICIT_PUBLIC_ROS_V6_REQUIRED')
    return navigator.update(**kwargs)


def receive_rays(grid, latest, static_hits, observation, pose):
    """Finite measured rays: clear the complete line, then mark current returns.

    Floor points are clearing-only; wall points are clearing+marking. The grid's
    free provenance records ray support, not a claim of directly seen floor area.
    Distinct points mapping to identical cell rays are deduplicated this frame.
    """
    payload = dict(observation)
    rays = set()
    for prefix in ('floor', 'wall'):
        points = np.asarray(payload[prefix+'_xy'], float).reshape(-1, 2)
        origins = np.asarray(payload.pop(prefix+'_origins_xy'), float)
        if origins.size == 0:
            origins = origins.reshape(-1, 2)
        if origins.shape != points.shape or not np.isfinite(origins).all():
            raise ValueError('OBSERVED_RAYS_REQUIRE_ONE_FINITE_CAMERA_ORIGIN_PER_POINT')
        # Validate before transforming or mutating any map state.
        if not np.isfinite(points).all():
            raise ValueError('NAV_INVALID_OBSERVATION')
        rays.update((grid.cell(a), grid.cell(b)) for a, b in
                    zip(transform(origins, pose), transform(points, pose)))
    grid.observe(**payload, pose=pose)  # own identity, frame, schema and pose validation
    hits = {grid.cell(p) for p in transform(np.asarray(payload['wall_xy'], float).reshape(-1, 2), pose)}
    cleared = {cell for start, end in rays for cell in raytrace_cells(start, end)}
    for cell in cleared-set(static_hits):
        latest[cell] = False
        grid.odds[cell] = -max(1., abs(grid.odds.get(cell, 0.)))
        grid.floor_frames.setdefault(cell, set()).add(payload['frame_id'])
    # A different ray can cross a current endpoint: marking must be the last pass.
    for cell in hits:
        latest[cell] = True
        grid.odds[cell] = max(1., grid.odds.get(cell, 0.))
    # Off-view occupied memory survives; only intersecting rays can remove it.
    for cell, occupied in latest.items():
        if occupied:
            grid.odds[cell] = max(1., grid.odds.get(cell, 0.))
    return dict(rays=len(rays), cleared_cells=len(cleared-set(static_hits)-hits), hit_cells=len(hits))


class RaytraceActor(ResolutionActor):
    def __init__(self, condition, static_grid=None, static_goal=None, *, navigation='off'):
        if navigation != OPTION:
            raise ValueError('EXPLICIT_PUBLIC_ROS_V6_REQUIRED')
        super().__init__(condition, static_grid, static_goal, navigation='public_ros_v5')
        self.raytrace_profile = OPTION
        self.ray_updates = []

    def receive(self, observation, patches):
        counts = receive_rays(self.grid, self.latest, self.static_hits, observation, self.odom.pose)
        self.ray_updates.append(dict(frame_id=observation['frame_id'], **counts))
        self.last_patches = self.goal.add(patches, self.t, observation['frame_id'], self.odom.pose)
        return self.last_patches
