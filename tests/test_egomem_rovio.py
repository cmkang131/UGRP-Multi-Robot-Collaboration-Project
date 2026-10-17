"""Native upstream retention and relative EKF invariants; no sim/render."""
import math
from pathlib import Path

import numpy as np
import pytest

from harness.egocentric_landmark_memory import LandmarkMemory, MemoryOptions, OPTION, relative, observation_model
from harness.rovio_feature_statistics import PROFILE, RovioLibrary
from scripts.build_egomem_rovio_statistics import build


@pytest.fixture(scope='module')
def library(tmp_path_factory):
    path = tmp_path_factory.mktemp('rovio')/'statistics.so'
    build(path)
    return path


def observation(xy, name='blue'):
    return dict(id=name, kind='zone_corner', signature=name,
                relative_xy_m=xy, covariance_m2=(np.eye(2)*.04).tolist())


def memory(library, **kwargs):
    return LandmarkMemory(option=OPTION, options=MemoryOptions(
        implementation=PROFILE, statistics_library=str(library), **kwargs))


def test_native_upstream_visibility_and_global_quality(library):
    stats = RovioLibrary(library).create(0.)
    for time in range(1, 12):
        stats.observe(float(time), False)
        values = stats.values()
        # Header counts the current frame; initial status was TRACKED.
        assert values['local_quality'] == 1.
        assert values['local_visibility'] == pytest.approx(.99**time)
        assert values['global_quality'] == pytest.approx(.01)
        assert stats.good() == (values['local_visibility'] > .9-.1*.01)
    assert not stats.good()


def test_predict_update_matches_linear_gaussian_conditioning(library):
    m = memory(library)
    m.step(0., [0, 0, 0], np.zeros((3, 3)),
           [observation([2., 1.]), observation([-1., 2.], 'red')])
    old_x, old_p = m.x.copy(), m.p.copy()
    delta = np.array([.1, .2, .3]); q = np.diag([.01, .02, .03])
    augmented = np.r_[old_x, delta]
    jac = np.vstack([observation_model(augmented, i)[1] for i in range(2)])
    predicted = np.concatenate([relative(p, delta) for p in old_x.reshape(-1, 2)])
    joint = np.zeros((7, 7)); joint[:4, :4] = old_p; joint[4:, 4:] = q
    p = jac @ joint @ jac.T
    h = np.eye(4)[:2]; z = predicted[:2]+[.1, -.1]; r = np.eye(2)*.04
    gain = p @ h.T @ np.linalg.inv(h @ p @ h.T+r)
    expected = predicted+gain @ (z-h @ predicted)
    expected_p = p-gain @ h @ p
    m.step(1., delta, q, [observation(z.tolist())])
    assert np.allclose(m.x, expected)
    assert np.allclose(m.p, expected_p)
    assert not np.allclose(m.x[2:], predicted[2:])  # shared motion updates unseen red
    assert np.linalg.eigvalsh(m.p).min() > 0


def test_only_observation_ticks_age_upstream_and_delete(library):
    m = memory(library)
    m.step(0., [0, 0, 0], np.zeros((3, 3)), [observation([2, 0])])
    for i in range(1, 51):
        m.step(i/10, [0, 0, 0], np.zeros((3, 3)), observation_tick=False)
    assert m.snapshot(5.)[0]['freshness'] == 1.
    reasons = []
    for i in range(6, 17):
        result = m.step(float(i), [0, 0, 0], np.zeros((3, 3)))
        reasons.extend(e['reason'] for e in result['events'])
    assert not m.items and 'rovio_quality_removed' in reasons


def test_upstream_reserve_replaces_lru_and_excess_is_recorded(library):
    m = memory(library, max_landmarks=4)
    initial = [observation([i+1, 0], str(i)) for i in range(5)]
    result = m.step(0., [0, 0, 0], np.zeros((3, 3)), initial)
    assert len(m.items) == 4
    assert sum(e['reason']=='rovio_no_free_slot' for e in result['events']) == 1
    result = m.step(1., [0, 0, 0], np.zeros((3, 3)))
    assert len(m.items) <= 1  # int(4*.75) free slots, no tracked features
    assert any(e['reason']=='rovio_reserve_removed' for e in result['events'])
    assert not any(e['reason']=='memory_slot_evicted' for e in result['events'])


def test_opt_in_requires_library_and_rejects_custom_fade(library):
    with pytest.raises(ValueError, match='EXPLICIT_ROVIO_LIBRARY'):
        LandmarkMemory(option=OPTION, options=MemoryOptions(implementation=PROFILE))
    with pytest.raises(ValueError, match='REPLACES_CUSTOM_FADE'):
        memory(library, fade_tau_s=10.)
    assert LandmarkMemory().step(0., [0, 0, 0], np.zeros((3, 3)))['status']=='off'
    m = memory(library)
    with pytest.raises(ValueError, match='UNEXPECTED_OBSERVATION'):
        m.step(0., [0, 0, 0], np.zeros((3, 3)),
               [{**observation([1, 0]), 'spawn': [1, 2]}])
