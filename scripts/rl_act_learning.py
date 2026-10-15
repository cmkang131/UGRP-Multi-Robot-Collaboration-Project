"""Small off-policy residual learner; privileged inputs go to critics only.

Training requires explicit Linux gcp2 L4 metadata before Torch is imported.
Reference recipe: ResFiT2509.19301 §III-C, sfujim/TD3 (tau .005, target noise
.2 clipped .5, Adam3e-4). Pilot: batch128, delayed actor4, n-step3, gamma.995.
The hard ACT decoder uses a straight-through gradient ONLY in actor loss;
forward values and replay actions are actual decoded issued commands. This
is a declared pilot approximation (Bengio et al.1308.3432), not exact TD3/ResFiT.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np

GAMMA = .995


@dataclass(frozen=True)
class Transition:
    features: np.ndarray
    base: np.ndarray
    privileged: np.ndarray
    action: np.ndarray
    reward: float
    next_features: np.ndarray
    next_base: np.ndarray
    next_privileged: np.ndarray
    terminal: bool


class Replay:
    """Per-world n-step queues. No crossing task/reset boundaries."""
    def __init__(self, nworld, feature_dim, critic_dim, *, capacity=25000, seed=20261016):
        if any(type(x) is not int or x <= 0 for x in (nworld, feature_dim, critic_dim, capacity)):
            raise ValueError('positive finite replay dimensions required')
        self.pending = [deque() for _ in range(nworld)]
        self.data = {k:np.empty((capacity, width),dtype=dtype) for k,width,dtype in (
            ('features',feature_dim,np.float32), ('next_features',feature_dim,np.float32),
            ('privileged',critic_dim,np.float32), ('next_privileged',critic_dim,np.float32),
            ('base',14,np.float64), ('next_base',14,np.float64), ('action',14,np.float32),
            ('reward',1,np.float32), ('discount',1,np.float32))}
        self.capacity, self.size, self.total, self.transitions = capacity, 0, 0, 0
        self.rng = np.random.default_rng(seed)

    def _store(self, q, count, *, terminal):
        first, last = q[0], q[count-1]
        row = {k:getattr(first,k) for k in ('features','base','privileged','action')}
        row.update({k:getattr(last,k) for k in ('next_features','next_base','next_privileged')})
        row['reward'] = [sum(GAMMA**i * q[i].reward for i in range(count))]
        row['discount'] = [0. if terminal else GAMMA**count]
        index = self.total % self.capacity
        for key,value in row.items():
            a = np.asarray(value)
            if a.shape != self.data[key].shape[1:] or not np.isfinite(a).all():
                raise ValueError('invalid replay field '+key)
            self.data[key][index] = a
        self.total += 1
        self.size = min(self.total, self.capacity)
        q.popleft()

    def push(self, world, transition):
        if (type(world) is not int or not 0 <= world < len(self.pending)
                or type(transition.terminal) is not bool or not math.isfinite(transition.reward)):
            raise ValueError('invalid world transition')
        for key in ('features','base','privileged','action','next_features','next_base','next_privileged'):
            value = np.asarray(getattr(transition,key))
            if value.shape != self.data[key].shape[1:] or not np.isfinite(value).all():
                raise ValueError('invalid transition field '+key)
        q = self.pending[world]
        q.append(deepcopy(transition))
        self.transitions += 1
        if len(q) >= 3:
            self._store(q, 3, terminal=transition.terminal)
        if transition.terminal:
            while q:
                self._store(q, len(q), terminal=True)

    def truncate(self, world):
        # Collector/resource truncation still bootstraps. Task cap90 is terminal
        # and must instead be sent through push(terminal=True).
        q = self.pending[world]
        while q:
            self._store(q, len(q), terminal=False)

    def reset(self, world):
        if self.pending[world]:
            raise ValueError('flush terminal/truncation before reset; no cross-episode credit')

    def sample(self, batch_size=128):
        if type(batch_size) is not int or batch_size <= 0 or self.size < batch_size:
            raise ValueError('insufficient replay')
        indices = self.rng.integers(0, self.size, batch_size)
        return {k:v[indices].copy() for k,v in self.data.items()}


def actor_network(torch, feature_dim):
    nn = torch.nn
    net = nn.Sequential(nn.Linear(feature_dim,256),nn.ReLU(),nn.Linear(256,256),
                        nn.ReLU(),nn.Linear(256,14),nn.Tanh())
    nn.init.zeros_(net[-2].weight)
    nn.init.zeros_(net[-2].bias)
    return net


def critic_network(torch, feature_dim, critic_dim):
    nn = torch.nn
    return nn.Sequential(nn.Linear(feature_dim+critic_dim+14,256),nn.LayerNorm(256),nn.ReLU(),
                         nn.Linear(256,256),nn.LayerNorm(256),nn.ReLU(),nn.Linear(256,1))


class ResidualTD3:
    def __init__(self, feature_dim, critic_dim, limits, decoder, encoder, *, enabled=False,
                 seed=20261016):
        if not enabled:
            raise ValueError('residual learning is default OFF')
        from scripts.simalt_host import gcp2_identity
        host = gcp2_identity()
        if host['instance'] != 'ugrp-act-l4-gcp2':
            raise RuntimeError('training requires the approved gcp2 L4')
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA required; no CPU/Mac training fallback')
        limits = np.asarray(limits,np.float64)
        if limits.shape != (14,) or not np.isfinite(limits).all() or np.any(limits<0):
            raise ValueError('empirically calibrated14D limits required')
        torch.manual_seed(seed)
        self.torch, self.host = torch, host
        self.decoder, self.encoder, self.limits = decoder, encoder, limits
        self.actor = actor_network(torch,feature_dim).cuda()
        self.critics = torch.nn.ModuleList([critic_network(torch,feature_dim,critic_dim) for _ in range(2)]).cuda()
        self.actor_target, self.critics_target = deepcopy(self.actor), deepcopy(self.critics)
        self.actor_target.requires_grad_(False)
        self.critics_target.requires_grad_(False)
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(),lr=3e-4)
        self.critic_optimizer = torch.optim.Adam(self.critics.parameters(),lr=3e-4)
        self.steps = 0
        self.rng = np.random.default_rng(seed)
        self.config = dict(feature_dim=feature_dim,critic_dim=critic_dim,hidden=[256,256],
            actor_delay=4,n_step=3,gamma=GAMMA,tau=.005,batch=128,utd=1,
            target_noise=.2,target_noise_clip=.5,optimizer_lr=3e-4,
            exploration='uniform normalized [-1,1], clipped to calibrated median envelope',
            projection_gradient='straight-through pilot approximation; forward exact decoder',
            privileged_actor_inputs=0)

    def select(self, features, *, explore=False):
        torch = self.torch
        with torch.no_grad():
            values = self.actor(torch.as_tensor(features,dtype=torch.float32,device='cuda')).cpu().numpy()
        if explore:
            # Full calibrated per-channel correction envelope, already measured
            # from GCP2 shadow corrections; no new motion/acceptance threshold.
            values = np.clip(values+self.rng.uniform(-1,1,values.shape),-1,1)
        if not np.isfinite(values).all():
            raise RuntimeError('nonfinite residual policy')
        return values

    def _project(self, residual, features, base, *, straight_through):
        torch = self.torch
        # The final allowed feature is the issued-done latch, never a GT stage.
        free = (features[:,-1:] == 0).to(residual.dtype)
        raw = base+residual.to(torch.float64)*free*self.torch.as_tensor(self.limits,device='cuda')
        decoded = []
        for values in raw.detach().cpu().numpy():
            action = self.decoder(values.tolist())
            command = dict(t=0.,**{k:action[k] for k in ('wheels','duration_s','pwm')})
            decoded.append(self.encoder(command,done=action['done']))
        exact = torch.as_tensor(np.asarray(decoded),dtype=torch.float32,device='cuda')
        continuous = raw.to(torch.float32)
        return continuous+(exact-continuous).detach() if straight_through else exact

    def update(self, replay):
        torch = self.torch
        sampled = replay.sample(128)
        b = {k:torch.from_numpy(v).cuda() for k,v in sampled.items()}
        features, private = b['features'].detach(), b['privileged'].detach()
        with torch.no_grad():
            noise = (torch.randn_like(b['action'])*.2).clamp(-.5,.5)
            residual = (self.actor_target(b['next_features'])+noise).clamp(-1,1)
            next_action = self._project(residual,b['next_features'],b['next_base'],straight_through=False)
            next_q = torch.cat([b['next_features'],b['next_privileged'],next_action],1)
            target = b['reward']+b['discount']*torch.minimum(*[q(next_q) for q in self.critics_target])
        current = torch.cat([features,private,b['action']],1)
        loss = sum(torch.nn.functional.mse_loss(q(current),target) for q in self.critics)
        if not torch.isfinite(loss):
            raise RuntimeError('nonfinite critic loss')
        self.critic_optimizer.zero_grad(set_to_none=True)
        loss.backward()
        self.critic_optimizer.step()
        self.steps += 1
        result = dict(optimizer_steps=self.steps,critic_loss=float(loss.detach().cpu()),actor_loss=None)
        if self.steps % 4 == 0:
            self.critics.requires_grad_(False)
            try:
                residual = self.actor(features)  # NO privileged argument.
                projected = self._project(residual,features,b['base'],straight_through=True)
                actor_loss = -self.critics[0](torch.cat([features,private,projected],1)).mean()
                if not torch.isfinite(actor_loss):
                    raise RuntimeError('nonfinite actor loss')
                self.actor_optimizer.zero_grad(set_to_none=True)
                actor_loss.backward()
                self.actor_optimizer.step()
                result['actor_loss'] = float(actor_loss.detach().cpu())
            finally:
                self.critics.requires_grad_(True)
            with torch.no_grad():
                for source,target_net in ((self.actor,self.actor_target),(self.critics,self.critics_target)):
                    for p,t in zip(source.parameters(),target_net.parameters()):
                        t.lerp_(p,.005)
        return result

    def save(self, path, metadata):
        path = Path(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            raise FileExistsError(path)
        with path.open('xb') as f:
            self.torch.save(dict(schema='ugrp.rl1b.residual.v1',config=self.config,metadata=metadata,
                limits=self.limits.tolist(),optimizer_steps=self.steps,
                actor=self.actor.state_dict(),critics=self.critics.state_dict(),
                actor_target=self.actor_target.state_dict(),critics_target=self.critics_target.state_dict(),
                actor_optimizer=self.actor_optimizer.state_dict(),
                critic_optimizer=self.critic_optimizer.state_dict()),f)
