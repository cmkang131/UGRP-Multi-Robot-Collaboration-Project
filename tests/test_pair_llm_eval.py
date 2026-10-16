"""The provisional pair judge and the metric row. Evaluation only; no physics, network or model."""
import math

import pytest

from harness import pair_llm_eval as ev
from harness import zone_final_pair_contract as c

STATIC = c.resolve('zone_wide_door_geometry_v3')[0]
B = STATIC['regions']['zone_B']['center_m']


def rows(points, dt=.05, t0=1.):
    return [{'t': round(t0 + i * dt, 6), 'beam_xyz_m': list(p)} for i, p in enumerate(points)]


def judge(points, **kw):
    return ev.judge(rows(points), static_map=STATIC, target_zone='B', start_s=1., **kw)


def test_a_lifted_delivered_and_set_down_beam_is_a_provisional_success():
    z0 = .03
    path = [(1., .05, z0)] * 5 + [(1., .05, z0 + .1)] * 5 + [(B[0], B[1], z0 + .1)] * 3 + [(B[0], B[1], z0)] * 5
    verdict = judge(path)
    assert verdict['success_provisional'] and verdict['reason'] == 'OK'
    assert verdict['in_zone_final'] and verdict['lifted'] and verdict['set_down']
    assert verdict['judge_status'] == ev.JUDGE_STATUS and 'NOT_THE_363_JUDGE' in verdict['judge_status']
    assert verdict['delivery_s'] is not None and verdict['first_motion_s'] is not None


@pytest.mark.parametrize('name, path, reason', [
    ('never moved', [(1., .05, .03)] * 12, 'NOT_IN_ZONE'),
    ('dragged, never lifted', [(1., .05, .03)] * 3 + [(B[0], B[1], .03)] * 8, 'NEVER_LIFTED'),
    ('left in the air', [(1., .05, .03)] * 3 + [(B[0], B[1], .20)] * 8, 'NOT_SET_DOWN'),
])
def test_failures_are_named(name, path, reason):
    if reason == 'NOT_SET_DOWN':
        path = [(1., .05, .03)] * 3 + [(1., .05, .15)] * 3 + path[3:]
    verdict = judge(path)
    assert not verdict['success_provisional'] and verdict['reason'] == reason, name


def test_no_trajectory_is_never_a_success():
    assert ev.judge([], static_map=STATIC, target_zone='B')['reason'] == 'NO_TRAJECTORY'
    assert not ev.judge(rows([(1., 0., .03)]), static_map=STATIC, target_zone='B')['success_provisional']


def test_trial_metrics_without_a_trial_is_the_rule_row():
    row = ev.trial_metrics(condition='rule', verdict={'success_provisional': True, 'judge_status': ev.JUDGE_STATUS},
                           command_counts={'r1': 4, 'r2': 6}, end_sim_s=12.)
    assert row['success'] is True and row['command_count_total'] == 10 and row['model_calls'] == 0
    assert row['self_sabotage'] == {'events': 0, 'rows': []} and row['language']['share'] is None and row['language']['gate'] is False
    assert math.isclose(row['end_sim_s'], 12.)
