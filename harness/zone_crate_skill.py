"""T06 crate-lug decision skill; native actuation/perception are NOT implemented.

This module emits bounded semantic intents, not servo/base commands. A future
own-camera adapter must supply the perception seam and execute those intents.
Nothing here certifies physical support or delivery, even with perfect fakes.
The existing fixed-enum wire is used identically in all four study conditions.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass

from harness.zone_pair_status import CONTROL_S, EPS, PairStatusEndpoint, finite

PROFILE = 'heavy_crate_lug_decisions_v1'
ROLES = {'r1': 'west', 'r2': 'east'}  # T07 owns symmetric/r3 expansion.
MASS_KG = .900
CONTACT_PROFILE = 'cargo_noslip_v1'


def capability():
    return {'profile': PROFILE, 'decision_logic': True,
            'native_adapter': False, 'physical_supported': False,
            'reason': 'CRATE_PHYSICAL_ADAPTER_UNAVAILABLE'}


def lug_target(role):
    """Static catalogue geometry, in the CRATE frame; never a live world pose."""
    if role not in ('west', 'east'):
        raise ValueError('UNSUPPORTED_CRATE_ROLE')
    return {'part': 'lug_' + role, 'grip_xyz_m': (-.10 if role == 'west' else .10, 0., .024),
            'grip_width_m': .040, 'lug_height_m': .046, 'mass_kg': MASS_KG}


def validate_request(order, actor, role, partner, zone):
    if (not isinstance(order, dict) or order.get('kind') != 'heavy_crate'
            or type(order.get('count')) is not int or order['count'] != 1
            or type(order.get('required_robots')) is not int or order['required_robots'] != 2
            or not isinstance(order.get('order_id'), str) or not order['order_id']):
        raise ValueError('UNSUPPORTED_CRATE_ORDER')
    if (not isinstance(actor, str) or not isinstance(partner, str)
            or actor not in ROLES or partner not in ROLES or actor == partner):
        raise ValueError('UNSUPPORTED_CRATE_PAIR')
    if role != ROLES[actor]:
        raise ValueError('UNSUPPORTED_CRATE_ROLE')
    if zone not in ('A', 'B', 'C') or zone != order.get('destination_zone'):
        raise ValueError('WRONG_CRATE_DESTINATION')


def executor_request(order, actor, role, zone):
    """Explicit kind dispatch seam; no change to long_beam role/API semantics."""
    partner = {'r1': 'r2', 'r2': 'r1'}.get(actor) if isinstance(actor, str) else None
    validate_request(order, actor, role, partner, zone)
    return order['order_id'], zone, partner


def refuse_native(own, item_ref, zone, partner, *, now):
    """Production API gate. Injection of a FakeM2 must not admit a crate."""
    own.now = now
    args = {'order_id': own._token(item_ref), 'target_ref': own._token(zone),
            'role': ROLES.get(own.robot_id)}
    try:
        validate_request(own.orders.get(item_ref), own.robot_id, args['role'], partner, zone)
    except ValueError as exc:
        reason = str(exc)
    else:
        reason = capability()['reason']
    return own._ack('pair_carry', args, False, reason)


def task_id(order, static_map):
    """Match public task + static inputs, not hidden placement/item identity."""
    public = {k: order.get(k) for k in ('order_id', 'kind', 'count', 'required_robots', 'destination_zone')}
    record = {'order': public, 'map': static_map, 'roles': ROLES, 'profile': PROFILE}
    return 'crate-' + hashlib.sha256(json.dumps(record, sort_keys=True, allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class OwnRGB:
    robot_id: str
    frame_id: int
    observed_at_s: float
    jpeg: bytes
    camera: str = 'robot_cam'


@dataclass(frozen=True)
class CrateEvidence:
    """Returned ONLY by an own-RGB perception adapter; unknown is not yes.

    aligned/grasped refer to the assigned lug, holding to this robot's grip,
    at_destination/supported/released to own RGB and the public static map.
    No evidence may be inferred solely from an issued command or a waypoint.
    """
    target_part: str | None = None
    aligned: str = 'unknown'
    grasped: str = 'unknown'
    holding: str = 'unknown'
    at_destination: str = 'unknown'
    supported: str = 'unknown'
    released: str = 'unknown'
    failed: bool = False


class CrateLugSkill:
    """One robot's decisions from own frames/history and delivered enum records.

    ``perceive(frame, own_commands, goal)`` is intentionally a separate seam.
    There is no native provider fallback. ``goal`` contains only the static map,
    public order/role and lug geometry. The owning adapter records actual issued
    commands using on_command(); semantic intents are logged separately.
    """
    def __init__(self, order, static_map, robot_id, role, partner_id, status: PairStatusEndpoint,
                 perceive, *, now=0., phase_timeout_s=120., horizon_s=900.):
        validate_request(order, robot_id, role, partner_id, order.get('destination_zone'))
        if (status.robot_id != robot_id or tuple(status.channel.participants) != ('r1', 'r2')
                or status.channel.task_id != task_id(order, static_map)):
            raise ValueError('CRATE_STATUS_CONTRACT_MISMATCH')
        if (not callable(perceive) or not finite(now) or now < 0
                or not finite(phase_timeout_s) or not .2 <= phase_timeout_s <= 900.
                or not finite(horizon_s) or not .2 <= horizon_s <= 900.):
            raise ValueError('INVALID_CRATE_CONFIG')
        self.robot_id, self.partner_id, self.role = robot_id, partner_id, role
        self.status, self.perceive = status, perceive
        self.goal = {'kind': 'heavy_crate', 'order_id': order['order_id'],
                     'destination_zone': order['destination_zone'], 'role': role,
                     'target': lug_target(role), 'static_map': copy.deepcopy(static_map)}
        self.phase, self.phase_at = 'approach', now
        self.phase_timeout_s, self.deadline = phase_timeout_s, now + horizon_s
        self.last_now, self.last_action_at = now, -1.
        self.peer_seen, self.failure, self.terminal = False, None, False
        self.commands, self.intents, self.inputs = [], [], []
        self.last_frame, self.last_evidence = None, None

    def on_command(self, row):
        fields = {'robot_id', 't', 'kind', 'forward', 'left', 'turn', 'duration_s', 'servo_id', 'pulse', 'pulses'}
        kinds = {'mecanum', 'arm', 'look', 'hold', 'initial_servo_command', 'observe_lug', 'approach_lug',
                 'close_lug', 'lift_lug', 'carry_to_zone', 'lower_lugs', 'open_lugs'}
        if (not isinstance(row, dict) or row.get('robot_id') != self.robot_id or not set(row) <= fields
                or row.get('kind') not in kinds or not finite(row.get('t'))
                or not 0 <= row['t'] <= self.last_now + EPS):
            raise ValueError('NOT_OWN_COMMAND')
        if any(not finite(row[k]) for k in set(row) - {'robot_id', 't', 'kind', 'pulses'}):
            raise ValueError('INVALID_COMMAND_VALUE')
        if 'pulses' in row and (not isinstance(row['pulses'], dict)
                or any(str(k) not in ('1', '2', '3', '4', '5', '6') or not finite(v)
                       for k, v in row['pulses'].items())):
            raise ValueError('INVALID_COMMAND_VALUE')
        self.commands.append(copy.deepcopy(row))

    def _intent(self, kind, now):
        out = {'kind': kind, 'robot_id': self.robot_id, 'role': self.role,
               'target': lug_target(self.role), 'destination_zone': self.goal['destination_zone'],
               'at_s': now, 'max_duration_s': CONTROL_S, 'physical_supported': False}
        self.intents.append(copy.deepcopy(out))
        return out

    def abort(self, reason, now):
        if not self.terminal:
            self.failure, self.phase, self.terminal = reason, 'failed', True
            self.status.fail(reason, now)
        return self._intent('hold', now)

    def _observe(self, frame, now):
        if (not isinstance(frame, OwnRGB) or frame.robot_id != self.robot_id or frame.camera != 'robot_cam'
                or type(frame.frame_id) is not int or frame.frame_id < 0
                or not finite(frame.observed_at_s) or not 0 <= now - frame.observed_at_s < .3
                or not isinstance(frame.jpeg, bytes) or not frame.jpeg):
            raise ValueError('INVALID_OWN_RGB')
        if self.last_frame is not None:
            if frame.frame_id < self.last_frame.frame_id or frame.observed_at_s < self.last_frame.observed_at_s:
                raise ValueError('REPLAYED_OWN_RGB')
            if frame.frame_id == self.last_frame.frame_id:
                if frame != self.last_frame:
                    raise ValueError('MUTATED_OWN_RGB')
                return self.last_evidence
        try:
            evidence = self.perceive(frame, copy.deepcopy(tuple(self.commands)), copy.deepcopy(self.goal))
        except Exception as exc:
            raise ValueError('CRATE_PERCEPTION_ERROR') from exc
        if (not isinstance(evidence, CrateEvidence) or type(evidence.failed) is not bool
                or evidence.target_part not in (None, 'box', 'lug_west', 'lug_east')
                or any(getattr(evidence, k) not in ('yes', 'no', 'unknown')
                       for k in ('aligned', 'grasped', 'holding', 'at_destination', 'supported', 'released'))):
            raise ValueError('INVALID_CRATE_EVIDENCE')
        self.last_frame, self.last_evidence = frame, evidence
        self.inputs.append({'frame_id': frame.frame_id, 'observed_at_s': frame.observed_at_s,
                            'sha256': hashlib.sha256(frame.jpeg).hexdigest(), 'evidence': asdict(evidence)})
        return evidence

    def _report(self, phase, ready, frame, now):
        return self.status.sync_for(phase).report(
            self.robot_id, ready=ready, observed_at_s=frame.observed_at_s, received_at_s=now,
            frame_id=f'{self.robot_id}-{frame.frame_id}-{hashlib.sha256(frame.jpeg).hexdigest()[:12]}')

    def _barrier(self, phase, ready, frame, now):
        if not self._report(phase, ready, frame, now):
            self.abort('INVALID_READY_EVIDENCE', now)
            return False
        if not ready:
            return False
        result = self.status.sync_for(phase).authorize(now)
        if result['phase'] == 'ABORT':
            self.abort(self.status.failure or 'BARRIER_ABORT', now)
        return result['phase'] == 'GO'

    def _advance(self, phase, intent, now):
        self.phase, self.phase_at, self.last_action_at = phase, now, now
        return self._intent(intent, now)

    def _peer_holding(self, now):
        """Fresh delivered holding evidence; a heartbeat never renews RGB age.

        carry_ready_1 is reserved as the moving holding heartbeat in this skill.
        lower_ready_0 means own holding AND own destination evidence. Neither
        message contains pose, free text, GT or the partner's live controller.
        """
        rows = [m for m in self.status.channel.log if m['robot_id'] == self.partner_id]
        if not rows or rows[-1]['state'] not in ('carry_go_0', 'carry_ready_1', 'lower_ready_0'):
            return False
        evidence = next((m for m in reversed(rows)
                         if m['state'] in ('carry_ready_0', 'carry_ready_1', 'lower_ready_0')), None)
        return bool(evidence and now < evidence['ready_until_s'] - EPS)

    def step(self, now, frame):
        if not finite(now) or now < self.last_now:
            raise ValueError('INVALID_LOCAL_CLOCK')
        self.last_now = now
        if self.terminal:
            return self._intent('hold', now)
        if now >= self.deadline - EPS or now >= self.phase_at + self.phase_timeout_s - EPS:
            return self.abort('CRATE_TIMEOUT', now)
        peer = self.status.channel.partner_view(self.robot_id, now)[self.partner_id]
        if peer['state'] == 'abort':
            return self.abort('PARTNER_ABORT', now)
        if not peer['alive'] and (self.peer_seen or peer['age_s'] is not None):
            return self.abort('PARTNER_SILENT', now)
        self.peer_seen = self.peer_seen or peer['alive']
        if self.status.grant and now > self.status.grant[1] + EPS:
            state, at = self.status.grant
            if not any(m['robot_id'] == self.partner_id and m['state'] == state
                       and abs(m['sent_at_s'] - at) <= EPS for m in self.status.channel.log):
                return self.abort('PARTNER_MISSED_GO', now)
        try:
            ev = self._observe(frame, now)
        except (ValueError, TypeError, KeyError):
            return self.abort('INVALID_OWN_RGB_OR_EVIDENCE', now)
        if ev.failed:
            return self.abort('OWN_CRATE_FAILURE', now)
        self.status.tick(self.status.state or 'start_ready', now)
        if not peer['alive']:
            return self._intent('hold', now)
        fresh = frame.observed_at_s > self.last_action_at + EPS
        lug = ev.target_part == lug_target(self.role)['part']
        if self.phase == 'approach':
            if self._barrier('close@0', lug and ev.aligned == 'yes', frame, now):
                return self._advance('grasp', 'close_lug', now)
            if self.terminal:
                return self._intent('hold', now)
            if not lug:
                return self._intent('observe_lug', now)
            return self._intent('approach_lug' if lug and ev.aligned != 'yes' else 'hold', now)
        if self.phase == 'grasp':
            if fresh and ev.grasped == 'no':
                return self.abort('OWN_GRASP_FAILED', now)
            if self._barrier('lift@0', fresh and lug and ev.grasped == 'yes', frame, now):
                return self._advance('lift', 'lift_lug', now)
        elif self.phase == 'lift':
            if self._barrier('carry@0', fresh and lug and ev.holding == 'yes', frame, now):
                return self._advance('carry', 'carry_to_zone', now)
        elif self.phase == 'carry':
            if not lug or ev.holding != 'yes':
                return self.abort('OWN_HOLDING_LOST', now)
            if fresh and ev.at_destination == 'yes':
                if self._barrier('lower@0', True, frame, now):
                    return self._advance('lower', 'lower_lugs', now)
            else:
                self._report('carry@1', True, frame, now)
            if not self._peer_holding(now):
                return self.abort('PARTNER_HOLDING_UNCONFIRMED', now)
            if ev.at_destination != 'yes':
                return self._intent('carry_to_zone', now)
        elif self.phase == 'lower':
            if self._barrier('open@0', fresh and ev.supported == 'yes' and ev.at_destination == 'yes', frame, now):
                return self._advance('release', 'open_lugs', now)
        elif self.phase == 'release':
            if fresh and ev.released == 'yes' and ev.supported == 'yes' and ev.at_destination == 'yes':
                self.status.tick('done', now)
                if peer['state'] == 'done':
                    self.phase, self.terminal = 'sequence_complete_unconfirmed', True
                    return self._intent('sequence_complete_unconfirmed', now)
        return self._intent('hold', now)
