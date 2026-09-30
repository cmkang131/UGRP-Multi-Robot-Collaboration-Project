"""T09b decision loop over own RGB, authored geometry and a delivered inbox.

This opt-in adapter has no simulator, scenario, clock schedule or referee input.
Perception and navigation are dependency-injected; their real RGB/drive adapters
still need integration and physical validation. A fake is not such an adapter.
All communication conditions use this class; only the upstream inbox differs.

An active pair cannot switch paths unilaterally using the fixed enum channel.
It stops/aborts the old job and returns a candidate for NEW matching high-level
submissions. No route, pose or reason is smuggled into that channel.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Protocol

from harness.zone_static_door_routes import DoorRoute, MotionContract, plan_door_routes
from harness.zone_study_contract import ENVELOPE_KEYS, MESSAGE_ENVELOPE_SCHEMA, STRUCTURED_FIELDS

VERSION = 'ugrp.observed_door_reroute.v1'
MEMORY_VERSION = 'monotone_blocked_doors.v1'
STATUS_PROFILE = 'zone_pair_status_v5'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class OwnFrame:
    robot_id: str
    sequence: int
    rgb: bytes

    @property
    def sha256(self):
        return hashlib.sha256(self.rgb).hexdigest()


@dataclass(frozen=True)
class OwnObservation:
    """Output of an own-RGB observer, not a host-authored discovery flag.

    pose is the cargo-frame estimate from this image and own command history.
    None means uncertainty. blocked_doors must be directly visible/confirmed;
    suspected or out-of-view obstacles do not enter this tuple.
    """
    frame_sha256: str
    pose_m_rad: tuple[float, float, float] | None
    blocked_doors: tuple[str, ...] = ()
    image_valid: bool = True


@dataclass(frozen=True)
class IssuedCommand:
    """An ACTUALLY ISSUED own command reported by the lower adapter, not motion."""
    name: str
    arguments: tuple[float, ...] = ()


@dataclass(frozen=True)
class NavigationFeedback:
    # running/stopped/reached/failed; reached is only a lower-layer claim.
    state: str
    issued: tuple[IssuedCommand, ...] = ()


class Observer(Protocol):
    version: str

    def observe(self, frame: OwnFrame, static_map: dict,
                own_commands: tuple[IssuedCommand, ...]) -> OwnObservation: ...


class Navigation(Protocol):
    """One implementation/version across conditions, with own-only inputs.

    tick must continuously enforce local RGB safety and stop/heartbeat/barrier
    guards. For pairs it must require matching high-level job submissions and
    the EXISTING status channel before moving. stop cancels ALL queued legs;
    stopped means that cancellation completed, not GT velocity measured zero.
    """
    version: str

    def tick(self, route: DoorRoute, frame: OwnFrame, observation: OwnObservation,
             own_commands: tuple[IssuedCommand, ...]) -> NavigationFeedback: ...

    def stop(self) -> NavigationFeedback: ...


@dataclass(frozen=True)
class Decision:
    state: str
    reason: str | None
    route: DoorRoute | None
    blocked_doors: tuple[str, ...]


def delivered_blockages(records, robot_id, doors):
    """Conservative, identical parser for a transport-owned robot inbox.

    Korean v1 supports only the unambiguous complete sentence '<door> 막힘 확인'.
    Other prose (including negation/suspicion) is not guessed at. Structured
    messages use the existing inform/blocked/high vocabulary. Sender claims
    remain beliefs, not referee facts. Sending/queuing is not delivery.
    """
    claims = []
    if not isinstance(records, (list, tuple)):
        return ()
    for record in records:
        if (not isinstance(record, dict) or set(record) != set(ENVELOPE_KEYS)
                or record.get('schema') != MESSAGE_ENVELOPE_SCHEMA
                or record.get('sender') not in ('r1', 'r2', 'r3')
                or record['sender'] == robot_id
                or not isinstance(record.get('recipients'), list)
                or robot_id not in record['recipients']
                or not isinstance(record.get('message_id'), str)
                or not record['message_id']):
            continue
        body = record.get('body')
        if not isinstance(body, dict):
            continue
        door = None
        if record.get('encoding') == 'free_ko' and set(body) == {'text'}:
            door = next((d for d in doors if body['text'] == f'{d} 막힘 확인'), None)
        elif (record.get('encoding') == 'schema'
              and set(body) == set(STRUCTURED_FIELDS)
              and body.get('act') == 'inform' and body.get('state') == 'blocked'
              and body.get('confidence') == 'high'):
            door = body.get('passage')
        if isinstance(door, str) and door in doors:
            claims.append((door, record['message_id']))
    return tuple(claims)


class ObservedDoorReroute:
    def __init__(self, *, robot_id, static_map, goal_pose, cargo_kind, roles,
                 observer: Observer, navigation: Navigation, pair_status=None):
        if robot_id not in ('r1', 'r2', 'r3'):
            raise ValueError('unknown robot')
        # Freeze a geometry-only projection; reject known private containers.
        if not isinstance(static_map, dict) or set(static_map) & {'eval', 'setup', 'hidden_events'}:
            raise ValueError('authored static map required')
        self._map = copy.deepcopy({k: static_map[k] for k in
                                   ('bounds_m', 'obstacles', 'terrain', 'passages') if k in static_map})
        self.robot_id, self.goal = robot_id, tuple(goal_pose)
        self.kind, self.roles = cargo_kind, tuple(roles)
        self.observer, self.navigation = observer, navigation
        self.pair_status = pair_status
        if len(self.roles) == 2:
            if (pair_status is None or pair_status.robot_id != robot_id
                    or robot_id not in pair_status.channel.participants
                    or len(pair_status.channel.participants) != 2
                    or any(r not in ('r1', 'r2', 'r3') for r in pair_status.channel.participants)
                    or len(set(pair_status.channel.participants)) != 2):
                raise ValueError('pair requires its existing fixed-enum endpoint')
        elif pair_status is not None:
            raise ValueError('solo cannot receive partner status')
        if any(not isinstance(x.version, str) or not x.version for x in (observer, navigation)):
            raise ValueError('pin observer/navigation versions')
        self._doors = frozenset(p['id'] for p in self._map.get('passages', ())
                                if isinstance(p, dict) and p.get('kind') == 'door'
                                and isinstance(p.get('id'), str))
        self._blocked = {}  # door -> first local RGB hash or delivered message id
        self._history = ()
        self._stop_confirmed = False
        self.route = None
        self.state, self.reason = 'NEW', None
        self._last_sequence, self._last_now = -1, -math.inf

    @property
    def belief(self):
        return copy.deepcopy(self._blocked)

    @property
    def own_commands(self):
        return self._history

    @property
    def invariant(self):
        """Configuration identity; actual source hashes belong in run manifests."""
        return {'controller': VERSION, 'memory': MEMORY_VERSION, 'sensors': 'own_rgb_only',
                'status_channel': STATUS_PROFILE, 'map_sha256': digest(self._map),
                'prior_sha256': digest({}), 'observer': self.observer.version,
                'navigation': self.navigation.version, 'motion': asdict(MotionContract()),
                'cargo_kind': self.kind, 'roles': self.roles, 'goal': self.goal}

    def _decision(self):
        return Decision(self.state, self.reason, self.route, tuple(sorted(self._blocked)))

    def _feedback(self, feedback):
        if not isinstance(feedback, NavigationFeedback) or feedback.state not in {
                'running', 'stopped', 'reached', 'failed'}:
            raise ValueError('invalid navigation feedback')
        if not isinstance(feedback.issued, tuple) or any(
                not isinstance(c, IssuedCommand) or not isinstance(c.name, str) or not c.name
                or not isinstance(c.arguments, tuple) or any(
                    type(v) not in (int, float) or not math.isfinite(v) for v in c.arguments)
                for c in feedback.issued):
            raise ValueError('invalid own commands')
        self._history += feedback.issued
        return feedback.state

    def _stop(self):
        try:
            result = self._feedback(self.navigation.stop())
        except Exception:
            result = 'failed'
        self._stop_confirmed = result == 'stopped'
        return result

    def _fail(self, reason, now):
        self.state, self.reason = 'FAILED', reason
        stopped = self._stop()
        if stopped != 'stopped':
            self.reason += ':STOP_UNCONFIRMED'
        if self.pair_status is not None:
            self.pair_status.fail(reason, now)
        return self._decision()

    def _plan(self, pose):
        # Block belief closes authored portals only; no hidden obstacle geometry.
        plans = plan_door_routes(self._map, pose, self.goal, cargo_kind=self.kind,
                                  roles=self.roles, robot_model='masterpi_v3')
        available = [route for route in plans.routes if route.passage_id not in self._blocked]
        self.route = available[0] if available else None
        if not self.route:
            self.state = 'REFUSED'
            self.reason = ('ALL_DOORS_BLOCKED' if self._doors and self._doors <= self._blocked.keys()
                           else 'NO_SUPPORTED_ROUTE:' + ','.join(sorted({r.reason for r in plans.refusals})))

    def tick(self, frame, *, now_s, delivered_messages=()):
        """now_s is the robot's monotonic timer, not a scenario/event clock feed.

        delivered_messages MUST come from the existing transport's robot inbox
        after delivery. No pending/send log, peer controller or evaluator view.
        """
        if self.state in {'FAILED', 'REFUSED', 'PAIR_REPLAN_REQUIRED', 'ROUTE_FINISHED'}:
            if not self._stop_confirmed:
                self._stop()
            return self._decision()
        if type(now_s) not in (int, float) or not math.isfinite(now_s) or now_s < 0 or now_s < self._last_now:
            return self._fail('INVALID_OWN_TIME', max(0., self._last_now))
        self._last_now = now_s
        if (not isinstance(frame, OwnFrame) or frame.robot_id != self.robot_id
                or type(frame.sequence) is not int or frame.sequence <= self._last_sequence
                or not isinstance(frame.rgb, bytes) or not frame.rgb):
            return self._fail('INVALID_OWN_FRAME', now_s)
        self._last_sequence = frame.sequence
        try:
            observation = self.observer.observe(frame, copy.deepcopy(self._map), self._history)
            pose = observation.pose_m_rad
            if (not isinstance(observation, OwnObservation) or observation.image_valid is not True
                    or observation.frame_sha256 != frame.sha256
                    or not isinstance(pose, tuple) or len(pose) != 3
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in pose)
                    or not isinstance(observation.blocked_doors, tuple)
                    or any(not isinstance(d, str) or d not in self._doors for d in observation.blocked_doors)):
                return self._fail('INVALID_OWN_OBSERVATION', now_s)
        except Exception:
            return self._fail('OBSERVER_ERROR', now_s)
        if self.pair_status is not None:
            peer = self.pair_status.channel.partner_view(self.robot_id, now_s)
            if any(not row['alive'] or row['state'] in {'abort', 'invalid_image', 'uncertain',
                                                       'incompatible', 'stopped'} for row in peer.values()):
                return self._fail('PAIR_NOT_SAFE', now_s)
        for door in observation.blocked_doors:
            self._blocked.setdefault(door, {'source': 'own_rgb', 'ref': frame.sha256})
        for door, message_id in delivered_blockages(delivered_messages, self.robot_id, self._doors):
            self._blocked.setdefault(door, {'source': 'message', 'ref': message_id})
        needs_replan = self.route is not None and self.route.passage_id in self._blocked
        if needs_replan:
            # Cancel the old leg queue first. Never drive wide while narrow runs.
            if self.pair_status is not None:
                self.pair_status.fail('ROUTE_CHANGED', now_s)
            stopped = self._stop()
            if stopped == 'running':
                self.state, self.reason = 'STOPPING', 'BLOCKAGE'
                return self._decision()
            if stopped != 'stopped':
                return self._fail('STOP_FAILED', now_s)
            self._plan(pose)
            if self.pair_status is not None:
                if self.route is not None:
                    self.state, self.reason = 'PAIR_REPLAN_REQUIRED', 'NEW_MATCHING_JOB_REQUIRED'
                return self._decision()
            if self.route is None:
                return self._decision()
            # Fresh own RGB after cancellation, not the pre-stop pose, starts it.
            self.state, self.reason = 'REPLAN_READY', None
            return self._decision()
        if self.route is None or self.state == 'REPLAN_READY':
            self._plan(pose)
            if self.route is None:
                if self.pair_status is not None:
                    self.pair_status.fail(self.reason, now_s)
                if self._stop() != 'stopped':
                    return self._fail('STOP_FAILED', now_s)
                return self._decision()
        try:
            self._stop_confirmed = False
            result = self._feedback(self.navigation.tick(self.route, frame, observation, self._history))
        except Exception:
            return self._fail('NAVIGATION_ERROR', now_s)
        if result == 'failed':
            return self._fail('NAVIGATION_FAILED', now_s)
        if result == 'reached':
            if (math.dist(pose[:2], self.goal[:2]) > .02
                    or abs((pose[2] - self.goal[2] + math.pi) % (2 * math.pi) - math.pi) > .02):
                return self._fail('UNCONFIRMED_ROUTE_END', now_s)
            if self._stop() != 'stopped':
                return self._fail('STOP_FAILED', now_s)
            self.state, self.reason = 'ROUTE_FINISHED', 'OWN_ESTIMATE_ONLY_NOT_DELIVERY'
        else:
            self.state, self.reason = 'RUNNING', None
        return self._decision()
