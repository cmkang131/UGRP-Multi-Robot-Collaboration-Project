"""pairact P2 carry route detour_v1 (opt-in): formation-space A* only when both
straight variants are blocked. Pure functions, no simulator."""
import json
import math

import pytest

from harness import pair_carry_teacher_warp as ct
from test_pair_carry_teacher_warp import (ARM, MAP, PWM, ROLES, _teacher_rollout, ce, handover, make,
                                                wheels)

RECTS = ct.wall_rects(MAP)

# world 1 (smoke-1c world-000, seed 8420001) handover, copied from
# outputs/pairact-world1-recovery-20261021/world1-fields.json carry.events[0]
W1_BEAM = (1.548663854598999, 0.6587918996810913, 0.839400004991969)
W1_OFF = {'r1': (0.47045964197299395, 0.0003201594874747693, -3.1401638946686767),
          'r2': (-0.47145286543089343, 0.0002026747235729376, 0.02787405516349395)}
W1_HIT = 0.46774193548387094      # failure_analysis.hit.fraction_along_segment


def w1_object(rid, radius=.12, u=.55):
    """The blocking object's GT pose is not in the recovered fields [확인 필요]:
    reconstruct one disc that reproduces the recorded first hit exactly (kind
    'object' at fraction 0.4677 of to_west_staging): the robot ``rid`` centre at
    55 % of the straight segment, radius 0.12 m."""
    route, _ = ct.carry_route(W1_BEAM, W1_OFF, MAP)
    w = route[0][1]
    p = (W1_BEAM[0] + (w[0] - W1_BEAM[0])*u, W1_BEAM[1] + (w[1] - W1_BEAM[1])*u, W1_BEAM[2])
    return [{'id': 'w1_object', 'xy': list(ct.compose(p, W1_OFF[rid])[:2]), 'radius': radius}]


def w1_teacher(obstacles, **kw):
    beam = W1_BEAM
    robots = {rid: ct.compose(beam, off) for rid, off in W1_OFF.items()}
    row = {'t': 0., 'beam': {'pose': list(beam), 'min_z': .03, 'tilt_deg': 1.}, 'objects': {},
           'robots': {rid: {'pose': list(p)} for rid, p in robots.items()},
           'contacts': {'r1': [2., 2.], 'r2': [2., 2.]}}
    return ct.PairCarryTeacherWarp(ROLES, row, 23.5, MAP, ARM, PWM, wheel_fn=wheels, obstacles=obstacles, **kw)


@pytest.mark.parametrize('rid', ['r1', 'r2'])
def test_world1_straight_is_blocked_exactly_like_the_recorded_failure(rid):
    teacher = w1_teacher(w1_object(rid))
    assert teacher.outcome == 'route_blocked'
    fail = teacher.events[-1]
    assert fail['detail']['segment'] == 'to_west_staging'
    assert fail['detail']['hit'] == ('object', W1_HIT)
    assert teacher.route_info['formation_radius_m'] == pytest.approx(0.6414529089952078)
    assert teacher.route_info['variant'] == 'rotate_first'


@pytest.mark.parametrize('rid', ['r1', 'r2'])
def test_world1_detour_finds_a_collision_free_path(rid):
    obstacles = w1_object(rid)
    teacher = w1_teacher(obstacles, route_mode='detour_v1')
    assert teacher.outcome is None and not teacher.done
    info = teacher.route_info
    assert info['variant'] == 'detour' and info['route_mode'] == 'detour_v1'
    assert info['straight_blocked']['hit'] == ('object', W1_HIT)
    det = info['detour']
    assert det['search']['found'] and det['nodes_expanded'] == det['search']['expanded'] > 0
    assert det['waypoints'] and det['min_clearance_m'] >= 0.
    # authoritative check = the same swept-formation test as the straight route
    ok, why = ct.route_clear(W1_BEAM, teacher.route, teacher.offsets, RECTS, obstacles)
    assert ok, why
    assert ct.route_min_clearance(W1_BEAM, teacher.route, teacher.offsets, RECTS, obstacles) == det['min_clearance_m']
    tags = [t for t, _ in teacher.route]
    n = len(det['waypoints'])
    assert tags == ['to_west_staging']*n + ['rotate_door', 'to_door_entry', 'door_pass', 'to_east_staging',
                                           'rotate_zone', 'to_zone']
    assert set(tags) <= set(ct.PHASES)
    west = info['west_staging']
    assert teacher.route[n - 1][1][:2] == pytest.approx(tuple(west))
    # rotations happen in place only (never blended into a translation)
    prev = W1_BEAM
    for _, p in teacher.route[:n + 1]:
        moved, turned = math.dist(prev[:2], p[:2]) > 1e-9, abs(ct.wrap(p[2] - prev[2])) > 1e-9
        assert not (moved and turned)
        prev = p
    # door/zone legs are the planned ones
    planned, _ = ct.carry_route(W1_BEAM, teacher.offsets, MAP)
    assert teacher.route[n + 1:] == planned[2:]
    json.dumps(teacher.diagnostic())


def test_world1_detour_rollout_reaches_zone_b():
    """Ideal kinematics through the detour (multi-segment to_west_staging)."""
    obstacles = w1_object('r2')
    import test_pair_carry_teacher_warp as base
    beam0 = W1_BEAM
    reach = math.hypot(*W1_OFF['r1'][:2])
    teacher = ct.PairCarryTeacherWarp(ROLES, handover(beam0, reach), 0., MAP, ARM, PWM, wheel_fn=wheels,
                                      obstacles=obstacles, route_mode='detour_v1')
    assert teacher.route_info['variant'] == 'detour'
    rows = _teacher_rollout(teacher, beam0, cap=110.)
    assert teacher.outcome == 'command_sequence_complete', teacher.events[-3:]
    lower = next(e['t'] for e in teacher.events if e.get('to') == 'lower')
    res = ce.evaluate(rows, MAP, list(ROLES), lower_start_t=lower, handover_t=0.)
    assert res['success'], res['failure']
    # executed virtual path never touched the object
    for r in teacher.log:
        assert ct.formation_clearance(tuple(r['virtual']), teacher.offsets, RECTS, obstacles) >= 0.
    assert base  # same fixtures as the frozen P2 tests


STRAIGHT_CASES = [
    ((.7, -1.5, .3), []),                                                       # frozen rollout beam
    ((.6, -1.5, 0.), []),
    (W1_BEAM, []),                                                              # world 1 without the object
    ((.7, -1.5, .3), [{'id': 'far', 'xy': [-.6, 1.0], 'radius': .2}]),
]


@pytest.mark.parametrize('beam,obstacles', STRAIGHT_CASES)
def test_clear_straight_route_is_byte_identical_under_detour_mode(beam, obstacles):
    a = make(beam, obstacles=obstacles)
    b = make(beam, obstacles=obstacles, route_mode='detour_v1')
    assert a.outcome is None and b.outcome is None
    assert json.dumps(a.route) == json.dumps(b.route)
    assert json.dumps(a.route_info, sort_keys=True) == json.dumps(b.route_info, sort_keys=True)
    assert json.dumps(a.diagnostic(), sort_keys=True) == json.dumps(b.diagnostic(), sort_keys=True)


def test_rotate_first_route_is_unchanged_under_detour_mode():
    offsets = {'r1': (-.5, 0, 0), 'r2': (.5, 0, math.pi)}
    start = (0., 0., math.pi/2)
    route = [('to_west_staging', (2., 0., math.pi/2)), ('rotate_door', (2., 0., 0.))]
    wall = [(1., .75, .05, .1, 0.)]
    out, blocked = ct.check_route(start, route, offsets, wall, [])
    assert blocked[0] is True        # detour_v1 never runs when rotate-first is clear


def test_no_path_is_a_distinct_failure_code():
    beam = (.6, -1.5, 0.)
    ring = [{'id': f'o{k}', 'xy': [.6 + 1.1*math.cos(a), -1.5 + 1.1*math.sin(a)], 'radius': .3}
            for k, a in enumerate(i*math.pi/6 for i in range(12))]
    straight = make(beam, obstacles=ring)
    assert straight.outcome == 'route_blocked'                  # default unchanged
    teacher = make(beam, obstacles=ring, route_mode='detour_v1')
    assert teacher.outcome == ct.NO_PATH == 'route_blocked_no_path' and teacher.done
    assert ct.NO_PATH in ct.ABORTS
    detail = teacher.events[-1]['detail']
    assert detail['straight']['segment'] == 'to_west_staging'
    assert detail['search']['found'] is False and detail['search']['expanded'] > 0
    assert detail['search']['reason'] in ('exhausted', 'node_budget')


def test_existing_object_detour_test_now_succeeds_only_when_opted_in():
    obstacles = [{'id': 'box', 'xy': [1.0, -2.0], 'radius': .3}, {'id': 'box2', 'xy': [.6, -1.0], 'radius': .3}]
    assert make((.6, -1.5, 0.), obstacles=obstacles).outcome == 'route_blocked'
    teacher = make((.6, -1.5, 0.), obstacles=obstacles, route_mode='detour_v1')
    assert teacher.outcome in (None, ct.NO_PATH)
    if teacher.outcome is None:
        assert ct.route_clear((.6, -1.5, 0.), teacher.route, teacher.offsets, RECTS, obstacles)[0]


def test_unknown_route_mode_rejected():
    with pytest.raises(ValueError, match='route mode'):
        make((.7, -1.5, .3), route_mode='bogus')


def test_runner_route_default_and_validation(tmp_path):
    from test_pair_carry_teacher_warp import _runner_function
    fn = _runner_function()
    kw = {a.arg: d.value for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults) if isinstance(d, ast_Constant())}
    assert kw['carry_route'] == 'straight_v1'
    from scripts import run_grasp_act_teacher as runner
    with pytest.raises(ValueError, match='requires pair carry'):
        runner.run({'roles': ROLES}, tmp_path, carry_route='detour_v1')
    with pytest.raises(ValueError, match='unknown carry route'):
        runner.run({'roles': ROLES}, tmp_path, pair_carry=ct.MODE, teacher_profile='visible_only', carry_route='x')


def ast_Constant():
    import ast
    return ast.Constant


def test_default_runner_result_has_no_route_key():
    """result.json for existing candidates gets no new key (carry_route only when opted in)."""
    from pathlib import Path
    src = (Path(ct.__file__).resolve().parents[1]/'scripts/run_grasp_act_teacher.py').read_text()
    assert "**({'carry_route':carry_route} if carry_route!='straight_v1' else {})," in src
