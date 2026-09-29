"""Physical realisation of the integrated zone study's hidden events (B6, #224).

EVALUATION SIDE ONLY: experimenter-injected disturbances. The physics owner
(``scripts/run_zone_study_integration.StudyTeamHost``) is the only caller.
Nothing here produces a robot input, message, command row or wake; a robot
learns of an event only through its own camera (or through what a peer saw and
said). Every effect is logged for ``eval_only/hidden_events.jsonl`` only.

No frozen source is edited (PR #257 review P1-G): ``harness/zone_own_team_host.py``
and the other scene-contract sources of ``scripts/zone_pair_dev_contract.py``,
``sim/camera_robot_port.py`` and ``sim/multi_masterpi_production.py`` stay
byte-for-byte. The three mechanisms:

* :func:`hidden_event_scene` appends the scenario's obstacles as parked static
  (mocap) boxes by wrapping the transform of the scene INSTANCE the host
  receives through its existing ``scene=`` argument. A scenario without
  obstacles never calls it, so its scene XML is exactly the previous one.
* :class:`ActuatorFaults` wraps ``_physics_step_for`` of ONE world instance.
  Inside each physics step it forces the wheel motor state and command of a held
  robot to 0 (``robot_hold``: wheels blocked at the actuator) and drives the
  gripper position actuators of a faulted robot to the open target
  (``item_dropped``: a gripper servo fault, ``GRIPPER_FAULT_S`` long). After the
  step the issued values are restored, so the port's issued-command state, the
  robot's ``servo_command_pulses`` and the host's command rows never show the
  fault. Contact, friction, joint limits and the contact profile are unchanged
  (AGENTS.md: normal physics stays; no weld, no contact edit).
* :class:`HiddenEventPhysics` fires the due events of a
  ``harness.zone_study_referee.HiddenEventSchedule`` and logs each effect.
"""
from __future__ import annotations

import copy
import math

import numpy as np

from harness.zone_study_contract import ROBOTS, ContractViolation

PARK_Z_M = -5.
HIDDEN_BODY_PREFIX = 'hidden_obstacle__'
#: Gripper servo fault of ``item_dropped``: the holding robot's gripper actuator
#: is driven to this PWM target (MasterPi open, ``scripts/zone_teacher.OPEN``;
#: ``sim/masterpi_dynamics_v2`` maps >= 2000 to zero closure) for this long.
GRIPPER_FAULT_PULSE = 2000
GRIPPER_FAULT_S = 1.0
HIDDEN_EVENT_PROFILE = 'zone_study_hidden_events.v2'
REALISATION = {
    'passage_blocked': 'a parked static (mocap) box built into the scene XML moves into the opening',
    'obstruction_added': 'as passage_blocked, anywhere',
    'passage_cleared': "the passage's parked obstacle returns below the floor",
    'item_moved': 'free joint set to to_pose_m (x, y, yaw; height kept) with zero velocity; no effect while held',
    'item_dropped': (f'gripper servo fault: every holding robot\'s gripper actuator is driven open '
                     f'(PWM {GRIPPER_FAULT_PULSE}) inside each physics step for {GRIPPER_FAULT_S} s; issued '
                     'commands and command rows unchanged; normal contact physics; no effect when not held'),
    'robot_hold': ("wheels blocked at the actuator: the robot's wheel motor state and command are 0 inside "
                   'each physics step for duration_s; its issued commands and command rows stay as issued'),
}


def profile(kinds) -> dict:
    """The realisation of the given event kinds (hashed into the run bundle by the schedule)."""
    return {'profile': HIDDEN_EVENT_PROFILE, 'gripper_fault_pulse': GRIPPER_FAULT_PULSE,
            'gripper_fault_s': GRIPPER_FAULT_S, 'park_z_m': PARK_Z_M,
            'realisation': {k: REALISATION[k] for k in sorted(kinds)}}


# ---------------------------------------------------------------------------
# Scene: parked obstacles, through the host's existing scene= argument

def obstacle_xml(obstacles):
    """XML transform adding each hidden obstacle as a parked static (mocap) box below the floor."""
    if not obstacles:
        raise ContractViolation('obstacle_xml needs at least one obstacle')
    bodies = ''.join(
        f'<body name="{HIDDEN_BODY_PREFIX}{o["obstacle_id"]}" mocap="true" pos="0 0 {PARK_Z_M}">'
        f'<geom name="{HIDDEN_BODY_PREFIX}{o["obstacle_id"]}_geom" type="box" '
        f'size="{o["half_extents_m"][0]} {o["half_extents_m"][1]} {float(o["height_m"]) / 2}" '
        f'rgba=".45 .33 .20 1" contype="1" conaffinity="1"/></body>' for o in obstacles)

    def transform(xml):
        head, sep, tail = xml.rpartition('</worldbody>')
        if not sep:
            raise ContractViolation('scene XML has no </worldbody> for hidden obstacles')
        return head + bodies + sep + tail
    return transform


def _cargo_free_twin(base):
    """``TaggedCargoZoneScene`` without cargo that equals a plain ``TaggedZoneScene``.

    ``own_scene`` accepts an injected scene only of the two cargo scene classes;
    without cargo items (and without a cargo contact profile on the scene)
    ``TaggedCargoZoneScene`` builds exactly the ``TaggedZoneScene`` XML (its own
    docstring and tests). The twin keeps the episode's goal and extra boxes and
    must reproduce the base config, inventory and bounds, or this refuses.
    """
    from sim.zone_cargo_scene import CARGO_SET_SCHEMA
    from sim.zone_landmarks import TaggedZoneScene
    from sim.zone_tagged_cargo_scene import TaggedCargoZoneScene
    if type(base) is not TaggedZoneScene:
        raise ContractViolation(f'hidden obstacles: unsupported scene class {type(base).__name__}')
    selected = copy.deepcopy(base.scene)
    selected['cargo_contact_profile'] = None
    selected['params'] = {**selected.get('params', {}), 'cargo_set': {'schema': CARGO_SET_SCHEMA, 'items': []}}
    twin = TaggedCargoZoneScene(selected, base.base_dir)
    same = ({k: v for k, v in twin.config.items() if k != 'cargo_set'} == base.config
            and twin.inventory == base.inventory and twin.bounds == base.bounds
            and twin.engine_layout == base.engine_layout and twin.selection == base.selection and not twin.cargo)
    if not same:
        raise ContractViolation('hidden obstacles: the cargo-free scene twin differs from the base scene')
    return twin


def hidden_event_scene(spec, contact_profile, obstacles, scene=None):
    """The scene the host would build, with the obstacles appended to its XML transform."""
    from sim.zone_geometry_scene import GeometryCargoZoneScene
    from sim.zone_own_scene_provider import own_scene
    from sim.zone_tagged_cargo_scene import TaggedCargoZoneScene
    base = own_scene(spec, contact_profile, scene)
    if not isinstance(base, (TaggedCargoZoneScene, GeometryCargoZoneScene)):
        base = _cargo_free_twin(base)
    add, inner = obstacle_xml(obstacles), base.transform

    def transform(xml):
        return add(inner(xml))
    base.transform = transform                       # this instance only; the class is untouched
    if own_scene(spec, contact_profile, base) is not base:
        raise ContractViolation('hidden obstacles: the host would not accept the wrapped scene')
    return base


# ---------------------------------------------------------------------------
# Actuator faults inside the physics step

class ActuatorFaults:
    """Per-step actuator overrides of one world; the issued commands are restored after each step."""

    def __init__(self, world, log):
        if '_physics_step_for' in vars(world):
            raise ContractViolation('this world already has a wrapped physics step')
        self.world, self.log = world, log
        self._inner = world._physics_step_for
        self.wheels: dict[str, tuple[float, str]] = {}     # rid -> (until SIM s, event id)
        self.grippers: dict[str, tuple[float, str]] = {}
        self.fault_steps = {'wheels_held': 0, 'gripper_open': 0}
        self._open = {}
        world._physics_step_for = self._step

    def hold_wheels(self, rid, until, event_id):
        self.wheels[rid] = (float(until), event_id)

    def open_gripper(self, rid, until, event_id):
        self.grippers[rid] = (float(until), event_id)

    def _open_targets(self, rid):
        """(actuator, ctrl) of the open gripper, clipped like ``set_servo_pulses`` does."""
        if rid not in self._open:
            c, m = self.world.controllers[rid], self.world.model
            value = c.pulse_to_joint_targets({1: GRIPPER_FAULT_PULSE})['gripper']
            rows = []
            for aid, jid in zip(c.gripper_act, c.gripper_joint):
                lo, hi = (float(v) for v in m.jnt_range[jid])
                rows.append((int(aid), max(lo, min(hi, value)) if int(m.jnt_limited[jid]) else float(value)))
            self._open[rid] = rows
        return self._open[rid]

    def _expire(self, now):
        for table, effect in ((self.wheels, 'wheels_released'), (self.grippers, 'gripper_fault_cleared')):
            for rid, (until, event_id) in sorted(table.items()):
                if now + 1e-9 >= until:            # the schedule's own tolerance
                    del table[rid]
                    self.log.append({'t': round(now, 4), 'event_id': event_id, 'robot_id': rid, 'effect': effect})

    def _step(self, active, commands=None):
        world, data = self.world, self.world.data
        self._expire(float(data.time))
        if commands is not None:
            # The wrapped step's own first action, done before the override so it
            # cannot bypass a hold; the step then runs with commands=None.
            active.motor_command[:] = np.clip(np.asarray(commands, dtype=float), -1.0, 1.0)
        held = [world.controllers[rid] for rid in sorted(self.wheels)]
        issued = [c.motor_command.copy() for c in held]
        saved = {}
        for c in held:
            c.motor_command[:] = 0.
            c.motor_state[:] = 0.
        for rid in sorted(self.grippers):
            for aid, target in self._open_targets(rid):
                saved[aid] = float(data.ctrl[aid])
                data.ctrl[aid] = target
        try:
            self._inner(active, None)
        finally:
            for c, command in zip(held, issued):
                c.motor_command[:] = command                # the issued command; the wheel state stays physical
            for aid, value in saved.items():
                data.ctrl[aid] = value                      # the issued gripper target
        self.fault_steps['wheels_held'] += len(held)
        self.fault_steps['gripper_open'] += bool(saved)


# ---------------------------------------------------------------------------
# Event realisation

def finger_holders(data, item_geoms, finger_geoms):
    """Robots whose finger geoms touch any of ``item_geoms`` (simulator truth; evaluation/physics only)."""
    out = set()
    for i in range(data.ncon):
        pair = {int(data.contact[i].geom1), int(data.contact[i].geom2)}
        if pair & item_geoms:
            out.update(r for r in ROBOTS if pair & (finger_geoms[r][0] | finger_geoms[r][1]))
    return sorted(out)


class HiddenEventPhysics:
    """Fire the schedule's due events on the world; log every effect (evaluation only)."""

    def __init__(self, world, schedule, *, objects, item_geoms, finger_geoms):
        self.world, self.schedule = world, schedule
        self.objects, self.item_geoms, self.finger_geoms = objects, item_geoms, finger_geoms
        self.log: list[dict] = []
        self._parked: dict[str, int] = {}
        kinds = {e['kind'] for e in schedule.events}
        self.faults = ActuatorFaults(world, self.log) if kinds & {'robot_hold', 'item_dropped'} else None

    def tick(self, now):
        for event in self.schedule.due(now):
            self.log.append({'t': round(float(now), 4), **self.apply(event, float(now))})

    def holders(self, item):
        return finger_holders(self.world.data, self.item_geoms.get(item, set()), self.finger_geoms)

    def apply(self, event, now):
        import mujoco
        m, d = self.world.model, self.world.data
        kind, target = event['kind'], event['target']
        row = {'event_id': event['event_id'], 'kind': kind, 'at_sim_s': event['trigger']['at_sim_s']}
        if kind == 'robot_hold':
            duration = target.get('duration_s')
            if (isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration)
                    or duration <= 0 or target.get('robot_id') not in ROBOTS):
                raise ContractViolation(f'{event["event_id"]}: robot_hold needs a robot id and a positive finite '
                                        'duration_s')
            self.faults.hold_wheels(target['robot_id'], now + duration, event['event_id'])
            return {**row, 'robot_id': target['robot_id'], 'effect': 'wheels_held',
                    'until_sim_s': round(now + duration, 4)}
        if kind in ('passage_blocked', 'obstruction_added', 'passage_cleared'):
            if kind == 'passage_cleared':
                mid = self._parked.pop(target['passage'], None)
                if mid is None:
                    return {**row, 'effect': 'none_no_obstacle'}
                pos = [0., 0., PARK_Z_M]
            else:
                ob = target['obstacle']
                bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, HIDDEN_BODY_PREFIX + ob['obstacle_id'])
                if bid < 0 or int(m.body_mocapid[bid]) < 0:
                    raise ContractViolation(f'{event["event_id"]}: obstacle {ob["obstacle_id"]!r} is not in the scene')
                mid = int(m.body_mocapid[bid])
                pos = [float(ob['center_m'][0]), float(ob['center_m'][1]), float(ob['height_m']) / 2]
                if kind == 'passage_blocked':
                    self._parked[target['passage']] = mid
            d.mocap_pos[mid] = pos
            mujoco.mj_forward(m, d)
            return {**row, 'effect': 'obstacle_moved', 'pos_m': [round(v, 4) for v in pos]}
        item = target['item_id']
        holders = self.holders(item)
        if kind == 'item_moved':
            if holders:
                return {**row, 'effect': 'none_item_held', 'holders': holders}
            bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, self.objects[item]['body_name'])
            jid = int(m.body_jntadr[bid])
            if jid < 0 or int(m.jnt_type[jid]) != int(mujoco.mjtJoint.mjJNT_FREE):
                raise ContractViolation(f'{item}: item_moved needs a free joint')
            q, v = int(m.jnt_qposadr[jid]), int(m.jnt_dofadr[jid])
            x, y, yaw = (float(t) for t in target['to_pose_m'])
            d.qpos[q:q + 7] = [x, y, float(d.qpos[q + 2]), math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
            d.qvel[v:v + 6] = 0
            mujoco.mj_forward(m, d)
            return {**row, 'effect': 'item_moved', 'to_pose_m': [x, y, yaw]}
        if kind == 'item_dropped':
            if not holders:
                return {**row, 'effect': 'none_item_not_held'}
            for rid in holders:
                self.faults.open_gripper(rid, now + GRIPPER_FAULT_S, event['event_id'])
            return {**row, 'effect': 'gripper_fault_open', 'holders': holders, 'pwm': GRIPPER_FAULT_PULSE,
                    'until_sim_s': round(now + GRIPPER_FAULT_S, 4)}
        raise ContractViolation(f'unsupported hidden event kind {kind!r}')
