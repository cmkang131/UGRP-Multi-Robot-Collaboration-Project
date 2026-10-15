"""Numerical and view-planning contracts only; no plant, render or GT."""
import math
import numpy as np
import pytest
from harness.active_relocalization import (OPTION, LOOK, prior_support, conditioned_modes,
    relative_candidates, ViewEvidence, next_view, validate)


def test_full_command_prior_wrap_and_incomplete_search_fail_closed():
    P = np.array([[1., .99, 0], [.99, 1., 0], [0, 0, .01]])
    keep, _ = prior_support([[1, -1, 0], [.1, .1, 0]], [0, 0, 0], P)
    assert keep.tolist() == [False, True]
    keep, _ = prior_support([[0, 0, -math.pi+.01]], [0, 0, math.pi-.01], np.eye(3)*.01)
    assert keep.all()
    poses = [[0, 0, 0], [2, 0, 0]]
    modes = conditioned_modes(poses, [0., 0.], [0, 0, 0], np.eye(3)*.01)
    assert not modes['ambiguous'] and modes['command_supported_N'] == 1
    assert conditioned_modes(poses, [0., 0.], [0, 0, 0], np.eye(3)*.01, complete=False)['ambiguous']
    assert conditioned_modes(poses, [0., 0.], [0, 0, 0], np.eye(3)*4)['ambiguous']


def test_relative_command_motion_and_independent_rgb_likelihood():
    now = [1, 2, math.pi/2]; past = [0, 2, 0]
    np.testing.assert_allclose(relative_candidates([now], now, past), [past], atol=1e-10)
    bank = ViewEvidence(); poses = np.array([[0., 0., 0.], [1., 0., 0.]])
    score = lambda p: -100*p[:, 0]**2
    bank.add([0, 0, 0], 0., 0., score)
    _, independent = bank.score(poses, [0, 0, 0], 1., 0., score)
    assert not independent
    scores, independent = bank.score(poses, [0, 0, 0], 1., .5, lambda p: np.zeros(len(p)))
    assert independent == [0.] and scores[0] > scores[1]+50
    assert not bank.score(poses, [0, 0, 0], 61., .5, score)[1]
    bank.add([0, 0, 0], 2., .5, score)
    bank.add([0, 0, 0], 3., 0., score)
    assert len(bank.frames)==2 and [f['t'] for f in bank.frames]==[2.,3.]


def test_map_nbv_uses_fixed_fk_limits_and_avoids_repeated_heading():
    from harness.active_camera import pitch
    static = dict(obstacles=[dict(kind='wall', center_m=[1.5, 0], half_extents_m=[.05, 2])],
                  regions={}, passages=[])
    P = np.diag([.02, .02, .01])
    view = next_view(static, [0, 0, 0], P)
    assert view['predicted_points'] > 0 and view['predicted_only']
    assert -8 < pitch(view['servo']) < -7
    assert all(500 <= p <= 2500 for p in view['servo'].values())
    other = next_view(static, [0, 0, 0], P, previous_headings=[view['heading_rad']])
    assert abs(float((other['heading_rad']-view['heading_rad']+math.pi)%(2*math.pi)-math.pi)) >= math.radians(20)
    assert view['motion'] == 'in_place_only'
    validate('off'); validate(OPTION)
    with pytest.raises(ValueError): validate(True)
