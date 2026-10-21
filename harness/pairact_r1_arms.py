"""pairact-r1 training arms F and N on the same collected data (t5-architecture-advice.md).

``harness/pairact_r1.py`` is a collection-frozen file (``harness.pairact_collect.COLLECTOR_FILES``,
RUN_MANIFEST ``file_sha256``), so the arm logic lives here and wraps it without changing it.

- arm F (``full_v1``): every segment, "학습 전 구간". The original config file has no ``arm`` key.
- arm N (``near_only_v1``): "학습 근거리 + 코드 운반(hybrid)". Rows whose stage target is
  ``carry`` (teacher ``carry:carry_hold`` .. ``carry:zone_settle``: carry and door passage) get
  sampler weight 0, and carry horizon entries of the remaining rows are masked like padding, so
  they leave the action, done and stage losses (all three key off ``action_is_pad``).
  Everything else (steps, seed, sampler, history augmentation, lr, ...) equals arm F;
  ``assert_arm_pair`` refuses any other difference.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from harness import pairact_r1 as p

ARM_SCOPE = {'F': 'full_v1', 'N': 'near_only_v1'}
NEAR_EXCLUDED_STAGES = ('carry',)
# Keys that may differ between the arm F and arm N config files (everything else must match).
ARM_FREE_KEYS = ('schema', 'status', 'arm', 'segment_scope', 'notes', 'written')


def config_arm(config):
    """Arm id; the original draft file has no ``arm`` key and is arm F."""
    arm = config.get('arm', 'F')
    if arm not in ARM_SCOPE:
        raise ValueError(f'unknown pairact-r1 arm {arm!r}')
    return arm


def segment_scope(config):
    scope = config.get('segment_scope', 'full_v1')
    if scope not in ARM_SCOPE.values():
        raise ValueError(f'unknown segment scope {scope!r}')
    return scope


def validate_config(config):
    p.validate_config(config)
    arm, scope = config_arm(config), segment_scope(config)
    if ARM_SCOPE[arm] != scope:
        raise ValueError(f'arm {arm} is registered with segment scope {ARM_SCOPE[arm]}')
    return config


def load_config(path):
    return validate_config(json.loads(Path(path).read_text()))


def assert_arm_pair(full, near):
    """Arm N differs from arm F only in arm/segment_scope (same seed, steps, sampling, ...)."""
    validate_config(full), validate_config(near)
    if (config_arm(full), config_arm(near)) != ('F', 'N'):
        raise ValueError('expected one arm F and one arm N config')
    keys = (set(full) | set(near)) - set(ARM_FREE_KEYS)
    diff = sorted(k for k in keys if full.get(k) != near.get(k))
    if diff:
        raise ValueError(f'arm N must reuse arm F hyperparameters; differs in {diff}')
    return True


def near_only_keep(target):
    """(rows, CHUNK) stage targets -> bool mask of horizon entries arm N trains on."""
    target = np.asarray(target)
    excluded = [p.stage_index(s) for s in NEAR_EXCLUDED_STAGES]
    return (target != p.PAD) & ~np.isin(target, excluded)


def scoped_row_weights(weights, h0_targets, scope):
    """Sampler mass under the arm's segment scope: arm N never samples an h0 carry row."""
    weights = np.asarray(weights, float)
    if scope == 'full_v1':
        return weights
    if scope != 'near_only_v1':
        raise ValueError(f'unknown segment scope {scope!r}')
    return weights * near_only_keep(np.asarray(h0_targets)[:, None])[:, 0]


def pair_dataset_class():
    """pairact_r1.PairActDataset + segment scope (TRAIN only)."""
    base = p.pair_dataset_class()

    class ArmDataset(base):
        def __init__(self, root, split, *, scope='full_v1', **kwargs):
            if scope not in ARM_SCOPE.values():
                raise ValueError(f'unknown segment scope {scope!r}')
            if split != 'train' and scope != 'full_v1':
                raise ValueError('segment scope is TRAIN only (validation rows are scored by offline_metrics)')
            super().__init__(root, split, **kwargs)
            self.scope = scope
            h0 = np.concatenate([t[:, 0] for t in self.targets])
            self.row_weights = scoped_row_weights(self.row_weights, h0, scope)
            if not self.row_weights.any():
                raise ValueError('no trainable rows under the segment scope')

        def sample(self, generator, batch_size):
            if self.scope == 'full_v1':
                return super().sample(generator, batch_size)
            import torch
            weights = torch.from_numpy(self.row_weights)
            return torch.multinomial(weights, batch_size, replacement=True, generator=generator).tolist()

        def __getitem__(self, index):
            batch = super().__getitem__(index)
            if self.scope == 'near_only_v1':
                keep = near_only_keep(batch['stage_target'][None])[0]
                batch['action_is_pad'] = ~keep
                batch['stage_target'][~keep] = p.PAD
            return batch

    return ArmDataset


def offline_metrics(pred, target, segments, done_score, done_target, *, scope='full_v1'):
    """pairact_r1.offline_metrics under the arm scope.

    near_only_v1: carry rows are run by code at evaluation, so per-stage accuracy, premature
    stage rates and done rates are computed without them. The registered transitions are still
    measured on the full sequence: carry->place hits are predictions on the first place rows,
    i.e. the hand-back point. Thresholds (pairact_r1.GATE) are the same for both arms."""
    full = p.offline_metrics(pred, target, segments, done_score, done_target)
    if scope == 'full_v1':
        return dict(full, scored_rows=full['rows'], segment_scope=scope)
    if scope != 'near_only_v1':
        raise ValueError(f'unknown segment scope {scope!r}')
    keep = near_only_keep(np.asarray(target)[:, None])[:, 0]
    if not keep.any():
        raise ValueError('no near-field rows to score')
    pick = lambda xs: [x for x, k in zip(xs, keep) if k]
    near = p.offline_metrics(pick(pred), pick(target), pick(segments), pick(done_score), pick(done_target))
    return dict(near, rows=full['rows'], scored_rows=int(keep.sum()), segment_scope=scope,
                transitions=full['transitions'])
