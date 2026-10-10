"""Opt-in S3 one-shot door reservation, using own estimates and fixed enums only.

Each client independently applies the same public priority (pair, then solo).
The relay validates and broadcasts; it never receives poses or chooses a winner.
Reserve before starting a job, release only after its last command AND an own
clearance estimate. This deliberately coarse critical section cannot re-enter.
See experiments/2026-10-06-s3-door-yield/README.md for sources and limitations.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
import math

from harness import zone_s3_host as base

PROFILE = 's3-door-yield-v1'
CONDITIONS = ('rule', 'no_comm', 'peer_nl')
TEAMS = (('r1', 'r2'), ('r3',))  # public, fixed tie-breaking priority
STATES = ('REQUEST', 'USING', 'CLEAR')
MAX_REPORT_AGE_S = 1.
CLEAR_MARGIN_M = .05
SIGMA = 3.


def specification():
    return {'profile': PROFILE, 'resource': 'door_1', 'conditions': list(CONDITIONS),
            'priority': [list(t) for t in TEAMS], 'fields': list(Signal.__dataclass_fields__),
            'delivery': 'complete synchronous batch to every client, before producer step',
            'critical_section': 'whole one-shot job; wait at initial dock before any job command',
            'release': 'own job ended AND own estimated footprint east of door; all team members',
            'timeout_releases': False, 'dev_light_bypass': False,
            'report_max_age_s': MAX_REPORT_AGE_S, 'clear_margin_m': CLEAR_MARGIN_M,
            'sigma_multiplier': SIGMA, 'physical_clearance_verified': False}


@dataclass(frozen=True)
class Signal:
    robot_id: str
    resource: str
    round: int
    state: str


def validated_batch(messages, round_no):
    """Fixed schema, exact membership and round; no free text or numeric pose."""
    if len(messages) != len(base.ROBOTS):
        raise ValueError('DOOR_STATUS_MISSING')
    out = {}
    for m in messages:
        if (type(m) is not Signal or m.robot_id not in base.ROBOTS
                or m.robot_id in out or m.resource != 'door_1'
                or type(m.round) is not int or m.round != round_no or m.state not in STATES):
            raise ValueError('DOOR_STATUS_INVALID')
        out[m.robot_id] = m.state
    return out


class Client:
    """Only one robot's own callbacks and the public plan/formation geometry."""
    def __init__(self, robot_id, *, own_report, own_done, door_exit_x, offset, envelope):
        if robot_id not in base.ROBOTS:
            raise ValueError('unknown door participant')
        self.robot_id, self.own_report, self.own_done = robot_id, own_report, own_done
        self.door_exit_x, self.offset, self.envelope = door_exit_x, offset, envelope
        self.team = next(t for t in TEAMS if robot_id in t)
        self.table, self.round, self.state = {}, 0, 'REQUEST'
        self.entered = False

    def owner(self):
        if set(self.table) != set(base.ROBOTS):
            return None
        return next((t for t in TEAMS if not all(self.table[r] == 'CLEAR' for r in t)), None)

    def permits(self):
        # A cleared member may continue only stationary terminal processing.
        return self.owner() == self.team and all(self.table[r] in ('USING', 'CLEAR') for r in self.team)

    def clear(self, now):
        # No release on time, command issuance alone, job failure or peer pose.
        if not self.entered or not self.own_done():
            return False
        r = self.own_report()
        if r is None or not r.initialized:
            return False
        values = (r.t_est, r.x_m, r.y_m, r.yaw_rad, r.std_xy_m, r.std_yaw_rad)
        if (not all(math.isfinite(v) for v in values) or r.std_xy_m < 0 or r.std_yaw_rad < 0
                or not -1e-8 <= now-r.t_est <= MAX_REPORT_AGE_S
                or r.last_fix_t is None or not math.isfinite(r.last_fix_t)
                or r.last_fix_t > r.t_est+1e-8):
            return False
        # Public planned grasp offset: infer the carried envelope from SELF only.
        # This is an estimate assuming the formation, never a peer/cargo truth read.
        dx, dy, heading = self.offset
        yaw = r.yaw_rad-heading
        c, s = math.cos(yaw), math.sin(yaw)
        centre_x = r.x_m-c*dx+s*dy
        ex, ey = self.envelope
        # Bound rotation uncertainty by chord displacement of the farthest corner.
        radius = math.hypot(dx, dy)+math.hypot(ex, ey)
        yaw_pad = 2*radius*math.sin(min(math.pi, SIGMA*r.std_yaw_rad)/2)
        west_edge = centre_x-abs(c)*ex-abs(s)*ey-SIGMA*r.std_xy_m-yaw_pad
        return west_edge > self.door_exit_x+CLEAR_MARGIN_M

    def offer(self, now):
        state = self.state
        if state == 'REQUEST' and self.owner() == self.team:
            state = 'USING'
        elif state == 'USING' and self.clear(now):
            state = 'CLEAR'
        return Signal(self.robot_id, 'door_1', self.round, state)

    def receive(self, messages):
        table = validated_batch(messages, self.round)
        for r, state in table.items():
            previous = self.table.get(r, 'REQUEST')
            if STATES.index(state)-STATES.index(previous) not in (0, 1):
                raise ValueError('DOOR_STATUS_TRANSITION')
            team = next(t for t in TEAMS if r in t)
            if previous == 'REQUEST' and state == 'USING' and self.owner() != team:
                raise ValueError('DOOR_STATUS_NOT_OWNER')
        self.table, self.state = table, table[self.robot_id]
        self.round += 1
        self.entered = self.entered or self.permits()


class Relay:
    """Transport and validation only. No client callbacks/poses/priority choice."""
    def __init__(self):
        self.round, self.events, self.previous = 0, [], None

    def broadcast(self, messages, now):
        states = validated_batch(messages, self.round)
        if states != self.previous:
            self.events.append({'sim_s': now, 'signals': [asdict(m) for m in messages]})
            self.previous = states
        self.round += 1
        return tuple(messages)


class GatedProducer:
    """Do not advance a waiting state machine or emit arm proposals then discard them."""
    def __init__(self, producer, robots, clients):
        self.producer, self.robots, self.clients = producer, robots, clients

    def __getattr__(self, name):
        return getattr(self.producer, name)

    def allowed(self):
        return all(self.clients[r].permits() for r in self.robots)

    def step(self, now):
        return (self.producer.step(now) if self.allowed()
                else [(r, {'kind': 'hold'}) for r in self.robots])

    def arm_step(self, now):
        return self.producer.arm_step(now) if self.allowed() else []


class Runtime(base.Runtime):
    """Same producers, own observations and issued-command histories; explicit opt-in."""
    def __init__(self, static, orders, calibration, calibration_sha, *, condition='rule', **kwargs):
        if condition not in CONDITIONS:
            raise ValueError('door yield requires rule/no_comm/peer_nl boundary')
        doors = [p for p in static['passages'] if p['id'] == 'door_1']
        if (static['map_id'] != 'zone_wide_door_geometry_v3' or len(doors) != 1
                or doors[0]['kind'] != 'door' or doors[0]['axis'] != 'x'):
            raise ValueError('door yield v1 requires S3 one-door eastbound plan')
        self.door_failure = None
        super().__init__(static, orders, calibration, calibration_sha, **kwargs)
        try:
            from sim.zone_model_conventions import station_offset
            end_x = doors[0]['center_m'][0]+doors[0]['half_extents_m'][0]
            self.clients = {}
            for rid, own in self.pair.actors.items():
                role = next(k for k, r in base.ROLES.items() if r == rid)
                self.clients[rid] = Client(rid, own_report=lambda own=own: own.last_report,
                    own_done=lambda own=own: any(j['kind'] == 'pair_carry' and j.get('confirmation') != 'failed'
                                                for j in own.jobs_done),
                    door_exit_x=end_x, offset=station_offset(static, 'long_beam', role),
                    envelope=tuple(max(abs(v) for v in base.skill.ENVELOPE[k]) for k in ('x_m', 'y_m')))
            own = self.solo
            self.clients['r3'] = Client('r3', own_report=lambda: own.last_report,
                own_done=lambda: own.terminal and not own.failure, door_exit_x=end_x,
                offset=(0., 0., 0.),
                envelope=tuple(max(abs(v) for v in base.solo.ENVELOPE[k]) for k in ('x_m', 'y_m')))
            self.relay = Relay()
            self.pair = GatedProducer(self.pair, ('r1', 'r2'), self.clients)
            self.solo = GatedProducer(self.solo, ('r3',), self.clients)
            self.wait_robot_s = {r: 0. for r in base.ROBOTS}
            self.last_tick, self.waiting = None, set(base.ROBOTS)
            self.wait_accounted_until = None
        except Exception:
            self.close()
            raise

    @property
    def failures(self):
        result = super().failures
        if self.door_failure:
            result['door_1'] = self.door_failure
        return result

    def exchange(self, now):
        batch = self.relay.broadcast([c.offer(now) for c in self.clients.values()], now)
        for c in self.clients.values():
            c.receive(batch)

    def step(self, now):
        if self.trial is None:
            raise ValueError('S3 runtime requires IntegratedTrial')
        if not math.isfinite(now) or (self.last_tick is not None and now < self.last_tick):
            self.door_failure = 'DOOR_CLOCK_INVALID'
            return [(r, {'kind': 'hold'}) for r in base.ROBOTS]
        self.account_wait(now)
        self.last_tick = now
        if self.failures:
            return [(r, {'kind': 'hold'}) for r in base.ROBOTS]
        try:
            self.exchange(now)
            # The initial REQUEST batch is a barrier; a second round publishes
            # local USING before either member can issue its first job command.
            if self.relay.round == 1:
                self.exchange(now)
            self.waiting = {r for r, c in self.clients.items() if not c.permits() and c.state != 'CLEAR'}
            rows = super().step(now)
            if not self.failures:
                # Publish local completion even if the host ends on this tick.
                self.exchange(now)
            return rows
        except ValueError as exc:
            self.door_failure = str(exc)
            return [(r, {'kind': 'hold'}) for r in base.ROBOTS]

    def account_wait(self, now):
        if self.wait_accounted_until is not None:
            for r in self.waiting:
                self.wait_robot_s[r] += now-self.wait_accounted_until
        self.wait_accounted_until = now

    def on_command(self, rid, now, action):
        # The host issues final holds at the horizon without another step.
        # Include that final interval exactly once, even with three hold rows.
        if (not self.failures and math.isfinite(now)
                and (self.wait_accounted_until is None or now >= self.wait_accounted_until)):
            self.account_wait(now)
        super().on_command(rid, now, action)

    def record(self):
        result = super().record()
        result['door_yield'] = {**specification(), 'events': copy.deepcopy(self.relay.events),
            'wait_robot_s': dict(self.wait_robot_s), 'rounds': self.relay.round,
            'final_states': {r: c.state for r, c in self.clients.items()},
            'failure': self.door_failure}
        return result
