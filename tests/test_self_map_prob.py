"""Probability contracts and legacy byte goldens. No simulator or model calls."""
import json
import math
from pathlib import Path
import types

import numpy as np
import pytest

from harness.self_map_csm import CSMOptions
from harness.self_map_prob import (MomentMatcher, ProbabilisticOdomGrid, V7CommandOdometry,
                                  insertion_weight, moments)
from harness.self_odom_grid import CommandOdometry
from harness.self_map_rbpf import (RaoBlackwellizedGrid, improved_proposal,
                                  importance_increment, systematic_indices)
from harness.self_wall_memory import SelfWallMemory

ROOT = Path(__file__).resolve().parents[1]
CORNER = np.array([[[2., -1.], [2., 1.]], [[.5, 1.], [2., 1.]]])


def observe(grid, t, frame, segments=CORNER):
    return grid.observe_contacts(t=t, frame_id=frame, segments=segments,
                                 camera_xy=[0., 0.], robot_id='r1')


def test_moments_include_mode_ambiguity_and_are_stable():
    mean, cov, weights = moments(np.array([[-2., 0., 0.], [2., 0., 0.]]), np.array([-10000., -10000.]))
    np.testing.assert_allclose(mean, 0.)
    assert cov[0, 0] == pytest.approx(4.)
    assert weights.sum() == pytest.approx(1.)


def test_v7_noise_changes_covariance_only_and_rest_stays_fixed():
    plain, uncertain = CommandOdometry(), V7CommandOdometry()
    before = uncertain.covariance.copy()
    for odom in (plain, uncertain):
        odom.advance(1.)
    np.testing.assert_allclose(uncertain.covariance, before)
    for odom in (plain, uncertain):
        odom.command({'t': 1., 'kind': 'drive', 'forward': .2, 'turn': .1, 'duration_s': 1.})
        odom.advance(3.)
    np.testing.assert_allclose(plain.pose, uncertain.pose, atol=1e-12)
    assert np.trace(uncertain.covariance) > np.trace(before)


def test_covariance_weight_is_monotone_and_scales_hit_and_miss():
    low = ProbabilisticOdomGrid('r1', settle_s=None)
    high = ProbabilisticOdomGrid('r1', settle_s=None)
    high.odom.covariance *= 10
    for grid in (low, high):
        observe(grid, 0., 0)
    assert high.insertion_weights[0] < low.insertion_weights[0] < 1.
    assert high.cells.keys() == low.cells.keys()
    ratio = high.insertion_weights[0]/low.insertion_weights[0]
    for cell in low.cells:
        assert high.cells[cell] == pytest.approx(low.cells[cell]*ratio)
    assert insertion_weight(np.array([[4., 0.]]), [0, 0, 0], np.diag([0, 0, .1]), CSMOptions()) < .01


def test_moment_match_does_not_shrink_wall_tangent_covariance():
    from harness.self_map_csm import sample_segments
    wall = np.array([[[2., -2.], [2., 2.]]])
    prior = np.diag([.1, .3, .01])
    result = MomentMatcher().match([.05, 0., 0.], prior, sample_segments(wall), [0., 0.], wall, np.zeros((3, 3)))
    assert result['reason'] == 'accepted'
    assert np.array(result['covariance'])[1, 1] >= prior[1, 1]-1e-10
    assert 'posterior_moment_covariance' in result


def test_improved_proposal_informs_pose_and_uses_actual_density_ratio():
    class AnalyticCorner:
        def query(self, p):
            return np.minimum(abs(p[..., 0]-2.), abs(p[..., 1]-1.))
    from harness.self_map_csm import sample_segments
    prior, cov = np.array([.1, .1, 0.]), np.diag([.04, .04, .002])
    pose, increment, e = improved_proposal(AnalyticCorner(), sample_segments(CORNER), [0., 0.], prior, cov,
                                           np.random.default_rng(5), CSMOptions())
    assert e['reason'] == 'improved_proposal'
    assert np.linalg.norm(e['proposal_mean'][:2]) < np.linalg.norm(prior[:2])
    assert np.linalg.det(e['proposal_covariance']) < np.linalg.det(cov)
    assert np.isfinite(increment) and np.isfinite(pose).all()
    assert importance_increment(-3., prior, prior, cov, prior, cov) == pytest.approx(-3.)
    assert importance_increment(-3., prior, prior, cov, prior, cov*2) != pytest.approx(-3.)


def test_failed_proposal_is_motion_with_sensor_importance():
    class WrongMap:
        def query(self, p):
            return np.full(p.shape[:-1], 5.)
    _, increment, e = improved_proposal(WrongMap(), CORNER.reshape(-1, 2), [0., 0.], np.zeros(3), np.eye(3)*.01,
                                        np.random.default_rng(1), CSMOptions())
    assert e['reason'] == 'low_overlap' and e['proposal'] == 'motion_fallback'
    assert increment < 0.


def test_selective_resampling_copies_maps_and_preserves_history():
    grid = RaoBlackwellizedGrid('r1', settle_s=None)
    observe(grid, 0., 0)
    neff, indices = grid.resample_if_needed()
    assert neff == pytest.approx(30.) and indices is None
    grid.maps[0].cells[(99, 99)] = 2.
    grid.weights[:] = 0.
    grid.weights[0] = 1.
    neff, indices = grid.resample_if_needed()
    assert neff == 1. and indices == [0]*30
    assert len({id(g.cells) for g in grid.maps}) == 30
    grid.maps[0].cells[(99, 99)] = -2.
    assert grid.maps[1].cells[(99, 99)] == 2.
    grid.histories[0].append({'extra': True})
    assert len(grid.histories[0]) == len(grid.histories[1])+1
    assert np.all(grid.weights == 1/30)


@pytest.mark.parametrize('option', ['own_map_csm_prob_v1', 'own_map_rbpf_v1'])
def test_own_only_duplicate_and_settle_guards(option):
    m = SelfWallMemory('r1', self_map='odom_grid_v1', pose_correction=option,
                       self_map_options={'settle_s': None})
    g = m.self_map
    observe(g, 0., 0)
    frozen = json.dumps([g.export(), g.decisions])
    observe(g, 0., 0)
    assert json.dumps([g.export(), g.decisions]) == frozen
    with pytest.raises(ValueError, match='PEER_INPUT'):
        g.observe_contacts(t=1., frame_id=1, segments=CORNER, camera_xy=[0, 0], robot_id='r2')
    observe(g, .1, 1)
    assert g.decisions[-1]['status'] == 'deferred' and g.decisions[-1]['inserted']
    observe(g, 2., 2, np.array([[[4., 0.], [4., .1]]]))
    assert not g.decisions[-1]['inserted']


@pytest.mark.parametrize('option', [None, 'off', 'own_map_csm_v1', 'own_map_csm_v2'])
def test_all_previous_options_byte_identical(option):
    old = types.ModuleType('before_prob')
    exec((ROOT/'tests/fixtures/self_wall_memory_before_prob.py.txt').read_text(), old.__dict__)
    kwargs = {'self_map': 'odom_grid_v1', 'self_map_options': {'settle_s': None}, 'clock': lambda: 9.}
    if option is not None:
        kwargs['pose_correction'] = option
    a, b = old.SelfWallMemory('r1', **kwargs), SelfWallMemory('r1', **kwargs)
    for i in range(3):
        record = {'t_sim': float(i), 'view_index': i, 'posture': 'other', 'load': False,
                  'seg': [[math.hypot(*x), math.atan2(x[1], x[0]), math.hypot(*y), math.atan2(y[1], y[0]), None]
                          for x, y in CORNER]}
        for memory in (a, b):
            memory.command({'t': float(i), 'kind': 'drive', 'forward': .01, 'turn': .01, 'duration_s': .2})
            memory.observe_wall(record, camera_xy=[0., 0.], robot_id='r1')
        assert json.dumps(a.self_map.export()).encode() == json.dumps(b.self_map.export()).encode()
        assert json.dumps(a.snapshot()).encode() == json.dumps(b.snapshot()).encode()


def test_particle_count_and_resolution_are_fixed():
    with pytest.raises(ValueError, match='30_OR_100'):
        RaoBlackwellizedGrid('r1', correction_options={'particles': 50})
    with pytest.raises(ValueError, match='010M'):
        RaoBlackwellizedGrid('r1', resolution_m=.2)
    assert len(RaoBlackwellizedGrid('r1', correction_options={'particles': 100}).maps) == 100


def replay_module():
    import importlib.util
    path = ROOT/'experiments/2026-10-05-ego-wall-map-probe/code/own_map_prob_replay.py'
    spec = importlib.util.spec_from_file_location('prob_replay', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_particle_json_uses_native_scalar_types():
    module = replay_module()
    grid = RaoBlackwellizedGrid('r1', settle_s=None)
    observe(grid, 0., 0)
    payload = json.loads(json.dumps(module.particle_artifacts(grid), allow_nan=False))
    assert len(payload) == 30 and payload[0]['cells']


def test_evaluation_aligns_oracle_and_keeps_final_rejected_map_state(tmp_path, monkeypatch):
    module = replay_module()
    inputs = tmp_path/'inputs'
    inputs.mkdir()
    (inputs/'static_map.json').write_text(json.dumps({'obstacles': [
        {'kind': 'wall', 'center_m': [2., 0.], 'half_extents_m': [.05, 1.]}]}))
    monkeypatch.setattr(module.base, 'ground_truth', lambda *args: (np.array([0., 1., 2.]), np.zeros((3, 3))))
    poses = [{'t': float(t), 'pose': [0., 0., 0.]} for t in range(3)]
    obs = [{'t': 1., 'pose': [0., 0., 0.], 'camera': [0., 0.], 'segments': [[[2., -.5], [2., .5]]]}]
    states = [{'t': 0., 'occupied': []}, {'t': 1., 'occupied': [[2.05, 0.]]},
              {'t': 2., 'occupied': [[2.05, 0.], [10., 10.]]}]
    result, series = module.evaluate_prediction(tmp_path, 'r1', poses, obs, states)
    assert len(series) == 3
    assert series[1]['precision_015'] == 1.
    assert result['final']['occupied_cells'] == 2
    assert result['final']['precision_015'] == .5
