"""A-r1 DRAFT: history dither/dropout and release oversampling, default off (no training)."""
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import act18_carry_r1 as r1
from harness import grasp_act_contract as c


def command(t, pwm1=1500, wheel=0.):
    return {'t': t, 'wheels': [wheel, 0., 0., 0.], 'duration_s': [.1 if wheel else 0., 0., 0., 0.],
            'pwm': {str(s): (pwm1 + 7 * index if s == 1 else 1500 + index)
                    for index, s in enumerate(c.SERVOS)}}


def observation():
    issued = [command(round(10. - .1 * (15 - k), 6), pwm1=1500 + 20 * k, wheel=.35 if k % 2 else 0.)
              for k in range(c.HISTORY)]
    refs = [{'path': 'rgb/r1/%06d.jpg' % i, 'sha256': '%064x' % i, 't': 10. - lag, 'robot_id': 'r1'}
            for i, lag in enumerate(c.RGB_LAGS_S)]
    return {'schema': c.SCHEMA, 'robot_id': 'r1', 'sample_id': 'x:0:r1', 't': 10., 'skill': 'release',
            'object_kind': 'cyan', 'role': 'west', 'destination_zone': 'B', 'rgb': refs,
            'issued': issued, 'skill_elapsed_s': 1., 'pwm_elapsed_s': 2.}


def test_layout_matches_contract_context():
    obs = observation()
    state = np.asarray(c.context(obs), np.float32)
    assert len(state) == c.CONTEXT_DIM == r1.HISTORY * r1.ENTRY + 28
    values = state[r1.pwm_columns()].reshape(r1.HISTORY, r1.SERVOS)
    expected = [[(item['pwm'][str(s)] - 1500) / 1000 for s in c.SERVOS] for item in obs['issued']]
    assert np.allclose(values, expected)


def test_options_default_off_and_bounds():
    assert r1.validate_options() is False
    assert r1.validate_options(dither_max_pwm=6, dither_prob=.5) is True
    for bad in (dict(dither_max_pwm=0, dither_prob=.5), dict(dither_max_pwm=6),
                dict(dither_prob=.5), dict(dropout_prob=1.), dict(release_weight=.5)):
        with pytest.raises(ValueError):
            r1.validate_options(**bad)


def test_dither_touches_only_history_pwm_by_1_to_6():
    state = np.asarray(c.context(observation()), np.float32)
    out = r1.history_dither(state, np.random.default_rng(1), 6, 1.)
    changed = np.flatnonzero(~np.isclose(out, state))
    assert set(changed) <= set(r1.pwm_columns().tolist())
    delta = np.rint((out - state)[r1.pwm_columns()] * 1000)
    assert np.all((np.abs(delta) >= 1) & (np.abs(delta) <= 6))
    assert np.array_equal(r1.history_dither(state, np.random.default_rng(1), 6, 0.), state)
    assert state is not out


def test_dropout_repeat_pads_oldest_entries_and_keeps_ages():
    state = np.asarray(c.context(observation()), np.float32)
    rng = np.random.default_rng(3)
    out = r1.history_dropout(state, rng, .999999)
    entries = out[:r1.HISTORY * r1.ENTRY].reshape(r1.HISTORY, r1.ENTRY)
    original = state[:r1.HISTORY * r1.ENTRY].reshape(r1.HISTORY, r1.ENTRY)
    assert np.array_equal(entries[:, 13], original[:, 13])          # ages unchanged
    k = next(i for i in range(r1.HISTORY) if np.array_equal(entries[i], original[i]))
    assert k >= 1
    assert all(np.array_equal(entries[j, :13], original[k, :13]) for j in range(k))
    assert np.array_equal(entries[k:], original[k:])
    assert np.array_equal(out[r1.HISTORY * r1.ENTRY:], state[r1.HISTORY * r1.ENTRY:])
    assert np.array_equal(r1.history_dropout(state, rng, 1e-12), state)


def test_release_oversampling_weights_and_sampler_mass():
    from act18_policy import weighted_sampler_mass
    metadata = [dict(skill='grasp')] * 6 + [dict(skill='release')] * 2
    weights = r1.release_row_weights(metadata, 3.)
    assert weights.tolist() == [1.] * 6 + [3.] * 2
    assert r1.release_row_weights(metadata, None).tolist() == [1.] * 8
    mass = weighted_sampler_mass([np.arange(8)], weights)
    assert mass[6:].sum() == pytest.approx(.5)                   # 2 rows x 3 / 12


def test_dataset_sampler_and_augment_switch():
    import torch
    cls = r1.carry_dataset_class()
    data = cls.__new__(cls)
    data.episode_indices = [np.arange(4), np.arange(4, 8)]
    data.metadata = [dict(skill='grasp')] * 3 + [dict(skill='release')] + [dict(skill='grasp')] * 3 + [dict(skill='release')]
    data.row_weights = r1.release_row_weights(data.metadata, 20.)
    picks = data.sample(torch.Generator().manual_seed(0), 400, r1.SAMPLING)
    share = sum(data.metadata[i]['skill'] == 'release' for i in picks) / len(picks)
    assert share > .8                                             # 20/(3+20) per episode
    with pytest.raises(ValueError):
        data.sample(torch.Generator().manual_seed(0), 4, 'uniform_episode_v1')
    data.options = dict(dither_max_pwm=6, dither_prob=1., dropout_prob=None, release_weight=20.)
    data.rng = np.random.default_rng(0)
    state = np.asarray(c.context(observation()), np.float32)
    assert not np.array_equal(data.augment_raw_state(state), state)


def test_candidate_registered_as_init_pilot():
    import act18_policy as policy
    assert policy.CANDIDATES[r1.CANDIDATE] == 8
    assert r1.CANDIDATE in policy.PILOT_CANDIDATES and r1.KIND in policy.PILOT_KINDS
    import act18_train as train
    with pytest.raises(ValueError):
        train.validate_probe_options(r1.CANDIDATE, None, 10000, None, None)
    assert train.validate_probe_options(r1.CANDIDATE, Path('r8'), 10000, None, None) == 10000
