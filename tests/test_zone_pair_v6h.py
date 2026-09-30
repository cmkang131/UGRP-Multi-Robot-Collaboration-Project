"""v6h pre-seal registered controller: pure PF/geometry/fake controller, no physics or models."""
import copy
from dataclasses import replace
import hashlib
import importlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness import owncam_carry_v6e as carry
from harness import zone_own_guards as guards
from harness.owncam_pose_source import OwnCamPoseSource
from harness.zone_pair_geometry import PairSweepGuard
from harness.zone_pair_guards import MovedFixMonitor
from harness.zone_pair_v6_policy import POLICIES, REVISION_POLICIES, PairPolicy, pair_policy
from tests.test_zone_pair_v6e import V6, cloud, _team, _axial_schedule, _lateral_schedule

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((ROOT/'tests/fixtures/zone_pair_v6h/off_golden.json').read_text())
FLAGS = ('carry_fwd_gain', 'loaded_k_xy', 'loaded_k_yaw', 'loaded_gate_yaw_deg',
         'progress_arm_on_moved_fix', 'carry_axial_lag')
BUILDER = importlib.import_module('experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h')


@pytest.mark.parametrize('name', GOLDEN['policies'])
def test_all_existing_policy_fields_are_unchanged_and_new_flags_default_off(name):
    p = pair_policy(name)
    assert {k: v for k, v in vars(p).items() if k not in FLAGS} == GOLDEN['policies'][name]['flags']
    assert tuple(getattr(p, k) for k in FLAGS) == (1., 2., 2., None, False, False)


def test_bv6h1_is_bv6g_plus_exactly_the_five_decided_options():
    g, h = pair_policy('b-v6g'), pair_policy('b-v6h1')
    assert replace(h, name=g.name, **{k: getattr(g, k) for k in FLAGS}) == g
    assert tuple(getattr(h, k) for k in FLAGS) == (carry.FWD_GAIN, 1., 1., (5., 4.), True, True)
    assert REVISION_POLICIES['v6h'] == ('v5h', 'b-only', 'b-v6h1')


@pytest.mark.parametrize('name', GOLDEN['policies'])
def test_flags_off_localizer_is_bit_identical_to_main_a8094cc1(name):
    loc = cloud(); p = pair_policy(name); provider = SimpleNamespace(loc=loc)
    info = None
    if p.carry_dr_model:
        info = carry.enable_provider(provider, pair_yaw=p.carry_pair_yaw,
                                     beam_edge=p.carry_beam_edge, general=p.carry_dr_general,
                                     carry_fwd_gain=p.carry_fwd_gain)
    loc.predict_to(2.)
    loc.command({'t': 2., 'kind': 'mecanum', 'forward': .035, 'left': 0., 'turn': 0., 'duration_s': 4.})
    loc.predict_to(7.)
    loc.command({'t': 7., 'kind': 'mecanum', 'forward': 0., 'left': .025, 'turn': .01, 'duration_s': 3.})
    loc.predict_to(11.)
    gold = GOLDEN['policies'][name]
    assert loc.px.mean(0) == pytest.approx(gold['mean'], abs=1e-9, rel=0)
    assert loc.px.std(0) == pytest.approx(gold['std'], abs=1e-9, rel=0)
    assert hashlib.sha256(loc.px.tobytes()).hexdigest() == gold['particle_sha256']
    assert float(loc.rng.random()) == pytest.approx(gold['rng_next'], abs=1e-12, rel=0)
    assert info == gold['info']


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


def test_sigma_relaxation_is_only_loaded_motion_not_approach_or_arm_sweeps(monkeypatch):
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


def test_candidate_policy_bundle_workflow_and_ci_list_are_consistent_without_a_seal():
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
    assert CURRENT_REVISION == 'v6e' and PENDING_REVISION == 'v6h' and not PREREG_V6H.exists()
    with pytest.raises(ValueError, match='pending seal'):
        contract()
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
    assert operation['chain_stop_leg'] == 1 and operation['policy'] == 'b-v6h1'
    assert operation['contact_track'] and operation['pf_track'] and not operation['weld']
    assert p['confirmatory_plan']['text_verbatim'] == (BUILDER.HERE/'PREREG_DRAFT.md').read_text()
    assert BUILDER.main(['--dry-run']) == BUILDER.main(['--verify']) == 0
    assert not PREREG_V6H.exists()
    capsys.readouterr(); p['runs'][0]['seed'] = 911
    with pytest.raises(ValueError, match='differs'):
        BUILDER.verify(p)
