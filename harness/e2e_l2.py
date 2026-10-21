"""L2 E2E: LLM role assignment -> learned pair-carry policy (default OFF).

Scope (aggressive-replan-1105.md §2 10/31-11/2 row, §6 L2 definition):

- order sheet ``v_l2``: ONE large beam (``long_beam``) to zone B, with no
  "single robot impossible" flag and no robot named.  Each robot's LLM must
  decide (a) whether a partner is needed and (b) which beam end it takes
  (``west`` or ``east``).
- information asymmetry: each robot's brief holds only its OWN observation
  (its own distance to the west and east grip bands).  The peer's distances
  are never written into a robot input; a robot may disclose its own numbers
  through the permitted channel (measured, not leaked).
- four channels, the L1-lite design (``dsh/l1lite-alloc``
  ``harness/e2ewarp_l1lite.py``) re-implemented here as a self-contained,
  in-memory protocol because that branch is not in this stack (no import, no
  shared code; [확인 필요] unify with ``e2e_warp_runtime.Channels`` after both
  branches meet): ``no_comm`` (0 messages), ``structured`` (fixed enum
  ``need_partner|claim_end|ack`` + end), ``peer_en`` (free English) and
  ``leader_en`` (leader = ``seed % 2`` assigns both ends, follower acks).
- the LLM decides; the code binds.  The decided ends are translated into the
  pair-carry role tokens (``teal``/``blue`` = the beam's grip bands at local
  x = -0.27 / +0.27, ``harness/grasp_act_contract.KIND_ROLES['long_beam']``)
  and written into ``case['plan']['roles']``, which is the only role input of
  both the P5 student worker reset (the "number tag" the student reads) and
  the P2 teacher.  Nothing else in the case changes.
- every missing, malformed, solo or duplicate decision fails closed with a
  stable code; such a seed is NOT executed and counts as a failure in N.

This module has no HTTP, no physics and no clock.  ``ask(robot, dynamic)`` is
the only model boundary, so unit tests stub the LLM.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
from collections.abc import Mapping

VERSION = 'ugrp.e2e_l2.v1'
ORDER_SHEET_VERSION = 'v_l2'
ENV = 'E2E_L2'
ENV_ON = 'on_v1'
ROBOTS = ('r1', 'r2')
CONDITIONS = ('no_comm', 'structured', 'peer_en', 'leader_en')
ENDS = ('west', 'east')
STRUCTURED_ACTS = ('need_partner', 'claim_end', 'ack')
#: Same protocol design values as L1-lite (not measured constants).
MAX_ROUNDS = 3
MAX_UTTERANCE_CHARS = 400
#: Grip-band offsets along the beam axis, verified in the teacher tree
#: (``scripts/make_grasp_act_plan.py`` ``ends={'teal':-.27,'blue':.27}``).
BAND_OFFSET_M = {'teal': -.27, 'blue': .27}
BAND_SPAN_M = BAND_OFFSET_M['blue'] - BAND_OFFSET_M['teal']
#: Pre-run case admissibility: the two bands must be separated by at least
#: half the span along world x, i.e. ``|cos(yaw)| >= 0.5`` (beam within 60 deg
#: of east-west).  Otherwise "west/east end" is not a meaningful name.  Design
#: value fixed before any run (prereg), applied to the case table only.
MIN_ABS_COS_YAW = .5
#: Own-distance resolution written into a brief (design value).
DISTANCE_DECIMALS = 2

ORDER_SHEET = dict(
    schema='ugrp.e2e_l2.order_sheet.v1',
    version=ORDER_SHEET_VERSION,
    scenario_id='l2_one_beam_to_zone_b',
    destination_zone='B',
    orders=[dict(order_id='B-beam', kind='transport', item='beam_1', object_kind='long_beam', count=1,
                 destination_zone='B', assigned_robot=None,
                 description='one long beam with a grip band near each end (west end and east end)')],
    note='no robot is named and no single-robot limit is stated',
)


class L2Error(ValueError):
    """A fail-closed L2 decision/channel error with a stable code."""

    def __init__(self, code, *, detail=None, record=None):
        self.code = str(code)
        self.detail = None if detail is None else str(detail)
        self.record = copy.deepcopy(record) if record is not None else None
        super().__init__(self.code + (':' + self.detail if self.detail else ''))


def enabled(environ=None):
    return (os.environ if environ is None else environ).get(ENV) == ENV_ON


def require_enabled(environ=None):
    if not enabled(environ):
        raise L2Error('L2_ENV_REQUIRED', detail=f'{ENV}={ENV_ON}')


def order_sheet():
    return copy.deepcopy(ORDER_SHEET)


def leader_for_seed(seed):
    _check_int(seed, 'L2_SEED_INVALID')
    return ROBOTS[seed % len(ROBOTS)]


def _check_int(value, code):
    if isinstance(value, bool) or not isinstance(value, int):
        raise L2Error(code, detail=repr(value))
    return value


# ---------------------------------------------------------------------------
# Geometry (admin side): band positions from the plan, east/west naming.


def _plan(case):
    plan = case.get('plan') if isinstance(case, Mapping) else None
    if not isinstance(plan, Mapping):
        raise L2Error('L2_CASE_INVALID', detail='plan missing')
    for key in ('beam_pose', 'spawns', 'roles', 'seed'):
        if key not in plan:
            raise L2Error('L2_CASE_INVALID', detail=f'plan.{key} missing')
    if tuple(sorted(plan['roles'])) != ROBOTS or sorted(plan['roles'].values()) != ['blue', 'teal']:
        raise L2Error('L2_CASE_INVALID', detail='pair long_beam roles r1/r2 teal/blue required')
    return plan


def band_positions(plan):
    x, y, yaw = (float(v) for v in plan['beam_pose'][:3])
    return {band: (x + d * math.cos(yaw), y + d * math.sin(yaw)) for band, d in BAND_OFFSET_M.items()}


def case_admissible(case):
    """(ok, reason). Pre-run static check only; never applied after outcomes."""
    plan = _plan(case)
    cos_yaw = abs(math.cos(float(plan['beam_pose'][2])))
    if cos_yaw < MIN_ABS_COS_YAW - 1e-12:
        return False, f'beam within {math.degrees(math.acos(MIN_ABS_COS_YAW)):.0f} deg of north-south (|cos|={cos_yaw:.3f})'
    return True, None


def end_to_band(plan):
    """``{'west': band, 'east': band}``; west = smaller world x (+x is east)."""
    ok, why = case_admissible({'plan': plan})
    if not ok:
        raise L2Error('L2_CASE_EAST_WEST_AMBIGUOUS', detail=why)
    pos = band_positions(plan)
    west = min(pos, key=lambda b: pos[b][0])
    return {'west': west, 'east': 'blue' if west == 'teal' else 'teal'}


def reference_ends(plan):
    """The ends the case generator sampled each start for (eval-only reference)."""
    band_end = {b: e for e, b in end_to_band(plan).items()}
    return {r: band_end[plan['roles'][r]] for r in ROBOTS}


def own_distances(plan, robot):
    pos = band_positions(plan)
    sx, sy = (float(v) for v in plan['spawns'][robot][:2])
    names = end_to_band(plan)
    return {end: round(math.dist((sx, sy), pos[names[end]]), DISTANCE_DECIMALS) for end in ENDS}


def nearer_end(distances):
    return 'west' if distances['west'] <= distances['east'] else 'east'


def geometry_record(case):
    """Admin/eval-only geometry summary (never a robot input)."""
    plan = _plan(case)
    dist = {r: own_distances(plan, r) for r in ROBOTS}
    near = {r: nearer_end(dist[r]) for r in ROBOTS}
    pairings = {('west', 'east'): dist['r1']['west'] + dist['r2']['east'],
                ('east', 'west'): dist['r1']['east'] + dist['r2']['west']}
    best = min(pairings, key=pairings.get)
    return dict(seed=plan['seed'], end_to_band=end_to_band(plan), reference_ends=reference_ends(plan),
                own_distances=dist, nearer_end=near, nearer_end_conflict=near['r1'] == near['r2'],
                min_total_distance_ends={'r1': best[0], 'r2': best[1]},
                min_total_distance_m=round(pairings[best], 3))


# ---------------------------------------------------------------------------
# Briefs (the ONLY place a robot's own observation is written).


def robot_brief(case, robot, condition):
    if condition not in CONDITIONS:
        raise L2Error('L2_CONDITION_UNKNOWN', detail=str(condition))
    if robot not in ROBOTS:
        raise L2Error('L2_ROBOT_UNKNOWN', detail=str(robot))
    plan = _plan(case)
    seed = _check_int(plan['seed'], 'L2_SEED_INVALID')
    peer = next(r for r in ROBOTS if r != robot)
    return dict(
        schema=VERSION, robot=robot, peer=peer, condition=condition,
        role=('leader' if condition == 'leader_en' and robot == leader_for_seed(seed) else 'worker'),
        order_sheet=order_sheet(),
        own_capability='one front gripper; one robot can hold one grip band of an object',
        # [대체] geometry from the plan, not the perception stack: the
        # perception -> brief link is not wired in this stack ([확인 필요]).
        own_observation=dict(source='plan_geometry_v1', band_span_m=round(BAND_SPAN_M, 2),
                             own_distance_m=own_distances(plan, robot)),
        default_rule=('if a partner is needed and you cannot agree, take the end nearer to you'),
    )


def brief_has_peer_data(brief, case):
    """True if any peer-only number leaked into this brief (boundary check)."""
    plan = _plan(case)
    peer = brief['peer']
    peer_values = set(own_distances(plan, peer).values()) - set(own_distances(plan, brief['robot']).values())
    text = json.dumps(brief, sort_keys=True)
    return peer in text and any(f'{v:.{DISTANCE_DECIMALS}f}' in text or repr(v) in text for v in peer_values)


# ---------------------------------------------------------------------------
# Channel (in-memory, same topology rules as L1-lite).


def has_hangul(text):
    return bool(re.search('[가-힣]', str(text or '')))


def message_problems(condition, sender, envelope):
    if condition not in CONDITIONS:
        return ['unknown condition']
    if condition == 'no_comm':
        return ['no_comm allows no messages at all']
    if not isinstance(envelope, Mapping) or set(envelope) != {'to', 'body'}:
        return ['message envelope must be exactly {"to": [...], "body": {...}}']
    to = envelope['to']
    if sender not in ROBOTS:
        return ['sender outside execution robot set']
    if not isinstance(to, (list, tuple)) or list(to) != [next(r for r in ROBOTS if r != sender)]:
        return ['recipient must be exactly the peer']
    body = envelope['body']
    if condition == 'structured':
        if not isinstance(body, Mapping) or set(body) != {'act', 'end'}:
            return ['structured message needs exactly act and end']
        if body['act'] not in STRUCTURED_ACTS:
            return [f'act must be one of {STRUCTURED_ACTS}']
        if body['end'] not in ENDS:
            return [f'end must be one of {ENDS}']
        return []
    if not isinstance(body, Mapping) or set(body) != {'text'}:
        return ['a free message body must be exactly {"text": "..."}']
    text = body['text']
    if not isinstance(text, str) or not text.strip():
        return ['free message body needs non-empty text']
    if len(text) > MAX_UTTERANCE_CHARS:
        return [f'free message body exceeds {MAX_UTTERANCE_CHARS} characters']
    return []


class Channel:
    def __init__(self, condition):
        self.condition = condition
        self.events = []

    def send(self, sender, envelope, round_no):
        problems = message_problems(self.condition, sender, envelope)
        if problems:
            raise L2Error('L2_MESSAGE_INVALID', detail='; '.join(problems))
        self.events.append(dict(sender=sender, to=list(envelope['to']), body=copy.deepcopy(envelope['body']),
                                round=round_no,
                                language_slip=(self.condition in ('peer_en', 'leader_en')
                                               and has_hangul(envelope['body'].get('text')))))

    def inbox(self, robot):
        return dict(inbox=[dict(sender=e['sender'], body=copy.deepcopy(e['body']), round=e['round'])
                           for e in self.events if robot in e['to']])


# ---------------------------------------------------------------------------
# Allocation protocol.

_ANSWER_KEYS = {'need_partner', 'act', 'message'}
_SOLO = dict(id='solo_carry', end=None)
_END_CANDIDATES = [dict(id='end_' + e, end=e) for e in ENDS]


def _record_skeleton(condition, case):
    plan = _plan(case)
    return dict(schema=VERSION, condition=condition, seed=plan['seed'], robots=list(ROBOTS),
                leader=leader_for_seed(plan['seed']), order_sheet_version=ORDER_SHEET_VERSION,
                transcript=[], calls=[], messages=[], errors=[], message_drops=[], usage=[],
                need_partner={}, decisions={}, rounds=0, utterances=0, fatal=False,
                distinct=None, cooperate_ok=None, success_eligible=False,
                role_assignment='llm_decision')


def _finish(record, channel):
    record['messages'] = copy.deepcopy(channel.events)
    record['utterances'] = len(channel.events)
    ends = record['decisions']
    record['distinct'] = set(ends) == set(ROBOTS) and set(ends.values()) == set(ENDS)
    record['cooperate_ok'] = (set(record['need_partner']) == set(ROBOTS)
                              and all(record['need_partner'].values()))
    record['success_eligible'] = bool(record['distinct'] and record['cooperate_ok']
                                      and not record['errors'] and not record['fatal'])
    return record


def _validate_answer(answer, candidates, robot, round_no):
    tag = f'{robot}:round{round_no}'
    if not isinstance(answer, Mapping):
        raise L2Error('L2_INVALID_DECISION', detail=tag + ':not_a_mapping')
    keys = set(answer) - {'usage'}
    if keys != _ANSWER_KEYS:
        raise L2Error('L2_INVALID_DECISION', detail=tag + ':keys')
    if type(answer['need_partner']) is not bool:
        raise L2Error('L2_INVALID_DECISION', detail=tag + ':need_partner_not_bool')
    ids = {c['id'] for c in candidates}
    if answer['act'] not in ids:
        raise L2Error('L2_INVALID_END', detail=f'{tag}:{answer["act"]!r}')
    if (answer['act'] == 'solo_carry') == answer['need_partner']:
        raise L2Error('L2_INVALID_DECISION', detail=tag + ':need_partner_act_mismatch')
    return answer


def _ask(record, channel, ask, robot, round_no, candidates, *, inbox, send):
    dynamic = dict(round=round_no, candidates=copy.deepcopy(candidates), **inbox)
    answer = ask(robot, dynamic)
    answer = _validate_answer(answer, candidates, robot, round_no)
    if isinstance(answer.get('usage'), Mapping):
        record['usage'].append(dict(robot=robot, round=round_no, **{
            k: int(answer['usage'].get(k, 0)) for k in ('prompt_tokens', 'completion_tokens')}))
    chosen = next(c for c in candidates if c['id'] == answer['act'])
    message, sent, dropped = answer['message'], False, None
    if message is not None and send:
        try:
            channel.send(robot, message, round_no)
            sent = True
        except L2Error as exc:
            dropped = exc.detail
            record['message_drops'].append(dict(robot=robot, round=round_no, reason=dropped))
            record['errors'].append('L2_MESSAGE_INVALID')
    elif message is not None:
        dropped = 'L2_MESSAGE_NOT_ALLOWED'
        record['message_drops'].append(dict(robot=robot, round=round_no, reason=dropped))
    record['transcript'].append(dict(robot=robot, round=round_no, act=answer['act'],
                                     need_partner=answer['need_partner'], end=chosen.get('end'),
                                     message=(message.get('body') if isinstance(message, Mapping) else None),
                                     message_sent=sent, message_dropped=dropped,
                                     inbox_n=len(inbox.get('inbox') or ())))
    record['calls'].append(dict(robot=robot, round=round_no, act=answer['act'], message_sent=sent))
    record['need_partner'][robot] = answer['need_partner']
    if answer['act'] == 'solo_carry':
        raise L2Error('L2_SOLO_DECISION', detail=f'{robot}:round{round_no}')
    return chosen, sent


def allocate_ends(condition, case, *, ask, max_rounds=MAX_ROUNDS):
    """Run the pre-drive LLM stage; return an admin/eval-only record.

    ``ask(robot, dynamic) -> {'need_partner': bool, 'act': candidate_id,
    'message': envelope_or_None[, 'usage': {...}]}``.  Raises :class:`L2Error`
    (record attached, ``fatal=True``) for any decision that cannot be executed.
    A duplicate end after the last round is a non-fatal named error: the record
    keeps both decisions but ``success_eligible`` is False and the seed is not
    executed (``build_l2_case`` refuses it).
    """
    if condition not in CONDITIONS:
        raise L2Error('L2_CONDITION_UNKNOWN', detail=str(condition))
    if not callable(ask):
        raise L2Error('L2_ASK_REQUIRED')
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds < 1:
        raise L2Error('L2_MAX_ROUNDS_INVALID', detail=str(max_rounds))
    channel = Channel(condition)
    record = _record_skeleton(condition, case)
    leader = record['leader']
    follower = next(r for r in ROBOTS if r != leader)
    full = [copy.deepcopy(_SOLO)] + copy.deepcopy(_END_CANDIDATES)
    try:
        if condition == 'no_comm':
            for robot in ROBOTS:
                chosen, _ = _ask(record, channel, ask, robot, 1, full, inbox=dict(inbox=[]), send=False)
                record['decisions'][robot] = chosen['end']
            record['rounds'] = 1
        elif condition in ('structured', 'peer_en'):
            for round_no in range(1, max_rounds + 1):
                inboxes = {r: channel.inbox(r) for r in ROBOTS}   # same-round sends cannot leak in
                for robot in ROBOTS:
                    chosen, _ = _ask(record, channel, ask, robot, round_no, full, inbox=inboxes[robot], send=True)
                    record['decisions'][robot] = chosen['end']
                record['rounds'] = round_no
                if round_no >= 2 and set(record['decisions'].values()) == set(ENDS):
                    break
        else:  # leader_en
            options = [copy.deepcopy(_SOLO),
                       dict(id='leader_west', ends={leader: 'west', follower: 'east'}),
                       dict(id='leader_east', ends={leader: 'east', follower: 'west'})]
            chosen, sent = _ask(record, channel, ask, leader, 1, options, inbox=dict(inbox=[]), send=True)
            if not sent:
                record['errors'].append('L2_LEADER_UNASSIGNED')
                raise L2Error('L2_LEADER_UNASSIGNED', detail=f'{leader}:round1')
            record['decisions'].update(chosen['ends'])
            ack = [copy.deepcopy(_SOLO), dict(id='ack_assignment', end=chosen['ends'][follower])]
            chosen2, ack_sent = _ask(record, channel, ask, follower, 2, ack, inbox=channel.inbox(follower), send=True)
            if not ack_sent:
                record['errors'].append('L2_LEADER_ACK_MISSING')
                raise L2Error('L2_LEADER_ACK_MISSING', detail=f'{follower}:round2')
            record['rounds'] = 2
        if set(record['decisions'].values()) != set(ENDS):
            record['errors'].append('L2_DUPLICATE_END')
    except L2Error as exc:
        if exc.code not in record['errors']:
            record['errors'].append(exc.code)
        record['fatal'] = True
        exc.record = _finish(record, channel)
        raise
    return _finish(record, channel)


def run_stage(condition, case, *, ask, max_rounds=MAX_ROUNDS):
    """``allocate_ends`` that never raises: fatal errors come back as the record."""
    try:
        return allocate_ends(condition, case, ask=ask, max_rounds=max_rounds)
    except L2Error as exc:
        if exc.record is None:
            raise
        return exc.record


# ---------------------------------------------------------------------------
# Binding to the execution stage.

ARMS = ('student', 'teacher_fallback')
ARM_LABEL = {'student': 'learned pair-carry ACT (P5 --student-eval)',
             'teacher_fallback': '[대체 단계] P2 GT teacher, NOT a learned result'}


def build_l2_case(case, record, *, arm):
    """Case for ``run_warp_flow_teacher.py`` with the LLM-decided roles.

    Only ``plan['roles']`` changes (the student's role token / teacher end);
    the admin block ``l2_admin`` is ignored by the runner.  Refuses any record
    that is not ``success_eligible`` (fail-closed: not executed, counts as
    failure).
    """
    if arm not in ARMS:
        raise L2Error('L2_ARM_UNKNOWN', detail=str(arm))
    if not record.get('success_eligible'):
        raise L2Error('L2_NOT_EXECUTABLE', detail=','.join(record.get('errors') or ['not_eligible']))
    plan = _plan(case)
    if record.get('seed') != plan['seed']:
        raise L2Error('L2_SEED_MISMATCH', detail=f'{record.get("seed")}!={plan["seed"]}')
    names = end_to_band(plan)
    out = copy.deepcopy(case)
    out['plan']['roles'] = {r: names[record['decisions'][r]] for r in ROBOTS}
    out['l2_admin'] = dict(schema=VERSION, arm=arm, arm_label=ARM_LABEL[arm], condition=record['condition'],
                           decided_ends=dict(record['decisions']),
                           original_roles=dict(plan['roles']),
                           record_sha256=record_sha256(record))
    return out


def record_sha256(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Model boundary adapters.


def planner_ask(planner, frames, briefs):
    """Wrap an L1-lite style ``Planner.decide(frame, dynamic)`` object.

    TODO([확인 필요]): the ``Planner`` class lives in ``dsh/l1lite-alloc``
    ``scripts/run_e2e_warp.py`` (relay URL, pinned planner model) and is not in
    this stack.  Its reply format for an L2 brief is unverified, so this adapter
    is intentionally not implemented; wire it once the branches meet and add a
    recorded-reply test.
    """
    raise NotImplementedError('L2 live planner binding is not wired in this stack (TODO, see docstring)')


def price_table(path='configs/model_endpoints.json'):
    """Planner USD per 1M tokens from the pinned endpoint file."""
    data = json.loads(open(path, encoding='utf-8').read())
    row = next(e for e in data['endpoints'] if e.get('role') == 'planner')
    return dict(row['baseline_usd_per_million'], model=row['model'], provider=row['provider'])
