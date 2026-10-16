"""Finite pre-grasp goal set for the visible-only demonstration teacher.

Generate poses, reject unreachable/colliding ones, then minimize route cost.
Inputs are the visible/command-odometry world, never simulator state. See
experiments/2026-10-14-e2e18-grasp-rootcause/approach-goal-set.md for sources.
"""
import math
from sim.grasp_act_teacher import STATION_M, grasp_poses, wrap
from sim.grasp_act_visible_route import constraints, free, segment_free
from scripts.zone_teacher import PeerDisc, plan_path

ANGLES_DEG = (0, -15, 15, -30, 30, -45, 45, -60, 60, -75, 75, -90, 90)
DISTANCES_M = (STATION_M, .198, .208)


def geometry(world, rid, end, choice):
    pose = world['robots'][rid]['pose']
    point = world['beam']['ends'][end]
    offset, distance = choice
    heading = world['beam']['pose'][2] + (math.pi if end == 'blue' else 0.) + offset
    goal = (point[0] - distance * math.cos(heading), point[1] - distance * math.sin(heading))
    return pose, point, heading, goal


def nominal_goal_blocked(world, rid, end, bounds, folded, *, static_map_only=False):
    """Only a static obstruction of the nominal stance enables alternatives.

    A peer can move away: preserve the original planner's wait/replan behavior.
    Peers still participate in every route and alternative-goal collision test.
    A failed grid segment or route is not evidence of a blocked grasp stance.
    """
    # The map-handoff toggle shares the planner's exact clearance predicate,
    # but never treats observed cargo or a temporary peer as a map obstruction.
    source = ({'robots': {rid: world['robots'][rid]}, 'objects': {},
               'beam': world['beam'], 'walls': world.get('walls', [])}
              if static_map_only else world)
    radius, discs, rects = constraints(source, rid, folded)
    if static_map_only:discs = []
    goal = geometry(world, rid, end, (0., STATION_M))[3]
    x0, x1, y0, y1 = bounds
    return (not (x0+radius <= goal[0] <= x1-radius and y0+radius <= goal[1] <= y1-radius)
            or not free(goal, [d for d in discs if not isinstance(d, PeerDisc)], rects, radius))


def select_goal(world, rid, end, bounds, folded, current=(0., STATION_M), *, choices=None, navigation=None):
    """Fallback after nominal_goal_blocked; keep an already selected stance.

    Angles stay on the assigned end's outward half-circle. Distances must pass
    the existing descent/hover IK, and every path segment keeps the unchanged
    collision margin (including the exact start and terminal segment).
    """
    from sim.grasp_act_visible_route import free, segment_free
    from scripts.zone_teacher import plan_path
    if navigation is not None:
        free,segment_free,plan_path=navigation.free,navigation.segment_free,navigation.plan_path
    radius, discs, rects = constraints(world, rid, folded)
    start = world['robots'][rid]['pose'][:2]
    x0, x1, y0, y1 = bounds
    checked = []; reachable = {}

    def candidate(choice):
        pose, point, heading, goal = geometry(world, rid, end, choice)
        distance = choice[1]
        if distance not in reachable:
            try:
                grasp_poses((distance, 0., point[2])); reachable[distance] = True
            except ValueError:
                reachable[distance] = False
        row = {'offset_deg': math.degrees(choice[0]), 'distance_m': distance, 'goal': goal}
        checked.append(row)
        if not reachable[distance]:row['reason'] = 'ik_unreachable'; return None
        if not (x0+radius <= goal[0] <= x1-radius and y0+radius <= goal[1] <= y1-radius):
            row['reason'] = 'outside_bounds'; return None
        if not free(goal, discs, rects, radius):row['reason'] = 'blocked_goal'; return None
        # Avoid A* for a clear direct route, including a robot already at goal.
        if segment_free(start, goal, discs, rects, radius):
            path = [tuple(start), goal]
        else:
            path = plan_path(start, goal, bounds, discs, rects=rects, radius=radius)
        if not path:row['reason'] = 'no_path'; return None
        points = [tuple(start), *path]
        if not all(segment_free(a, b, discs, rects, radius) for a, b in zip(points, points[1:])):
            row['reason'] = 'unsafe_segment'; return None
        cost = sum(math.dist(a, b) for a, b in zip(points, points[1:])) + .02*abs(wrap(heading-pose[2]))
        row.update(reason='feasible', cost=cost)
        return {'choice': choice, 'goal': goal, 'heading': heading, 'path': path, 'cost': cost}

    best = candidate(current)
    if best is None:
        alternatives = []
        candidates = ([(math.radians(a), d) for a in ANGLES_DEG for d in DISTANCES_M]
                      if choices is None else choices)
        for choice in candidates:
            if choice == current:continue
            item = candidate(choice)
            if item is not None:alternatives.append(item)
        # The narrow axial set first minimizes departure from the nominal
        # distance; the original wide-angle comparison keeps route-cost order.
        rank = ((lambda p:p['cost']) if choices is None else
                (lambda p:(abs(p['choice'][1]-STATION_M),p['cost'])))
        best = min(alternatives, key=rank) if alternatives else None
    return best, checked
