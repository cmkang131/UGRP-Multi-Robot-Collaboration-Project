"""Egocentric memory projection for judgment-LLM requests (default OFF).

Toggle
------
``UGRP_PLANNER_EGOCENTRIC_MEMORY=planner_egocentric_memory_v1`` (environment).
Anything else, including unset, is OFF and leaves the request object untouched
(identity, not a copy).  The toggle is deliberately default-off: current-stack
decisions keep static-map flows until a caller turns this on for a diagnostic.

What the ON path does
---------------------
* removes every static-map block (coordinate frame, bounds, walls, passages,
  zones, door layout, pickup slots, map ids/hashes) and every map figure image;
* removes the robot's world/own-frame pose blocks and the observation-time world
  coordinates that duplicate them;
* adds ``egocentric_memory``: per remembered observation a kind/subject/state,
  approximate distance and bearing in the CURRENT own body frame (robot at the
  origin facing forward; 0 deg = forward, + = left), an uncertainty block from
  the observation's pose covariance, and the age since the last observation;
* rewrites the system prompt so it no longer advertises a static map and states
  that memory is approximate, shifts opposite to own motion, and must be
  re-observed;
* orders the user JSON as fixed (task/order sheet/rules/format) then variable
  (time, self state, memory, received messages, candidates, evidence), with the
  own RGB image last.  The caller supplies the system message first.

The projection is intended to be called once, at the end of a request builder,
with a one-line hook::

    request = apply_request_if_enabled(request)

It is idempotent for already-projected requests.

Research basis (implemented, not cited as a new result)
-------------------------------------------------------
* Generative Agents (Park et al., UIST 2023, arXiv:2304.03442) -- a memory
  stream retrieved by recency plus importance; here recency is explicit as
  ``last_seen_age_s`` and no importance score is invented.
* Inner Monologue (Huang et al., CoRL 2022, arXiv:2207.05608) -- textual
  observation memory fed back to an LLM instead of a metric map.
* ROVIO (Bloesch et al., RA-L 2017, doi:10.1109/LRA.2017.2718635) and relative
  maps (Castellanos et al., "Robocentric map joining", RAS 2007,
  doi:10.1016/j.robot.2006.12.001) -- robot-centric relative landmark state.
* OpenRouter prompt caching -- fixed prefix before variable content;
  ``usage.prompt_tokens_details.cached_tokens`` is the measured field:
  https://openrouter.ai/docs/features/prompt-caching

It does not measure task accuracy and does not claim that memory is as good as
the removed map.  It only makes the map-free prompt auditable.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re

OPTION = 'planner_egocentric_memory_v1'
ENV_VAR = 'UGRP_PLANNER_EGOCENTRIC_MEMORY'
SCHEMA = 'ugrp.egocentric_memory.v1'
AUDIT_SCHEMA = 'ugrp.planner_egocentric_audit.v1'
PROJECTION_KEY = 'egocentric_memory_projection_v1'

#: Matches the planner's existing own-memory deque (``TaskPlanner.memory`` maxlen=8 in
#: harness/task_planner.py on claude/e2e18-gemma-planner).  This is a request-size
#: budget copied from existing code, not a new judgment threshold.
MAX_ENTRIES = 8

#: Fixed context keys, in the order a cacheable prefix wants them.  Only keys that
#: are present are emitted.  ``order_sheet`` is task information (fixed by user
#: decision); its semantic locations/zones are not coordinates.
FIXED_KEYS = (
    'schema', 'robot_id', 'condition', 'task', 'order_sheet', 'public_rules',
    'can_send_to', 'channel', 'reply_contract', 'action_message_contract',
    'input_profile_id',
)

#: Variable context keys.  Requested order: time -> self state -> memory ->
#: received messages -> candidates, then the remaining evidence window.  The
#: own RGB image is attached after this text by the wire builder.
VARIABLE_KEYS = (
    'request_id', 'now_s', 'sim_time_s',
    'own', 'own_rgb', 'own_rgb_refs', 'own_command_history', 'self_belief',
    'own_status', 'own_belief', 'own_map', 'own_route_proposal',
    'egocentric_memory',
    'peer_reports', 'inbox', 'received_messages',
    'candidates',
    'decision_window', 'dialogue_window', 'events', 'evidence_assessment',
    'evidence_gate', 'planner_evidence_gate', 'own_act_results',
)

#: Keys that carry a static/prebuilt map or its figure.  Removed everywhere.
MAP_KEYS = frozenset({
    'static_map', 'static_map_section', 'public_map', 'map_bundle', 'map_public',
    'map_figure', 'map_figure_jpeg', 'map_figure_png', 'map_image', 'map_image_ref',
    'map_png', 'schematic', 'schematic_ref', 'map_id', 'map_version', 'map_hash',
    'map_file_sha256', 'map_sha256', 'static_map_sha256', 'public_map_sha256',
    'static_map_figure_sha256', 'map_figure_sha256',
})

#: World/own-frame pose keys.  Removed outside ``own_map`` (own_map is an own
#: observation in the own start-body frame and is explicitly allowed input).
POSE_KEYS = frozenset({
    'pose', 'pose_own_m', 'observer_pose_own_m', 'world_pose', 'pose_world',
    'ground_truth_pose', 'location_world', 'world_coordinates', 'world_xy',
})

WALL_KEYS = frozenset({'walls'})

TRUTH_KEYS = frozenset({
    'ground_truth', 'best_choices', 'hidden_state', 'simulator_state',
    'oracle', 'truth_pose', 'ground_truth_pose',
})

_BANNED_SYSTEM = ('static_map', 'static map', '정적 지도', 'schematic',
                  'camera/command pose estimate', 'world pose', 'world coordinate')
_BANNED_VALUES = ('static_map', 'static map', 'public_map', 'schematic',
                  'pose_own_m', 'observer_pose_own_m', 'ground_truth', 'best_choices',
                  'STATIC MAP FIGURE')

#: Prose in the fixed task/rules is rewritten too; a request must not advertise a
#: map that the projection removed.  Received message bodies are also passed
#: through this deterministic token rewrite, never paraphrased.
_PROSE_REWRITES = (
    ('Select route to the destination. Static map has both doors; current blockage may differ.',
     'Select route to the destination. Both doors may be remembered; current blockage may differ.'),
    ('Select route. Static map has both doors; current blockage may differ.',
     'Select route. Both doors may be remembered; current blockage may differ.'),
    ('Static map has both doors', 'Both doors may be remembered'),
    ('STATIC MAP FIGURE', 'EGOCENTRIC MEMORY SUMMARY'),
    ('Static map', 'Egocentric memory'),
    ('static_map', 'egocentric_memory'),
    ('정적 지도', '자기 중심 기억 요약'),
)

#: Exact rewrites for the builders this module was surveyed against
#: (planner bundle, pair/beam, S4, e2e own).  Longer strings first.
_REWRITES = (
    ('Use only the order sheet, static map, your camera/command pose estimate, own\n'
     'act results',
     'Use only the order sheet, your egocentric memory summary (approximate own observations; '
     'you are always at the origin facing forward), own act results'),
    ('Use only the order sheet, static map, your camera/command pose estimate',
     'Use only the order sheet, your egocentric memory summary (you are always at the origin '
     'facing forward)'),
    ('매 호출 제공되는 static_map, 정적 지도 그림 1장, order_sheet는 초기 계획 정보입니다.',
     '매 호출 제공되는 order_sheet는 초기 작업 정보입니다.'),
    ('매 호출 제공되는 static_map과 order_sheet는 초기 계획 정보입니다.',
     '매 호출 제공되는 order_sheet는 초기 작업 정보입니다.'),
    ('item, role, passage, location_ref는 static_map과 order_sheet에 있는 ID만 씁니다.',
     'item, role, passage, location_ref는 주어진 후보와 order_sheet에 있는 ID만 씁니다.'),
    ('  static_map, order_sheet, own_rgb, own_commands, own_belief, message입니다.',
     '  egocentric_memory, order_sheet, own_rgb, own_commands, own_belief, message입니다.'),
    ('자기 wrist RGB와 자기 발행 명령, 정적 지도·주문, 실제 수신 메시지만 근거입니다.',
     '자기 wrist RGB와 자기 발행 명령, 주문, 실제 수신 메시지만 근거입니다.'),
    ('정적 지도 그림은 현재 상황이 아닙니다.',
     '자기 중심 기억 요약은 현재 상황이 아닙니다.'),
    ('No truth, peer images or authored map.', 'No truth or peer images.'),
    ('No truth, peer images .', 'No truth or peer images.'),
    ('STATIC MAP FIGURE', 'EGOCENTRIC MEMORY SUMMARY'),
    ('정적 지도 그림 1장', '자기 중심 기억 요약'),
    ('정적 지도', '자기 중심 기억 요약'),
    ('static_map', 'egocentric_memory'),
    ('static map figure', 'egocentric memory summary'),
    ('Static map', 'Egocentric memory'),
    ('static map', 'egocentric memory'),
    ('authored map', 'egocentric memory'),
    ('EGOCENTRIC MEMORY SUMMARY FIGURE', 'EGOCENTRIC MEMORY SUMMARY'),
)

INSTRUCTION_EN = (
    '\n\nEgocentric memory: egocentric_memory.entries are approximate memories from your own '
    'observations, not current truth. Each entry gives kind, subject, state, distance_m and '
    'bearing_deg when known (0 degrees = forward, positive = left), an uncertainty block, and '
    'last_seen_age_s. You are always at the origin facing forward; remembered positions shift '
    'opposite to your own motion. Re-observe before acting when an entry is old, uncertain, or '
    'missing. An empty list means nothing is remembered yet.'
)
INSTRUCTION_KO = (
    '\n\n자기 중심 기억: egocentric_memory.entries는 자기 관측에서 나온 대략적인 기억이며 현재 '
    '사실이 아닙니다. 각 항목은 kind, subject, state, 알 때의 대략 distance_m·bearing_deg'
    '(0=정면, +=왼쪽), uncertainty, last_seen_age_s입니다. 로봇은 항상 원점에서 정면을 향하며, '
    '기억 속 위치는 자기 이동의 반대 방향으로 밀립니다. 오래되었거나 불확실하거나 비어 있으면 '
    '행동 전에 다시 관측하십시오. 빈 목록은 아직 기억이 없음을 뜻합니다.'
)
_HANGUL = re.compile('[가-힣]')


class EgocentricLeak(RuntimeError):
    """The projected request still contains a forbidden map/pose/truth field."""


def enabled(value=None, environ=None) -> bool:
    """Default-off toggle.  Only the exact option name (or 1/on/true/yes) turns it on."""
    raw = value
    if raw is None:
        raw = (os.environ if environ is None else environ).get(ENV_VAR, '')
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in ('', '0', 'off', 'false', 'no'):
        return False
    if text in ('1', 'on', 'true', 'yes', OPTION):
        return True
    raise ValueError(f'{ENV_VAR}: unknown value {raw!r}; use {OPTION!r} or unset it')


def apply_request_if_enabled(request, *, value=None, environ=None):
    """One-line hook for a request builder.

    OFF: returns the same object (byte-identical path, no copy).
    ON: returns a projected copy and raises ``EgocentricLeak`` if the audit finds
    a static map, map figure, world pose, truth field, or a removed coordinate.
    """
    if not enabled(value=value, environ=environ):
        return request
    if isinstance(request, dict) and (request.get(PROJECTION_KEY) or {}).get('option') == OPTION:
        return request
    return project_request(request)


def project_request(request):
    """Transform one ``{messages:[system,user,...], images:[...]}`` request."""
    if not isinstance(request, dict):
        raise TypeError('request must be a dict')
    messages = request.get('messages')
    if not isinstance(messages, list) or not messages:
        raise ValueError('request needs a non-empty messages list')
    sys_idx = next((i for i, m in enumerate(messages) if m.get('role') == 'system'), None)
    user_idx = next((i for i, m in enumerate(messages) if m.get('role') == 'user'), None)
    if sys_idx is None or user_idx is None:
        raise ValueError('request needs one system and one user message')
    system = messages[sys_idx].get('content')
    user_text = messages[user_idx].get('content')
    if not isinstance(system, str) or not isinstance(user_text, str):
        raise ValueError('system and user contents must be strings')
    try:
        original = json.loads(user_text)
    except json.JSONDecodeError as error:
        raise ValueError(f'user message is not a JSON object: {error}') from None
    if not isinstance(original, dict):
        raise ValueError('user message JSON must be an object')

    projected = project_context(original)
    system2 = variant_system(system)
    user2 = json.dumps(projected, ensure_ascii=False)

    out = copy.deepcopy(request)
    out['messages'][sys_idx] = dict(out['messages'][sys_idx], content=system2)
    out['messages'][user_idx] = dict(out['messages'][user_idx], content=user2)

    if 'images' in out:
        out['images'] = _ordered_images(_keep_non_map(out['images']))
    if 'image_refs' in out:
        out['image_refs'] = _ordered_images(_keep_non_map(out['image_refs']))

    out['tokens'] = _request_tokens(system2, user2, out.get('images') or ())
    _refresh_billed_tokens(out)

    if 'request_sha256' in out:
        refs = out.get('image_refs')
        if refs:
            out['request_sha256'] = _digest_from_refs(system2, user2, refs)
        else:
            out['request_sha256'] = _digest(system2, user2, out.get('images') or ())

    before = audit_context(original, system=system, images=request.get('images') or ())
    after = audit_context(projected, system=system2, images=out.get('images') or (),
                          forbidden_values=_world_values(original))
    leaks = list(after['leaks'])
    out[PROJECTION_KEY] = {
        'option': OPTION, 'schema': SCHEMA,
        'static_map_keys_before': before['static_map_keys'],
        'map_figure_images_before': before['map_figure_images'],
        'world_pose_keys_before': before['world_pose_keys'],
        'memory_entries': projected['egocentric_memory']['count'],
        'image_order': 'own_last', 'system_rewritten': system2 != system,
        'audit_leaks': len(leaks),
    }
    if leaks:
        raise EgocentricLeak(json.dumps(leaks[:8], ensure_ascii=False))
    return out


def project_context(context):
    """Return a new context dict: no static map, no world poses, plus egocentric memory."""
    if not isinstance(context, dict):
        raise TypeError('context must be a dict')
    body = copy.deepcopy(context)
    now = _number(body.get('now_s'))
    if now is None:
        now = _number(body.get('sim_time_s'))

    static_map = body.pop('static_map', None)
    own = body.get('own') if isinstance(body.get('own'), dict) else None
    fact_rows = list((own or {}).get('observed_facts') or [])
    evidence = body.get('evidence_assessment')
    if isinstance(evidence, dict):
        fact_rows += list(evidence.get('own_observed_facts') or [])
        evidence = copy.deepcopy(evidence)
        evidence.pop('own_observed_facts', None)
        body['evidence_assessment'] = evidence

    if isinstance(own, dict):
        own2 = copy.deepcopy(own)
        own2.pop('pose', None)
        own2.pop('observed_facts', None)
        body['own'] = own2

    previous = body.get('egocentric_memory') if isinstance(body.get('egocentric_memory'), dict) else None
    memory = build_memory(fact_rows, (own or {}).get('pose'), now)
    if previous is not None and not fact_rows:
        memory = copy.deepcopy(previous)          # idempotent re-projection
    body['egocentric_memory'] = memory
    body = _strip_map_and_pose(body)
    body = _rewrite_prose(body)
    body = _ordered(body)
    leaks = audit_context(body, forbidden_values=_world_values(context))['leaks']
    if leaks:
        raise EgocentricLeak(json.dumps(leaks[:8], ensure_ascii=False))
    if static_map is not None and 'static_map' in json.dumps(body):
        raise EgocentricLeak('static_map survived projection')
    return body


def build_memory(facts, pose, now=None):
    """Convert own observation facts (world/own-metre poses) to egocentric entries.

    ``pose`` is the CURRENT own pose (mean + covariance) in the source frame; it is
    used only inside this function and never emitted.  The output distances and
    bearings are relative to that current pose, so when the robot moves the same
    landmark's remembered position shifts opposite to the motion.
    """
    mean, sigma = _pose(pose)
    entries, seen = [], set()
    for row in facts or ():
        if not isinstance(row, dict):
            continue
        entry = _entry(row, mean, sigma, now)
        if entry is None:
            continue
        key = (entry.get('kind'), entry.get('subject'), json.dumps(entry.get('state'),
                                                                  sort_keys=True, ensure_ascii=False))
        if key in seen:
            continue
        seen.add(key)
        entries.append(entry)
    entries.sort(key=lambda e: (e['last_seen_age_s'] is None,
                                e['last_seen_age_s'] if e['last_seen_age_s'] is not None else 0.0,
                                str(e.get('subject')), str(e.get('kind'))))
    entries = entries[:MAX_ENTRIES]
    return {'schema': SCHEMA, 'entries': entries, 'count': len(entries)}


def variant_system(system):
    """Rewrite a builder system prompt to the map-free egocentric variant."""
    if not isinstance(system, str):
        raise TypeError('system must be a string')
    text = system
    for old, new in _REWRITES:
        text = text.replace(old, new)
    instruction = INSTRUCTION_KO if _HANGUL.search(text) else INSTRUCTION_EN
    if instruction not in text:
        text = text.rstrip() + instruction
    hits = [token for token in _BANNED_SYSTEM if token in text]
    if hits:
        raise EgocentricLeak(f'system still mentions {hits}')
    return text


def audit_context(context, *, system=None, images=(), forbidden_values=None):
    """Structural + value + removed-coordinate audit of one context (and optional system/images)."""
    leaks = []
    static_keys = _count_keys(context, MAP_KEYS)
    pose_keys = _count_keys_outside_own_map(context, POSE_KEYS)
    wall_keys = _count_keys_outside_own_map(context, WALL_KEYS)
    truth_keys = _count_keys(context, TRUTH_KEYS)
    for path in _key_paths_outside_own_map(context, MAP_KEYS):
        leaks.append({'kind': 'static_map_key', 'path': path})
    for path in _key_paths_outside_own_map(context, POSE_KEYS):
        leaks.append({'kind': 'world_pose_key', 'path': path})
    for path in _key_paths_outside_own_map(context, WALL_KEYS):
        leaks.append({'kind': 'wall_key', 'path': path})
    for path in _key_paths(context, TRUTH_KEYS):
        leaks.append({'kind': 'truth_key', 'path': path})

    text = json.dumps(context, ensure_ascii=False)
    low = text.lower()
    value_hits = [token for token in _BANNED_VALUES if token.lower() in low]
    for token in value_hits:
        leaks.append({'kind': 'forbidden_value', 'token': token})
    if system is not None:
        sys_hits = [token for token in _BANNED_SYSTEM if token in system]
        for token in sys_hits:
            leaks.append({'kind': 'system_mention', 'token': token})
    map_images = [row for row in images or () if _is_map_image(row)]
    for row in map_images:
        leaks.append({'kind': 'map_figure_image', 'label': row.get('label')})

    numeric = []
    if forbidden_values:
        numeric = _numeric_hits(context, forbidden_values)
        for hit in numeric:
            leaks.append({'kind': 'removed_coordinate', **hit})

    return {
        'schema': AUDIT_SCHEMA,
        'leaks': leaks,
        'static_map_keys': static_keys,
        'world_pose_keys': pose_keys,
        'wall_keys': wall_keys,
        'truth_keys': truth_keys,
        'forbidden_value_hits': value_hits,
        'system_mentions': ([t for t in _BANNED_SYSTEM if t in system] if system is not None else None),
        'map_figure_images': len(map_images),
        'numeric_matches': numeric,
        'memory_entries': ((context.get('egocentric_memory') or {}).get('count')
                           if isinstance(context.get('egocentric_memory'), dict) else None),
    }


def audit_projection(original_request, variant_request):
    """Paired audit + token report for one original/variant request (experiment record)."""
    orig_system, orig_user = _messages(original_request)
    var_system, var_user = _messages(variant_request)
    original = json.loads(orig_user)
    variant = json.loads(var_user)
    before = audit_context(original, system=orig_system,
                           images=original_request.get('images') or ())
    after = audit_context(variant, system=var_system,
                          images=variant_request.get('images') or (),
                          forbidden_values=_world_values(original))
    before_tokens = _request_tokens(orig_system, orig_user, original_request.get('images') or ())
    after_tokens = _request_tokens(var_system, var_user, variant_request.get('images') or ())
    order_ok = _order_is_variant_order(list(variant))
    return {
        'schema': AUDIT_SCHEMA,
        'ok': not after['leaks'] and before['static_map_keys'] > 0 and order_ok,
        'leaks': after['leaks'],
        'static_map_keys_before': before['static_map_keys'],
        'static_map_keys_after': after['static_map_keys'],
        'world_pose_keys_before': before['world_pose_keys'],
        'world_pose_keys_after': after['world_pose_keys'],
        'map_figure_images_before': before['map_figure_images'],
        'map_figure_images_after': after['map_figure_images'],
        'system_static_map_mentions_before': len(before['system_mentions'] or ()),
        'system_static_map_mentions_after': len(after['system_mentions'] or ()),
        'memory_entries': after['memory_entries'],
        'top_level_order_ok': order_ok,
        'top_level_keys': list(variant),
        'tokens_before': before_tokens,
        'tokens_after': after_tokens,
        'text_tokens_saved': before_tokens['total_text'] - after_tokens['total_text'],
        'images_before': len(original_request.get('images') or ()),
        'images_after': len(variant_request.get('images') or ()),
    }


def _entry(row, mean, sigma, now):
    subject = _scalar(row.get('subject'))
    if subject is None and isinstance(row.get('entity'), dict):
        subject = _scalar(row['entity'].get('id'))
    predicate = _scalar(row.get('predicate'))
    value = row.get('value')
    if not isinstance(value, (str, int, float, bool)) and value is not None:
        value = '<non-scalar omitted>'
    if subject is None and predicate is None:
        return None
    pos = _coord(row.get('pose_own_m'))
    distance = bearing = None
    uncertainty = None
    if mean is not None and pos is not None:
        dx, dy = pos[0] - mean[0], pos[1] - mean[1]
        c, s = math.cos(mean[2]), math.sin(mean[2])
        forward = c * dx + s * dy
        left = -s * dx + c * dy
        distance = math.hypot(forward, left)
        if distance > 0.0:
            bearing = math.degrees(math.atan2(left, forward))
            if bearing <= -180.0:
                bearing += 360.0
            elif bearing > 180.0:
                bearing -= 360.0
        if sigma is not None:
            uncertainty = {
                'range_m': round(sigma, 2),
                'bearing_deg': (round(math.degrees(math.atan2(sigma, max(distance, 1e-9))), 1)
                                if distance > 0.0 else None),
                'source': 'own pose covariance at observation (sigma_xy)',
            }
    observed = _number(row.get('observed_at'))
    age = None
    if observed is not None and now is not None and now >= observed:
        age = round(now - observed, 1)
    return {
        'kind': predicate or 'observation',
        'subject': subject,
        'state': value,
        'distance_m': (round(distance, 2) if distance is not None else None),
        'bearing_deg': (round(bearing, 1) if bearing is not None else None),
        'uncertainty': uncertainty,
        'last_seen_age_s': age,
        'evidence': 'own observation',
    }


def _pose(pose):
    if not isinstance(pose, dict):
        return None, None
    mean = pose.get('mean')
    if isinstance(mean, dict):
        mean = [mean.get('x'), mean.get('y'), mean.get('yaw', mean.get('theta', 0.0))]
    if not isinstance(mean, (list, tuple)) or len(mean) < 2:
        return None, None
    vals = [_number(v) for v in mean[:3]]
    if vals[0] is None or vals[1] is None:
        return None, None
    yaw = vals[2] if len(vals) > 2 and vals[2] is not None else 0.0
    sigma = None
    cov = pose.get('covariance')
    if isinstance(cov, (list, tuple)) and len(cov) >= 2:
        a = cov[0][0] if isinstance(cov[0], (list, tuple)) and cov[0] else None
        b = cov[1][1] if isinstance(cov[1], (list, tuple)) and len(cov[1]) > 1 else None
        if _number(a) is not None and _number(b) is not None and a >= 0 and b >= 0:
            sigma = math.sqrt(a + b)
    return (vals[0], vals[1], yaw), sigma


def _coord(value):
    if isinstance(value, dict):
        x, y = _number(value.get('x')), _number(value.get('y'))
        return (x, y) if x is not None and y is not None else None
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        x, y = _number(value[0]), _number(value[1])
        return (x, y) if x is not None and y is not None else None
    return None


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _scalar(value):
    return value if isinstance(value, (str, int, float, bool)) and value is not None else None


def _ordered(body):
    out = {}
    for key in FIXED_KEYS:
        if key in body:
            out[key] = body[key]
    for key in VARIABLE_KEYS:
        if key in body:
            out[key] = body[key]
    for key, value in body.items():                 # unknown keys are variable, kept last
        if key not in out:
            out[key] = value
    return out


def _order_is_variant_order(keys):
    rank = {k: i for i, k in enumerate(FIXED_KEYS + VARIABLE_KEYS)}
    known = [rank[k] for k in keys if k in rank]
    return known == sorted(known)


def _strip_map_and_pose(node, path=()):
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in MAP_KEYS:
                continue
            if 'own_map' not in path and (key in POSE_KEYS or key in WALL_KEYS):
                continue
            out[key] = _strip_map_and_pose(value, path + (key,))
        return out
    if isinstance(node, list):
        return [_strip_map_and_pose(value, path) for value in node]
    return node


def _rewrite_prose(node):
    if isinstance(node, dict):
        return {key: _rewrite_prose(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_rewrite_prose(value) for value in node]
    if isinstance(node, str):
        for old, new in _PROSE_REWRITES:
            node = node.replace(old, new)
        return node
    return node


def _count_keys(node, keys):
    if isinstance(node, dict):
        return sum(1 for k in node if k in keys) + sum(_count_keys(v, keys) for v in node.values())
    if isinstance(node, list):
        return sum(_count_keys(v, keys) for v in node)
    return 0


def _count_keys_outside_own_map(node, keys, path=()):
    if isinstance(node, dict):
        if 'own_map' in path:
            return 0
        return sum(1 for k in node if k in keys) + sum(
            _count_keys_outside_own_map(v, keys, path + (k,)) for k, v in node.items())
    if isinstance(node, list):
        return sum(_count_keys_outside_own_map(v, keys, path) for v in node)
    return 0


def _key_paths(node, keys, path=()):
    out = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = path + (key,)
            if key in keys:
                out.append('$.' + '.'.join(map(str, here)))
            out.extend(_key_paths(value, keys, here))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            out.extend(_key_paths(value, keys, path + (f'[{i}]',)))
    return out


def _key_paths_outside_own_map(node, keys, path=()):
    if isinstance(node, dict) and 'own_map' in path:
        return []
    return _key_paths(node, keys, path)


def _world_values(context):
    """Pairs/triples and high-precision scalars from the removed map/pose blocks."""
    pairs, scalars = set(), set()
    roots = [context.get('static_map'), (context.get('own') or {}).get('pose')]
    own = context.get('own') or {}
    facts = list(own.get('observed_facts') or ())
    evidence = context.get('evidence_assessment') or {}
    facts += list(evidence.get('own_observed_facts') or ())
    for fact in facts:
        if isinstance(fact, dict):
            roots.extend([fact.get('pose_own_m'), fact.get('observer_pose_own_m')])

    def walk(value):
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            nums = [_number(v) for v in value]
            if len(nums) in (2, 3) and all(v is not None for v in nums):
                pairs.add((round(nums[0], 6), round(nums[1], 6)))
            for item in value:
                walk(item)
        else:
            v = _number(value)
            if v is not None and not float(v).is_integer() and len(repr(float(v)).split('.')[-1]) >= 6:
                scalars.add(round(v, 9))

    for root in roots:
        walk(root)
    return {'pairs': pairs, 'scalars': scalars}


def _numeric_hits(context, forbidden):
    pairs, scalars = set(), set()

    def walk(value, path=()):
        if isinstance(value, dict):
            if 'own_map' in path:
                return
            for key, item in value.items():
                walk(item, path + (key,))
        elif isinstance(value, list):
            if 'own_map' in path:
                return
            nums = [_number(v) for v in value]
            if len(nums) in (2, 3) and all(v is not None for v in nums):
                pairs.add((round(nums[0], 6), round(nums[1], 6)))
            for item in value:
                walk(item, path)
        else:
            v = _number(value)
            if v is not None and not float(v).is_integer():
                scalars.add(round(v, 9))

    walk(context)
    hits = []
    for pair in sorted(pairs & forbidden['pairs']):
        hits.append({'pair': list(pair)})
    for value in sorted(scalars & forbidden['scalars']):
        hits.append({'scalar': value})
    return hits


def _is_map_image(row):
    if not isinstance(row, dict):
        return False
    label = str(row.get('label') or '').lower()
    ref = str(row.get('ref') or '').lower()
    return ('static map' in label or 'map figure' in label or 'schematic' in label
            or 'map' in ref or 'schematic' in ref)


def _keep_non_map(rows):
    return [copy.deepcopy(row) for row in rows or () if not _is_map_image(row)]


def _ordered_images(rows):
    return sorted(rows, key=lambda row: 0 if 'own' in str(row.get('label') or '').lower()
                  or 'own' in str(row.get('ref') or '').lower() else 1)


def _messages(request):
    messages = request.get('messages') or ()
    system = next((m.get('content') for m in messages if m.get('role') == 'system'), '')
    user = next((m.get('content') for m in messages if m.get('role') == 'user'), '')
    return system, user


def _request_tokens(system, user, images=()):
    from harness.zone_study_prompts_ko import request_tokens
    return request_tokens(system, user, images)


def _digest(system, user, images=()):
    from harness.zone_study_prompts_ko import request_digest
    return request_digest(system, user, images)


def _digest_from_refs(system, user, refs):
    from harness.zone_study_prompts_ko import request_digest_from_refs
    return request_digest_from_refs(system, user, refs)


def _refresh_billed_tokens(request):
    billed = request.get('billed_tokens')
    if billed is None:
        return
    tokens = request['tokens']
    if isinstance(billed, dict) and 'image_policy' in billed:
        from harness.pair_llm_billing import billed_tokens as pair_billed
        request['billed_tokens'] = pair_billed(
            tokens, system_billed=billed.get('system_billed', tokens['system']))
        return
    if isinstance(billed, dict) and 'policy' in billed and 'total_text_billed' in billed:
        out = dict(billed)
        out['system_actual'] = tokens['system']
        out['user'] = tokens['user']
        out['images'] = tokens['images']
        out['total_text_billed'] = out.get('system_billed', tokens['system']) + tokens['user']
        request['billed_tokens'] = out
        return
    raise ValueError('unknown billed_tokens shape; cannot keep the bill consistent')


__all__ = [
    'OPTION', 'ENV_VAR', 'SCHEMA', 'AUDIT_SCHEMA', 'PROJECTION_KEY', 'MAX_ENTRIES',
    'FIXED_KEYS', 'VARIABLE_KEYS', 'MAP_KEYS', 'POSE_KEYS', 'TRUTH_KEYS',
    'EgocentricLeak', 'enabled', 'apply_request_if_enabled', 'project_request',
    'project_context', 'build_memory', 'variant_system', 'audit_context',
    'audit_projection',
]
