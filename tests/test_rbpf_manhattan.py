import json
import math
import numpy as np
import pytest
from harness.rbpf_manhattan import install, axis_observation, condition, OPTION, PERIOD
from tests.test_rbpf_rejection import grid as selective_grid
from tests.test_self_map_prob import observe, CORNER


def test_axial_mean_is_undirected_orthogonal_and_rotation_equivariant():
    r = axis_observation(CORNER, .02)
    reverse = axis_observation(CORNER[:, ::-1], .02)
    assert abs(np.exp(4j*r['angle_rad'])-np.exp(4j*reverse['angle_rad'])) < 1e-12
    assert r['resultant'] == pytest.approx(1.) and r['variance_rad2'] == pytest.approx(.0004)
    angle = .31
    R = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    rotated = axis_observation(CORNER@R.T, .02)
    assert abs(np.exp(4j*rotated['angle_rad'])-np.exp(4j*(r['angle_rad']+angle))) < 1e-12


def test_directionless_inputs_and_scatter_uncertainty():
    assert axis_observation([], .02) is None
    assert axis_observation([[[0,0],[0,0]]], .02) is None
    assert axis_observation([[[0,0],[float('nan'),1]]], .02) is None
    ambiguous = [[[0,0],[1,0]], [[0,0],[2**-.5,2**-.5]]]
    assert axis_observation(ambiguous, .02) is None
    scattered = [[[0,0],[1,0]], [[0,0],[math.cos(.2),math.sin(.2)]]]
    assert axis_observation(scattered, .02)['variance_rad2'] > .0004


def test_gaussian_conditioning_correct_sign_joseph_covariance_and_modes():
    p = np.array([[.1,0,.01],[0,.1,0],[.01,0,.04]])
    obs = dict(angle_rad=0.,variance_rad2=.001)
    mean,cov,ll,d = condition(np.array([0.,0.,.15]),p,0.,obs,np.random.default_rng(1))
    assert abs(mean[2]) < .01 and mean[0] < 0 and d['branch']==0
    np.testing.assert_allclose(cov, p-np.outer(p[:,2],p[2,:])/(p[2,2]+.001))
    assert np.linalg.eigvalsh(cov).min() > 0 and np.isfinite(ll)
    alternative = condition(np.array([0.,0.,PERIOD+.15]),p,0.,obs,np.random.default_rng(1))
    assert abs(alternative[0][2]-PERIOD) < .01  # do not falsely force absolute yaw zero
    assert alternative[2] == pytest.approx(ll)


def test_off_bytes_rng_and_installer_contract():
    a,b=install(selective_grid()),selective_grid()
    for i,t in enumerate([0.,.2,2.]):
        for g in (a,b):
            if i==2:g.odom.driver._pose[2]+=.6
            observe(g,t,i)
        assert json.dumps([a.export(),a.decisions,a.rng.bit_generator.state]).encode()==json.dumps([b.export(),b.decisions,b.rng.bit_generator.state]).encode()
    assert not hasattr(a,'_manhattan_axes')
    with pytest.raises(ValueError):install(a,yaw_prior='bad')


def test_axis_reference_resampling_duplicate_and_range():
    g=install(selective_grid(),yaw_prior=OPTION)
    observe(g,0.,0)
    axes=g._manhattan_axes.copy()
    assert np.std(axes)>0 and g._manhattan_events[-1]['status']=='initialized'
    saved=json.dumps([g.export(),g._manhattan_events,g.rng.bit_generator.state])
    observe(g,0.,0)
    assert json.dumps([g.export(),g._manhattan_events,g.rng.bit_generator.state])==saved
    g.weights[:]=0.;g.weights[4]=1.
    _,parents=g.resample_if_needed()
    assert parents==[4]*30
    np.testing.assert_array_equal(g._manhattan_axes,np.full(30,axes[4]))
    g.odom.driver._pose[2]+=.6
    observe(g,2.,1, np.array([[[5.,0.],[5.,1.]]]))
    assert g._manhattan_events[-1]['status']=='no_direction'


def test_observation_does_not_require_map_overlap_and_forecast_is_private():
    from harness.active_information_gain import forecast
    g=install(selective_grid(),yaw_prior=OPTION)
    observe(g,0.,0)
    # Known command prediction drift; synthetic body lines supply heading only.
    g.poses[:,2]+=.25
    g.pending_cov[:]=np.diag([.1,.1,.03])
    g.odom.driver._pose[2]+=.6
    observe(g,2.,1)
    assert g._manhattan_events[-1]['status']=='conditioned'
    assert g._manhattan_events[-1]['particles']==30
    assert g._manhattan_events[-1]['max_abs_correction_deg']>0
    saved=json.dumps([g.export(),g._manhattan_events,g.rng.bit_generator.state])
    forecast(g,[[0,0],[.5,0]])
    assert json.dumps([g.export(),g._manhattan_events,g.rng.bit_generator.state])==saved
