"""Fixed, task-content-free M2 status transport (all four study conditions).

The frozen team_carry_status v1 cannot encode a checkpoint rendezvous. This
version adds a finite set of readiness enums; there is no second barrier bus.
Frame ids, reasons, poses and task arguments stay in the sender's local audit.
"""
from __future__ import annotations

from collections.abc import Mapping
import math

from harness.team_carry_status import FIELDS, HEARTBEAT_S, STALE_S

PROFILE = 'zone_pair_status_v2'
MAX_SEGMENTS = 8
BARRIERS = ('approach', 'lift', 'carry', 'lower', 'open')
STATES = frozenset(('available', 'busy', 'uncertain', 'stopped', 'occupied', 'incompatible',
                    'start_ready', 'aligning', 'not_ready', 'ready', 'lift', 'carry',
                    'put_down', 'done', 'abort') + tuple(
                        f'{phase}_ready_{seg}' for seg in range(MAX_SEGMENTS) for phase in BARRIERS))


class PairStatusChannel:
    """Only validated wire records are shared. No executor/controller references."""

    def __init__(self, task_id, participants=('r1', 'r2')):
        self.task_id, self.participants = task_id, tuple(participants)
        self.latest, self.log, self.rejected = {}, [], []

    def publish(self, raw, received_at_s):
        valid = (isinstance(raw, Mapping) and set(raw) == FIELDS
                 and isinstance(raw.get('state'), str) and raw['state'] in STATES
                 and raw.get('task_id') == self.task_id
                 and isinstance(raw.get('robot_id'), str) and raw['robot_id'] in self.participants
                 and type(raw.get('seq')) is int and raw['seq'] > 0
                 and type(raw.get('sent_at_s')) in (int, float) and math.isfinite(raw['sent_at_s'])
                 and raw['sent_at_s'] >= 0
                 and type(received_at_s) in (int, float) and math.isfinite(received_at_s)
                 and 0 <= received_at_s - raw['sent_at_s'] <= STALE_S)
        prev = self.latest.get(raw['robot_id']) if valid else None
        if prev:
            valid = (prev['state'] != 'abort' and raw['seq'] > prev['seq']
                     and raw['sent_at_s'] >= prev['sent_at_s'])
        if not valid:
            self.rejected.append({'reason': 'INVALID_STATUS'})
            return False
        row = dict(raw)
        self.latest[row['robot_id']] = row
        self.log.append(dict(row))
        return True

    def partner_view(self, me, now):
        """v1-compatible view for the frozen M2 wait policy, derived ONLY from wire enums."""
        out = {}
        for rid in self.participants:
            if rid == me:
                continue
            msg = self.latest.get(rid)
            state = None if msg is None else msg['state']
            if state == 'not_ready':
                state = 'aligning'
            if state and '_ready_' in state:
                state = {'approach': 'aligning', 'lift': 'ready', 'carry': 'lift',
                         'lower': 'carry', 'open': 'put_down'}[state.split('_')[0]]
            age = None if msg is None else now - msg['sent_at_s']
            out[rid] = {'state': state, 'age_s': age, 'alive': age is not None and 0 <= age <= STALE_S}
        return out


class PairStatusEndpoint:
    """A sender and its local barrier adapter. Barrier state is never shared privately."""

    def __init__(self, channel, robot_id):
        self.channel, self.robot_id = channel, robot_id
        self.seq, self.sent_at, self.state = 0, -math.inf, None
        self.barriers = {}
        self.latched = None

    def tick(self, state, now):
        if self.state == 'abort':
            return
        # Frozen M2 publishes coarse lifecycle states on every tick. Preserve
        # a readiness enum until the local controller consumes that barrier.
        state = 'abort' if state == 'abort' else self.latched or state
        if state != self.state or now - self.sent_at >= HEARTBEAT_S:
            self.seq += 1
            if not self.channel.publish(dict(robot_id=self.robot_id, task_id=self.channel.task_id,
                                             seq=self.seq, state=state, sent_at_s=float(now)), now):
                raise ValueError('status publication rejected')
            self.state, self.sent_at = state, now

    def sync_for(self, key):
        if key not in self.barriers:
            phase, _, segment = key.partition('@')
            state = f'{phase}_ready_{int(segment or 0)}'
            if state not in STATES:
                raise ValueError('unsupported M2 barrier')
            self.barriers[key] = _StatusBarrier(self, state)
        return self.barriers[key]


class _StatusBarrier:
    """PairCarrySync interface backed entirely by fixed-enum status messages."""
    epoch = 1

    def __init__(self, endpoint, state):
        self.endpoint, self.state = endpoint, state
        self.go_at = None

    def report(self, rid, *, ready, observed_at_s, received_at_s, **local_only):
        if rid != self.endpoint.robot_id or not 0 <= received_at_s - observed_at_s <= STALE_S:
            return False
        if ready:
            self.endpoint.latched = self.state
            self.endpoint.tick(self.state, received_at_s)
        else:
            # Revocation must be visible too; do not keep an old readiness claim.
            self.endpoint.latched = None
            self.endpoint.tick('not_ready', received_at_s)
        return True

    def authorize(self, now):
        ep, bus = self.endpoint, self.endpoint.channel
        if any(not v['alive'] or v['state'] == 'abort' for v in bus.partner_view(ep.robot_id, now).values()):
            return {'phase': 'WAIT'}
        # Retain the joint-ready instant from wire records. The first consumer
        # may already have advanced when the second polls. Recheck revocations
        # even if a previous poll computed GO's future timestamp.
        seen, candidate = {}, None
        for msg in bus.log:
            seen[msg['robot_id']] = msg
            # Same tolerance as GO below: 3.2 + .2 and a clock's 3.4 must
            # not turn the first consumer's transition into a revocation.
            if candidate is not None and (msg['state'] == 'not_ready'
                    or msg['sent_at_s'] + 1e-9 < candidate and msg['state'] != self.state):
                candidate = None
            if (len(seen) == len(bus.participants) and all(m['state'] == self.state for m in seen.values())
                    and max(m['sent_at_s'] for m in seen.values()) - min(m['sent_at_s'] for m in seen.values()) <= STALE_S):
                if candidate is None:
                    candidate = max(m['sent_at_s'] for m in seen.values()) + .2
        self.go_at = candidate
        if self.go_at is None or now + 1e-9 < self.go_at:
            return {'phase': 'WAIT'}
        ep.latched = None
        return {'phase': 'GO', 'go_at_s': self.go_at}

    def hold(self, reason, now):
        # Free-text reason is deliberately discarded at the wire boundary.
        self.endpoint.tick('abort', now)
