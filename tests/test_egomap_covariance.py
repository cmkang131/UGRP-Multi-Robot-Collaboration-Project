from types import SimpleNamespace

import numpy as np
import pytest

from harness import egomap_covariance as m
from scripts import evaluate_egomap_covariance as score


def calibration():
    return dict(option=m.OPTION, target='xy', dof=2, pooled_factor=2.,
                factors={'return/turn_left':4.}, fit_seeds=[1], check_seeds=[2])


def test_off_does_not_read_or_modify_controller():
    c = object()
    assert m.install(c) is c


def test_scalar_inflation_preserves_cross_terms_psd_and_exact_nees_relation():
    p = np.array([[2., .5, .1], [.5, 1., .2], [.1, .2, .5]])
    before = p.copy()
    result = m.inflated(p, 4.)
    assert np.array_equal(p, before)
    assert np.allclose(result, 4*p)
    assert np.linalg.eigvalsh(result-p).min() > 0
    assert score.nees([1., 2.], result) == pytest.approx(score.nees([1., 2.], p)/4)
    with pytest.raises(ValueError):
        m.inflated(p, .99)
    with pytest.raises(ValueError):
        m.inflated(np.zeros((3,3)), 2.)


def test_live_selection_uses_previous_command_and_inflates_consumed_covariance_once():
    raw = np.diag([.01, .02, .03])
    base = SimpleNamespace(covariance=raw, pose=(1., 2., 3.))
    g = SimpleNamespace(odom=base)
    c = SimpleNamespace(explorer=SimpleNamespace(memory=SimpleNamespace(self_map=g)),
                        stage='return', last_command={'turn':.35}, last_trace=None)
    def receive(**kw):
        seen = g.odom.covariance.copy()
        c.stage = 'declared'  # factors must remain those selected before frame.
        return {'kind':'hold'}, {'consumed':seen.tolist(), 'sigma_xy':np.sqrt(seen[1,1])}
    c.receive = receive
    m.install(c, covariance_inflation=m.OPTION, calibration=calibration())
    command, trace = c.receive(t=1.)
    assert command == {'kind':'hold'}
    assert np.array_equal(trace['consumed'], 4*raw)
    assert trace['covariance_inflation']['stratum'] == 'return/turn_left'
    assert np.array_equal(g.odom.covariance, 4*raw)
    assert np.array_equal(g.odom.covariance, 4*raw)  # no accumulated inflation.
    assert np.array_equal(base.covariance, raw)
    assert g.odom.pose == base.pose
    assert trace == c.last_trace
    with pytest.raises(ValueError, match='ALREADY_INSTALLED'):
        m.install(c, covariance_inflation=m.OPTION, calibration=calibration())


def test_command_strata_and_finite_nonshrinking_artifact():
    assert m.stratum('return', {'turn':-.35}) == 'return/turn_right'
    assert m.stratum('explore', {'forward':-.2}) == 'approach/translation'
    assert m.stratum('approach', None) == 'approach/hold'
    bad = calibration(); bad['pooled_factor'] = float('nan')
    with pytest.raises(ValueError): m.validate(bad)
    bad = calibration(); bad['check_seeds'] = [1]
    with pytest.raises(ValueError): m.validate(bad)


def test_offline_fit_disjoint_seed_and_episode_weighting_no_holdout_leak():
    def row(run, seed, value):
        return dict(run=run, seed=seed, nees=value, stratum='approach/hold', error_xy_m=[1.,0.])
    rows = [row('short',1,2.)]*30 + [row('long',1,6.)]*60 + [row('check',2,1000.)]*20
    artifact = score.fit(rows,[1],[2])
    # Episode balance mean([2,6])/2, not row-weighted 7/3 or heldout tuning.
    assert artifact['pooled_factor'] == 2.
    assert artifact['factors']['approach/hold'] == 2.
    result = score.evaluate(rows, artifact)
    check = result['check']['overall']['stratified']
    assert check['samples'] == 20
    assert check['exceedances']['p999']['count'] == 20
    assert check['mean'] == 500.
    assert check['error_bias_xy_m'] == [1.,0.]  # bias never removed to pass NEES.


def test_exact_nees_requires_full_covariance():
    assert score.nees([1.,1.], [[1.,.5],[.5,1.]]) == pytest.approx(4/3)
    assert score.nees([1.,1.], [[1.,1.],[1.,1.]]) is None
