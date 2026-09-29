"""Static passage (door / corridor) planning for the pair-carry route (issue #221 follow-up).

`harness.zone_pair_executor.make_plan` only knows the M2 door (`door_1`, 0.5 m at
x = 2.2). Any other map raises `UNSUPPORTED_PAIR_MAP`, so corridor and two-door
maps could not be measured. This module adds an OPT-IN route builder for those
maps. It is pure static geometry (map JSON + the coarse order sheet): no world,
no simulator, no peer state. A planned route is not physical passage proof; the
controller still follows it with its own camera and its own SweepGuard.

Reused, not rebuilt:

* obstacles / terrain / envelope test / A* -> `harness.map_goto` (`authored_obstacles`,
  `envelope_overlaps`, `plan_path`, `interior_bounds`, `MARGIN_M`).
* controller safety margin -> `harness.zone_own_guards.SweepGuard` (the same object the
  pair guards build from the static map), used offline for the passage slack report.
* leg schedule (axial / lateral legs, own-estimate axis alignment at every leg start,
  <= 0.85 m legs) -> the frozen M2 controller (RoutedM2 in `harness.zone_pair_executor`, unchanged).
* plan assembly -> the frozen `make_plan` itself (called on the M2 door map for everything that is not the
  route), so pre-stations, keep-outs and beam geometry are byte-identical to the registered plan.

The executor / team-host files are NOT edited: they are hash-pinned by the registered v6-family source
closure. The opt-in is `install()` (process-local swap of `zone_pair_executor.make_plan`), used by
scripts/run_pair_stage_probes.py for `case['pair_passage']`. Folding it into make_plan is a ~10 line change
recorded in experiments/2026-09-29-pair-passage-map/adopt_in_executor.patch for the next registration.

Scope (see experiments/2026-09-29-pair-passage-map/README.md): passages whose axis
is x (the beam's long axis runs along the passage), route legs axial/lateral only,
terrain is an obstacle to avoid (loaded terrain crossing is unvalidated), route
length bounded by the frozen 8-segment status protocol.

CLI (plan only, imports no simulator):
    python -m harness.pair_passage_plan --map zone_wide_corridor_tags_v3 --target A
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'ugrp.pair_passage_plan.v1'

# Static footprint of the loaded pair (beam + both carriers). MUST equal the literal in
# harness.zone_pair_executor.make_plan (pinned by tests/test_pair_passage_plan.py).
PAIR_ENVELOPE = {'x_m': [-.625, .625], 'y_m': [-.20, .20]}
ROUTE_MARGIN_M = .02        # harness.map_goto.MARGIN_M (the A* obstacle margin)
EXIT_PAD_M = .05            # beam trailing edge clears the passage end by this much before a lateral leg
LEGACY_EXIT_M = 1.0         # M2 door route: lateral leg at door x + 1.0 (scripts.run_m2_pair DOOR_PLAN target 3.20)
DOOR_ALIGN_MAX_M = .15      # scripts.run_m2_pair.DOOR_ALIGN_MAX_M: own axis alignment clamp at each leg start
LEG_MAX_M = .85             # make_plan's carry/relocalize cadence (split length)
MAX_LEGS = 8                # harness.zone_pair_status.MAX_SEGMENTS (frozen status protocol)
PRIOR_STD = (.03, .012)     # harness.pair_stage_probe.E2E_MATCHED_PRIOR (own-pose std at carry start)
TRAVERSABLE_KINDS = ('door', 'corridor')
DECLARED_TOL_M = .005
SCAN_STEP_M = .1


class PassageRefusal(ValueError):
    """A static-map refusal with an explicit reason code (str(e) is the code)."""

    def __init__(self, code, **detail):
        super().__init__(code)
        self.code, self.detail = code, detail


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def load_map(map_id):
    return json.loads((ROOT / 'maps' / 'zones' / f'{map_id}.json').read_text())


# ------------------------------------------------------------------ map -> passages
def traversable_passages(static_map):
    """Doors and corridors of the public map. Passing bays are waiting places, never routes.

    `executor_view` aliases are not passages of the map and are skipped.
    """
    return [p for p in static_map.get('passages', ()) if p.get('kind') in TRAVERSABLE_KINDS and 'alias_of' not in p]


def executor_view(static_map):
    """Probe-only map view that `ZoneOwnExecutor.__init__` accepts on a map without a door-kind passage.

    harness/zone_own_executor.py:134 takes `next(p for p in passages if p['kind'] == 'door')`: a corridor map
    (kind 'corridor') raises StopIteration when the per-robot executor is built, before any pair code runs. The
    executor is hash-pinned by the registered source closure, so this view appends an ALIAS door entry
    (`alias_of` marks it; the planner ignores it and the plan hashes the map without it). Only the solo `goto`
    door waypoint and the status passage label use that entry; the pair carry uses neither. Returns the map
    unchanged when it already has a door-kind passage.
    """
    passages = static_map.get('passages', ())
    if any(p.get('kind') == 'door' for p in passages):
        return static_map
    first = traversable_passages(static_map)
    if not first:
        return static_map
    view = copy.deepcopy(static_map)
    alias = {**copy.deepcopy(first[0]), 'id': first[0]['id'] + '_executor_alias', 'kind': 'door', 'alias_of': first[0]['id']}
    view['passages'] = [*view['passages'], alias]
    return view


def without_aliases(static_map):
    if not any('alias_of' in p for p in static_map.get('passages', ())):
        return static_map
    stripped = copy.deepcopy(static_map)
    stripped['passages'] = [p for p in stripped['passages'] if 'alias_of' not in p]
    return stripped


def passage_by_id(static_map, passage_id):
    return next(p for p in static_map['passages'] if p['id'] == passage_id)


def _extent(passage):
    """(along-axis interval, cross-axis centre, declared cross half width) for an axis-x/y passage."""
    (cx, cy), (hx, hy) = passage['center_m'], passage['half_extents_m']
    if passage['axis'] == 'x':
        return (cx - hx, cx + hx), cy, hy
    return (cy - hy, cy + hy), cx, hx


def required_width(axis, *, envelope=PAIR_ENVELOPE, margin=ROUTE_MARGIN_M):
    """Cross-axis width the loaded pair needs. The pair's long axis is x.

    axis 'x' (beam runs along the passage): the envelope's y extent, i.e. the beam and the
    chassis widths. axis 'y' (the pair crosses sideways): the envelope's x extent, i.e. the
    beam length plus the two-robot spacing.
    """
    lo, hi = envelope['y_m'] if axis == 'x' else envelope['x_m']
    return (hi - lo) + 2 * margin


def measured_opening(static_map, passage, step=.0125):
    """Free interval around the passage centre line, from the authored obstacles (walls + terrain).

    Sweeps the passage's along-axis extent; the binding cross-section is the smallest free
    interval. Returns lower/upper edge distances from the centre line at their tightest x.
    Independent of the passage's declared width_m (which is only cross-checked).
    """
    from harness.map_goto import authored_obstacles, interior_bounds

    if passage['axis'] != 'x':
        raise PassageRefusal('PAIR_PASSAGE_AXIS_UNSUPPORTED', axis=passage['axis'])
    (x0, x1), yc, _ = _extent(passage)
    obstacles = authored_obstacles(static_map)
    bx0, bx1, by0, by1 = interior_bounds(static_map)
    n = max(1, math.ceil((x1 - x0) / step))
    best = {'width_m': math.inf}
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        lower, upper, low_id, up_id = by0, by1, 'map_bound', 'map_bound'
        for o in obstacles:
            (cx, cy), (hx, hy) = o['center_m'], o['half_extents_m']
            if not cx - hx <= x <= cx + hx:
                continue
            if cy - hy < yc < cy + hy:
                lower, upper, low_id, up_id = yc, yc, o['id'], o['id']
                break
            if cy + hy <= yc and cy + hy > lower:
                lower, low_id = cy + hy, o['id']
            if cy - hy >= yc and cy - hy < upper:
                upper, up_id = cy - hy, o['id']
        width = upper - lower
        if width < best['width_m'] or (width == best['width_m'] and i == 0):
            best = {'width_m': width, 'x_m': x, 'lower_m': yc - lower, 'upper_m': upper - yc,
                    'lower_id': low_id, 'upper_id': up_id}
    return best


def check_passage(static_map, passage, *, envelope=PAIR_ENVELOPE, margin=ROUTE_MARGIN_M):
    """Width verdict for the loaded pair. Raises PassageRefusal; returns the numbers otherwise."""
    axis = passage.get('axis')
    need = required_width(axis, envelope=envelope, margin=margin)
    if axis != 'x':
        # The pair is ~1.25 m long: a passage along y must be that wide (plus margin) to cross sideways.
        code = 'PAIR_PASSAGE_TOO_NARROW' if passage.get('width_m', 0.) < need else 'PAIR_PASSAGE_AXIS_UNSUPPORTED'
        raise PassageRefusal(code, axis=axis, declared_width_m=passage.get('width_m'), required_width_m=need)
    (_, yc, hy) = _extent(passage)
    declared = float(passage['width_m'])
    if abs(declared - 2 * hy) > DECLARED_TOL_M:
        raise PassageRefusal('PAIR_PASSAGE_MAP_INCONSISTENT', declared_width_m=declared, half_extents_width_m=2 * hy)
    opening = measured_opening(static_map, passage)
    detail = {'declared_width_m': declared, 'measured_free_width_m': opening['width_m'],
              'required_width_m': need, 'binding': opening}
    if opening['width_m'] < need - 1e-9:
        raise PassageRefusal('PAIR_PASSAGE_TOO_NARROW', **detail)
    half = need / 2
    if min(opening['lower_m'], opening['upper_m']) < half - 1e-9 or abs(opening['width_m'] - declared) > DECLARED_TOL_M:
        # Wide enough in total, but the declared centre line is not the middle of the opening.
        raise PassageRefusal('PAIR_PASSAGE_MAP_INCONSISTENT', **detail)
    detail['slack_per_side_m'] = opening['width_m'] / 2 - half
    return detail


# ------------------------------------------------------------------ controller guard margin (offline)
def _station_offsets():
    """Carrier base offsets from the beam centre for a beam at yaw 0 (static catalogue geometry)."""
    from scripts import run_m2_pair as m2
    from sim.zone_cargo import instances, world_grasps

    pose = [0., 0., 0.]
    item = instances([{'item_id': 'ordered_beam', 'kind': 'long_beam', 'pose': pose}])[0]
    grasps = world_grasps(item, pose=pose)
    return {r: list(grasps[role]['base_xyyaw']) for r, role in m2.ROLES.items()}


def guard_slack(static_map, passage, x_range, *, sigma=PRIOR_STD, offsets=None):
    """Offline SweepGuard chassis clearance of both carriers with the beam on the passage centre line.

    Same object and margin formula the pair guards use in flight (`harness.zone_own_guards.SweepGuard`:
    base margin + residual + 2 sigma_xy + 2 sigma_yaw * lever). Chassis only: arm and beam sweeps are not
    included. Returns the minimum clearance at the stated prior sigma, the largest sigma_xy that still clears
    (with the stated sigma_yaw), and the largest whole-pair yaw offset that clears at sigma 0.
    """
    from harness.zone_own_guards import SIGMA_CAP_XY_M, OwnPose, SweepGuard

    offsets = offsets or _station_offsets()
    guard = SweepGuard(static_map)
    (_, yc, _) = _extent(passage)
    xs = [x_range[0] + SCAN_STEP_M * i for i in range(int((x_range[1] - x_range[0]) / SCAN_STEP_M) + 1)]

    def poses(theta):
        c, s = math.cos(theta), math.sin(theta)
        for x in xs:
            for dx, dy, yaw in offsets.values():
                yield x + c * dx - s * dy, yc + s * dx + c * dy, yaw + theta

    def clearance(sxy, syaw, theta=0.):
        return min(guard.chassis_clearance(OwnPose(px, py, yaw, sxy, syaw))[0] for px, py, yaw in poses(theta))

    at_prior = clearance(*sigma)
    lo, hi = 0., SIGMA_CAP_XY_M
    if clearance(hi, sigma[1]) >= 0:
        max_sxy = hi
    elif clearance(lo, sigma[1]) < 0:
        max_sxy = 0.
    else:
        for _ in range(9):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if clearance(mid, sigma[1]) >= 0 else (lo, mid)
        max_sxy = lo
    lo, hi = 0., .5
    if clearance(0., 0., hi) >= 0:
        max_yaw = hi
    else:
        for _ in range(9):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if clearance(0., 0., mid) >= 0 else (lo, mid)
        max_yaw = lo
    return {'source': 'harness.zone_own_guards.SweepGuard.chassis_clearance (offline, static map)',
            'prior_sigma_xy_m': sigma[0], 'prior_sigma_yaw_rad': sigma[1],
            'min_clearance_at_prior_m': at_prior, 'max_sigma_xy_m': max_sxy, 'max_pair_yaw_offset_rad': max_yaw,
            'scope': 'carrier chassis only; arm and beam sweeps and loaded gate stops are not modelled here'}


# ------------------------------------------------------------------ route
def _sweep_blocker(route, envelope, obstacles, bounds, margin):
    """First reason the axis-aligned route is not clear for the fixed-heading envelope, or None."""
    from harness.map_goto import envelope_overlaps

    x0, x1, y0, y1 = bounds
    for a, b in zip(route, route[1:]):
        n = max(1, math.ceil(math.dist(a, b) / .02))
        for i in range(n + 1):
            p = [a[k] + (b[k] - a[k]) * i / n for k in (0, 1)]
            if not (x0 <= p[0] + envelope['x_m'][0] and p[0] + envelope['x_m'][1] <= x1
                    and y0 <= p[1] + envelope['y_m'][0] and p[1] + envelope['y_m'][1] <= y1):
                return 'PAIR_ROUTE_OUTSIDE_MAP', None
            for o in obstacles:
                if envelope_overlaps(p, envelope, o, margin):
                    return ('PAIR_PASSAGE_ROUTE_CROSSES_UNVALIDATED_TERRAIN' if o['id'].startswith('unvalidated_')
                            else 'PAIR_PASSAGE_ROUTE_BLOCKED'), o['id']
    return None, None


def split_legs(route, limit=LEG_MAX_M):
    """The same <= 0.85 m split `make_plan` applies (kept identical so the leg count is exact)."""
    out = [list(route[0])]
    for a, b in zip(route, route[1:]):
        n = max(1, math.ceil(math.dist(a, b) / limit))
        out.extend([[a[k] + (b[k] - a[k]) * i / n for k in (0, 1)] for i in range(1, n + 1)])
    return out


def _is_m2_door_geometry(passage):
    return passage.get('axis') == 'x' and passage['center_m'] == [2.2, .05] and passage.get('width_m') == .5


def axis_route(static_map, pose, target_zone, passage, *, envelope=PAIR_ENVELOPE):
    """Un-split axis-aligned key points: (lateral to the axis) -> through the passage -> (lateral, axial) to the zone."""
    (x_in, x_out), yc, _ = _extent(passage)
    px, py = float(pose[0]), float(pose[1])
    tx, ty = static_map['regions']['zone_' + target_zone]['center_m']
    ex1 = envelope['x_m'][1]
    x_exit = max(x_out + ex1 + EXIT_PAD_M, passage['center_m'][0] + LEGACY_EXIT_M)
    if px + ex1 > x_in - ROUTE_MARGIN_M:
        raise PassageRefusal('PAIR_PASSAGE_PICKUP_TOO_CLOSE', pickup_x_m=px, passage_start_x_m=x_in)
    # Within the controller's own alignment clamp the route snaps onto the axis (as the M2 door route does);
    # beyond it a lateral leg on the pickup side gets the beam onto the axis first.
    route = [[px, yc]] if abs(yc - py) <= DOOR_ALIGN_MAX_M else [[px, py], [px, yc]]
    if _is_m2_door_geometry(passage):
        # Same key points as the validated M2 route (checkpoints at beam x 1.55 / 2.40 -> 3.20).
        route.extend([[x, yc] for x in (1.55, 2.40) if x > px + 1e-6])
    route.append([x_exit, yc])
    for point in ([x_exit, ty], [tx, ty]):
        if math.dist(route[-1], point) > 1e-6:
            route.append(list(point))
    return route, x_exit


def passage_legs(route, info):
    """Route-leg indexes by role relative to the passage (for `--legs` of the stage probe).

    lateral_to_axis: pickup-side lateral legs before the first crossing leg (they bring the beam onto the axis).
    entry / inside / exit: on-axis axial legs whose beam envelope overlaps the passage x range
    (first / middle / last of them); all_crossing lists all of them.
    """
    x_in, x_out = info['x_range_m']
    yc = info['axis_y_m']
    ex0, ex1 = PAIR_ENVELOPE['x_m']
    crossing = []
    for k, (a, b) in enumerate(zip(route, route[1:])):
        on_axis = abs(a[1] - yc) < 1e-6 and abs(b[1] - yc) < 1e-6
        if on_axis and abs(b[0] - a[0]) > 1e-6 and max(a[0], b[0]) + ex1 > x_in and min(a[0], b[0]) + ex0 < x_out:
            crossing.append(k)
    first = crossing[0] if crossing else 0
    return {'lateral_to_axis': [k for k in range(first) if abs(route[k + 1][0] - route[k][0]) < 1e-6],
            'entry': crossing[:1], 'inside': crossing[1:-1], 'exit': crossing[-1:] if len(crossing) > 1 else [],
            'all_crossing': crossing}


def _astar(static_map, start, goal, envelope):
    """Reachability oracle for the fixed-heading pair envelope (harness.map_goto.plan_path, unchanged)."""
    from harness.map_goto import plan_path

    plan = plan_path(static_map, start, goal, envelope, margin_m=ROUTE_MARGIN_M)
    if plan is None:
        return None
    crossed = []
    for p in traversable_passages(static_map):
        (a0, a1), yc, hy = _extent(p)
        if p.get('axis') != 'x':
            continue
        for u, v in zip(plan['waypoints_m'], plan['waypoints_m'][1:]):
            n = max(1, math.ceil(math.dist(u, v) / .025))
            if any(a0 <= u[0] + (v[0] - u[0]) * i / n <= a1 and abs(u[1] + (v[1] - u[1]) * i / n - yc) <= hy
                   for i in range(n + 1)):
                crossed.append(p['id'])
                break
    return {'length_m': plan['length_m'], 'passages': crossed, 'planner': plan['planner']}


def _candidate(static_map, pose, target_zone, passage, envelope):
    """One passage -> a complete verdict (raises PassageRefusal)."""
    check = check_passage(static_map, passage, envelope=envelope)
    (x_range, yc, _) = _extent(passage)
    key, x_exit = axis_route(static_map, pose, target_zone, passage, envelope=envelope)
    route = split_legs(key)
    if len(route) - 1 > MAX_LEGS:
        raise PassageRefusal('PAIR_PASSAGE_TOO_MANY_SEGMENTS', legs=len(route) - 1, max_legs=MAX_LEGS, passage=passage['id'])
    from harness.map_goto import authored_obstacles, interior_bounds
    reason, blocker = _sweep_blocker(route, envelope, authored_obstacles(static_map), interior_bounds(static_map),
                                     ROUTE_MARGIN_M)
    if reason:
        raise PassageRefusal(reason, blocker=blocker, passage=passage['id'])
    guard = guard_slack(static_map, passage, (route[0][0], x_exit))
    if guard['min_clearance_at_prior_m'] < 0:
        raise PassageRefusal('PAIR_PASSAGE_GUARD_MARGIN', **guard)
    info = {'schema': SCHEMA, 'id': passage['id'], 'kind': passage['kind'], 'axis': passage['axis'],
            'axis_y_m': yc, 'x_range_m': list(x_range), 'exit_x_m': x_exit, **check,
            'envelope': copy.deepcopy(envelope), 'margin_m': ROUTE_MARGIN_M, 'guard': guard,
            'route_length_m': sum(math.dist(a, b) for a, b in zip(route, route[1:])), 'legs': len(route) - 1}
    info['leg_roles'] = passage_legs(route, info)
    return route, key, info


def plan_passage_route(static_map, pose, target_zone, passage='auto', *, envelope=PAIR_ENVELOPE):
    """Route + passage record for a passage map, or None when the frozen M2 door route applies (`door_1`).

    passage: 'auto' (shortest valid route) or a passage id. Raises PassageRefusal with an explicit code
    when the pair cannot pass. Returned dict: route (already split), key_points, door_plan (overrides for
    the M2 door plan), passage (report, hashed into the plan).
    """
    passages = traversable_passages(static_map)
    if not passages:
        raise PassageRefusal('PAIR_PASSAGE_NONE')
    if passage != 'auto':
        chosen = [p for p in passages if p['id'] == passage]
        if not chosen:
            raise PassageRefusal('PAIR_PASSAGE_UNKNOWN', passage=passage, known=[p['id'] for p in passages])
        passages = chosen
    from scripts import run_m2_pair as m2
    if len(passages) == 1 and passages[0]['id'] == m2.DOOR_PLAN['door_id'] and passages[0]['center_m'] == [2.2, .05] \
            and passages[0]['width_m'] == .5:
        return None                       # the frozen M2 door route (byte-identical legacy path)
    ok, refused = [], []
    for p in passages:
        try:
            ok.append(_candidate(static_map, pose, target_zone, p, envelope))
        except PassageRefusal as e:
            refused.append({'passage': p['id'], 'code': e.code})
            last = e
    if not ok:
        if len(refused) == 1:
            raise last                    # one candidate: its own explicit code
        tx, ty = static_map['regions']['zone_' + target_zone]['center_m']
        if _astar(static_map, [float(pose[0]), float(pose[1])], [tx, ty], envelope) is None:
            raise PassageRefusal('PAIR_NO_PATH_FOR_PAIR_ENVELOPE', refused=refused)   # the pair fits nowhere
        raise PassageRefusal('PAIR_PASSAGE_NONE_USABLE', refused=refused)              # a path exists, no axis route
    route, key, info = min(ok, key=lambda r: r[2]['route_length_m'])
    tx, ty = static_map['regions']['zone_' + target_zone]['center_m']
    info['selected_by'] = 'requested' if passage != 'auto' else 'shortest valid route'
    info['refused_candidates'] = refused
    info['a_star'] = _astar(static_map, [float(pose[0]), float(pose[1])], [tx, ty], envelope)
    info['target_zone'] = target_zone
    # Only door_id / axis / target / checkpoints matter to the frozen controller's constructor (segments and
    # per-leg axis are then overwritten by make_plan's route); headings stay the M2 pair headings.
    x0 = route[0][0]
    checkpoints = (1.55, 2.40) if _is_m2_door_geometry(passage_by_id(static_map, info['id'])) else tuple(
        round(x0 + (info['exit_x_m'] - x0) * f, 4) for f in (1 / 3, 2 / 3))
    door_plan = {'door_id': info['id'], 'axis_y_m': info['axis_y_m'], 'target_beam_x_m': info['exit_x_m'],
                 'checkpoints_beam_x_m': checkpoints}
    return {'route': route, 'key_points': key, 'door_plan': door_plan, 'passage': info}


# ------------------------------------------------------------------ plan assembly + opt-in install
TEMPLATE_MAP_ID = 'zone_wide_door_tags_v2_dock_v3'   # the M2 door map the frozen make_plan accepts
REFUSALS = []                                         # explicit refusal log of the installed wrapper (this process)


def _frozen_make_plan():
    from harness import zone_pair_executor

    return getattr(zone_pair_executor.make_plan, '_passage_legacy', zone_pair_executor.make_plan)


def passage_make_plan(static_map, sheet, target_zone, passage='auto'):
    """`harness.zone_pair_executor.make_plan` for passage maps (opt-in), built WITHOUT editing the executor.

    The frozen make_plan is called on the M2 door map for everything that does not depend on the passage
    (sheet validation, pre-stations, keep-outs, beam geometry); only the route, the door plan and the map hash
    come from this module. `passage=None` or the M2 door itself returns the frozen plan unchanged. Raises
    PassageRefusal (explicit code) for a passage map that cannot be used.
    """
    legacy = _frozen_make_plan()
    if passage is None:
        return legacy(static_map, sheet, target_zone)
    base = legacy(load_map(TEMPLATE_MAP_ID), sheet, target_zone)        # validates sheet, pickup envelope, grid
    planned = plan_passage_route(static_map, sheet['beam_xyyaw'], target_zone, passage)
    if planned is None:
        return legacy(static_map, sheet, target_zone)
    plan = copy.deepcopy(base)
    plan['route'] = planned['route']
    plan['door_plan'].update(planned['door_plan'])
    plan['map_sha256'] = digest(without_aliases(static_map))      # the file's map, not the executor view
    plan['passage'] = planned['passage']
    return plan


def install(passage='auto'):
    """Process-local opt-in: `zone_pair_executor.make_plan` becomes `passage_make_plan(..., passage)`.

    Nothing is installed by default, and the executor file stays byte-identical (it is hash-pinned by the
    registered v6-family source closure). Used by the stage-probe worker for `case['pair_passage']`.
    Refusals are appended to REFUSALS; the executor's own ack still says INVALID_PAIR_PLAN.
    """
    from harness import zone_pair_executor

    if hasattr(zone_pair_executor.make_plan, '_passage_legacy'):
        raise RuntimeError('passage planning already installed in this process')
    legacy = zone_pair_executor.make_plan

    def make_plan(static_map, sheet, target_zone):
        try:
            return passage_make_plan(static_map, sheet, target_zone, passage)
        except PassageRefusal as error:
            REFUSALS.append({'code': error.code, 'passage': passage, 'target_zone': target_zone,
                             'detail': json.loads(json.dumps(error.detail, default=str))})
            raise

    make_plan._passage_legacy = legacy
    zone_pair_executor.make_plan = make_plan
    return legacy


def uninstall():
    from harness import zone_pair_executor

    legacy = getattr(zone_pair_executor.make_plan, '_passage_legacy', None)
    if legacy is not None:
        zone_pair_executor.make_plan = legacy


# ------------------------------------------------------------------ stage-probe support
def passage_setup(map_id, *, passage='auto', target='B'):
    """A stage-probe setup for a passage map: the BASE_SETUP placement plus the map / passage / target opt-in.

    Consumed by `harness.pair_stage_probe.teacher_cases(setup=...)` (route via plan_route) and, through the
    case fields `map` / `pair_passage` / `target`, by scripts/run_pair_stage_probes.py.
    """
    from harness.pair_stage_probe import BASE_SETUP

    setup = copy.deepcopy(BASE_SETUP)
    setup.update(map_id=map_id, passage=passage, target=target)
    return setup


def map_tag(map_id):
    return map_id.removeprefix('zone_wide_')


def passage_teacher_cases(stage, map_id, *, passage='auto', target='B', **kw):
    """`pair_stage_probe.teacher_cases` on a passage map. Cases carry map / pair_passage / target (opt-in fields)."""
    from harness import pair_stage_probe as sp

    cases = sp.teacher_cases(stage, setup=passage_setup(map_id, passage=passage, target=target), **kw)
    for case in cases:
        case['case_id'] += ':M' + map_tag(map_id)
        case.update(map=map_id, pair_passage=passage, target=target)
    return cases


def passage_build_cases(args):
    """`--passage-map` branch of scripts/run_pair_stage_probes.build_cases (teacher source only)."""
    from harness import pair_stage_probe as sp

    cases = []
    for stage in args.stage:
        if not sp.STAGES[stage]['implemented']:
            raise ValueError(f'stage {stage} is not implemented here')
        for policy in args.policies:
            for leg in (args.legs or [None]):
                cases += passage_teacher_cases(stage, args.passage_map, passage=args.passage, target=args.passage_target,
                                               seeds=tuple(args.seeds), nominal_seeds=tuple(args.nominal_seeds),
                                               subset=set(args.cells) if args.cells else None, policy=policy,
                                               prior_std=args.prior_std, leg=leg)
    cases = sp.apply_diag_patch(cases, args.diag_patch)
    return cases[:args.limit] if args.limit else cases


# ------------------------------------------------------------------ CLI (plan only)
def main(argv=None):
    p = argparse.ArgumentParser(description='Plan-only passage route report (no simulator).')
    p.add_argument('--map', required=True, help='map id under maps/zones/')
    p.add_argument('--target', default='B', choices=('A', 'B', 'C'))
    p.add_argument('--passage', default='auto')
    p.add_argument('--beam', nargs=3, type=float, default=[1.0, 0.0, 0.0], help='coarse order sheet beam x y yaw')
    args = p.parse_args(argv)
    static_map = load_map(args.map)
    try:
        plan = plan_passage_route(static_map, args.beam, args.target, args.passage)
    except PassageRefusal as e:
        print(json.dumps({'map': args.map, 'target': args.target, 'refused': e.code, 'detail': e.detail}, indent=1, default=str))
        return 2
    print(json.dumps({'map': args.map, 'target': args.target,
                      'legacy_m2_door_route': plan is None, **({} if plan is None else plan)}, indent=1, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
