"""Pinned upstream ACT and a serialized, own-observation-only deployment adapter."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from harness import grasp_act_contract as c
from harness.grasp_act_data import (IMAGE_HW, MODEL_IMAGE_HW, IMAGE_KEYS, assert_tensor_keys,
                                    image_array, history_image, sha256, write_json)

UPSTREAM_SHA = '89236ea0f4f81a81ca566081e20dd1ff5f823cbe'


def verify_upstream():
    direct = json.loads(importlib.metadata.distribution('lerobot').read_text('direct_url.json'))
    if direct.get('vcs_info', {}).get('commit_id') != UPSTREAM_SHA:
        raise ValueError('requires requirements-reference-act.txt pinned LeRobot')


def make_policy(*, pretrained=False, device='cpu'):
    verify_upstream()
    from lerobot.configs.types import FeatureType, PolicyFeature
    from lerobot.policies.act.configuration_act import ACTConfig
    from lerobot.policies.act.modeling_act import ACTPolicy
    features = {key: PolicyFeature(type=FeatureType.VISUAL, shape=(3, *MODEL_IMAGE_HW)) for key in IMAGE_KEYS}
    features['observation.state'] = PolicyFeature(type=FeatureType.STATE, shape=(c.CONTEXT_DIM,))
    config = ACTConfig(input_features=features,
        output_features={'action': PolicyFeature(type=FeatureType.ACTION, shape=(c.ACTION_DIM,))},
        chunk_size=c.CHUNK, n_action_steps=c.CHUNK, temporal_ensemble_coeff=None,
        vision_backbone='resnet18', pretrained_backbone_weights=None,
        dim_model=512, n_heads=8, dim_feedforward=3200, n_encoder_layers=4,
        n_decoder_layers=1, n_vae_encoder_layers=4, latent_dim=32,
        kl_weight=10., dropout=.1, optimizer_lr=1e-5, optimizer_lr_backbone=1e-5,
        optimizer_weight_decay=1e-4, device=device)
    policy = ACTPolicy(config)
    if pretrained:
        from torchvision.models import ResNet18_Weights, resnet18
        weights = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1).state_dict()
        policy.model.backbone.load_state_dict({k: weights[k] for k in policy.model.backbone.state_dict()}, strict=True)
    return policy.to(device)


def observation_batch(observation, jpegs, stats, *, blank=False):
    c.validate_observation(observation)
    if len(jpegs) != c.RGB_HISTORY:
        raise ValueError('exact own RGB history required')
    frames = []
    for ref, jpeg in zip(observation['rgb'], jpegs):
        if hashlib.sha256(jpeg).hexdigest() != ref['sha256']:
            raise ValueError('inference RGB hash mismatch')
        frames.append(image_array(jpeg))
    batch = {IMAGE_KEYS[0]: history_image(frames, blank=blank)}
    batch['observation.state'] = ((np.asarray(c.context(observation), np.float32) -
        np.asarray(stats['state_mean'], np.float32)) / np.asarray(stats['state_std'], np.float32))
    assert_tensor_keys(batch)
    return batch


def save_actor(policy, output, stats, provenance, *, blank=False, done_mode='legacy_l1'):
    from harness.grasp_act_loss import DONE_MODES
    if done_mode not in DONE_MODES:
        raise ValueError('unknown completion output mode')
    import draccus
    from safetensors.torch import save_file
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    save_file({k: v.detach().cpu().contiguous() for k, v in policy.state_dict().items()},
              str(output / 'model.safetensors'))
    write_json(output / 'config.json', draccus.encode(policy.config))
    write_json(output / 'adapter.json', {'schema': 'ugrp.grasp_act.adapter.v1' if done_mode == 'legacy_l1' else 'ugrp.grasp_act.adapter.v2',
        **({'done_mode': done_mode} if done_mode != 'legacy_l1' else {}),
        'contract_sha256': sha256(Path(c.__file__)), 'upstream_sha': UPSTREAM_SHA,
        'image_hw': list(IMAGE_HW), 'model_image_hw': list(MODEL_IMAGE_HW),
        'history_layout': '2x2_row_major_oldest_to_newest',
        'image_keys': list(IMAGE_KEYS), 'blank_images': blank,
        'stats': stats, 'provenance': provenance})
    write_json(output / 'SHA256.json', {p.name: sha256(p) for p in output.iterdir()})


class GraspActor:
    def __init__(self, policy, stats, *, blank=False, device='cpu', done_mode='legacy_l1'):
        self.policy, self.stats, self.blank, self.device = policy.eval(), stats, blank, device
        self.done_mode = done_mode

    def decode_predictions(self, values):
        values = np.asarray(values)
        decoded = values * np.asarray(self.stats['action_std']) + np.asarray(self.stats['action_mean'])
        if self.done_mode == 'balanced_bce_v1':
            # Stable sigmoid. Class-balanced scores are not calibrated probabilities.
            z = values[..., -1]
            decoded[..., -1] = np.exp(-np.logaddexp(0., -z))
        return decoded

    def predict(self, observation, jpegs):
        import torch
        batch = observation_batch(observation, jpegs, self.stats, blank=self.blank)
        batch = {k: torch.from_numpy(v.copy()).unsqueeze(0).to(self.device) for k, v in batch.items()}
        with torch.inference_mode():
            values = self.policy.predict_action_chunk(batch)[0].cpu().numpy()
        values = self.decode_predictions(values)
        if values.shape != (c.CHUNK, c.ACTION_DIM) or not np.isfinite(values).all():
            raise ValueError('nonfinite/wrong-sized ACT chunk; no fallback')
        return values.tolist()

    @classmethod
    def load(cls, root, *, device='cpu'):
        import draccus
        from safetensors.torch import load_file
        root = Path(root)
        hashes = json.loads((root / 'SHA256.json').read_text())
        if set(hashes) != {'model.safetensors', 'config.json', 'adapter.json'}:
            raise ValueError('artifact inventory mismatch')
        for name, digest in hashes.items():
            if sha256(root / name) != digest:
                raise ValueError('checkpoint artifact hash mismatch')
        meta = json.loads((root / 'adapter.json').read_text())
        done_mode = meta.get('done_mode', 'legacy_l1')
        if ((meta['schema'], done_mode) not in (
                ('ugrp.grasp_act.adapter.v1', 'legacy_l1'),
                ('ugrp.grasp_act.adapter.v2', 'balanced_bce_v1')) or meta['upstream_sha'] != UPSTREAM_SHA
                or meta['contract_sha256'] != sha256(Path(c.__file__))
                or meta['image_hw'] != list(IMAGE_HW) or meta['model_image_hw'] != list(MODEL_IMAGE_HW)
                or meta['history_layout'] != '2x2_row_major_oldest_to_newest'
                or meta['image_keys'] != list(IMAGE_KEYS)):
            raise ValueError('checkpoint adapter mismatch')
        policy = make_policy(device=device)
        saved = json.loads((root / 'config.json').read_text())
        actual = json.loads(json.dumps(draccus.encode(policy.config)))
        # Training CUDA and deployment CPU are the sole allowed config difference.
        saved['device'] = actual['device']
        if saved != actual:
            raise ValueError('checkpoint differs from audited ACT configuration')
        policy.load_state_dict(load_file(str(root / 'model.safetensors')), strict=True)
        return cls(policy, meta['stats'], blank=meta['blank_images'], device=device, done_mode=done_mode)


class ChunkExecutor:
    """No simulator capability. Reset on task switch or interruption; no fallback."""
    def __init__(self, predict, *, n_action_steps=c.CHUNK, temporal_ensemble_coeff=None):
        if type(n_action_steps) is not int or not 1 <= n_action_steps <= c.CHUNK:
            raise ValueError('n_action_steps must be 1..chunk_size')
        if temporal_ensemble_coeff is not None and (
                not np.isfinite(temporal_ensemble_coeff) or temporal_ensemble_coeff < 0 or n_action_steps not in (1, 2, 3, 4)):
            raise ValueError('temporal ensembling requires finite nonnegative coefficient and n_action_steps=1..4')
        self.predict = predict
        self.n_action_steps, self.temporal_ensemble_coeff = n_action_steps, temporal_ensemble_coeff
        self.reset()

    def reset(self):
        self.pending, self.identity, self.last_t = [], None, None
        self.done_requested = False
        self.chunks = []
        self.ensemble_ticks = 0

    def step(self, observation, jpegs, *, interrupt=False):
        c.validate_observation(observation)
        identity = tuple(observation[k] for k in ('robot_id', 'skill', 'object_kind', 'role', 'destination_zone'))
        now = observation['t']
        if self.identity != identity or interrupt:
            self.reset()
        if self.last_t is not None and abs(now - self.last_t - c.PERIOD_S) > 1e-5:
            self.reset()
        self.identity, self.last_t = identity, now
        if interrupt or self.done_requested:
            value = dict(observation['issued'][-1], t=now, wheels=[0.] * 4, duration_s=[0.] * 4)
            return value, self.done_requested
        ensemble = self.temporal_ensemble_coeff is not None
        need_prediction = (self.ensemble_ticks % self.n_action_steps == 0) if ensemble else not self.pending
        if need_prediction:
            values = np.asarray(self.predict(observation, jpegs), dtype=float)
            if values.shape != (c.CHUNK, c.ACTION_DIM) or not np.isfinite(values).all():
                raise ValueError('invalid action chunk')
            decoded = [c.decode_action(row) for row in values]
            if not ensemble:
                self.pending = decoded[:self.n_action_steps]
            else:
                self.chunks.append(values)
        if ensemble:
            # Sparse refresh is an opt-in deployment variant. Shift ALL chunks
            # every tick, including ticks without inference, to align horizons.
            weights = np.exp(-self.temporal_ensemble_coeff * np.arange(len(self.chunks)))
            averaged = np.average([chunk[0] for chunk in self.chunks], axis=0, weights=weights)
            action = c.decode_action(averaged)
            self.chunks = [chunk[1:] for chunk in self.chunks if len(chunk) > 1]
            self.ensemble_ticks += 1
        else:
            action = self.pending.pop(0)
        self.done_requested = action['done']
        if self.done_requested:
            self.pending.clear()
            self.chunks.clear()
        value = {'t': now, **{k: action[k] for k in ('wheels', 'duration_s', 'pwm')}}
        c.command(value)
        return value, self.done_requested
