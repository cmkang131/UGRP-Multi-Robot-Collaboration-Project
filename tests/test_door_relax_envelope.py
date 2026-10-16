"""Opt-in envelope grid and chain early stop of the stage-probe runner (2026-09-30, door-relax envelope)."""
import math

import pytest

from harness import pair_stage_probe as sp
from scripts import run_pair_stage_probes as runner


def args_for(*extra):
    return runner.parser().parse_args(['--stage', 'carry', '--sources', 'teacher', '--prior-std', 'e2e', '--output', '/tmp/x', *extra])


def envelope(*extra, policy='b-v6g', leg=1):
    a = args_for(*extra)
    return runner.envelope_cases('carry', a, policy, leg)


def test_envelope_places_the_true_beam_and_keeps_the_route_on_the_door_axis():
    cases = envelope('--env-y', '-0.06', '0.17', '--env-yaw-deg', '0', '-3.9')
    assert [c['cell'] for c in cases] == ['E_y-0.060_h+0.0', 'E_y-0.060_h-3.9', 'E_y+0.170_h+0.0', 'E_y+0.170_h-3.9']
    assert len({c['case_id'] for c in cases}) == 4
    c = cases[1]
    assert c['setup_variant'] == 'ENV' and c['leg'] == 1
    assert c['coarse_order_sheet'] == sp.BASE_SETUP['coarse_order_sheet']            # fixed sheet: the route does not move
    assert all(cc['route'] == cases[0]['route'] for cc in cases)
    assert abs(c['route'][1][1] - 0.05) < 1e-9                                        # door axis y
    x, y, yaw = c['beam_xyyaw']                                                       # shifted to route point 1 (leg 1)
    assert abs(y - (-0.06)) < 1e-9 and abs(yaw - math.radians(-3.9)) < 1e-9 and abs(x - 1.55) < 1e-9


def test_envelope_prior_is_the_recorded_posterior_plus_the_stated_bias_only():
    (plain,) = envelope('--env-y', '0.05')
    (biased,) = envelope('--env-y', '0.05', '--env-bias-y-m', '0.02', '--env-bias-yaw-deg', '2')
    assert biased['cell'].endswith('_b+0.020_+2.0')
    for rid in ('r1', 'r2'):
        p, b = plain['prior'][rid], biased['prior'][rid]
        d = [bv - pv for pv, bv in zip(p['mean_xyyaw'], b['mean_xyyaw'])]
        assert d == pytest.approx([0, 0.02, math.radians(2)], abs=1e-9)
        assert (p['std_xy_m'], p['std_yaw_rad']) == (b['std_xy_m'], b['std_yaw_rad'])      # the stated spread is not touched


def test_b_v6h_envelope_cases_carry_the_variant_and_the_registered_policy():
    (c,) = runner.envelope_cases('carry', args_for('--env-y', '0.05', '--door-relax', 'k1g'), 'b-v6h', 1)
    assert c['pair_policy'] == 'b-v6g' and c['door_relax'] == 'k1g' and c['contact_track'] is True


def test_chain_stop_leg_only_for_the_chain_stage():
    with pytest.raises(SystemExit):
        runner.main(['--stage', 'carry', '--sources', 'teacher', '--chain-stop-leg', '1', '--output', '/tmp/never_written'])


def test_progress_relax_is_process_local_and_only_for_b_v6h(monkeypatch):
    from harness import zone_own_guards as g
    from harness import zone_pair_progress_relax as pr
    assert pr.install(None) is None
    monkeypatch.setattr(g, 'STALL_COMMANDED_M', g.STALL_COMMANDED_M)      # restored after the test
    reg = g.STALL_COMMANDED_M
    assert reg == pr.REGISTERED['stall_commanded_m']
    info = pr.install('p1')
    assert g.STALL_COMMANDED_M == 1.2 and info['registered']['stall_commanded_m'] == reg
    mon = g.ProgressMonitor()
    mon.trusted((1., 0.), 1.)
    mon.drove(0.9)
    assert not mon.needs_check()                    # 0.9 m commanded: the registered 0.40 m rule would have fired
    with pytest.raises(ValueError):
        pr.install('p9')
    with pytest.raises(SystemExit):
        runner.main(['--stage', 'carry', '--sources', 'teacher', '--policies', 'b-v6g', '--progress-relax', 'p1', '--output', '/tmp/never_written'])


def test_progress_relax_p2_arms_the_monitor_only_after_commanded_motion(monkeypatch):
    from harness import zone_own_guards as g
    from harness import zone_pair_progress_relax as pr
    for name in ('drove', 'reset', 'trusted'):
        monkeypatch.setattr(g.ProgressMonitor, name, getattr(g.ProgressMonitor, name))     # restored after the test
    reg = g.ProgressMonitor()
    reg.trusted((1., 0.), 1.)
    assert reg.baseline is not None                          # registered: a stationary fix arms the baseline
    info = pr.install('p2')
    assert g.STALL_COMMANDED_M == pr.REGISTERED['stall_commanded_m'] and 'ProgressMonitor' in info['patched'][0]
    mon = g.ProgressMonitor()
    mon.reset()
    mon.trusted((1., 0.), 1.)                                # stationary re-grasp fix: ignored
    assert mon.baseline is None
    mon.drove(0.5)
    assert not mon.needs_check()                             # no baseline -> nothing to check (single-leg-probe behaviour)
    mon.trusted((1.3, 0.), 0.7)                              # an in-leg trusted estimate arms it
    assert mon.baseline is not None
    mon.drove(0.45)                                          # the 0.40 m rule still fires afterwards
    assert mon.needs_check()
    mon.reset()
    assert mon.baseline is None
