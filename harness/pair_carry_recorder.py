"""P3 recorder hook design for the GT pair-carry demonstrations (not wired in P2).

Goal: carry/set-down samples land in the SAME student schema the beamact
loaders already read (``harness/grasp_act_contract.py`` v5 rows, converted by
``harness/grasp_act_data.py`` into ``ugrp.grasp_act.dataset.v1``), so the
grasp segment (skill ``grasp``) and the carry segment (skill ``release`` with
``destination_zone='B'``) of one episode are two consecutive segments of the
same per-robot stream.

Three files, never mixed (same split as beampair8 / beamact1):
  student-{rid}.jsonl  own RGB refs (4 lags) + own 16 issued commands + "number
                       tag" tokens (skill, object_kind, role, destination_zone)
                       + own clocks. Nothing else.
  teacher-{rid}.jsonl  label: clean/applied command, done, teacher_phase
                       ('carry:<phase>'), segment 'pair_carry_gt'.
  eval-only.jsonl      simulator truth (already written by the runner).

The "number tag" (번호표) is not a separate field in the ACT schema: it is the
discrete instruction tuple (skill, object_kind, role, destination_zone) that is
one-hot encoded into observation.state. For the carry segment it is
('release', 'long_beam', <teal|blue>, 'B').
"""
from __future__ import annotations

import hashlib
from collections import deque

from harness import grasp_act_contract as contract

CARRY_SKILL = 'release'
CARRY_DESTINATION = 'B'
SEGMENT = 'pair_carry_gt'
LABEL_FIELDS = ('sample_id', 'object_kind', 'skill', 'done', 'terminal_reason', 'clean_teacher_command',
                'applied_command', 'perturbed', 'teacher_phase', 'local_skill_sample', 'assignment_source',
                'skill_instruction_source', 'segment', 'destination_zone', 'teacher_input')


class OwnClock:
    """Student-side instruction clock: resets on (skill, kind, role, destination)
    like ``harness/grasp_act_rollout.OwnHistory`` (NOT on the teacher's private
    handoff flag)."""

    def __init__(self):
        self.inner = contract.IssuedClock()

    def observe(self, skill, kind, role, destination, now, issued_pwm):
        return self.inner.observe((skill, kind, role, destination), now, issued_pwm)


class CarryRecorder:
    """Per-robot buffers. ``history`` must be the runner's existing deque of
    applied commands (so grasp -> carry continuity of the 16-command window is
    kept); ``images`` the runner's own-RGB ref deque."""

    def __init__(self, rid, role, *, history, images, episode_id):
        if role not in contract.KIND_ROLES['long_beam']:
            raise ValueError('long_beam role teal/blue required')
        self.rid, self.role, self.episode_id = rid, role, episode_id
        self.history, self.images = history, images
        self.clock = OwnClock()

    def add_frame(self, i, now, jpg):
        """Return the rgb ref for a 640x480 own-camera JPEG saved at rgb/{rid}/{i:06d}.jpg."""
        ref = {'path': f'rgb/{self.rid}/{i:06d}.jpg', 'sha256': hashlib.sha256(jpg).hexdigest(),
               't': float(now), 'robot_id': self.rid}
        self.images.append(ref)
        return ref

    def student_row(self, i, now, previous_pwm):
        clocks = self.clock.observe(CARRY_SKILL, 'long_beam', self.role, CARRY_DESTINATION, now, previous_pwm)
        row = {'schema': contract.SCHEMA, 'robot_id': self.rid, 'sample_id': f'{self.episode_id}:{i}:{self.rid}',
               't': float(now), 'object_kind': 'long_beam', 'skill': CARRY_SKILL, 'role': self.role,
               'destination_zone': CARRY_DESTINATION,
               'rgb': contract.image_history(list(self.images), now), 'issued': list(self.history), **clocks}
        return contract.validate_observation(row)

    def label_row(self, i, *, clean, applied, done, phase, outcome, assignment_source='pairact_p2_fixed_roles'):
        return carry_label(f'{self.episode_id}:{i}:{self.rid}', clean=clean, applied=applied, done=done,
                           phase=phase, outcome=outcome, assignment_source=assignment_source)


def carry_label(sample_id, *, clean, applied, done, phase, outcome, assignment_source):
    """Teacher label row for one carry tick (also used by the runner, so the
    unrecorded P2 smoke writes exactly the P3 label shape)."""
    row = {'sample_id': sample_id, 'object_kind': 'long_beam', 'skill': CARRY_SKILL,
           'done': bool(done),
           'terminal_reason': 'command_sequence_complete' if done and outcome == 'command_sequence_complete' else None,
           'clean_teacher_command': clean, 'applied_command': applied, 'perturbed': False,
           'teacher_phase': 'carry:' + phase, 'local_skill_sample': True,
           'assignment_source': assignment_source,
           'skill_instruction_source': 'demo GT pair-carry supervisor; student runtime instruction from LLM',
           'segment': SEGMENT, 'destination_zone': CARRY_DESTINATION,
           'teacher_input': 'simulator_truth_demo_exception'}
    assert tuple(row) == LABEL_FIELDS
    return row


def new_buffers():
    """Fresh buffers with the contract lengths (for tests / a standalone recorder)."""
    return (deque(maxlen=contract.HISTORY),
            deque(maxlen=max(contract.HISTORY + 1, int(contract.MEMORY_S/.1) + 3)))


def wire_into_runner(*_args, **_kwargs):  # pragma: no cover
    """TODO(P3): call add_frame/student_row/label_row from the runner carry tick
    when record_training is on. Not wired in P2: the runner refuses
    record_training together with pair_carry (fail closed)."""
    raise NotImplementedError('P3: carry recording hook is designed but not wired')
