"""Fixed-enum M2 synchronization, identical in all four communication conditions.

Only status and bounded camera-evidence metadata cross this wire. Task choices,
poses, image bytes and free-text reasons never do. Heartbeats do not renew evidence.
"""
from __future__ import annotations

from collections.abc import Mapping
import math
import re

PROFILE = 'zone_pair_status_v5'
MAX_SEGMENTS = 8
CONTROL_S = .1
ARM_S = .05
HEARTBEAT_S = .05
HEARTBEAT_TIMEOUT_S = .15
READINESS_TTL_S = .6
EPS = 1e-8
FIELDS = frozenset(('robot_id', 'task_id', 'seq', 'state', 'sent_at_s',
                    'observed_at_s', 'frame_id', 'ready_until_s'))
EVIDENCE = ('observed_at_s', 'frame_id', 'ready_until_s')
BARRIERS = ('approach', 'close', 'lift', 'carry', 'lower', 'open')
STATES = frozenset(('available', 'busy', 'uncertain', 'stopped', 'occupied', 'incompatible', 'invalid_image',
                    'start_ready', 'aligning', 'not_ready', 'ready', 'lift', 'carry',
                    'put_down', 'done', 'abort') + tuple(
                        f'{phase}_{event}_{seg}' for seg in range(MAX_SEGMENTS) for phase in BARRIERS for event in ('ready', 'go')))

# Wire phase semantics shared by partner_view and resting-beam safety. The
# channel has no separate descending/closing/lifting messages: open descent is
# aligning, grasp/closing is ready, and lifting is lift. Even approach barriers
# normalize to aligning; they do not certify that the peer cannot touch cargo.
BARRIER_PHASES = dict(approach='aligning', close='aligning', lift='ready',
                      carry='lift', lower='carry', open='put_down')


def status_phase(state):
    if state == 'not_ready':
        return 'aligning'
    if state in STATES and ('_ready_' in state or '_go_' in state):
        return BARRIER_PHASES[state.split('_')[0]]
    return state


BEAM_MOTION_STATES = frozenset(state for state in STATES if status_phase(state) in BARRIER_PHASES.values())


def finite(v):
    return type(v) in (int, float) and math.isfinite(v)


class PairStatusChannel:
    """Only wire records are shared; never an executor/controller reference."""
    def __init__(self, task_id, participants=('r1', 'r2'), *, heartbeat_timeout_s=HEARTBEAT_TIMEOUT_S,
                 readiness_ttl_s=READINESS_TTL_S):
        if not finite(heartbeat_timeout_s) or not .1 <= heartbeat_timeout_s <= .5:
            raise ValueError('heartbeat timeout must be between 0.1 and 0.5 seconds')
        if not finite(readiness_ttl_s) or not .2 <= readiness_ttl_s <= 1.:
            raise ValueError('readiness TTL must be between 0.2 and 1.0 seconds')
        self.task_id, self.participants = task_id, tuple(participants)
        self.heartbeat_timeout_s, self.readiness_ttl_s = heartbeat_timeout_s, readiness_ttl_s
        self.latest, self.log, self.rejected = {}, [], []
        self.frames = {}  # evidence identity is immutable even across heartbeat retransmissions

    def publish(self, raw, received_at_s):
        valid = (isinstance(raw, Mapping) and set(raw) == FIELDS
                 and isinstance(raw.get('state'), str) and raw['state'] in STATES
                 and raw.get('task_id') == self.task_id
                 and isinstance(raw.get('robot_id'), str) and raw['robot_id'] in self.participants
                 and type(raw.get('seq')) is int and raw['seq'] > 0
                 and finite(raw.get('sent_at_s')) and raw['sent_at_s'] >= 0
                 and finite(received_at_s) and -EPS <= received_at_s - raw['sent_at_s'] <= self.heartbeat_timeout_s)
        prev = self.latest.get(raw['robot_id']) if valid else None
        if prev:
            valid = (prev['state'] != 'abort' and raw['seq'] > prev['seq']
                     and raw['sent_at_s'] >= prev['sent_at_s'])
        if valid and '_ready_' in raw['state']:
            at, fid, until = (raw[k] for k in EVIDENCE)
            valid = (finite(at) and finite(until) and 0 <= at <= raw['sent_at_s'] + EPS
                     and raw['sent_at_s'] < until + EPS and 0 < until - at <= self.readiness_ttl_s + EPS
                     and isinstance(fid, str) and re.fullmatch(raw['robot_id'] + r'-\d+-[a-f0-9]{12}', fid) is not None
                     and (fid not in self.frames or self.frames[fid] == at))
        elif valid:
            valid = all(raw[k] is None for k in EVIDENCE)
        if not valid:
            self.rejected.append({'reason': 'INVALID_STATUS'})
            return False
        row = dict(raw)
        if row['frame_id'] is not None:
            self.frames[row['frame_id']] = row['observed_at_s']
        self.latest[row['robot_id']] = row
        self.log.append(dict(row))
        return True

    def partner_view(self, me, now):
        out = {}
        for rid in self.participants:
            if rid == me:
                continue
            msg = self.latest.get(rid)
            state = None if msg is None else status_phase(msg['state'])
            age = None if msg is None else now - msg['sent_at_s']
            out[rid] = {'state': state, 'age_s': age,
                        'alive': age is not None and -EPS <= age < self.heartbeat_timeout_s - EPS}
        return out


class PairStatusEndpoint:
    def __init__(self, channel, robot_id):
        self.channel, self.robot_id = channel, robot_id
        self.seq, self.sent_at, self.state = 0, -math.inf, None
        self.barriers, self.latched = {}, None
        self.evidence = dict.fromkeys(EVIDENCE)
        self.failure = None
        self.grant = None

    def tick(self, state, now, *, force=False):
        if self.state == 'abort':
            return
        if state == 'abort':
            self.latched = None  # explicit stop always wins, including at evidence expiry
        elif self.latched and now >= self.evidence['ready_until_s'] - EPS:
            self.latched, state = None, 'not_ready'
        state = 'abort' if state == 'abort' else self.latched or state
        evidence = self.evidence if '_ready_' in state else dict.fromkeys(EVIDENCE)
        if force or state != self.state or now - self.sent_at >= HEARTBEAT_S - EPS:
            row = dict(robot_id=self.robot_id, task_id=self.channel.task_id, seq=self.seq + 1,
                       state=state, sent_at_s=float(now), **evidence)
            if not self.channel.publish(row, now):
                raise ValueError('status publication rejected')
            self.seq += 1
            self.state, self.sent_at = state, now

    def fail(self, reason, now):
        self.failure = reason  # local diagnostic only
        self.tick('abort', now)

    def sync_for(self, key):
        if key not in self.barriers:
            phase, _, segment = key.partition('@')
            state = f'{phase}_ready_{int(segment or 0)}'
            if state not in STATES:
                raise ValueError('unsupported M2 barrier')
            self.barriers[key] = _StatusBarrier(self, state)
        return self.barriers[key]


class _StatusBarrier:
    epoch = 1

    def __init__(self, endpoint, state):
        self.endpoint, self.state, self.go_at = endpoint, state, None

    def report(self, rid, *, ready, observed_at_s, received_at_s, frame_id=None, **local_only):
        ep, bus = self.endpoint, self.endpoint.channel
        if (rid != ep.robot_id or not finite(observed_at_s) or not finite(received_at_s)
                or not 0 <= received_at_s - observed_at_s < bus.readiness_ttl_s
                or not isinstance(frame_id, str)
                or re.fullmatch(rid + r'-\d+-[a-f0-9]{12}', frame_id) is None
                or (frame_id in bus.frames and bus.frames[frame_id] != observed_at_s)):
            return False
        if ep.state == 'abort':
            return False
        if ready:
            ep.latched = self.state
            ep.evidence = dict(observed_at_s=observed_at_s, frame_id=frame_id,
                               ready_until_s=observed_at_s + bus.readiness_ttl_s)
            ep.tick(self.state, received_at_s, force=True)
        else:
            ep.latched = None
            ep.tick('not_ready', received_at_s, force=True)
        return True

    def authorize(self, now):
        ep, bus = self.endpoint, self.endpoint.channel
        if ep.state == 'abort':
            return {'phase': 'ABORT'}
        if any(not v['alive'] or v['state'] == 'abort' for v in bus.partner_view(ep.robot_id, now).values()):
            return {'phase': 'WAIT'}
        seen, candidate, until = {}, None, None
        for msg in bus.log:
            seen[msg['robot_id']] = msg
            if candidate is not None and (msg['state'] in ('not_ready', 'abort')
                    or msg['sent_at_s'] + EPS < candidate and msg['state'] != self.state):
                if msg['sent_at_s'] > candidate + EPS:
                    ep.fail('LATE_OR_EXPIRED_GO', now)
                    return {'phase': 'ABORT'}
                candidate, until = None, None
            if len(seen) == len(bus.participants) and all(m['state'] == self.state for m in seen.values()):
                at = max(m['sent_at_s'] for m in seen.values())
                expiry = min(m['ready_until_s'] for m in seen.values())
                # Control-grid rendezvous; never start at a robot's late polling time.
                go = round(math.ceil((at + .2 - EPS) / CONTROL_S) * CONTROL_S, 9)
                if candidate is None and go < expiry - EPS:
                    candidate, until = go, expiry
        self.go_at = candidate
        if candidate is None or now < candidate - EPS:
            return {'phase': 'WAIT'}
        if now > candidate + EPS or now >= until - EPS:
            ep.fail('LATE_OR_EXPIRED_GO', now)
            return {'phase': 'ABORT'}
        ep.latched = None
        consumed = self.state.replace('_ready_', '_go_')
        ep.tick(consumed, now, force=True)
        ep.grant = (consumed, candidate)
        return {'phase': 'GO', 'go_at_s': candidate}

    def hold(self, reason, now):
        self.endpoint.fail('BARRIER_HOLD', now)
