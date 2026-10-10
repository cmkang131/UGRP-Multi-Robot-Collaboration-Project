import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from harness import pf_sensor_proposal as p


def test_off_identity_and_unchanged_rng():
    marker = object()
    assert p.attach_s3(marker) is marker
    assert p.attach_ownmap(marker) is marker
    rng = np.random.default_rng(14201); before = copy.deepcopy(rng.bit_generator.state)
    assert p.attach_s3(SimpleNamespace(rng=rng)).rng is rng
    assert rng.bit_generator.state == before


def test_importance_ratio_recovers_target_with_map_and_motion_constraints():
    motion = np.log([.1, .2, .3, .4]); sensor = np.log([.2, 4., 2., 3.])
    q, target, audit = p.mixture(motion, sensor, [True, True, False, False])
    good = q > 0
    assert np.allclose(q[good]*np.exp(target[good]-np.log(q[good])), [.02, .8])
    assert q[2:].sum() == 0 and audit['rejected'] == 2
    assert np.isneginf(target[2:]).all()
    assert np.array_equal(p.bounded(np.array([[0., 0, 0], [7., 0, 0]]), np.eye(3)), [True, False])
    with pytest.raises(p.NoSupport): p.mixture(motion, sensor, [False]*4)


def test_sensor_reset_fraction_only_increases_on_likelihood_mismatch():
    _, _, good = p.mixture(np.log([.99, .01]), np.log([1., 1.]), [1, 1])
    _, _, bad = p.mixture(np.log([.99999, .00001]), np.log([.001, 1.]), [1, 1])
    assert good['sensor_fraction'] == .1 and not good['mismatch']
    assert bad['sensor_fraction'] == .2 and bad['mismatch']


def test_two_modes_keep_two_samples_without_inflating_weak_mass():
    lm = np.log([.999, .001]); ls = np.zeros(2)
    i, lw, audit = p.draw(lm, ls, [1, 1], np.random.default_rng(8), 100, [0, 1])
    w = np.exp(lw); w /= w.sum()
    assert min(np.bincount(i)) >= 2
    assert w[i == 1].sum() == pytest.approx(.001)
    assert len(i) == 100 and sum(audit['mode_allocation']) == 100


def test_unknown_or_occupied_own_map_is_not_free():
    grid = SimpleNamespace(resolution_m=.1, cells={(0, 0): -.2, (1, 0): .4})
    assert p.observed_free(grid, np.array([[.05, .05, 0], [.15, .05, 0], [.25, .05, 0]])).tolist() == [True, False, False]


def test_predictive_nodes_preserve_heading_modes_and_collapsed_covariance():
    poses = np.array([[0., 0, 0], [4., 2, np.pi]])
    nodes, lm, parents, labels = p.predictive_nodes(poses, [.8, .2])
    assert len(nodes) == 54 and np.exp(lm).sum() == pytest.approx(1.)
    assert len(np.unique(nodes, axis=0)) == 2  # no invented covariance floor
    assert np.array_equal(parents, labels)
    for k in (0, 1): assert np.exp(lm[parents == k]).sum() == pytest.approx([.8, .2][k])


def test_real_s3_tracking_handoff_and_current_sensor_packet(tmp_path):
    from tests.s3_stage_probe import consistency_fixture
    from harness.zone_s3_consistency_contract import inputs, ROOT, hp
    from harness.zone_s3_consistent_runtime import Runtime
    from harness.pf_observation_consistency import _closure
    from harness.zone_solo_cyan_landmarks import Measurement
    b = consistency_fixture('0'*40)
    rt = Runtime(hp.resolve(b['map_id'])[0], inputs()[2]['orders'], ROOT/b['calibration'],
        b['calibration_sha256'], seed=b['seed'], config=b['controller_config'])
    try:
        own = rt.localizers['r1']; pf = own.pose.provider.loc._pf
        p.attach_s3(own, sensor_proposal=p.OPTION, tracking_particles=100, static=hp.resolve(b['map_id'])[0])
        before = pf.px.copy(); n = pf.n
        own.on_command('r1', 0., dict(kind='hold'))
        assert np.array_equal(before, pf.px) and pf.n == n
        own.on_command('r1', 0., dict(kind='mecanum', forward=.35, left=0., turn=0., duration_s=.1))
        assert pf.n == 100 and own.sensor_proposal_audit['handoff']['after'] == 100
        selected = _closure(pf.update_obs, 'selected').cell_contents
        score, resample = (selected.__globals__[k] for k in ('likelihood', 'resample'))
        packet = Measurement(np.empty((0, 2)), [])
        assert np.array_equal(score(None, pf.px, packet), np.ones(100))
        triggers = len(own.active_observation['triggers'])
        resample(pf)
        assert len(own.active_observation['triggers']) == triggers
        assert own.sensor_proposal_audit['rows'][-1]['skipped'] == 'existing_ESS_above_half'
        score(None, pf.px, packet)
        pf.logw[:] = -100.; pf.logw[0] = 0.  # explicit resampling-boundary fixture
        triggers = len(own.active_observation['triggers'])
        resample(pf)
        assert len(own.active_observation['triggers']) == triggers
        assert pf.n == 100 and np.isfinite(pf.logw).all()
        assert (pf._map_logprior(pf.px) == 0).all()
        assert own.sensor_proposal_audit['rows'][-1]['support'] > 0
    finally: rt.close()
