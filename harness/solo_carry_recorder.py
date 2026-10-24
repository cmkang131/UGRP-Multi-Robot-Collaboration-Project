"""Recorder for the single-robot carry demonstrations (v5 recorder semantics).

DERIVED / UNVERIFIED (solo-e2e/20261024): never exercised by a physics run.

Semantics are those of ``harness/pair_carry_recorder.py`` (same three-file
split, same v7 deadband-2 own clock, same ``(skill, object_kind, role,
destination_zone)`` instruction tuple one-hot-style token). Differences:

* the tuple is built by ``harness.solo_carry_contract.instruction`` for BOTH
  the grasp and the carry segment: ``(grasp|wait, can, solo, none)`` then
  ``(release, can, solo, B)``. The teacher-internal end token (``teal``) and
  the teacher's private handoff flag never reach a recorded student row;
* one clock object per robot serves both segments and is keyed on the public
  tuple only, so ``skill_elapsed_s`` resets exactly when a deployed student's
  own tuple changes; ``pwm_elapsed_s`` is recorded as the clock reports it;
* the grasp segment is produced by the unchanged runner/teacher code, which
  writes the beam-era fields (``long_beam`` / ``teal`` / its own clock);
  ``rewrite_grasp_row`` replaces object_kind, role and both clock fields from
  the row's own already-recorded inputs (skill, t, last issued PWM).
"""
from __future__ import annotations

import hashlib
import json

from harness import grasp_act_contract as contract
from harness import solo_carry_contract as sc
from harness.pair_carry_recorder import DeadbandIssuedClock, OwnClock, stage_for

SEGMENT = 'solo_carry_gt'
LABEL_FIELDS = ('sample_id', 'object_kind', 'skill', 'done', 'terminal_reason', 'clean_teacher_command',
                'applied_command', 'perturbed', 'teacher_phase', 'local_skill_sample', 'assignment_source',
                'skill_instruction_source', 'segment', 'destination_zone', 'teacher_input')
STATUS = sc.STATUS


class SoloRecorder:
    """Per-robot buffers and clock for both segments of one solo episode."""

    def __init__(self, rid, *, history, images, episode_id):
        if rid != sc.ROBOT_ID:
            raise ValueError('solo carry records robot r1 only')
        self.rid, self.episode_id = rid, episode_id
        self.history, self.images = history, images
        self.clock = OwnClock(DeadbandIssuedClock())
        self.done_recorded = False
        self.grasp_rows = self.carry_rows = 0

    # ---- grasp segment (rows computed by the unchanged runner, tuple replaced)
    def rewrite_grasp_row(self, row):
        """Public tuple + recomputed clocks for a row the runner wrote in the grasp segment."""
        if row.get('role') == sc.ROLE:                 # already a solo row (carry rows pass through)
            return sc.validate_solo_observation(row)
        if row['destination_zone'] != sc.GRASP_DESTINATION or row['skill'] not in sc.GRASP_SKILLS:
            raise ValueError('only grasp/wait rows are rewritten')
        skill, kind, role, dest = sc.instruction(row['skill'], sc.GRASP_DESTINATION)
        clocks = self.clock.observe(skill, kind, role, dest, row['t'], row['issued'][-1]['pwm'])
        out = {**row, 'object_kind': kind, 'role': role, 'destination_zone': dest, **clocks}
        self.grasp_rows += 1
        return sc.validate_solo_observation(out)

    # ---- carry segment
    def add_frame(self, i, now, jpg):
        ref = {'path': f'rgb/{self.rid}/{i:06d}.jpg', 'sha256': hashlib.sha256(jpg).hexdigest(),
               't': float(now), 'robot_id': self.rid}
        self.images.append(ref)
        return ref

    def student_row(self, i, now, previous_pwm):
        skill, kind, role, dest = sc.carry_instruction()
        clocks = self.clock.observe(skill, kind, role, dest, now, previous_pwm)
        row = {'schema': contract.SCHEMA, 'robot_id': self.rid, 'sample_id': f'{self.episode_id}:{i}:{self.rid}',
               't': float(now), 'object_kind': kind, 'skill': skill, 'role': role, 'destination_zone': dest,
               'rgb': contract.image_history(list(self.images), now), 'issued': list(self.history), **clocks}
        self.carry_rows += 1
        return sc.validate_solo_observation(row)

    def label_row(self, i, *, clean, applied, done, phase, outcome, assignment_source='solo_e2e_fixed_roles'):
        local = not self.done_recorded
        if done:
            self.done_recorded = True
        return carry_label(f'{self.episode_id}:{i}:{self.rid}', clean=clean, applied=applied, done=done,
                           phase=phase, outcome=outcome, assignment_source=assignment_source, local=local)


def carry_label(sample_id, *, clean, applied, done, phase, outcome, assignment_source, local=True):
    row = {'sample_id': sample_id, 'object_kind': sc.OBJECT_KIND, 'skill': sc.CARRY_SKILL,
           'done': bool(done),
           'terminal_reason': 'command_sequence_complete' if done and outcome == 'command_sequence_complete' else None,
           'clean_teacher_command': clean, 'applied_command': applied, 'perturbed': False,
           'teacher_phase': 'carry:' + phase, 'local_skill_sample': bool(local),
           'assignment_source': assignment_source,
           'skill_instruction_source': 'demo GT solo-carry supervisor; student runtime instruction from LLM',
           'segment': SEGMENT, 'destination_zone': sc.CARRY_DESTINATION,
           'teacher_input': 'simulator_truth_demo_exception'}
    assert tuple(row) == LABEL_FIELDS
    stage_for(row['teacher_phase'])
    return row


class SoloStudentWriter:
    """File-like wrapper installed on the runner's student stream in solo mode."""

    def __init__(self, stream, recorder):
        self.stream, self.recorder = stream, recorder

    def write(self, text):
        row = self.recorder.rewrite_grasp_row(json.loads(text))
        return self.stream.write(json.dumps(row) + '\n')


class SoloLabelWriter:
    """Teacher-label stream: the object kind of grasp-segment labels becomes the solo cargo kind."""

    def __init__(self, stream):
        self.stream = stream

    def write(self, text):
        row = json.loads(text)
        if row.get('object_kind') == 'long_beam':
            row['object_kind'] = sc.OBJECT_KIND
        return self.stream.write(json.dumps(row) + '\n')


def recording_summary(recorders):
    return {'status': STATUS, 'issued_clock': 'v7_issued_clock_deadband_2',
            'instruction_tuples': {'grasp': list(sc.grasp_instruction(False)), 'carry': list(sc.carry_instruction())},
            'grasp_rows': {rid: r.grasp_rows for rid, r in recorders.items()},
            'carry_rows': {rid: r.carry_rows for rid, r in recorders.items()},
            'carry_done_recorded': {rid: r.done_recorded for rid, r in recorders.items()},
            'issued_clock_resets': {rid: int(getattr(r.clock.inner, 'resets', 0)) for rid, r in recorders.items()}}
