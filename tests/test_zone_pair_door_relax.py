"""b-v6h door-guard relaxation (stage-probe opt-in; no physics, no models).

The registered b-v6e / b-v6g sources must stay byte-identical: the relaxation lives in
``harness/zone_pair_door_relax.py`` and is applied to the running probe process only.
"""
import hashlib
import math
from pathlib import Path

import pytest

import harness.zone_own_guards as guards
import harness.zone_pair_door_relax as relax
import harness.zone_pair_geometry as geometry
import harness.zone_pair_guards as pair_guards
from harness import pair_stage_probe as sp
from harness.zone_own_guards import OwnPose
from tests.test_zone_pair_grasp import real_pair

ROOT = Path(__file__).resolve().parents[1]
CMD = {'kind': 'mecanum', 'forward': .05, 'left': 0., 'turn': 0., 'duration_s': .15}


@pytest.fixture
def restore(monkeypatch):
    """Undo every process-local patch a test installs."""
    for obj, name in ((guards.SweepGuard, 'margin'), (geometry.PairSweepGuard, 'motion_clear')):
        monkeypatch.setattr(obj, name, getattr(obj, name))
    for module in (guards, pair_guards):
        monkeypatch.setattr(module, 'GATE_LOADED', module.GATE_LOADED)
    import harness.zone_own_driver as driver
    import harness.zone_own_sweep as sweep
    for module in (driver, sweep):
        monkeypatch.setattr(module, 'GATE_LOADED', module.GATE_LOADED)
    relax.EVENTS.clear()
    relax._BUDGET.clear()


def pair_guard():
    _, _, eps = real_pair()
    ep = eps['r1']
    return ep, geometry.PairSweepGuard(ep.own.guard, ep.plan['beam_geometry'], ep.arguments['role'])


def test_registered_sources_are_not_touched_by_this_change():
    """The relaxation adds files only; none of the sealed closure is modified (the sealing test checks the bytes)."""
    import json
    prereg = json.loads((ROOT / 'experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json').read_text())
    for path, expected in prereg['v6_contract']['source_sha256'].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    assert 'harness/zone_pair_door_relax.py' not in prereg['v6_contract']['source_sha256']


def test_relaxed_margin_at_the_registered_multiples_is_the_registered_margin():
    _, guard = pair_guard()
    pose = OwnPose(2., .05, 0., .043, .038)
    registered = guards.SweepGuard.margin(guard, pose, .18)
    assert relax.relaxed_margin(guards.K_SIGMA, guards.K_SIGMA)(guard, pose, .18) == pytest.approx(registered)
    assert registered == pytest.approx(relax.needed_clearance_m(2., .043, 2., .038))   # the hR_analysis need formula
    # the fixed part (0.02 + 0.015) stays in every variant
    assert relax.relaxed_margin(0., 0.)(guard, pose, .18) == pytest.approx(.035)
    assert relax.relaxed_margin(1., 1.)(guard, pose, .18) == pytest.approx(.035 + .043 + .038 * .18)


def test_relaxed_margin_keeps_the_registered_sigma_caps():
    _, guard = pair_guard()
    big = OwnPose(2., 0., 0., 9., 9.)
    capped = relax.relaxed_margin(1., 1.)(guard, big, .2)
    assert capped == pytest.approx(.035 + guards.SIGMA_CAP_XY_M + guards.SIGMA_CAP_YAW_RAD * .2)


def test_variants_only_relax_never_tighten():
    for name, v in relax.VARIANTS.items():
        assert v['k_xy'] <= relax.REGISTERED['k_xy'] and v['k_yaw'] <= relax.REGISTERED['k_yaw'], name
        if v['gate_yaw_deg']:
            assert v['gate_yaw_deg'][0] > relax.REGISTERED['gate_yaw_deg'][0]
            assert v['gate_yaw_deg'][1] < v['gate_yaw_deg'][0]
    assert [n for n, v in relax.VARIANTS.items() if v['advisory_s']] == ['adv']
    with pytest.raises(ValueError, match='unknown door-relax variant'):
        relax.variant('k3')


def door_scan(guard, ep, ys):
    out = []
    for y in ys:
        out.append(guard.motion_clear(ep.own.servo, OwnPose(2., y, 0., .04, .04), CMD, loaded=True))
    return out


def test_the_relaxation_lets_a_pair_through_the_door_that_the_registered_guard_refuses(restore):
    ep, guard = pair_guard()
    ys = [-.06, -.04, -.02, 0., .02, .04]
    assert door_scan(guard, ep, ys) == [False, False, False, False, True, True]     # registered: 2 sigma of 4 cm / 2.3 deg
    assert relax.install('k1')['variant'] == 'k1'
    assert door_scan(guard, ep, ys) == [False, True, True, True, True, True]
    relax.install('k0')
    assert door_scan(guard, ep, ys) == [True] * 6


def test_the_relaxation_never_lets_a_command_through_that_overlaps_a_post(restore):
    """k0 keeps the fixed 0.035 m: a robot that is (by its own estimate) on top of the post is still refused."""
    ep, guard = pair_guard()
    relax.install('k0')
    on_post = OwnPose(2.2, .36, 0., .01, .01)       # the estimate sits inside post_door_1_hi (2.2, 0.35)
    assert guard.motion_clear(ep.own.servo, on_post, CMD, loaded=True) is False


def test_gate_widening_rebinds_every_module_that_holds_the_loaded_gate(restore):
    import harness.zone_own_driver as driver
    import harness.zone_own_sweep as sweep
    reg = guards.GATE_LOADED
    relax.install('k0')
    assert guards.GATE_LOADED is reg and pair_guards.GATE_LOADED is reg      # k0 leaves the gate registered
    relax.install('k0g')
    for module in (guards, driver, sweep, pair_guards):
        assert math.degrees(module.GATE_LOADED.high_yaw_rad) == pytest.approx(5.)
        assert math.degrees(module.GATE_LOADED.low_yaw_rad) == pytest.approx(4.)
        assert module.GATE_LOADED.high_xy_m == reg.high_xy_m and module.GATE_LOADED.low_xy_m == reg.low_xy_m
        assert module.GATE_LOADED.enter_dwell_s == reg.enter_dwell_s and module.GATE_LOADED.exit_dwell_s == reg.exit_dwell_s


def test_advisory_override_is_bounded_logged_and_per_role(restore):
    ep, guard = pair_guard()
    relax.install('adv')
    far_left = OwnPose(2., -.20, 0., .04, .04)      # in the post: refused even without any sigma inflation
    assert geometry.PairSweepGuard.motion_clear is not None
    # 3 s of 0.15 s commands are waved through, the 21st is refused; not loaded is never waved through
    assert guard.motion_clear(ep.own.servo, far_left, CMD, loaded=False) is False
    results = [guard.motion_clear(ep.own.servo, far_left, CMD, loaded=True) for _ in range(22)]
    assert results[:20] == [True] * 20 and results[20:] == [False, False]
    assert len(relax.EVENTS) == 20 and relax.EVENTS[0]['cmd']['forward'] == .05
    assert relax.EVENTS[-1]['used_s'] == pytest.approx(3.0)
    assert set(relax.EVENTS[0]) >= {'own_estimate', 'std_xy_m', 'std_yaw_rad', 'cmd', 'role'}
    # a different role has its own budget
    _, _, eps = real_pair()
    other = geometry.PairSweepGuard(eps['r2'].own.guard, eps['r2'].plan['beam_geometry'], eps['r2'].arguments['role'])
    assert other.motion_clear(eps['r2'].own.servo, far_left, CMD, loaded=True) is True


def test_advisory_never_waves_through_a_malformed_command(restore):
    ep, guard = pair_guard()
    relax.install('adv')
    far_left = OwnPose(2., -.20, 0., .04, .04)
    for bad in (dict(CMD, duration_s=2.), dict(CMD, duration_s=float('nan')), dict(CMD, duration_s=None)):
        assert guard.motion_clear(ep.own.servo, far_left, bad, loaded=True) is False


def test_install_none_is_a_noop(restore):
    margin, motion = guards.SweepGuard.margin, geometry.PairSweepGuard.motion_clear
    assert relax.install(None) is None
    assert guards.SweepGuard.margin is margin and geometry.PairSweepGuard.motion_clear is motion


# ---------------------------------------------------------------- stage-probe case generation

def teacher(policy, leg, **kw):
    return sp.teacher_cases('carry', policy=policy, leg=leg, prior_std='e2e', subset={'nominal'}, nominal_seeds=(911,), **kw)


def test_b_v6h_cases_run_the_registered_b_v6g_and_carry_the_variant():
    (case,) = teacher('b-v6h', 1, door_relax='k0g')
    assert case['pair_policy'] == 'b-v6g'                               # the spec, the controller and the receipts see b-v6g
    assert (case['policy_id'], case['door_relax'], case['contact_track']) == ('b-v6h', 'k0g', True)
    assert case['case_id'].startswith('carry@b-v6h.k0g:teacher:nominal:')
    (base,) = teacher('b-v6g', 1)
    assert 'door_relax' not in base and 'policy_id' not in base and 'contact_track' not in base
    stripped = {k: v for k, v in case.items() if k not in ('case_id', 'policy_id', 'door_relax', 'contact_track')}
    assert stripped == {k: v for k, v in base.items() if k != 'case_id'}   # same staging, prior, route, seed


def test_b_v6h_needs_a_variant_and_no_other_policy_accepts_one():
    with pytest.raises(ValueError, match='needs a door-relax variant'):
        teacher('b-v6h', 1)
    with pytest.raises(ValueError, match='unknown door-relax variant'):
        teacher('b-v6h', 1, door_relax='k5')
    with pytest.raises(ValueError, match='applies to policy b-v6h only'):
        teacher('b-v6g', 1, door_relax='k0')


def test_the_registered_policy_case_ids_are_unchanged():
    (case,) = teacher('b-v6g', 1)
    assert case['case_id'] == 'carry@b-v6g:teacher:nominal:s911:pE2E:L1'


# ---------------------------------------------------------------- eval-side outcome class

def _outcome(passed, episodes, tilt=2., submit=5., stop=30.):
    from scripts import run_pair_stage_probes as runner
    row = {'passed': passed}
    result = {'wall_contact': {'episodes': episodes}, 'submit_t': submit, 'gt_at_stop': {'t': stop}, 'max_tilt_deg': tilt}
    return runner.contact_outcome(row, result)


def ep(who='r1', t0=10., t1=11., pen=.001, wall='zone_wall_x'):
    return {'who': who, 'wall_geom': wall, 'other_geom': 'r1__body', 't_first': t0, 't_last': t1, 'steps': 5, 'max_pen_m': pen}


def test_outcome_classes():
    assert _outcome(True, [])[0] == 'PASS_CLEAN'
    assert _outcome(True, [ep()])[0] == 'PASS_CONTACT_RECOVERED'
    assert _outcome(True, [ep(pen=.0051)])[0] == 'FAIL_HARD_LIMIT'         # > 5 mm penetration
    assert _outcome(True, [ep(pen=.005)])[0] == 'PASS_CONTACT_RECOVERED'   # the limit itself is allowed
    assert _outcome(True, [], tilt=15.01)[0] == 'FAIL_HARD_LIMIT'          # > 15 deg tilt over the stage
    assert _outcome(True, [], tilt=15.)[0] == 'PASS_CLEAN'
    assert _outcome(False, [ep()])[0] == 'FAIL' and _outcome(False, [])[0] == 'FAIL'


def test_contact_before_the_submit_or_after_the_stop_is_not_counted():
    assert _outcome(True, [ep(t0=1., t1=4.9)])[0] == 'PASS_CLEAN'          # staging window
    assert _outcome(True, [ep(t0=30.5, t1=31.)])[0] == 'PASS_CLEAN'        # after the stage stop
    assert _outcome(True, [ep(t0=4., t1=5.5)])[0] == 'PASS_CONTACT_RECOVERED'   # overlaps the submit


def test_outcome_summary_names_who_touched_what():
    outcome, s = _outcome(True, [ep('r2', pen=.002, wall='zone_wall_post_a'), ep('beam', pen=.004, wall='zone_wall_post_a')])
    assert outcome == 'PASS_CONTACT_RECOVERED'
    assert s['who'] == ['beam', 'r2'] and s['max_penetration_m'] == .004 and s['episodes'] == 2
    assert s['hard_limits'] == {'max_tilt_deg': 15., 'max_penetration_m': .005}


# ---- review fixes (PR #281): registry, grouping key, stage limit ----

def test_b_v6h_is_probe_only_not_a_registered_policy():
    from harness import pair_stage_probe as sp
    assert 'b-v6h' not in sp.POLICIES and 'b-v6h' in sp.PROBE_ONLY_POLICIES
    assert sp._pid('b-v6h')                          # accepted for case ids
    with pytest.raises(ValueError):
        sp._pid('b-v9z')


def test_policy_key_and_summary_group_by_variant_not_registered_policy():
    from harness import pair_stage_probe as sp
    assert sp.policy_key({'pair_policy': 'b-v6g'}) == 'b-v6g'
    assert sp.policy_key({'pair_policy': 'b-v6g', 'policy_id': 'b-v6h', 'door_relax': 'k1g'}) == 'b-v6h.k1g'
    assert sp.policy_key({}) == 'v5h'
    rows = [{'stage': 'carry', 'source': 'teacher', 'passed': p, 'category': 'x', 'cause': None, 'pair_policy': 'b-v6g', **extra}
            for p, extra in ((True, {}), (False, {'policy_id': 'b-v6h', 'door_relax': 'k1g'}),
                             (True, {'policy_id': 'b-v6h', 'door_relax': 'k0g'}))]
    bp = sp.summarize(rows)['stages']['carry']['by_policy']
    assert set(bp) == {'b-v6g', 'b-v6h.k1g', 'b-v6h.k0g'}
    assert bp['b-v6h.k1g']['passed'] == 0 and bp['b-v6h.k0g']['passed'] == 1


def test_view_abbreviations_cover_every_variant_uniquely():
    import importlib.util
    spec = importlib.util.spec_from_file_location('views', ROOT / 'scripts' / 'build_pair_stage_probe_views.py')
    views = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(views)
    from harness import zone_pair_door_relax as relax
    for v in relax.VARIANTS:
        assert f'b-v6h.{v}' in views.POLICY_SHORT
    vals = [x for x in views.POLICY_SHORT.values() if x]
    assert len(vals) == len(set(vals))


def test_b_v6h_limited_to_carry_and_setdown():
    from harness import pair_stage_probe as sp
    for stage in ('grasp_lift', 'chain'):
        with pytest.raises(ValueError):
            sp.teacher_cases(stage, policy='b-v6h', door_relax='k1')
    assert sp.teacher_cases('carry', policy='b-v6h', door_relax='k1', leg=1)
