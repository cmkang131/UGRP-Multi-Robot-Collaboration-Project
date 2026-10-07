import copy
import json
import numpy as np
import pytest
from harness.rbpf_motion_gate import install as motion_install, OPTION as MOTION
from harness.rbpf_rejection import install, motion_variance, OPTION
from tests.test_rbpf_motion_gate import grid as old_grid
from tests.test_self_map_prob import observe, CORNER


def grid(option=OPTION):
    return install(motion_install(old_grid(None), rbpf_update=MOTION), rbpf_rejection=option)


def test_off_full_bytes_and_rng_golden():
    a, b = grid('off'), motion_install(old_grid(None), rbpf_update=MOTION)
    for i, t in enumerate([0., .2, 2., 3.]):
        for g in (a, b):
            if i == 2:
                g.odom.driver._pose[2] += .6
                g.propagate([0, 0, .6], [.001, .001, .01])
            observe(g, t, i)
        assert json.dumps([a.export(), a.decisions, a.rng.bit_generator.state]).encode() == json.dumps([b.export(), b.decisions, b.rng.bit_generator.state]).encode()
    assert not hasattr(a, '_selective_state')


def fake_match(reason, increment=-100.):
    def run(field, points, camera, prior, covariance, rng, options):
        pose = rng.multivariate_normal(prior, covariance)
        return pose, increment, dict(reason=reason, proposal='scan_matched_gaussian' if reason == 'improved_proposal' else 'motion_fallback', log_weight_increment=increment)
    return run


def next_scan(g):
    g.odom.driver._pose[2] += .6
    observe(g, 2., 1)


def test_rejected_scan_preserves_weights_maps_even_when_neff_low(monkeypatch):
    g = grid()
    observe(g, 0., 0)
    g.weights[:] = .001
    g.weights[0] = 1-.001*(len(g.weights)-1)
    g.log_weights = np.log(g.weights)
    saved = [g.weights.tobytes(), g.log_weights.tobytes(), copy.deepcopy(g.cells), json.dumps(g.histories)]
    monkeypatch.setattr('harness.rbpf_rejection.improved_proposal', fake_match('low_overlap'))
    next_scan(g)
    d = g.decisions[-1]
    assert d['status'] == 'rejected' and d['neff'] < 15 and not d['resampled']
    assert not d['sensor_weight_update'] and not d['inserted']
    assert [g.weights.tobytes(), g.log_weights.tobytes(), g.cells, json.dumps(g.histories)] == saved
    assert np.linalg.eigvalsh(g.odom.covariance[:2, :2]).max() > .001


def test_accepted_frame_resamples_only_below_half(monkeypatch):
    g = grid()
    observe(g, 0., 0)
    monkeypatch.setattr('harness.rbpf_rejection.improved_proposal', fake_match('improved_proposal', 0.))
    next_scan(g)
    assert not g.decisions[-1]['resampled']
    g.weights[:] = 0.
    g.weights[:15] = 1/15
    assert g.resample_if_needed()[1] is None  # exact N/2 boundary
    g.weights[:] = .001
    g.weights[0] = 1-.001*29
    g.log_weights = np.log(g.weights)
    g.odom.driver._pose[2] += .6
    observe(g, 4., 2)
    assert g.decisions[-1]['status'] == 'accepted' and g.decisions[-1]['resampled']


def test_mixed_failure_cannot_win_then_resample(monkeypatch):
    g = grid()
    observe(g, 0., 0)
    before = g.weights.tobytes()
    count = 0
    def mixed(*args):
        nonlocal count
        count += 1
        return fake_match('improved_proposal' if count == 1 else 'low_overlap', -100.)(*args)
    monkeypatch.setattr('harness.rbpf_rejection.improved_proposal', mixed)
    next_scan(g)
    d = g.decisions[-1]
    assert d['status'] == 'rejected' and not d['resampled'] and not d['sensor_weight_update']
    assert g.weights.tobytes() == before and d['inserted_particles'] == 0


def test_official_noise_ratios_and_direction_symmetry():
    np.testing.assert_allclose(motion_variance([1, 0, 0]), [.01, .0009, .04])
    np.testing.assert_allclose(motion_variance([0, 1, 0]), [.0009, .01, .04])
    np.testing.assert_allclose(motion_variance([0, 0, 1]), [.01, .01, .04])
    np.testing.assert_array_equal(motion_variance([.2, .1, .3]), motion_variance([-.2, -.1, -.3]))
    np.testing.assert_array_equal(motion_variance([0, 0, 0]), [0, 0, 0])


def test_frame_noise_not_integrator_partition_or_repeated_timestamp():
    a, b = grid(), grid()
    command = dict(t=0., kind='mecanum', forward=.35, left=0., turn=0., duration_s=.10)
    for g in (a, b):
        g.odom.command(command)
    # Internal integration call partition must not change noise for one RGB.
    for t in [.05, .10, .15]:
        b.odom.driver.advance(t)
    for g in (a, b):
        g.odom.advance(.2)
    np.testing.assert_allclose(a.pending_cov, b.pending_cov, atol=1e-12)
    previous = a.pending_cov.copy()
    a.odom.advance(.2)
    np.testing.assert_array_equal(a.pending_cov, previous)
    a.odom.advance(1.)
    assert a._selective_state['noise_frames'] == 1


def test_off_invalid_option_peer_and_forecast_copy_isolation():
    with pytest.raises(ValueError):
        install(old_grid(), rbpf_rejection=OPTION)
    g = grid()
    observe(g, 0., 0)
    saved = json.dumps([g.export(), g.decisions, g.rng.bit_generator.state])
    observe(g, 0., 0)
    from harness.active_information_gain import forecast
    forecast(g, [[0, 0], [.5, 0]])
    assert json.dumps([g.export(), g.decisions, g.rng.bit_generator.state]) == saved
    with pytest.raises(ValueError, match='PEER'):
        g.observe_contacts(t=1., frame_id=4, segments=CORNER, camera_xy=[0, 0], robot_id='r2')
