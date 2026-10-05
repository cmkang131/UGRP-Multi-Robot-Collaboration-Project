"""Partial-fix receipt (second-eigenvalue rule): no simulator, renderer or model."""
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_pair_highpose_partial_fix as pfix


def test_rule_accepts_two_strong_directions_and_keeps_old_verdict_when_full_rank():
    assert pfix.verdicts(np.array([0., 5., 40.]), True) == (False, True, 2)        # one straight wall: along-wall unobserved
    assert pfix.verdicts(np.array([0., 0., 40.]), True) == (False, False, 1)       # a single strong direction is not a fix
    assert pfix.verdicts(np.array([2., 5., 40.]), True) == (True, True, 3)         # full rank: old and new agree
    assert pfix.verdicts(np.array([0., 5., 40.]), False) == (False, False, 2)      # inlier/support/saturation tests still apply
    assert pfix.verdicts(np.array([1., 1., 1.]), True) == (False, False, 0)        # threshold is strict, as in the old gate


def test_information_matrix_recovers_an_analytic_quadratic():
    a = np.array([[40., 0., 3.], [0., 0., 0.], [3., 0., 25.]])        # y (index 1) unobserved

    def loglik(points, obs, pose):
        d = np.asarray(points) - np.array([.1, -.2, .3])
        return -.5*np.einsum('ni,ij,nj->n', d, a, d)

    info = pfix.information_matrix(loglik, np.array([.1, -.2, .3]), None, None)
    assert np.allclose(info, a, atol=1e-6)
    eig = np.linalg.eigvalsh(info)
    assert eig[0] == pytest.approx(0., abs=1e-6) and eig[1] > 1.


def fake_pf(old_accepts):
    pf = SimpleNamespace(last_scan_t=None, v3_last_fix_quality=None, stats={}, partial_fix=None)
    pf.apply_scan = lambda t, obs, pose: None

    def update(t, obs, pose):
        pf.apply_scan(t, obs, pose)
        if old_accepts:
            pf.last_scan_t = t
        return {'measured': old_accepts}
    pf.update_obs = update
    return pf


def test_install_sets_receipt_only_when_the_old_gate_refused(monkeypatch):
    informative = {'accepted': True, 'informative': True, 'old_informative': False, 'settled': True, 'ambiguous': False,
                   'partial': True, 'eigenvalues': [0., 5., 40.], 'observed_rank': 2}
    monkeypatch.setattr(pfix, 'scan_quality', lambda *a: dict(informative))
    pf = fake_pf(old_accepts=False)
    pfix.install(pf, object())
    out = pf.update_obs(3.0, object(), {6: 1500})
    assert out['measured'] is True and pf.last_scan_t == 3.0
    assert pf.v3_last_fix_quality['t'] == 3.0 and pf.v3_last_fix_quality['partial'] is True
    assert 'eigenvalues' not in pf.v3_last_fix_quality and pf.partial_fix['accepted_partial'] == 1
    with pytest.raises(ValueError, match='already installed'):
        pfix.install(pf, object())

    monkeypatch.setattr(pfix, 'scan_quality', lambda *a: {**informative, 'informative': False, 'ambiguous': True})
    pf = fake_pf(old_accepts=False)
    pfix.install(pf, object())
    assert pf.update_obs(3.0, object(), {})['measured'] is False and pf.last_scan_t is None

    pf = fake_pf(old_accepts=True)
    pfix.install(pf, object())
    assert pf.update_obs(4.0, object(), {})['measured'] is True
    assert pf.partial_fix['old_accepted'] == 1 and pf.partial_fix['accepted_partial'] == 0
    assert pf.v3_last_fix_quality is None        # old path keeps the frozen receipt


def test_default_provider_is_untouched():
    from harness import vision_pose_source_highpose as default
    assert not hasattr(default, 'partial_fix') and pfix.record()['default'] == 'off'


def test_partial_provider_installs_on_the_real_pf_and_default_has_no_hook(tmp_path, monkeypatch):
    from harness import zone_pair_highpose_contract as c
    from harness.vision_pose_source_highpose import HighPoseSource
    from tests.test_zone_final_pair_highpose import synthetic, MAPS
    path, _ = synthetic(tmp_path, monkeypatch)
    sha = c.base.sha(path)
    default = HighPoseSource(c.resolve(MAPS[0])[0], path, sha)
    partial = pfix.build_source_class()(c.resolve(MAPS[0])[0], path, sha)
    assert getattr(default.loc._pf, 'partial_fix', None) is None
    assert partial.loc._pf.partial_fix['record']['id'] == pfix.ID
    assert partial.m1_calibration['partial_fix']['id'] == pfix.ID and 'partial_fix' not in default.m1_calibration


def _wstd(px, logw, axis):
    w = np.exp(logw - logw.max())
    w /= w.sum()
    m = (w * px[:, axis]).sum()
    return float(np.sqrt((w * (px[:, axis] - m) ** 2).sum()))


def test_partial_receipt_resets_fix_age_but_not_the_weak_direction_sigma(monkeypatch):
    """#383 P3: a single-wall view (wall along x) constrains y only. The receipt resets the fix age (last_scan_t), but
    the spread along the weak direction x is left as it was: the wrapper never touches particles or weights, and the
    scan's own likelihood is flat in x."""
    gx, gy = np.meshgrid(np.linspace(-.3, .3, 25), np.linspace(-.3, .3, 25))
    pf = SimpleNamespace(last_scan_t=1.0, v3_last_fix_quality=None, stats={}, partial_fix=None,
                         px=np.c_[gx.ravel(), gy.ravel(), np.zeros(gx.size)], logw=np.zeros(gx.size))
    pf.apply_scan = lambda t, obs, pose: setattr(pf, 'logw', pf.logw - .5 * (pf.px[:, 1] / .02) ** 2)

    def update(t, obs, pose):
        pf.apply_scan(t, obs, pose)
        return {'measured': False}          # old gate (lambda_min) refuses the single-wall view
    pf.update_obs = update
    q = {'accepted': True, 'informative': True, 'old_informative': False, 'settled': True, 'ambiguous': False,
         'partial': True, 'eigenvalues': [0., 5., 40.], 'observed_rank': 2, 'weakest_direction_xy_yaw': [1., 0., 0.]}
    monkeypatch.setattr(pfix, 'scan_quality', lambda *a: dict(q))
    pfix.install(pf, object())
    sx, sy, px0 = _wstd(pf.px, pf.logw, 0), _wstd(pf.px, pf.logw, 1), pf.px.copy()
    assert pf.update_obs(5.0, object(), {})['measured'] is True and pf.last_scan_t == 5.0   # fix age reset
    assert np.array_equal(pf.px, px0)
    assert _wstd(pf.px, pf.logw, 0) == pytest.approx(sx, rel=1e-9)        # weak direction: unchanged
    assert _wstd(pf.px, pf.logw, 1) < .2 * sy                               # observed direction: tightened


def test_report_marks_partial_fix():
    from dataclasses import dataclass, field

    @dataclass(frozen=True)
    class R:
        observation_quality: dict = field(default_factory=dict)
    out = pfix.mark_partial(R({'informative': True}), {'partial': True, 'observed_rank': 2,
                                                         'weakest_direction_xy_yaw': [1., 0., 0.]})
    assert out.observation_quality['informative'] is True and out.observation_quality['partial'] is True
    assert out.observation_quality['observed_rank'] == 2
    assert pfix.mark_partial(R(), None).observation_quality['partial'] is False
