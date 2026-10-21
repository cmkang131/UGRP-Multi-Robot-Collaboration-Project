"""pairact P2 -c6 carry route detour_v2 (opt-in): start-pocket escape + several
object-aware west staging goals in one multi-goal A*. Pure functions, no simulator.
Obstacle placements are synthetic [확인 필요: real pilot handover states come
from scripts/analyze_pairact_pilot.py --replay on the fetched eval-only rows]."""
import json
import math
import subprocess
from pathlib import Path

import pytest

from harness import pair_carry_teacher_warp as ct
from test_pair_carry_detour import RECTS, STRAIGHT_CASES, W1_BEAM, W1_OFF, w1_object, w1_teacher
from test_pair_carry_teacher_warp import ARM, MAP, PWM, ROLES, _teacher_rollout, ce, handover, make, wheels

ROBOTS, _ = ct.formation_points(W1_BEAM, W1_OFF)


def pocket(rid='r1', ang=0., gap=.01, radius=.12):
    """An object disc ``gap`` m from robot ``rid``'s planning disc at handover."""
    p, d = ROBOTS[rid], ct.ROBOT_RADIUS_M + radius + gap
    return {'id': 'pocket', 'xy': [p[0] + d*math.cos(math.radians(ang)), p[1] + d*math.sin(math.radians(ang))],
            'radius': radius}


@pytest.mark.parametrize('beam,obstacles', STRAIGHT_CASES)
def test_clear_straight_route_is_byte_identical_under_detour_v2(beam, obstacles):
    a = make(beam, obstacles=obstacles)
    b = make(beam, obstacles=obstacles, route_mode='detour_v2')
    assert a.outcome is None and b.outcome is None
    assert json.dumps(a.diagnostic(), sort_keys=True) == json.dumps(b.diagnostic(), sort_keys=True)


def test_detour_v1_code_is_unchanged_from_c5():
    """-c6 adds detour_v2 next to v1; the v1 functions stay byte-identical to -c5 75929e77."""
    import inspect
    root = Path(ct.__file__).resolve().parents[1]
    try:
        old = subprocess.check_output(['git', '-C', str(root), 'show', '75929e771:harness/pair_carry_teacher_warp.py'],
                                      text=True)
    except subprocess.CalledProcessError:
        pytest.fail('base commit 75929e771 missing (fetch-depth 0 required)')
    for fn in (ct.plan_formation_path, ct._shortcut, ct.detour_route, ct.check_route, ct.route_clear,
               ct.segment_clear, ct.formation_clearance, ct.carry_route, ct.staging_point):
        assert inspect.getsource(fn) in old, fn.__name__


@pytest.mark.parametrize('rid,ang', [('r1', 0.), ('r2', 90.), ('r1', 270.)])
def test_start_pocket_v1_stalls_v2_escapes(rid, ang):
    """Handover 1 cm from an object: v1 needs the full node margin (0.065 m) at
    every neighbour, so it expands one node and gives up; v2 may leave the pocket
    without ever getting closer than the start clearance."""
    obstacles = w1_object('r2') + [pocket(rid, ang)]
    v1 = w1_teacher(obstacles, route_mode='detour_v1')
    assert v1.outcome == ct.NO_PATH
    assert v1.route_info['detour']['search']['reason'] == 'exhausted'
    assert v1.route_info['detour']['search']['expanded'] == 1
    v2 = w1_teacher(obstacles, route_mode='detour_v2')
    assert v2.outcome is None and v2.route_info['variant'] == 'detour'
    det = v2.route_info['detour']
    s = det['search']
    assert s['found']
    assert s['escape_floor_m'] == pytest.approx(min(s['start_clearance_m'], .03 + .05*math.sqrt(2)/2))
    assert s['start_clearance_m'] == pytest.approx(.01, abs=1e-6)
    # start clearance >= 0 -> the ordinary swept check (margin 0) passes for the whole route
    assert ct.route_clear(W1_BEAM, v2.route, v2.offsets, RECTS, obstacles)[0]
    assert det['min_clearance_m'] >= 0.
    tags = [t for t, _ in v2.route]
    assert tags[-6:] == ['rotate_door', 'to_door_entry', 'door_pass', 'to_east_staging', 'rotate_zone', 'to_zone']
    assert set(tags) <= set(ct.PHASES)
    json.dumps(v2.diagnostic())
    json.dumps(v2.route_record())


def test_small_start_overlap_escapes_only_inside_the_pocket():
    obstacles = w1_object('r2') + [pocket('r1', 0., gap=-.01)]
    v2 = w1_teacher(obstacles, route_mode='detour_v2')
    assert v2.outcome is None
    s = v2.route_info['detour']['search']
    assert s['start_clearance_m'] == pytest.approx(-.01, abs=1e-6) and s['escape_floor_m'] == s['start_clearance_m']
    assert not ct.route_clear(W1_BEAM, v2.route, v2.offsets, RECTS, obstacles)[0]   # overlap at the start itself
    assert ct.escape_route_clear(W1_BEAM, v2.route, v2.offsets, RECTS, obstacles, floor=s['escape_floor_m'],
                                 escape_radius=ct.DETOUR_V2['escape_radius_m'])[0]
    # never worse than the start, and clear (>= 0) once outside the escape radius
    prev = W1_BEAM
    for _, b in v2.route:
        for u in (0., .25, .5, .75, 1.):
            p = (prev[0]+(b[0]-prev[0])*u, prev[1]+(b[1]-prev[1])*u, ct.wrap(prev[2]+ct.wrap(b[2]-prev[2])*u))
            c = ct.formation_clearance(p, v2.offsets, RECTS, obstacles)
            far = math.dist(p[:2], W1_BEAM[:2]) > ct.DETOUR_V2['escape_radius_m']
            assert c >= (0. if far else s['escape_floor_m']) - 1e-9
        prev = b


def test_start_overlap_beyond_tolerance_is_start_in_collision():
    obstacles = w1_object('r2') + [pocket('r1', 0., gap=-.05)]
    v2 = w1_teacher(obstacles, route_mode='detour_v2')
    assert v2.outcome == ct.NO_PATH
    assert v2.events[-1]['detail']['search']['reason'] == 'start_in_collision'


def test_blocked_planned_staging_uses_another_goal():
    """An object where the formation would stand at the planned west staging
    (door yaw): v2 reaches another object-aware staging goal; the rotate_door
    point moves there and the door/zone legs are the planned ones."""
    obstacles = w1_object('r2') + [{'id': 'nearwest', 'xy': [.8, -2.15], 'radius': .12}]
    v2 = w1_teacher(obstacles, route_mode='detour_v2')
    assert v2.outcome is None
    det, west = v2.route_info['detour'], v2.route_info['west_staging']
    assert ct.formation_clearance((west[0], west[1], 0.), v2.offsets, RECTS, obstacles) < ct.DETOUR_V2['goal_margin_m']
    assert det['goal'] != pytest.approx(list(west)) and det['goal_is_planned_west'] is False
    rot = next(p for t, p in v2.route if t == 'rotate_door')
    assert rot[:2] == pytest.approx(tuple(det['goal']))
    assert ct.route_clear(W1_BEAM, v2.route, v2.offsets, RECTS, obstacles)[0]
    planned, _ = ct.carry_route(W1_BEAM, v2.offsets, MAP)
    assert v2.route[-5:] == planned[2:]


def test_object_in_the_door_lane_fails_fast_with_reason():
    obstacles = w1_object('r2') + [{'id': 'lane', 'xy': [1.75, -2.3], 'radius': .12}]
    v2 = w1_teacher(obstacles, route_mode='detour_v2')
    assert v2.outcome == ct.NO_PATH
    info = v2.route_info['detour']
    assert info['goals'] == [] and info['search']['reason'] == 'no_staging_goal' and info['search']['expanded'] == 0
    assert info['downstream_blocked']['segment'] in ('to_door_entry', 'door_pass')


def test_staging_candidates_order_and_filters():
    route, info = ct.carry_route(W1_BEAM, W1_OFF, MAP)
    goals = ct.staging_candidates(info['door'], info['west_staging'], route[1][1][2], route[2:], W1_OFF, RECTS, [],
                                  radius=info['formation_radius_m'])
    assert goals[0] == tuple(info['west_staging'])           # no objects: planned west first
    assert 1 < len(goals) <= ct.DETOUR_V2['max_goals']
    d = [math.dist(g, info['west_staging']) for g in goals[1:]]
    assert d == sorted(d)
    for g in goals:
        assert ct.circle_clear(g, info['formation_radius_m'], RECTS, margin=ct.Params().clear_margin_m)


def test_pocket_detour_rollout_reaches_zone_b():
    """Ideal kinematics through a v2 pocket escape; evaluator success."""
    obstacles = w1_object('r2') + [pocket('r1', 90.)]
    reach = math.hypot(*W1_OFF['r1'][:2])
    teacher = ct.PairCarryTeacherWarp(ROLES, handover(W1_BEAM, reach), 0., MAP, ARM, PWM, wheel_fn=wheels,
                                      obstacles=obstacles, route_mode='detour_v2')
    assert teacher.route_info['variant'] == 'detour'
    rows = _teacher_rollout(teacher, W1_BEAM, cap=110.)
    assert teacher.outcome == 'command_sequence_complete', teacher.events[-3:]
    lower = next(e['t'] for e in teacher.events if e.get('to') == 'lower')
    res = ce.evaluate(rows, MAP, list(ROLES), lower_start_t=lower, handover_t=0.)
    assert res['success'], res['failure']
    for r in teacher.log:
        assert ct.formation_clearance(tuple(r['virtual']), teacher.offsets, RECTS, obstacles) >= -1e-9


def test_runner_accepts_detour_v2_only_with_pair_carry(tmp_path):
    from scripts import run_grasp_act_teacher as runner
    src = (Path(ct.__file__).resolve().parents[1]/'scripts/run_grasp_act_teacher.py').read_text()
    assert "choices=('straight_v1','detour_v1','detour_v2')" in src
    with pytest.raises(ValueError, match='requires pair carry'):
        runner.run({'roles': ROLES}, tmp_path, carry_route='detour_v2')
