"""P3 recorder for the GT pair-carry demonstrations (wired into the runner when
``record_training`` and ``pair_carry`` are both on; default off).

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

Clock (COLLECT_SPEC §4 on dsh/pairact-carry-r1): own clocks are the v7
issued clock with deadband 2 (``DeadbandIssuedClock``, same rule as
``harness/pairact_r1.py`` and act18 C2c ``ac274afeb``). The runner uses ONE
clock object per robot for the grasp and the carry segment, so
``pwm_elapsed_s`` is continuous across the hand-over like a deployed student.

Stage vocabulary: ``TEACHER_PHASE_TO_STAGE`` maps every ``teacher_phase``
this runner can write (visible_only grasp teacher + ``carry:<phase>``) onto
the 8 pairact-r1 stage-head classes. It is the same table as
``harness/pairact_r1.py`` on dsh/pairact-carry-r1 for every shared key
(test ``test_phase_table_matches_pairact_r1_copy``).
"""
from __future__ import annotations

import hashlib
from collections import deque

from harness import grasp_act_contract as contract

CLOCK_DEADBAND = 2              # v7 (C2c); 0 would be the v6 contract IssuedClock
CLOCK_TAG = 'v7_issued_clock_deadband_2'
STAGES = ('approach', 'alignment', 'ready', 'execute', 'carry', 'place', 'recover', 'complete')
# Grasp segment: VisibleOnlyGraspTeacher (sim/grasp_act_teacher_v3.py) + its
# GraspTeacher base (sim/grasp_act_teacher.py). Literal phases in those files
# (test ``test_phase_table_covers_every_teacher_phase_literal``).
GRASP_PHASE_TO_STAGE = {
    'approach': 'approach', 'search': 'approach',
    'align': 'alignment',
    'relook': 'recover',          # alignment recovery (align_relook_v1): withdraw READY
    'ready': 'ready',
    'pick': 'execute', 'verify': 'execute',
    'complete': 'complete', 'done': 'complete',
}
# Carry segment: harness/pair_carry_teacher_warp.py PHASES, written as 'carry:<phase>'.
CARRY_PHASE_TO_STAGE = {
    **{p: 'carry' for p in ('carry_hold', 'to_west_staging', 'rotate_door', 'to_door_entry', 'door_pass',
                            'to_east_staging', 'rotate_zone', 'to_zone', 'zone_settle')},
    **{p: 'place' for p in ('lower', 'open', 'raise', 'retreat')},
    'done': 'complete',
}
TEACHER_PHASE_TO_STAGE = {**GRASP_PHASE_TO_STAGE, **{'carry:' + k: v for k, v in CARRY_PHASE_TO_STAGE.items()}}


def stage_for(teacher_phase):
    """Stage-head class of one teacher label; unknown phases are an error, never guessed."""
    if teacher_phase not in TEACHER_PHASE_TO_STAGE:
        raise ValueError(f'unmapped teacher phase {teacher_phase!r}')
    return TEACHER_PHASE_TO_STAGE[teacher_phase]


class DeadbandIssuedClock:
    """v7 own-issued clock (copy of ``harness/pairact_r1.DeadbandIssuedClock``).

    A servo move of |dPWM| <= deadband from the previously observed issued PWM
    does not reset ``pwm_elapsed_s``; a larger move does. Instruction changes
    reset ``skill_elapsed_s``. deadband 0 == ``grasp_act_contract.IssuedClock``.
    """

    def __init__(self, deadband=CLOCK_DEADBAND):
        if deadband not in (0, CLOCK_DEADBAND):
            raise ValueError('registered deadband 0 or 2 required')
        self.deadband = deadband
        self.skill = self.started = self.changed = self.pwm = None
        self.resets = 0

    def observe(self, instruction, now, issued_pwm):
        now = contract.finite(now)
        if instruction != self.skill or self.started is None:
            self.skill, self.started = instruction, now
        current = {str(s): int(issued_pwm[str(s)]) for s in contract.SERVOS}
        if self.changed is None:
            self.changed = now
        elif any(abs(current[k] - self.pwm[k]) > self.deadband for k in current):
            self.changed = now
            self.resets += 1
        self.pwm = current
        return {'skill_elapsed_s': now - self.started, 'pwm_elapsed_s': now - self.changed}


CARRY_SKILL = 'release'
CARRY_DESTINATION = 'B'
SEGMENT = 'pair_carry_gt'
LABEL_FIELDS = ('sample_id', 'object_kind', 'skill', 'done', 'terminal_reason', 'clean_teacher_command',
                'applied_command', 'perturbed', 'teacher_phase', 'local_skill_sample', 'assignment_source',
                'skill_instruction_source', 'segment', 'destination_zone', 'teacher_input')


class OwnClock:
    """Student-side instruction clock: resets on (skill, kind, role, destination)
    like ``harness/grasp_act_rollout.OwnHistory`` (NOT on the teacher's private
    handoff flag). ``inner`` is the runner's per-robot v7 clock when given."""

    def __init__(self, inner=None):
        self.inner = inner if inner is not None else DeadbandIssuedClock()

    def observe(self, skill, kind, role, destination, now, issued_pwm):
        return self.inner.observe((skill, kind, role, destination), now, issued_pwm)


class CarryRecorder:
    """Per-robot buffers. ``history`` must be the runner's existing deque of
    applied commands (so grasp -> carry continuity of the 16-command window is
    kept); ``images`` the runner's own-RGB ref deque."""

    def __init__(self, rid, role, *, history, images, episode_id, clock=None):
        if role not in contract.KIND_ROLES['long_beam']:
            raise ValueError('long_beam role teal/blue required')
        self.rid, self.role, self.episode_id = rid, role, episode_id
        self.history, self.images = history, images
        self.clock = OwnClock(clock)
        self.done_recorded = False

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
        # Only the first done=true row is a training target; the 1.5 s passive
        # rows after the teacher finished are kept in raw but not local samples.
        local = not self.done_recorded
        if done:
            self.done_recorded = True
        return carry_label(f'{self.episode_id}:{i}:{self.rid}', clean=clean, applied=applied, done=done,
                           phase=phase, outcome=outcome, assignment_source=assignment_source, local=local)


def carry_label(sample_id, *, clean, applied, done, phase, outcome, assignment_source, local=True):
    """Teacher label row for one carry tick (also used by the runner, so the
    unrecorded P2 smoke writes exactly the P3 label shape)."""
    row = {'sample_id': sample_id, 'object_kind': 'long_beam', 'skill': CARRY_SKILL,
           'done': bool(done),
           'terminal_reason': 'command_sequence_complete' if done and outcome == 'command_sequence_complete' else None,
           'clean_teacher_command': clean, 'applied_command': applied, 'perturbed': False,
           'teacher_phase': 'carry:' + phase, 'local_skill_sample': bool(local),
           'assignment_source': assignment_source,
           'skill_instruction_source': 'demo GT pair-carry supervisor; student runtime instruction from LLM',
           'segment': SEGMENT, 'destination_zone': CARRY_DESTINATION,
           'teacher_input': 'simulator_truth_demo_exception'}
    assert tuple(row) == LABEL_FIELDS
    stage_for(row['teacher_phase'])
    return row


def new_buffers():
    """Fresh buffers with the contract lengths (for tests / a standalone recorder)."""
    return (deque(maxlen=contract.HISTORY),
            deque(maxlen=max(contract.HISTORY + 1, int(contract.MEMORY_S/.1) + 3)))


def recording_summary(recorders, clocks):
    """result.json block for COLLECT_SPEC §4 (clock tag, reset counts, vocabulary)."""
    return {'issued_clock': CLOCK_TAG, 'issued_clock_deadband': CLOCK_DEADBAND,
            'issued_clock_resets': {rid: int(getattr(c, 'resets', 0)) for rid, c in clocks.items()},
            'carry_done_recorded': {rid: r.done_recorded for rid, r in recorders.items()},
            'stage_vocabulary': 'pair_carry_recorder.TEACHER_PHASE_TO_STAGE', 'stages': list(STAGES)}
