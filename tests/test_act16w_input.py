"""Causal input boundary, not GPU training or physical success."""
import numpy as np
import pytest

from scripts.act16w_input import HISTORY_END, MASK_COLUMNS, transform_batch, transform_state


def test_baseline_is_identity_and_does_not_advance_rng():
    state = np.arange(252, dtype=np.float32)
    batch = {"observation.state": state, "observation.images.own": object()}
    old = np.random.get_state()
    assert transform_batch(batch) is batch
    assert transform_state(state) is state
    new = np.random.get_state()
    assert old[0] == new[0] and np.array_equal(old[1], new[1]) and old[2:] == new[2:]


def test_intervention_blocks_all_wheel_pulse_lags_and_preserves_every_other_input():
    state = np.arange(504, dtype=np.float32).reshape(2, 252) + 1
    raw = state.copy()
    result = transform_state(state, "wheel_pulse_train_mean")
    keep = sorted(set(range(252)) - set(MASK_COLUMNS))
    assert np.all(result[:, MASK_COLUMNS] == 0)
    assert np.array_equal(result[:, keep], raw[:, keep])
    assert np.array_equal(state, raw)
    assert len(MASK_COLUMNS) == 128
    # Latest issued PWM, age, task and clocks are preserved as well.
    assert np.array_equal(result[:, HISTORY_END-6:], raw[:, HISTORY_END-6:])


def test_training_and_unbatched_inference_apply_identical_intervention():
    state = np.linspace(-1, 1, 252, dtype=np.float32)
    batch = {"observation.state": state[None], "action": object(), "action_is_pad": object(),
             "observation.images.own": object()}
    train = transform_batch(batch, "wheel_pulse_train_mean")
    inference = transform_state(state, "wheel_pulse_train_mean")
    assert np.array_equal(train['observation.state'][0], inference)
    for k in batch.keys() - {'observation.state'}:
        assert train[k] is batch[k]


def test_invalid_mode_or_context_rejected():
    with pytest.raises(ValueError):
        transform_state(np.zeros(252), "all_state")
    with pytest.raises(ValueError):
        transform_state(np.zeros(HISTORY_END), "wheel_pulse_train_mean")


def test_torch_uses_same_columns_if_installed():
    torch = pytest.importorskip('torch')
    state = np.arange(252, dtype=np.float32)
    assert np.array_equal(transform_state(state, "wheel_pulse_train_mean"),
                          transform_state(torch.from_numpy(state), "wheel_pulse_train_mean").numpy())
