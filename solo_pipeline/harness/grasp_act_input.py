"""Opt-in training regularizer for issued-command history, never a controller.

Drop an entire sample's normalized history to its TRAIN mean. Preserve task
tokens/clocks, RGB, actions and padding. Inference always uses real own history.
No inverted-dropout scaling: the retained histories keep their original scale.
"""
import math

from harness import grasp_act_contract as c


def validate_history_dropout(probability):
    if (isinstance(probability, bool) or not isinstance(probability, (int, float))
            or not math.isfinite(probability) or not 0 <= probability <= 1):
        raise ValueError('command history dropout must be finite in [0, 1]')
    return float(probability)


def drop_command_history(batch, probability=0.):
    probability = validate_history_dropout(probability)
    if probability == 0.:
        return batch  # Byte-identical default, including RNG state.
    import torch
    state = batch['observation.state']
    if state.ndim != 2 or state.shape[-1] != c.CONTEXT_DIM:
        raise ValueError('batched normalized ACT state required')
    # Uses the device RNG already saved/restored in train_grasp_act checkpoints.
    dropped = torch.rand((state.shape[0],), device=state.device) < probability
    changed = state.clone()
    changed[dropped, :c.HISTORY*14] = 0.
    return {**batch, 'observation.state': changed}
