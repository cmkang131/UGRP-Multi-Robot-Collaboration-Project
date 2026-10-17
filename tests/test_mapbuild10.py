"""Coarse prior, original Nav2 sensor robustness, and closed runtime admission."""
import copy
import math
import numpy as np
import pytest
from harness.mapbuild_amcl import StaticAMCL, StaticField, OPTION
from harness.mapbuild_start_zone import OPTION as PRIOR, SCHEMA
from harness.mapbuild_amcl_vendor import algorithms as nav2

STATIC = dict(map_id='fixture', bounds_m=[-1, 1, -1, 1], obstacles=[
    dict(id='wall_north', center_m=[0, .9], half_extents_m=[1, .02])])
REQ = dict(handoff=dict(position_error_m=.2007512557246549,
    yaw_error_rad=.3739074138060199, nominal_target_range_m=.8483145702460003))
CAL = dict(truth_inputs=0, alphas=[.1, .2, .3, .4])
ZONE = dict(schema=SCHEMA, zone_id='operator_test_box', map_id='fixture',
    bounds_m=[-.25, .25, -.25, .25], heading_center_rad=0.,
    heading_half_width_rad=math.pi/6, source_kind='operator_coarse',
    source_evidence='synthetic fixture; not a real recording start region')


def model(prior=ZONE, **kw):
    return StaticAMCL(STATIC, CAL, REQ, option=OPTION, profile='nav2_defaults_v1',
                      initial_prior_option=PRIOR, initial_prior=prior, **kw)


def test_uniform_coarse_prior_and_nav2_defaults_no_exact_pose():
    m = model()
    assert len(m.particles) == 2000 and m.minimum_particles == 500
    assert m.sigma_hit == .2 and m.alpha_slow == m.alpha_fast == 0
    p = m.particles
    assert np.ptp(p[:, 0]) > .48 and np.ptp(p[:, 1]) > .48
    assert np.ptp(p[:, 2]) > math.pi/3-.01
    assert np.max(abs(p[:, :2])) <= .25 and np.max(abs(p[:, 2])) <= math.pi/6
    assert np.all(m.field.distances(p[:, :2]) > 0)
    np.testing.assert_array_equal(p, model().particles)
    assert not m.belief()['converged'] and not m.belief()['ready_for_handoff']


@pytest.mark.parametrize('change', [dict(spawn_pose=[0, 0, 0]), dict(pose=[0, 0, 0]),
    dict(bounds_m=[0, 0, 0, 0]), dict(bounds_m=[-.1, .1, -.25, .25]),
    dict(heading_half_width_rad=.01), dict(source_evidence=''),
    dict(source_kind='rounded_spawn'), dict(map_id='other'),
    dict(bounds_m=[math.nan, 1, -1, 1]), dict(source_kind='authored_static_zone')])
def test_reject_exact_or_unproven_prior(change):
    zone = {**ZONE, **change}
    with pytest.raises(ValueError):
        model(zone)


def test_prior_toggle_is_explicit_and_no_missing_value_fallback():
    with pytest.raises(ValueError, match='EXPLICIT'):
        StaticAMCL(STATIC, CAL, REQ, initial_prior=ZONE)
    with pytest.raises(ValueError, match='COARSE_START_ZONE'):
        model(None)
    m = StaticAMCL(STATIC, CAL, REQ, option=OPTION, profile='nav2_defaults_v1')
    assert np.ptp(m.particles[:, 0]) > 1.9 and np.ptp(m.particles[:, 2]) > 6.2
    assert m.initial_prior_option == 'off'


def test_authored_map_zone_is_literal_and_can_override_box_size():
    static = copy.deepcopy(STATIC)
    static['start_zones'] = {'small_authored': dict(bounds_m=[-.1, .1, -.2, .2])}
    zone = {**ZONE, 'zone_id': 'small_authored', 'bounds_m': [-.1, .1, -.2, .2],
            'source_kind': 'authored_static_zone'}
    m = StaticAMCL(static, CAL, REQ, option=OPTION, profile='nav2_defaults_v1',
        initial_prior_option=PRIOR, initial_prior=zone)
    assert np.max(abs(m.particles[:, 0])) <= .1


def test_nav2_sum_preserves_outlier_support_product_does_not():
    field = StaticField(STATIC)
    poses = np.array([[0, 0, 0], [0, -.13, .1]])
    points = np.tile([0, .9], (96, 1))
    before = points.copy()
    a = nav2.likelihood(field, poses, points, .2)
    product = nav2.likelihood_product(field, poses, points, .0202)
    assert (a >= 1).all() and a[1]/a[0] > .1
    assert product[1]/product[0] < 1e-10
    np.testing.assert_array_equal(points, before)
    # Retain upstream's integer stride: max_beams=60 gives 96 on 96 slots.
    assert abs(a[0]-(1+96*.505**3)) < 1e-12


def test_failed_profile_cannot_become_runtime_handoff_and_own_map_is_separate():
    m = model()
    field = m.field.dist.copy()
    row = m.step(0., 0, [0, 0, 0], dict(segments=[[[0, .9], [.1, .9]]]))
    assert not row['runtime_qualified'] and not row['ready_for_handoff']
    assert row['adopted_pose'] is None and 500 <= len(m.particles) <= 2000
    assert len(m.local_map) == 1
    np.testing.assert_array_equal(field, m.field.dist)
