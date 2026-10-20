"""ACT skill client for the E2E-min nav runner (runner side; no torch import).

Splits the C2c evaluation stack across the same boundary in the opposite
direction: here the physics/render runner (nav ``.venv-warp``) is the parent
and the ACT actor runs in its own torch env as a JSON-lines child
(``scripts/e2e_min_act_server.py``).

Observation construction mirrors the frozen owner ``History``
([O] 0362037 ``scripts/warp_act_api.py:51-76``, ``:220-228``):

* own JPEG ring pruned to MEMORY_S + 0.1 s, subsampled by
  ``grasp_act_contract.image_history`` at RGB_LAGS_S;
* HISTORY (16) issued command rows, seeded with HISTORY copies of the
  command current at skill start;
* ``destination_zone`` = 'pickup_site' for release, 'none' otherwise;
* ``skill_elapsed_s`` from the v6 contract clock and ``pwm_elapsed_s`` from
  the C2c v7 own-issued deadband-2 clock (``act18_evaluate.py:116-159``: the
  evaluator re-applied only ``pwm_elapsed_s``).

Only own frames and own issued commands are read.  The command returned by
the actor is validated by the contract whitelist; ``record_issued`` must be
be fed every tick through the builder's ``observe_tick`` (route_tick
observers) so frames and issued history advance like the owner's History,
also during carry/hold ticks.  The clocks advance only on ACT ticks.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import subprocess
from collections import deque

from harness import grasp_act_contract as C

SCHEMA = 'ugrp.e2e_min.act_client.v1'
DEADBAND = 2
CLOCK_SERVOS = ('1', '3', '4', '5', '6')
KIND_ROLE = {'cyan': 'west', 'red': 'west', 'green': 'west', 'yellow': 'west'}


class DeadbandClock:
    """C2c v7 clock: pwm clock resets only when a servo moves by > DEADBAND."""

    def __init__(self, deadband=DEADBAND):
        if deadband != DEADBAND:
            raise ValueError('registered deadband 2 required')
        self.deadband = deadband
        self.skill = self.started = self.changed = self.pwm = None
        self.resets = 0

    def observe(self, instruction, now, issued_pwm):
        now = float(now)
        if instruction != self.skill or self.started is None:
            self.skill, self.started = instruction, now
        if self.changed is None:
            self.changed = now
        elif any(abs(int(issued_pwm[s]) - int(self.pwm[s])) > self.deadband for s in CLOCK_SERVOS):
            self.changed = now
            self.resets += 1
        self.pwm = {s: int(issued_pwm[s]) for s in CLOCK_SERVOS}
        return {'skill_elapsed_s': now - self.started, 'pwm_elapsed_s': now - self.changed}


class ActObservationBuilder:
    """Own-input student observation for one robot (owner History semantics)."""

    def __init__(self, robot, kind, role, initial_command, *, episode='e2e-min'):
        if kind not in KIND_ROLE or role not in C.KIND_ROLES[kind]:
            raise ValueError('ACT box kind/role required')
        self.robot, self.kind, self.role, self.episode = robot, kind, role, episode
        first = C.command(initial_command)
        self.issued = deque([copy.deepcopy(first) for _ in range(C.HISTORY)], maxlen=C.HISTORY)
        self.frames = deque()
        self.v6 = C.IssuedClock()
        self.v7 = DeadbandClock()
        self.index = 0
        self._seen = []

    def add_frame(self, now, jpeg):
        """Record this tick's own frame once (owner refresh runs every tick)."""
        now = float(now)
        if self.frames and self.frames[-1][0]['t'] >= now - 1e-9:
            if self.frames[-1][0]['t'] > now + 1e-9:
                raise ValueError('own frame time went backwards')
            return
        ref = dict(path=f'rgb/{self.robot}/{len(self._seen):06d}.jpg',
                   sha256=hashlib.sha256(jpeg).hexdigest(), t=now, robot_id=self.robot)
        self._seen.append(now)
        self.frames.append((ref, jpeg))
        while len(self.frames) > 1 and self.frames[1][0]['t'] < now - C.MEMORY_S - .1:
            self.frames.popleft()

    def observe_tick(self, robot, frame, now, command):
        """Per-tick observer hook (route_tick): own frame + actually issued command."""
        if robot != self.robot:
            raise ValueError('cross-robot observer call')
        self.add_frame(now, frame.jpeg)
        if command is not None:
            self.issue(command)

    def observe(self, now, jpeg, skill):
        if skill not in ('grasp', 'release'):
            raise ValueError('grasp or release skill required')
        self.add_frame(now, jpeg)
        refs = C.image_history([r for r, _ in self.frames], now)
        pixels = {r['path']: j for r, j in self.frames}
        destination = 'pickup_site' if skill == 'release' else 'none'
        instruction = (skill, self.kind, self.role, destination)
        pwm = self.issued[-1]['pwm']
        clock = self.v6.observe(instruction, now, pwm)
        clock['pwm_elapsed_s'] = self.v7.observe(instruction, now, pwm)['pwm_elapsed_s']
        obs = dict(schema=C.SCHEMA, robot_id=self.robot, sample_id=f'{self.episode}:{self.index}:{self.robot}',
                   t=float(now), skill=skill, object_kind=self.kind, role=self.role,
                   destination_zone=destination, rgb=refs, issued=copy.deepcopy(list(self.issued)), **clock)
        C.validate_observation(obs)
        self.index += 1
        return obs, tuple(pixels[r['path']] for r in refs)

    def issue(self, command):
        self.issued.append(copy.deepcopy(C.command(command)))


class ActServerTransport:
    """JSON-lines child process running the ACT actor (torch env)."""

    def __init__(self, argv, *, stderr_path):
        self.stderr = open(stderr_path, 'x')
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.stderr, text=True, bufsize=1)
        self.hello = self._receive()
        if self.hello.get('ready') is not True:
            raise RuntimeError('ACT server not ready: ' + json.dumps(self.hello)[:300])

    def _receive(self):
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError('ACT server closed (see stderr log)')
        reply = json.loads(line)
        if 'error' in reply:
            raise RuntimeError('ACT server error: ' + str(reply['error']))
        return reply

    def request(self, payload):
        self.proc.stdin.write(json.dumps(payload, allow_nan=False) + '\n')
        self.proc.stdin.flush()
        return self._receive()

    def step(self, robot, observation, jpegs):
        reply = self.request(dict(op='step', robot=robot, observation=observation,
                                  jpegs=[base64.b64encode(j).decode() for j in jpegs]))
        return reply['command'], reply['done']

    def reset(self, robot):
        self.request(dict(op='reset', robot=robot))

    def close(self):
        try:
            if self.proc.poll() is None:
                self.request(dict(op='close'))
        finally:
            self.proc.wait(timeout=60)
            self.stderr.close()


class ActSkillClient:
    """Executor-protocol adapter (harness/e2e_min_runtime.py) for one robot+skill."""

    def __init__(self, robot, skill, builder, transport):
        if skill not in ('grasp', 'release'):
            raise ValueError('grasp or release skill required')
        self.robot, self.skill, self.builder, self.transport = robot, skill, builder, transport
        self.started = False
        self.calls = 0

    def propose(self, frame, now):
        if frame.robot_id != self.robot:
            raise ValueError('cross-robot ACT input rejected')
        if not self.started:
            # Same as the evaluator's instruct + chunk.reset on a skill change.
            self.transport.reset(self.robot)
            self.started = True
        obs, jpegs = self.builder.observe(now, frame.jpeg, self.skill)
        command, done = self.transport.step(self.robot, obs, jpegs)
        self.calls += 1
        if type(done) is not bool:
            raise ValueError('ACT done flag must be bool')
        return dict(command=C.command(command), done=done)
