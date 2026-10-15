"""Opt-in crate16 geometry from admitted sight/memory and issued pose only.

No simulator, evaluator, measured joints, or private object memory. The input
producer removes held cargo and expires visual memory at MEMORY_S. Planning
tries 15 mm first, then 5 mm; every issued pulse keeps the 5 mm safety check.
"""
import heapq
import math
from harness.grasp_act_contract import MEMORY_S
from harness.grasp_act_visible_world import command_delta
from sim.crate_motion_v15 import GRID_M
from sim.crate_navigation_v12 import HALF_X, HALF_Y

MODE = 'crate_motion_v16'
PADS_M = (.015, .005)
MAX_EXPANSIONS = 96                 # per pad/goal, including stale heap entries
MAX_TICK_EXPANSIONS = 384           # shared by all goals on one admitted world


def rectangle_gap(pose, rect, pad):
    """Same signed SAT lower bound as polygon_gap, analytic rectangle axes."""
    x, y, a = pose; rx, ry, hx, hy, ra = rect
    c, s = math.cos(a), math.sin(a); rc, rs = math.cos(ra), math.sin(ra)
    dx, dy = rx-x, ry-y
    co, si = abs(c*rc+s*rs), abs(c*rs-s*rc)
    hx += pad; hy += pad
    return max(abs(dx*c+dy*s)-HALF_X-hx*co-hy*si,
               abs(-dx*s+dy*c)-HALF_Y-hx*si-hy*co,
               abs(dx*rc+dy*rs)-hx-HALF_X*co-HALF_Y*si,
               abs(-dx*rs+dy*rc)-hy-HALF_X*si-HALF_Y*co)


class Navigation:
    def __init__(self, world, rid, folded, profile, bounds, end=None, *, search=False,
                 budget=None):
        self.pose = tuple(world['robots'][rid]['pose'])
        self.bounds = bounds
        self.rectangles = [('wall', tuple(r)) for r in world.get('walls', ())]
        self.radius = .13 if folded else .17
        self.circles = []
        vis = world['visibility'][rid]
        beam = world['beam']
        fresh = beam is not None and (vis['visible_probes'] >= 5 or
                    0. <= world['t']-beam.get('seen_t', -math.inf) <= MEMORY_S+1e-9)
        beam = beam if fresh else None
        self.crate_source = ('current' if vis['visible_probes'] >= 5 else 'memory') if beam else 'none'
        self.focus = beam['ends'].get(end) if beam else None
        body = world['objects'].get(profile.item_id)
        if self.focus is None and body is not None and profile.item_id in vis['objects']:
            self.focus = body['xy']
        # Expired search/relook matches crate14's walls-only pulse policy.
        self.walls_only = search and beam is None
        if not self.walls_only:
            self.rectangles += [('peer', (*v['pose'][:2], HALF_X, HALF_Y, v['pose'][2]))
                                for key, v in world['robots'].items() if key != rid]
            if beam is not None:
                x, y, a = beam['pose']; c, s = math.cos(a), math.sin(a)
                self.rectangles += [('crate', (x+c*d, y+s*d, hx, hy, a))
                                    for d, hx, hy in ((0., .07, .05), (-.09, .03, .02), (.09, .03, .02))]
            for key, obj in world['objects'].items():
                if key == profile.item_id:  # never substitute a circle for this crate
                    continue
                pad = .005 if folded and obj.get('top_z_bound_m', math.inf) <= .1 else .02+(.17-self.radius)
                self.circles.append(('other_cargo', (*obj['xy'], obj['radius']+pad)))
        self._clearance_cache = {}; self._segment_cache = {}; self._path_cache = {}
        self.budget = budget if budget is not None else {'remaining': MAX_TICK_EXPANSIONS}
        self.stats = {'expansions': 0, 'segment_calls': 0, 'segment_cache_hits': 0,
                      'budget_exhausted': 0, 'path_pads_m': []}

    def clearances(self, point, yaw, pad=.005):
        key = (*point[:2], yaw, pad)
        if key not in self._clearance_cache:
            values = [(kind, rectangle_gap((*point[:2], yaw), r, pad)) for kind, r in self.rectangles]
            values += [(kind, math.dist(point[:2], d[:2])-d[2]-self.radius-(pad-.005))
                       for kind, d in self.circles]
            x, y = point[:2]; c, s = abs(math.cos(yaw)), abs(math.sin(yaw))
            ex, ey = HALF_X*c+HALF_Y*s, HALF_X*s+HALF_Y*c
            x0, x1, y0, y1 = self.bounds
            values.append(('bounds', min(x-ex-x0, x1-x-ex, y-ey-y0, y1-y-ey)-pad))
            self._clearance_cache[key] = tuple(values)
        return self._clearance_cache[key]

    def free(self, point, yaw, pad=.005):
        return all(v > 0. for _, v in self.clearances(point, yaw, pad))

    def segment(self, a, b, ayaw, byaw, pad=.005):
        key = (*a[:2], *b[:2], ayaw, byaw, pad)
        self.stats['segment_calls'] += 1
        if key in self._segment_cache:
            self.stats['segment_cache_hits'] += 1
            return self._segment_cache[key]
        # Per-obstacle no-closer rule: an admitted pose inside a margin may
        # retreat/rotate, but cannot reduce that obstacle's initial clearance.
        # Once outside the margin it must remain outside. No mm slack.
        limits = [min(0., v) for _, v in self.clearances(a, ayaw, pad)]
        da = math.atan2(math.sin(byaw-ayaw), math.cos(byaw-ayaw))
        n = max(1, math.ceil(math.dist(a[:2], b[:2])/.002), math.ceil(abs(da)/math.radians(.5)))
        safe = True
        for i in range(1, n+1):
            values = self.clearances((a[0]+(b[0]-a[0])*i/n, a[1]+(b[1]-a[1])*i/n), ayaw+da*i/n, pad)
            if any(v < limit-1e-9 for (_, v), limit in zip(values, limits)):
                safe = False; break
            limits = [max(limit, min(0., v)) for (_, v), limit in zip(values, limits)]
        self._segment_cache[key] = safe
        return safe

    def heading_at(self, point, fallback):
        if self.focus is None: return fallback
        return math.atan2(self.focus[1]-point[1], self.focus[0]-point[0])

    def path(self, start, goal, heading):
        key = (*start[:2], *goal[:2], heading)
        if key not in self._path_cache:
            path = None
            for pad in PADS_M:
                path = self._path(start, goal, heading, pad)
                if path:
                    self.stats['path_pads_m'].append(pad); break
            self._path_cache[key] = path
        value = self._path_cache[key]
        return list(value) if value else None

    def _path(self, start, goal, heading, pad):
        if not self.free(goal, heading, pad): return None
        if self.segment(start, goal, self.pose[2], heading, pad): return [tuple(start), tuple(goal)]
        cell = lambda p: (round(p[0]/GRID_M), round(p[1]/GRID_M))
        point = lambda k: (k[0]*GRID_M, k[1]*GRID_M)
        sc = cell(start); front = []; cost = {}; came = {}; closed = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                k = (sc[0]+dx, sc[1]+dy); p = point(k); yaw = self.heading_at(p, heading)
                if self.free(p, yaw, pad) and self.segment(start, p, self.pose[2], yaw, pad):
                    cost[k] = math.dist(start, p); came[k] = None
                    heapq.heappush(front, (cost[k]+math.dist(p, goal), k))
        steps = 0; final = None
        while front and steps < MAX_EXPANSIONS and self.budget['remaining'] > 0:
            _, k = heapq.heappop(front); steps += 1; self.budget['remaining'] -= 1
            self.stats['expansions'] += 1
            if k in closed: continue
            closed.add(k); p = point(k); yaw = self.heading_at(p, heading)
            if math.dist(p, goal) <= GRID_M*1.5 and self.segment(p, goal, yaw, heading, pad):
                final = k; break
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if not dx and not dy: continue
                    nxt = (k[0]+dx, k[1]+dy); q = point(nxt); qyaw = self.heading_at(q, heading)
                    new = cost[k]+math.dist(p, q)
                    if nxt in closed or new >= cost.get(nxt, math.inf) or not self.free(q, qyaw, pad): continue
                    if not self.segment(p, q, yaw, qyaw, pad): continue
                    cost[nxt] = new; came[nxt] = k
                    heapq.heappush(front, (new+math.dist(q, goal), nxt))
        if final is None:
            self.stats['budget_exhausted'] += int(bool(front)); return None
        route = [tuple(goal)]
        while final is not None: route.append(point(final)); final = came[final]
        return [tuple(start), *reversed(route)]

    def waypoint(self, start, path, target):
        if not path: return None
        nearest = min(range(len(path)), key=lambda i: math.dist(start, path[i])); best = None
        for p in path[nearest:]:
            distance = math.dist(start, p)
            if distance < .001: continue
            yaw = math.atan2(target[1]-p[1], target[0]-p[0])
            if self.segment(start, p, self.pose[2], yaw):
                best = p
                if distance >= .12: break
            elif best is not None: break
        return best

    def pulse_safe(self, value):
        if not any(value['wheels']): return True
        times = sorted({0., .1, *(i*.005 for i in range(1, 20)), *(min(.1, d) for d in value['duration_s'])})
        x, y, a = self.pose
        # Each subsegment enforces no-closer from its own start. This is at
        # least as strict as a single initial floor for the entire lease.
        for ta, tb in zip(times, times[1:]):
            dx, dy, da = command_delta({**value, 'duration_s': [max(0., d-ta) for d in value['duration_s']]}, tb-ta)
            c, s = math.cos(a+da/2), math.sin(a+da/2); end = (x+c*dx-s*dy, y+s*dx+c*dy)
            if not self.segment((x, y), end, a, a+da): return False
            x, y = end; a += da
        return True
