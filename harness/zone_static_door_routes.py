"""T09a: static door candidates, never an executor or an admission gate.

Inputs are an authored map, an allowed own/coarse cargo pose, a public goal,
and a selected catalogue formation. No scenario, inventory, events, peers or
referee enter this API. The caller must preserve that provenance. All four
communication conditions use this same API and motion contract.

V1 supports fixed east/west item heading and stopped axial/lateral legs only.
It checks continuous translation of every cargo/chassis/arm polygon, including
the authored start and final goal. It does not search rotations or arbitrary
detours. A refusal is not proof that no geometric path exists. M1/M2 wiring,
observed blockage, localization uncertainty and physical validation are T09b.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from harness import static_keepouts as ko
from harness.zone_team_footprint import BOX_KINDS, CATALOGUE, convex_hull
from harness.zone_team_footprint_v3 import team_footprint

VERSION = 'ugrp.static_door_routes.v1'
FOOTPRINT_MARGIN_M = .03
EXIT_PAD_M = .02
EPS = 1e-9


@dataclass(frozen=True)
class MotionContract:
    """Common bounded fixed-heading XY primitive; not runtime support evidence."""
    version: str = 'fixed_heading_xy_v1'
    max_leg_m: float = .85
    max_legs: int = 8


@dataclass(frozen=True)
class Refusal:
    passage_id: str | None
    reason: str


@dataclass(frozen=True)
class DoorRoute:
    passage_id: str
    direction: str
    poses_m_rad: tuple[tuple[float, float, float], ...]
    travel_heading_rad: tuple[float, ...]

    @property
    def length_m(self):
        return sum(math.dist(a[:2], b[:2]) for a, b in zip(self.poses_m_rad, self.poses_m_rad[1:]))


@dataclass(frozen=True)
class DoorPlans:
    routes: tuple[DoorRoute, ...] = ()
    refusals: tuple[Refusal, ...] = ()

    @property
    def selected(self):
        """Shortest accepted candidate, ties by passage ID; no host role choice."""
        return self.routes[0] if self.routes else None


class _Reject(ValueError):
    pass


def _vector(value, size):
    if not isinstance(value, (list, tuple)) or len(value) != size or any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value
    ):
        raise _Reject('INVALID_INPUT')
    return tuple(float(v) for v in value)


def _rectangle(row):
    if not isinstance(row, dict):
        raise _Reject('INVALID_MAP')
    cx, cy = _vector(row.get('center_m'), 2)
    hx, hy = _vector(row.get('half_extents_m'), 2)
    yaw, = _vector([row.get('yaw_rad', 0.)], 1)
    if min(hx, hy) <= 0:
        raise _Reject('INVALID_MAP')
    return cx, cy, hx, hy, yaw


def _geometry(static_map):
    if not isinstance(static_map, dict) or {'eval', 'setup', 'hidden_events'} & static_map.keys():
        raise _Reject('INVALID_STATIC_MAP')
    bounds = _vector(static_map.get('bounds_m'), 4)
    if not (bounds[0] < bounds[1] and bounds[2] < bounds[3]):
        raise _Reject('INVALID_MAP')
    # Require the obstacle list: missing geometry must never mean free space.
    rows = static_map.get('obstacles')
    terrain = static_map.get('terrain', [])
    passages = static_map.get('passages')
    if any(not isinstance(v, (list, tuple)) for v in (rows, terrain, passages)):
        raise _Reject('INVALID_MAP')
    rects = tuple(_rectangle(r) for r in (*rows, *terrain))
    ids = set()
    for p in passages:
        if not isinstance(p, dict) or not isinstance(p.get('id'), str) or not p['id'] or p['id'] in ids:
            raise _Reject('INVALID_MAP')
        ids.add(p['id'])
    return bounds, rects, sorted((p for p in passages if p.get('kind') == 'door'), key=lambda p: p['id'])


def _formation(kind, roles, robot_model):
    if robot_model != 'masterpi_v3':
        raise _Reject('UNSUPPORTED_ROBOT_MODEL')
    if not isinstance(kind, str) or (kind not in BOX_KINDS and kind not in CATALOGUE):
        raise _Reject('UNSUPPORTED_CARGO')
    if not isinstance(roles, (list, tuple)) or any(not isinstance(r, str) for r in roles):
        raise _Reject('INVALID_FORMATION')
    allowed = (('west',),) if kind in BOX_KINDS else CATALOGUE[kind].formations
    # Never accept just one carrier of a pair or a cropped point/disc envelope.
    formation = next((f for f in allowed if len(roles) == len(f) and set(roles) == set(f)), None)
    if formation is None:
        raise _Reject('INVALID_FORMATION')
    return team_footprint({'robot_model': robot_model}, kind, formation, margin=FOOTPRINT_MARGIN_M)


def _continuous_clear(a, b, parts, rects, bounds):
    """Exact swept polygons for translation, avoiding sample gaps at corners."""
    obstacles = [ko.rect_corners(r) for r in rects]
    x0, x1, y0, y1 = bounds
    for part in parts:
        sweep = convex_hull(ko.polygon_at(a, part) + ko.polygon_at(b, part))
        if any(not (x0 < x < x1 and y0 < y < y1) for x, y in sweep):
            return False
        if any(ko.polygons_overlap(sweep, obstacle) for obstacle in obstacles):
            return False
    return True


def _candidate(passage, start, goal, footprint, rects, bounds, motion):
    if passage.get('axis') != 'x' or passage.get('alias_of') is not None:
        raise _Reject('UNSUPPORTED_PASSAGE')
    cx, cy, hx, hy, yaw = _rectangle(passage)
    width, = _vector([passage.get('width_m')], 1)
    if yaw != 0. or width <= 0. or abs(width - 2 * hy) > EPS:
        raise _Reject('INVALID_PASSAGE_GEOMETRY')
    vertices = [v for part in footprint.parts for v in ko.polygon_at((0., 0., start[2]), part)]
    xmin, xmax = min(x for x, _ in vertices), max(x for x, _ in vertices)
    ymin, ymax = min(y for _, y in vertices), max(y for _, y in vertices)
    if ymax - ymin >= width - EPS:
        raise _Reject('FOOTPRINT_TOO_WIDE')
    if start[0] + xmax < cx - hx and goal[0] + xmin > cx + hx:
        sign, direction = 1, 'west_to_east'
        exit_x = cx + hx - xmin + EXIT_PAD_M
    elif start[0] + xmin > cx + hx and goal[0] + xmax < cx - hx:
        sign, direction = -1, 'east_to_west'
        exit_x = cx - hx - xmax - EXIT_PAD_M
    else:
        raise _Reject('ENDPOINTS_NOT_ACROSS_DOOR')
    # Do not overshoot a goal that already clears the wall by less than EXIT_PAD.
    exit_x = min(exit_x, goal[0]) if sign == 1 else max(exit_x, goal[0])
    # Match the shared convex-hull precision; sin(pi) must not add a phantom
    # lateral leg to a symmetric east/west formation.
    axis_y = round(cy - (ymin + ymax) / 2, 12)
    keys = [start, (start[0], axis_y, start[2]), (exit_x, axis_y, start[2]),
            (exit_x, goal[1], start[2]), goal]
    route = [start]
    for a, b in zip(keys, keys[1:]):
        distance = math.dist(a[:2], b[:2])
        if distance == 0.:
            continue
        if not _continuous_clear(a, b, footprint.parts, rects, bounds):
            raise _Reject('STATIC_SWEEP_BLOCKED')
        # Reject before division: a finite but tiny user limit must not overflow
        # or allocate an unbounded path while trying to honour the contract.
        if distance > motion.max_leg_m * (motion.max_legs - len(route) + 1):
            raise _Reject('CONTROLLER_SEGMENT_LIMIT')
        count = math.ceil(distance / motion.max_leg_m)
        if len(route) - 1 + count > motion.max_legs:
            raise _Reject('CONTROLLER_SEGMENT_LIMIT')
        route.extend(b if i == count else
                     (a[0] + (b[0] - a[0]) * i / count,
                      a[1] + (b[1] - a[1]) * i / count, start[2]) for i in range(1, count + 1))
    return DoorRoute(passage['id'], direction, tuple(route),
                     tuple(math.atan2(b[1] - a[1], b[0] - a[0]) for a, b in zip(route, route[1:])))


def plan_door_routes(static_map, start_pose, goal_pose, *, cargo_kind, roles,
                     robot_model, passage_id=None, motion=MotionContract()):
    """Return sorted static candidate routes and explicit refusals, with no side effects.

    Poses are of the cargo frame, never the base of one carrier. `roles` selects
    a complete catalogue formation, not actor IDs. `robot_model` is explicit so
    legacy maps cannot silently select a v2 footprint. This API does not load a
    map, mutate a scenario, install a controller or report passage completion.
    Terrain is conservatively treated as a fixed obstacle. Unknown obstacles
    and future events are absent; T09b must establish an allowed observation
    boundary before replanning. No condition-specific overrides are accepted.
    """
    try:
        bounds, rects, doors = _geometry(static_map)
        start, goal = _vector(start_pose, 3), _vector(goal_pose, 3)
        if not isinstance(motion, MotionContract) or motion.version != 'fixed_heading_xy_v1':
            raise _Reject('UNSUPPORTED_MOTION')
        leg, = _vector([motion.max_leg_m], 1)
        if not 0 < leg <= .85 or type(motion.max_legs) is not int or not 0 < motion.max_legs <= 8:
            raise _Reject('INVALID_MOTION')
        delta = (goal[2] - start[2] + math.pi) % (2 * math.pi) - math.pi
        if abs(delta) > EPS or abs(math.sin(start[2])) > EPS:
            raise _Reject('UNSUPPORTED_ROTATION')
        # Equivalent wrapped headings have exactly the same path geometry.
        heading = 0. if math.cos(start[2]) > 0 else math.pi
        start, goal = (*start[:2], heading), (*goal[:2], heading)
        footprint = _formation(cargo_kind, roles, robot_model)
        if passage_id is not None:
            doors = [p for p in doors if p['id'] == passage_id]
            if not doors:
                raise _Reject('UNKNOWN_DOOR')
        if not doors:
            raise _Reject('NO_DOORS')
        if not _continuous_clear(start, start, footprint.parts, rects, bounds):
            raise _Reject('START_FOOTPRINT_BLOCKED')
        if not _continuous_clear(goal, goal, footprint.parts, rects, bounds):
            raise _Reject('GOAL_FOOTPRINT_BLOCKED')
    except _Reject as error:
        return DoorPlans(refusals=(Refusal(None, str(error)),))
    routes, refusals = [], []
    for door in doors:
        try:
            routes.append(_candidate(door, start, goal, footprint, rects, bounds, motion))
        except _Reject as error:
            refusals.append(Refusal(door['id'], str(error)))
    return DoorPlans(tuple(sorted(routes, key=lambda r: (r.length_m, r.passage_id))), tuple(refusals))
