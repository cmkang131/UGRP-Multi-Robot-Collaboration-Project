"""Single-robot carry: shared constants and the public instruction tuple.

DERIVED / UNVERIFIED (solo-e2e/20261024): no physics run has exercised any of
this. See docs/solo-e2e-20261024.md.

This module is the ONE place that builds the discrete instruction tuple
``(skill, object_kind, role, destination_zone)``. The teacher recorder
(``harness/solo_carry_recorder.py``) and the deploy student
(``harness/pairact_solo_student.py``) both call ``instruction()``, so the
recorded tuple and the deployed tuple cannot drift apart.

Cargo (2026-10-14 user decision "cargo v6": tile and can leave the study and
are replaced by the existing small boxes; the one-robot cargo kinds are the
four boxes): the carried object is the production dispatch box painted cyan,
the scenario's own unique ``cyan_1`` replica. Its role token is the only
v5-legal box role, ``grasp_act_contract.KIND_ROLES['cyan'] == ('west',)``, so
every recorded row is a plain v5 observation (``validate_observation`` and the
loader's ``context()`` accept it unchanged; no solo-only vocabulary).

Box geometry (all from the tree, no new number):
  * half extents (.017, .020, .016) m: ``sim/zone_arena.py:46`` ``BOX_HALF``,
    the replica of the production box ``sim/research_dispatch_arena.py:135-137``
    (dimensions (.034, .040, .032) m, mass .030 kg); 40 mm is the grip width
    across the jaws (``sim/zone_cargo.py:38-41``)
  * grasp height .024 m: ``sim/zone_cargo.py:34`` ``GRASP_Z_M`` (calibrated box
    grasp of ``scripts/zone_teacher.py``)
"""
from __future__ import annotations

import math

from harness import grasp_act_contract as contract

MODE = 'solo_box_v1'
MODES = ('off', MODE)
OBJECT_KIND = 'cyan'                # production box colour (sim/zone_arena.py:43-44); v6 one-robot kind
ROLE, = contract.KIND_ROLES[OBJECT_KIND]   # 'west': the only v5-legal role for a box
CARRY_SKILL = 'release'
CARRY_DESTINATION = 'B'
GRASP_DESTINATION = 'none'
GRASP_SKILLS = ('grasp', 'wait')
ROBOT_ID = 'r1'
TEACHER_END = 'teal'                # teacher-internal end token; never recorded
CARGO_ITEM_ID = 'cyan_1'            # the scenario's own cyan replica (configs/zone_study_scenarios_v6/*.json)
# sim/zone_arena.py:46 BOX_HALF = replica of sim/research_dispatch_arena.py:135-137 (.034 x .040 x .032 m)
CARGO_HALF_EXTENTS_M = (.017, .020, .016)
CARGO_MASS_KG = .030                # sim/research_dispatch_arena.py:136 (CargoSpec mass)
GRASP_Z_M = .024                    # sim/zone_cargo.py:34 calibrated box grasp height
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
    """The unchanged v5 observation checks plus: this task's box kind and its v5 role."""
    if row.get('role') != ROLE or row.get('object_kind') != OBJECT_KIND:
        raise ValueError(f'solo observation requires object_kind {OBJECT_KIND!r} and role {ROLE!r}')
    contract.validate_observation(row)
    return row


def _finite_pose(pose, what):
    if (not isinstance(pose, (list, tuple)) or len(pose) != 3
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in pose)):
        raise ValueError(f'{what} must be three finite numbers [x, y, yaw]')
    return tuple(float(v) for v in pose)


def validate_plan(plan):
    """Plan-provided solo fields (seed-fixed; setup-only, never a policy input).

    plan['solo_cargo'] = {'item_id': 'cyan_1', 'kind': 'cyan', 'pose': [x, y, yaw]}
        the scenario's own cyan box, moved to this pose at setup (the scene check that it
        exists and is the scene's only cyan item is ``solo_carry_visible.select_solo_cargo``)
    plan['solo_slot']  = {'zone': 'zone_B', 'pose': [x, y, yaw], 'half_extents_m': [hx, hy]}
        the designated zone-B slot rectangle (pose = rectangle centre and yaw).
    plan['roles']      = {'r1': 'teal'}   (teacher-internal end token; recorded role is 'west')
    plan['cargo_scene'] = 'cargo_v6'     (v6 scenario; hash-checked by sim.grasp_act_scene)
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
    if plan.get('cargo_scene') != 'cargo_v6':
        # 2026-10-14 user decision (cargo v6): new runs use the v6 scenarios (no tile / can); the
        # scenario hash and the no-tile/can check are sim.grasp_act_scene.validate_cargo_scene's
        raise ValueError("solo carry requires plan cargo_scene 'cargo_v6'")
    return plan


def rect_contains_point(rect, xy, margin=0.):
    """True if ``xy`` lies inside the rectangle (``pose`` = centre and yaw) shrunk by ``margin``."""
    cx, cy, yaw = rect['pose']
    hx, hy = rect['half_extents_m']
    dx, dy = xy[0] - cx, xy[1] - cy
    c, s = math.cos(yaw), math.sin(yaw)
    lx, ly = c*dx + s*dy, -s*dx + c*dy
    return abs(lx) <= hx - margin + 1e-9 and abs(ly) <= hy - margin + 1e-9


def footprint_corners(pose, half_extents):
    """The four floor corners of a rectangle footprint at ``pose`` = (x, y, yaw)."""
    x, y, yaw = pose
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x + c*sx*half_extents[0] - s*sy*half_extents[1], y + s*sx*half_extents[0] + c*sy*half_extents[1])
            for sx in (-1, 1) for sy in (-1, 1)]


def slot_contains(slot, pose, half_extents=CARGO_HALF_EXTENTS_M, margin=0.):
    """True if the box footprint (``half_extents`` x/y at ``pose`` incl. yaw) lies fully inside the slot rectangle.

    Both yaws are honoured: the slot rectangle's and the box's own. A rectangle is
    convex, so all four footprint corners inside <=> the whole footprint inside.
    """
    return all(rect_contains_point(slot, corner, margin) for corner in footprint_corners(pose, half_extents[:2]))


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
