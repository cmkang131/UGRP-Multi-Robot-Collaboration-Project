"""pairact P2 teacher -c4: the carry route (incl. the detour_v1 A*) is planned
once at the handover and never again during step(); the planned route is
available as a JSON record the runner writes immediately. Pure functions."""
import json
import math
from pathlib import Path

import pytest

from harness import pair_carry_teacher_warp as ct
from test_pair_carry_detour import W1_BEAM, W1_OFF, w1_object
from test_pair_carry_teacher_warp import ARM, MAP, PWM, ROLES, _teacher_rollout, handover, make, wheels


def _counting(monkeypatch):
    calls = {'plan_formation_path': 0, 'carry_route': 0, 'check_route': 0}
    for name in calls:
        real = getattr(ct, name)

        def wrapped(*a, _real=real, _name=name, **kw):
            calls[_name] += 1
            return _real(*a, **kw)
        monkeypatch.setattr(ct, name, wrapped)
    return calls


def test_detour_search_runs_once_over_the_whole_rollout(monkeypatch):
    obstacles = w1_object('r2')                            # (helper itself calls carry_route)
    calls = _counting(monkeypatch)
    teacher = ct.PairCarryTeacherWarp(ROLES, handover(W1_BEAM, math.hypot(*W1_OFF['r1'][:2])), 0., MAP, ARM, PWM,
                                      wheel_fn=wheels, obstacles=obstacles, route_mode='detour_v1')
    assert teacher.route_info['variant'] == 'detour'
    assert calls == {'plan_formation_path': 1, 'carry_route': 1, 'check_route': 1}
    _teacher_rollout(teacher, W1_BEAM, cap=110.)
    assert teacher.outcome == 'command_sequence_complete'
    assert len(teacher.log) > 100                          # many control ticks ...
    assert calls == {'plan_formation_path': 1, 'carry_route': 1, 'check_route': 1}   # ... no replanning
    assert teacher.route_plans == 1 and teacher.detour_searches == 1


def test_straight_route_plans_once_and_never_searches(monkeypatch):
    calls = _counting(monkeypatch)
    teacher = make((.7, -1.5, .3), route_mode='detour_v1')
    _teacher_rollout(teacher, (.7, -1.5, .3), cap=110.)
    assert calls == {'plan_formation_path': 0, 'carry_route': 1, 'check_route': 1}
    assert teacher.route_plans == 1 and teacher.detour_searches == 0


def test_route_record_is_strict_json_and_matches_the_teacher():
    obstacles = w1_object('r1')
    teacher = ct.PairCarryTeacherWarp(ROLES, handover(W1_BEAM, math.hypot(*W1_OFF['r1'][:2])), 0., MAP, ARM, PWM,
                                      wheel_fn=wheels, obstacles=obstacles, route_mode='detour_v1')
    rec = teacher.route_record()
    text = json.dumps(rec, allow_nan=False)                 # runner write() uses allow_nan=False
    back = json.loads(text)
    assert back['schema'] == ct.ROUTE_RECORD_SCHEMA
    assert back['route_info']['variant'] == 'detour'
    assert back['route_info']['detour']['nodes_expanded'] > 0
    assert back['route'] == json.loads(json.dumps([[t, list(p)] for t, p in teacher.route]))
    assert back['route_plans'] == 1 and back['detour_searches'] == 1 and back['outcome'] is None


def test_no_path_record_keeps_the_search_stats():
    beam = (.6, -1.5, 0.)
    ring = [{'id': f'o{k}', 'xy': [.6 + 1.1*math.cos(a), -1.5 + 1.1*math.sin(a)], 'radius': .3}
            for k, a in enumerate(i*math.pi/6 for i in range(12))]
    rec = make(beam, obstacles=ring, route_mode='detour_v1').route_record()
    json.dumps(rec, allow_nan=False)
    assert rec['outcome'] == ct.NO_PATH and rec['route_info']['detour']['search']['found'] is False


def test_route_record_does_not_change_the_diagnostic():
    a = make((.7, -1.5, .3))
    before = json.dumps(a.diagnostic(), sort_keys=True)
    a.route_record()
    assert json.dumps(a.diagnostic(), sort_keys=True) == before
    assert 'route_plans' not in a.diagnostic() and 'route_plans' not in a.route_info


def test_runner_writes_route_at_handover_only_for_opt_in_modes():
    src = (Path(ct.__file__).resolve().parents[1]/'scripts/run_grasp_act_teacher.py').read_text()
    i = src.index('carry=start_from_runner(')
    block = src[i:src.index('recorders=', i)]
    assert "if carry_route!='straight_v1':" in block
    assert "write(out/'carry-route.json',planned)" in block
    assert "CARRY_ROUTE_PLANNED" in block and 'flush=True' in block
    # start_from_runner stays in the carry-is-None branch: called once per episode
    assert src.count('carry=start_from_runner(') == 1
    assert src.index('elif carry is not None:') < i
