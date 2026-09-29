"""Door-frame ultrasonic sweep characterisation (offline; no physics step, no controller)."""
from __future__ import annotations

import importlib.util
import math

import numpy as np
import pytest

pytest.importorskip('mujoco')                                  # the CI offline shards have no MuJoCo

from harness.ultrasonic_model import DEFAULT_SPEC, noisy_reading_with_cause, reading_rng, sensor_seed
from scripts import door_ultrasonic_sweep as ds

HAS_MUJOCO = importlib.util.find_spec('mujoco') is not None
FACTS = {'door_half_width': .25}


def test_vectorised_noise_equals_the_shared_reading_model():
    rng = np.random.default_rng(3)
    for th in (15., 7.5):
        spec = ds.spec_for(th)
        true = np.where(rng.random(400) < .15, np.nan, rng.uniform(.03, 3.9, 400))
        true[:3] = [.01, 3.99, 4.2]                            # blind zone, edge of range, beyond range
        draws = ds.noise_draws(7, len(true))
        ok, r = ds.apply_noise(true, np.arange(len(true)), draws, spec)
        seed = sensor_seed(7, ds.ROBOT)
        for k, e in enumerate(true):
            ref, _ = noisy_reading_with_cause(k * spec.period_s, None if np.isnan(e) else float(e),
                                              reading_rng(seed, ds.ROBOT, k), spec)
            assert ok[k] == ref.valid
            if ref.valid:
                assert r[k] == pytest.approx(ref.range_m, abs=1e-9)


def _synthetic(shift, slope=0., W=.5, v=.05, wall=.6, half_window=.09, seed=0, noise=.004):
    s = np.arange(-W, W + 1e-9, v * .06)
    y_s = s + shift                                             # sensor lateral offset from the door centre
    r = wall + slope * s
    far = np.abs(y_s) < half_window
    r = np.where(far, 3.7, r)
    rng = np.random.default_rng(seed)
    r = r + rng.normal(0, noise, len(s))
    ok = np.ones(len(s), bool)
    return s, ok, r


def test_estimator_recovers_lateral_offset_from_the_two_edges():
    for shift in (-.08, 0., .05, .10):
        s, ok, r = _synthetic(shift)
        est = ds.estimate_sweep(s, ok, r, FACTS, theta_deg=15.)
        assert est['status'] == 'ok' and est['yaw_resolved']
        # y_base of a yaw-0 robot = sensor offset - 0 (yaw 0): the sweep started at offset `shift` at s=0
        assert est['y_base_m'] == pytest.approx(shift, abs=.006)
        assert abs(est['yaw_deg']) < .3


def test_narrow_sweep_gives_the_aim_point_but_marks_yaw_unresolved():
    s, ok, r = _synthetic(.02, W=.15, half_window=.04, noise=.012)
    est = ds.estimate_sweep(s, ok, r, FACTS, theta_deg=15.)
    assert est['status'] == 'ok' and not est['yaw_resolved'] and 'yaw_deg' not in est
    assert est['aim_m'] == pytest.approx(.02, abs=.01)


def test_sweep_that_never_leaves_the_window_is_reported_not_guessed():
    s, ok, r = _synthetic(0., half_window=.9)                   # far reading at every position
    assert ds.estimate_sweep(s, ok, r, FACTS)['status'] in ('no_wall_range', 'no_bracket', 'too_few_readings')
    s, ok, r = _synthetic(.5, half_window=.09)                  # window beyond the sweep: wall everywhere
    assert ds.estimate_sweep(s, ok, r, FACTS)['status'] == 'no_bracket'


def test_change_point_scan_over_flips_equals_exhaustive_search():
    rng = np.random.default_rng(5)
    for trial in range(30):
        n = int(rng.integers(40, 120))
        i, j = sorted(rng.integers(6, n - 6, 2))
        if j - i < 4:
            continue
        s = np.linspace(-.5, .5, n)
        r = np.full(n, .6)
        r[i:j] = 3.7
        flip = rng.random(n) < .05
        r[flip] = np.where(r[flip] > 1, .6, 3.7)
        ok = np.ones(n, bool)
        est = ds.estimate_sweep(s, ok, r, FACTS, theta_deg=15., max_mismatch_frac=1.)
        near = (r < 1)
        best = min(((ii - near[:ii].sum()) + near[ii:jj].sum() + ((n - jj) - near[jj:].sum()), ii, jj)
                   for ii in range(3, n - 2) for jj in range(ii + 3, n - 2))
        if est['status'] == 'ok':
            cost = est['mismatches']
            assert cost == best[0]


@pytest.mark.skipif(not HAS_MUJOCO, reason='needs mujoco')
def test_door_world_reads_the_wall_then_the_far_room_without_stepping_physics():
    import mujoco

    def forbidden(*a, **k):
        raise AssertionError('physics stepping is forbidden')
    saved = {n: getattr(mujoco, n) for n in ('mj_step', 'mj_step1', 'mj_step2')}
    for n in saved:
        setattr(mujoco, n, forbidden)
    try:
        world = ds.DoorWorld()
        assert world.facts['door_half_width'] == .25 and world.facts['wall_height_m'] == .4
        spec = ds.spec_for(15.)
        near = ds.echo_trace(world, spec, .6, .0, 0., np.array([-.3]))[0]      # in front of the wall, beside the opening
        far = ds.echo_trace(world, spec, .6, .0, 0., np.array([0.]))[0]        # cone inside the opening
        assert near == pytest.approx(.6, abs=.005)
        assert far > 3.0
        # the two half-angle readings differ at the same pose: 7.5 deg still fits inside the opening at 1.0 m
        d10_15 = ds.echo_trace(world, spec, 1., .0, 0., np.array([0.]))[0]
        d10_75 = ds.echo_trace(world, ds.spec_for(7.5), 1., .0, 0., np.array([0.]))[0]
        assert 1.0 < d10_15 < 1.1 and (np.isnan(d10_75) or d10_75 > 3.)
    finally:
        for n, fn in saved.items():
            setattr(mujoco, n, fn)


def test_truth_aim_matches_geometry():
    assert ds.truth_aim(.6, .03, 0.) == pytest.approx(.03)
    psi = math.radians(4)
    assert ds.truth_aim(.6, 0., psi) == pytest.approx((.6 + DEFAULT_SPEC.face_x_m * (1 - math.cos(psi))) * math.tan(psi)
                                                      + DEFAULT_SPEC.face_x_m * math.sin(psi))


def test_strafe_gain_error_flips_sign_between_the_out_and_back_passes():
    sg = ds.s_grid()
    trace = sg.copy()                                           # 'echo' equals the true strafe coordinate
    W, v, period, gain = .4, .05, .06, 1.03
    s_f, e_f, _ = ds.sample_sweep(trace, W, v, period, scale=gain)
    s_b, e_b, _ = ds.sample_sweep(trace, W, v, period, scale=gain, reverse=True)
    assert np.all(np.diff(s_f) > 0) and np.all(np.diff(s_b) > 0)
    err_f = np.interp(0., s_f, e_f - s_f)
    err_b = np.interp(0., s_b, e_b - s_b)
    assert err_f == pytest.approx((gain - 1) * W, abs=.002)     # forward pass drifts by gain*distance from its start
    assert err_b == pytest.approx(-(gain - 1) * W, abs=.002)    # return pass starts at the other end: opposite sign
    s0, e0, _ = ds.sample_sweep(trace, W, v, period, latency=.1)
    assert np.mean(e0 - s0) == pytest.approx(-.1 * v, abs=.001)  # stamped position lags the true one
