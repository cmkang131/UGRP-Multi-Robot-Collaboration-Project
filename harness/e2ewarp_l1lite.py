"""L1-lite slot allocation: two robots, private constraints, four channels.

Scope (2026-10-20 plan §1/§3; **default OFF**):

- task: two robots start in the west room, pass the divider's wide door and
  each reaches one half ("slot") of the zone B floor marking.  Picking and
  placing are out of scope; the own-input ``ARRIVED`` claim is the "delivered"
  signal and is never a physical-success claim.
- order sheet ``v_l1lite``: two one-robot slot deliveries (``B-left`` and
  ``B-right``) with ``assigned_robot=None``.  It replaces the fixed
  ``SLOT_BY_ROBOT`` order-sheet slot **only** when
  ``E2EWARP_NAV_L1LITE=on_v1`` is set *and* every check below passes; a process
  without the variable keeps the r5 behaviour byte-identical.
- information asymmetry: exactly one robot per seed receives a *private*
  loading constraint (which slot it may use).  The constraint is written only
  into that robot's own brief.  The peer brief, the peer's channel input and
  the navigation adapter's static never contain it.  A robot may *choose* to
  disclose it through the permitted channel; that is measured, not leaked.
- four channels, identical decisions and code driving:
  ``no_comm`` (0 messages), ``structured`` (fixed enum
  ``my_constraint|claim_slot|ack``), ``peer_en`` (free English) and
  ``leader_en`` (the leader, ``seed % 2``, assigns both slots and the follower
  acknowledges).
- the LLM decides the slot(s); the code drives.  A missing, malformed or
  duplicate decision fails closed with a named error and can never make a run
  a success (``L1LITE_NO_DECISION``, ``L1LITE_INVALID_SLOT``,
  ``L1LITE_DUPLICATE_SLOT``, ``L1LITE_LEADER_UNASSIGNED``,
  ``L1LITE_LEADER_ACK_MISSING``, ``L1LITE_SEED_UNKNOWN``).

The seed table below is the deterministic, pre-registerable generator required
by plan §3 item 2.  It is *not* written by this file into any robot input; the
queue records only its sha256 (``constraint_table_digest``) so the pre-registered
table can be pinned.  The prereg document itself is written by Claude (10/22).
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping

from harness.e2ewarp_selfnav import SLOT_LEFT, SLOT_RIGHT, SLOTS
from harness.zone_study_contract import ContractViolation

VERSION = 'ugrp.e2ewarp.l1lite.v1'
ORDER_SHEET_VERSION = 'v_l1lite'
ROBOTS = ('r1', 'r2')
CONDITIONS = ('no_comm', 'peer_en', 'leader_en', 'structured')
STRUCTURED_ACTS = ('my_constraint', 'claim_slot', 'ack')
#: One message per robot per decision round; 3 rounds is the protocol design
#: value (round 1 claim, round 2 answer, round 3 last chance), not a measured
#: constant.  Exhausting it records the duplicate-slot error, never success.
MAX_ROUNDS = 3
#: The gate's SIM budget is 60 s; an allocation that never produced an
#: ``ARRIVED`` claim for both robots by then is reported as the 60 SIM s
#: deadlock auxiliary metric (plan §3 item 4), separately from a decision error.
DEADLOCK_SIM_S = 60.0
#: Free-prose protocol cap (design value; keeps one turn bounded and comparable
#: across seeds).  Only the message body is capped, never the decision payload.
MAX_UTTERANCE_CHARS = 400
#: ``r1`` keeps the authored north lane and ``r2`` the south lane
#: (``e2ewarp_nav_gate.LANE_Y``); facing +x (east), robot-left is +y (north), so
#: the north-lane robot's spawn-side slot is the left half of the marking and
#: the south-lane robot's is the right half.  Derived from the already-authored
#: lane assignment (same derivation as ``SLOT_BY_ROBOT``), not a tuned constant.
SPAWN_LANE_SLOT = {'r1': SLOT_LEFT, 'r2': SLOT_RIGHT}
LANE = {'r1': 'north', 'r2': 'south'}

ORDER_SHEET = dict(
    schema='ugrp.e2ewarp.l1lite_order_sheet.v1',
    version=ORDER_SHEET_VERSION,
    scenario_id='l1lite_two_slot_delivery',
    destination_zone='B',
    orders=[
        dict(order_id='B-left', kind='slot_delivery', count=1, required_robots=1,
             destination_zone='B', slot=SLOT_LEFT, assigned_robot=None),
        dict(order_id='B-right', kind='slot_delivery', count=1, required_robots=1,
             destination_zone='B', slot=SLOT_RIGHT, assigned_robot=None),
    ],
    note=('two one-robot slot deliveries, no robot named in the sheet; '
          'picking and placing are outside this task'),
)

#: Deterministic private-constraint table (plan §1, Claude decision 2026-10-20).
#: ``robot`` is the single robot that receives the constraint, ``slot`` the only
#: slot it may use.  TEST seeds (601-606) are the pre-registered main-run seeds;
#: DEV seeds (701-702) are only for the shared-component tournament and are
#: never pooled with TEST.  The no_comm default rule (private constraint if
#: any, else the robot's spawn-lane slot) collides exactly when the constrained
#: robot's slot equals the *peer's* spawn-lane slot.  With r1 3 / r2 3 and
#: left 3 / right 3 the collision count is necessarily even (0, 2 or 4); the
#: TEST table takes 4 so that most seeds need information exchange (no_comm
#: expected 2/6), and ``table_violations`` asserts it so a later edit cannot
#: silently tip it.
TEST_TABLE = {
    601: dict(robot='r1', slot=SLOT_RIGHT),   # no_comm collision (r2 lane=right)
    602: dict(robot='r2', slot=SLOT_LEFT),    # no_comm collision (r1 lane=left)
    603: dict(robot='r1', slot=SLOT_LEFT),    # no_comm split
    604: dict(robot='r1', slot=SLOT_RIGHT),   # no_comm collision
    605: dict(robot='r2', slot=SLOT_LEFT),    # no_comm collision
    606: dict(robot='r2', slot=SLOT_RIGHT),   # no_comm split
}
DEV_TABLE = {
    701: dict(robot='r1', slot=SLOT_RIGHT),   # no_comm collision
    702: dict(robot='r2', slot=SLOT_RIGHT),   # no_comm split
}
SEED_TABLE = {**TEST_TABLE, **DEV_TABLE}
DEV_SEEDS = tuple(sorted(DEV_TABLE))
TABLE_SEEDS = tuple(sorted(TEST_TABLE))
#: sha256 of the canonical table; recorded in the queue so the pre-registered
#: constraint assignment is pinned without writing the private rows into a run
#: input (the table is admin data, not a robot observation).
TABLE_SHA256 = hashlib.sha256(
    json.dumps(dict(version=VERSION, test=TEST_TABLE, dev=DEV_TABLE), sort_keys=True,
               separators=(',', ':')).encode()).hexdigest()

#: Pinned planner prices (USD per 1M tokens) copied from
#: ``configs/model_endpoints.json`` (CoreWeave fp4, recorded 2026-10-16).
PLANNER_PRICE_USD_PER_MILLION = dict(prompt=0.1, completion=0.34,
                                     input_cache_read=0.1)


class L1LiteError(ValueError):
    """A fail-closed L1-lite decision/channel error with a stable code."""

    def __init__(self, code, *, detail=None, record=None):
        self.code = str(code)
        self.detail = None if detail is None else str(detail)
        self.record = copy.deepcopy(record) if record is not None else None
        super().__init__(self.code + (':' + self.detail if self.detail else ''))


def constraint_table_digest():
    """sha256 of the pre-registered private-constraint table."""
    return TABLE_SHA256


def constraint_table():
    """A fresh copy of the pre-registered TEST admin table (never a robot input)."""
    return copy.deepcopy(TEST_TABLE)


def dev_constraint_table():
    """A fresh copy of the DEV admin table (tournament only, never pooled)."""
    return copy.deepcopy(DEV_TABLE)


def seed_split(seed):
    """'test' or 'dev' for a known seed; recorded in the queue."""
    _check_seed(seed)
    return 'dev' if seed in DEV_TABLE else 'test'


def table_violations(table):
    """Why a constraint table is not the pre-registered balanced table."""
    out = []
    if not isinstance(table, Mapping) or set(table) != set(TABLE_SEEDS):
        return ['table must hold exactly seeds ' + ','.join(str(s) for s in TABLE_SEEDS)]
    per_robot = {r: 0 for r in ROBOTS}
    per_slot = {s: 0 for s in SLOTS}
    collisions = 0
    for seed in TABLE_SEEDS:
        row = table[seed]
        if not isinstance(row, Mapping) or set(row) != {'robot', 'slot'}:
            out.append(f'seed {seed}: row must hold exactly robot and slot')
            continue
        robot, slot = row['robot'], row['slot']
        if robot not in ROBOTS or slot not in SLOTS:
            out.append(f'seed {seed}: invalid robot/slot {robot!r}/{slot!r}')
            continue
        per_robot[robot] += 1
        per_slot[slot] += 1
        peer = next(r for r in ROBOTS if r != robot)
        if slot == SPAWN_LANE_SLOT[peer]:
            collisions += 1
    if any(count != 3 for count in per_robot.values()):
        out.append('robot balance must be 3/3, got ' + repr(per_robot))
    if any(count != 3 for count in per_slot.values()):
        out.append('slot balance must be 3/3, got ' + repr(per_slot))
    if collisions not in (0, 2, 4):
        out.append('no_comm collision count must be even with 3/3 balances, got '
                   + str(collisions))
    if collisions != 4:
        out.append('the pre-registered table has 4 no_comm collisions, got '
                   + str(collisions))
    return out


if table_violations(TEST_TABLE):
    raise RuntimeError('L1LITE_CONSTRAINT_TABLE_INVALID:' + '; '.join(
        table_violations(TEST_TABLE)))


def _check_seed(seed):
    if isinstance(seed, bool) or not isinstance(seed, int) or seed not in SEED_TABLE:
        raise L1LiteError('L1LITE_SEED_UNKNOWN', detail=str(seed))
    return seed


def constraint_text(robot, slot):
    """The private constraint sentence shown to its owner only (English)."""
    return (f'Loading constraint for {robot}: only the B-{slot} slot can be '
            'used for this delivery.')


def private_constraint(seed, robot):
    """This robot's private constraint, or None; never returns the peer's row."""
    _check_seed(seed)
    if robot not in ROBOTS:
        raise L1LiteError('L1LITE_ROBOT_UNKNOWN', detail=str(robot))
    row = SEED_TABLE[seed]
    if row['robot'] != robot:
        return None
    return dict(kind='loading_constraint', robot=robot, slot=row['slot'],
                text=constraint_text(robot, row['slot']), private=True)


def default_slot(seed, robot):
    """The pre-registered no_comm rule: constraint slot, else spawn-lane slot."""
    constraint = private_constraint(seed, robot)
    return constraint['slot'] if constraint else SPAWN_LANE_SLOT[robot]


def all_constraints(seed):
    """Admin/eval-only map ``robot -> constrained slot or None`` (never an input)."""
    _check_seed(seed)
    return {r: (SEED_TABLE[seed]['slot'] if SEED_TABLE[seed]['robot'] == r else None)
            for r in ROBOTS}


def order_sheet():
    """The authored v_l1lite order sheet (unassigned, two one-robot deliveries)."""
    return copy.deepcopy(ORDER_SHEET)


def reply_format(condition):
    """Response-format guidance carried in every brief (all four conditions).

    The runtime SYSTEM line only says the reply is ``act`` plus ``message``
    with "permitted condition content" as the body; it never spells out the
    body shape this channel validates.  Without the shape stated here, the
    leader_en smoke (2026-10-24) failed twice: the follower sent its report
    body as a bare string instead of ``{"text": "..."}``, the channel
    rejected it, and the run recorded L1LITE_LEADER_REPORT_MISSING.  The
    text below names the exact envelope and body per condition; it carries
    no private information (identical for both robots of a condition).
    """
    base = ('Reply with a single JSON object with exactly two fields: '
            '"act" (the id of one candidate offered this round) and '
            '"message" (null, or an object of the form '
            '{"recipients": ["<the other robot id>"], "body": {...}}). '
            'No other fields.')
    if condition == 'no_comm':
        return base + (' This condition has no communication: "message" '
                       'must be null.')
    if condition == 'structured':
        return base + (' In this condition the message body must be exactly '
                       '{"act": "<one of: my_constraint, claim_slot, ack>", '
                       '"slot": "<one of: left, right>"} with no other '
                       'fields and no free text.')
    return base + (' In this condition the message body must be exactly '
                   '{"text": "<your message in English>"}: a JSON object '
                   'whose only field is "text". Never send the message as a '
                   'bare string, and do not add fields such as "act" or '
                   '"slot" to a free-text body.')


def robot_brief(seed, robot, condition):
    """Per-robot LLM brief: order sheet, own constraint, own lane, no peer rows.

    This mapping is the *only* place a private constraint is written.  It is
    passed to that robot's own planner prompt and never to the peer, the
    channel or the navigation adapter (``nav_static`` rejects ``own_constraint``
    by allowlist, which the boundary test pins).
    """
    if condition not in CONDITIONS:
        raise L1LiteError('L1LITE_CONDITION_UNKNOWN', detail=str(condition))
    if robot not in ROBOTS:
        raise L1LiteError('L1LITE_ROBOT_UNKNOWN', detail=str(robot))
    peer = next(r for r in ROBOTS if r != robot)
    return dict(
        schema=VERSION, robot=robot, peer=peer,
        # The leader role exists only in the leader_en channel; carrying it in
        # the other conditions would bias an otherwise peer-level dialogue.
        role=('leader' if condition == 'leader_en'
              and robot == ROBOTS[seed % len(ROBOTS)] else 'worker'),
        condition=condition,
        order_sheet=order_sheet(),
        own_lane=LANE[robot],
        own_lane_slot=SPAWN_LANE_SLOT[robot],
        own_constraint=private_constraint(seed, robot),
        default_slot_rule=('choose your private constraint slot if you have one; '
                           'otherwise choose your own spawn-lane slot'),
        reply_format=reply_format(condition),
    )


def leader_for_seed(seed):
    """Leader rotation identical to the runner's ``leader_for_seed`` (seed % 2)."""
    _check_seed(seed)
    return ROBOTS[seed % len(ROBOTS)]


# ---------------------------------------------------------------------------
# Channel schemas (four main conditions; identical to the existing runner
# topology, but with the L1-lite structured enum and English free prose).


def _envelope_problems(sender, recipients):
    out = []
    if sender not in ROBOTS:
        out.append('sender outside execution robot set: ' + str(sender))
    if not isinstance(recipients, (list, tuple)) or not recipients:
        out.append('recipients must be a non-empty list')
        return out
    if len(set(recipients)) != len(recipients):
        out.append('recipients must be unique')
    if sender in recipients:
        out.append('a robot cannot send to itself')
    outside = [r for r in recipients if r not in ROBOTS]
    if outside:
        out.append('recipient outside execution robot set: '
                   + ','.join(str(r) for r in outside))
    return out


def _structured_problems(body):
    if not isinstance(body, Mapping):
        return ['structured message must be an object']
    if set(body) != {'act', 'slot'}:
        return ['structured message needs exactly act and slot']
    if body['act'] not in STRUCTURED_ACTS:
        return [f'act must be one of {STRUCTURED_ACTS}, got {body["act"]!r}']
    if body['slot'] not in SLOTS:
        return [f'slot must be one of {SLOTS}, got {body["slot"]!r}']
    return []


def has_hangul(text):
    return bool(re.search('[\uac00-\ud7a3]', str(text or '')))


def free_text_problems(body):
    if not isinstance(body, Mapping):
        return ['free message body must be an object']
    if set(body) != {'text'}:
        return ['a free message body must be exactly {"text": "..."}']
    text = body.get('text')
    if not isinstance(text, str) or not text.strip():
        return ['free message body needs non-empty text']
    if len(text) > MAX_UTTERANCE_CHARS:
        return [f'free message body exceeds {MAX_UTTERANCE_CHARS} characters']
    return []


def validate_l1lite_message(condition, sender, recipients, body, *, seed=None):
    """Validate one L1-lite message; raise ``ContractViolation`` on any breach.

    Format/topology only.  Unverified peer claims (including a false
    ``my_constraint``) stay deliverable data: honesty is measured by the
    evaluator, never enforced by the transport.
    """
    if condition not in CONDITIONS:
        raise ContractViolation('unknown L1-lite condition: ' + str(condition))
    problems = _envelope_problems(sender, recipients)
    if problems:
        raise ContractViolation('; '.join(problems))
    if condition == 'no_comm':
        raise ContractViolation('no_comm allows no messages at all')
    if condition == 'structured':
        problems = _structured_problems(body)
    else:
        problems = free_text_problems(body)
    if problems:
        raise ContractViolation('; '.join(problems))
    return True


def message_language_slip(condition, body):
    """True for a free-prose message with Hangul (recorded, never blocking)."""
    return (condition in ('peer_en', 'leader_en') and isinstance(body, Mapping)
            and has_hangul(body.get('text')))


# ---------------------------------------------------------------------------
# Allocation protocol.  The caller supplies ``ask(robot, dynamic)`` and returns
# the model's parsed ``{'act': candidate_id, 'message': envelope_or_None}``;
# this module contains no HTTP, no physics and no clock, so a unit test stubs
# the LLM and the full protocol is deterministic.

_CANDIDATE_BY_SLOT = {slot: dict(id='slot_' + slot, slot=slot) for slot in SLOTS}


def _channel(condition, seed, channels=None):
    from harness.e2e_warp_runtime import Channels
    if channels is not None:
        return channels
    return Channels(condition, seed, robots=ROBOTS, message_schema='l1lite')


def _record_skeleton(condition, seed):
    return dict(
        schema=VERSION, condition=condition, seed=seed, robots=list(ROBOTS),
        leader=leader_for_seed(seed),
        order_sheet_version=ORDER_SHEET_VERSION,
        constraint_table_sha256=constraint_table_digest(),
        constraints=all_constraints(seed),
        transcript=[], calls=[], messages=[], errors=[], message_drops=[],
        decisions={}, rounds=0, utterances=0, deadlock=False, fatal=False,
        distinct=None, constraint_ok=None, success_eligible=False,
        slot_assignment='llm_decision',
    )


def _finish(record, channels):
    record['messages'] = copy.deepcopy(channels.events)
    record['utterances'] = len(channels.events)
    slots = dict(record['decisions'])
    record['distinct'] = (set(slots) == set(ROBOTS) and len(set(slots.values())) == 2
                          and set(slots.values()) == set(SLOTS))
    record['constraint_ok'] = {
        r: (record['constraints'].get(r) is None
            or slots.get(r) == record['constraints'].get(r))
        for r in ROBOTS}
    record['success_eligible'] = bool(record['distinct'] and not record['errors']
                                      and not record['fatal'])
    return record


def _validate_reply(answer, candidate_ids, robot, round_no, record):
    if not isinstance(answer, Mapping):
        raise L1LiteError('L1LITE_INVALID_DECISION',
                          detail=f'{robot}:round{round_no}:not_a_mapping', record=record)
    if set(answer) != {'act', 'message'}:
        raise L1LiteError('L1LITE_INVALID_DECISION',
                          detail=f'{robot}:round{round_no}:keys', record=record)
    if answer['act'] not in candidate_ids:
        raise L1LiteError('L1LITE_INVALID_SLOT',
                          detail=f'{robot}:round{round_no}:{answer["act"]!r}',
                          record=record)
    return answer


def _ask_round(record, channels, ask, robot, round_no, candidates, *,
               record_message=True, inbox=None):
    inbox = channels.inbox(robot) if inbox is None else inbox
    dynamic = dict(round=round_no, candidates=copy.deepcopy(candidates), **inbox)
    answer = ask(robot, dynamic)
    answer = _validate_reply(answer, {c['id'] for c in candidates}, robot, round_no,
                             record)
    chosen = next(c for c in candidates if c['id'] == answer['act'])
    message = answer.get('message')
    sent, dropped = False, None
    if message is not None and record_message:
        try:
            channels.validate(robot, message)
            channels.send(robot, message, now=0.0)
            sent = True
        except (ValueError, TypeError) as exc:
            dropped = str(exc)
            record['message_drops'].append(dict(robot=robot, round=round_no,
                                                reason=dropped))
            record['errors'].append('L1LITE_MESSAGE_INVALID')
    elif message is not None:
        dropped = 'L1LITE_MESSAGE_NOT_EXPECTED_IN_THIS_PHASE'
        record['message_drops'].append(dict(robot=robot, round=round_no,
                                            reason=dropped))
    record['transcript'].append(dict(robot=robot, round=round_no, act=answer['act'],
                                     slot=chosen.get('slot'),
                                     message=(message.get('body') if message else None),
                                     message_sent=sent, message_dropped=dropped,
                                     inbox_n=len(inbox.get('inbox') or ())))
    record['calls'].append(dict(robot=robot, round=round_no, act=answer['act'],
                                accepted=True, message_sent=sent))
    return chosen, message, sent


def allocate_slots(condition, seed, *, ask, max_rounds=MAX_ROUNDS, channels=None):
    """Run the pre-drive allocation and return an admin/eval-only record.

    ``ask`` is the only model boundary: ``ask(robot, dynamic) -> answer`` where
    ``answer`` is the parsed ``{'act', 'message'}`` object.  A reply that does
    not name one of the advertised candidates, or a missing reply, raises
    :class:`L1LiteError` with a stable code and the partial record attached, so
    the runner records the named error instead of starting a run.
    """
    if condition not in CONDITIONS:
        raise L1LiteError('L1LITE_CONDITION_UNKNOWN', detail=str(condition))
    _check_seed(seed)
    if not callable(ask):
        raise L1LiteError('L1LITE_ASK_REQUIRED')
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds < 1:
        raise L1LiteError('L1LITE_MAX_ROUNDS_INVALID', detail=str(max_rounds))
    channels = _channel(condition, seed, channels)
    record = _record_skeleton(condition, seed)
    leader = record['leader']
    follower = next(r for r in ROBOTS if r != leader)
    try:
        if condition == 'no_comm':
            # One round, no messages: the LLM still decides, but its only
            # candidate is the pre-registered default rule (constraint slot if
            # any, else the own spawn-lane slot).  A deviating or missing
            # decision is a fail-closed invalid slot, never a fallback.
            for robot in ROBOTS:
                slot = default_slot(seed, robot)
                candidates = [copy.deepcopy(_CANDIDATE_BY_SLOT[slot])]
                chosen, _message, _sent = _ask_round(
                    record, channels, ask, robot, 1, candidates,
                    record_message=False)
                record['decisions'][robot] = chosen['slot']
            record['rounds'] = 1
            if len(set(record['decisions'].values())) != 2:
                # The two independent default choices collide: a named error,
                # not a silent same-slot run.  The slots stay bound so the
                # evaluator can still report the measured consequence.
                record['errors'].append('L1LITE_DUPLICATE_SLOT')
        elif condition in ('structured', 'peer_en'):
            for round_no in range(1, max_rounds + 1):
                # Snapshot every inbox first so both robots decide on the same
                # round's information set (a same-round send cannot leak in).
                inboxes = {r: channels.inbox(r) for r in ROBOTS}
                for robot in ROBOTS:
                    candidates = [copy.deepcopy(_CANDIDATE_BY_SLOT[s]) for s in SLOTS]
                    chosen, _message, _sent = _ask_round(
                        record, channels, ask, robot, round_no, candidates,
                        inbox=inboxes[robot])
                    record['decisions'][robot] = chosen['slot']
                record['rounds'] = round_no
                slots = set(record['decisions'].values())
                # The channel conditions always conduct the claim round and at
                # least one answer round (so the manipulation is applied even
                # when both robots already agree); a third round is only used
                # while the two choices still collide.
                if round_no >= 2 and len(slots) == 2 and slots == set(SLOTS):
                    break
            record['distinct'] = (len(set(record['decisions'].values())) == 2
                                  and set(record['decisions'].values()) == set(SLOTS))
            if not record['distinct']:
                record['errors'].append('L1LITE_DUPLICATE_SLOT')
        else:  # leader_en
            # Report -> assign -> ack (Codex review 2026-10-20 §2): the
            # follower first reports its own status to the leader, so the
            # leader's assignment is made with the follower's private
            # constraint available on the channel, as in the other channel
            # conditions.  Whether the follower mentions it is the model's
            # choice; the protocol only guarantees the round exists.
            report = dict(id='report_status')
            _chosen, _report_message, report_sent = _ask_round(
                record, channels, ask, follower, 1, [report])
            if not report_sent:
                record['errors'].append('L1LITE_LEADER_REPORT_MISSING')
                raise L1LiteError('L1LITE_LEADER_REPORT_MISSING',
                                  detail=f'{follower}:round1',
                                  record=_finish(record, channels))
            take_left = dict(id='take_left', slots={leader: SLOT_LEFT,
                                                    follower: SLOT_RIGHT})
            take_right = dict(id='take_right', slots={leader: SLOT_RIGHT,
                                                      follower: SLOT_LEFT})
            leader_decision, message, sent = _ask_round(
                record, channels, ask, leader, 2, [take_left, take_right])
            if not sent:
                # Without the assignment message the follower has nothing to
                # acknowledge; this is a named fail-closed error, not a retry.
                record['errors'].append('L1LITE_LEADER_UNASSIGNED')
                raise L1LiteError('L1LITE_LEADER_UNASSIGNED',
                                  detail=f'{leader}:round2', record=_finish(record, channels))
            record['decisions'].update(leader_decision['slots'])
            ack = dict(id='ack_assignment')
            chosen, _ack_message, ack_sent = _ask_round(
                record, channels, ask, follower, 3, [ack])
            if chosen['id'] != 'ack_assignment' or not ack_sent:
                record['errors'].append('L1LITE_LEADER_ACK_MISSING')
                raise L1LiteError('L1LITE_LEADER_ACK_MISSING',
                                  detail=f'{follower}:round3',
                                  record=_finish(record, channels))
            record['rounds'] = 3
    except L1LiteError as exc:
        # Every fatal decision keeps its stable code in the record as well as in
        # the exception, so ``slot-decisions.json`` names the failure.  Rebuild
        # the attached record from the live one (the exception snapshot was
        # taken before the code was appended).
        if exc.code not in record['errors']:
            record['errors'].append(exc.code)
        record['fatal'] = True
        exc.record = _finish(record, channels)
        raise
    return _finish(record, channels)


def slot_records(record):
    """Compact admin row written to ``slot-decisions.json`` by the runner."""
    needed = ('schema', 'condition', 'seed', 'robots', 'leader', 'decisions',
              'constraints', 'errors', 'message_drops', 'rounds', 'utterances',
              'deadlock', 'fatal', 'distinct', 'constraint_ok',
              'success_eligible', 'slot_assignment', 'transcript', 'calls',
              'messages', 'constraint_table_sha256', 'order_sheet_version')
    return {key: copy.deepcopy(record.get(key)) for key in needed}


# ---------------------------------------------------------------------------
# Queue binding (admin only): the L1-lite markers pin the table and declare that
# the slot is a run-time LLM decision; no fixed ``nav_slots`` may be prepared.


def queue_fields(seed, robots=ROBOTS):
    """Queue markers written only by an explicit L1-lite ``--prepare``."""
    _check_seed(seed)
    if tuple(robots) != ROBOTS:
        raise L1LiteError('L1LITE_PAIR_ONLY', detail=','.join(str(r) for r in robots))
    return dict(nav_l1lite='on_v1',
                nav_l1lite_order_sheet=ORDER_SHEET_VERSION,
                nav_l1lite_constraints_sha256=constraint_table_digest(),
                nav_l1lite_slot_assignment='llm_decision',
                # test (main experiment) or dev (shared-component tournament);
                # the analysis never pools the two (PREREG_L1LITE §5).
                nav_l1lite_seed_split=seed_split(seed))


def validate_queue(queue, *, seed, condition, robots=ROBOTS):
    """Re-check the prepared L1-lite queue before any physics import."""
    from harness.e2ewarp_nav_gate import GATE_MODE_V230_R5, l1lite_enabled
    markers = {k: v for k, v in queue.items() if str(k).startswith('nav_l1lite')}
    enabled = l1lite_enabled()
    if not enabled:
        if markers:
            raise L1LiteError('L1LITE_ENV_REQUIRED')
        return queue
    if queue.get('nav_l1lite') != 'on_v1':
        raise L1LiteError('L1LITE_QUEUE_REQUIRED')
    if queue.get('nav_gate_mode') != GATE_MODE_V230_R5:
        raise L1LiteError('L1LITE_REQUIRES_V230_R5',
                          detail=str(queue.get('nav_gate_mode')))
    if queue.get('nav_l1lite_order_sheet') != ORDER_SHEET_VERSION:
        raise L1LiteError('L1LITE_ORDER_SHEET_MISMATCH')
    if queue.get('nav_l1lite_constraints_sha256') != constraint_table_digest():
        raise L1LiteError('L1LITE_CONSTRAINT_TABLE_MISMATCH')
    if queue.get('nav_l1lite_slot_assignment') != 'llm_decision':
        raise L1LiteError('L1LITE_SLOT_SOURCE_MISMATCH')
    if queue.get('nav_l1lite_seed_split') != seed_split(seed):
        raise L1LiteError('L1LITE_SEED_SPLIT_MISMATCH',
                          detail=str(queue.get('nav_l1lite_seed_split')))
    if queue.get('nav_slots') is not None:
        raise L1LiteError('L1LITE_SLOTS_RUNTIME_DECISION')
    if tuple(robots) != ROBOTS or tuple(queue.get('nav_robots') or ()) != ROBOTS:
        raise L1LiteError('L1LITE_PAIR_ONLY')
    if queue.get('seed') != seed:
        raise L1LiteError('L1LITE_SEED_MISMATCH')
    _check_seed(seed)
    if condition not in CONDITIONS or queue.get('condition') != condition:
        raise L1LiteError('L1LITE_CONDITION_MISMATCH', detail=str(condition))
    return queue
