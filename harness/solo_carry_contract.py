"""Single-robot carry: shared constants and the public instruction tuple.

DERIVED / UNVERIFIED (solo-e2e/20261024): no physics run has exercised any of
this. See docs/solo-e2e-20261024.md.

This module is the ONE place that builds the discrete instruction tuple
``(skill, object_kind, role, destination_zone)``. The teacher recorder
(``harness/solo_carry_recorder.py``) and the deploy student
(``harness/pairact_solo_student.py``) both call ``instruction()``, so the
recorded tuple and the deployed tuple cannot drift apart.

Contract note (needs a user decision, see docs): the recording schema is
``ugrp.grasp_act.student.v5`` (``harness/grasp_act_contract.py``, pinned and not
edited here). Its vocabulary has no role ``'solo'``: ``KIND_ROLES['can']`` is
``('any',)`` and ``context()`` one-hot encodes ``ROLES`` which lacks ``'solo'``.
``validate_solo_observation`` therefore runs every v5 check with the role
swapped for the contract's only legal ``can`` role and then requires the
recorded role to be ``'solo'``. Rows written here validate under this module
only; the v5 ``context()`` encoder cannot encode them until the vocabulary
question is settled.
"""
from __future__ import annotations

import math

from harness import grasp_act_contract as contract

MODE = 'solo_box_v1'
MODES = ('off', MODE)
OBJECT_KIND = 'can'                 # sim/zone_cargo.py CATALOGUE['can']: 0.080 kg, solo tier
ROLE = 'solo'                       # public role token for the single-robot carry
CONTRACT_ROLE = contract.KIND_ROLES[OBJECT_KIND][0]   # 'any': the only v5-legal role for 'can'
CARRY_SKILL = 'release'
CARRY_DESTINATION = 'B'
GRASP_DESTINATION = 'none'
GRASP_SKILLS = ('grasp', 'wait')
ROBOT_ID = 'r1'
TEACHER_END = 'teal'                # teacher-internal end token; never recorded
CARGO_ITEM_ID = 'can_1'
ZONE = 'zone_B'
MAX_CARRY_CAP_S = 120.              # same finite-cap bound as the pair carry
STATUS = 'derived_unverified_no_physics_run'


def instruction(skill, destination_zone):
    """The public instruction tuple for this task. Recorder and student both use it."""
    if skill == CARRY_SKILL:
        if destination_zone != CARRY_DESTINATION:
            raise ValueError("release requires destination zone 'B'")
    elif skill in GRASP_SKILLS:
        if destination_zone != GRASP_DESTINATION:
            raise ValueError("grasp/wait use destination zone 'none'")
    else:
        raise ValueError(f'unknown solo skill {skill!r}')
    return (skill, OBJECT_KIND, ROLE, destination_zone)


def grasp_instruction(waiting):
    return instruction('wait' if waiting else 'grasp', GRASP_DESTINATION)


def carry_instruction():
    return instruction(CARRY_SKILL, CARRY_DESTINATION)


def row_tuple(row):
    return (row['skill'], row['object_kind'], row['role'], row['destination_zone'])


def validate_solo_observation(row):
    """v5 observation checks, with role ``'solo'`` required (see module docstring)."""
    if row.get('role') != ROLE or row.get('object_kind') != OBJECT_KIND:
        raise ValueError("solo observation requires object_kind 'can' and role 'solo'")
    contract.validate_observation({**row, 'role': CONTRACT_ROLE})
    return row


def _finite_pose(pose, what):
    if (not isinstance(pose, (list, tuple)) or len(pose) != 3
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in pose)):
        raise ValueError(f'{what} must be three finite numbers [x, y, yaw]')
    return tuple(float(v) for v in pose)


def validate_plan(plan):
    """Plan-provided solo fields (seed-fixed; setup-only, never a policy input).

    plan['solo_cargo'] = {'item_id': 'can_1', 'kind': 'can', 'pose': [x, y, yaw]}
    plan['solo_slot']  = {'zone': 'zone_B', 'pose': [x, y, yaw], 'half_extents_m': [hx, hy]}
        the designated zone-B slot rectangle (pose = rectangle centre and yaw).
    plan['roles']      = {'r1': 'teal'}   (teacher-internal end token; recorded role is 'solo')
    """
    if plan.get('roles') != {ROBOT_ID: TEACHER_END}:
        raise ValueError("solo carry requires plan roles {'r1': 'teal'} (one robot)")
    cargo = plan.get('solo_cargo')
    if not isinstance(cargo, dict) or set(cargo) != {'item_id', 'kind', 'pose'}:
        raise ValueError('plan solo_cargo = {item_id, kind, pose} required')
    if cargo['item_id'] != CARGO_ITEM_ID or cargo['kind'] != OBJECT_KIND:
        raise ValueError(f"solo cargo must be item {CARGO_ITEM_ID!r} of kind {OBJECT_KIND!r}")
    _finite_pose(cargo['pose'], 'solo_cargo pose')
    slot = plan.get('solo_slot')
    if not isinstance(slot, dict) or set(slot) != {'zone', 'pose', 'half_extents_m'}:
        raise ValueError('plan solo_slot = {zone, pose, half_extents_m} required')
    if slot['zone'] != ZONE:
        raise ValueError(f'solo slot must be in {ZONE}')
    _finite_pose(slot['pose'], 'solo_slot pose')
    half = slot['half_extents_m']
    if (not isinstance(half, (list, tuple)) or len(half) != 2
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not v > 0 for v in half)):
        raise ValueError('solo_slot half_extents_m must be two positive numbers')
    return plan


def slot_contains(slot, xy, radius, margin=0.):
    """True if a disc of ``radius`` at ``xy`` lies fully inside the slot rectangle (rect yaw honoured)."""
    cx, cy, yaw = slot['pose']
    hx, hy = slot['half_extents_m']
    dx, dy = xy[0] - cx, xy[1] - cy
    c, s = math.cos(yaw), math.sin(yaw)
    lx, ly = c*dx + s*dy, -s*dx + c*dy
    return abs(lx) <= hx - radius - margin + 1e-9 and abs(ly) <= hy - radius - margin + 1e-9


def validate_runner_args(solo_carry, *, pair_carry, teacher_profile, plan, probe, student_eval,
                         carry_cap_s, record_training=False, handoff_observation='off'):
    """Called by scripts/run_grasp_act_teacher.py before anything else uses solo_carry."""
    if solo_carry not in MODES:
        raise ValueError('unknown solo carry mode')
    if solo_carry == 'off':
        return
    if pair_carry != 'off':
        raise ValueError('solo carry and pair carry are mutually exclusive')
    if teacher_profile != 'visible_only':
        raise ValueError('solo carry requires teacher_profile visible_only (strict mode)')
    if probe:
        raise ValueError('solo carry is not a probe mode')
    if student_eval is not None:
        raise ValueError('solo student eval is not wired into the runner (TODO)')
    if not 0 < carry_cap_s <= MAX_CARRY_CAP_S:
        raise ValueError('finite carry cap required')
    if record_training and handoff_observation != 'visible_handoff_v1':
        raise ValueError('recording requires visible handoff observation')
    validate_plan(plan)
