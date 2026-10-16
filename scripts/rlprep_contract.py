"""Default-off, dependency-injected RL preparation; no engine/learner launcher.

Reuse PR530's ActorEnv and training-only reward/critic lane. A future warp3
transport must implement that interface; RECORD_API_READY is metadata, not an
RL admission or a proof of bitwise trajectories. See experiments/2026-10-16-rlprep.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from scripts.rl_act_env import ActorEnv, TrainingOutput
from scripts.rl_act_reward import Heuristics, TrainingTruth

WARP3_SOURCE = '0362037280c6cbc4677f70366db43b9892b23690'
WARP3_CONTROLLER = 'f0db6b1abb842ea65b71c433738210254f300a7c'
# Existing ACT15/warp3 API contract: one issued command every 0.1 SIM seconds.
SIM_TICK_S = .1


@dataclass(frozen=True)
class CountBudget:
    # Resource proposals, NOT measured throughput or acceptance thresholds:
    # pilot = 8 worlds * 1 episode * 900 ticks; stage1 = 16 * 5 * 900.
    # The 900-tick horizon is inherited from ACT15/warp3, not tuned for RL.
    worlds: int = 8
    transitions: int = 7200

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in (self.worlds, self.transitions)):
            raise ValueError('positive integer world and transition budgets required')

    @property
    def aggregate_sim_s(self):
        return self.transitions * SIM_TICK_S


def inspect_warp3_marker(path):
    """Validate the REAL warp3 marker shape, without claiming proof retrieval."""
    raw = Path(path).read_bytes()
    row = json.loads(raw)
    if (row.get('status') != 'RECORD_API_READY' or row.get('ready') is not True
            or row.get('source_sha') != WARP3_SOURCE
            or row.get('controller_source') != WARP3_CONTROLLER):
        raise ValueError('unexpected warp3 API marker/source')
    for proof in ('gate', 'reset_pause', 'native_recording', 'actual_actor'):
        item = row.get('proofs', {}).get(proof, {})
        digest = item.get('sha256', '')
        if (not item.get('path') or type(digest) is not str or len(digest) != 64
                or any(c not in '0123456789abcdef' for c in digest)):
            raise ValueError('missing warp3 proof reference: ' + proof)
    return {'marker_sha256': hashlib.sha256(raw).hexdigest(), 'metadata_valid': True,
            'proofs_retrieved_this_task': False, 'record': row}


def stop_event(category, *, detail, blocking_object='not_applicable', cap_end=False):
    """No invented clearance for non-geometric preparation/budget rejections."""
    if any(type(v) is not str or not v.strip() for v in (category, detail, blocking_object)):
        raise ValueError('category, detail and blocking_object must be nonempty')
    if type(cap_end) is not bool:
        raise ValueError('boolean cap_end required')
    return dict(category=category, blocking_object=blocking_object, minimum_gap_m=None,
                minimum_gap_status='not_geometric', cap_end=cap_end, detail=detail)


class Warp3BackendAdapter:
    """Normalize warp3 Owner's private truth dict to PR530's TrainingTruth.

    Source 036203728 scripts/warp_act_api.py:205 returns (dict, critic tuple),
    whereas ActorEnv expects TrainingTruth. No engine import or owner creation.
    """
    def __init__(self, owner, *, training=False):
        self.owner, self.training = owner, training

    def reset(self, plans, indices):
        return self.owner.reset(plans, indices=indices)

    def step(self, actions):
        return self.owner.step(actions)

    def read_actor(self, i):
        return self.owner.read_actor(i)

    def read_training(self, i):
        if not self.training:
            raise RuntimeError('no privileged adapter lane during evaluation')
        truth, critic = self.owner.read_training(i)
        if isinstance(truth, dict):
            truth = TrainingTruth(**truth)
        if not isinstance(truth, TrainingTruth):
            raise ValueError('warp3 training truth contract mismatch')
        return truth, tuple(critic)


class PreparationBatchEnv:
    """Skeleton adapter for ActorEnv-compatible MJWarp transports.

    No backend is constructed here. Use the exact frozen ACT contract validators,
    including its nested whitelists. step() exposes only policy inputs and public
    SIM/issued-done flags; reward/critic are obtained through training_output().
    Logs are separate from policy inputs. The wrapper cannot establish that an
    arbitrary backend never read truth: GPU/process isolation remains unverified.
    """
    def __init__(self, backend, validate_observation, validate_command, *, budget=CountBudget(),
                 rlprep_batch_v1=False, training=False, distance_p95=1.):
        if rlprep_batch_v1 is not True:
            raise ValueError('rlprep_batch_v1 is default OFF')
        self.budget = budget
        self.env = ActorEnv(Warp3BackendAdapter(backend, training=training),
                            validate_observation, validate_command,
                            nworld=budget.worlds, enabled=True, training=training,
                            heuristics=Heuristics(), distance_p95=distance_p95)
        self.transitions = 0
        self.audit = []
        self._training_outputs = None
        self._success_paid = [False] * budget.worlds
        self.closed_by_cap = False

    def reset(self, plans, indices=None):
        if self.closed_by_cap:
            raise RuntimeError('aggregate budget exhausted; new prepared run required')
        actors = self.env.reset(plans, indices)
        for i in range(self.budget.worlds) if indices is None else indices:
            self._success_paid[i] = False
        # Old rewards must never be paired with a fresh reset observation.
        self._training_outputs = None
        return actors

    def step(self, actions):
        if not self.env.initialized:
            raise RuntimeError('reset required before step')
        if self.closed_by_cap:
            raise RuntimeError('aggregate budget exhausted')
        active = sum(not terminal for terminal in self.env.terminal)
        if not active:
            raise RuntimeError('no active worlds; reset required')
        if self.transitions + active > self.budget.transitions:
            self.closed_by_cap = True
            self._training_outputs = None
            self.audit.append(stop_event('aggregate_transition_cap', cap_end=True,
                detail='whole active batch would exceed sealed transition budget'))
            raise RuntimeError('cap_end: no further backend step issued')
        actors, terminal, private = self.env.step(actions)
        self.transitions += active
        if self.env.training:
            normalized = []
            for i, output in enumerate(private):
                if output is None:
                    normalized.append(None)
                    continue
                reward = deepcopy(output.reward)
                # Episodic success objective (ResFiT §IV-B), not repeated lift
                # farming after drop/regrasp. Keep PR530's ten-unit scale.
                bonus = reward['success_reward']
                if bonus and self._success_paid[i]:
                    reward['reward'] -= bonus
                    reward['success_reward'] = 0.
                self._success_paid[i] |= bool(bonus)
                normalized.append(TrainingOutput(reward, output.critic))
            self._training_outputs = tuple(normalized)
        self.audit.append(dict(event='transition', transitions=self.transitions,
            aggregate_sim_s=self.transitions * SIM_TICK_S, active_worlds=active,
            policy_payloads_validated=len(actors),
            training_privileged_reward_reads=self.env.training_privileged_reward_reads,
            training_privileged_critic_reads=self.env.training_privileged_critic_reads,
            input_audit_scope='frozen-validator payload boundary; no process read proof'))
        return actors, terminal

    def training_output(self):
        if not self.env.training:
            raise RuntimeError('reward/critic lane unavailable during evaluation')
        if self._training_outputs is None:
            raise RuntimeError('no current training transition')
        return deepcopy(self._training_outputs)

    def write_audit(self, path):
        # Write-once run log. Never place this file in an actor input directory.
        with Path(path).open('x') as stream:
            for row in self.audit:
                stream.write(json.dumps(row, allow_nan=False, sort_keys=True) + '\n')


def start_training(*args, **kwargs):
    """Preparation-only hard stop, even if someone flips a config boolean."""
    raise RuntimeError('rlprep is design-only: training/GPU launch prohibited; ACT gate pending')
