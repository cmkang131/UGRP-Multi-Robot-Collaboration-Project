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

CANDIDATES = {'R8': 8, 'R100': 100}


def extend_targets(actions, metadata, chunk):
    """Reconstruct future labels from original h0, within the same skill only."""
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
    return out, pad


class ReferenceDataset(Dataset):
    def __init__(self, root, split, *, chunk=8):
        super().__init__(root, split, image_mode='current_full_v1')
        if chunk not in CANDIDATES.values():
            raise ValueError('registered ACT chunk required')
        self.chunk = chunk
        offset = 0
        for shard in self.shards:
            n = len(shard['state'])
            actions, pad = extend_targets(shard['action'][:, 0], self.metadata[offset:offset+n], chunk)
            # This is a new view over existing successful v7 recordings. Verify
            # byte-exact parity with all original horizons that still exist.
            common = min(chunk, shard['action'].shape[1])
            if (not np.array_equal(actions[:, :common], shard['action'][:, :common])
                    or not np.array_equal(pad[:, :common], shard['action_is_pad'][:, :common])):
                raise ValueError('reconstructed future targets differ from original chunk8')
            shard['action'], shard['action_is_pad'] = actions, pad
            offset += n


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
