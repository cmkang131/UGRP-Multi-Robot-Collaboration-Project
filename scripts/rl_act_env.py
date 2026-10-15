"""Default-OFF RL wrapper contract; no engine or handcrafted grasp fallback.

Backend binding requires committed distinct-start/reset/own-RGB support.
Original unexecuted prototype: outputs/rl1b/imported-originals/rl_act_env.py.
"""
from copy import deepcopy
from dataclasses import dataclass
import math

from scripts.rl_act_reward import Heuristics, reward_transition


@dataclass(frozen=True)
class ActorInput:
    observation: dict
    jpegs: tuple[bytes, ...]


@dataclass(frozen=True)
class TrainingOutput:
    reward: dict
    critic: tuple[float, ...]


class ActorEnv:
    """Inject the frozen ACT observation validator and an admitted backend.

    Conventional reset(plans, indices) and step(actions) own physics. Separate
    read_actor(i) returns only (observation, own JPEGs); read_training(i) returns
    (TrainingTruth, critic). Terminal flags depend on issued done and SIM time.
    Backend writes evaluation files independently. This wrapper does not
    implement or claim validated Warp partial reset or masked pausing.
    """
    def __init__(self, backend, validate_observation, validate_command, *, nworld, enabled=False,
                 training=False, heuristics=Heuristics(), distance_p95=1.):
        if not enabled:
            raise ValueError('RL wrapper is default OFF')
        if (type(training) is not bool or type(nworld) is not int or nworld <= 0
                or not math.isfinite(distance_p95) or distance_p95 <= 0):
            raise ValueError('invalid RL wrapper configuration')
        if not training and heuristics != Heuristics():
            raise ValueError('reward heuristics are training-only')
        self.backend, self.validate = backend, validate_observation
        self.validate_command = validate_command
        self.initialized = False
        self.nworld, self.training = nworld, training
        self.heuristics, self.distance_p95 = heuristics, distance_p95
        self.previous = [None] * nworld
        self.done_latched = [False] * nworld
        self.terminal = [True] * nworld
        self.training_privileged_reward_reads = 0
        self.training_privileged_critic_reads = 0

    def actor_inputs(self):
        result = []
        for i in range(self.nworld):
            observation, jpegs = self.backend.read_actor(i)
            self.validate(observation)
            if any(type(jpg) is not bytes for jpg in jpegs):
                raise ValueError('own JPEG bytes required')
            result.append(ActorInput(deepcopy(observation), tuple(jpegs)))
        return tuple(result)

    def _truth(self, i):
        if not self.training:
            raise RuntimeError('privileged reads unavailable during evaluation')
        truth, critic = self.backend.read_training(i)
        if not all(math.isfinite(v) for v in critic):
            raise ValueError('nonfinite training critic input')
        self.training_privileged_reward_reads += 1
        self.training_privileged_critic_reads += 1
        return truth, tuple(critic)

    def reset(self, plans, indices=None):
        indices = tuple(range(self.nworld)) if indices is None else tuple(indices)
        if (not indices or len(set(indices)) != len(indices) or len(plans) != len(indices)
                or any(type(i) is not int or not 0 <= i < self.nworld for i in indices)):
            raise ValueError('one reset plan per unique world index required')
        if not self.initialized and set(indices) != set(range(self.nworld)):
            raise ValueError('first reset must initialize every world')
        self.backend.reset(deepcopy(plans), indices=indices)
        for i in indices:
            self.previous[i] = self._truth(i)[0] if self.training else None
            self.done_latched[i], self.terminal[i] = False, False
        self.initialized = True
        return self.actor_inputs()

    def step(self, actions):
        if not self.initialized:
            raise RuntimeError('reset required before step')
        if len(actions) != self.nworld:
            raise ValueError('one issued action per world required')
        for action in actions:
            if set(action) != {'command', 'done'} or type(action['done']) is not bool:
                raise ValueError('issued action whitelist mismatch')
            self.validate_command(action['command'])
        was_terminal = self.terminal.copy()
        if any(self.previous[i] is None for i in range(self.nworld)
               if self.training and not was_terminal[i]):
            raise RuntimeError('training world not reset')
        terminal = self.backend.step(deepcopy(actions))
        if len(terminal) != self.nworld or any(type(v) is not bool for v in terminal):
            raise ValueError('backend must return SIM/done-only terminal flags')
        if any(old and not new for old, new in zip(was_terminal, terminal)):
            raise ValueError('terminal world resumed without reset')
        training_outputs = []
        for i, action in enumerate(actions):
            if was_terminal[i]:
                training_outputs.append(None)
                continue
            first_done = action['done'] and not self.done_latched[i]
            self.done_latched[i] |= action['done']
            if self.training:
                after, critic = self._truth(i)
                reward = reward_transition(self.previous[i], after,
                    distance_p95=self.distance_p95, first_done=first_done,
                    terminal=terminal[i], heuristics=self.heuristics)
                training_outputs.append(TrainingOutput(reward, critic))
                self.previous[i] = after
            else:
                training_outputs.append(None)
        self.terminal = list(terminal)
        return self.actor_inputs(), tuple(terminal), tuple(training_outputs)
