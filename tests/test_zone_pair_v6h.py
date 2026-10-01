"""v6h pre-seal registered controller: pure PF/geometry/fake controller, no physics or models."""
import copy
from dataclasses import replace
import hashlib
import importlib
import json
import math
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from harness import owncam_carry_v6e as carry
from harness import zone_own_guards as guards
from harness.owncam_pose_source import OwnCamPoseSource
from harness.zone_pair_geometry import PairSweepGuard
from harness.zone_pair_guards import MovedFixMonitor
from harness.zone_pair_v6_policy import POLICIES, REVISION_POLICIES, PairPolicy, pair_policy
from tests.test_zone_pair_v6e import V6, cloud, _team, _axial_schedule, _lateral_schedule
from tests.test_zone_pair_grasp import beam_fit

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((ROOT/'tests/fixtures/zone_pair_v6h/off_golden.json').read_text())
FLAGS = ('carry_fwd_gain', 'loaded_k_xy', 'loaded_k_yaw', 'loaded_gate_yaw_deg',
         'progress_arm_on_moved_fix', 'carry_axial_lag', 'door_relax_sigma_scope')
BUILDER = importlib.import_module('experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h')


@pytest.fixture(scope='module')
def baseline_carry():
    """Compare exact PF bytes on this host; libm/NumPy bytes differ across hosts.

    The PF and its dependencies are unchanged. Execute only the frozen carry
    module, with a separate namespace/provider, never an old simulation runner.
    Fixed Mac mean/std goldens below still apply with the 1e-9 tolerance.
    """
    from scripts.zone_pair_registered_source import committed_blob
    for path in ('harness/owncam_localizer.py', 'harness/own_beam_edge.py'):
        assert (ROOT/path).read_bytes() == committed_blob(str(ROOT), GOLDEN['source_commit'], path)
    path = 'harness/owncam_carry_v6e.py'
    raw = committed_blob(str(ROOT), GOLDEN['source_commit'], path)
    module = ModuleType('v6h_off_baseline_carry')
    module.__file__ = str(ROOT/path)
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def _off_pf_trace(name, carry_module):
    loc = cloud(); p = pair_policy(name); provider = SimpleNamespace(loc=loc)
    info = None
    if p.carry_dr_model:
        info = carry_module.enable_provider(provider, pair_yaw=p.carry_pair_yaw,
                                            beam_edge=p.carry_beam_edge, general=p.carry_dr_general)
    loc.predict_to(2.)
    loc.command({'t': 2., 'kind': 'mecanum', 'forward': .035, 'left': 0., 'turn': 0., 'duration_s': 4.})
    loc.predict_to(7.)
    loc.command({'t': 7., 'kind': 'mecanum', 'forward': 0., 'left': .025, 'turn': .01, 'duration_s': 3.})
    loc.predict_to(11.)
    return loc, info


@pytest.mark.parametrize('name', GOLDEN['policies'])
def test_all_existing_policy_fields_are_unchanged_and_new_flags_default_off(name):
    p = pair_policy(name)
    assert {k: v for k, v in vars(p).items() if k not in FLAGS} == GOLDEN['policies'][name]['flags']
    assert tuple(getattr(p, k) for k in FLAGS) == (1., 2., 2., None, False, False, 'loaded_base_motion')


def test_bv6h1_is_bv6g_plus_exactly_the_five_decided_options():
    g, h = pair_policy('b-v6g'), pair_policy('b-v6h1')
    assert replace(h, name=g.name, **{k: getattr(g, k) for k in FLAGS}) == g
    assert tuple(getattr(h, k) for k in FLAGS) == (carry.FWD_GAIN, 1., 1., (5., 4.), True, True, 'probe_all_sweeps')
    assert REVISION_POLICIES['v6h'] == ('v5h', 'b-only', 'b-v6h1')


@pytest.mark.parametrize('name', GOLDEN['policies'])
def test_flags_off_localizer_is_bit_identical_to_main_a8094cc1(name, baseline_carry):
    loc, info = _off_pf_trace(name, carry)
    old, old_info = _off_pf_trace(name, baseline_carry)
    gold = GOLDEN['policies'][name]
    assert loc.px.mean(0) == pytest.approx(gold['mean'], abs=1e-9, rel=0)
    assert loc.px.std(0) == pytest.approx(gold['std'], abs=1e-9, rel=0)
    assert loc.px.tobytes() == old.px.tobytes()
    assert loc.rng.bit_generator.state == old.rng.bit_generator.state
    assert float(loc.rng.random()) == pytest.approx(gold['rng_next'], abs=1e-12, rel=0)
    assert info == old_info == gold['info']


def test_gain_only_changes_loaded_00_once_and_does_not_mutate_other_providers_or_inputs():
    params = copy.deepcopy(V6['params']); original = copy.deepcopy(params)
    p, q = [OwnCamPoseSource(V6['map'], params, seed=628) for _ in range(2)]
    ordinary = carry.enable_provider(q, pair_yaw=True, beam_edge=True, general=True)
    info = carry.enable_provider(p, pair_yaw=True, beam_edge=True, general=True, carry_fwd_gain=carry.FWD_GAIN)
    before = copy.deepcopy(q.loc.params)
    assert p.loc.params['motion'] == q.loc.params['motion']
    expected = copy.deepcopy(q.loc.params['motion_loaded']); expected['gain'][0][0] *= carry.FWD_GAIN
    assert p.loc.params['motion_loaded'] == expected and params == original
    assert info['gain_fix']['file_sha256'] == carry.FWD_GAIN_FIT_SHA256
    bound_params = p.loc.params
    assert carry.enable_provider(p, pair_yaw=True, beam_edge=True, general=True, carry_fwd_gain=carry.FWD_GAIN) is info
    assert p.loc.params is bound_params and q.loc.params == before and 'gain_fix' not in ordinary
    for multiplier in (1.0, .95):
        with pytest.raises(ValueError, match='fresh provider'):
            carry.enable_provider(p, pair_yaw=True, beam_edge=True, general=True, carry_fwd_gain=multiplier)


@pytest.mark.parametrize('invalid', [.95, float('nan'), float('inf')])
def test_unregistered_gain_value_fails_without_mutating_provider(invalid):
    p = OwnCamPoseSource(V6['map'], V6['params'], seed=628); original = copy.deepcopy(p.loc.params)
    with pytest.raises(ValueError, match='fixed PR #284'):
        carry.enable_provider(p, carry_fwd_gain=invalid)
    assert p.loc.params == original and not carry.bound(p)


def test_gain_fit_hash_is_verified(monkeypatch, tmp_path):
    bad = tmp_path/'fit.json'; bad.write_text('{}')
    monkeypatch.setattr(carry, 'FWD_GAIN_FIT', str(bad))
    with pytest.raises(ValueError, match='hash mismatch'):
        carry.forward_gain_receipt(carry.FWD_GAIN)


def test_flags_off_margin_gate_and_progress_match_main_goldens():
    # Main a8094cc1: BASE .020 + residual .015 + 2*.04 + 2*.03*.7.
    pose = guards.OwnPose(0., 0., 0., .04, .03)
    guard = guards.SweepGuard({})
    assert guard.margin(pose, .7) == pytest.approx(.157, abs=1e-9, rel=0)
    assert guard.margin(pose, .7, loaded=True) == guard.margin(pose, .7)
    assert guards.loaded_gate_profile() is guards.GATE_LOADED
    gate = guards.UncertaintyGate(guards.loaded_gate_profile())
    assert (gate.profile.high_yaw_rad, gate.profile.low_yaw_rad) == pytest.approx(
        (math.radians(3.), math.radians(2.5)), abs=1e-9, rel=0)
    assert [gate.update(t, True, .04, .03) for t in (0., .2, .4)] == [None, None, 'exited']
    assert gate.allows(True, .04, .03) and not gate.allows(True, .04, math.radians(4.))
    monitor = guards.ProgressMonitor(); monitor.trusted((0., 0.), 1.)
    monitor.drove(.4)
    assert monitor.baseline == (0., 0., 1., 0.) and monitor.needs_check() and not monitor.stalled()
    monitor.trusted((0., 0.), 1.)
    assert monitor.stalled() and monitor.checks == 0


@pytest.mark.parametrize('name', GOLDEN['pair_guard'])
def test_flags_off_pair_command_guard_matches_main_command_and_monitor_goldens(monkeypatch, name):
    from tests.test_zone_pair_executor import active
    flags = {k: v for k, v in vars(pair_policy(name)).items() if k != 'name'}
    host = _team(monkeypatch, 'guard-off-'+name, flags)
    ep = active(host)['r1']; ep.controller.state = 'carry'
    ep.own.last_report = replace(ep.own.last_report, fix_age_s=0., last_fix_t=0.)
    g = ep.command_guard
    cmd = {'kind': 'mecanum', 'forward': .01, 'left': 0., 'turn': 0., 'duration_s': .1}
    result = g.check(0., [cmd]); g.on_command({'t': 0., **cmd})
    gold = GOLDEN['pair_guard'][name]
    assert result == gold['commands'] and ep.controller.failure == gold['failure']
    assert g.monitor.baseline == pytest.approx(gold['baseline'], abs=1e-9, rel=0)
    assert g.monitor.commanded_m == pytest.approx(gold['commanded_m'], abs=1e-9, rel=0)
    assert ep.own.gate.as_dict() == gold['gate']


def test_default_sigma_scope_preserves_loaded_motion_only_selection(monkeypatch):
    from tests.test_zone_pair_executor import MAP
    from harness.zone_pair_executor import make_plan
    from tests.test_zone_pair_executor import SHEETS
    geometry = make_plan(MAP, SHEETS['cargoX'], 'B')['beam_geometry']
    own = guards.SweepGuard({})
    pg = PairSweepGuard(own, geometry, 'end_neg', loaded_k_xy=1., loaded_k_yaw=1.)
    pose = guards.OwnPose(0., 0., 0., .04, .03)
    servo = {1: 1500, 3: 1500, 4: 1500, 5: 1500, 6: 1500}
    assert pg.margin(pose, .7) == pytest.approx(.157, abs=1e-9)
    recorded = []
    def clearance(at):
        recorded.append(pg.margin(at, .7))
        return math.inf, None
    monkeypatch.setattr(pg, 'chassis_clearance', clearance)
    cmd = {'forward': 0., 'left': 0., 'turn': 0., 'duration_s': .1}
    for loaded, expected in ((False, .157), (True, .096)):
        recorded.clear(); assert pg.motion_clear(servo, pose, cmd, loaded=loaded)
        assert recorded and all(v == pytest.approx(expected, abs=1e-9) for v in recorded)
        assert pg.margin(pose, .7) == pytest.approx(.157, abs=1e-9)  # restored after motion
    pg.arm_clearance(servo, pose, loaded=True)
    assert not pg._loaded_motion and guards.K_SIGMA == 2.


@pytest.mark.parametrize('operation,loaded', [
    ('arm_clearance', False), ('arm_clearance', True),
    ('transition_clear', False), ('transition_clear', True),
    ('transition_diagnostic', False), ('transition_diagnostic', True),
    ('plan', False), ('plan', True),
    ('translation_clear', False), ('translation_clear', True),
    ('motion_clear', False), ('motion_clear', True),
    ('chassis_clearance', False), ('stationary_beam_clearance', False),
])
def test_bv6h1_every_sweep_margin_matches_probe_exactly(monkeypatch, operation, loaded):
    from tests.test_zone_pair_executor import active
    from harness.zone_pair_door_relax import relaxed_margin
    h = pair_policy('b-v6h1')
    ep = active(_team(monkeypatch, 'sigma-all', {k: v for k, v in vars(h).items() if k != 'name'}))['r1']
    pg = ep.command_guard.sweep_guard()
    # Keep every clearance positive so even full base paths visit every sample.
    pg.boxes = [{'id': 'far', 'center': (10., 10.), 'half': (.1, .1), 'yaw': 0., 'height': 1.}]
    pose = guards.OwnPose(0., 0., 0., .04, .03)
    servo = dict(ep.own.servo); target = {**servo, 6: servo[6] + 20}
    probe = PairSweepGuard(ep.own.guard, ep.plan['beam_geometry'], ep.arguments['role'])
    probe.boxes = pg.boxes
    seen = []
    registered = pg.margin
    def checked_margin(at, lever):
        actual = registered(at, lever)
        assert actual == relaxed_margin(1., 1.)(pg, at, lever)
        seen.append(actual)
        return actual
    monkeypatch.setattr(pg, 'margin', checked_margin)
    beam = {'grip_base_m': (.2, 0.), 'axis_heading_rad': 0., 'std_xy_m': .01, 'std_yaw_rad': .02}
    def evaluate(g):
        if operation == 'chassis_clearance': return g.chassis_clearance(pose)
        if operation == 'stationary_beam_clearance': return g.stationary_beam_clearance(beam, pose)
        if operation == 'arm_clearance': return g.arm_clearance(servo, pose, loaded=loaded)
        if operation.startswith('transition_'):
            return getattr(g, operation)(servo, target, pose, loaded=loaded)
        if operation == 'plan': return g.plan(servo, target, [servo[6]], pose, loaded=loaded)
        if operation == 'translation_clear': return g.translation_clear(servo, pose, .01, 0., loaded=loaded)
        return g.motion_clear(servo, pose, {'forward': .01, 'duration_s': .1}, loaded=loaded)
    actual = evaluate(pg)
    with monkeypatch.context() as patch:
        patch.setattr(guards.SweepGuard, 'margin', relaxed_margin(1., 1.))
        expected = evaluate(probe)
    assert seen and actual == expected
    assert not pg._loaded_motion and guards.K_SIGMA == 2.
    # The inherited probe formula retains the caps as well as the fixed 35 mm.
    large = guards.OwnPose(0., 0., 0., 9., 9.)
    assert registered(large, .7) == relaxed_margin(1., 1.)(pg, large, .7)


@pytest.mark.parametrize('name', GOLDEN['policies'])
def test_existing_policy_sweep_margins_keep_exact_2sigma_golden(monkeypatch, name):
    from tests.test_zone_pair_executor import active
    p = pair_policy(name)
    ep = active(_team(monkeypatch, 'sigma-off', {k: v for k, v in vars(p).items() if k != 'name'}))['r1']
    pg = ep.command_guard.sweep_guard()
    pose = guards.OwnPose(0., 0., 0., .04, .03)
    expected = .02 + .015 + 2. * .04 + 2. * .03 * .7
    assert ep.controller.driver.guard is ep.own.guard
    assert ep.own.guard.margin(pose, .7) == expected
    if p.beam_relative:
        expected = .02 + .015 + 2. * (.04 + .03 * .7)  # historical global arithmetic
    for moving in (False, True):
        pg._loaded_motion = moving
        assert pg.margin(pose, .7) == expected


def test_bv6h1_approach_guard_matches_probe_without_leaking_to_own_executor(monkeypatch):
    from tests.test_zone_pair_executor import active
    from harness.zone_pair_door_relax import relaxed_margin
    h = pair_policy('b-v6h1')
    ep = active(_team(monkeypatch, 'approach-sigma', {k: v for k, v in vars(h).items() if k != 'name'}))['r1']
    driver = ep.controller.driver
    pose = guards.OwnPose(0., 0., 0., .04, .03)
    assert driver.guard is not ep.own.guard
    assert driver.guard.margin(pose, .7) == relaxed_margin(1., 1.)(driver.guard, pose, .7)
    assert ep.own.guard.door_relax_sigma_scope == 'loaded_base_motion'
    assert ep.own.guard.margin(pose, .7) == .02 + .015 + 2. * .04 + 2. * .03 * .7
    # Exercise the driver's actual arm/backoff checks, not just its field.
    servo = ep.own.servo
    def evaluate(g):
        return (g.plan(servo, servo, [servo[6]], pose, loaded=False, allow_backoff=True),
                g.translation_clear(servo, pose, .01, 0., loaded=False))
    actual = evaluate(driver.guard)
    with monkeypatch.context() as patch:
        patch.setattr(guards.SweepGuard, 'margin', relaxed_margin(1., 1.))
        assert actual == evaluate(ep.own.guard)


def test_recorded_s03_pregrasp_view_filter_recovers_probe_candidates(monkeypatch):
    from tests.test_zone_pair_executor import active, MAP
    from harness.zone_pair_align import ranked_look_pans
    from harness.zone_pair_door_relax import relaxed_margin
    saved = json.loads((ROOT/'tests/fixtures/zone_pair_v6h/pregrasp_s03.json').read_text())
    assert hashlib.sha256((ROOT/saved['map']['path']).read_bytes()).hexdigest() == saved['map']['sha256']
    r = saved['report']
    report = SimpleNamespace(initialized=True, x_m=r['xyyaw'][0], y_m=r['xyyaw'][1], yaw_rad=r['xyyaw'][2],
                             std_xy_m=r['std_xy_m'], std_yaw_rad=r['std_yaw_rad'])
    servo = {int(k): v for k, v in saved['commanded_servo'].items()}
    # Isolate collision filtering; no image, localization or physics is run.
    provider = SimpleNamespace(expected_observability=lambda *args: 1.)
    h = pair_policy('b-v6h1')
    ep = active(_team(monkeypatch, 's03-sigma', {k: v for k, v in vars(h).items() if k != 'name'}))['r2']
    ep.plan['beam_geometry'] = saved['beam_geometry']
    def candidates(g):
        return ranked_look_pans(MAP, report, servo, g, provider, recovery_v6=True)
    old = PairSweepGuard(ep.own.guard, saved['beam_geometry'], ep.arguments['role'])
    assert candidates(old) == []  # 2/2 reproduces PREGRASP_NO_SAFE_VIEW
    actual = candidates(ep.command_guard.sweep_guard())
    assert [r['pan'] for r in actual] == [1500, 1230, 1770, 970, 2030, 700, 2300]
    with monkeypatch.context() as patch:
        patch.setattr(guards.SweepGuard, 'margin', relaxed_margin(1., 1.))
        assert actual == candidates(old)  # exact scores as well as candidate set


def test_preclose_uses_the_policy_scope_and_keeps_beam_fit_2sigma(beam_fit, monkeypatch):
    from tests.test_zone_pair_executor import active
    from tests.test_zone_pair_grasp import ready_to_close
    from harness.zone_pair_door_relax import relaxed_margin
    h = pair_policy('b-v6h1')
    ep = active(_team(monkeypatch, 'preclose-sigma', {k: v for k, v in vars(h).items() if k != 'name'}))['r1']
    ready_to_close(ep, 1.)
    seen = []
    original = PairSweepGuard.stationary_beam_clearance
    def capture(g, beam, pose):
        assert g.door_relax_sigma_scope == 'probe_all_sweeps'
        assert g.margin(pose, .7) == relaxed_margin(1., 1.)(g, pose, .7)
        actual = original(g, beam, pose)
        with monkeypatch.context() as patch:
            patch.setattr(guards.SweepGuard, 'margin', relaxed_margin(1., 1.))
            probe = PairSweepGuard(ep.own.guard, ep.plan['beam_geometry'], ep.arguments['role'])
            assert actual == original(probe, beam, pose)  # extra beam-fit term stays 2
        seen.append(actual)
        return actual
    monkeypatch.setattr(PairSweepGuard, 'stationary_beam_clearance', capture)
    ep.command_guard.preclose_check(1., ep.own.last_obs)
    assert seen


def test_loaded_gate_5_4_is_scoped_and_preserves_unloaded_and_xy():
    old, new = guards.GATE_LOADED, guards.loaded_gate_profile((5., 4.))
    assert (new.high_yaw_rad, new.low_yaw_rad) == pytest.approx((math.radians(5.), math.radians(4.)), abs=1e-9)
    assert replace(new, high_yaw_rad=old.high_yaw_rad, low_yaw_rad=old.low_yaw_rad) == old
    assert guards.loaded_gate_profile() is old and guards.GATE_UNLOADED.high_yaw_rad != new.high_yaw_rad


@pytest.mark.parametrize('fix', [None, float('nan'), float('inf'), -float('inf'), True, '2', 0.9, 1.0])
def test_p2f_cannot_arm_without_a_finite_strictly_moved_fix(fix):
    report = SimpleNamespace(last_fix_t=fix); m = MovedFixMonitor(lambda: report)
    m.trusted((0., 0.), 1.); assert m.baseline is None
    m.note_command({'t': 1., 'kind': 'mecanum', 'forward': .05, 'duration_s': .1})
    m.drove(1.); m.trusted((0., 0.), 1.)
    assert m.baseline is None and not m.needs_check() and not m.stalled() and m.armed_count == 0


def test_p2f_arms_resets_and_then_uses_the_registered_stall_rule():
    r = SimpleNamespace(last_fix_t=1.1); m = MovedFixMonitor(lambda: r)
    m.note_command({'t': 0., 'kind': 'hold'}); assert m.move_t0 is None
    m.note_command({'t': 1., 'kind': 'mecanum', 'forward': .05, 'duration_s': .1})
    m.trusted((0., 0.), 1.); assert m.armed_count == 1
    m.drove(.41); assert m.needs_check() and not m.stalled()
    m.trusted((0., 0.), 1.); assert m.stalled()
    m.reset(); assert m.move_t0 is None and m.baseline is None
    m.trusted((0., 0.), 1.); assert m.baseline is None


def test_pair_guard_and_sweep_receive_flags_but_unloaded_driver_monitor_does_not(monkeypatch):
    from tests.test_zone_pair_executor import active
    h = pair_policy('b-v6h1'); flags = {k: v for k, v in vars(h).items() if k != 'name'}
    host = _team(monkeypatch, 'v6h-fixture', flags)
    for ep in active(host).values():
        g = ep.command_guard
        assert isinstance(g.monitor, MovedFixMonitor)
        assert type(ep.controller.driver.monitor) is guards.ProgressMonitor
        assert g.loaded_profile.high_yaw_rad == pytest.approx(math.radians(5.))
        assert g.recheck.loaded_profile is g.loaded_profile
        assert ep.controller.driver.loaded_profile == g.loaded_profile
        assert g.sweep_guard().loaded_k_xy == g.sweep_guard().loaded_k_yaw == 1.


def test_axial_lag_uses_corrected_plant_but_lateral_and_input_stay_identical(monkeypatch):
    h = pair_policy('b-v6h1'); flags = {k: v for k, v in vars(h).items() if k not in ('name', 'carry_axial_lag')}
    off = _team(monkeypatch, 'h-axial-off', flags)
    on = _team(monkeypatch, 'h-axial-on', {**flags, 'carry_axial_lag': True})
    for rid in ('r1', 'r2'):
        a, b = _axial_schedule(off, rid), _axial_schedule(on, rid)
        assert a[0] == b[0] and a[2] == b[2] and a[1] != b[1]
        assert _lateral_schedule(off, rid) == _lateral_schedule(on, rid)
    params = copy.deepcopy(V6['params']); saved = copy.deepcopy(params)
    assert carry.timing_calibration(params, 'lateral', carry.FWD_GAIN) is params
    scaled = carry.timing_calibration(params, 'axial', carry.FWD_GAIN)
    assert scaled['motion_loaded']['gain'][0][0] == pytest.approx(params['motion_loaded']['gain'][0][0]*carry.FWD_GAIN)
    assert params == saved
    duration = carry.leg_duration(.85, 'axial', [.06/1.4, 0., 0.], scaled)
    mp = scaled['motion_loaded']
    assert carry.lag_travel(duration, abs(carry.steady_speed(scaled, 'axial', [.06/1.4, 0., 0.])),
                            mp['tau_s'], mp['tau_stop_s']) == pytest.approx(.85, abs=1e-9)


def test_axial_lag_requires_forward_correction_and_gain_requires_dr(monkeypatch):
    from harness.zone_pair_executor import PairTeam
    for name, flags, error in [('axial-only', {'carry_axial_lag': True}, 'requires carry_fwd_gain'),
                               ('gain-only', {'carry_fwd_gain': carry.FWD_GAIN}, 'requires carry_dr_model')]:
        monkeypatch.setitem(POLICIES, name, PairPolicy(name, **flags))
        with pytest.raises(ValueError, match=error):
            PairTeam({}, {}, V6['params'], cancel_scheduled=lambda *a: None, contact_profile='cargo_noslip_v1', policy=name)


def test_candidate_policy_bundle_workflow_and_ci_list_match_analysis_seal():
    from harness.zone_pair_v6_policy import EXECUTION_BUNDLE_ID
    from harness import pair_stage_probe as sp, zone_study_integration as zi
    from scripts.zone_pair_v6_contract import CURRENT_REVISION, PENDING_REVISION, PREREG_V6H, candidate_contract, contract
    from scripts.run_ci_tests import collect_test_files, TEST_PATTERNS
    catalog = json.loads((ROOT/'configs/simulation_workflows.json').read_text())
    workflow = next(w for w in catalog['workflows'] if w['id'] == 'zone-study-integration-run')
    assert workflow['version'] == BUILDER.RESERVED['workflow'] == '2.16.0'
    assert EXECUTION_BUNDLE_ID == zi.EXECUTION_BUNDLE_ID == BUILDER.RESERVED['bundle']
    assert 'zone-pair-v81-carry-dr-general' in zi.RETIRED_BUNDLE_IDS
    assert 'b-v6h1' in sp.POLICIES and 'b-v6h1' not in sp.PROBE_ONLY_POLICIES
    assert 'tests/test_zone_pair_v6h.py' in collect_test_files(ROOT, TEST_PATTERNS)
    assert CURRENT_REVISION == 'v6h' and PENDING_REVISION is None and PREREG_V6H.exists()
    assert json.loads(PREREG_V6H.read_text())['state'] == 'sealed'
    flags = candidate_contract()['policy_flags']['b-v6h1']
    assert flags == json.loads(json.dumps(vars(pair_policy('b-v6h1'))))


def test_stage_probe_parser_builds_registered_chain_with_no_probe_patch(tmp_path):
    from scripts.run_pair_stage_probes import parser, build_cases
    args = parser().parse_args(['--stage', 'chain', '--policies', 'b-v6h1', '--sources', 'teacher',
                                '--cells', 'nominal', '--seeds', '941', '--nominal-seeds', '941'])
    args.unavailable = []
    cases = build_cases(args)
    assert len(cases) == 1 and cases[0]['pair_policy'] == 'b-v6h1' and cases[0]['stage'] == 'chain'
    assert cases[0]['teacher_held'] and cases[0]['source'] == 'teacher_grid'
    assert not any(k in cases[0] for k in ('door_relax', 'progress_relax', 'carry_gain_fix', 'carry_axial_lag'))
    args.env_placements = ROOT/'experiments/2026-09-30-pair-v6h-carry/placements_confirmatory_DRAFT.json'
    assert len(build_cases(args)) == 60


def test_builder_dry_run_verify_and_tamper_rejection_without_final_seal(capsys):
    from scripts.zone_pair_v6_contract import PREREG_V6H
    p = BUILDER.build(); assert BUILDER.verify(p)['status'] == 'verified_unsealed'
    assert len(p['runs']) == 72 and sum(r['primary'] for r in p['runs']) == 60
    assert p['confirmatory_plan']['default_A']['pass_at_least'] == 48
    assert p['confirmatory_plan']['default_C'] == 'report-only, not an adoption gate'
    operation = p['confirmatory_plan']['operation']
    assert p['confirmatory_plan']['coordinator_decisions']['sigma_scope'] == 'probe_all_sweeps'
    assert operation['chain_stop_leg'] == 1 and operation['policy'] == 'b-v6h1'
    assert operation['contact_track'] and operation['pf_track'] and not operation['weld']
    assert p['confirmatory_plan']['text_verbatim'] == (BUILDER.HERE/'PREREG_DRAFT.md').read_text()
    assert BUILDER.main(['--dry-run']) == BUILDER.main(['--verify']) == 0
    assert json.loads(PREREG_V6H.read_text())['state'] == 'sealed'
    capsys.readouterr(); p['runs'][0]['seed'] = 911
    with pytest.raises(ValueError, match='differs'):
        BUILDER.verify(p)


# Fixed numbers independently calculated by the reviewer's probe+fake-team replay.
# Extended with a 50-digit Decimal solution of d = v*(T-(.8-.05)*(1-exp(-T/.8))).
# v = 1.4004 * .9483378899463337 * (.06/(2.2/1.4)); kappa exactly once.
# Keep these literals: using leg_duration/timing_calibration here would hide M3.
@pytest.mark.parametrize('seg,length,end,stop', [
    (0, .25, 22.179622442616015, 22.2),
    (0, .55, 28.09653105964494, 28.1),
    (1, .85, 34.01282131543404, 34.1),
])
def test_real_two_robot_schedule_and_carry_stop_ticks(monkeypatch, seg, length, end, stop):
    from tests.test_zone_pair_executor import active
    h = pair_policy('b-v6h1')
    host = _team(monkeypatch, 'fixed-timing', {k: v for k, v in vars(h).items() if k != 'name'})
    endpoints = active(host)
    # The route is static task input. Different PF x must not change its timing.
    for rid, x in (('r1', -100.), ('r2', 100.)):
        from harness.zone_pair_executor import m2_controller
        from tests.test_zone_pair_executor import CALIB
        ep = endpoints[rid]
        ep.plan['route'][seg + 1] = [ep.plan['route'][seg][0] + length, ep.plan['route'][seg][1]]
        ctl = m2_controller(ep, copy.deepcopy(ep.plan), copy.deepcopy(CALIB['params']))
        ctl.seg = seg
        ctl.grasp_estimate = [x, .05, 0. if rid == 'r1' else math.pi]
        ctl.schedule = ctl.door_schedule(10.)
        assert len(ctl.schedule) == 2
        assert ctl.schedule[0] == (10., 16., {'forward': 0., 'left': 0., 'turn': 0.})
        assert ctl.door_schedule(10.) == ctl.schedule  # repeat does not apply kappa twice
        start, actual_end, command = ctl.schedule[-1]
        assert start == 16.5
        assert actual_end == pytest.approx(end, abs=1e-9, rel=0)
        assert command == {'forward': (1 if rid == 'r1' else -1)*.06/(2.2/1.4), 'left': 0., 'turn': 0.}
        emitted = []
        ctl.port = SimpleNamespace(apply=lambda c, t: emitted.append((t, c)),
                                   hold=lambda t: emitted.append((t, {'kind': 'hold'})))
        ctl.state = 'carry'; ctl.next_look = math.inf  # timing-only fake; no image/physics
        for tick in range(100, int(round(stop * 10)) + 1):
            ctl._carry(tick / 10., True)
        assert ctl.state == 'wait_lower'
        assert ctl.claims['route_done']['sim_time'] == stop
        assert emitted[-1] == (stop, {'kind': 'hold'})
        assert emitted[-2] == (pytest.approx(stop - .1), {'kind': 'mecanum', **command, 'duration_s': .15})


def _sealed_v6h(tmp_path, monkeypatch):
    """Synthetic promotion in pytest's scratch only; never create repository prereg_v6h.json."""
    from scripts import zone_pair_v6_contract as c
    from scripts.zone_pair_authorization import digest, registration_payload
    p = BUILDER.build()
    p['sealed'] = True
    p['registration_sha256'] = digest(registration_payload(p))
    path = tmp_path/'sealed-fixture.json'; path.write_text(json.dumps(p))
    monkeypatch.setattr(c, 'CURRENT_REVISION', 'v6h')
    return path, p


def _confirmatory_args(path, output):
    from scripts.run_pair_stage_probes import parser
    return parser().parse_args([
        '--prereg', str(path), '--output', str(output), '--stage', 'chain',
        '--policies', 'b-v6h1', '--sources', 'teacher', '--seeds', '941', '--nominal-seeds', '941',
        '--env-placements', str(BUILDER.HERE/'placements_confirmatory_DRAFT.json'),
        '--render-profile', 'floor_light_v1', '--chain-stop-leg', '1', '--pf-track', '--contact-track',
        '--omp-threads', '1'])


def test_real_builder_72_case_admission_and_stage_probe_prepare(tmp_path, monkeypatch, capsys):
    from scripts import zone_pair_v6_contract as c, run_pair_stage_probes as runner
    path, p = _sealed_v6h(tmp_path, monkeypatch)
    args = _confirmatory_args(path, tmp_path/'never-created')
    accepted, case = c.load_config(SimpleNamespace(**{**vars(args), 'run_id': p['runs'][0]['id']}))
    assert accepted == p and case == p['cases'][0]
    accepted, cases = runner.prepare_cases(args)
    assert accepted == p and len(cases) == 72
    assert [r['seed'] for r in cases] == [941]*60 + [943]*12
    for actual, frozen in zip(cases, p['cases']):
        assert actual == frozen
        assert actual['render_profile'] == 'floor_light_v1'
        assert actual['chain_stop_leg'] == 1 and actual['pf_track'] and actual['contact_track']
    assert not args.output.exists()
    # Exercise the public CLI through the same admission, still prepare-only.
    argv = ['--prereg', str(path), '--output', str(args.output), '--stage', 'chain',
            '--policies', 'b-v6h1', '--sources', 'teacher', '--seeds', '941', '--nominal-seeds', '941',
            '--env-placements', str(args.env_placements), '--render-profile', 'floor_light_v1',
            '--chain-stop-leg', '1', '--pf-track', '--contact-track', '--omp-threads', '1']
    assert runner.main(argv) == 0
    assert json.loads(capsys.readouterr().out)['cases'] == 72
    assert not args.output.exists()
    args.execute = True
    with pytest.raises(ValueError, match='prepare-only'):
        runner.prepare_cases(args)
    assert not args.output.exists()


@pytest.mark.parametrize('key,value', [
    ('render_profile', None), ('chain_stop_leg', 0), ('pf_track', False), ('contact_track', False),
    ('policies', ['b-v6g']), ('seeds', [911]), ('sources', ['e2e']), ('limit', 1),
    ('workers', 2), ('omp_threads', 2), ('stage', ['carry']), ('diag_patch', 'image_valid_off'),
    ('env_bias_y_m', [.01]), ('setup_variant', 'hR2'), ('prior_std', 'e2e'),
])
def test_confirmatory_stage_options_cannot_override_seal(tmp_path, monkeypatch, key, value):
    from scripts.run_pair_stage_probes import prepare_cases
    path, _ = _sealed_v6h(tmp_path, monkeypatch)
    args = _confirmatory_args(path, tmp_path/'never')
    setattr(args, key, value)
    with pytest.raises(ValueError, match='sealed.*option'):
        prepare_cases(args)
    assert not args.output.exists()


@pytest.mark.parametrize('target', ['run_count', 'seed', 'placement', 'prior', 'case', 'render', 'trace', 'termination', 'source'])
def test_confirmatory_plan_tamper_rejected_even_with_recomputed_digest(tmp_path, monkeypatch, target):
    from scripts import zone_pair_v6_contract as c
    from scripts.zone_pair_authorization import digest, registration_payload
    path, p = _sealed_v6h(tmp_path, monkeypatch)
    if target == 'run_count': p['runs'].pop()
    elif target == 'seed': p['runs'][-1]['seed'] = 945
    elif target == 'placement': p['runs'][0]['placement']['x'] += .01
    elif target == 'prior': p['runs'][0]['placement']['prior'] = 'hR2_02'
    elif target == 'case': p['cases'][0]['beam_xyyaw'][0] += .01
    elif target == 'render': p['confirmatory_plan']['operation']['render_profile'] = 'baseline'
    elif target == 'trace': p['confirmatory_plan']['operation']['contact_track'] = False
    elif target == 'termination': p['confirmatory_plan']['operation']['chain_stop_leg'] = 0
    else: p['v6_contract']['source_sha256']['scripts/zone_teacher.py'] = '0'*64
    p['registration_sha256'] = digest(registration_payload(p)); path.write_text(json.dumps(p))
    args = SimpleNamespace(prereg=path, execute=False, output=tmp_path/'never', run_id=None, pair_policy=None)
    with pytest.raises(ValueError, match='sealed.*(plan|source)'):
        c.load_config(args)
    assert not args.output.exists()


@pytest.mark.parametrize('source', ['scripts/zone_teacher.py', 'harness/owncam_pair_hold_v3.py',
                                    'harness/static_keepouts.py', 'harness/zone_event_scheduler.py'])
def test_real_chain_source_tamper_rejected(tmp_path, monkeypatch, source):
    from scripts import zone_pair_v6_contract as c
    path, p = _sealed_v6h(tmp_path, monkeypatch)
    original = Path.read_bytes
    assert source in p['v6_contract']['source_sha256']
    def changed(file):
        raw = original(file)
        if file == ROOT/source:
            if source == 'scripts/zone_teacher.py':
                assert b'CONTROL_S = .1' in raw
                return raw.replace(b'CONTROL_S = .1', b'CONTROL_S = .2')
            return raw + b'\n# synthetic source tamper\n'
        return raw
    monkeypatch.setattr(Path, 'read_bytes', changed)
    with pytest.raises(ValueError, match='sealed.*source'):
        c.load_config(SimpleNamespace(prereg=path, execute=False, output=tmp_path/'never', run_id=None))


def test_seal_hash_promotion_and_legacy_runtime_cannot_be_bypassed(tmp_path, monkeypatch):
    from scripts import zone_pair_v6_contract as c, run_zone_pair_dev as dev
    path, p = _sealed_v6h(tmp_path, monkeypatch)
    args = SimpleNamespace(prereg=path, execute=False, output=tmp_path/'never', run_id=None)
    monkeypatch.setattr(c, 'CURRENT_REVISION', 'v6e')
    with pytest.raises(ValueError, match='pending seal'): c.load_config(args)
    monkeypatch.setattr(c, 'CURRENT_REVISION', 'v6h')
    p['registration_sha256'] = '0'*64; path.write_text(json.dumps(p))
    with pytest.raises(ValueError, match='registration hash'): c.load_config(args)
    # A six-case payload cannot be promoted as v6h anymore.
    p = json.loads(c.PREREG_V6E.read_text()); p['registration_revision'] = 'v6h'
    path.write_text(json.dumps(p))
    with pytest.raises(ValueError, match='sealed confirmatory plan'): c.load_config(args)
    with pytest.raises(ValueError, match='run_pair_stage_probes'): dev.load_config(args)


@pytest.mark.parametrize('field,value', [('render_profile', 'noshadow_v1'), ('chain_stop_leg', 0),
                                        ('pf_track', False), ('contact_track', False), ('prior', {})])
def test_worker_case_tamper_stops_before_physics(tmp_path, monkeypatch, field, value):
    from scripts import run_pair_stage_probes as runner
    from scripts import zone_pair_v6h_admission as admission
    path, p = _sealed_v6h(tmp_path, monkeypatch)
    case = copy.deepcopy(p['cases'][0]); case[field] = value
    case['registration'] = {'prereg': str(path), 'registration_sha256': p['registration_sha256'],
                            'run_id': p['runs'][0]['id'], 'expected_source_sha': 'a'*40, 'lock_owner': 'codex'}
    monkeypatch.setattr(admission, 'authorize_execution', lambda *a: pytest.fail('must reject before authorization'))
    with pytest.raises(ValueError, match='worker case differs'):
        runner.run_case(case, tmp_path/'never')
    assert not (tmp_path/'never').exists()
    del case['registration']
    with pytest.raises(ValueError, match='requires its registration receipt'):
        runner.run_case(case, tmp_path/'never')


def test_registered_execution_requires_source_and_one_bound_run(tmp_path, monkeypatch):
    from scripts import zone_pair_v6_contract as c
    from scripts.zone_pair_authorization import digest, registration_payload
    path, p = _sealed_v6h(tmp_path, monkeypatch)
    p.update(status='REGISTERED', runnable=True)
    p['registration_sha256'] = digest(registration_payload(p))
    args = _confirmatory_args(path, tmp_path/'never')
    args.execute = True; args.run_id = p['runs'][0]['id']; args.expected_source_sha = 'a'*40
    path.write_text(json.dumps(p))
    with pytest.raises(ValueError, match='execution_authorization'): c.load_config(args)
    auth = {'by': 'coordinator', 'source_sha': 'a'*40, 'registration_sha256': p['registration_sha256'],
            'run_id': args.run_id, 'ref': 'https://github.com/kcm0127-dotcom/ugrp/issues/216#issuecomment-123'}
    auth['sha256'] = digest(auth); p['execution_authorization'] = auth; path.write_text(json.dumps(p))
    _, case = c.load_config(args)
    assert case == p['cases'][0]
    args.expected_source_sha = 'b'*40
    with pytest.raises(ValueError, match='source_sha differs'): c.load_config(args)
    args.expected_source_sha = 'a'*40; args.run_id = p['runs'][1]['id']
    with pytest.raises(ValueError, match='run_id differs'): c.load_config(args)
    args.run_id = None
    with pytest.raises(ValueError, match='one authorized'): c.load_config(args)


def test_scope_wording_matches_not_approach_gate_and_progress(monkeypatch):
    from tests.test_zone_pair_executor import active
    h = pair_policy('b-v6h1')
    host = _team(monkeypatch, 'scope', {k: v for k, v in vars(h).items() if k != 'name'})
    ep = active(host)['r1']; guard = ep.command_guard
    for phase in ('align', 'grasp', 'carry', 'lower', 'cp_open'):
        ep.controller.state = phase
        assert not getattr(ep.controller, 'beam_grasp_receipt', None)
        guard.check(0., [{'kind': 'hold'}])
        assert not guard.approach
        assert ep.own.gate.profile.high_yaw_rad == pytest.approx(math.radians(5.))
        guard.monitor.reset()
        guard.on_command({'t': 0., 'kind': 'mecanum', 'forward': .01, 'duration_s': .1})
        assert guard.monitor.move_t0 == 0.
    ep.controller.state = 'approach'; guard.monitor.reset()
    guard.check(0., [{'kind': 'hold'}])
    guard.on_command({'t': 0., 'kind': 'mecanum', 'forward': .01, 'duration_s': .1})
    assert ep.own.gate.profile is guards.GATE_UNLOADED and guard.monitor.move_t0 is None
    # Guard-scope documentation is part of the registration, not a grasp-only promise.
    for name in ('REGISTRATION_PLAN.md', 'README.md'):
        text = (BUILDER.HERE/name).read_text()
        assert 'not approach' in text and 'probe_all_sweeps' in text
        assert '접근·팔 스윕 여유의 완화는 한 번도 시험되지 않았다' not in text


def test_valid_registered_worker_rechecks_source_and_live_authorization(tmp_path, monkeypatch):
    from scripts import zone_pair_v6h_admission as admission, zone_pair_authorization as auth
    from scripts import run_pair_stage_probes as runner, agent_lock
    path, p = _sealed_v6h(tmp_path, monkeypatch)
    p.update(status='REGISTERED', runnable=True)
    p['registration_sha256'] = auth.digest(auth.registration_payload(p))
    envelope = {'by': 'coordinator', 'source_sha': 'a'*40, 'registration_sha256': p['registration_sha256'],
                'run_id': p['runs'][0]['id'],
                'ref': 'https://github.com/kcm0127-dotcom/ugrp/issues/216#issuecomment-123'}
    envelope['sha256'] = auth.digest(envelope); p['execution_authorization'] = envelope
    path.write_text(json.dumps(p))
    case = copy.deepcopy(p['cases'][0])
    case['registration'] = {'prereg': str(path), 'registration_sha256': p['registration_sha256'],
                            'run_id': p['runs'][0]['id'], 'expected_source_sha': 'a'*40, 'lock_owner': 'codex'}
    seen = []
    def source(root, prereg_path, plan, sha):
        assert root == ROOT and prereg_path == path and sha == 'a'*40
        auth.validate_authorization(plan, execute=True, expected_source_sha=sha, run_id=case['registration_run_id'])
        seen.append('source')
    def github(plan, sha, run_id):
        auth.validate_authorization(plan, execute=True, expected_source_sha=sha, run_id=run_id)
        seen.append('live-approval'); return {'test_only': True}
    monkeypatch.setattr(auth, 'verify_source', source)
    monkeypatch.setattr(auth, 'verify_github_authorization', github)
    monkeypatch.setattr(runner, 'primary_root', lambda: tmp_path)
    monkeypatch.setattr(runner, 'git', lambda *a: 'codex/pair-v6h-register')
    monkeypatch.setattr(agent_lock, 'status', lambda *a: {
        'pid_alive': True, 'owner': 'codex', 'branch': 'codex/pair-v6h-register'})
    # Call just the pre-physics worker guard. No worker/simulator starts.
    admission.validate_worker_case(case, tmp_path/'outputs/case')
    assert seen == ['source', 'live-approval', 'source']
    assert not (tmp_path/'outputs').exists()
