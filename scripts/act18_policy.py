"""Opt-in reference ACT configurations; own RGB/issued-state input unchanged.

The 100-step chunk and 100k schedule come from pinned LeRobot defaults.
Both candidates retain the existing completion head as an explicit task adapter.
No teacher, evaluator, world pose or measured joint enters this module.
"""
from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from act16w_runtime import LEROBOT_ACT_SHA256, sha256
from act17_data import Dataset, library
from act17_policy import observation_batch

# TUNE is a default-off short fine-tune probe: same chunk8 R8 recipe, initialized
# from the completed R8 100k checkpoint and optionally upweighting the
# align..close demonstration segments. It is never a packaged comparison model
# (adapter training_complete stays False because its step != protocol steps).
CANDIDATES = {'R8': 8, 'R100': 100, 'act18-tune': 8, 'act18-doneb1': 100,
              'act18-std': 20, 'act18-b3': 20}
TUNE_CANDIDATE = 'act18-tune'
# Registered short pilot checkpoints (never 100k reference models, never packaged):
# 'act18-tune' = post-close weighted 2k probe on R8; 'act18-doneb1' = done-only
# 5k probe on R100 (pre-registered 2026-10-18 for Lead-approved B1).
PILOT_CANDIDATES = ('act18-tune', 'act18-doneb1', 'act18-std', 'act18-b3')
PILOT_KINDS = ('init_aligned_finetune_v1', 'done_positive_balanced_finetune_v1',
               'standard_aligned_scratch_v1', 'done_horizon_current_only_v1')
# Segment table frozen before the probe run (Lead 2026-10-18 instruction):
# the post-close phases are where the student halts, pre-close phases are the
# immediately preceding approach/alignment tail. Phase labels are the recorded
# teacher labels from samples.json, not a new sensor or truth input.
POST_CLOSE_PHASES = ('lift', 'lift_settle', 'lookback_pose', 'lookback',
                     'lookback_settle', 'verify_lift', 'hold')
PRE_CLOSE_PHASES = ('hover', 'descent', 'close')


def _segment_weight(value, label):
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 1 <= value <= 20:
        raise ValueError(label+' must be a number within [1, 20]')
    return float(value)


def align_close_row_weights(metadata, post_close_weight=None, pre_close_weight=None):
    """Per-row sampling weight: 1.0 baseline, post-close/pre-close upweights."""
    post = _segment_weight(post_close_weight, 'post-close weight')
    pre = _segment_weight(pre_close_weight, 'pre-close weight')
    weights = np.ones(len(metadata), dtype=np.float64)
    if post is None and pre is None:
        return weights
    for index, row in enumerate(metadata):
        phase = row.get('teacher_phase')
        if post is not None and row['stage'] == 'grasp' and phase in POST_CLOSE_PHASES:
            weights[index] = post
        elif pre is not None and row['stage'] == 'grasp' and phase in PRE_CLOSE_PHASES:
            weights[index] = pre
    return weights


def weighted_sampler_mass(episode_indices, row_weights):
    """Probability mass per row for episode-uniform, weight-within-episode sampling."""
    row_weights = np.asarray(row_weights, dtype=np.float64)
    if row_weights.shape != (sum(len(indices) for indices in episode_indices),):
        raise ValueError('row weights must cover every episode row exactly once')
    if not np.all(np.isfinite(row_weights)) or np.any(row_weights <= 0):
        raise ValueError('positive finite row weights required')
    mass = np.zeros(len(row_weights), dtype=np.float64)
    for indices in episode_indices:
        weights = row_weights[indices]
        mass[indices] = (weights / weights.sum()) / len(episode_indices)
    if abs(mass.sum() - 1.0) > 1e-9:
        raise ValueError('sampler mass must sum to one')
    return mass


def extend_targets(actions, metadata, chunk, done_horizon='all'):
    """Reconstruct future labels from original h0, within the same skill only.

    done_horizon='current_only' keeps the completion target only at the chunk
    row that corresponds to the observation itself (h=0). B1 showed the learned
    done mass sits at far horizons (h≈99) while execution reads h=0, so this
    candidate isolates the horizon-contract hypothesis.
    """
    if done_horizon not in ('all', 'current_only'):
        raise ValueError('done_horizon must be all or current_only')
    actions = np.asarray(actions)
    out = np.zeros((len(actions), chunk, actions.shape[-1]), dtype=np.float32)
    pad = np.ones((len(actions), chunk), dtype=bool)
    for i, origin in enumerate(metadata):
        for h in range(chunk):
            j = i+h
            if j >= len(actions):
                break
            other = metadata[j]
            if (other['sample_id'].split(':')[0] != origin['sample_id'].split(':')[0]
                    or other['skill'] != origin['skill']
                    or abs(other['t']-origin['t']-.1*h) > 1e-5):
                break
            out[i, h], pad[i, h] = actions[j], False
            if actions[j, -1] == 1:
                break
    if done_horizon == 'current_only':
        out[:, 1:, -1] = 0.
    return out, pad


class ReferenceDataset(Dataset):
    # First eight encoded action dims are the base command (wheel magnitude x4 +
    # pulse duration x4); act-plus-plus applies a 5-sample moving average to the
    # mobile base action at data-load time (utils.preprocess_base_action). The
    # optional window keeps that standard alignment toggle default OFF.
    BASE_ACTION_DIMS = 8

    def __init__(self, root, split, *, chunk=8, base_smooth_window=None, done_horizon='all'):
        super().__init__(root, split, image_mode='current_full_v1')
        if chunk not in CANDIDATES.values():
            raise ValueError('registered ACT chunk required')
        if base_smooth_window is not None and (type(base_smooth_window) is not int or base_smooth_window < 1):
            raise ValueError('base_smooth_window must be a positive integer')
        self.chunk = chunk
        self.base_smooth_window = base_smooth_window
        offset = 0
        for shard in self.shards:
            n = len(shard['state'])
            raw = shard['action'][:, 0]
            if base_smooth_window is not None and base_smooth_window > 1:
                kernel = np.ones(base_smooth_window, dtype=np.float64) / base_smooth_window
                smoothed = np.array(raw, dtype=np.float64, copy=True)
                for column in range(self.BASE_ACTION_DIMS):
                    smoothed[:, column] = np.convolve(raw[:, column], kernel, mode='same')
                target_source = smoothed.astype(np.float32)
            else:
                target_source = raw
            actions, pad = extend_targets(target_source, self.metadata[offset:offset+n], chunk,
                                          done_horizon=done_horizon)
            # This is a new view over existing successful v7 recordings. Verify
            # byte-exact parity with all original horizons that still exist.
            common = min(chunk, shard['action'].shape[1])
            # done_horizon='current_only' intentionally clears the completion
            # column for h>0, so parity covers only the untouched columns.
            kept = shard['action'].shape[-1] - 1 if done_horizon == 'current_only' else shard['action'].shape[-1]
            if base_smooth_window is None:
                if (not np.array_equal(actions[:, :common, :kept], shard['action'][:, :common, :kept])
                        or not np.array_equal(pad[:, :common], shard['action_is_pad'][:, :common])):
                    raise ValueError('reconstructed future targets differ from original chunk8')
            elif not np.array_equal(actions[:, :common, self.BASE_ACTION_DIMS:kept],
                                    shard['action'][:, :common, self.BASE_ACTION_DIMS:kept]):
                raise ValueError('smoothed base action changed non-base targets')
            shard['action'], shard['action_is_pad'] = actions, pad
            offset += n


def registered_pilot_checkpoint(provenance, protocol_sha256):
    """True only for the default-off short TUNE probe checkpoint (not a 100k model).

    The probe completes its own short schedule, so training_complete is True for
    that schedule. Packaging stays impossible because the packaging script also
    requires provenance.step == protocol steps (100000) and an explicit
    packaging_eligible flag.
    """
    probe = provenance.get('probe') or {}
    step = provenance.get('step')
    receipt = probe.get('init_checkpoint')
    if receipt is not None and (not isinstance(receipt.get('model_sha256'), str)
                                or len(receipt['model_sha256']) != 64):
        return False
    candidate = provenance.get('candidate')
    kind = probe.get('kind')
    init_kinds = ('init_aligned_finetune_v1', 'done_positive_balanced_finetune_v1',
                  'done_horizon_current_only_v1')
    if kind in init_kinds and not isinstance(receipt, dict):
        # B2 was trained from scratch with the done fix and predates the
        # standard-scratch kind label; its standard flags still register it.
        if not (candidate == 'act18-std' and (probe.get('val_select') or probe.get('base_smooth_window'))):
            return False
    if kind == 'standard_aligned_scratch_v1' and candidate != 'act18-std':
        return False
    return bool(candidate in PILOT_CANDIDATES
                and kind in PILOT_KINDS
                and provenance.get('training_complete') is True
                and probe.get('packaging_eligible') is False
                and type(step) is int and step == probe.get('steps_override') and 1 <= step <= 20000
                and provenance.get('protocol_sha256') == protocol_sha256)


def done_positive_indices(data):
    """Global dataset indices whose first-step completion target is 1 (raw label)."""
    indices = []
    for index, (shard, row) in enumerate(data.index):
        value = float(data.shards[shard]['action'][row, 0, -1])
        if value not in (0.0, 1.0):
            raise ValueError('binary TRAIN completion target required')
        if value == 1.0:
            indices.append(index)
    if not indices:
        raise ValueError('at least one positive completion row required')
    return np.asarray(indices, dtype=np.int64)


class WeightedReferenceDataset(ReferenceDataset):
    """TUNE-only episode-balanced sampling with post-close/pre-close upweighting."""

    def __init__(self, root, split, *, chunk=8, post_close_weight=None, pre_close_weight=None):
        super().__init__(root, split, chunk=chunk)
        if self.split != 'train' or (post_close_weight is None and pre_close_weight is None):
            raise ValueError('weighted TRAIN sampling with explicit upweights required')
        self.row_weights = align_close_row_weights(self.metadata, post_close_weight, pre_close_weight)
        weighted_sampler_mass(self.episode_indices, self.row_weights)

    def sample(self, generator, batch_size, sampling):
        import torch
        if sampling != 'weighted_post_close_v1':
            raise ValueError('declared weighted sampler required')
        if self.split != 'train':
            raise ValueError('only TRAIN sampling is permitted')
        selected = torch.randint(len(self.episode_indices), (batch_size,), generator=generator).tolist()
        picks = []
        for episode in selected:
            indices = self.episode_indices[episode]
            weights = torch.from_numpy(self.row_weights[indices].copy())
            picks.append(int(indices[int(torch.multinomial(weights, 1, generator=generator))]))
        return picks

    def completion_priors(self, sampling):
        """Class fractions under the exact weighted sampling measure, not VAL."""
        from harness import grasp_act_contract as c
        if sampling != 'weighted_post_close_v1' or self.split != 'train':
            raise ValueError('declared weighted TRAIN sampler required')
        mass = weighted_sampler_mass(self.episode_indices, self.row_weights)
        totals = {skill: dict(mass=0., positive_mass=0., positive_n=0, rows_N=0) for skill in c.SKILLS}
        for index, (shard, row) in enumerate(self.index):
            skill = self.metadata[index]['skill']
            value = totals[skill]
            positive = float(self.shards[shard]['action'][row, 0, -1])
            if positive not in (0., 1.):
                raise ValueError('binary TRAIN completion required')
            value['mass'] += float(mass[index])
            value['positive_mass'] += float(mass[index]) * positive
            value['positive_n'] += int(positive)
            value['rows_N'] += 1
        return {skill: {**value, 'positive_fraction': value['positive_mass'] / value['mass'],
                        'source': 'unique TRAIN h0 labels under declared weighted sampler; not VAL'}
                for skill, value in totals.items() if value['rows_N'] and 0 < value['positive_mass'] < value['mass']}


def make_policy(chunk, *, device='cpu', pretrained=False):
    library()
    from harness.grasp_act_policy import make_policy as old_make
    from lerobot.policies.act.modeling_act import ACTPolicy
    # Reuse the exact pinned configuration; alter only the registered horizon.
    original = old_make(device=device, pretrained=False)
    config = replace(original.config, chunk_size=chunk, n_action_steps=1, temporal_ensemble_coeff=None)
    del original
    policy = ACTPolicy(config).to(device)
    if pretrained:
        from torchvision.models import ResNet18_Weights, resnet18
        weights = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1).state_dict()
        policy.model.backbone.load_state_dict({k: weights[k] for k in policy.model.backbone.state_dict()}, strict=True)
    return policy


def save_actor(policy, root, stats, provenance):
    import draccus
    from safetensors.torch import save_file
    from harness import grasp_act_contract as c
    from harness.grasp_act_policy import UPSTREAM_SHA
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    save_file({k: v.detach().cpu().contiguous() for k, v in policy.state_dict().items()}, str(root/'model.safetensors'))
    (root/'config.json').write_text(json.dumps(draccus.encode(policy.config), indent=2)+'\n')
    (root/'adapter.json').write_text(json.dumps(dict(schema='ugrp.act18.adapter.v1',
        chunk=policy.config.chunk_size, image_mode='current_full_v1', image_hw=[480,640], model_image_hw=[480,640],
        done_mode='balanced_bce_v1', stats=stats, provenance=provenance,
        upstream_sha=UPSTREAM_SHA, lerobot_act_sha256=LEROBOT_ACT_SHA256,
        contract_sha256=sha256(Path(c.__file__)),
        student_input_contract='own RGB + own issued command history + task labels/clocks only',
        static_map_use='none', policy_ground_truth_fields=0, handwritten_nearfield_fallback=False), indent=2)+'\n')
    (root/'SHA256.json').write_text(json.dumps({name:sha256(root/name) for name in ['model.safetensors','config.json','adapter.json']}, indent=2)+'\n')


class Actor:
    def __init__(self, policy, stats, device, chunk):
        self.policy, self.stats, self.device, self.chunk = policy.eval(), stats, device, chunk

    def decode(self, values):
        values = np.asarray(values)
        out = values*np.asarray(self.stats['action_std'])+np.asarray(self.stats['action_mean'])
        out[..., -1] = np.exp(-np.logaddexp(0., -values[..., -1]))
        return out

    def predict(self, obs, jpgs):
        import torch
        batch = {k:torch.from_numpy(v.copy()).unsqueeze(0).to(self.device)
            for k,v in observation_batch(obs,jpgs,self.stats,'current_full_v1').items()}
        with torch.inference_mode():
            values = self.decode(self.policy.predict_action_chunk(batch)[0].cpu().numpy())
        if values.shape != (self.chunk,14) or not np.isfinite(values).all():
            raise ValueError('invalid ACT output; no fallback')
        return values.tolist()

    @classmethod
    def load(cls, root, *, device='cpu'):
        library()
        import draccus
        from safetensors.torch import load_file
        from harness import grasp_act_contract as c
        from harness.grasp_act_policy import UPSTREAM_SHA
        from lerobot.policies.act import modeling_act
        root = Path(root)
        hashes = json.loads((root/'SHA256.json').read_text())
        if set(hashes) != {'model.safetensors','config.json','adapter.json'} or any(sha256(root/k)!=v for k,v in hashes.items()):
            raise ValueError('ACT18 artifact hash/inventory mismatch')
        meta = json.loads((root/'adapter.json').read_text())
        if (meta.get('schema')!='ugrp.act18.adapter.v1' or meta.get('chunk') not in CANDIDATES.values()
                or meta.get('contract_sha256')!=sha256(Path(c.__file__)) or meta.get('upstream_sha')!=UPSTREAM_SHA
                or sha256(Path(modeling_act.__file__))!=LEROBOT_ACT_SHA256
                or meta.get('image_mode')!='current_full_v1' or meta.get('done_mode')!='balanced_bce_v1'):
            raise ValueError('ACT18 frozen runtime/input mismatch')
        policy = make_policy(meta['chunk'], device=device)
        saved = json.loads((root/'config.json').read_text())
        actual = json.loads(json.dumps(draccus.encode(policy.config)))
        saved['device'] = actual['device']
        if saved != actual:
            raise ValueError('saved ACT configuration changed')
        policy.load_state_dict(load_file(str(root/'model.safetensors')), strict=True)
        return cls(policy, meta['stats'], device, meta['chunk'])
