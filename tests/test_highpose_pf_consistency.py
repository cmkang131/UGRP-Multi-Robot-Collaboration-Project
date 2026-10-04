"""v98 PF consistency module: view counting, column tempering, gate unchanged. No simulator or renderer."""
import math
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_pair_highpose_pf_consistency as pfc
from harness import vision_loc_protocol as vp


def test_validate_rejects_bad_configs():
    assert pfc.validate(None) == pfc.DEFAULT
    assert pfc.validate(pfc.NEUTRAL) == pfc.NEUTRAL
    for bad in ({'repeat_rho': 1.5}, {'repeat_rho': -.1}, {'effective_columns': 0.},
                {'effective_columns': float('nan')}, {'update_min_d': -1.}, {'update_min_a': True},
                {'sigma_px': 2.5}, {'schema': 'other'}):
        with pytest.raises(ValueError):
            pfc.validate(bad)


def test_design_effect_exponents():
    assert [pfc.exponent(k, 0.) for k in range(1, 6)] == [1.]*5
    assert [pfc.exponent(k, 1.) for k in range(1, 6)] == [1., 0., 0., 0., 0.]
    half = [pfc.exponent(k, .5) for k in range(1, 30)]
    assert all(a > 0 for a in half) and math.isclose(sum(half), pfc.cumulative(29, .5))
    assert pfc.cumulative(10**6, .5) < 2.   # K equally correlated scans never exceed 1/rho scans


class FakePF:
    """Minimal PF surface the module wraps (t, vel, load, stats, predict_to, apply_scan, scan_loglik)."""

    def __init__(self):
        self.t, self.vel, self.load = 0., np.zeros(3), SimpleNamespace(loaded=False)
        self.stats, self.measurement, self.applied = {}, {'effective_columns': 8}, []

    def predict_to(self, t):
        self.t = t

    def scan_loglik(self, obs, pose):
        return np.array([-4., -1.]), obs

    def apply_scan(self, t, obs, pose):
        self.applied.append(self.scan_loglik(obs, pose)[0])

    def command(self, row):
        self.last_command = row

    def init_gaussian(self, mean, std):
        self.prior = (mean, std)


def test_view_rules_on_fake_pf():
    pf = FakePF()
    pfc.install(pf, {'repeat_rho': 1., 'effective_columns': 2., 'update_min_d': .02, 'update_min_a': .035})
    with pytest.raises(ValueError, match='already installed'):
        pfc.install(pf, None)
    assert pf.measurement == {'effective_columns': 8}           # gate input untouched
    still = {1: 1500, 6: 1500}
    for t in (.05, .10, .15):                                    # one still view, 96 column terms
        pf.predict_to(t)
        pf.apply_scan(t, 96, still)
    np.testing.assert_array_equal(pf.applied[0], np.array([-4., -1.])*2/8)
    np.testing.assert_array_equal(pf.applied[1], 0.*pf.applied[1])
    np.testing.assert_array_equal(pf.applied[2], 0.*pf.applied[2])
    pf.apply_scan(.2, 96, {1: 1500, 6: 1510})                     # posture change -> new view
    pf.vel = np.array([.1, 0., 0.]); pf.predict_to(.45)           # 25 mm own commanded odometry
    pf.apply_scan(.45, 96, {1: 1500, 6: 1510})                    # odometry >= update_min_d -> new view
    pf.vel = np.zeros(3); pf.predict_to(.5)
    pf.apply_scan(.5, 4, {1: 1500, 6: 1510})                      # repeat; frame with 4 terms (< E)
    pf.load.loaded = True
    pf.apply_scan(.55, 4, {1: 1500, 6: 1510})                     # load change -> new view, 4 terms
    np.testing.assert_array_equal(pf.applied[3], np.array([-4., -1.])*2/8)
    np.testing.assert_array_equal(pf.applied[4], np.array([-4., -1.])*2/8)
    np.testing.assert_array_equal(pf.applied[5], 0.*pf.applied[5])
    np.testing.assert_array_equal(pf.applied[6], np.array([-4., -1.])*.5)   # min(1, 2/4)/min(1, 8/4)
    pf.command({'t': .6, 'kind': 'hold'})                          # zero/hold commands are not a move
    pf.apply_scan(.65, 96, {1: 1500, 6: 1510})
    pf.command({'t': .7, 'kind': 'mecanum', 'forward': .08, 'left': 0., 'turn': 0., 'duration_s': .3})
    assert pf.last_command['kind'] == 'mecanum'                    # forwarded to the frozen PF
    pf.apply_scan(1.1, 96, {1: 1500, 6: 1510})                     # own drive pulse below update_min_d -> new view
    pf.apply_scan(1.15, 96, {1: 1500, 6: 1510})
    pf.init_gaussian((0., 0., 0.), (.1, .1, .1))                   # re-initialised cloud -> new view
    assert pf.prior == ((0., 0., 0.), (.1, .1, .1))
    pf.apply_scan(1.2, 96, {1: 1500, 6: 1510})
    assert [float(a[0]) for a in pf.applied[7:]] == [0., -1., 0., -1.]
    assert pf.stats == {'view_scans': 6, 'repeat_scans': 5, 'repeat_weight': 0.}


def test_neutral_config_is_frozen_likelihood():
    pf = FakePF()
    pfc.install(pf, pfc.NEUTRAL)
    for t in (.05, .1, .15):
        pf.apply_scan(t, 96, {1: 1500})
    pf.apply_scan(.2, 3, {1: 1500})
    assert all(np.array_equal(a, np.array([-4., -1.])) for a in pf.applied)


def _scan(src, servo):
    """A frame whose bottom-edge rows equal particle 0's prediction (varied per-particle log-likelihood)."""
    vl, _ = vp.load_vis3()
    pf = src.loc._pf
    vb, _ = pf.expected(pf.px[:1], servo)
    rows = np.asarray(vb[0], float)
    n = rows.size
    kind = np.where(np.isfinite(rows), vl.EDGE, vl.NONE)
    return vl.ColumnObs(np.asarray(pf.columns), kind, rows, rows, np.full(n, vl.NONE), np.full(n, np.nan),
                        np.full(n, np.nan))


def test_provider_installs_registered_config(tmp_path, monkeypatch):
    from tests.test_zone_final_pair_highpose import synthetic, MAPS, c, pose
    from harness.vision_pose_source_highpose import HighPoseSource
    path, _ = synthetic(tmp_path, monkeypatch)
    floor = pose.grasp_postures()[1][-1]
    servo = {1: 2000, **floor}

    def build():
        src = HighPoseSource(c.resolve(MAPS[0])[0], path, c.base.sha(path))
        src.init_prior((1., 0., 0.), (.1, .1, .1), source='synthetic public dock')
        return src

    src = build()
    pf = src.loc._pf
    assert src.runtime_contract['pf_consistency'] == pfc.record(pfc.CONFIG)
    assert pf.pf_consistency['config'] == pfc.validate(pfc.CONFIG)
    assert pf.measurement['effective_columns'] == 8                # registered gate input unchanged
    obs = _scan(src, servo)
    frozen, n = type(pf).scan_loglik(pf, obs, servo)
    assert n > 8 and np.ptp(frozen) > 0
    w0 = pf.logw.copy()
    pf.apply_scan(1., obs, servo)
    np.testing.assert_allclose(pf.logw - w0, frozen*pfc.CONFIG['effective_columns']/8, rtol=0, atol=1e-12)
    assert pf.v3_scan_quality is not None                          # informative gate still evaluated
    w1 = pf.logw.copy()
    pf.apply_scan(1.05, obs, servo)                                # same still view: design-effect share only
    cfg = pfc.validate(pfc.CONFIG)
    np.testing.assert_allclose(pf.logw - w1, frozen*cfg['effective_columns']/8*pfc.exponent(2, cfg['repeat_rho']),
                               rtol=0, atol=1e-12)
    assert pfc.exponent(2, cfg['repeat_rho']) < 1.
    assert pf.stats['view_scans'] == 1 and pf.stats['repeat_scans'] == 1

    monkeypatch.setattr(pfc, 'CONFIG', pfc.NEUTRAL)
    neutral = build()
    assert neutral.identity_sha256 != src.identity_sha256
    npf = neutral.loc._pf
    w0 = npf.logw.copy()
    npf.apply_scan(1., obs, servo)
    npf.apply_scan(1.05, obs, servo)
    np.testing.assert_array_equal(npf.logw - w0, (w0 + frozen + frozen) - w0)  # frozen: every scan counted
    vp.check_frozen()
