"""Project a blind-strip search viewpoint onto reachable, body-clear map cells."""
from collections import deque
import math
import numpy as np
from harness.map_goto import (GRID_M, MARGIN_M, _Grid, _envelope_bounds, authored_obstacles,
                              interior_bounds, plan_path)

MAX_PROJECTION_M = .45
MIN_RETREAT_M = .10


def project_reachable_viewpoint(static_map, start, desired, original, envelope, *, obstacles=()):
    """Closest reachable grid point within .45 m of desired and >=.10 m west.

    Use the same fixed-heading envelope, margin and no-corner-cutting rule as
    plan_path. Final validation uses plan_path itself with no start escape.
    Never project to an arbitrary map edge or silently repeat the old view.
    """
    if not np.isfinite([*start, *desired, *original]).all():
        return None
    obstacles = list(obstacles)
    bounds = interior_bounds(static_map)
    grid = _Grid(bounds, GRID_M)
    ex0, ex1, ey0, ey1 = _envelope_bounds(envelope)
    blocked = ~((grid.X+ex0 >= bounds[0]) & (grid.X+ex1 <= bounds[1])
                & (grid.Y+ey0 >= bounds[2]) & (grid.Y+ey1 <= bounds[3]))
    for obstacle in authored_obstacles(static_map)+obstacles:
        blocked |= grid.footprint_mask(obstacle, envelope, MARGIN_M)
    sx, sy = grid.cell(start)
    if blocked[sy, sx]:
        return None
    seen = np.zeros(grid.shape, dtype=bool)
    seen[sy, sx] = True
    queue = deque([(sx, sy)])
    width, height = len(grid.xs), len(grid.ys)
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = x+dx, y+dy
            if not (0 <= nx < width and 0 <= ny < height) or seen[ny, nx] or blocked[ny, nx]:
                continue
            if dx and dy and (blocked[y, nx] or blocked[ny, x]):
                continue
            seen[ny, nx] = True
            queue.append((nx, ny))
    dist = np.hypot(grid.X-desired[0], grid.Y-desired[1])
    candidates = np.argwhere(seen & (dist <= MAX_PROJECTION_M) & (grid.X <= original[0]-MIN_RETREAT_M))
    for y, x in sorted(candidates, key=lambda cell: (dist[tuple(cell)], int(cell[0]), int(cell[1]))):
        point = grid.point((x, y))
        plan = plan_path(static_map, start, point, envelope, obstacles=obstacles)
        if plan is not None:
            return {'point': point, 'desired': list(desired), 'projection_m': math.dist(desired, point),
                    'plan_sha256': plan['plan_sha256']}
    return None
