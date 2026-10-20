"""A-r1 DRAFT (carry plan D, H-A1): history-robust R8 fine-tune options. Default OFF.

Not executed. Three training-side changes, each off unless explicitly set:

1. history dither: add integer +-1..6 PWM to the own issued-PWM history entries of
   ``observation.state`` (the student's closed-loop dither that the teacher data
   never contains). Targets stay the clean teacher command.
2. history dropout: with probability p, the oldest k (1..15) history entries take the
   command content of entry k (repeat padding, the same form OwnHistory uses at an
   episode start); ages are kept.
3. release oversampling: episode-uniform sampling, rows of the release skill weighted
   ``release_weight`` within their episode.

The state is the raw contract context (``harness.grasp_act_contract.context``):
16 entries x [4 wheels, 4 pulse/0.15, 5 (pwm-1500)/1000, age] followed by task
one-hots and the two clocks. Augmentation is applied to the raw state before the
frozen normalisation. Only own issued-command history is touched.
"""
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ENTRY = 14
HISTORY = 16
PWM_OFFSET = 8
SERVOS = 5
COMMAND_SLICE = slice(0, 13)        # wheels, pulse widths, PWMs (age at 13 excluded)
CANDIDATE = 'act18-carry-r1'
KIND = 'carry_history_robust_finetune_v1'
SAMPLING = 'carry_release_weighted_v1'
REGISTERED = dict(dither_max_pwm=6, dither_prob=.5, dropout_prob=.1, release_weight=3.,
                  steps=10000, seed=20261017)


def validate_options(*, dither_max_pwm=None, dither_prob=None, dropout_prob=None,
                     release_weight=None):
    """None everywhere = off. Bounds only; registered values live in the config draft."""
    if dither_max_pwm is not None:
        if type(dither_max_pwm) is not int or not 1 <= dither_max_pwm <= 9:
            raise ValueError('history dither max PWM must be an integer in [1, 9]')
        if dither_prob is None or not 0 < dither_prob <= 1:
            raise ValueError('history dither needs a probability in (0, 1]')
    elif dither_prob is not None:
        raise ValueError('--history-dither-prob requires --history-dither-pwm')
    if dropout_prob is not None and not 0 < dropout_prob < 1:
        raise ValueError('history dropout probability must be in (0, 1)')
    if release_weight is not None and not 1 <= release_weight <= 20:
        raise ValueError('release weight must be within [1, 20]')
    return any(value is not None for value in (dither_max_pwm, dropout_prob, release_weight))


def pwm_columns():
    """Raw-state columns of the 16 x 5 issued-PWM history values."""
    return np.array([entry * ENTRY + PWM_OFFSET + servo
                     for entry in range(HISTORY) for servo in range(SERVOS)], dtype=np.int64)


def history_dither(state, rng, max_pwm, prob):
    """+-1..max_pwm integer PWM on each history PWM value with probability ``prob``.

    PWM stays inside the contract range [500, 2500]."""
    out = np.array(state, dtype=np.float32, copy=True)
    columns = pwm_columns()
    mask = rng.random(len(columns)) < prob
    steps = rng.integers(1, max_pwm + 1, size=len(columns)) * rng.choice((-1, 1), size=len(columns))
    pwm = np.rint(out[columns] * 1000. + 1500.)
    pwm = np.clip(pwm + np.where(mask, steps, 0), 500, 2500)
    out[columns] = ((pwm - 1500.) / 1000.).astype(np.float32)
    return out


def history_dropout(state, rng, prob):
    """With probability ``prob``: entries 0..k-1 := command content of entry k."""
    out = np.array(state, dtype=np.float32, copy=True)
    if rng.random() >= prob:
        return out
    k = int(rng.integers(1, HISTORY))
    keep = out[k * ENTRY:k * ENTRY + ENTRY][COMMAND_SLICE].copy()
    for entry in range(k):
        out[entry * ENTRY:entry * ENTRY + 13] = keep
    return out


def release_row_weights(metadata, release_weight):
    weights = np.ones(len(metadata), dtype=np.float64)
    if release_weight is None:
        return weights
    for index, row in enumerate(metadata):
        if row['skill'] == 'release':
            weights[index] = float(release_weight)
    return weights


def carry_dataset_class():
    """Lazily built so the module imports without the training stack."""
    from act18_policy import ReferenceDataset, weighted_sampler_mass

    class CarryR1Dataset(ReferenceDataset):
        """R8-view TRAIN data with default-off history augmentation and release weights.

        ``augment`` starts False so the train/deployment transform identity check in
        act18_train.py sees the unmodified row; the trainer enables it afterwards.
        """
        def __init__(self, root, split, *, chunk=8, seed, dither_max_pwm=None, dither_prob=None,
                     dropout_prob=None, release_weight=None):
            super().__init__(root, split, chunk=chunk)
            validate_options(dither_max_pwm=dither_max_pwm, dither_prob=dither_prob,
                             dropout_prob=dropout_prob, release_weight=release_weight)
            if self.split != 'train':
                raise ValueError('carry-r1 augmentation is TRAIN only')
            self.options = dict(dither_max_pwm=dither_max_pwm, dither_prob=dither_prob,
                                dropout_prob=dropout_prob, release_weight=release_weight)
            self.rng = np.random.default_rng(seed)
            self.augment = False
            self.row_weights = release_row_weights(self.metadata, release_weight)
            weighted_sampler_mass(self.episode_indices, self.row_weights)

        def augment_raw_state(self, raw):
            if self.options['dither_max_pwm'] is not None:
                raw = history_dither(raw, self.rng, self.options['dither_max_pwm'],
                                     self.options['dither_prob'])
            if self.options['dropout_prob'] is not None:
                raw = history_dropout(raw, self.rng, self.options['dropout_prob'])
            return raw

        def __getitem__(self, index):
            batch = super().__getitem__(index)
            if self.augment:
                shard, row = self.index[index]
                raw = self.augment_raw_state(self.shards[shard]['state'][row])
                batch['observation.state'] = ((raw - np.asarray(self.stats['state_mean'], np.float32))
                                              / np.asarray(self.stats['state_std'], np.float32))
            return batch

        def sample(self, generator, batch_size, sampling):
            import torch
            if sampling != SAMPLING:
                raise ValueError('declared carry-r1 sampler required')
            selected = torch.randint(len(self.episode_indices), (batch_size,), generator=generator).tolist()
            picks = []
            for episode in selected:
                indices = self.episode_indices[episode]
                weights = torch.from_numpy(self.row_weights[indices].copy())
                picks.append(int(indices[int(torch.multinomial(weights, 1, generator=generator))]))
            return picks

        def completion_priors(self, sampling):
            from harness import grasp_act_contract as c
            if sampling != SAMPLING:
                raise ValueError('declared carry-r1 sampler required')
            mass = weighted_sampler_mass(self.episode_indices, self.row_weights)
            totals = {skill: dict(mass=0., positive_mass=0., positive_n=0, rows_N=0) for skill in c.SKILLS}
            for index, (shard, row) in enumerate(self.index):
                value = totals[self.metadata[index]['skill']]
                positive = float(self.shards[shard]['action'][row, 0, -1])
                if positive not in (0., 1.):
                    raise ValueError('binary TRAIN completion required')
                value['mass'] += float(mass[index])
                value['positive_mass'] += float(mass[index]) * positive
                value['positive_n'] += int(positive)
                value['rows_N'] += 1
            return {skill: {**value, 'positive_fraction': value['positive_mass'] / value['mass'],
                            'source': 'TRAIN h0 labels under the carry-r1 release-weighted sampler'}
                    for skill, value in totals.items()
                    if value['rows_N'] and 0 < value['positive_mass'] < value['mass']}

    return CarryR1Dataset
