"""The one seam of the pair LLM layer: a claim gate in front of ``Team.start``.

``harness.zone_final_pair_runtime.Runtime.step`` calls ``self.team.start(rid, 'cargoX', target,
partner, now=now)`` on every control tick while a robot has no job and has not submitted yet. That
call IS the C-rule behaviour (both robots submit the identical task as soon as they are idle). The
LLM arms put the study's scheduler-released ``claim`` in front of that single call:

* ``ClaimGate.grant`` is the only way a claim reaches the runtime. It stores a PERMIT for one robot
  (order, destination zone, partner); it never starts anything by itself.
* The gate replaces ``team.start`` (an instance attribute of ``Team``, so no source is edited). While
  a robot has no permit the call is refused with ``CLAIM_NOT_RELEASED`` and nothing else happens.
* With a permit, the gate calls the ORIGINAL ``Team.start`` with the CLAIM's arguments (not the
  runtime's), so a wrong zone or a mismatching partner claim fails exactly where it fails in the
  scripted path (``WRONG_PAIR_DESTINATION``, ``PAIR_SUBMISSION_MISMATCH``) and stays measurable.
* A permit stands until the submission is accepted or refused for a reason that cannot change by
  waiting. A transient refusal (``SELF_<readiness state>``) keeps the permit, because the scripted
  arm also retries every tick; so the arms differ only in WHEN the first attempt is allowed.
* Everything after an accepted ``Team.start`` (rendezvous, align, grasp, lift, carry, barriers,
  lower, release, the fixed-enum status wire) is the unmodified scripted skill.

Nothing here reads a simulator, a pose, a joint or a result. The gate sees only the arguments of a
claim and the acknowledgement of ``Team.start``.
"""
from __future__ import annotations

from harness.zone_final_pair_contract import ROBOTS
from harness.zone_final_pair_runtime import Runtime

GATE_VERSION = 'ugrp.pair_llm_claim_gate.v2'     # v2: + refusal_total / last_event (own status source)
NOT_RELEASED = 'CLAIM_NOT_RELEASED'
#: Refusals of ``Team.start`` that waiting can resolve; the permit stays and the next idle tick retries
#: (the scripted Runtime retries every tick as well). Everything else consumes the permit.
RETRYABLE_PREFIX = 'SELF_'
NON_RETRYABLE_SELF = ('SELF_STOPPED',)


def retryable(reason) -> bool:
    return (isinstance(reason, str) and reason.startswith(RETRYABLE_PREFIX)
            and reason not in NON_RETRYABLE_SELF)


class ClaimGate:
    """Permits released by the study scheduler, consumed by ``Runtime.step``'s start call."""

    def __init__(self, robots=ROBOTS):
        self.robots = tuple(robots)
        self.permits: dict = {}
        self.log: list = []
        self.refused_without_permit = {rid: 0 for rid in self.robots}
        self.retries = {rid: 0 for rid in self.robots}
        self.refusals = {rid: {} for rid in self.robots}      # reason -> count, every refused submission
        self.refusal_total = {rid: 0 for rid in self.robots}  # every refused submission, all reasons
        self.last_event = {rid: None for rid in self.robots}  # the latest submission outcome of the robot
        self.listeners: list = []
        self._raw = None

    def bind(self, raw_start) -> None:
        if self._raw is not None:
            raise RuntimeError('claim gate is already bound to a Team.start')
        self._raw = raw_start

    # -- the scheduler side --------------------------------------------------------
    def grant(self, rid, order_id, zone, partner, *, now, call_ref=None) -> dict:
        if rid not in self.robots or partner not in self.robots or rid == partner:
            raise ValueError(f'a permit needs two distinct pair robots, got {rid!r} and {partner!r}')
        replaced = self.permits.get(rid)
        permit = {'robot_id': rid, 'order_id': order_id, 'zone': zone, 'partner': partner,
                  'released_at_sim_s': float(now), 'call_ref': call_ref}
        self.permits[rid] = permit
        self.log.append({'event': 'claim_released', 'sim_s': float(now), 'robot_id': rid, 'order_id': order_id,
                         'zone': zone, 'partner': partner, 'call_ref': call_ref,
                         'replaced_pending': replaced is not None})
        return permit

    def revoke(self, rid, *, now, reason) -> bool:
        permit = self.permits.pop(rid, None)
        if permit is not None:
            self.log.append({'event': 'claim_revoked', 'sim_s': float(now), 'robot_id': rid, 'reason': reason,
                             'call_ref': permit['call_ref']})
        return permit is not None

    def pending(self, rid) -> bool:
        return rid in self.permits

    def status_view(self, rid) -> dict:
        """This robot's own bookkeeping for ``pair_llm_status.build``: nothing about the partner, no raw detail."""
        permit = self.permits.get(rid)
        event = self.last_event.get(rid)
        return {'permit_released_at_sim_s': None if permit is None else permit['released_at_sim_s'],
                'last_event': None if event is None else dict(event),
                'refusal_total': self.refusal_total.get(rid, 0)}

    # -- the runtime side ----------------------------------------------------------
    def start(self, rid, item_ref=None, target_zone=None, partner_id=None, *, now):
        """Drop-in for ``Team.start``: refuse without a permit, else submit the claim's own arguments."""
        if self._raw is None:
            raise RuntimeError('claim gate is not bound to a Team.start')
        permit = self.permits.get(rid)
        if permit is None:
            self.refused_without_permit[rid] = self.refused_without_permit.get(rid, 0) + 1
            return {'robot_id': rid, 'api': 'pair_carry', 'accepted': False, 'rejected_reason': NOT_RELEASED,
                    'job_id': None, 'local_state': 'command_rejected'}
        ack = self._raw(rid, permit['order_id'], permit['zone'], permit['partner'], now=now)
        if ack['accepted']:
            self.last_event[rid] = {'kind': 'accepted', 'reason': None, 'sim_s': float(now), 'retryable': False}
        else:
            reason = str(ack.get('rejected_reason'))
            self.refusals[rid][reason] = self.refusals[rid].get(reason, 0) + 1
            self.refusal_total[rid] += 1
            self.last_event[rid] = {'kind': 'refused', 'reason': reason, 'sim_s': float(now),
                                    'retryable': retryable(reason)}
        if not ack['accepted'] and retryable(ack.get('rejected_reason')):
            self.retries[rid] += 1
            return ack
        self.permits.pop(rid, None)
        row = {'event': 'claim_submitted', 'sim_s': float(now), 'robot_id': rid, 'order_id': permit['order_id'],
               'zone': permit['zone'], 'partner': permit['partner'], 'call_ref': permit['call_ref'],
               'released_at_sim_s': permit['released_at_sim_s'], 'accepted': bool(ack['accepted']),
               'reason': ack.get('rejected_reason'), 'job_id': ack.get('job_id'),
               'retried_ticks': self.retries[rid]}
        self.retries[rid] = 0
        self.log.append(row)
        for listener in self.listeners:
            listener(row)
        return ack

    def record(self) -> dict:
        return {'version': GATE_VERSION, 'log': [dict(r) for r in self.log],
                'refused_without_permit': dict(self.refused_without_permit),
                'refusals': {rid: dict(rows) for rid, rows in self.refusals.items()},
                'refusal_total': dict(self.refusal_total),
                'pending': {rid: dict(p) for rid, p in self.permits.items()}}


class GatedRuntime(Runtime):
    """The v88 pair ``Runtime`` with ``Team.start`` behind a :class:`ClaimGate` (LLM arms only).

    ``Runtime.step`` and every other method are inherited unchanged; the ``rule`` arm uses the plain
    ``Runtime``. After a permit is granted the robot may submit again (``submitted`` is cleared), so a
    robot whose pair job ended can claim a retry.
    """

    def __init__(self, static, calibration_path, calibration_sha, *, seed, provider_factory=None, gate=None):
        super().__init__(static, calibration_path, calibration_sha, seed=seed, provider_factory=provider_factory)
        try:
            self.gate = gate or ClaimGate(ROBOTS)
            self.gate.bind(self.team.start)
            self.team.start = self.gate.start
        except Exception:
            self.close()
            raise

    def grant(self, rid, order_id, zone, partner, *, now, call_ref=None) -> dict:
        permit = self.gate.grant(rid, order_id, zone, partner, now=now, call_ref=call_ref)
        self.submitted.discard(rid)
        return permit

    def record(self):
        return {**super().record(), 'claim_gate': self.gate.record()}


__all__ = ['GATE_VERSION', 'NOT_RELEASED', 'ClaimGate', 'GatedRuntime', 'retryable']
