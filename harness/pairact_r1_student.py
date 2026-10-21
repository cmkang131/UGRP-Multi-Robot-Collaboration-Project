"""P5 student controller for the pairact-r1 learned pair-carry ACT (default OFF).

Runs in the isolated actor process (``scripts/pairact_r1_student_worker.py``)
next to the checkpoint; the MJWarp runner only sends each robot's OWN camera
JPEG and the command it actually applied, and only receives commands back.

Inputs per robot are exactly the student contract: own RGB history, own 16
issued commands, task tokens (skill, object_kind, role, destination_zone) and
own v7 clocks (deadband 2). No GT, teacher, partner pose, stage target or
geometry is accepted (the request allowlist is checked here and in the worker).

Instruction sequence (pre-registered, PAIRACT_R1_EVAL_PREREG_DRAFT.json):
  grasp segment   skill 'grasp' (or 'wait' while the own READY is pending
                  without GO, the same token the teacher demos used), dest 'none'
  release segment skill 'release', destination 'B'
The switch happens for BOTH robots when both robots' own command-completion
flags (``done``) have been continuously true for ``RELEASE_AFTER_S`` SIM s in
the grasp segment. The flags are booleans on the same message channel as
READY; no truth, teacher phase or hold measurement decides the switch.
``finished`` is reported when both robots' release ``done`` flags have been
continuously true for ``FINISH_AFTER_S``.
"""
from __future__ import annotations

import hashlib
from collections import deque
from copy import deepcopy

from harness import grasp_act_contract as c
from harness.pairact_r1 import (DeadbandIssuedClock, PairActBarrier, PairActChunkExecutor, PLACE_SYNC_MODE,
                                RECOVERY_MODE, STAGES)

MODE = 'pairact_r1_student_eval_v1'
OBJECT_KIND = 'long_beam'
DESTINATION = 'B'
RELEASE_AFTER_S = 3.     # same 3 s as the joint-hold gate, timed on the shared SIM clock
FINISH_AFTER_S = 1.5     # same passive tail as the teacher runner after carry done
REQUEST_KEYS = {'jpeg', 'issued'}
SHADOW_KEYS = {'jpeg', 'applied'}


class OwnInputs:
    """Own RGB refs + own issued commands + v7 clock (grasp_act_rollout.OwnHistory with
    the deadband-2 clock and an explicit destination token)."""

    def __init__(self, robot_id, episode_id, initial_command, *, deadband=2):
        self.robot_id, self.episode_id = robot_id, episode_id
        self.issued = deque([c.command(initial_command)] * c.HISTORY, maxlen=c.HISTORY)
        self.frames = deque()
        self.clock, self.index = DeadbandIssuedClock(deadband), 0

    def observe(self, now, jpeg, *, skill, role, destination_zone):
        path = f'rgb/{self.robot_id}/{self.index:06d}.jpg'
        ref = {'path': path, 'sha256': hashlib.sha256(jpeg).hexdigest(), 't': now, 'robot_id': self.robot_id}
        self.frames.append((ref, jpeg))
        while len(self.frames) > 1 and self.frames[1][0]['t'] < now - c.MEMORY_S - .1:
            self.frames.popleft()
        refs = c.image_history([r for r, _ in self.frames], now)
        pixels = {r['path']: jpg for r, jpg in self.frames}
        instruction = (skill, OBJECT_KIND, role, destination_zone)
        obs = {'schema': c.SCHEMA, 'robot_id': self.robot_id,
               'sample_id': f'{self.episode_id}:{self.index}:{self.robot_id}', 't': now,
               'skill': skill, 'object_kind': OBJECT_KIND, 'role': role,
               'destination_zone': destination_zone, 'rgb': refs, 'issued': list(self.issued),
               **self.clock.observe(instruction, now, self.issued[-1]['pwm'])}
        self.index += 1
        c.validate_observation(obs)
        return obs, [pixels[r['path']] for r in refs], path

    def issue(self, value):
        self.issued.append(c.command(value))


class PairStudentController:
    """Two robots, one learned policy each (same checkpoint), no teacher."""

    def __init__(self, predict, roles, episode_id, initial, *, done_recovery=RECOVERY_MODE, place_sync='off',
                 deadband=2):
        if sorted(roles.values()) != ['blue', 'teal']:
            raise ValueError('one robot per beam end required')
        if place_sync not in ('off', PLACE_SYNC_MODE):
            raise ValueError('unknown place sync mode')
        if place_sync != 'off':
            raise NotImplementedError('place_sync needs a second protocol barrier in the runner (r1 config: off)')
        self.roles = dict(roles)
        self.inputs = {r: OwnInputs(r, episode_id, initial[r], deadband=deadband) for r in roles}
        self.executors = {r: PairActChunkExecutor(predict, done_recovery=done_recovery) for r in roles}
        self.barriers = {r: PairActBarrier(place_sync=place_sync) for r in roles}
        self.segment = 'grasp'
        self.permits = {r: False for r in roles}
        self.proposals = {}
        self.done = {r: False for r in roles}
        self.done_since = {r: None for r in roles}
        self.switch_t = self.finish_t = None
        self.events = []
        self.shadow_ticks = 0

    def _token(self, rid):
        if self.segment == 'release':
            return 'release', DESTINATION
        b = self.barriers[rid]
        waiting = b.pending is not None and not self.permits[rid]
        return ('wait' if waiting else 'grasp'), 'none'

    def propose(self, now, robots):
        """robots[rid] = {'jpeg': bytes, 'issued': applied command}. Returns READY booleans
        and the logged student observations (no pixels)."""
        if set(robots) != set(self.roles) or any(set(v) != REQUEST_KEYS for v in robots.values()):
            raise ValueError('own camera + own issued command only')
        out = {}
        for rid, req in robots.items():
            skill, dest = self._token(rid)
            obs, jpegs, path = self.inputs[rid].observe(now, req['jpeg'], skill=skill, role=self.roles[rid],
                                                        destination_zone=dest)
            ex, barrier = self.executors[rid], self.barriers[rid]
            proposal, done = ex.step(obs, jpegs)
            barrier.propose(proposal, done, req['issued'], stage=ex.stage)
            if barrier.blocked:
                ex.discard_pending()
            self.proposals[rid] = (proposal, done, req['issued'])
            out[rid] = {'ready': bool(barrier.ready), 'observation': obs, 'rgb_path': path, 'stage': ex.stage}
        return out

    def issue(self, now, permits):
        if set(permits) != set(self.roles) or any(type(v) is not bool for v in permits.values()):
            raise ValueError('protocol permits only')
        self.permits = dict(permits)
        out = {}
        for rid, (proposal, done, previous) in self.proposals.items():
            barrier, ex = self.barriers[rid], self.executors[rid]
            value, done = barrier.issue(now, previous, proposal, done, permits[rid])
            if barrier.blocked or (barrier.ready and not permits[rid]):
                ex.discard_pending()
            self.inputs[rid].issue(value)
            self.done[rid] = bool(done)
            if done:
                self.done_since[rid] = now if self.done_since[rid] is None else self.done_since[rid]
            else:
                self.done_since[rid] = None
            out[rid] = {'command': value, 'done': bool(done), 'stage': ex.stage, 'segment': self.segment,
                        'permit': permits[rid], 'blocked': bool(barrier.blocked)}
        self.proposals = {}
        self._sequence(now)
        return out

    def shadow(self, now, robots, *, predict=True):
        """Hybrid carry segment (default unused): the code drives, the student only watches.

        robots[rid] = {'jpeg': own camera bytes, 'applied': the code command applied at ``now``}.
        The own observation is built exactly as in ``propose`` (own RGB + own issued history +
        v7 clock), the policy may run for the log (``predict``), its proposal is discarded, and
        the command the robot actually executed is appended to the own issued history, so the
        history after hand-back holds the real (code) commands. Barrier, permits and the
        segment sequence are not touched; done flags stay cleared."""
        if self.segment != 'release':
            raise ValueError('shadow is only valid after the release instruction (hybrid carry segment)')
        if set(robots) != set(self.roles) or any(set(v) != SHADOW_KEYS for v in robots.values()):
            raise ValueError('own camera + own applied command only')
        out = {}
        for rid, req in robots.items():
            obs, jpegs, path = self.inputs[rid].observe(now, req['jpeg'], skill='release', role=self.roles[rid],
                                                        destination_zone=DESTINATION)
            ex = self.executors[rid]
            stage = None
            if predict:
                ex.step(obs, jpegs)
                stage = ex.stage
                ex.discard_pending()
            self.inputs[rid].issue(req['applied'])
            out[rid] = {'stage': stage, 'observation': obs, 'rgb_path': path}
        self.proposals = {}
        self.done_since = {r: None for r in self.roles}
        self.shadow_ticks += 1
        return out

    def _held(self, now, span):
        return all(s is not None and now - s >= span - 1e-8 for s in self.done_since.values())

    def _sequence(self, now):
        if self.segment == 'grasp' and self._held(now, RELEASE_AFTER_S):
            self.segment, self.switch_t = 'release', now
            self.done_since = {r: None for r in self.roles}
            for ex in self.executors.values():
                ex.discard_pending()
            self.events.append({'t': now, 'event': 'release_instruction', 'source': 'both_own_done_flags'})
        elif self.segment == 'release' and self.finish_t is None and self._held(now, FINISH_AFTER_S):
            self.finish_t = now
            self.events.append({'t': now, 'event': 'finished', 'source': 'both_own_release_done_flags'})

    @property
    def finished(self):
        return self.finish_t is not None

    def summary(self):
        return {'mode': MODE, 'segment': self.segment, 'release_instruction_t': self.switch_t,
                'finished_t': self.finish_t, 'events': deepcopy(self.events),
                'barrier_events': {r: deepcopy(b.events) for r, b in self.barriers.items()},
                'clock_resets': {r: v.clock.resets for r, v in self.inputs.items()},
                'stages': list(STAGES), 'teacher_actions': 0, 'truth_inputs': 0,
                'shadow_ticks': self.shadow_ticks}
