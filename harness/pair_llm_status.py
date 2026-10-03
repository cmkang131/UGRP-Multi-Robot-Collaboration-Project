"""The robot's OWN skill/claim status, as a compact closed record for the model (pair LLM layer, v100).

Why: in the v99 live smoke1 the blind controller refused both robots' start every tick (``SELF_UNCERTAIN``,
1,069 times each) while the model's only evidence was ``own_command_history`` (``command_issued``) and a
low-confidence ``self_belief``, so it kept saying ``continue``. The refusal is the robot's own software
state (the acknowledgement of its own ``Team.start`` call and its own executor's job events), not simulator
truth, so it may be told to the model. This module builds that record and checks it.

What it contains (all of it is the robot's own bookkeeping):

* ``last_outcome``: the latest outcome of the robot's own claim / skill, one of a CLOSED enum
  (:data:`OUTCOMES`);
* ``reason``: one token of a closed vocabulary or ``null``; anything outside it becomes ``other``;
* ``since_claim_s``: SIM seconds since this robot issued its latest ``claim`` (its own decision time);
* ``refusals_since_last_call``: how many times the robot's own start was refused since this robot's previous
  model call started.

What it never contains: a pose, a joint, a contact, a delivery or success flag, a partner's state, a raw
reason string or any executor ``detail``. A job that ended is reported as the study's own two classes only
(``queue_empty`` / ``local_timeout``, ``zone_study_contract.LOCAL_STATES``). It is not a success flag: the end of
a job is not a carried beam.

What partner-caused events reveal (the reviewed and accepted design, M1 of the #371 review): the robot's own
command outcome. ``PAIR_SUBMISSION_MISMATCH`` and ``PAIR_STATIC_INPUT_MISMATCH`` (the partner's pending submission
differs) reach THIS robot as a refused claim (``claim_rejected``), and reach the robot that was waiting as the end of
its job (``pair_job_ended``); ``PAIR_RENDEZVOUS_TIMEOUT`` (the partner never started) is also a job-end reason of
the waiting robot, not a start refusal, and becomes ``queue_empty``. So a partner-caused refusal or job end reveals
ONE bit through the robot's own command outcome: "my claim was not accepted" / "the pair job ended", with the time.
That bit is the robot's own acknowledgement and job event (a real robot gets it too; since v99
``own_command_history`` already turns a rejected claim into ``command_rejected`` and a finished job into
``queue_empty`` / ``local_timeout``), and it is identical in ``no_comm`` and ``peer_nl``, so the arms still differ
only in the dialogue channel. What the status does NOT carry is the NAME of the partner-caused reason: such a
refusal is folded to ``other``. This module does not claim that ``no_comm`` learns nothing about the partner.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

STATUS_VERSION = 'ugrp.pair_llm_own_status.v1'
STATUS_KEYS = ('last_outcome', 'reason', 'since_claim_s', 'refusals_since_last_call')
OUTCOMES = ('no_claim', 'claim_released', 'start_refused', 'claim_rejected', 'pair_job_running', 'pair_job_ended',
            'look_around_running', 'look_around_ended')
OTHER = 'other'
#: Own-readiness refusals of ``Team.start`` (``'SELF_' + readiness state``; the states are listed in
#: ``zone_pair_admission.readiness_snapshot``: stopped, busy, incompatible, uncertain, invalid_image, occupied).
SELF_REASONS = ('SELF_STOPPED', 'SELF_BUSY', 'SELF_INCOMPATIBLE', 'SELF_UNCERTAIN', 'SELF_INVALID_IMAGE',
                'SELF_OCCUPIED')
#: Refusals of the claim's own arguments against the robot's own static order sheet and map.
TASK_REASONS = ('BAD_PAIR_ARGUMENTS', 'UNKNOWN_ORDER', 'UNSUPPORTED_PAIR_ORDER', 'WRONG_PAIR_DESTINATION',
                'UNSUPPORTED_PAIR')
END_REASONS = ('queue_empty', 'local_timeout')
REASONS_BY_OUTCOME = {
    'no_claim': (), 'claim_released': (), 'pair_job_running': (), 'look_around_running': (),
    'start_refused': SELF_REASONS + (OTHER,),
    'claim_rejected': TASK_REASONS + ('SELF_STOPPED', OTHER),
    'pair_job_ended': END_REASONS + (OTHER,), 'look_around_ended': END_REASONS + (OTHER,)}
#: Tie-break of two facts with the same SIM time: the later stage of the story wins.
_RANK = {'claim_released': 0, 'start_refused': 1, 'claim_rejected': 2, 'pair_job_ended': 3, 'look_around_ended': 3}
_ENDED = {'pair_carry': 'pair_job_ended', 'look_around': 'look_around_ended'}
_RUNNING = {'pair_carry': 'pair_job_running', 'look_around': 'look_around_running'}


def reason_token(reason, outcome: str) -> str | None:
    """``reason`` if it is in the closed vocabulary of ``outcome``, else ``other`` (``None`` where none is kept)."""
    allowed = REASONS_BY_OUTCOME[outcome]
    if not allowed:
        return None
    return reason if isinstance(reason, str) and reason in allowed else OTHER


def end_class(reason) -> str:
    """The study's own classification of a finished job (``on_executor_event``): a local timeout or not."""
    return 'local_timeout' if isinstance(reason, str) and reason.startswith('LOCAL_TIMEOUT') else 'queue_empty'


def build(*, now, claim_issued_s, view: Mapping, job_kind, last_end, refusals_since_last_call) -> dict:
    """One status record. All inputs are the robot's OWN bookkeeping.

    ``view`` is the claim gate's record of this robot (``ClaimGate.status_view``): ``permit_released_at_sim_s``
    (the pending permit or None), ``last_event`` (the latest submission outcome or None) and nothing else.
    ``job_kind`` is the kind of the robot's own running job (or None); ``last_end`` the robot's latest own job
    end ``{'job_kind', 'reason_class', 'sim_s'}`` (or None).
    """
    outcome, reason = None, None
    if job_kind in _RUNNING:
        outcome = _RUNNING[job_kind]
    else:
        facts = []                                              # (sim_s, rank, outcome, raw reason)
        permit_t = view.get('permit_released_at_sim_s')
        event = view.get('last_event')
        if permit_t is not None:
            facts.append((float(permit_t), _RANK['claim_released'], 'claim_released', None))
        if isinstance(event, Mapping) and event.get('kind') == 'refused':
            if not event.get('retryable'):
                stage = 'claim_rejected'                        # the permit was consumed by this refusal
            else:
                stage = 'start_refused' if permit_t is not None else None   # no permit left: the refusal is stale
            if stage is not None:
                facts.append((float(event['sim_s']), _RANK[stage], stage, event.get('reason')))
        if isinstance(last_end, Mapping) and last_end.get('job_kind') in _ENDED:
            facts.append((float(last_end['sim_s']), _RANK['pair_job_ended'], _ENDED[last_end['job_kind']],
                          last_end.get('reason_class')))
        if facts:
            _, _, outcome, reason = max(facts, key=lambda f: (f[0], f[1]))
    if outcome is None:
        outcome = 'no_claim'
    since = None if claim_issued_s is None else round(max(0., float(now) - float(claim_issued_s)), 3)
    return {'last_outcome': outcome, 'reason': reason_token(reason, outcome), 'since_claim_s': since,
            'refusals_since_last_call': max(0, int(refusals_since_last_call))}


def status_violations(status: object) -> list:
    """Every violation of the closed own-status record (empty = clean). Used by the payload boundary check."""
    if not isinstance(status, Mapping):
        return ['own_status must be an object']
    out = []
    extra, missing = sorted(set(status) - set(STATUS_KEYS)), [k for k in STATUS_KEYS if k not in status]
    if extra:
        out.append(f'own_status has key(s) outside the closed schema: {extra}')
    if missing:
        out.append(f'own_status misses key(s): {missing}')
    if out:
        return out
    outcome = status['last_outcome']
    if outcome not in OUTCOMES:
        return [f'own_status.last_outcome {outcome!r} is not one of {OUTCOMES}']
    allowed = REASONS_BY_OUTCOME[outcome]
    reason = status['reason']
    if (not allowed and reason is not None) or (allowed and reason not in allowed):
        out.append(f'own_status.reason {reason!r} is not in the closed vocabulary of {outcome}')
    since = status['since_claim_s']
    if since is not None and (isinstance(since, bool) or not isinstance(since, (int, float))
                              or not math.isfinite(since) or since < 0):
        out.append('own_status.since_claim_s must be null or a non-negative finite number')
    count = status['refusals_since_last_call']
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        out.append('own_status.refusals_since_last_call must be a non-negative integer')
    return out


def record() -> dict:
    """What the bundle records about the status."""
    return {'version': STATUS_VERSION, 'keys': list(STATUS_KEYS), 'outcomes': list(OUTCOMES),
            'reasons': {k: list(v) for k, v in REASONS_BY_OUTCOME.items() if v},
            'source': 'the robot\'s own start acknowledgement (ClaimGate) and its own executor job events',
            'excluded': 'pose, joints, contact, delivery/success flags, partner state, raw reasons, executor detail; '
                        'the name of a partner-caused refusal folds to "other" (the refused-claim / job-end event itself stays '
                        'visible, identically in no_comm and peer_nl)'}


__all__ = ['STATUS_VERSION', 'STATUS_KEYS', 'OUTCOMES', 'SELF_REASONS', 'TASK_REASONS', 'END_REASONS',
           'REASONS_BY_OUTCOME', 'reason_token', 'end_class', 'build', 'status_violations', 'record']
