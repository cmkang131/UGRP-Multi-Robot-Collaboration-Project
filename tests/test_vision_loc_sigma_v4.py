"""VIS4 uncertainty calibration regression, synthetic and offline only."""
import copy
import fnmatch
import importlib.util
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT/'experiments/2026-09-26-vision-loc'
sys.path.insert(0, str(HERE))

import calibrate_sigma_v4 as cs
import vision_loc as vl
import vision_loc_cli as cli
import vision_pf
import vision_sigma as vs


def config(a=1., b=0., q=.001, envelope=True):
    return {'enabled': True, 'stale_envelope': envelope,
            'states': {s: dict(a=a, b_m2=b, q_m2_s=q) for s in vs.STATES}}


def test_absent_measurement_grows_even_when_particle_cloud_collapses():
    h = vs.VarianceCalibrator(config())
    assert h.step(.04, 0., 0., False, True) == pytest.approx(.04)
    assert h.step(.001, 10., 0., False, True) == pytest.approx(.05)
    # A repeat report at the same instant cannot double-charge stale growth.
    assert h.step(.001, 10., 0., False, True) == pytest.approx(.05)
    assert h.step(.001, 11., 11., False, True) == pytest.approx(.001)


def test_load_and_arm_changes_cannot_reset_stale_envelope():
    c = config(b=.1)
    c['states']['loaded_unsettled'] = dict(a=.25, b_m2=0., q_m2_s=.02)
    h = vs.VarianceCalibrator(c)
    assert h.step(.01, 0., 0., False, True) == pytest.approx(.11)
    assert h.step(.001, 2., 0., True, False) == pytest.approx(.15)


def test_no_observation_since_initialization_uses_elapsed_age():
    h = vs.VarianceCalibrator(config(), start_t=5.)
    assert h.step(.01, 15., None, False, True) == pytest.approx(.02)


@pytest.mark.parametrize('config_value', [[], {'bogus': 1}, {'enabled': 1}, {'enabled': False, 'states': {}},
    {'enabled': True, 'states': {}}, config(a=0), config(a=float('nan')), config(q=-1), config(q=0), config(b=True)])
def test_invalid_calibration_fails_closed(config_value):
    with pytest.raises(ValueError): vs.VarianceCalibrator(config_value)


@pytest.mark.parametrize('args', [(-1., 2., 0., False, True), (.1, 2., 3., False, True),
    (.1, float('nan'), None, False, True), (.1, 2., 0., 'loaded', True)])
def test_invalid_runtime_input_fails_closed(args):
    with pytest.raises(ValueError): vs.VarianceCalibrator(config()).step(*args)


def test_backwards_clock_or_scan_is_rejected():
    for time, scan in [(1., 1.), (3., None), (3., 1.)]:
        h = vs.VarianceCalibrator(config()); h.step(.1, 2., 2., False, True)
        with pytest.raises(ValueError): h.step(.1, time, scan, False, True)


def test_covariance_remains_psd_and_mean_yaw_untouched():
    raw = np.array([[.04, .009, .003], [.009, .01, .001], [.003, .001, .002]])
    e = dict(initialized=True, x=1., y=2., yaw=.3, cov=raw.tolist(),
             std_xy_m=math.sqrt(.05), std_yaw_rad=math.sqrt(.002))
    before = copy.deepcopy(e)
    got = vs.VarianceCalibrator(config(a=4., b=.02)).report(e, t=0., last_scan_t=0., loaded=True, settled=True)
    c = np.array(got['cov'])
    assert e == before
    assert np.linalg.eigvalsh(c).min() > 0.
    assert got['std_xy_m']**2 == pytest.approx(.22)
    assert c[0, 2] == pytest.approx(2*raw[0, 2])
    assert c[2, 2] == pytest.approx(raw[2, 2])
    assert all(got[k] == e[k] for k in ('x', 'y', 'yaw', 'std_yaw_rad'))
    assert got['radius95_xy_m'] == pytest.approx(math.sqrt(-2*math.log(.05)*np.linalg.eigvalsh(c[:2,:2]).max()))


def test_exact_nees_uses_cross_covariance_and_refuses_singular_matrix():
    assert vs.xy_nees([.2, .1], [[.04, 0], [0, .01]]) == pytest.approx(2.)
    assert vs.xy_nees([1, 1], [[1, .5], [.5, 1]]) == pytest.approx(4./3.)
    with pytest.raises(ValueError): vs.xy_nees([1, 1], [[1, 1], [1, 1]])


def make_pf(sigma=None):
    m1 = vl.mp.load_m1_localizer()
    p = copy.deepcopy(m1.DEFAULT_PARAMS); p['particles'] = 32
    static = json.loads((HERE/'maps/zone_wide_door_walls_v3_notags.json').read_text())
    pf = vision_pf.make_robust_pf(m1, static, p, {}, {}, {}, 42, sigma_v4=sigma)
    pf.init_gaussian([0., 0., 0.], [.05, .03, .02])
    return pf


def test_report_head_never_changes_particle_rng_weights_or_position():
    a, b, c = make_pf(), make_pf({'enabled': False}), make_pf(config(a=4., b=.01))
    for t in (.2, .4, .6):
        for p in (a, b, c):
            p.command({'t': t-.1, 'kind': 'mecanum', 'forward': .1, 'left': 0., 'turn': .02, 'duration_s': .2})
            p.predict_to(t)
        ea, eb, ec = (p.estimate() for p in (a, b, c))
        assert ea == eb
        for k in ('x', 'y', 'yaw', 'std_yaw_rad'): assert ea[k] == ec[k]
        assert ec['std_xy_m'] > ea['std_xy_m']
        for p in (b, c):
            assert np.array_equal(a.px, p.px) and np.array_equal(a.logw, p.logw)
            assert a.rng.bit_generator.state == p.rng.bit_generator.state


def test_serialized_frames_preserve_full_covariance_and_measurement_clock():
    pf = make_pf(config()); pf.last_scan_t = 0.
    est = pf.estimate()
    row = dict(frame=0, t=0., phase='init', skill_phase=None, commanded_servo={'3':740,'6':1500})
    saved = cli._frame_record(row, {'vision': SimpleNamespace(loc=pf, last=est)})['vision']
    assert saved['cov'] == est['cov'] and saved['raw_cov'] == est['raw_cov']
    assert saved['last_scan_t'] == 0.


def test_cached_and_online_variance_recurrences_match():
    a = np.zeros((4, 14)); a[:,1] = [0, 1, 2, 3]; a[:,2] = [0, 0, 0, 3]
    a[:,3] = [0, 1, 3, 2]; a[:,4] = [.1, .01, .001, .02]
    h = vs.VarianceCalibrator(config())
    expected = [h.step(r[4], r[1], r[2], r[3]>=2, r[3] in (0,2)) for r in a]
    assert np.array_equal(cs.variance_series({'a':a}, config()), expected)


def test_iso_radius_uses_trace_not_axis_sigma():
    a = np.zeros((2, 14)); a[:,5] = [.029, .031]
    r = cs.metrics(a, np.full(2, .01))
    assert r['coverage95'] == .5  # trace .01 -> squared 95% radius .029957
    assert r['nees_iso_mean'] == pytest.approx(6.)


def test_command_features_uses_past_own_commands_only():
    frames = [dict(frame=0, t=1., commanded_servo={'6':1500}), dict(frame=1,t=2.,commanded_servo={'6':1600})]
    commands = [dict(t=0.,kind='initial_servo_command',pulses={'6':1500}), dict(t=1.,kind='look',pan_pulse=1600)]
    assert cs.command_features(frames, commands, .5) == [(False,True),(False,True)]
    with pytest.raises(ValueError): cs.command_features(frames, list(reversed(commands)), .5)


def test_old_test_input_is_rejected_before_file_io(monkeypatch):
    plan = json.loads(cs.PLAN.read_text()); plan['fit_teacher_episodes'][0] = 'vl3-test-s951'
    def forbidden(*args): raise AssertionError('opened data before split guard')
    monkeypatch.setattr(cs, 'read', forbidden)
    with pytest.raises(ValueError): cs.load_data(plan)


def test_global_fit_equal_episode_weights_not_long_episode_domination():
    def seq(n, ratio):
        a=np.zeros((n,14)); a[:,1]=np.arange(n); a[:,2]=np.arange(n); a[:,4]=.01; a[:,5]=ratio*.01
        return dict(name=str(n), kind='vision', cohort='fit_teacher', a=a)
    plan=json.loads(cs.PLAN.read_text()); plan['fit_rule']['q_trace_grid_m2_per_s']=[.000001]
    configs,_=cs.fit([seq(10,2),seq(100,4)],plan)
    assert configs['u1']['states']['unloaded_settled']['a'] == pytest.approx(3.)


def test_selection_rejects_blanket_inflation_and_single_episode_regression():
    def result(nll, coverage):
        return {'cohorts': {'validation/vision':dict(episode_balanced_nll_iso=nll,coverage95=coverage,over_3sigma_fraction=0),
                            'validation/oracle':dict(episode_balanced_nll_iso=nll)},
                'sequences': {'vl3-dev-s945/vision':dict(point_sha256='fixed',all=dict(nll_iso=nll))}}
    results={'u0':result(2,.5),'u1':result(1,1.),'u2':result(1,.95)}
    results['u2']['sequences']['vl3-dev-s945/vision']['all']['nll_iso']=2.11
    assert cs.select(results)['selected']=='u0'
    results['u2']['sequences']['vl3-dev-s945/vision']['all']['nll_iso']=2.
    assert cs.select(results)['selected']=='u2'


def test_sigma_suite_is_collected_in_ci():
    spec=importlib.util.spec_from_file_location('ci_sigma',ROOT/'scripts/run_ci_tests.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert any(fnmatch.fnmatch('tests/test_vision_loc_sigma_v4.py',p) for p in module.TEST_PATTERNS)


def test_sigma_dependency_is_frozen_in_future_motion_replays():
    import compare_v4
    assert 'vision_sigma.py' in compare_v4.RUNTIME
    assert compare_v4.source_hashes()['vision_sigma.py'] == cli.sha_file(HERE/'vision_sigma.py')


def test_pf_only_applied_scan_resets_sigma_growth(monkeypatch):
    p=make_pf(config(q=.01))
    monkeypatch.setattr(p,'scan_loglik',lambda obs,pose:(np.zeros(p.n),96))
    obs=SimpleNamespace(informative=np.ones(96,bool))
    first=p.update_obs(0.,obs,{})
    assert first['measured'] and first['last_scan_t']==0.
    p.px[:,:2]=0.
    stale=p.update_obs(1.,None,{})
    assert not stale['measured'] and stale['last_scan_t']==0.
    assert stale['std_xy_m']**2 >= first['std_xy_m']**2+.01-1e-10
    # An available but unsettled image cannot reset the applied-scan clock.
    p.own_servo_cmd_t=1.
    skipped=p.update_obs(1.1,obs,{})
    assert not skipped['measured'] and skipped['last_scan_t']==0.
    p.own_servo_cmd_t=-1e9
    fresh=p.update_obs(1.2,obs,{})
    assert fresh['measured'] and fresh['last_scan_t']==1.2
    assert fresh['std_xy_m'] < skipped['std_xy_m']
