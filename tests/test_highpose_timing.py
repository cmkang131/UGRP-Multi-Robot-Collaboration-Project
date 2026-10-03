"""v96 per-case cap (coordinator amendment 300 SIM s) and its automatic time lower bound."""
import copy
import pytest
from harness import zone_pair_highpose_timing as t
from harness import zone_pair_highpose_contract as c
from harness import zone_pair_highpose as pose
from scripts import run_pair_highpose as run


def test_bounds_from_controller_constants_and_amended_cap():
    static = c.resolve('zone_wide_door_geometry_v3')[0]
    rows = t.bounds(static, 'p03')
    assert [r['segment'] for r in rows] == [1, 3, 7]
    assert [r['lower_bound_s'] for r in rows] == pytest.approx([63.83, 104.17, 184.57], abs=.01)
    assert t.CAP_S == c.CASE_CAP_S == 300. and [r['feasible'] for r in rows] == [True, True, True]
    for r in rows:
        p = r['parts_s']
        assert r['cap_s'] == 300 and p['raise_to_high_s'] == 17.2 and p['low_lift_s'] == 1.5
        assert p['intermediate_lower_open_raise_s'] == 0 and 'final_lower_s' not in p
        assert p['leg_align_s'] == pytest.approx(6.5*r['segment'])
        assert p['checkpoint_reobserve_s'] == pytest.approx(1.2*r['segment'])
        # Realistic, code-derived approach: 0.12 cmd x FORWARD_GAIN, two sweeps.
        assert p['approach_translation_s'] == pytest.approx(r['approach_straight_m']/(.12*2.2/1.4))
        assert p['initial_look_sweep_s'] == p['arrival_check_sweep_s'] == pytest.approx(3.6)
    # The binding term is travel at the registered 0.06 m/s, not HIGH arm timing.
    last = rows[-1]['parts_s']
    assert rows[-1]['lower_bound_s']-last['raise_to_high_s']-last['leg_align_s'] > 120
    assert len(t.require_feasible(static)) == 3
    assert [row['sim_cap_s'] for row in c.cases('p03')] == [300.]*3
    assert sum(d+s for _, d, s in pose.lower_path()) == pytest.approx(13.6)
    carry = [t.bounds(c.resolve(m)[0], 'carry')[0] for m in c.registry()['maps']]
    assert [r['lower_bound_s'] for r in carry] == pytest.approx([219.34, 219.34, 190.44], abs=.01)
    assert all(r['feasible'] and r['parts_s']['final_lower_s'] == pytest.approx(13.6) for r in carry)
    # 300 s was set a priori at ~1.4x the largest bound (full carry 219.3 s).
    assert 1.3 < c.CASE_CAP_S/max(r['lower_bound_s'] for r in carry) < 1.45


def test_automatic_bound_still_rejects_a_cap_below_the_bound(monkeypatch):
    static = c.resolve('zone_wide_door_geometry_v3')[0]
    monkeypatch.setattr(t, 'CAP_S', 120.)
    with pytest.raises(ValueError, match='TIME_LOWER_BOUND_EXCEEDS_CASE_CAP: before_destination'):
        t.require_feasible(static)
    assert t.require_feasible(static, 'before_door') and t.require_feasible(static, 'after_door')
    with pytest.raises(ValueError, match='carry_full_route'):
        t.require_feasible(static, 'carry_full_route', 'carry')


def test_cap_amendment_is_registered_prereg_and_hashed_in_bundle():
    reg = c.registry()
    cap = reg['case_cap']
    assert cap['sim_cap_s'] == 300. and cap['decided_before_p03_data'] is True
    assert cap['decision'] == c.CAP_DECISION and 'v88' in cap['supersedes']
    b = c.bundle('zone_wide_door_geometry_v3', 'p03')
    assert c.CAP_DECISION in b['source_sha256'] and c.REGISTRY in b['source_sha256']
    assert b['timing']['case_sim_cap_s'] == 300.
    obs = b['timing']['observation']
    assert obs['carry_hold_look_every_s'] == .4 and obs['transit_rgb_sample_s'] == .1
    bad = copy.deepcopy(reg)
    bad['case_cap']['sim_cap_s'] = 120.
    import harness.zone_pair_highpose_contract as mod
    orig = mod.base.read
    try:
        mod.base.read = lambda path: bad if str(path).endswith(c.REGISTRY) else orig(path)
        with pytest.raises(ValueError, match='registry mismatch'):
            c.registry()
    finally:
        mod.base.read = orig


def test_measured_lag_only_increases_the_bound(tmp_path, monkeypatch):
    from tests.highpose_fixtures import d5_output
    _, cal = d5_output(tmp_path)
    static = c.resolve('zone_wide_door_geometry_v3')[0]
    plain = {r['case']: r['lower_bound_s'] for r in t.bounds(static)}
    lagged = {r['case']: r for r in t.bounds(static, calibration=cal)}
    assert all(lagged[k]['lower_bound_s'] >= plain[k] for k in plain)
    assert all(r['calibration_lag'] == 'measured' for r in lagged.values())


def test_plan_runs_all_three_cases_under_the_amended_cap(capsys, monkeypatch):
    import json
    assert run.main(['--check', 'p03', '--expected-source-sha', 'a'*40, '--output', '/nonexistent/x']) == 0
    plan = json.loads(capsys.readouterr().out)
    assert [r['case'] for r in plan['time_lower_bounds']] == ['before_door', 'after_door', 'before_destination']
    assert plan['denominator'] == 3 and all(r['feasible'] for r in plan['time_lower_bounds'])
    assert not [b for b in plan['blocked_on'] if b.startswith('TIME_LOWER_BOUND')]
    assert plan['cohort_role'] == 'FUNCTIONAL_DEV_REPLAY' and plan['confirmation_sample'] is False
    assert run.main(['--check', 'carry', '--expected-source-sha', 'a'*40, '--output', '/nonexistent/x']) == 0
    plan = json.loads(capsys.readouterr().out)
    assert not [b for b in plan['blocked_on'] if b.startswith('TIME_LOWER_BOUND')]
    # The plan reports exactly what the code enforces (no doc/code split).
    monkeypatch.setattr(t, 'CAP_S', 120.)
    assert run.main(['--check', 'p03', '--expected-source-sha', 'a'*40, '--output', '/nonexistent/x']) == 0
    plan = json.loads(capsys.readouterr().out)
    assert 'TIME_LOWER_BOUND_EXCEEDS_CASE_CAP: zone_wide_door_geometry_v3/before_destination' in plan['blocked_on']
