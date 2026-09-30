"""Offline motion/noise checks: no physics, images or model requests."""
import ast
import copy
import json
import math
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.linalg import expm

from scripts import fit_unloaded_consumer as c


def test_all_start_windows_keep_onset_stop_and_segment_boundaries():
    starts, k = c.windows([(10, 30), (40, 60)], .5, .05)
    np.testing.assert_array_equal(starts, np.r_[np.arange(10, 21), np.arange(40, 51)])
    assert k == 10
    with pytest.raises(ValueError):
        c.windows([(0, 20)], .123, .05)


def test_endpoint_uses_start_pose_frame_and_wraps_heading():
    pose = np.array([[2., 3., np.pi/2], [2., 4., np.pi/2+.1]])
    np.testing.assert_allclose(c.endpoint_targets(pose, np.array([0]), 1), [[1., 0., .1]], atol=1e-15)
    pose[:, 2] = [np.pi-.1, -np.pi+.1]
    assert c.endpoint_targets(pose, np.array([0]), 1)[0, 2] == pytest.approx(.2)


def test_grey_box_linear_limit_matches_independent_augmented_matrix_exponential():
    dt = .05
    u = np.array([.03]*17+[-.02]*12+[0.]*20)
    active = u != 0
    parameters = [.18, .18, 1.4, 18., 0.]
    p, v = c.grey_box(u, active, dt, parameters, rtol=1e-10)
    state = np.array([0., 0., 0., 1.])  # position, velocity, motor, affine constant
    expected = [state.copy()]
    for command, moving in zip(u, active):
        a = np.zeros((4, 4))
        a[0, 1] = 1
        a[1, 1] = -(1.4 if moving else 18.)/1.1
        a[1, 2] = .18*12/1.1
        a[2, 2], a[2, 3] = -1/.085, command/.085
        state = expm(a*dt) @ state
        expected.append(state.copy())
    np.testing.assert_allclose(p, np.array(expected)[:, 0], atol=2e-10)
    np.testing.assert_allclose(v, np.array(expected)[:, 1], atol=2e-10)


def test_abab_projection_is_causal_and_matches_unclipped_axis_lag():
    u = np.zeros((20, 3))
    u[:, 1] = .03
    projection = c.motor_projection(u, .05)
    t = np.arange(21)*.05
    np.testing.assert_allclose(projection[:, 1], 12*.03*(1-np.exp(-t/.085)), atol=1e-15)
    np.testing.assert_allclose(projection[:, [0, 2]], 0, atol=1e-15)
    assert np.all(projection[0] == 0)


def test_future_pose_cannot_change_command_only_hidden_state_or_prediction():
    data = {'u': np.column_stack((np.full(50, .02), np.zeros((50, 2)))), 'dt': .05,
            'pose': np.zeros((51, 3))}
    p, v = c.predict(data, 0, 'gain_first_order', [1.2, .3, .05])
    data['pose'][10:] = 10000.
    p2, v2 = c.predict(data, 0, 'gain_first_order', [1.2, .3, .05])
    np.testing.assert_array_equal(p, p2)
    np.testing.assert_array_equal(v, v2)
    assert v[25] > 0  # a window at t=1.25 keeps the warm command state


def test_grey_stop_switch_changes_coast_without_resetting_motor_state():
    u = np.r_[np.full(40, .03), np.zeros(10)]
    switched, _ = c.grey_box(u, u != 0, .05, [.18, .18, 1.4, 18., .008])
    running, _ = c.grey_box(u, np.ones(len(u), bool), .05, [.18, .18, 1.4, 18., .008])
    np.testing.assert_allclose(switched[:41], running[:41], atol=1e-8)
    assert 0 < switched[-1]-switched[40] < running[-1]-running[40]


def test_pf_white_covariance_uses_dt_squared_not_continuous_diffusion():
    increments = np.zeros((30, 3))
    mp = {'noise_rel': [0., 0., 0.], 'noise_abs': [.01, .02, .03],
          'scale_std': .2, 'scale_walk': .1}
    _, covariance = c.legacy_windows(increments, np.array([0]), 20, .05, mp, scale=False)
    np.testing.assert_allclose(np.diag(covariance[0]), np.array(mp['noise_abs'])**2*20*.05**2)


def test_pf_scale_uncertainty_is_persistent_not_independent_each_step():
    increments = np.zeros((30, 3))
    increments[:, 0] = .001
    mp = {'noise_rel': [0., 0., 0.], 'noise_abs': [0., 0., 0.],
          'scale_std': .2, 'scale_walk': 0.}
    _, covariance = c.legacy_windows(increments, np.array([0]), 20, .05, mp, scale=True)
    assert covariance[0, 0, 0] == pytest.approx((.2*.001*20)**2)


def test_reference_mean_matches_frozen_consumers_actual_method_without_importing_it():
    blob = subprocess.check_output(['git', 'show', f'{c.FROZEN_M1_SHA}:harness/owncam_localizer.py'], cwd=c.ROOT)
    tree = ast.parse(blob)
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'OwnCamLocalizer')
    fn = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == 'predict_to')
    env = {'np': np, 'math': math, 'STEP_S': .05, 'wrap': lambda v: np.arctan2(np.sin(v), np.cos(v))}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'frozen_predict_to_only', 'exec'), env)
    mp = json.loads((c.ROOT/'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json').read_text())['params']['motion']
    u = np.array([[.02, 0., 0.]]*7 + [[-.01, 0., 0.]]*9 + [[0., .03, 0.]]*11 + [[0., 0., 0.]]*20)
    expected = c.legacy_increments({'u': u, 'dt': .05}, mp)
    pf = SimpleNamespace(t=0., vel=np.zeros(3), initialized=False, _motion_params=lambda: mp)
    actual = []
    for i, command in enumerate(u):
        pf.cmd, pf.cmd_expires = command, (i+1)*.05
        env['predict_to'](pf, (i+1)*.05)
        actual.append(pf.vel*.05)
    np.testing.assert_allclose(actual, expected, atol=1e-16)


def test_noise_fit_recovers_known_motion_variance_and_does_not_invent_turn_alphas():
    rng = np.random.default_rng(472)
    features = np.column_stack((rng.uniform(.2, 3., 50000), rng.uniform(.005, .09, 50000)**2))
    truth = np.array([[1e-6, .012], [2e-7, .003], [3e-6, .006]])
    error = rng.normal(size=(len(features), 3))*np.sqrt(features @ truth.T)
    noise = c.fit_noise({'all': {'features': features, 'residual': error}})
    np.testing.assert_allclose(noise['coefficients_along_cross_yaw'], truth, rtol=.10)
    assert noise['alpha2'] is None and noise['alpha4'] is None
    metrics = c.calibration_metrics(error, c.noise_variance({'features': features}, noise))
    np.testing.assert_allclose(metrics['coverage_1sigma'], .6827, atol=.01)
    np.testing.assert_allclose(metrics['coverage_2sigma'], .9545, atol=.01)
    assert metrics['mean_nees_3d'] == pytest.approx(3., abs=.03)


def test_bias_is_retained_in_nees_and_coverage():
    m = c.calibration_metrics(np.full((100, 3), 2.), np.ones((100, 3)))
    assert m['mean_nees_3d'] == 12.
    assert m['coverage_1sigma'] == [0., 0., 0.]


def passing_records():
    model = {'eligible': True}
    noise = {'translation_feature_rank': 2, 'optimizer': [{'success': True}]*3}
    row = {'n': 200, 'calibrated_noise': {'coverage_1sigma': [.68]*3, 'coverage_2sigma': [.95]*3,
            'mean_nees_per_dimension': [1.]*3}, 'existing_white': {'normalized_abs_error_p95': [1.5]*3},
           'new_to_existing_white_sigma_ratio_p95': [.8]*3}
    return model, noise, {'0.2': row, '3.2': copy.deepcopy(row)}


@pytest.mark.parametrize('failure', ['long_horizon', 'inflate', 'overcoverage', 'rank'])
def test_acceptance_fails_closed_on_each_condition(failure):
    model, noise, summary = passing_records()
    gate = json.loads(c.CRITERION.read_text())['acceptance']
    assert c.rejection_reasons(model, noise, summary, gate) == []
    if failure == 'long_horizon':
        summary['3.2']['existing_white']['normalized_abs_error_p95'][0] = 2.1
    elif failure == 'inflate':
        summary['0.2']['new_to_existing_white_sigma_ratio_p95'][0] = 1.1
    elif failure == 'overcoverage':
        summary['0.2']['calibrated_noise']['coverage_2sigma'][2] = 1.
    else:
        model['eligible'] = False
    assert c.rejection_reasons(model, noise, summary, gate)


def test_revision_has_no_legacy_or_turn_bypass_and_keeps_old_object():
    old = {'params': {'motion': {'gain': 1}, 'motion_loaded': None, 'motion_profiles': {'fine': None}},
           'status': 'PARTIAL_UNLOADED_SIM'}
    before = copy.deepcopy(old)
    report = {'r2_sha256': 'abc', 'report_sha256': 'def', 'criterion_sha256': 'ghi',
              'input_manifest_sha256': 'jkl', 'axes': {a: {'selected': None, 'reasons': ['failed']}
                  for a in ('forward', 'left', 'rotate')}}
    new = c.revision(old, report)
    assert old == before
    assert new['params']['motion'] is None
    assert all(v is None for v in new['params']['motion_consumer'].values())
    assert new['status'] == 'PARTIAL_UNLOADED_SIM'
    assert new['motion_identification']['existing_consumer_unchanged'] is False


def test_published_r3_provenance_selection_and_legacy_bytes():
    folder = c.ROOT/c.RECORD
    report_bytes = (folder/'consumer_report_r3.json').read_bytes()
    report = json.loads(report_bytes)
    revision = json.loads((folder/'calibration_partial_r3.json').read_bytes())
    assert c.sha(report_bytes) == revision['motion_identification']['report_sha256']
    assert c.sha(c.CRITERION.read_bytes()) == report['criterion_sha256']
    assert c.sha((folder/'input_manifest_r3.json').read_bytes()) == report['input_manifest_sha256']
    for key, filename in (('r1_sha256', 'calibration_partial.json'), ('r2_sha256', 'calibration_partial_r2.json')):
        frozen = subprocess.check_output(['git', 'show', f'8feab578:{c.RECORD}/{filename}'], cwd=c.ROOT)
        assert frozen == (folder/filename).read_bytes()
        assert c.sha(frozen) == report[key]
    for axis in ('forward', 'left'):
        candidates = report['axes'][axis]['models']
        for model in candidates:
            reasons = c.rejection_reasons(model, model['noise'], model['prbs'], report['criterion']['acceptance'])
            assert model['passes_A'] == (not reasons)
            assert model['noise']['alpha2'] is None and model['noise']['alpha4'] is None
        selected = report['axes'][axis]['selected']
        passing = [m for m in candidates if m['passes_A']]
        assert (selected is None) == (not passing)
        if selected:
            assert selected['kind'] == passing[0]['kind']
        assert revision['params']['motion_consumer'][axis] == selected
    assert revision['params']['motion_consumer']['rotate'] is None
