"""Opt-in learned pair stage head on the unchanged beamact3 ACT decoder.

No stage or geometry is an observation. Separate offline targets train the
head; deployment derives both actions and stages from the same own RGB/issued
command/task batch. This module does not collect data or start training.
"""
import json
from pathlib import Path

import numpy as np

from harness import grasp_act_contract as c
from harness import beamact3
from harness.beamact_pair_student import STAGE_MODE, LEARNED_STAGES

SCHEMA = 'ugrp.grasp_act.adapter.beamact4.v1'
TARGET_SCHEMA = 'ugrp.beamact4.stage-target.v1'


def install_stage_head(policy, *, stage_mode='off'):
    if stage_mode == 'off':
        return policy
    if stage_mode != STAGE_MODE:
        raise ValueError('unknown stage mode')
    from torch import nn

    class ActionAndStage(nn.Module):
        def __init__(self, action):
            super().__init__()
            self.action = action
            self.stage = nn.Linear(policy.config.dim_model, len(LEARNED_STAGES))
            self.stage_logits = None

        @property
        def logits(self):
            return self.action.logits  # existing wheel CE observes the same forward

        def forward(self, features):
            self.stage_logits = self.stage(features)
            return self.action(features)  # keep the CVAE/action target at 14-D

    policy.model.action_head = ActionAndStage(policy.model.action_head).to(next(policy.parameters()).device)
    return policy


def policy_loss(policy, batch, *, stage_mode='off', **kwargs):
    if stage_mode == 'off':
        return beamact3.policy_loss(policy, batch, **kwargs)
    if stage_mode != STAGE_MODE or 'stage_target' not in batch:
        raise ValueError('explicit learned-stage targets required')
    import torch
    import torch.nn.functional as F
    target, valid = batch['stage_target'], ~batch['action_is_pad']
    if (target.shape != valid.shape or target.dtype != torch.long or not valid.any()
            or not torch.all((target[valid] >= 0) & (target[valid] < len(LEARNED_STAGES)))):
        raise ValueError('aligned categorical stage targets required')
    # Targets are removed before the ACT forward: never encoder inputs or
    # privileged CVAE features. No second VAE sample/forward is introduced.
    model_batch = {k: v for k, v in batch.items() if k != 'stage_target'}
    head = policy.model.action_head
    head.stage_logits = None
    loss, metrics = beamact3.policy_loss(policy, model_batch, **kwargs)
    logits = head.stage_logits
    if logits is None or logits.shape != (*valid.shape, len(LEARNED_STAGES)):
        raise ValueError('missing shared-decoder stage logits')
    # Standard nonweighted categorical CE, mean over valid horizons. Unit
    # coefficient matches beamact3 wheel CE; not tuned on validation/heldout.
    stage_loss = F.cross_entropy(logits[valid], target[valid])
    return loss + stage_loss, {**metrics, 'stage_ce_loss': stage_loss.detach().item()}


def save_actor(policy, output, stats, provenance, *, stage_mode='off', arm='A'):
    from harness.grasp_act_data import sha256, write_json
    if stage_mode != STAGE_MODE or not hasattr(policy.model.action_head, 'stage'):
        raise ValueError('explicit stage head required; no legacy checkpoint relabeling')
    beamact3.save_actor(policy, output, stats, provenance, arm=arm)
    output = Path(output)
    meta = json.loads((output / 'adapter.json').read_text())
    meta.update(schema=SCHEMA, beamact4_stage_v1=STAGE_MODE,
        learned_stages=list(LEARNED_STAGES), stage_target_schema=TARGET_SCHEMA,
        stage_loss='unweighted_valid_mean_cross_entropy', stage_decoder='unique_argmax',
        stage_adapter_source_sha256=sha256(Path(__file__)))
    write_json(output / 'adapter.json', meta)
    write_json(output / 'SHA256.json', {n: sha256(output / n)
        for n in ('model.safetensors', 'config.json', 'adapter.json')})


class Beam4Actor(beamact3.Beam3Actor):
    def predict(self, observation, jpegs):
        raise ValueError('explicit predict_staged required; no stage-dropping fallback')

    def predict_staged(self, observation, jpegs):
        from harness.beamact4_execution import decode_stages
        chunk = super().predict(observation, jpegs)
        logits = self.policy.model.action_head.stage_logits[0].detach().cpu().numpy()
        decode_stages(logits)  # reject wrong shape/nonfinite/ties before worker output
        return {'chunk': chunk, 'stage_logits': np.asarray(logits).tolist()}

    @classmethod
    def load(cls, root, *, device='cpu'):
        import draccus
        from safetensors.torch import load_file
        from harness.grasp_act_data import IMAGE_HW, MODEL_IMAGE_HW, IMAGE_KEYS, sha256
        from harness.grasp_act_policy import UPSTREAM_SHA, GraspActor, make_policy
        root = Path(root)
        hashes = json.loads((root / 'SHA256.json').read_text())
        if set(hashes) != {'model.safetensors', 'config.json', 'adapter.json'} or any(
                sha256(root / n) != v for n, v in hashes.items()):
            raise ValueError('stage ACT inventory/hash mismatch')
        meta = json.loads((root / 'adapter.json').read_text())
        arm = meta.get('beamact3_v1')
        if (meta.get('schema') != SCHEMA or meta.get('beamact4_stage_v1') != STAGE_MODE
                or meta.get('learned_stages') != list(LEARNED_STAGES)
                or meta.get('stage_target_schema') != TARGET_SCHEMA
                or meta.get('stage_loss') != 'unweighted_valid_mean_cross_entropy'
                or meta.get('stage_decoder') != 'unique_argmax'
                or meta.get('stage_adapter_source_sha256') != sha256(Path(__file__))
                or meta.get('adapter_source_sha256') != sha256(Path(beamact3.__file__))
                or arm not in ('A', 'B') or meta.get('blank_images')
                or meta.get('compact_history') != beamact3.COMPACT_HISTORY
                or meta.get('wheel_values') != list(beamact3.WHEEL_VALUES)
                or meta.get('done_mode') != 'balanced_bce_v1'
                or meta.get('command_history_dropout') != 0.
                or meta.get('history_causal_split_v1') != ('off' if arm == 'A' else 'wheel_pulse_train_mean')
                or meta.get('upstream_sha') != UPSTREAM_SHA
                or meta.get('contract_sha256') != sha256(Path(c.__file__))
                or meta.get('image_hw') != list(IMAGE_HW)
                or meta.get('model_image_hw') != list(MODEL_IMAGE_HW)
                or meta.get('image_keys') != list(IMAGE_KEYS)
                or meta.get('history_layout') != '2x2_row_major_oldest_to_newest'):
            raise ValueError('stage ACT adapter mismatch; legacy models have no learned READY head')
        policy = install_stage_head(beamact3.install_head(make_policy(device=device), meta['stats']), stage_mode=STAGE_MODE)
        saved = json.loads((root / 'config.json').read_text())
        actual = json.loads(json.dumps(draccus.encode(policy.config)))
        saved['device'] = actual['device']
        if saved != actual:
            raise ValueError('stage ACT config mismatch')
        policy.load_state_dict(load_file(str(root / 'model.safetensors')), strict=True)
        return cls(GraspActor(policy, meta['stats'], device=device, done_mode=meta['done_mode']), arm)
