"""T08a: setup-public north/south beam geometry, never an executable plan.

Only a pre-authored coarse sheet, a public order and a static map enter here.
No scenario/eval adapter, robot assignment, start pose, controller or I/O exists.
The complete initial uncertainty interval is enclosed analytically; PASS means
static wall clearance of the local pre-station -> station geometry only.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping

from harness.static_keepouts import polygon_at, polygons_overlap, rect_corners
from harness.zone_team_footprint_v3 import TeamFootprintV3
from sim.masterpi_robot_models import station_grasp_convention

SCHEMA = 'ugrp.beam_initial_pose_plan.v1'
SHEET_SCHEMA = 'ugrp.beam_initial_coarse_sheet.v1'
SOURCE = 'coarse order sheet (setup pose rounded to the sheet grid; static, fixed before the run)'
GRID = {'xy_m': .1, 'yaw_rad': .174533}
PROVENANCE = 'public_setup_predeclared_v1'
# Half a quantization bin plus the legacy sheet's six-decimal serialization.
ERROR = {'xy_per_axis_m': .0500005, 'yaw_rad': math.radians(5) + .0000005}
PRESTATION_BACK_M = .25  # new candidate, NOT the frozen M2 controller's .30 m
MARGIN_M = .02
ROLES = ('end_neg', 'end_pos')
TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
MAP_KEYS = {'schema', 'map_id', 'version', 'frame', 'bounds_m', 'top_cameras', 'obstacles',
            'terrain', 'regions', 'zone_slots', 'box_kinds', 'approach_convention',
            'passages', 'wall_profile', 'base_map'}


class PlanRefusal(ValueError):
    def __init__(self, code, **detail):
        super().__init__(code)
        self.code, self.detail = code, detail


def digest(value):
    try:
        data = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError, OverflowError):
        raise PlanRefusal('NON_JSON_STATIC_INPUT') from None
    return hashlib.sha256(data.encode()).hexdigest()


def _numbers(value, size):
    return (isinstance(value, (list, tuple)) and len(value) == size
            and all(type(x) in (int, float) and math.isfinite(x) for x in value))


def _token(value):
    return isinstance(value, str) and TOKEN.fullmatch(value) is not None


def _order(order):
    keys = {'order_id', 'kind', 'count', 'identity', 'item_ids', 'required_robots',
            'destination_zone', 'initial_location'}
    if not isinstance(order, Mapping) or set(order) != keys:
        raise PlanRefusal('BAD_PUBLIC_BEAM_ORDER')
    location = order['initial_location']
    if (order['kind'] != 'long_beam' or type(order['count']) is not int or order['count'] != 1
            or order['identity'] != 'specific_item' or type(order['required_robots']) is not int
            or order['required_robots'] != 2 or not _token(order['order_id'])
            or not isinstance(order['item_ids'], list) or len(order['item_ids']) != 1
            or not _token(order['item_ids'][0]) or order['destination_zone'] not in ('A', 'B', 'C')
            or not isinstance(location, Mapping) or set(location) != {'pickup_bay', 'slot'}
            or not all(_token(v) for v in location.values())
            or not location['slot'].startswith(location['pickup_bay'] + '-')):
        raise PlanRefusal('UNSUPPORTED_PUBLIC_BEAM_ORDER')


def _map(static_map):
    # Reject scenario/scene/provider dictionaries rather than projecting eval data.
    if (not isinstance(static_map, Mapping) or set(static_map) - MAP_KEYS
            or static_map.get('schema') != 'ugrp.zone_arena.v1'
            or not _token(static_map.get('map_id'))
            or not isinstance(static_map.get('wall_profile'), Mapping)
            or static_map.get('wall_profile', {}).get('id') != 'walls_v3'
            or not _numbers(static_map.get('bounds_m'), 4)):
        raise PlanRefusal('UNSUPPORTED_STATIC_MAP')
    x0, x1, y0, y1 = static_map['bounds_m']
    if x0 >= x1 or y0 >= y1:
        raise PlanRefusal('BAD_STATIC_BOUNDS')
    for field in ('obstacles', 'terrain'):
        rows = static_map.get(field)
        if not isinstance(rows, list):
            raise PlanRefusal('BAD_STATIC_OBSTACLES')
        for row in rows:
            if (not isinstance(row, Mapping) or not _token(row.get('id'))
                    or not _numbers(row.get('center_m'), 2)
                    or not _numbers(row.get('half_extents_m'), 2)
                    or min(row['half_extents_m']) <= 0
                    or not _numbers([row.get('yaw_rad', 0.)], 1)):
                raise PlanRefusal('BAD_STATIC_OBSTACLES')
    regions = static_map.get('regions')
    if not isinstance(regions, Mapping) or 'pickup' not in regions:
        raise PlanRefusal('BAD_STATIC_REGIONS')
    for row in regions.values():
        if (not isinstance(row, Mapping) or not _numbers(row.get('center_m'), 2)
                or not _numbers(row.get('half_extents_m'), 2) or min(row['half_extents_m']) <= 0):
            raise PlanRefusal('BAD_STATIC_REGIONS')


def _coarse(coarse):
    if not isinstance(coarse, Mapping) or set(coarse) != {'beam_xyyaw', 'grid', 'source'}:
        raise PlanRefusal('BAD_COARSE_ORDER_SHEET')
    if coarse['source'] != SOURCE:
        raise PlanRefusal('UNTRUSTED_COARSE_SOURCE')
    if coarse['grid'] != GRID or not _numbers(coarse['beam_xyyaw'], 3):
        raise PlanRefusal('ORDER_SHEET_NOT_ON_COARSE_GRID')
    pose = coarse['beam_xyyaw']
    if any(abs(v) > 100 for v in pose):
        raise PlanRefusal('ORDER_SHEET_NOT_ON_COARSE_GRID')
    quantized = [round(round(v / g) * g, 6)
                 for v, g in zip(pose, (.1, .1, math.radians(10)))]
    if list(pose) != quantized:
        raise PlanRefusal('ORDER_SHEET_NOT_ON_COARSE_GRID')
    if pose[2] != round(math.pi / 2, 6):
        raise PlanRefusal('UNSUPPORTED_BEAM_HEADING')


def freeze_public_sheet(static_map, coarse, public_order):
    """Bind ALREADY PUBLIC setup data; never quantize a private/eval placement.

    The caller must preserve this record before execution. A source string or
    hash is an integrity check, not proof of who authored the values.
    """
    _map(static_map)
    _coarse(coarse)
    _order(public_order)
    return {'schema': SHEET_SCHEMA, 'provenance': PROVENANCE,
            'coarse': copy.deepcopy(coarse), 'initial_error_bound': dict(ERROR),
            'coarse_sha256': digest(coarse),
            'order_id': public_order['order_id'], 'item_id': public_order['item_ids'][0],
            'order_sha256': digest(public_order), 'map_sha256': digest(static_map)}


def _rotated_range(x, y, lo, hi):
    """Exact extrema of x*cos(a)-y*sin(a) over a closed angle interval."""
    phase = math.atan2(-y, x)
    angles = [lo, hi]
    angles += [phase + k * math.pi for k in range(math.ceil((lo-phase)/math.pi),
                                                   math.floor((hi-phase)/math.pi) + 1)]
    values = [x * math.cos(a) - y * math.sin(a) for a in angles]
    return min(values), max(values)


def _sweep_bounds(polygons, pose):
    """Enclose every vertex, yaw, XY error and straight local approach fraction.

    Polygons contain both endpoints of a fixed-heading translation. Each
    coordinate is affine along that translation, so its extrema occur at an
    endpoint. Yaw extrema are analytic (no sampled gaps); XY error is a box.
    """
    x, y, yaw = pose
    lo, hi = yaw - ERROR['yaw_rad'], yaw + ERROR['yaw_rad']
    points = [p for poly in polygons for p in poly]
    xr = [_rotated_range(px, py, lo, hi) for px, py in points]
    yr = [_rotated_range(py, -px, lo, hi) for px, py in points]
    pad = ERROR['xy_per_axis_m'] + MARGIN_M
    return [x + min(v[0] for v in xr) - pad, x + max(v[1] for v in xr) + pad,
            y + min(v[0] for v in yr) - pad, y + max(v[1] for v in yr) + pad]


def _check_bounds(name, box, static_map):
    x0, x1, y0, y1 = box
    bx0, bx1, by0, by1 = static_map['bounds_m']
    if not (bx0 < x0 < x1 < bx1 and by0 < y0 < y1 < by1):
        raise PlanRefusal('INITIAL_APPROACH_OUTSIDE_MAP', component=name, bounds_m=box)
    polygon = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for row in static_map['obstacles'] + static_map['terrain']:
        rect = (*row['center_m'], *row['half_extents_m'], row.get('yaw_rad', 0.))
        if polygons_overlap(polygon, rect_corners(rect)):
            raise PlanRefusal('INITIAL_APPROACH_BLOCKED', component=name, obstacle_id=row['id'])


def make_initial_pose_plan(static_map, sheet, public_order):
    """Return role geometry only. No route/door_plan accepted by M2 is returned."""
    if not isinstance(sheet, Mapping) or 'coarse' not in sheet:
        raise PlanRefusal('BAD_PUBLIC_SHEET')
    expected = freeze_public_sheet(static_map, sheet['coarse'], public_order)
    if dict(sheet) != expected:
        raise PlanRefusal('PUBLIC_SHEET_BINDING_MISMATCH')
    target = 'zone_' + public_order['destination_zone']
    if target not in static_map['regions']:
        raise PlanRefusal('UNKNOWN_TARGET_ZONE')
    pose = sheet['coarse']['beam_xyyaw']
    pickup = static_map['regions']['pickup']
    if any(abs(pose[i] - pickup['center_m'][i]) + ERROR['xy_per_axis_m']
           > pickup['half_extents_m'][i] for i in (0, 1)):
        raise PlanRefusal('BEAM_INITIAL_RANGE_OUTSIDE_PICKUP')
    team = TeamFootprintV3({'robot_model': 'masterpi_v3'}, 'long_beam', ROLES, margin=0.)
    model = station_grasp_convention('masterpi_v3')
    geometry, swept = {}, {}
    swept['beam'] = _sweep_bounds(team.item_parts, pose)
    for role in ROLES:
        station = team.stations[role]
        yaw = station[2]
        back = (-PRESTATION_BACK_M * math.cos(yaw), -PRESTATION_BACK_M * math.sin(yaw))
        pre = (station[0] + back[0], station[1] + back[1], yaw)
        # Reuse model-aware chassis/arm parts. Extend the legacy SEARCH front
        # by the v3 arm mount. SEARCH is only at pre-station; the inward segment
        # requires grasp posture (its 3-D transition is unvalidated).
        parts = team.carrier_parts[role]
        endpoints = parts + [[(x + back[0], y + back[1]) for x, y in p] for p in parts]
        front = .2 + model['arm_mount_x_m']
        search = polygon_at(pre, [(-.2, -.2), (front, -.2), (front, .2), (-.2, .2)])
        swept[role] = _sweep_bounds(endpoints + [search], pose)
        xy = polygon_at(pose, [station[:2], pre[:2]])
        heading = (pose[2] + yaw + math.pi) % (2 * math.pi) - math.pi
        geometry[role] = {'station_xyyaw': [*xy[0], heading],
                          'prestation_xyyaw': [*xy[1], heading],
                          'local_approach': [[*xy[1], heading], [*xy[0], heading]],
                          'local_approach_posture': 'grasp_geometry_only_requires_T08B_transition',
                          'local_parts_at_endpoints': endpoints, 'search_at_pre': search}
    for name, box in swept.items():
        _check_bounds(name, box, static_map)
    a, b = (swept[r] for r in ROLES)
    if not (a[1] < b[0] or b[1] < a[0] or a[3] < b[2] or b[3] < a[2]):
        raise PlanRefusal('CARRIER_APPROACH_ENVELOPES_OVERLAP')
    value = {'schema': SCHEMA, 'verdict': 'STATIC_INITIAL_GEOMETRY_ONLY',
             'executable': False, 'e2e_admitted': False, 'sim_cap_s': 0,
             'sheet': copy.deepcopy(sheet), 'order': copy.deepcopy(public_order),
             'map_sha256': digest(static_map), 'sheet_sha256': digest(sheet),
             'order_sha256': digest(public_order), 'role_geometry_sha256': digest(geometry),
             'model_convention': model,
             'geometry_sha256': digest(team.record()), 'roles': geometry,
             'swept_bounds_m': swept, 'prestation_back_m': PRESTATION_BACK_M,
             'clearance_margin_m': MARGIN_M, 'role_assignment': None,
             'controller_code_sha256': None,
             'refusals': {'spawn_to_prestation': 'REQUIRES_T08B_OWN_RGB_APPROACH',
                          'carry_route': 'REQUIRES_T09A_T10A_AND_CONTROLLER_VALIDATION',
                          'pivot': 'REQUIRES_T11_DESIGN',
                          'execution': 'STATIC_PLAN_NOT_EXECUTABLE'},
             'unchecked': ['other_items_and_robots', 'arm_posture_transition_3d',
                           'robot_localization_error', 'turn_to_approach_heading',
                           'own_rgb_localization', 'grasp_and_lift', 'delivery']}
    return {**value, 'plan_sha256': digest(value)}
