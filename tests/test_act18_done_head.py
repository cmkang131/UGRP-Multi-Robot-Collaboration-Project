"""act18-doneh: own-command-history features must match the offline probe exactly."""
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from act18_done_head import (FEATURE_SPEC, CommandFeatureState, apply_done_override, command_vector,
                             done_fires, padded_window, skill_onehot_vector, validate_metadata)
from act18_done_offline import command_features


def _action_stream(n=40, seed=7):
    rng = np.random.default_rng(seed)
    actions = np.zeros((n, 14), np.float32)
    actions[:, :4] = rng.choice([0.0, 0.35, -0.35], size=(n, 4))
    actions[:, 4:8] = np.where(actions[:, :4] != 0, 1.0, 0.0)
    actions[:, 8:13] = rng.uniform(-1, 1, size=(n, 5))
    actions[20:, 11] = 0.5   # gripper closes
    actions[20:, 12] = 0.7
    return actions


def test_streaming_features_match_offline_feature_extractor():
    actions = _action_stream()
    offline = command_features(actions)
    state = CommandFeatureState()
    streaming = np.stack([state.update(row) for row in actions])
    assert np.allclose(offline, streaming, atol=1e-4)


def test_command_vector_round_trips_encoded_action_semantics():
    command = dict(t=1.0, wheels=[0.35, 0.0, -0.35, 0.0], duration_s=[0.15, 0.0, 0.075, 0.0],
                   pwm={'1': 1700, '3': 1300, '4': 1500, '5': 2000, '6': 1000})
    encoded = command_vector(command)
    assert encoded.shape == (14,)
    assert encoded[0] == pytest.approx(0.35) and encoded[4] == pytest.approx(1.0)
    assert encoded[8] == pytest.approx(0.2) and encoded[12] == pytest.approx(-0.5)


def test_done_override_and_threshold_follow_frozen_semantics():
    command = dict(t=1.0, wheels=[0.35, 0.35, 0.35, 0.35], duration_s=[0.15]*4,
                   pwm={'1': 1500, '3': 1500, '4': 1500, '5': 1500, '6': 1500})
    assert done_fires(0.65) is True and done_fires(0.6499) is False
    stopped = apply_done_override(command, True)
    assert stopped['wheels'] == [0.0]*4 and stopped['duration_s'] == [0.0]*4
    assert apply_done_override(command, False) == command


def test_padded_window_keeps_newest_features_and_mask():
    rows = [np.full(18, i, np.float32) for i in range(3)]
    window, mask = padded_window(rows, 4)
    assert window.shape == (4, 18) and mask.tolist() == [0.0, 1.0, 1.0, 1.0]
    assert window[-1, 0] == 2.0


def test_metadata_requires_frozen_spec_hash_and_auc():
    meta = dict(schema='ugrp.act18.done_head.v1', feature_spec=FEATURE_SPEC,
                history=16, hidden=64, threshold=.65, persistence=1,
                skills=['grasp', 'wait', 'regrasp', 'release'],
                servos=['1', '3', '4', '5', '6'], source_sha='a'*40,
                dataset_manifest_sha256='b'*64, validation_auc=.99, model_sha256='c'*64)
    assert validate_metadata(meta, 'c'*64) is meta
    with pytest.raises(ValueError, match='threshold'):
        validate_metadata({**meta, 'threshold': .5}, 'c'*64)
    with pytest.raises(ValueError, match='model hash'):
        validate_metadata(meta, 'd'*64)
    with pytest.raises(ValueError, match='validation auc'):
        validate_metadata({**meta, 'validation_auc': .4}, 'c'*64)


def test_co_training_origin_token_dimensions():
    from act18_cotrain_data import ORIGIN_NATIVE, ORIGIN_V7, origin_token
    assert origin_token(ORIGIN_V7).tolist() == [1.0, 0.0]
    assert origin_token(ORIGIN_NATIVE).tolist() == [0.0, 1.0]
    assert origin_token(ORIGIN_V7, state_token=False).shape == (0,)
