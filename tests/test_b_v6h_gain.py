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
    for path in ('harness/zone_pair_carry_gain_fix.py', 'harness/zone_pair_progress_relax.py', 'harness/zone_pair_door_relax.py',
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
