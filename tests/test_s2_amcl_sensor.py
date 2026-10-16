import copy
import json
import math
from types import SimpleNamespace as NS

import numpy as np
import pytest

from test_solo_cyan_v106 import static, cal, FakePose, FakeVision, rt
from harness import zone_solo_cyan_amcl_sensor as m
from harness.zone_solo_cyan_likelihood_field import Field, likelihood as old_score, endpoints as old_endpoints
from harness.zone_solo_cyan_best_cluster import runtime_class as best_runtime
from harness.zone_solo_cyan_look_ahead import Runtime as Carry


def test_default_off_command_record_bytes(static, cal):
    Previous = best_runtime(Carry); Wrapped = m.runtime_class(Previous)
    rs = [cls(static, None, None, provider_factory=lambda *a, **k: FakePose(copy.deepcopy(cal)),
        vision_factory=FakeVision, **kw) for cls, kw in
        [(Previous, {}), (Wrapped, {}), (Wrapped, dict(sensor_model='off'))]]
    try:
        for r in rs:
            r.initial_commands(0., {'r3': {1: 1500, **rt.high.HIGH}})
            r.last_report = r.pose.report(1.); r.state = 'carry'; r.receipt = True
        for t in (1., 1.05, 1.1, 1.2, 1.65, 1.8):
            issued = [r.step(t) for r in rs]
            assert len({json.dumps(c).encode() for c in issued}) == 1
            for r, cmds in zip(rs, issued):
                for rid, a in cmds: r.on_command(rid, t, a)
        assert len({json.dumps(r.record()).encode() for r in rs}) == 1
    finally:
        for r in rs: r.close()


def test_original_stride_is_not_a_strict_sixty_beam_cap():
    assert len(m.beam_indices(96)) == 96
    assert len(m.beam_indices(120)) == 60
    np.testing.assert_array_equal(m.beam_indices(121), np.arange(0, 121, 2))
    assert len(m.beam_indices(180)) == 60
    assert len(m.beam_indices(0)) == 0


def test_missing_rays_are_skipped_after_original_index_stride():
    n = 121; points = np.c_[np.full(n, .2), np.arange(n)/100.]
    points[2] = np.nan; points[6] = [100., 0.]
    cm = NS(origin=np.zeros(3), _rot=np.array([[0, 0, 1], [1, 0, 0], [0, 1, 0]]),
        t_of_row=lambda v:v, floor_point=lambda t:points)
    kind = np.ones(n); kind[4] = 0
    obs = NS(columns=np.arange(n), b_kind=kind, b_lo=np.zeros(n))
    pts = m.endpoints(cm, obs)
    np.testing.assert_array_equal(pts, points[[0, *range(8, 121, 2)]])
    np.testing.assert_array_equal(pts, old_endpoints(cm, obs))


def test_ros_literal_particle_ray_loop_and_weight_multiplication():
    field = Field({'obstacles': [dict(kind='wall', center_m=[0., 0.], half_extents_m=[.02, .4])]})
    rng = np.random.default_rng(7)
    particles = np.r_[rng.uniform([-.2, -.2, -.5], [.2, .2, .5], (7, 3)), [[100., 0., 0.]]]
    points = rng.uniform([-.1, -.1], [.1, .1], (96, 2))
    expected = []
    for x, y, yaw in particles:
        p = 1.
        for a, b in points:
            distance = field.distances([[x+math.cos(yaw)*a-math.sin(yaw)*b,
                y+math.sin(yaw)*a+math.cos(yaw)*b]])[0]
            pz = .5*math.exp(-distance**2/(2*.2*.2))+.5/100.
            p += pz*pz*pz
        expected.append(p)
    actual = m.likelihood(field, particles, points)
    np.testing.assert_allclose(actual, expected, rtol=2e-15)
    # Sequential C++ addition vs NumPy pairwise reduction: n * machine epsilon.
    np.testing.assert_allclose(actual, old_score(field, particles, points), rtol=96*np.finfo(float).eps)
    prior = np.arange(1., 9.); prior /= prior.sum()
    cpp_weights = prior*expected; cpp_weights /= cpp_weights.sum()
    ll = np.log(actual); posterior = prior*np.exp(ll-ll.max()); posterior /= posterior.sum()
    np.testing.assert_allclose(posterior, cpp_weights, rtol=3e-15)
    np.testing.assert_array_equal(m.likelihood(field, particles, []), np.ones(8))


def test_selector_is_instance_local_and_uses_the_selected_kernel(static):
    from harness import zone_s2_realism_contract_v131 as contract
    from scripts.run_s2_look_ahead_dev import runtime_factory
    b = contract.bundle('a'*40, carry_pose='look_ahead_v1', servo_stiffness='real_v1',
        camera_pitch='stiff_target_v1', pregrasp_policy='log_only_v1')
    a = runtime_factory(b)(static, contract.ROOT/contract.old.CALIBRATION,
        contract.old.CALIBRATION_SHA, seed=1051)
    z = runtime_factory(b)(static, contract.ROOT/contract.old.CALIBRATION,
        contract.old.CALIBRATION_SHA, seed=1051)
    try:
        pa, pz = a.pose.provider.loc._pf, z.pose.provider.loc._pf
        original = pa.update_obs; other = pz.update_obs
        audit = m.install(a.pose)
        assert original.__globals__['likelihood'] is old_score
        assert other.__globals__['likelihood'] is old_score
        assert pz.update_obs is other
        field = Field(static); particles = np.array([[0., 0., 0.], [.1, 0., 0.]])
        score = pa.update_obs.__globals__['likelihood'](field, particles, [[.2, .1]])
        np.testing.assert_array_equal(score, m.likelihood(field, particles, [[.2, .1]]))
        assert audit['rows'][0]['valid_beams'] == 1
        assert pa.update_obs.__closure__ == original.__closure__
    finally: a.close(); z.close()


def test_invalid_or_probability_preset_is_refused(static):
    for kw in [dict(sensor_model='bad'), dict(sensor_model=m.OPTION),
               dict(sensor_model=m.OPTION, amcl_update='ros_motion_prob_v1')]:
        with pytest.raises(ValueError): m.runtime_class(Carry)(static, None, None, **kw)
