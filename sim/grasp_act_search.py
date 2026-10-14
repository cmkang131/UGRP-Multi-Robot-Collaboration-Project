"""Static-map next-best-view search for a target that has not been seen yet.

Opt-in teacher mode `search_body_scan_v1`. The robot first sweeps its camera
pan/tilt, then repeatedly picks the (viewpoint, heading) whose line-of-sight
sector covers the most still-unseen free map cells per unit of time, moves
there and sweeps again. Only the authored static map (bounds, interior wall
rectangles), the robot's own issued-command pose estimate and the cells it has
already swept are used. No cargo, peer or beam position enters the choice and
the gaze is never turned toward a hidden object.

References (bibliographic only; full texts not read in this work):
- Yamauchi, "A frontier-based approach for autonomous exploration", CIRA 1997.
- Gonzalez-Banos and Latombe, "Navigation strategies for exploring indoor
  environments", IJRR 21(10-11), 2002 (next-best-view by gain over cost).
- Aydemir et al., "Active visual object search in unknown environments using
  uncertain semantics", IEEE T-RO 29(4), 2013.
"""
import math
import numpy as np
from harness.static_keepouts import rect_distance

CELL_M = .25          # map cells that must be swept
VIEW_GRID_M = .5      # candidate viewpoints
RANGE_M = 2.5         # assumed useful viewing range (unverified, geometric)
# Three pan stops (-45, 0, +45 deg) of a 54 deg pinhole HFOV cover +-72 deg.
SECTOR_RAD = math.radians(72)
HEADINGS = tuple(k*math.pi/4 for k in range(8))
SWEEP_S = 3.6          # 3 pan stops x (near, far) tilt, 0.6 s each
SPEED_MPS = .10        # measured median 0.08-0.11 m/s of the same route driver (GCP gate)
TURN_RADPS = .45       # measured 0.47 rad/s of the search turn command (76015)


def wrap(x):
    return math.atan2(math.sin(x), math.cos(x))


def segment_hits_rect(a, b, rect):
    """Liang-Barsky clip of segment a-b against an oriented rectangle."""
    cx, cy, hx, hy, yaw = rect
    c, s = math.cos(yaw), math.sin(yaw)

    def loc(p):
        dx, dy = p[0]-cx, p[1]-cy
        return c*dx+s*dy, -s*dx+c*dy
    (x0, y0), (x1, y1) = loc(a), loc(b)
    t0, t1 = 0., 1.
    for p, q in ((-(x1-x0), x0+hx), (x1-x0, hx-x0), (-(y1-y0), y0+hy), (y1-y0, hy-y0)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
            continue
        r = q/p
        if p < 0:
            if r > t1:
                return False
            t0 = max(t0, r)
        else:
            if r < t0:
                return False
            t1 = min(t1, r)
    return t0 <= t1


class StaticMapSearch:
    def __init__(self, bounds, rects, *, radius=.17, margin=.05):
        x0, x1, y0, y1 = bounds
        self.bounds, self.rects, self.radius = tuple(bounds), tuple(rects), radius
        xs = np.arange(x0+CELL_M/2, x1, CELL_M)
        ys = np.arange(y0+CELL_M/2, y1, CELL_M)
        cells = [(float(x), float(y)) for x in xs for y in ys
                 if all(rect_distance((x, y), r) > 0. for r in self.rects)]
        self.cells = np.array(cells)
        vx = np.arange(x0+radius+margin, x1-radius-margin+1e-9, VIEW_GRID_M)
        vy = np.arange(y0+radius+margin, y1-radius-margin+1e-9, VIEW_GRID_M)
        self.candidates = [(float(x), float(y)) for x in vx for y in vy
                           if all(rect_distance((x, y), r) >= radius+margin for r in self.rects)]
        self._cache = {}

    def visibility(self, point):
        """Bool mask over cells with clear static line of sight within range, and bearings."""
        key = (round(point[0], 3), round(point[1], 3))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        d = self.cells-np.array(point)
        dist = np.hypot(d[:, 0], d[:, 1])
        mask = dist <= RANGE_M
        for i in np.flatnonzero(mask):
            c = (float(self.cells[i, 0]), float(self.cells[i, 1]))
            if any(segment_hits_rect(point, c, r) for r in self.rects):
                mask[i] = False
        bearing = np.arctan2(d[:, 1], d[:, 0])
        self._cache[key] = (mask, bearing)
        return mask, bearing

    def swept(self, pose):
        """Cells covered by one completed pan sweep at pose (x, y, yaw)."""
        mask, bearing = self.visibility(pose[:2])
        off = np.abs(np.arctan2(np.sin(bearing-pose[2]), np.cos(bearing-pose[2])))
        return mask & (off <= SECTOR_RAD)

    def choose(self, pose, covered, path_length, banned=()):
        """Best (viewpoint, heading) by gain / (sweep + max(travel, turn)); translation and
        yaw happen together.

        path_length(point) -> metres or None when unreachable; it is evaluated
        only for the best few candidates ranked by straight-line cost. banned lists
        points (e.g. earlier viewpoints) that candidates must stay 0.35 m away from.
        """
        here = (float(pose[0]), float(pose[1]))
        avoid = lambda q: any(math.dist(q, b) < .35 for b in banned)
        points = [p for p in [here]+[c for c in self.candidates if math.dist(c, here) > .3] if not avoid(p)]
        ranked = []
        for p in points:
            mask, bearing = self.visibility(p)
            open_cells = mask & ~covered
            if not open_cells.any():
                continue
            for h in HEADINGS:
                off = np.abs(np.arctan2(np.sin(bearing-h), np.cos(bearing-h)))
                gain = int((open_cells & (off <= SECTOR_RAD)).sum())
                if gain <= 0:
                    continue
                straight = math.dist(p, here)
                cost = SWEEP_S+max(straight/SPEED_MPS, abs(wrap(h-pose[2]))/TURN_RADPS)
                ranked.append((gain/cost, gain, cost, p, h))
        if not ranked:
            return None
        ranked.sort(key=lambda r: (-r[0], r[3], r[4]))
        best = None
        for _, gain, _, p, h in ranked[:8]:
            length = 0. if p == here else path_length(p)
            if length is None:
                continue
            cost = SWEEP_S+max(length/SPEED_MPS, abs(wrap(h-pose[2]))/TURN_RADPS)
            score = gain/cost
            if best is None or score > best[0]+1e-12:
                best = (score, p, h, gain, cost)
        return None if best is None else {'viewpoint': best[1], 'heading': best[2], 'gain': best[3], 'cost_s': best[4]}
