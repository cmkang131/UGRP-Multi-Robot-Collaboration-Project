"""L2 E2E: LLM role assignment -> learned pair-carry policy (default OFF).

Scope (aggressive-replan-1105.md §2 10/31-11/2 row, §6 L2 definition):

- order sheet ``v_l2``: ONE long beam to zone B, with no "single robot
  impossible" flag and no robot named.  Each robot's LLM decides (a) whether
  a partner is needed (``solo_carry`` vs an end) and (b) which beam end it
  takes.
- robot input = order sheet + the robot's OWN camera first frame (one JPEG)
  + the condition channel's inbox.  No plan coordinate, distance, pose or
  peer value is written into any LLM input (owner review 2026-10-21 item 2);
  the plan geometry is used only by the evaluator (``e2e_l2_eval``).
- end vocabulary: the beam's two grip bands are coloured; the LLM names the
  end by colour (``end_teal`` / ``end_blue``).  The colour is visible in the
  image and is exactly the pair-carry role token
  (``harness/grasp_act_contract.KIND_ROLES['long_beam'] == ('teal', 'blue')``),
  so binding the decision to ``case['plan']['roles']`` needs no geometry.
  West/east is an eval-only label.  (East/west as an LLM choice would need the
  robot's own heading, i.e. a plan pose, which is the leak removed above.)
- four channels and the model boundary are the L1-lite implementation from
  ``dsh/l1lite-alloc`` (``harness/e2e_warp_runtime.py`` ``Channels`` and
  ``Planner``, ``harness/e2ewarp_l1lite.py`` validators/prices), vendored
  byte-identical (``tests/test_e2e_l2.py`` pins the blobs).  The only L2
  addition is the structured body enum ``need_partner|claim_end|ack`` + end
  (``L2Channels``); free English uses the unchanged L1-lite validator.
- every missing, malformed, solo or duplicate decision fails closed with a
  stable code; such a seed is NOT executed and counts as a failure in N.

No HTTP or physics lives here: ``ask(robot, dynamic)`` is the only model
boundary (``planner_ask`` binds it to the L1-lite ``Planner``).
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from collections.abc import Mapping
from pathlib import Path

from harness import e2ewarp_l1lite as l1lite
from harness.e2e_warp_runtime import Channels, OwnFrame, Planner
from harness.zone_study_contract import ContractViolation

VERSION = 'ugrp.e2e_l2.v2'
ORDER_SHEET_VERSION = 'v_l2'
ENV = 'E2E_L2'
ENV_ON = 'on_v1'
ROBOTS = ('r1', 'r2')
CONDITIONS = ('no_comm', 'structured', 'peer_en', 'leader_en')
END_TOKENS = ('teal', 'blue')            # LLM vocabulary == student role tokens
EW = ('west', 'east')                    # eval-only labels
STRUCTURED_ACTS = ('need_partner', 'claim_end', 'ack')
MAX_ROUNDS = l1lite.MAX_ROUNDS
#: L1-lite source this stack vendors (byte-identical files, pinned in tests).
L1LITE_SOURCE = dict(branch='dsh/l1lite-alloc', sha='955c967d838a83bd6a3d0d33c05ae6be33303c3b',
                     blobs={'harness/e2e_warp_runtime.py': '1885466e41f9d7b409ec94f267548943c577ea92',
                            'harness/e2ewarp_l1lite.py': 'fb77997570edc260635681bda201d1fafd9b552b',
                            'harness/e2ewarp_selfnav.py': '96f03d4ebb167213a6dc1e6cf4682b2d18cdc2b3'})
#: Pinned planner (L1-lite live guard, ``scripts/run_e2e_warp.py`` on
#: ``dsh/l1lite-alloc``: relay ``/identity`` upstream must match).
PLANNER_PIN = dict(model='google/gemma-4-31b-it', provider='CoreWeave', quantization='fp4', allow_fallbacks=False)
PRICE_USD_PER_MILLION = dict(l1lite.PLANNER_PRICE_USD_PER_MILLION)
#: Env names that must not exist on the run host (same list as the L1-lite
#: live guard): the API key stays in the off-VM relay, never in code or logs.
CREDENTIAL_ENV_MARKERS = ('OPENROUTER_API', 'OPENAI_API', 'KAGGLE_KEY', 'GOOGLE_APPLICATION_CREDENTIALS')
#: Pre-run case admissibility (kept from the first draft, owner item 4):
#: ``|cos(yaw)| >= 0.5`` so the eval-only west/east label is meaningful.
MIN_ABS_COS_YAW = .5
BAND_OFFSET_M = {'teal': -.27, 'blue': .27}   # teacher tree make_grasp_act_plan.py

ORDER_SHEET = dict(
    schema='ugrp.e2e_l2.order_sheet.v2',
    version=ORDER_SHEET_VERSION,
    scenario_id='l2_one_beam_to_zone_b',
    destination_zone='B',
    orders=[dict(order_id='B-beam', kind='transport', item='beam_1', object_kind='long_beam', count=1,
                 destination_zone='B', assigned_robot=None,
                 description='one long beam; a teal grip band near one end and a blue grip band near the other end')],
    note='no robot is named and no single-robot limit is stated',
)

CANDIDATES = [dict(id='solo_carry', meaning='carry the whole beam alone, no partner'),
              dict(id='end_teal', meaning='a partner is needed; I hold the teal-band end'),
              dict(id='end_blue', meaning='a partner is needed; I hold the blue-band end')]


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
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise L2Error('L2_SEED_INVALID', detail=repr(seed))
    return ROBOTS[seed % len(ROBOTS)]


# ---------------------------------------------------------------------------
# Case checks and eval-only geometry (never written into an LLM input).


def plan_of(case):
    plan = case.get('plan') if isinstance(case, Mapping) else None
    if not isinstance(plan, Mapping):
        raise L2Error('L2_CASE_INVALID', detail='plan missing')
    for key in ('beam_pose', 'spawns', 'roles', 'seed'):
        if key not in plan:
            raise L2Error('L2_CASE_INVALID', detail=f'plan.{key} missing')
    if tuple(sorted(plan['roles'])) != ROBOTS or sorted(plan['roles'].values()) != sorted(END_TOKENS):
        raise L2Error('L2_CASE_INVALID', detail='pair long_beam roles r1/r2 teal/blue required')
    return plan


def case_admissible(case):
    """(ok, reason). Pre-run static N-S exclusion; never applied after outcomes."""
    plan = plan_of(case)
    cos_yaw = abs(math.cos(float(plan['beam_pose'][2])))
    if cos_yaw < MIN_ABS_COS_YAW - 1e-12:
        return False, f'beam within 60 deg of north-south (|cos yaw|={cos_yaw:.3f})'
    return True, None


def band_positions(plan):
    x, y, yaw = (float(v) for v in plan['beam_pose'][:3])
    return {b: (x + d * math.cos(yaw), y + d * math.sin(yaw)) for b, d in BAND_OFFSET_M.items()}


def geometry_record(case):
    """EVAL-ONLY: generator ends, own distances, west/east labels."""
    plan = plan_of(case)
    pos = band_positions(plan)
    dist = {r: {b: round(math.dist(plan['spawns'][r][:2], pos[b]), 3) for b in END_TOKENS} for r in ROBOTS}
    nearer = {r: min(END_TOKENS, key=lambda b: (dist[r][b], b)) for r in ROBOTS}
    pair = {('teal', 'blue'): dist['r1']['teal'] + dist['r2']['blue'],
            ('blue', 'teal'): dist['r1']['blue'] + dist['r2']['teal']}
    best = min(pair, key=pair.get)
    west = min(END_TOKENS, key=lambda b: pos[b][0])
    ok, _ = case_admissible(case)
    return dict(seed=plan['seed'], reference_ends=dict(plan['roles']), own_distances_m=dist, nearer_end=nearer,
                nearer_end_conflict=nearer['r1'] == nearer['r2'],
                min_total_distance_ends={'r1': best[0], 'r2': best[1]},
                band_label=({west: 'west', ('blue' if west == 'teal' else 'teal'): 'east'} if ok else None))


# ---------------------------------------------------------------------------
# Brief (Planner static) and dynamic.


def robot_brief(case, robot, condition):
    """The Planner ``static`` text for this robot: order sheet + rules only."""
    if condition not in CONDITIONS:
        raise L2Error('L2_CONDITION_UNKNOWN', detail=str(condition))
    if robot not in ROBOTS:
        raise L2Error('L2_ROBOT_UNKNOWN', detail=str(robot))
    plan = plan_of(case)
    peer = next(r for r in ROBOTS if r != robot)
    return dict(
        schema=VERSION, robot=robot, peer=peer, condition=condition,
        role=('leader' if condition == 'leader_en' and robot == leader_for_seed(plan['seed']) else 'worker'),
        order_sheet=order_sheet(),
        own_capability='one front gripper; one robot can hold one grip band of an object',
        own_input='the attached image is your own camera first frame at the start position',
        task=('decide whether this order needs a partner; if so, choose which grip band you hold. '
              'Your peer decides independently; two robots must not choose the same band.'),
        default_rule='if a partner is needed and you cannot agree, take the band that looks nearer in your image',
        channel=_channel_rule(condition),
    )


def _channel_rule(condition):
    return {'no_comm': 'no messages; message must be null',
            'structured': ('message body exactly {"act": one of need_partner|claim_end|ack, '
                           '"end": teal|blue}'),
            'peer_en': 'message body exactly {"text": English, <= 400 chars}',
            'leader_en': ('leader: choose leader_teal or leader_blue and send the assignment as '
                          '{"text": English}; follower: choose ack_assignment and reply {"text": English}')}[condition]


FORBIDDEN_INPUT_KEYS = ('beam_pose', 'spawns', 'pose', 'distance', 'own_distance', 'roles', 'reference', 'xy')


def input_leaks(value):
    """Names of plan/geometry keys present anywhere in an LLM input (boundary test)."""
    found = []

    def walk(v):
        if isinstance(v, Mapping):
            for k, x in v.items():
                if any(f in str(k).lower() for f in FORBIDDEN_INPUT_KEYS):
                    found.append(str(k))
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
    walk(value)
    return found


# ---------------------------------------------------------------------------
# Channel: the L1-lite ``Channels`` with one L2 structured enum.


def structured_problems(body):
    if not isinstance(body, Mapping) or set(body) != {'act', 'end'}:
        return ['structured message needs exactly act and end']
    if body['act'] not in STRUCTURED_ACTS:
        return [f'act must be one of {STRUCTURED_ACTS}']
    if body['end'] not in END_TOKENS:
        return [f'end must be one of {END_TOKENS}']
    return []


class L2Channels(Channels):
    """L1-lite ``Channels`` (topology, inbox, leader rotation, free English).

    Only the ``structured`` body differs: the L2 enum replaces the L1-lite
    slot enum.  Envelope/topology use the L1-lite checks unchanged.
    """

    def __init__(self, condition, seed):
        super().__init__(condition, seed, robots=ROBOTS, message_schema='l1lite')

    def validate(self, sender, message):
        if message is None or self.condition != 'structured':
            return super().validate(sender, message)
        if not isinstance(message, dict) or set(message) != {'recipients', 'body'}:
            raise ValueError('invalid message envelope')
        problems = l1lite._envelope_problems(sender, message['recipients']) or structured_problems(message['body'])
        if problems:
            raise ContractViolation('; '.join(problems))


# ---------------------------------------------------------------------------
# Allocation protocol.


def _record_skeleton(condition, case):
    plan = plan_of(case)
    return dict(schema=VERSION, condition=condition, seed=plan['seed'], robots=list(ROBOTS),
                leader=leader_for_seed(plan['seed']), order_sheet_version=ORDER_SHEET_VERSION,
                transcript=[], calls=[], messages=[], errors=[], message_drops=[], usage=[],
                need_partner={}, decisions={}, rounds=0, utterances=0, fatal=False,
                distinct=None, cooperate_ok=None, success_eligible=False, role_assignment='llm_decision',
                llm_input='order_sheet + own camera first frame + condition inbox')


def _finish(record, channels):
    record['messages'] = [dict(m, language_slip=l1lite.message_language_slip(channels.condition, m['body']))
                          for m in copy.deepcopy(channels.events)]
    record['utterances'] = len(channels.events)
    ends = record['decisions']
    record['distinct'] = set(ends) == set(ROBOTS) and set(ends.values()) == set(END_TOKENS)
    record['cooperate_ok'] = set(record['need_partner']) == set(ROBOTS) and all(record['need_partner'].values())
    record['success_eligible'] = bool(record['distinct'] and record['cooperate_ok']
                                      and not record['errors'] and not record['fatal'])
    return record


def _validate_answer(answer, candidates, robot, round_no):
    tag = f'{robot}:round{round_no}'
    if not isinstance(answer, Mapping) or set(answer) - {'usage'} != {'act', 'message'}:
        raise L2Error('L2_INVALID_DECISION', detail=tag + ':keys')
    if answer['act'] not in {c['id'] for c in candidates}:
        raise L2Error('L2_INVALID_END', detail=f'{tag}:{answer["act"]!r}')
    return answer


def _ask(record, channels, ask, robot, round_no, candidates, *, inbox, send):
    dynamic = dict(round=round_no, candidates=copy.deepcopy(candidates), **inbox)
    answer = _validate_answer(ask(robot, dynamic), candidates, robot, round_no)
    if isinstance(answer.get('usage'), Mapping):
        record['usage'].append(dict(robot=robot, round=round_no, **{
            k: int(answer['usage'].get(k) or 0) for k in ('prompt_tokens', 'completion_tokens')}))
    chosen = next(c for c in candidates if c['id'] == answer['act'])
    message, sent, dropped = answer['message'], False, None
    if message is not None and send:
        try:
            channels.send(robot, message, now=0.0)
            sent = True
        except (ValueError, TypeError) as exc:
            dropped = str(exc)
            record['message_drops'].append(dict(robot=robot, round=round_no, reason=dropped))
            record['errors'].append('L2_MESSAGE_INVALID')
    elif message is not None:
        dropped = 'L2_MESSAGE_NOT_ALLOWED'
        record['message_drops'].append(dict(robot=robot, round=round_no, reason=dropped))
    need = answer['act'] != 'solo_carry'
    record['transcript'].append(dict(robot=robot, round=round_no, act=answer['act'], need_partner=need,
                                     end=chosen.get('end'),
                                     message=(message.get('body') if isinstance(message, Mapping) else None),
                                     message_sent=sent, message_dropped=dropped,
                                     inbox_n=len(inbox.get('inbox') or ())))
    record['calls'].append(dict(robot=robot, round=round_no, act=answer['act'], message_sent=sent))
    record['need_partner'][robot] = need
    if not need:
        raise L2Error('L2_SOLO_DECISION', detail=f'{robot}:round{round_no}')
    return chosen, sent


def _end_candidates():
    return [dict(c, end=(None if c['id'] == 'solo_carry' else c['id'][4:])) for c in copy.deepcopy(CANDIDATES)]


def allocate_ends(condition, case, *, ask, max_rounds=MAX_ROUNDS):
    """Run the pre-drive LLM stage; return an admin/eval-only record.

    ``ask(robot, dynamic) -> {'act': candidate_id, 'message': envelope_or_None
    [, 'usage': {...}]}`` (the L1-lite ``Planner`` reply contract).  Raises
    :class:`L2Error` (record attached, ``fatal=True``) for a decision that
    cannot be executed.  A duplicate end after the last round is a non-fatal
    named error; the seed is still not executed (``build_l2_case`` refuses it).
    """
    if condition not in CONDITIONS:
        raise L2Error('L2_CONDITION_UNKNOWN', detail=str(condition))
    if not callable(ask):
        raise L2Error('L2_ASK_REQUIRED')
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds < 1:
        raise L2Error('L2_MAX_ROUNDS_INVALID', detail=str(max_rounds))
    record = _record_skeleton(condition, case)
    channels = L2Channels(condition, record['seed'])
    leader = record['leader']
    follower = next(r for r in ROBOTS if r != leader)
    try:
        if condition == 'no_comm':
            for robot in ROBOTS:
                chosen, _ = _ask(record, channels, ask, robot, 1, _end_candidates(),
                                 inbox=channels.inbox(robot), send=False)
                record['decisions'][robot] = chosen['end']
            record['rounds'] = 1
        elif condition in ('structured', 'peer_en'):
            for round_no in range(1, max_rounds + 1):
                inboxes = {r: channels.inbox(r) for r in ROBOTS}   # same-round sends cannot leak in
                for robot in ROBOTS:
                    chosen, _ = _ask(record, channels, ask, robot, round_no, _end_candidates(),
                                     inbox=inboxes[robot], send=True)
                    record['decisions'][robot] = chosen['end']
                record['rounds'] = round_no
                if round_no >= 2 and set(record['decisions'].values()) == set(END_TOKENS):
                    break
        else:  # leader_en
            options = [_end_candidates()[0]] + [
                dict(id='leader_' + e, meaning=f'a partner is needed; I (leader) hold {e}, the follower holds the other',
                     ends={leader: e, follower: next(x for x in END_TOKENS if x != e)}) for e in END_TOKENS]
            chosen, sent = _ask(record, channels, ask, leader, 1, options, inbox=channels.inbox(leader), send=True)
            if not sent:
                record['errors'].append('L2_LEADER_UNASSIGNED')
                raise L2Error('L2_LEADER_UNASSIGNED', detail=f'{leader}:round1')
            record['decisions'].update(chosen['ends'])
            ack = [_end_candidates()[0], dict(id='ack_assignment', meaning='accept the leader assignment',
                                              end=chosen['ends'][follower])]
            _, ack_sent = _ask(record, channels, ask, follower, 2, ack, inbox=channels.inbox(follower), send=True)
            if not ack_sent:
                record['errors'].append('L2_LEADER_ACK_MISSING')
                raise L2Error('L2_LEADER_ACK_MISSING', detail=f'{follower}:round2')
            record['rounds'] = 2
        if set(record['decisions'].values()) != set(END_TOKENS):
            record['errors'].append('L2_DUPLICATE_END')
    except L2Error as exc:
        if exc.code not in record['errors']:
            record['errors'].append(exc.code)
        record['fatal'] = True
        exc.record = _finish(record, channels)
        raise
    return _finish(record, channels)


def run_stage(condition, case, *, ask, max_rounds=MAX_ROUNDS):
    """``allocate_ends`` that never raises a decision error (returns the record)."""
    try:
        return allocate_ends(condition, case, ask=ask, max_rounds=max_rounds)
    except L2Error as exc:
        if exc.record is None:
            raise
        return exc.record


# ---------------------------------------------------------------------------
# Binding to the execution stage (no geometry: the decision IS the role token).

ARMS = ('student', 'teacher_fallback')
ARM_LABEL = {'student': 'learned pair-carry ACT (P5 --student-eval)',
             'teacher_fallback': '[대체 단계] P2 GT teacher, NOT a learned result'}


def record_sha256(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


def build_l2_case(case, record, *, arm):
    """Runner case with ``plan['roles']`` = the LLM decision; nothing else changes."""
    if arm not in ARMS:
        raise L2Error('L2_ARM_UNKNOWN', detail=str(arm))
    if not record.get('success_eligible'):
        raise L2Error('L2_NOT_EXECUTABLE', detail=','.join(record.get('errors') or ['not_eligible']))
    plan = plan_of(case)
    if record.get('seed') != plan['seed']:
        raise L2Error('L2_SEED_MISMATCH', detail=f'{record.get("seed")}!={plan["seed"]}')
    out = copy.deepcopy(case)
    out['plan']['roles'] = {r: record['decisions'][r] for r in ROBOTS}
    out['l2_admin'] = dict(schema=VERSION, arm=arm, arm_label=ARM_LABEL[arm], condition=record['condition'],
                           decided_ends=dict(record['decisions']), original_roles=dict(plan['roles']),
                           record_sha256=record_sha256(record))
    return out


# ---------------------------------------------------------------------------
# Live model boundary: L1-lite Planner (relay holds the key; CoreWeave fp4).


def credential_env(environ=None):
    env = os.environ if environ is None else environ
    return sorted(k for k in env if any(m in k.upper() for m in CREDENTIAL_ENV_MARKERS))


def check_relay(relay_url, *, identity_open=None, environ=None):
    """L1-lite live guard subset: loopback relay, pinned upstream, credit, no key env."""
    bad = credential_env(environ)
    if bad:
        raise L2Error('L2_VM_CREDENTIAL_ENV_FORBIDDEN', detail=','.join(bad))
    if not str(relay_url).startswith('http://127.0.0.1:') or not str(relay_url).endswith('/v1/chat/completions'):
        raise L2Error('L2_SSH_LOOPBACK_RELAY_ONLY')
    if identity_open is None:
        from urllib.request import urlopen

        def identity_open(url):
            with urlopen(url, timeout=30) as response:
                return json.load(response)
    relay = identity_open(relay_url.replace('/v1/chat/completions', '/identity'))
    pin = relay.get('upstream') or {}
    if any(pin.get(k) != v for k, v in PLANNER_PIN.items()) or relay.get('alerts') or relay.get('balance_usd', 0) <= 0:
        raise L2Error('L2_PINNED_RELAY_ENDPOINT_CREDIT_REQUIRED',
                      detail=json.dumps({k: pin.get(k) for k in PLANNER_PIN}, sort_keys=True))
    return dict(upstream={k: pin.get(k) for k in PLANNER_PIN}, alerts=relay.get('alerts'))


def make_planners(relay_url, root, case, condition, *, run_id, world_id, http_open=None):
    """One L1-lite ``Planner`` per robot; requests/responses archived under root/<robot>."""
    return {r: Planner(relay_url, Path(root) / r, robot_brief(case, r, condition), run_id=run_id,
                       world_id=world_id, robot=r, http_open=http_open) for r in ROBOTS}


def first_frames(jpegs, world_id):
    """``{robot: OwnFrame}`` from each robot's own first-frame JPEG bytes."""
    if set(jpegs) != set(ROBOTS):
        raise L2Error('L2_FRAMES_MISSING', detail=','.join(sorted(set(ROBOTS) - set(jpegs))))
    return {r: OwnFrame(robot_id=r, world_id=world_id, tick=0, sim_s=0.0, jpeg=jpegs[r], issued=())
            for r in ROBOTS}


def planner_ask(planners, frames):
    """``ask`` bound to the L1-lite ``Planner.decide(own frame, dynamic)``.

    A rejected/failed call (HTTP error, wrong provider, bad JSON, unknown
    candidate) is ``L2_NO_DECISION`` with the Planner's rejection reason; it is
    never retried here (prereg: no LLM retry).  HOST_ERROR RuntimeErrors from
    the Planner propagate unchanged.
    """
    def ask(robot, dynamic):
        planner = planners[robot]
        result, rejection = planner.decide(frames[robot], dynamic)
        if result is None:
            raise L2Error('L2_NO_DECISION', detail=f'{robot}:round{dynamic["round"]}:{rejection["reason"]}')
        return dict(result, usage=dict(planner.rows[-1].get('usage') or {}))
    return ask


def planner_ledger(planners):
    """Per-call rows (status, image sha256, usage) for cost and the archive index."""
    return {r: copy.deepcopy(p.rows) for r, p in planners.items()}
