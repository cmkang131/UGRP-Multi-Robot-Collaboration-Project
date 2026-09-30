"""Offline synthetic identification and calibration boundary regressions."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

from scripts import fit_unloaded_hammerstein as h


def sequence(u, dt=.05):
    return dict(u=np.asarray(u, float), y=np.zeros(len(u)+1), dt=dt, name='synthetic')


def model(kind='linear', order=1, delay=0, theta=None, beta=None):
    return dict(static=kind, order=order, delay_steps=delay,
                theta=theta or [np.log(.3)], coefficients=beta or [.03, .024])


def test_exact_first_order_integral_and_command_endpoint_convention():
    s = sequence([.02]*20)
    p = h.predict(s, model())
    t = np.arange(21)*.05
    np.testing.assert_allclose(p, .03*(t-.3*(1-np.exp(-t/.3))), atol=1e-15)
    assert p[0] == 0 and p[1] > 0


@pytest.mark.parametrize('zeta', [.4, 1., 2.])
def test_second_order_integral_matches_independent_state_space(zeta):
    from scipy.signal import cont2discrete, dlsim, tf2ss
    s = sequence([.02]*15+[-.02]*10+[0.]*20)
    m = model(order=2, theta=[np.log(.2), np.log(zeta)])
    # Integrator + two-pole ODE, independently discretized by matrix exponential.
    system = cont2discrete(tf2ss([1.], [.2**2, 2*zeta*.2, 1., 0.]), .05)
    u = h.static_basis(np.r_[s['u'], 0.], 'linear', [0,0]) @ m['coefficients']
    _, y, _ = dlsim(system, u)
    np.testing.assert_allclose(h.predict(s,m), y[:,0], atol=2e-10)


def test_delay_is_causal_and_negative_command_uses_its_own_gain():
    s = sequence([-.02]*10+[0.]*10)
    m = model(delay=2)
    p = h.predict(s,m)
    np.testing.assert_array_equal(p[:3], np.zeros(3))
    assert p[3] < 0
    np.testing.assert_allclose(p[2:], h.predict(sequence(s['u'][:-2]),model()))


def test_delay_steps_use_control_period_independent_of_observation_period():
    s=sequence([.02]*20,dt=.2)
    s['control_dt']=.25
    p=h.predict(s,model(delay=1))
    t=np.maximum(np.arange(21)*.2-.25,0.)
    np.testing.assert_allclose(p,.03*(t-.3*(1-np.exp(-t/.3))),atol=1e-15)


def test_deadband_polynomial_and_hinge_are_continuous_and_sign_specific():
    u = np.array([-.03,-.02,-.01,-.003,0,.003,.01,.02,.03])
    beta = [1., .5, 2., .25]
    a = h.static_basis(u,'deadband_pwl',[.2,.3]) @ beta
    assert a[4] == 0 and a[3] == 0 and a[5] == 0
    assert np.all(np.diff(a)>=0)
    assert not np.isclose(a[0],-a[-1])


def test_fit_recovers_known_deadband_and_lag_then_predicts_reversals():
    true = model(kind='deadband', theta=[np.log(.18),.2,.3], beta=[.035,.028])
    steps=[]
    for v in (.01,-.01,.02,-.02,.03,-.03):
        s=sequence([v]*100+[0.]*30)
        s['y']=h.predict(s,true)
        steps.append(s)
    m=h.fit(steps,'deadband',1,0)
    np.testing.assert_allclose(m['theta'],true['theta'],atol=2e-5)
    np.testing.assert_allclose(m['coefficients'],true['coefficients'],atol=2e-6)
    prbs=sequence(([.02]*10+[-.02]*10)*5)
    prbs['y']=h.predict(prbs,true)
    assert h.metrics([prbs],m)['nrmse'] < 1e-5


def test_one_amplitude_prbs_does_not_identify_polynomial_curve():
    s=sequence(([.02]*10+[-.02]*10)*3)
    x=h.design(s,'deadband_quadratic',1,0,[np.log(.3),.2,.3])
    assert x.shape[1]==4
    assert np.linalg.matrix_rank(x)==2


def test_nrmse_uses_centered_energy_and_does_not_remove_residual_bias():
    s=sequence([.02]*20)
    m=model()
    s['y']=h.predict(s,m)+.001
    result=h.metrics([s],m)
    assert result['rmse']==pytest.approx(.001)
    assert result['nrmse']==pytest.approx(.001/np.std(s['y'][1:]))


def test_revision_preserves_old_bytes_semantics_and_blocks_legacy_rotation():
    old={'schema':'v1','status':'PARTIAL_UNLOADED_SIM','params':{'motion':{'gain':[1,2,3]},
         'motion_loaded':None,'motion_profiles':{'fine':None}}}
    before=copy.deepcopy(old)
    empty = {'steps_to_prbs': {'candidates': []}, 'prbs_to_steps': {'candidates': []}}
    new=h.revision(old,{'old_calibration_sha256':'abc', 'axes':{'forward':empty,'left':empty}},'def')
    assert old==before
    assert new['status']=='PARTIAL_UNLOADED_SIM'
    assert new['params']['motion'] is None
    assert all(v is None for v in new['params']['motion_hammerstein'].values())
    assert new['params']['motion_loaded'] is None
    assert new['params']['motion_profiles']['fine'] is None


@pytest.mark.parametrize('bad', ['nrmse','identifiability','convergence','nonmonotonic'])
def test_adoption_rejects_failed_validation_or_unidentified_structure(bad):
    m=model()
    m.update(deadband_command=[0,0],optimizer_success=True,static_rank=2,static_columns=2,
             identifiable_static=True,validation={'nrmse':.02},bic=-100)
    reverse=copy.deepcopy(m)
    directions={'steps_to_prbs':{'candidates':[m]},'prbs_to_steps':{'candidates':[reverse]}}
    assert h.adoption(directions) is m
    if bad=='nrmse':
        reverse['validation']['nrmse']=.051
    elif bad=='identifiability':
        reverse['identifiable_static']=False
    elif bad=='convergence':
        reverse['optimizer_success']=False
    else:
        reverse['coefficients']=[-.01,.01]
    assert h.adoption(directions) is None


@pytest.mark.parametrize('relative', ['raw','raw/fit','.'])
def test_raw_input_tree_cannot_be_output(tmp_path, relative):
    with pytest.raises(ValueError,match='disjoint'):
        h.require_disjoint_output(tmp_path/relative,tmp_path/'raw')


def test_revision_artifact_and_p03_admission():
    from harness import zone_final_environment as env
    folder=h.ROOT/h.RECORD
    new=json.loads((folder/'calibration_partial_r2.json').read_text())
    report=json.loads((folder/'hammerstein_report.json').read_text())
    manifest=(folder/'input_manifest_v89.json').read_bytes()
    assert h.sha((folder/'calibration_partial.json').read_bytes())==new['previous_revision']['sha256']
    assert new['motion_measurement_manifest_sha256']==h.sha(manifest)==report['input_manifest_sha256']
    assert new['params']['motion'] is None
    assert all(v is None for v in new['params']['motion_hammerstein'].values())
    assert new['params']['motion_loaded'] is None
    assert new['camera_models']['loaded'] is None
    assert report['audit']['rotation_command_nonzero']==0
    for axis in ('forward','left'):
        assert h.adoption(report['axes'][axis]) is None
        assert report['axes'][axis]['steps_to_prbs']['best_cv']['validation']['nrmse']>.05
    with pytest.raises(ValueError,match='combination mismatch'):
        path=folder/'calibration_partial_r2.json'
        env.measured_calibration(path,env.sha(path),'zone_wide_two_doors_final_v3')
    # Portable source integrity check, without requiring local-only raw in CI.
    for entry in json.loads(manifest)['files']:
        if entry['kind']=='file' and '/ugrp-wt/calib-fit-v87/' in entry['path']:
            rel=entry['path'].split('/ugrp-wt/calib-fit-v87/',1)[1]
            assert h.sha((h.ROOT/rel).read_bytes())==entry['sha256']


def test_offline_suite_collects_this_file_once():
    from scripts.run_ci_tests import collect_test_files, TEST_PATTERNS
    assert collect_test_files(h.ROOT,TEST_PATTERNS).count('tests/test_unloaded_hammerstein.py')==1
