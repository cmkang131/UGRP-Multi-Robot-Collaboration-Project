"""b-v6h gain-fix cohort tooling (stage-probe opt-in; no physics): PF forward-gain multiplier, corrected progress-monitor timing rule
``p2f``, identity door-relax variant ``k2`` and the explicit placement list. The registered sources must stay byte-identical."""
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import harness.zone_own_driver as own_driver
import harness.zone_own_guards as guards
import harness.zone_pair_carry_axial_lag as axial_lag
import harness.zone_pair_carry_gain_fix as gain_fix
import harness.zone_pair_door_relax as relax
import harness.zone_pair_guards as pair_guards
import harness.zone_pair_progress_relax as pr
from harness import owncam_carry_v6e as v6e
from harness.owncam_pose_source import OwnCamPoseSource
from scripts import run_pair_stage_probes as runner
from tests.test_zone_pair_v6e import LEFT_CMD, V6, cloud  # noqa: F401  (fixtures: V6 map/params)

ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / 'experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json'
PLACEMENTS = ROOT / 'experiments/2026-09-30-b-v6h-gain/placements/held_out_12.json'


@pytest.fixture
def restore(monkeypatch):
    """Undo every process-local patch a test installs."""
    monkeypatch.setattr(v6e, 'enable_provider', v6e.enable_provider)
    monkeypatch.setattr(v6e, 'leg_duration', v6e.leg_duration)
    monkeypatch.setattr(v6e, 'LAG_AXES', v6e.LAG_AXES)
    axial_lag.LOGGED.clear()
    for name in ('__init__', 'on_command'):
        monkeypatch.setattr(pair_guards.PairCommandGuard, name, getattr(pair_guards.PairCommandGuard, name))
    monkeypatch.setattr(pair_guards.PairCommandGuard, '_p2f', False, raising=False)
    gain_fix.APPLIED.clear()
    pr.IGNORED.clear()
    pr.ARMED.clear()


# ------------------------------------------------------------------ registered sources
def test_registered_sources_are_untouched_and_the_new_modules_are_outside_the_seal():
    prereg = json.loads((ROOT / 'experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json').read_text())
    sealed = prereg['v6_contract']['source_sha256']
    for path, expected in sealed.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    for path in ('harness/zone_pair_carry_axial_lag.py', 'harness/zone_pair_carry_gain_fix.py', 'harness/zone_pair_progress_relax.py', 'harness/zone_pair_door_relax.py',
                 'scripts/run_pair_stage_probes.py'):
        assert path not in sealed


# ------------------------------------------------------------------ forward gain multiplier
def test_the_multiplier_is_the_pr284_fit_and_matches_the_registered_calibration():
    cal = json.loads(CAL.read_text())
    assert cal['params']['motion_loaded']['gain'][0][0] == pytest.approx(gain_fix.REGISTERED_FORWARD_GAIN)
    assert gain_fix.KAPPA * gain_fix.REGISTERED_FORWARD_GAIN == pytest.approx(gain_fix.SOURCE['forward_gain_M1'])
    assert 0.94 < gain_fix.KAPPA < 0.96


def test_scaled_gain_touches_only_the_forward_entry_and_does_not_mutate():
    gain = [[1.4004, 0.1, 0.0], [0.0, 1.0159, 0.0], [0.0, 0.0, 2.0]]
    out = gain_fix.scaled_gain(gain)
    assert out[0][0] == pytest.approx(1.4004 * gain_fix.KAPPA)
    assert [row[:] for i, row in enumerate(out) if i] == gain[1:] and out[0][1:] == gain[0][1:]
    assert gain[0][0] == 1.4004


def test_install_rescales_each_pf_once_and_leaves_other_providers_alone(restore):
    other = OwnCamPoseSource(V6['map'], V6['params'], seed=1)
    p = OwnCamPoseSource(V6['map'], V6['params'], seed=628)
    gain0 = [list(r) for r in p.loc.params['motion_loaded']['gain']]
    assert gain_fix.install(None) is None
    info = gain_fix.install('pf')
    assert info['kappa'] == gain_fix.KAPPA and info['mode'] == 'pf'
    rec = v6e.enable_provider(p)
    fixed = p.loc.params['motion_loaded']['gain']
    assert fixed[0][0] == pytest.approx(gain0[0][0] * gain_fix.KAPPA)
    assert [list(r) for r in fixed][1:] == gain0[1:] and list(fixed[0][1:]) == gain0[0][1:]
    assert other.loc.params['motion_loaded']['gain'] == gain0 or np.array_equal(other.loc.params['motion_loaded']['gain'], gain0)
    assert rec['gain_fix']['kappa'] == gain_fix.KAPPA and len(gain_fix.APPLIED) == 1
    v6e.enable_provider(p)                                               # idempotent: never scaled twice
    assert p.loc.params['motion_loaded']['gain'][0][0] == pytest.approx(gain0[0][0] * gain_fix.KAPPA)
    assert len(gain_fix.APPLIED) == 1
    with pytest.raises(RuntimeError, match='already installed'):
        gain_fix.install('pf')
    with pytest.raises(ValueError, match='unknown carry-gain-fix'):
        gain_fix.mode('pf+plan')


def test_the_corrected_pf_travels_kappa_times_the_registered_pf_on_a_forward_leg(restore):
    def travel(p):
        loc = p.loc
        loc.init_at = None
        loc.px = np.zeros((loc.n, 3))
        loc.scale = np.ones((loc.n, 3))
        loc.logw = np.zeros(loc.n)
        loc.initialized = True
        loc.load.loaded = True
        loc._draw_plant_state(True)
        loc.px[:] = 0.
        loc.command({'t': 0., 'kind': 'mecanum', 'forward': .05, 'left': 0., 'turn': 0., 'duration_s': 10.})
        loc.predict_to(16.)
        return float(np.mean(loc.px[:, 0]))
    a = OwnCamPoseSource(V6['map'], V6['params'], seed=628)
    v6e.enable_provider(a)
    reference = travel(a)
    gain_fix.install('pf')
    b = OwnCamPoseSource(V6['map'], V6['params'], seed=628)
    v6e.enable_provider(b)
    assert travel(b) / reference == pytest.approx(gain_fix.KAPPA, rel=0.02)


# ------------------------------------------------------------------ door-relax identity variant
def test_k2_is_the_registered_margin(restore, monkeypatch):
    monkeypatch.setattr(guards.SweepGuard, 'margin', guards.SweepGuard.margin)
    v = relax.variant('k2')
    assert (v['k_xy'], v['k_yaw'], v['gate_yaw_deg'], v['advisory_s']) == (relax.REGISTERED['k_xy'], relax.REGISTERED['k_yaw'],
                                                                             None, 0.)
    pose = guards.OwnPose(2., .05, 0., .043, .038)
    guard = SimpleNamespace(residual=.015)
    registered = guards.SweepGuard.margin(guard, pose, .18)
    assert relax.relaxed_margin(v['k_xy'], v['k_yaw'])(guard, pose, .18) == pytest.approx(registered)


# ------------------------------------------------------------------ p2f timing rule
def monitor(fix_t_holder):
    cls = pr.make_moved_fix_monitor(guards.ProgressMonitor)
    m = cls()
    m.report_source = lambda: SimpleNamespace(last_fix_t=fix_t_holder[0])
    return m


def drive_row(t):
    return {'t': t, 'kind': 'mecanum', 'forward': .05, 'left': 0., 'turn': 0., 'duration_s': .15}


def test_p2f_ignores_a_fix_taken_before_the_first_move_even_when_it_is_recent(restore):
    fix = [9.8]
    m = monitor(fix)
    m.trusted((1., 0.), 1.)                    # no move yet: ignored
    assert m.baseline is None and pr.IGNORED
    m.note_command(drive_row(10.0)); m.drove(.0075)
    m.trusted((1., 0.), 1.)                    # fix at 9.8 is younger than 0.3 s at t=10.05 but predates the move: ignored (p2 armed here)
    assert m.baseline is None and len(pr.IGNORED) == 2
    fix[0] = 10.0
    m.trusted((1., 0.), 1.)                    # a fix at the move-start time is not "later": ignored
    assert m.baseline is None
    fix[0] = 10.05
    m.trusted((1.01, 0.), .99)                 # strictly later than the move start: arms
    assert m.baseline is not None and len(pr.ARMED) == 1


def test_p2f_keeps_the_registered_stall_rule_once_armed_and_reset_clears_the_move(restore):
    fix = [10.5]
    m = monitor(fix)
    m.note_command(drive_row(10.0))
    m.trusted((1., 0.), 1.)
    assert m.baseline is not None
    m.drove(.45)
    assert m.needs_check() and not m.stalled()             # 0.40 m of commanded travel with no newer trusted estimate
    fix[0] = 12.
    m.trusted((1., 0.), 1.)                                # a newer trusted estimate that did not move: stalled
    assert m.stalled()
    m.reset()
    assert m.baseline is None and m.move_t0 is None
    fix[0] = 13.
    m.trusted((1., 0.), 1.)                                # after reset the next fix predates the (not yet issued) next move
    assert m.baseline is None


def test_p2f_zero_or_missing_fix_time_never_arms(restore):
    for value in (None, float('nan')):
        fix = [value]
        m = monitor(fix)
        m.note_command(drive_row(1.))
        m.trusted((1., 0.), 1.)
        assert m.baseline is None
    m = pr.make_moved_fix_monitor(guards.ProgressMonitor)()
    m.note_command(drive_row(1.))
    m.trusted((1., 0.), 1.)                                # no report source
    assert m.baseline is None


def test_p2f_patches_only_the_loaded_pair_guard(restore):
    from tests.test_zone_pair_grasp import real_pair
    registered_driver_cls = own_driver.ProgressMonitor
    assert registered_driver_cls is guards.ProgressMonitor
    info = pr.install('p2f')
    assert info['variant'] == 'p2f' and info['registered']['stall_commanded_m'] == 0.40
    assert guards.ProgressMonitor is registered_driver_cls and own_driver.ProgressMonitor is registered_driver_cls
    _, _, eps = real_pair()
    ep = eps['r1']
    assert type(ep.command_guard.monitor).__name__ == 'MovedFixMonitor'
    assert type(ep.controller.driver.monitor) is guards.ProgressMonitor          # the unloaded GuardedDriver is not patched
    ep.controller.state = 'carry'
    assert not ep.command_guard.approach
    ep.command_guard.on_command(drive_row(5.))
    assert ep.command_guard.monitor.move_t0 == 5.
    ep.command_guard.monitor.reset()
    ep.controller.state = 'approach'
    ep.command_guard.on_command(drive_row(6.))                                    # approach commands never start the loaded monitor
    assert ep.command_guard.monitor.move_t0 is None
    with pytest.raises(RuntimeError, match='already installed'):
        pr.install('p2f')


def test_the_old_variants_are_unchanged():
    assert set(pr.VARIANTS) == {'p1', 'p2', 'p2f'}
    assert pr.VARIANTS['p1']['stall_commanded_m'] == 1.2 and pr.VARIANTS['p2']['arm_after_motion']


# ------------------------------------------------------------------ runner
def args_for(*extra):
    return runner.parser().parse_args(['--stage', 'chain', '--sources', 'teacher', '--prior-std', 'e2e', '--output', '/tmp/x', *extra])


def test_the_placement_list_has_the_failing_placement_and_ten_new_ones():
    entries = json.loads(PLACEMENTS.read_text())
    assert len(entries) == 12 and len({e['name'] for e in entries}) == 12
    failing = entries[0]
    assert (failing['x'], failing['y'], failing['yaw_deg']) == pytest.approx((0.9298, -0.0204, -3.901), abs=1e-3)
    used = {(1.0, 0.05, 0.0), (0.93, -0.02, -3.9)}
    assert not any((round(e['x'], 2), round(e['y'], 2), round(e['yaw_deg'], 1)) in used for e in entries[1:])
    assert all(e['prior'].startswith('hR2_') for e in entries)


def test_env_placements_make_one_case_each_with_the_listed_pose(restore):
    a = args_for('--env-placements', str(PLACEMENTS), '--policies', 'b-v6h', '--door-relax', 'k1g', '--chain-stop-leg', '1',
                 '--seeds', '911', '913')
    cases = runner.envelope_cases('chain', a, 'b-v6h', None)
    assert len(cases) == 24 and len({c['case_id'] for c in cases}) == 24
    entries = json.loads(PLACEMENTS.read_text())
    first = [c for c in cases if c['seed'] == 911]
    for e, c in zip(entries, first):
        x, y, yaw = c['beam_xyyaw']
        assert (x, y, math.degrees(yaw)) == pytest.approx((e['x'], e['y'], e['yaw_deg']))
        assert c['cell'] == e['name'] and c['pair_policy'] == 'b-v6g' and c['door_relax'] == 'k1g'
    assert all(abs(c['route'][1][1] - 0.05) < 1e-9 for c in cases)                 # the route stays on the door axis


def test_flags_tag_the_case_ids_and_are_refused_for_other_policies(capsys):
    argv = ['--stage', 'chain', '--sources', 'teacher', '--prior-std', 'e2e', '--policies', 'b-v6h', '--door-relax', 'k1g',
            '--chain-stop-leg', '1', '--setup-variant', 'hR2', '--cells', 'hR2_01', '--seeds', '911',
            '--progress-relax', 'p2f', '--carry-gain-fix', 'pf', '--output', '/tmp/never_written_gain']
    assert runner.main(argv) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned['cases'] == 1 and '.k1g+p2f+gain:' in planned['case_ids'][0]
    with pytest.raises(SystemExit):
        runner.main(['--stage', 'carry', '--sources', 'teacher', '--policies', 'b-v6g', '--carry-gain-fix', 'pf',
                     '--output', '/tmp/never_written_gain'])


SHEET_PLACEMENTS = ROOT / 'experiments/2026-09-30-b-v6h-gain/placements/held_out_sheet_12.json'


def test_sheet_placements_use_the_rounded_order_sheet_so_the_route_moves_with_the_beam(restore):
    from harness.pair_owncam_approach import coarse_order_sheet
    entries = json.loads(SHEET_PLACEMENTS.read_text())
    assert len(entries) == 12 and all(e['sheet'] == 'coarse' for e in entries)
    a = args_for('--env-placements', str(SHEET_PLACEMENTS), '--policies', 'b-v6h', '--door-relax', 'k1g', '--chain-stop-leg', '1', '--seeds', '911')
    cases = runner.envelope_cases('chain', a, 'b-v6h', None)
    assert len(cases) == 12 and all(c['setup_variant'] == 'ENVS' for c in cases)
    for e, c in zip(entries, cases):
        beam = [e['x'], e['y'], math.radians(e['yaw_deg'])]
        assert c['coarse_order_sheet'] == coarse_order_sheet(beam) and c['beam_xyyaw'] == pytest.approx(beam)
    assert len({c['route'][0][0] for c in cases}) > 1                      # the route start follows the rounded sheet x
    assert all(abs(c['route'][1][1] - 0.05) < 1e-9 for c in cases)          # the door axis stays


def test_confirmatory_placement_draft_is_reproducible_fresh_and_in_distribution():
    """DRAFT prereg placements (not run): the committed list is exactly the seeded draw, shares no placement with the exploratory
    cohorts, and lies in the exploratory distribution."""
    import importlib.util
    path = ROOT / 'experiments/2026-09-30-pair-v6h-carry/make_confirmatory_placements.py'
    spec = importlib.util.spec_from_file_location('make_confirmatory_placements', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = mod.draw()
    assert json.loads(mod.OUT.read_text()) == rows and len(rows) == 60
    assert len({r['name'] for r in rows}) == 60 and all(r['sheet'] == 'coarse' for r in rows)
    assert all(mod.X_RANGE[0] <= r['x'] <= mod.X_RANGE[1] and mod.Y_RANGE[0] <= r['y'] <= mod.Y_RANGE[1]
               and mod.YAW_RANGE_DEG[0] <= r['yaw_deg'] <= mod.YAW_RANGE_DEG[1] for r in rows)
    old = mod.used()
    assert not any(math.hypot(r['x'] - a, r['y'] - b) < mod.DISTINCT_XY_M and abs(r['yaw_deg'] - c) < mod.DISTINCT_YAW_DEG
                   for r in rows for a, b, c in old)


# ------------------------------------------------------------------ axial lag-model leg length (PR #286 P1b)
FORWARD_GAIN = 2.2 / 1.4
AXIAL_CMD = [0.06 / FORWARD_GAIN, 0., 0.]


def cal_params():
    return json.loads(CAL.read_text())['params']


def test_axial_lag_refuses_without_the_gain_fix_and_a_second_install(restore):
    assert axial_lag.install(None, None) is None
    with pytest.raises(ValueError, match='gain fix'):
        axial_lag.install('axial', None)
    with pytest.raises(ValueError):
        axial_lag.install('nope', 'pf')
    info = axial_lag.install('axial', 'pf')
    assert info['lag_axes'] == ['lateral', 'axial'] and info['kappa'] == gain_fix.KAPPA
    with pytest.raises(RuntimeError, match='already installed'):
        axial_lag.install('axial', 'pf')


def test_axial_legs_use_the_kappa_gain_lag_plant_and_lateral_legs_stay_registered(restore):
    params = cal_params()
    registered_axial = v6e.leg_duration(0.85, 'axial', AXIAL_CMD, params)
    lateral_cmd = [0., 0.06 / (1.65 / 1.4), 0.]
    registered_lateral = v6e.leg_duration(0.717, 'lateral', lateral_cmd, params)
    assert v6e.LAG_AXES == ('lateral',)
    axial_lag.install('axial', 'pf')
    assert v6e.LAG_AXES == ('lateral', 'axial')
    assert v6e.leg_duration(0.717, 'lateral', lateral_cmd, params) == registered_lateral      # lateral: untouched
    seconds = v6e.leg_duration(0.85, 'axial', AXIAL_CMD, params)
    # the inverse of the plant the corrected PF integrates: forward gain 1.4004 * kappa
    scaled = {**params, 'motion_loaded': {**params['motion_loaded'], 'gain': gain_fix.scaled_gain(params['motion_loaded']['gain'])}}
    assert seconds == pytest.approx(v6e.lag_duration(0.85, abs(scaled['motion_loaded']['gain'][0][0] * AXIAL_CMD[0]),
                                                    params['motion_loaded']['tau_s'], params['motion_loaded']['tau_stop_s']))
    assert seconds > registered_axial                           # a slower assumed plant gives a longer command
    assert 17.2 < seconds < 17.8                                # PR #286: L1 command window ~17.5 s
    # the leg travels the planned distance in the plant it inverts
    v = gain_fix.KAPPA * 1.4004 * AXIAL_CMD[0]
    assert v6e.lag_travel(seconds, v, params['motion_loaded']['tau_s'], params['motion_loaded']['tau_stop_s']) == pytest.approx(0.85, abs=1e-6)
    assert params['motion_loaded']['gain'][0][0] == pytest.approx(1.4004)     # the session params were not mutated
    assert [e['distance_m'] for e in axial_lag.LOGGED] == [0.85]


def test_axial_lag_runs_only_through_the_registered_lag_flag_of_the_policy():
    """door_schedule reads LAG_AXES from the module at call time and only under policy.carry_lateral_lag (true for b-v6g)."""
    from harness.zone_pair_v6_policy import pair_policy
    assert pair_policy('b-v6g').carry_lateral_lag is True
    src = (ROOT / 'harness/zone_pair_executor.py').read_text()
    assert 'axis in v6e_carry.LAG_AXES' in src


def test_axial_lag_flag_tags_the_case_id_and_needs_the_gain_fix():
    a = args_for('--policies', 'b-v6h', '--door-relax', 'k1g', '--progress-relax', 'p2f', '--carry-gain-fix', 'pf', '--carry-axial-lag', 'axial',
                 '--setup-variant', 'hR2', '--chain-stop-leg', '1', '--seeds', '911')
    assert a.carry_axial_lag == 'axial'
    with pytest.raises(SystemExit):
        runner.main(['--stage', 'chain', '--sources', 'teacher', '--policies', 'b-v6h', '--door-relax', 'k1g', '--carry-axial-lag', 'axial',
                     '--setup-variant', 'hR2', '--chain-stop-leg', '1', '--output', '/tmp/never_written_alag'])
    with pytest.raises(SystemExit):
        runner.main(['--stage', 'carry', '--sources', 'teacher', '--policies', 'b-v6g', '--carry-gain-fix', 'pf', '--carry-axial-lag', 'axial',
                     '--output', '/tmp/never_written_alag'])
