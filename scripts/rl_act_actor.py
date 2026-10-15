"""Frozen ACT15 + bounded per-tick residual. No simulator/reward/critic imports.

Only own RGB, issued history and instruction pass the frozen ACT validator.
This module can be loaded in an isolated deployment process without any GT
files. NN/GPU execution remains unverified until the Linux gcp2 pilot runs.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ACT15_SHA256 = 'd90a2b545709df6cd1a5972874db2e20c264007f9a798888f1bdccac22882ed1'


def residual_network(torch, feature_dim):
    nn = torch.nn
    net = nn.Sequential(nn.Linear(feature_dim,256),nn.ReLU(),nn.Linear(256,256),
                        nn.ReLU(),nn.Linear(256,14),nn.Tanh())
    nn.init.zeros_(net[-2].weight)
    nn.init.zeros_(net[-2].bias)
    return net


def compose(base, residual, limits, decoder):
    """Empirical calibrated envelope, then the unchanged frozen decoder.

    Preserve float64 base values: adding exact zero must reproduce ACT15's
    original inverse-normalization/rounding, rather than re-quantizing a base.
    """
    base, residual, limits = [np.asarray(v, dtype=np.float64) for v in (base, residual, limits)]
    if (any(v.shape != (14,) or not np.isfinite(v).all() for v in (base, residual, limits))
            or np.any(limits < 0) or np.any(abs(residual) > 1)):
        raise ValueError('finite14D base, bounded residual and nonnegative limits required')
    return decoder((base + residual * limits).tolist())


class FrozenACT:
    """World-local raw chunks; actor observations only, no learned GT guard."""
    def __init__(self, source, checkpoint, nworld, *, device='cuda'):
        if type(nworld) is not int or nworld <= 0:
            raise ValueError('positive world count required')
        source = Path(source).resolve()
        # Caller uses a separate process from physics to preserve module roots.
        sys.path.insert(0, str(source))
        from harness import grasp_act_contract as c
        from harness.grasp_act_policy import GraspActor, observation_batch
        from harness.grasp_act_data import IMAGE_KEYS
        if Path(c.__file__).resolve().parent.parent != source:
            raise ValueError('ACT module root collision: use an isolated actor process')
        model = Path(checkpoint) / 'model.safetensors'
        h = hashlib.sha256()
        with model.open('rb') as f:
            for block in iter(lambda: f.read(1024*1024), b''):
                h.update(block)
        if h.hexdigest() != ACT15_SHA256:
            raise ValueError('rl1b requires the exact ACT15 checkpoint')
        self.actor = GraspActor.load(checkpoint, device=device)
        self.actor.policy.requires_grad_(False).eval()
        self.c, self.batch, self.image_key = c, observation_batch, IMAGE_KEYS[0]
        self.device, self.nworld = device, nworld
        self.pending = [deque() for _ in range(nworld)]
        self.latched = [False] * nworld
        self.last_t, self.identity = [None] * nworld, [None] * nworld
        # 2x2 lag montage: 4x4 bins preserve 2x2 spatial bins within each lag.
        self.feature_dim = 512*4*4 + c.CONTEXT_DIM + 14 + 2

    def reset(self, indices):
        for i in indices:
            self.pending[i].clear()
            self.latched[i], self.last_t[i], self.identity[i] = False, None, None

    def prepare(self, actor_inputs):
        import torch
        if len(actor_inputs) != self.nworld:
            raise ValueError('one own observation per world required')
        batches, raw, phase = [], [], []
        need = []
        for i, item in enumerate(actor_inputs):
            obs = item.observation
            self.c.validate_observation(obs)
            identity = tuple(obs[k] for k in ('robot_id','skill','object_kind','role','destination_zone'))
            if (self.identity[i] != identity or (self.last_t[i] is not None and
                    abs(obs['t']-self.last_t[i]-self.c.PERIOD_S) > 1e-5)):
                # Same issued-clock continuity tolerance as frozen ChunkExecutor.
                self.reset([i])
            self.identity[i], self.last_t[i] = identity, obs['t']
            batches.append(self.batch(obs, item.jpegs, self.actor.stats, blank=self.actor.blank))
            if not self.latched[i] and not self.pending[i]:
                need.append(i)
        tensors = {k: torch.from_numpy(np.stack([b[k] for b in batches])).to(self.device)
                   for k in batches[0]}
        with torch.no_grad():
            if need:
                selected = {k: v[need] for k,v in tensors.items()}
                chunks = self.actor.decode_predictions(
                    self.actor.policy.predict_action_chunk(selected).cpu().numpy())
                if chunks.shape != (len(need), self.c.CHUNK, 14) or not np.isfinite(chunks).all():
                    raise ValueError('invalid frozen ACT chunks; no fallback')
                for i, chunk in zip(need, chunks):
                    self.pending[i].extend(chunk.tolist())
            # Pinned LeRobot ACT ResNet18 exposes feature_map; fail explicitly if
            # upstream changes rather than silently replacing the representation.
            maps = self.actor.policy.model.backbone(tensors[self.image_key])
            if not isinstance(maps, dict) or 'feature_map' not in maps:
                raise ValueError('unexpected pinned ACT backbone interface')
            visual = torch.nn.functional.adaptive_avg_pool2d(maps['feature_map'], (4,4)).flatten(1)
            visual = visual.cpu().numpy()
        for i, item in enumerate(actor_inputs):
            if self.latched[i]:
                previous = dict(item.observation['issued'][-1], wheels=[0.]*4, duration_s=[0.]*4)
                raw.append(self.c.encode_action(previous, done=True))
                phase.append(0.)
            else:
                phase.append((self.c.CHUNK-len(self.pending[i]))/(self.c.CHUNK-1))
                raw.append(self.pending[i].popleft())
        raw = np.asarray(raw, np.float64)
        features = np.concatenate([visual, np.stack([b['observation.state'] for b in batches]),
            raw.astype(np.float32), np.asarray(phase,np.float32)[:,None],
            np.asarray(self.latched,np.float32)[:,None]], axis=1).astype(np.float32)
        if features.shape != (self.nworld, self.feature_dim) or not np.isfinite(features).all():
            raise ValueError('invalid allowed actor features')
        return features, raw

    def issue(self, actor_inputs, raw, residuals, limits):
        if len(residuals) != self.nworld or len(raw) != self.nworld:
            raise ValueError('one residual per world required')
        actions, encoded = [], []
        for i, item in enumerate(actor_inputs):
            residual = np.zeros(14) if self.latched[i] else residuals[i]
            action = compose(raw[i], residual, limits, self.c.decode_action)
            self.latched[i] |= action['done']
            if self.latched[i]:
                self.pending[i].clear()
            command = dict(t=item.observation['t'], **{k:action[k] for k in ('wheels','duration_s','pwm')})
            self.c.command(command)
            actions.append(dict(command=command, done=bool(self.latched[i])))
            encoded.append(self.c.encode_action(command, done=bool(self.latched[i])))
        return actions, np.asarray(encoded, np.float32)


class ResidualPolicy:
    """Deployment actor only: no critic/reward/evaluator files or modules."""
    def __init__(self, path, frozen, *, device='cuda'):
        import torch
        from safetensors.torch import load_file
        path = Path(path)
        hashes = json.loads((path/'SHA256.json').read_text())
        if set(hashes) != {'adapter.json','model.safetensors'}:
            raise ValueError('residual deployment inventory mismatch')
        for name,digest in hashes.items():
            if hashlib.sha256((path/name).read_bytes()).hexdigest() != digest:
                raise ValueError('residual deployment hash mismatch')
        adapter = json.loads((path/'adapter.json').read_text())
        if (adapter['schema'] != 'ugrp.rl1b.residual-actor.v1'
                or adapter['feature_dim'] != frozen.feature_dim
                or adapter['base_sha256'] != ACT15_SHA256
                or adapter['actor_module_sha256'] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
                or adapter['contract_sha256'] != hashlib.sha256(Path(frozen.c.__file__).read_bytes()).hexdigest()):
            raise ValueError('residual deployment contract mismatch')
        self.network = residual_network(torch,frozen.feature_dim).to(device)
        self.network.load_state_dict(load_file(str(path/'model.safetensors')),strict=True)
        self.network.requires_grad_(False).eval()
        self.limits = np.asarray(adapter['limits'],np.float64)
        if self.limits.shape != (14,) or not np.isfinite(self.limits).all() or np.any(self.limits<0):
            raise ValueError('invalid deployment residual limits')
        self.device = device

    def select(self, features):
        import torch
        with torch.no_grad():
            result = self.network(torch.as_tensor(features,dtype=torch.float32,device=self.device)).cpu().numpy()
        if not np.isfinite(result).all():
            raise ValueError('nonfinite deployed residual')
        return result
