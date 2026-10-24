"""Solo-carry student controller (mirror of harness/pairact_r1_student.py for ONE robot).

DERIVED / UNVERIFIED (solo-e2e/20261024): never run against a checkpoint.

Runs in the isolated actor process (``scripts/pairact_solo_student_worker.py``).
Inputs per tick are exactly: the robot's OWN camera JPEG and the command it
actually applied (request allowlist ``{'jpeg', 'issued'}``), plus the task
tuple and the own v7 clock. No GT, teacher, stage target or geometry is accepted.

The task tuple is built by ``harness.solo_carry_contract.instruction`` -- the
same function the teacher recorder uses -- so the deployed tuple is the
recorded tuple:
  grasp segment    (grasp | wait, cyan, west, none)   'wait' while the own READY is
                   pending without GO (the token the teacher demos used)
  release segment  (release, cyan, west, B)
The switch happens when the robot's OWN command-completion flag has been
continuously true for ``RELEASE_AFTER_S`` SIM s (the pair student's rule applied
to one robot); no truth, teacher phase or hold measurement decides it.
``finished`` is reported once the release ``done`` flag has been continuously
true for ``FINISH_AFTER_S``.

The chunk executor and READY/GO barrier are the pair student's classes
(``harness.pairact_r1.PairActChunkExecutor`` / ``PairActBarrier``), which live
on dsh/pairact-r1-dryrun and are NOT in the tree this branch was cut from; they
are injected (``executor_factory`` / ``barrier_factory``) and imported lazily
only when not given.
"""
from __future__ import annotations

import hashlib
from collections import deque
from copy import deepcopy

from harness import grasp_act_contract as c
from harness import solo_carry_contract as sc
from harness.pair_carry_recorder import DeadbandIssuedClock, OwnClock

MODE = 'pairact_solo_student_eval_v1'
RELEASE_AFTER_S = 3.     # same 3 s as the stable-lift hold, timed on the SIM clock
FINISH_AFTER_S = 1.5     # same passive tail as the teacher runner after carry done
REQUEST_KEYS = {'jpeg', 'issued'}
STATUS = sc.STATUS


class OwnInputs:
    """Own RGB refs + own issued commands + v7 clock; the tuple comes from the shared builder."""

    def __init__(self, robot_id, episode_id, initial_command, *, deadband=2):
        if robot_id != sc.ROBOT_ID:
            raise ValueError('solo student drives robot r1 only')
        self.robot_id, self.episode_id = robot_id, episode_id
        self.issued = deque([c.command(initial_command)] * c.HISTORY, maxlen=c.HISTORY)
        self.frames = deque()
        self.clock, self.index = OwnClock(DeadbandIssuedClock(deadband)), 0

    def observe(self, now, jpeg, *, skill, destination_zone):
        path = f'rgb/{self.robot_id}/{self.index:06d}.jpg'
        ref = {'path': path, 'sha256': hashlib.sha256(jpeg).hexdigest(), 't': now, 'robot_id': self.robot_id}
        self.frames.append((ref, jpeg))
        while len(self.frames) > 1 and self.frames[1][0]['t'] < now - c.MEMORY_S - .1:
            self.frames.popleft()
        refs = c.image_history([r for r, _ in self.frames], now)
        pixels = {r['path']: jpg for r, jpg in self.frames}
        s, kind, role, dest = sc.instruction(skill, destination_zone)
        obs = {'schema': c.SCHEMA, 'robot_id': self.robot_id,
               'sample_id': f'{self.episode_id}:{self.index}:{self.robot_id}', 't': now,
               'skill': s, 'object_kind': kind, 'role': role, 'destination_zone': dest,
               'rgb': refs, 'issued': list(self.issued),
               **self.clock.observe(s, kind, role, dest, now, self.issued[-1]['pwm'])}
        self.index += 1
        sc.validate_solo_observation(obs)
        return obs, [pixels[r['path']] for r in refs], path

    def issue(self, value):
        self.issued.append(c.command(value))


def _pair_parts():
    try:
        from harness.pairact_r1 import PairActBarrier, PairActChunkExecutor, RECOVERY_MODE
    except ImportError as error:   # pragma: no cover - depends on the other branch
        raise RuntimeError('harness.pairact_r1 is not in this tree (dsh/pairact-r1-dryrun); '
                           'inject executor_factory and barrier_factory') from error
    return PairActBarrier, PairActChunkExecutor, RECOVERY_MODE


class SoloStudentController:
    """One robot, one learned policy, no teacher."""

    def __init__(self, predict, episode_id, initial, *, robot_id=sc.ROBOT_ID, executor_factory=None,
                 barrier_factory=None, deadband=2):
        if executor_factory is None or barrier_factory is None:
            barrier, executor, recovery = _pair_parts()
            executor_factory = executor_factory or (lambda p: executor(p, done_recovery=recovery))
            barrier_factory = barrier_factory or (lambda: barrier(place_sync='off'))
        self.rid = robot_id
        self.inputs = OwnInputs(robot_id, episode_id, initial, deadband=deadband)
        self.executor, self.barrier = executor_factory(predict), barrier_factory()
        self.segment = 'grasp'
        self.permit = False
        self.proposal = None
        self.done = False
        self.done_since = None
        self.switch_t = self.finish_t = None
        self.events = []

    def _token(self):
        if self.segment == 'release':
            return sc.CARRY_SKILL, sc.CARRY_DESTINATION
        waiting = self.barrier.pending is not None and not self.permit
        return ('wait' if waiting else 'grasp'), sc.GRASP_DESTINATION

    def propose(self, now, robots):
        """robots[rid] = {'jpeg': bytes, 'issued': applied command}. Returns the READY boolean
        and the logged student observation (no pixels)."""
        if set(robots) != {self.rid} or set(robots[self.rid]) != REQUEST_KEYS:
            raise ValueError('own camera + own issued command only')
        req = robots[self.rid]
        skill, dest = self._token()
        obs, jpegs, path = self.inputs.observe(now, req['jpeg'], skill=skill, destination_zone=dest)
        proposal, done = self.executor.step(obs, jpegs)
        self.barrier.propose(proposal, done, req['issued'], stage=self.executor.stage)
        if self.barrier.blocked:
            self.executor.discard_pending()
        self.proposal = (proposal, done, req['issued'])
        return {self.rid: {'ready': bool(self.barrier.ready), 'observation': obs, 'rgb_path': path,
                           'stage': self.executor.stage}}

    def issue(self, now, permits):
        if set(permits) != {self.rid} or type(permits[self.rid]) is not bool:
            raise ValueError('protocol permits only')
        self.permit = permits[self.rid]
        proposal, done, previous = self.proposal
        value, done = self.barrier.issue(now, previous, proposal, done, self.permit)
        if self.barrier.blocked or (self.barrier.ready and not self.permit):
            self.executor.discard_pending()
        self.inputs.issue(value)
        self.done = bool(done)
        self.done_since = (now if self.done_since is None else self.done_since) if done else None
        out = {self.rid: {'command': value, 'done': bool(done), 'stage': self.executor.stage,
                          'segment': self.segment, 'permit': self.permit, 'blocked': bool(self.barrier.blocked)}}
        self.proposal = None
        self._sequence(now)
        return out

    def _held(self, now, span):
        return self.done_since is not None and now - self.done_since >= span - 1e-8

    def _sequence(self, now):
        if self.segment == 'grasp' and self._held(now, RELEASE_AFTER_S):
            self.segment, self.switch_t, self.done_since = 'release', now, None
            self.executor.discard_pending()
            self.events.append({'t': now, 'event': 'release_instruction', 'source': 'own_done_flag'})
        elif self.segment == 'release' and self.finish_t is None and self._held(now, FINISH_AFTER_S):
            self.finish_t = now
            self.events.append({'t': now, 'event': 'finished', 'source': 'own_release_done_flag'})

    @property
    def finished(self):
        return self.finish_t is not None

    def summary(self):
        return {'mode': MODE, 'status': STATUS, 'segment': self.segment, 'release_instruction_t': self.switch_t,
                'finished_t': self.finish_t, 'events': deepcopy(self.events),
                'barrier_events': deepcopy(self.barrier.events),
                'clock_resets': self.inputs.clock.inner.resets, 'teacher_actions': 0, 'truth_inputs': 0}
