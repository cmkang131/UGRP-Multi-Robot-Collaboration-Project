"""Frozen 3x120 P03 cap and continuous-HIGH carried-prefix receipts."""
import copy
import pytest
from harness import zone_pair_highpose_timing as t
from harness import zone_pair_highpose_contract as c
from harness import zone_pair_highpose as pose
from scripts import run_pair_highpose as run


def test_frozen_cap_rejects_last_checkpoint_and_full_carry():
    static = c.resolve('zone_wide_door_geometry_v3')[0]
    rows = t.bounds(static, 'p03')
    assert [r['segment'] for r in rows] == [1, 3, 7]
    assert [r['lower_bound_s'] for r in rows] == pytest.approx([63.83, 104.17, 184.57], abs=.01)
    assert [r['feasible'] for r in rows] == [True, True, False]
    for r in rows:
        p = r['parts_s']
        assert r['cap_s'] == 120 and p['raise_to_high_s'] == 17.2 and p['low_lift_s'] == 1.5
        assert p['intermediate_lower_open_raise_s'] == 0 and 'final_lower_s' not in p
        assert p['leg_align_s'] == pytest.approx(6.5*r['segment'])
        assert p['checkpoint_reobserve_s'] == pytest.approx(1.2*r['segment'])
        # Realistic, code-derived approach: 0.12 cmd x FORWARD_GAIN, two sweeps.
        assert p['approach_translation_s'] == pytest.approx(r['approach_straight_m']/(.12*2.2/1.4))
        assert p['initial_look_sweep_s'] == p['arrival_check_sweep_s'] == pytest.approx(3.6)
    # Infeasibility does not come from the HIGH arm timing: even with the raise
    # and every per-leg align at 0 s, travel at the registered 0.06 m/s fails.
    last = rows[-1]['parts_s']
    assert rows[-1]['lower_bound_s']-last['raise_to_high_s']-last['leg_align_s'] > 120
    assert t.require_feasible(static, 'before_door') and t.require_feasible(static, 'after_door')
    with pytest.raises(ValueError, match='TIME_LOWER_BOUND_EXCEEDS_CAP_120: before_destination'):
        t.require_feasible(static)
    assert sum(row['sim_cap_s'] for row in c.cases('p03')) == 360
    assert sum(d+s for _, d, s in pose.lower_path()) == pytest.approx(13.6)
    for map_id in c.registry()['maps']:
        (row,) = t.bounds(c.resolve(map_id)[0], 'carry')
        assert not row['feasible'] and row['parts_s']['final_lower_s'] == pytest.approx(13.6)
        with pytest.raises(ValueError, match='carry_full_route'):
            t.require_feasible(c.resolve(map_id)[0], 'carry_full_route', 'carry')


def test_measured_lag_only_increases_the_bound(tmp_path, monkeypatch):
    from tests.highpose_fixtures import d5_output
    _, cal = d5_output(tmp_path)
    static = c.resolve('zone_wide_door_geometry_v3')[0]
    plain = {r['case']: r['lower_bound_s'] for r in t.bounds(static)}
    lagged = {r['case']: r for r in t.bounds(static, calibration=cal)}
    assert all(lagged[k]['lower_bound_s'] >= plain[k] for k in plain)
    assert all(r['calibration_lag'] == 'measured' for r in lagged.values())


def test_plan_lists_bounds_and_blocks_infeasible_cases(capsys):
    import json
    assert run.main(['--check', 'p03', '--expected-source-sha', 'a'*40, '--output', '/nonexistent/x']) == 0
    plan = json.loads(capsys.readouterr().out)
    assert [r['case'] for r in plan['time_lower_bounds']] == ['before_door', 'after_door', 'before_destination']
    assert 'TIME_LOWER_BOUND_EXCEEDS_CAP_120: zone_wide_door_geometry_v3/before_destination' in plan['blocked_on']
    assert plan['cohort_role'] == 'FUNCTIONAL_DEV_REPLAY' and plan['confirmation_sample'] is False
    assert run.main(['--check', 'carry', '--expected-source-sha', 'a'*40, '--output', '/nonexistent/x']) == 0
    plan = json.loads(capsys.readouterr().out)
    assert len([b for b in plan['blocked_on'] if b.startswith('TIME_LOWER_BOUND')]) == 3


def test_checkpoint_needs_carried_prefix_for_both_robots():
    events = [{'event':'state','state':'carry','seg':i} for i in range(3)]
    events += [{'event':kind,'seg':3,'high':True,'opened':False}
               for kind in ('checkpoint_high_stop','checkpoint_high_reobserved')]
    record = {'pair':[{'plan':{'checkpoint_segments':{'after_door':3}},
                      'robots':{r:{'events':copy.deepcopy(events)} for r in c.ROBOTS}}]}
    got = run.checkpoint_record(record,'after_door')
    assert got['status'] == 'SEQUENCE_OBSERVED_UNQUALIFIED' and got['confirmation_sample'] is False
    record['pair'][0]['robots']['r2']['events'].pop(0)
    assert run.checkpoint_record(record,'after_door')['status'] == 'NOT_REACHED'
