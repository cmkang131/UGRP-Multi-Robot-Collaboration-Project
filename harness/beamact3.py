"""Default-off categorical ACT candidate; own issued history only.

Keep the pinned ACT encoder, decoder, CVAE, target layout and execution contract.
Replace four continuous wheel outputs by four three-class heads. Continuous
pulse/PWM outputs share the same decoder features; the existing command
projection makes pulse conditional on nonzero wheel classes.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from harness import grasp_act_contract as c

ARMS = ('off', 'A', 'B')
# Unique TRAIN same-sign nonzero wheel runs: median 5 ticks (actdiag audit,
# N=8293; p25=1, p75=18). This is a fixed compact-history design, not tuned on
# validation or heldout20. It retains every command at the 10Hz control rate.
COMPACT_HISTORY = 5
WHEEL_VALUES = (-.35, 0., .35)  # all and only unique TRAIN wheel classes
SCHEMA = 'ugrp.grasp_act.adapter.beamact3.v1'


def transform_state(state, arm='off'):
    if arm not in ARMS:
        raise ValueError('unknown beamact3 arm')
    if arm == 'off':
        return state
    if state.ndim not in (1, 2) or state.shape[-1] != c.CONTEXT_DIM:
        raise ValueError('normalized v6 state required')
    changed = state.copy() if isinstance(state, np.ndarray) else state.clone()
    changed[..., :(c.HISTORY-COMPACT_HISTORY)*14] = 0.
    if arm == 'B':
        columns = [j*14+k for j in range(c.HISTORY-COMPACT_HISTORY,c.HISTORY) for k in range(8)]
        changed[..., columns] = 0.
    return changed


def transform_batch(batch, arm='off'):
    if arm == 'off':
        return batch
    return {**batch, 'observation.state': transform_state(batch['observation.state'], arm)}


def install_head(policy, stats):
    """No upstream source patch; keep 14-D targets for the CVAE and deployment."""
    import torch
    from torch import nn

    class WheelClasses(nn.Module):
        def __init__(self):
            super().__init__()
            self.continuous = nn.Linear(policy.config.dim_model, 10)
            self.wheel = nn.Linear(policy.config.dim_model, 4*3)
            values = torch.tensor(WHEEL_VALUES, dtype=torch.float32)
            mean = torch.tensor(stats['action_mean'][:4], dtype=torch.float32)
            std = torch.tensor(stats['action_std'][:4], dtype=torch.float32)
            self.register_buffer('normalized_classes', (values[None,:]-mean[:,None])/std[:,None])
            self.logits = None

        def forward(self, features):
            logits = self.wheel(features).reshape(*features.shape[:-1],4,3)
            # Only CE trains the categorical head. Argmax also defines the
            # deployed output; no soft wheel mixtures or persistence fallback.
            self.logits = logits
            classes = self.normalized_classes.expand(*logits.shape[:-2],4,3)
            wheel = classes.gather(-1, logits.argmax(-1,keepdim=True)).squeeze(-1)
            return torch.cat((wheel,self.continuous(features)),dim=-1)

    policy.model.action_head = WheelClasses().to(next(policy.parameters()).device)
    return policy


def policy_loss(policy, batch, *, mode, stats, priors, weight=1.):
    import torch
    import torch.nn.functional as F
    from harness.grasp_act_loss import policy_loss as completion_loss
    if mode != 'balanced_bce_v1':
        raise ValueError('beamact3 requires the frozen completion loss')
    captured = []
    hook = policy.model.register_forward_hook(lambda module,args,out:captured.append(out[0]))
    try:
        loss, metrics = completion_loss(policy,batch,mode=mode,stats=stats,priors=priors,weight=weight)
    finally:
        hook.remove()
    if len(captured) != 1:
        raise ValueError('exactly one upstream forward required')
    prediction = captured[0]
    valid = ~batch['action_is_pad']
    if not valid.any():
        raise ValueError('nonempty valid horizons required')
    values = prediction.new_tensor(WHEEL_VALUES)
    target = batch['action'][...,:4]*prediction.new_tensor(stats['action_std'][:4])+prediction.new_tensor(stats['action_mean'][:4])
    distance = (target[...,None]-values).abs()
    classes = distance.argmin(-1)
    # float32 normalization roundtrip tolerance only; no control acceptance rule.
    if not torch.all(distance.min(-1).values[valid] < 1e-5):
        raise ValueError('TRAIN target outside frozen three wheel values')
    logits = policy.model.action_head.logits
    ce = F.cross_entropy(logits[valid].reshape(-1,3),classes[valid].reshape(-1))
    # Pinned upstream uses mean(valid horizons *14 scalar outputs). Remove
    # exactly the four old wheel L1 terms. CE is the standard unweighted mean
    # over valid wheel labels, with coefficient1, matching done group's unit
    # coefficient; no validation-selected weighting or class rebalancing.
    old_wheel = (prediction[...,:4]-batch['action'][...,:4]).abs()[valid].sum()/(valid.sum()*c.ACTION_DIM)
    loss = loss-old_wheel+ce
    metrics.update(wheel_ce_loss=ce.detach().item(),wheel_l1_removed=old_wheel.detach().item(),
                   movement_l1_loss=metrics['movement_l1_loss']-old_wheel.detach().item())
    return loss,metrics


def save_actor(policy, output, stats, provenance, *, arm, blank=False, done_mode='balanced_bce_v1'):
    from harness.grasp_act_data import sha256, write_json
    from harness.grasp_act_policy import save_actor as base_save
    if arm not in ('A','B') or blank or done_mode != 'balanced_bce_v1':
        raise ValueError('explicit beamact3 own-RGB candidate required')
    base_save(policy,output,stats,provenance,blank=blank,done_mode=done_mode)
    output = Path(output)
    meta = json.loads((output/'adapter.json').read_text())
    meta.update(schema=SCHEMA,beamact3_v1=arm,compact_history=COMPACT_HISTORY,
        wheel_values=list(WHEEL_VALUES),wheel_loss='unweighted_valid_mean_cross_entropy',
        wheel_decoder='argmax; shared continuous pulse/PWM; existing command projection',
        adapter_source_sha256=sha256(Path(__file__)),
        command_history_dropout=0.,history_causal_split_v1='off' if arm=='A' else 'wheel_pulse_train_mean')
    write_json(output/'adapter.json',meta)
    write_json(output/'SHA256.json',{n:sha256(output/n) for n in ('model.safetensors','config.json','adapter.json')})


class Beam3Actor:
    def __init__(self, base, arm):
        self.base,self.arm = base,arm
        self.policy,self.stats = base.policy,base.stats
        self.device,self.done_mode,self.blank = base.device,base.done_mode,base.blank

    def decode_predictions(self,values):
        return self.base.decode_predictions(values)

    def predict(self,observation,jpegs):
        import torch
        from harness.grasp_act_policy import observation_batch
        batch = transform_batch(observation_batch(observation,jpegs,self.stats),self.arm)
        inputs = {k:torch.from_numpy(v.copy()).unsqueeze(0).to(self.device) for k,v in batch.items()}
        with torch.inference_mode():
            values = self.policy.predict_action_chunk(inputs)[0].cpu().numpy()
        result = self.decode_predictions(values)
        if result.shape != (c.CHUNK,c.ACTION_DIM) or not np.isfinite(result).all():
            raise ValueError('invalid categorical ACT output; no fallback')
        return result.tolist()

    @classmethod
    def load(cls,root,*,device='cpu'):
        import draccus
        from safetensors.torch import load_file
        from harness.grasp_act_data import IMAGE_HW,MODEL_IMAGE_HW,IMAGE_KEYS,sha256
        from harness.grasp_act_policy import UPSTREAM_SHA,GraspActor,make_policy
        root = Path(root)
        hashes = json.loads((root/'SHA256.json').read_text())
        if set(hashes) != {'model.safetensors','config.json','adapter.json'} or any(sha256(root/n)!=v for n,v in hashes.items()):
            raise ValueError('categorical ACT inventory/hash mismatch')
        meta = json.loads((root/'adapter.json').read_text())
        arm = meta.get('beamact3_v1')
        if (meta.get('schema')!=SCHEMA or arm not in ('A','B') or meta.get('blank_images')
            or meta.get('compact_history')!=COMPACT_HISTORY or meta.get('wheel_values')!=list(WHEEL_VALUES)
            or meta.get('done_mode')!='balanced_bce_v1' or meta.get('command_history_dropout')!=0.
            or meta.get('adapter_source_sha256')!=sha256(Path(__file__))
            or meta.get('upstream_sha')!=UPSTREAM_SHA or meta.get('contract_sha256')!=sha256(Path(c.__file__))
            or meta.get('image_hw')!=list(IMAGE_HW) or meta.get('model_image_hw')!=list(MODEL_IMAGE_HW)
            or meta.get('image_keys')!=list(IMAGE_KEYS) or meta.get('history_layout')!='2x2_row_major_oldest_to_newest'
            or meta.get('history_causal_split_v1')!=('off' if arm=='A' else 'wheel_pulse_train_mean')):
            raise ValueError('categorical ACT adapter mismatch')
        policy = install_head(make_policy(device=device),meta['stats'])
        saved = json.loads((root/'config.json').read_text())
        actual = json.loads(json.dumps(draccus.encode(policy.config)))
        saved['device'] = actual['device']
        if saved != actual:
            raise ValueError('categorical ACT config mismatch')
        policy.load_state_dict(load_file(str(root/'model.safetensors')),strict=True)
        return cls(GraspActor(policy,meta['stats'],device=device,done_mode=meta['done_mode']),arm)


def load_actor(root,*,device='cpu'):
    meta = json.loads((Path(root)/'adapter.json').read_text())
    if meta.get('schema') == SCHEMA:
        return Beam3Actor.load(root,device=device)
    from harness.beamact_input import BeamActor
    return BeamActor.load(root,device=device)
