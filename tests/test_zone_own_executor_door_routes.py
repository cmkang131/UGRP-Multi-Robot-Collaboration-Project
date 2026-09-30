"""T09a fake/static checks. Collected by the existing zone_own_executor*.py CI glob."""
import copy
import hashlib
import inspect
import json
import math
from pathlib import Path

import pytest

from harness import static_keepouts as ko
from harness import zone_static_door_routes as dr
from harness.zone_team_footprint_v3 import team_footprint

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / 'maps/zones_final/zone_wide_two_doors_final_v1.json'
CONDITIONS = ('no_comm', 'peer_ko', 'leader_ko', 'structured')

# Independent v3 long-beam oracle, including the fixed 0.03 m planning margin.
# Catalogue: bar half-size .30 x .02, grips at +/-.27 m. V3 station radius
# .2032 = .155 reach + .0482 mount; bases at +/-.4732 m. Chassis in base
# frame [-.13, .1982] x [-.135, .135], arm [0, .2632] x [-.065, .065].
# Keep these expectations separate from _formation/team_footprint: otherwise
# deleting a carrier from their output also deletes it from the test oracle.
BEAM_PART_BOUNDS = {
    'cargo': (-.33, .33, -.05, .05),
    'end_neg_chassis': (-.6032, -.275, -.135, .135),
    'end_neg_arm': (-.4732, -.21, -.065, .065),
    'end_pos_chassis': (.275, .6032, -.135, .135),
    'end_pos_arm': (.21, .4732, -.065, .065),
}


def beam_sweeps(a, b):
    """Exact AABBs for fixed 0/pi heading and axial translations, not samples."""
    assert a[2] == b[2] and a[2] in (0., math.pi)
    assert a[0] == b[0] or a[1] == b[1]
    sign = 1 if a[2] == 0. else -1
    for name, (x0, x1, y0, y1) in BEAM_PART_BOUNDS.items():
        xs = [p[0] + sign * x for p in (a, b) for x in (x0, x1)]
        ys = [p[1] + sign * y for p in (a, b) for y in (y0, y1)]
        yield name, [(min(xs), min(ys)), (max(xs), min(ys)),
                     (max(xs), max(ys)), (min(xs), max(ys))]


def beam_hits(a, b, rects):
    return {name for name, sweep in beam_sweeps(a, b)
            if any(ko.polygons_overlap(sweep, ko.rect_corners(r)) for r in rects)}


def assert_full_beam_route_clear(route, static):
    rects = ko.keepout_rects(static, perimeter=True)
    x0, x1, y0, y1 = static['bounds_m']
    assert len(route.poses_m_rad) >= 2
    for a, b in zip(route.poses_m_rad, route.poses_m_rad[1:]):
        assert not beam_hits(a, b, rects), (route.passage_id, a, b, beam_hits(a, b, rects))
        for name, sweep in beam_sweeps(a, b):
            assert all(x0 < x < x1 and y0 < y < y1 for x, y in sweep), name


@pytest.fixture
def static():
    return json.loads(MAP.read_text())


def plan(static, start=(1., .05, 0.), goal=(3.5, .05, 0.), **kw):
    args = dict(cargo_kind='long_beam', roles=('end_neg', 'end_pos'), robot_model='masterpi_v3')
    args.update(kw)
    return dr.plan_door_routes(static, start, goal, **args)


def reasons(result):
    return {r.reason for r in result.refusals}


def block(static, door_id):
    """A pre-authored dev wall, not an injected/observed runtime event."""
    door = next(p for p in static['passages'] if p['id'] == door_id)
    static['obstacles'].append({'id': 'static_' + door_id, 'center_m': door['center_m'][:],
                                'half_extents_m': [.04, door['width_m'] / 2], 'kind': 'wall'})


def p09_crossings(path, static):
    """P09 audit.py passage_crossings, dec679978 (PR #302), geometry-only regression.

    Copy of the centre-plane criterion, without importing the private inventory
    or feasibility evaluator. Clearance and full passage exit are tested separately.
    """
    out = []
    for p in static['passages']:
        if p['kind'] == 'passing_bay':
            continue
        axis = 0 if p['axis'] == 'x' else 1
        cross = 1 - axis
        plane = p['center_m'][axis]
        lo, hi = (p['center_m'][cross] - p['half_extents_m'][cross],
                  p['center_m'][cross] + p['half_extents_m'][cross])
        off = [(i, point) for i, point in enumerate(path) if abs(point[axis] - plane) > 1e-9]
        for (ia, a), (_, b) in zip(off, off[1:]):
            if (a[axis] - plane) * (b[axis] - plane) >= 0:
                continue
            start, end = path[ia], path[ia + 1]
            fraction = (plane - start[axis]) / (end[axis] - start[axis])
            value = start[cross] + fraction * (end[cross] - start[cross])
            if lo <= value <= hi:
                labels = ('west_to_east', 'east_to_west') if axis == 0 else ('south_to_north', 'north_to_south')
                out.append((p['id'], labels[b[axis] < a[axis]]))
    return out


@pytest.mark.parametrize('door,y', [('door_narrow', .05), ('door_wide', -2.625)])
@pytest.mark.parametrize('kind,roles', [('cyan', ('west',)), ('heavy_crate', ('west', 'east')),
                                       ('long_beam', ('end_neg', 'end_pos'))])
@pytest.mark.parametrize('reverse', [False, True])
def test_each_door_full_formation_both_directions(static, door, y, kind, roles, reverse):
    start, goal = (1., y, 0.), (3.5, y, 0.)
    if reverse:
        start, goal = goal, start
    before = copy.deepcopy(static)
    result = plan(static, start, goal, cargo_kind=kind, roles=roles, passage_id=door)
    assert not result.refusals
    route = result.selected
    direction = 'east_to_west' if reverse else 'west_to_east'
    assert route.direction == direction
    assert route.poses_m_rad[0] == start and route.poses_m_rad[-1] == goal
    assert p09_crossings(route.poses_m_rad, static) == [(door, direction)]
    footprint = team_footprint({'robot_model': 'masterpi_v3'}, kind, roles)
    for a, b in zip(route.poses_m_rad, route.poses_m_rad[1:]):
        assert a[2] == b[2] == 0.
        assert a[0] == b[0] or a[1] == b[1]
        assert math.dist(a[:2], b[:2]) <= .85 + 1e-9
        for part in footprint.parts:
            assert ko.swept_clear(a, b, part, ko.keepout_rects(static, perimeter=True), bounds=static['bounds_m'])
    assert len(route.travel_heading_rad) == len(route.poses_m_rad) - 1
    assert static == before


@pytest.mark.parametrize('door,y', [('door_narrow', .05), ('door_wide', -2.625)])
def test_each_blocked_door_refuses(static, door, y):
    block(static, door)
    result = plan(static, (1., y, 0.), (3.5, y, 0.), passage_id=door)
    assert result.selected is None and reasons(result) == {'STATIC_SWEEP_BLOCKED'}


@pytest.mark.parametrize('yaw', [0., math.pi], ids=['east_heading', 'west_heading'])
@pytest.mark.parametrize('reverse', [False, True], ids=['west_to_east', 'east_to_west'])
def test_both_candidates_and_shortest_selection_are_order_independent(static, yaw, reverse):
    start, goal = (1., -1.2, yaw), (3.5, -1.2, yaw)
    if reverse:
        start, goal = goal, start
    result = plan(static, start, goal)
    assert {r.passage_id for r in result.routes} == {'door_narrow', 'door_wide'}
    assert result.selected.passage_id == 'door_narrow'
    direction = 'east_to_west' if reverse else 'west_to_east'
    for route in result.routes:  # Both candidates, not only the selected door.
        assert route.poses_m_rad[0] == start and route.poses_m_rad[-1] == goal
        assert p09_crossings(route.poses_m_rad, static) == [(route.passage_id, direction)]
        door = next(p for p in static['passages'] if p['id'] == route.passage_id)
        # Require a nonempty lateral sweep AFTER crossing the door plane.
        assert any(a[1] != b[1] and (a[0] < door['center_m'][0] if reverse
                                    else a[0] > door['center_m'][0])
                   for a, b in zip(route.poses_m_rad, route.poses_m_rad[1:]))
        assert_full_beam_route_clear(route, static)
    static['passages'].reverse()
    assert plan(static, start, goal) == result
    block(static, 'door_narrow')
    fallback = plan(static, start, goal)
    assert fallback.selected.passage_id == 'door_wide'
    for route in fallback.routes:
        assert_full_beam_route_clear(route, static)
    block(static, 'door_wide')
    assert plan(static, start, goal).selected is None


@pytest.mark.parametrize('door', ['door_narrow', 'door_wide'])
@pytest.mark.parametrize('yaw', [0., math.pi], ids=['east_heading', 'west_heading'])
@pytest.mark.parametrize('reverse', [False, True], ids=['west_to_east', 'east_to_west'])
def test_full_team_clears_each_door_before_lateral_exit(static, door, yaw, reverse):
    start, goal = (1., -1.2, yaw), (3.5, -1.2, yaw)
    if reverse:
        start, goal = goal, start
    result = plan(static, start, goal, passage_id=door)
    assert not result.refusals and len(result.routes) == 1
    route = result.selected
    assert route.passage_id == door
    assert route.poses_m_rad[0] == start and route.poses_m_rad[-1] == goal
    assert p09_crossings(route.poses_m_rad, static) == [
        (door, 'east_to_west' if reverse else 'west_to_east')]
    # The authored divider is at x=2.2 with half-thickness .025. Require a
    # nonzero lateral leg after crossing, where the missing rear carrier bites.
    assert any(a[1] != b[1] and (a[0] < 2.175 if reverse else a[0] > 2.225)
               for a, b in zip(route.poses_m_rad, route.poses_m_rad[1:]))
    assert_full_beam_route_clear(route, static)


def test_mouth_visit_and_plane_touch_are_not_crossings(static):
    # Exact P09 normal/reverse/mouth/retreat counterexamples, no evaluator input.
    path = [(1.8, .05, 0.), (1.8, -2.625, 0.), (2.2, -2.625, 0.), (2.5, -2.625, 0.)]
    assert p09_crossings(path, static) == [('door_wide', 'west_to_east')]
    assert p09_crossings(path[::-1], static) == [('door_wide', 'east_to_west')]
    assert p09_crossings([(1.8, .05, 0.), (2.2, .05, 0.), (1.8, .05, 0.)], static) == []
    assert p09_crossings([(1.8, .05, 0.), (2.2, .05, 0.)], static) == []
    result = plan(static, goal=(1.4, .05, 0.), passage_id='door_narrow')
    assert result.selected is None and reasons(result) == {'ENDPOINTS_NOT_ACROSS_DOOR'}


def test_requested_door_cannot_be_replaced_with_another_crossing(static):
    block(static, 'door_narrow')
    result = plan(static, (1., -1.2, 0.), (3.5, -1.2, 0.))
    assert p09_crossings(result.selected.poses_m_rad, static) == [('door_wide', 'west_to_east')]
    forced = plan(static, (1., -1.2, 0.), (3.5, -1.2, 0.), passage_id='door_narrow')
    assert forced.selected is None


@pytest.mark.parametrize('role', ['end_neg', 'end_pos'])
@pytest.mark.parametrize('yaw', [0., math.pi], ids=['east_heading', 'west_heading'])
def test_complete_team_corner_blocks_cropped_disc_and_point_counterexample(static, role, yaw):
    # Only the named carrier's chassis hits this independently fixed wall.
    # Start, bend and goal are clear: rejecting endpoints alone cannot pass.
    sign = (-1 if role == 'end_neg' else 1) * (1 if yaw == 0. else -1)
    wall = (1. + sign * .58, -.5, .005, .005, 0.)
    static['obstacles'].append({'id': 'corner', 'center_m': list(wall[:2]),
                                'half_extents_m': [.005, .005]})
    start, bend, goal = (1., -1., yaw), (1., .05, yaw), (3.5, .05, yaw)
    rects = ko.keepout_rects(static, perimeter=True)
    for pose in (start, bend, goal):
        assert not beam_hits(pose, pose, rects)
    assert beam_hits(start, bend, (wall,)) == {role + '_chassis'}
    for radius in (.000001, .17, .21):
        assert ko.swept_clear(start, bend, ko.disc_footprint(radius), rects, bounds=static['bounds_m'])
    result = plan(static, start, goal, passage_id='door_narrow')
    assert result.selected is None and reasons(result) == {'STATIC_SWEEP_BLOCKED'}


def test_full_footprint_at_goal_not_just_reference_point(static):
    result = plan(static, goal=(5., .05, 0.))
    assert result.selected is None and reasons(result) == {'GOAL_FOOTPRINT_BLOCKED'}


@pytest.mark.parametrize('gap,ok', [(.271, True), (.270, False), (.269, False)])
def test_width_boundary_includes_all_parts_and_margin(static, gap, ok):
    p = static['passages'][0]
    p['width_m'], p['half_extents_m'][1] = gap, gap / 2
    result = plan(static, passage_id='door_narrow')
    assert bool(result.selected) is ok
    if not ok:
        assert reasons(result) == {'FOOTPRINT_TOO_WIDE'}


def test_thin_obstacle_between_clear_endpoints_is_not_missed(static):
    static['obstacles'].append({'id': 'thin', 'center_m': [2.105, .05],
                                'half_extents_m': [.000001, .001], 'yaw_rad': .3})
    assert reasons(plan(static, passage_id='door_narrow')) == {'STATIC_SWEEP_BLOCKED'}


@pytest.mark.parametrize('pose', [(1., .05, math.pi / 2), (1., .05, .1)])
def test_rotation_required_is_unsupported_not_silently_planned(static, pose):
    assert reasons(plan(static, pose, (3.5, .05, pose[2]))) == {'UNSUPPORTED_ROTATION'}
    assert reasons(plan(static, goal=(3.5, .05, math.pi))) == {'UNSUPPORTED_ROTATION'}


def test_west_facing_heading_is_distinct_from_travel_heading(static):
    route = plan(static, (3.5, .05, math.pi), (1., .05, math.pi), passage_id='door_narrow').selected
    assert route.direction == 'east_to_west'
    assert all(p[2] == math.pi for p in route.poses_m_rad)
    assert all(abs(h) == math.pi for h in route.travel_heading_rad)


def test_tiny_lateral_offset_keeps_exact_endpoints_and_axis_legs(static):
    start, goal = (1.013, .05 + 1e-10, 0.), (3.567, .05 - 1e-10, 0.)
    route = plan(static, start, goal, passage_id='door_narrow').selected
    assert route is not None
    assert route.poses_m_rad[0] == start and route.poses_m_rad[-1] == goal
    assert all(a[0] == b[0] or a[1] == b[1]
               for a, b in zip(route.poses_m_rad, route.poses_m_rad[1:]))


@pytest.mark.parametrize('roles', [(), ('end_neg',), ('end_neg', 'end_neg'), ('r1', 'r2'), ('west', 'east')])
def test_incomplete_or_unknown_formation_refused(static, roles):
    assert reasons(plan(static, roles=roles)) == {'INVALID_FORMATION'}


@pytest.mark.parametrize('kw,reason', [({'cargo_kind': 'point'}, 'UNSUPPORTED_CARGO'),
                                     ({'robot_model': 'masterpi_v2'}, 'UNSUPPORTED_ROBOT_MODEL'),
                                     ({'passage_id': 'door_1'}, 'UNKNOWN_DOOR'),
                                     ({'motion': dr.MotionContract(version='rotate')}, 'UNSUPPORTED_MOTION'),
                                     ({'motion': dr.MotionContract(max_legs=1)}, 'CONTROLLER_SEGMENT_LIMIT'),
                                     ({'motion': dr.MotionContract(max_leg_m=0)}, 'INVALID_MOTION'),
                                     ({'motion': dr.MotionContract(max_leg_m=1e-320)}, 'CONTROLLER_SEGMENT_LIMIT'),
                                     ({'motion': dr.MotionContract(max_leg_m=.86)}, 'INVALID_MOTION'),
                                     ({'motion': dr.MotionContract(max_legs=9)}, 'INVALID_MOTION'),
                                     ({'motion': dr.MotionContract(max_legs=True)}, 'INVALID_MOTION')])
def test_unsupported_and_invalid_contracts(static, kw, reason):
    assert reason in reasons(plan(static, **kw))


@pytest.mark.parametrize('bad', [None, True, '1', math.nan, math.inf])
def test_invalid_pose_is_closed(static, bad):
    assert plan(static, (bad, .05, 0.)).selected is None


@pytest.mark.parametrize('field,value', [('width_m', math.nan), ('width_m', True), ('width_m', .8),
                                        ('half_extents_m', [0., .25]), ('axis', 'y'), ('yaw_rad', .1)])
def test_bad_door_geometry_refuses(static, field, value):
    static['passages'][0][field] = value
    assert plan(static, passage_id='door_narrow').selected is None


@pytest.mark.parametrize('mutation', ['missing_obstacles', 'bad_bounds', 'bad_obstacle', 'duplicate_door',
                                     'no_doors', 'private_scenario'])
def test_invalid_or_unsupported_map(static, mutation):
    if mutation == 'missing_obstacles':
        del static['obstacles']
    elif mutation == 'bad_bounds':
        static['bounds_m'] = [1., 1., 0., 1.]
    elif mutation == 'bad_obstacle':
        static['obstacles'][0]['half_extents_m'] = [-1., .02]
    elif mutation == 'duplicate_door':
        static['passages'].append(copy.deepcopy(static['passages'][0]))
    elif mutation == 'no_doors':
        static['passages'] = [{'id': 'corridor_1', 'kind': 'corridor'}]
    else:
        static['eval'] = {'hidden_events': []}
    assert plan(static).selected is None


def test_unvalidated_terrain_is_a_keepout(static):
    static['terrain'].append({'id': 'step', 'center_m': [2.2, .05], 'half_extents_m': [.1, .2]})
    assert reasons(plan(static, passage_id='door_narrow')) == {'STATIC_SWEEP_BLOCKED'}


def test_future_private_blockage_noninterference_all_conditions(static):
    scenario = json.loads((ROOT / 'configs/zone_study_scenarios_v2/s2_unmapped_blockage_v2.json').read_text())
    before = copy.deepcopy(scenario)
    def from_public_inputs(s):
        # Same boundary a caller must use: authored map ID + public order.
        # The own estimate is a fixed dev fixture, never setup.placements.
        authored = json.loads((ROOT / 'maps/zones_final' / (s['map_id'] + '.json')).read_text())
        order = s['orders'][0]
        assert order['kind'] == 'cyan'
        goal = (*authored['regions']['zone_' + order['destination_zone']]['center_m'], 0.)
        return plan(authored, (1., .05, 0.), goal, cargo_kind=order['kind'], roles=('west',))
    reference = from_public_inputs(scenario)
    assert reference.selected is not None
    hashes = set()
    for condition in CONDITIONS:
        changed = copy.deepcopy(scenario)
        changed['eval']['hidden_events'] = [{'time_s': 1e-6, 'target': 'door_wide', 'private': condition}]
        changed['eval']['setup']['placements'] = [{'private_pose': [99., 99., 99.]}]
        # The caller has only this public map + its own estimate/public goal.
        # A poison mapping catches attempts to add a private lookup here.
        class PrivateForbidden(dict):
            def __getitem__(self, key):
                raise AssertionError('private evaluator input accessed')
        changed['eval'] = PrivateForbidden(changed['eval'])
        assert from_public_inputs(changed) == reference
        hashes.add(hashlib.sha256(inspect.getsource(dr).encode()).hexdigest())
    assert len(hashes) == 1 and scenario == before
    assert not {'scenario', 'condition', 'events', 'inventory', 'peer', 'referee'} & set(inspect.signature(dr.plan_door_routes).parameters)


def test_new_file_is_collected_by_existing_ci_glob():
    from scripts.run_ci_tests import TEST_PATTERNS
    assert any(Path(__file__).match(pattern) for pattern in TEST_PATTERNS)
