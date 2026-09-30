"""Opt-in own-actor rendezvous/reassignment; no scenario or peer-state input.

The caller chooses a partner/role using its allowed inputs. This module only
waits on the existing enum wire, cancels the caller's job, and fences obsolete
requests. It does not detect a physical hold or choose a replacement partner.
Bind RoleAwareOwnPairPort to zone_pair_role_host.OwnCamTeamHost for r3.
The sealed zone_own_team_host.OwnCamTeamHost retains its r1/r2-only API.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Protocol

from harness.zone_pair_status import EPS, PROFILE as STATUS_PROFILE, PairStatusEndpoint, finite

PROFILE = 'own_pair_rendezvous_v1'
ROBOTS = ('r1', 'r2', 'r3')
ROLES = ('end_neg', 'end_pos')


@dataclass(frozen=True)
class PairRequest:
    order_id: str
    destination_zone: str
    partner_id: str
    role: str

    def validate(self, actor):
        if (actor not in ROBOTS or self.partner_id not in ROBOTS
                or self.partner_id == actor or self.role not in ROLES
                or not isinstance(self.order_id, str) or not self.order_id
                or self.destination_zone not in ('A', 'B', 'C')):
            raise ValueError('BAD_PAIR_REQUEST')

    def assignment_record(self, actor):
        self.validate(actor)
        # Canonical role -> robot direction matches T07's PairRoles receipt.
        roles = {self.role: actor, next(r for r in ROLES if r != self.role): self.partner_id}
        encoded = json.dumps(roles, sort_keys=True, separators=(',', ':')).encode()
        return {'role_to_robot': roles, 'role_assignment_sha256': hashlib.sha256(encoded).hexdigest()}


class OwnPairPort(Protocol):
    """Callbacks scoped to ONE actor; never expose peer executors to recovery.

    submit must validate the explicit role and return the normal pair_carry ack.
    abort must synchronously cancel the own controller/host queues, publish the
    existing abort enum and clear the own job. PairTeam propagates that enum.
    """
    def status(self) -> dict: ...
    def endpoint(self) -> PairStatusEndpoint | None: ...
    def submit(self, request: PairRequest) -> dict: ...
    def abort(self) -> dict: ...


class LegacyOwnPairPort:
    """Bind existing main's r1/r2 API without widening its supported roles.

    The bound callbacks may be host.call(rid, ...), ex.status and
    lambda: ex._pair.status if ex._pair else None. T07 owns the separate
    role-aware port. No monkey-patched robot IDs or role defaults are used here.
    """
    def __init__(self, actor, *, call, status, endpoint):
        if actor not in ROBOTS:
            raise ValueError('BAD_ACTOR')
        self.actor, self._call, self._status, self._endpoint = actor, call, status, endpoint

    def status(self):
        return self._status()

    def endpoint(self):
        return self._endpoint()

    def submit(self, request):
        supported = {'r1': ('end_neg', 'r2'), 'r2': ('end_pos', 'r1')}
        if supported.get(self.actor) != (request.role, request.partner_id):
            return {'accepted': False, 'rejected_reason': 'T07_ROLE_ROUTING_REQUIRED'}
        return self._call('pair_carry', request.order_id, request.destination_zone, request.partner_id)

    def abort(self):
        return self._call('abort', 'rendezvous_cancel_requested')


class RoleAwareOwnPairPort(LegacyOwnPairPort):
    """zone_pair_role_host's fourth-argument API; no legacy fallback.

    The sealed legacy host refuses the call as BAD_PAIR_ARGUMENTS. A host that
    silently ignores role is also rejected by the recovery ack validation.
    """
    def submit(self, request):
        return self._call('pair_carry', request.order_id, request.destination_zone,
                          request.partner_id, request.role)


@dataclass(frozen=True)
class RecoveryResult:
    state: str
    job_id: str | None = None
    reason: str | None = None


class OwnPairRecovery:
    """Explicit submit/cancel/replace with an own submission deadline.

    Same code/config for all communication conditions; leader and event
    schedules are deliberately absent. A stopped/occupied actor is still
    refused by its executor. Command acceptance never proves wheel motion.
    Timeout applies to submission rendezvous, not the physical approach.
    """
    def __init__(self, actor, port: OwnPairPort, *, rendezvous_timeout_s=5.):
        if actor not in ROBOTS:
            raise ValueError('BAD_ACTOR')
        if not finite(rendezvous_timeout_s) or not .2 <= rendezvous_timeout_s <= 30.:
            raise ValueError('BAD_RENDEZVOUS_TIMEOUT')
        self.actor, self.port, self.timeout_s = actor, port, float(rendezvous_timeout_s)
        self.job_id = self.request = self.deadline = self.task_id = None
        self.last_now = -1.
        self.events = []  # own audit only; never a STATUS payload or peer input

    def _clock(self, now):
        if not finite(now) or now < 0 or now < self.last_now:
            raise ValueError('BAD_OWN_CLOCK')
        self.last_now = float(now)

    def _result(self, state, now, reason=None, *, job_id=None):
        result = RecoveryResult(state, job_id or self.job_id, reason)
        self.events.append({'sim_s': float(now), **asdict(result)})
        return result

    def _owns(self):
        job = self.port.status().get('job')
        return bool(job and job.get('job_id') == self.job_id and job.get('kind') == 'pair_carry')

    def _forget(self):
        self.job_id = self.request = self.deadline = self.task_id = None

    def submit(self, request: PairRequest, *, now):
        self._clock(now)
        if not isinstance(request, PairRequest):
            raise ValueError('BAD_PAIR_REQUEST')
        request.validate(self.actor)
        # A stale local handle cannot cancel/adopt some newer external job.
        if self.port.status().get('job') is not None:
            return self._result('refused', now, 'SELF_BUSY')
        self._forget()
        ack = self.port.submit(request)
        if not ack.get('accepted'):
            return self._result('refused', now, ack.get('rejected_reason') or 'SUBMIT_REJECTED')
        self.job_id = ack.get('job_id')
        self.request = request
        endpoint = self.port.endpoint()
        args = ack.get('arguments', {})
        valid_ack = (isinstance(self.job_id, str) and bool(self.job_id)
                 and ack.get('robot_id') == self.actor and ack.get('api') == 'pair_carry'
                 and args.get('order_id') == request.order_id
                 and args.get('target_ref') == request.destination_zone and args.get('role') == request.role)
        # host.call polls safety before returning. An accepted submission can
        # already have ended (e.g. peer heartbeat expired); that is a normal
        # local terminal result, not a broken adapter or permission to retry.
        if valid_ack and self.port.status().get('job') is None:
            result = self._result('ended', now, 'OWN_JOB_ENDED_DURING_SUBMIT')
            self._forget()
            return result
        valid = (valid_ack and self._owns() and endpoint is not None and endpoint.robot_id == self.actor
                 and len(endpoint.channel.participants) == 2
                 and set(endpoint.channel.participants) == {self.actor, request.partner_id})
        if not valid:
            if self.job_id and self._owns():
                self.port.abort()
            self._forget()
            raise ValueError('PAIR_PORT_CONTRACT_MISMATCH')
        self.task_id = endpoint.channel.task_id
        self.deadline = float(now) + self.timeout_s
        self.events.append({'sim_s': float(now), 'state': 'submitted', 'job_id': self.job_id,
                            'request': asdict(request), **request.assignment_record(self.actor)})
        return RecoveryResult('waiting', self.job_id)

    def cancel(self, job_id, *, now, reason='CALLER_CANCELLED'):
        self._clock(now)
        if self.job_id is None or job_id != self.job_id or not self._owns():
            return self._result('refused', now, 'STALE_JOB', job_id=job_id)
        ack = self.port.abort()
        # A failed cancellation must not submit new work or forget the handle.
        if not ack.get('accepted') or self.port.status().get('job') is not None:
            return self._result('refused', now, 'CANCEL_NOT_CONFIRMED')
        result = self._result('cancelled', now, reason)
        self._forget()
        return result

    def replace(self, job_id, request: PairRequest, *, now):
        """Caller-selected reassignment; validate before cancelling old work."""
        if not isinstance(request, PairRequest):
            raise ValueError('BAD_PAIR_REQUEST')
        request.validate(self.actor)
        result = self.cancel(job_id, now=now, reason='CALLER_REASSIGNED')
        return self.submit(request, now=now) if result.state == 'cancelled' else result

    def poll(self, *, now):
        self._clock(now)
        if self.job_id is None:
            return RecoveryResult('idle')
        if not self._owns():
            result = self._result('ended', now, 'OWN_JOB_ENDED')
            self._forget()
            return result
        endpoint = self.port.endpoint()
        if (endpoint is None or endpoint.robot_id != self.actor or endpoint.channel.task_id != self.task_id
                or len(endpoint.channel.participants) != 2
                or set(endpoint.channel.participants) != {self.actor, self.request.partner_id}):
            return self.cancel(self.job_id, now=now, reason='OWN_ENDPOINT_LOST')
        channel = endpoint.channel
        if endpoint.state == 'abort':
            return self.cancel(self.job_id, now=now, reason='OWN_STATUS_ABORT')
        peer = channel.partner_view(self.actor, now).get(self.request.partner_id)
        if peer and peer['state'] == 'abort':
            return self.cancel(self.job_id, now=now, reason='PARTNER_ABORT')
        # Only bounded enum publications establish a join; private peer state
        # and an accepted motor command cannot do so. Late joins cannot revive
        # an expired attempt even if the caller has not polled the timeout yet.
        joined = {}
        for row in channel.log:
            if (row['state'] == 'start_ready' and row['sent_at_s'] <= now + EPS
                    and row['sent_at_s'] < self.deadline - EPS):
                joined.setdefault(row['robot_id'], row['sent_at_s'])
        if set(joined) == set(channel.participants):
            if not peer or not peer['alive']:
                return self.cancel(self.job_id, now=now, reason='PARTNER_SILENT')
            return RecoveryResult('active', self.job_id)
        if now >= self.deadline - EPS:
            return self.cancel(self.job_id, now=now, reason='PAIR_RENDEZVOUS_TIMEOUT')
        return RecoveryResult('waiting', self.job_id)

    def record(self):
        from pathlib import Path
        return {'profile': PROFILE, 'status_profile': STATUS_PROFILE,
                'recovery_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'robot_id': self.actor, 'rendezvous_timeout_s': self.timeout_s,
                'job_id': self.job_id,
                'assignment': None if self.request is None else self.request.assignment_record(self.actor)}
