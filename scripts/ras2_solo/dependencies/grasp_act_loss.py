"""Opt-in completion classification; keep the pinned upstream ACT forward/KL.

The legacy 14th action is normalized L1 regression, not a probability. The
candidate replaces only that term with class-balanced BCE on a logit. Priors
come from unique TRAIN rows, never validation or repeated chunk horizons.
"""
import math

import numpy as np

from harness import grasp_act_contract as c

DONE_MODES = ('legacy_l1', 'balanced_bce_v1')


def completion_priors(data):
    counts = {skill: [0, 0] for skill in c.SKILLS}
    for shard in data.shards:
        for state, action in zip(shard['state'], shard['action'][:, 0]):
            task = state[c.HISTORY * 14:c.HISTORY * 14 + len(c.SKILLS)]
            if not np.isin(task, [0., 1.]).all() or task.sum() != 1:
                raise ValueError('one-hot skill required for completion weighting')
            if action[-1] not in (0., 1.):
                raise ValueError('binary completion targets required')
            count = counts[c.SKILLS[int(task.argmax())]]
            count[0] += int(action[-1]); count[1] += 1
    if any(total and not 0 < n < total for n, total in counts.values()):
        raise ValueError('both TRAIN completion classes required per skill')
    return {skill: {'positive_n': n, 'rows_N': total, 'positive_fraction': n / total}
            for skill, (n, total) in counts.items() if total and 0 < n < total}


def policy_loss(policy, batch, *, mode='legacy_l1', stats=None, priors=None, weight=1.):
    if mode not in DONE_MODES or not math.isfinite(weight) or weight <= 0:
        raise ValueError('invalid completion loss option')
    if mode == 'legacy_l1':
        return policy(batch)
    import torch
    import torch.nn.functional as F
    # Observe the SAME upstream forward, without a second VAE sample or a copy
    # of its implementation. Remove the old completion L1 algebraically.
    captured = []
    hook = policy.model.register_forward_hook(lambda module, args, output: captured.append(output[0]))
    try:
        loss, metrics = policy(batch)
    finally:
        hook.remove()
    if len(captured) != 1:
        raise ValueError('expected one upstream ACT forward')
    prediction = captured[0]
    valid = ~batch['action_is_pad']
    target = batch['action'][..., -1] * stats['action_std'][-1] + stats['action_mean'][-1]
    if (not valid.any() or not torch.all(torch.isclose(target[valid], target[valid].round(), atol=1e-5))
            or not torch.all((target[valid] >= -1e-5) & (target[valid] <= 1+1e-5))):
        raise ValueError('nonempty binary completion targets required')
    target = target.round().clamp(0, 1)
    task = batch['observation.state'][:, c.HISTORY * 14:c.HISTORY * 14 + len(c.SKILLS)]
    if not torch.all((task == 0) | (task == 1)) or not torch.all(task.sum(-1) == 1):
        raise ValueError('one-hot skill required')
    fractions = []
    for index in task.argmax(-1).tolist():
        prior = (priors or {}).get(c.SKILLS[index], {}).get('positive_fraction', 0.)
        if not 0 < prior < 1:
            raise ValueError('both TRAIN completion classes required per skill')
        fractions.append(prior)
    prior = target.new_tensor(fractions)[:, None]
    class_weight = torch.where(target.bool(), .5 / prior, .5 / (1 - prior))
    bce = F.binary_cross_entropy_with_logits(prediction[..., -1], target, reduction='none')
    done_loss = (bce * class_weight)[valid].mean()
    old_done = (prediction[..., -1] - batch['action'][..., -1]).abs()[valid].mean() / c.ACTION_DIM
    loss = loss - old_done + weight * done_loss
    return loss, {'legacy_l1_loss': metrics['l1_loss'],
                  'movement_l1_loss': metrics['l1_loss'] - old_done.detach().item(),
                  'done_bce_loss': done_loss.detach().item(),
                  **{k: v for k, v in metrics.items() if k != 'l1_loss'}}
