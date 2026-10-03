"""Two-robot per-call input and request of the pair-carry LLM layer (viability test).

The zone-study input contract (``harness.zone_study_contract``) is hard-wired to three
robots: ``channel_section`` lists r3, ``allowed_edges`` is a 3-mesh, ``_build_sheet`` writes
``team_size=3`` and ``_shape_hits`` rejects any payload whose channel differs from that. A
two-robot payload therefore cannot pass ``validate_robot_payload`` and the study code is
frozen and hashed into earlier bundles. This module is the thin pair layer instead:

* its own payload schema (``ugrp.pair_llm_call_input.v1``), pair channel section
  (``can_send_to`` is the partner only) and ``team_size = 2`` order sheet;
* its validator REUSES the study's closed-schema checks (forbidden keys, non-ASCII keys,
  evaluation-only values, static-map / order-sheet / history / inbox / rgb-ref shapes, pinned
  hashes), so the input boundary is the study's boundary and cannot drift;
* the request has the same fields as ``zone_study_prompts_ko.build_request`` (messages, images,
  image_refs, request_sha256, tokens, billed_tokens, input_sha256), so ``archive_request`` /
  ``verify_archived_request`` and the send ledger work unchanged.

Input boundary (AGENTS.md): own robot_cam RGB (one JPEG), the static map (projection + schematic
figure), the order sheet, own command history, own belief, and delivered messages. Nothing from
the simulator, no measured joint, no contact/success flag, no shared top camera, no partner
status (the fixed-enum pair status stays between the two controllers and is not a model input).
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from harness import zone_study_contract as zc
from harness import zone_study_prompts_ko as pk
from harness import zone_study_protocol as zp
from harness.pair_llm_prompts_ko import (PAIR_CONDITIONS, PAIR_ROBOTS, PAIR_ROLES, PROMPT_VERSION,
                                         fixed_prompt_reference_tokens, partner_of, system_prompt)
from harness.zone_map_schematic import digest
from harness.zone_study_inputs import INPUT_PROFILE, OrderSheetSource, vocabulary

PAYLOAD_SCHEMA = 'ugrp.pair_llm_call_input.v1'
REQUEST_SCHEMA = 'ugrp.pair_llm_request.v1'
BASE_KEYS = ('schema', 'request_id', 'robot_id', 'condition', 'sim_time_s', 'static_map', 'order_sheet',
             'own_rgb_refs', 'own_command_history', 'self_belief', 'channel')
REQUIRED_KEYS = ('schema', 'request_id', 'robot_id', 'condition', 'sim_time_s', 'static_map', 'order_sheet',
                 'own_rgb_refs', 'own_command_history', 'channel')
IMAGE_OWN, IMAGE_MAP = pk.IMAGE_OWN, pk.IMAGE_MAP
JPEG, PNG = 'image/jpeg', 'image/png'


def allowlist(condition: str) -> frozenset:
    _check_condition(condition)
    return frozenset(BASE_KEYS) | ({'inbox'} if zp.spec(condition).channel_open else frozenset())


def _check_condition(condition):
    if condition not in PAIR_CONDITIONS:
        raise zc.ContractViolation(f'{condition!r} is not a pair LLM condition {PAIR_CONDITIONS}')


def pair_channel_section(condition: str, actor: str) -> dict:
    """The robot-facing description of its own channel: the partner is the only recipient."""
    _check_condition(condition)
    partner = partner_of(actor)
    spec = zp.spec(condition)
    peers = [partner] if spec.channel_open else []
    return {'condition': condition, 'topology': spec.topology, 'encoding': spec.encoding,
            'free_text_allowed': spec.encoding == 'free_ko', 'can_send_to': list(peers),
            'can_receive_from': list(peers), 'role': 'peer'}


class PairSheetSource:
    """The frozen order sheet of the pair run: the study sheet with ``team_size = 2``.

    ``OrderSheetSource`` builds and validates the sheet from the scenario config (including the
    opaque scenario ref and the map hashes); only the team size field is rewritten, and the digest
    of THIS sheet is what the payload is pinned to.
    """

    def __init__(self, scenario: Mapping, map_bundle: Mapping):
        self._inner = OrderSheetSource(scenario, map_bundle)
        sheet = self._inner.sheet()
        for order in sheet['orders']:
            if order['required_robots'] > len(PAIR_ROBOTS):
                raise zc.ContractViolation(f'{order["order_id"]}: needs {order["required_robots"]} robots; '
                                           f'the pair has {len(PAIR_ROBOTS)}')
        sheet['team_size'] = len(PAIR_ROBOTS)
        self._sheet = sheet
        self.sha256 = digest(sheet)
        self.scenario_id = self._inner.scenario_id
        self.scenario_ref = self._inner.scenario_ref
        self.seeds = self._inner.seeds

    def sheet(self) -> dict:
        return copy.deepcopy(self._sheet)

    @property
    def pinned(self) -> dict:
        return {**self._inner.pinned, 'order_sheet_sha256': self.sha256}

    def hidden_events(self) -> list:
        return self._inner.hidden_events()

    def manifest(self) -> dict:
        return {**self._inner.manifest(), 'order_sheet_sha256': self.sha256, 'team_size': len(PAIR_ROBOTS)}


# ---------------------------------------------------------------------------
# payload

def own_rgb_ref(robot_id: str, index: int, captured_at_sim_s: float, sha256: str) -> dict:
    if robot_id not in PAIR_ROBOTS:
        raise zc.ContractViolation(f'unknown pair robot: {robot_id!r}')
    if not isinstance(sha256, str) or not zc.SHA256_HEX.match(sha256):
        raise zc.ContractViolation('own_rgb_ref needs the sha256 of the frame bytes (auditable input)')
    return {'ref': f'own-{robot_id}-{int(index):04d}', 'kind': 'own_wrist_rgb',
            'captured_at_sim_s': float(captured_at_sim_s), 'sha256': sha256}


def _trim(values: Sequence | None, limit: int) -> list:
    items = list(values or ())
    return copy.deepcopy(items[-limit:] if limit and len(items) > limit else items)


def build_payload(*, robot_id: str, condition: str, request_id: str, sim_time_s: float, static_map: Mapping,
                  order_sheet: Mapping, own_rgb_refs: Sequence[Mapping], own_command_history: Sequence[Mapping],
                  self_belief: Mapping, inbox: Sequence[Mapping] | None = None, pinned: Mapping | None = None,
                  profile: Mapping = INPUT_PROFILE) -> dict:
    """One per-call payload of a pair robot, validated before it is returned."""
    _check_condition(condition)
    if robot_id not in PAIR_ROBOTS:
        raise zc.ContractViolation(f'{robot_id!r} is not a pair robot {PAIR_ROBOTS}')
    payload = {'schema': PAYLOAD_SCHEMA, 'request_id': request_id, 'robot_id': robot_id, 'condition': condition,
               'sim_time_s': float(sim_time_s), 'static_map': copy.deepcopy(dict(static_map)),
               'order_sheet': copy.deepcopy(dict(order_sheet)),
               'own_rgb_refs': _trim(own_rgb_refs, int(profile['own_rgb_frames'])),
               'own_command_history': _trim(own_command_history, int(profile['command_history_entries'])),
               'self_belief': copy.deepcopy(dict(self_belief)),
               'channel': pair_channel_section(condition, robot_id)}
    if zp.spec(condition).channel_open:
        payload['inbox'] = _trim(inbox, int(profile['inbox_messages']))
    elif inbox:
        raise zc.ContractViolation(f'{condition} delivers no messages, so an inbox is not allowed')
    problems = payload_violations(payload, pinned=pinned)
    if problems:
        raise zc.ContractViolation('pair payload violates the input boundary: ' + '; '.join(problems))
    return payload


def payload_violations(payload: object, *, pinned: Mapping | None = None) -> list[str]:
    """Every boundary violation of a pair payload (empty list = clean). Study checks, pair shape."""
    if not isinstance(payload, Mapping):
        return ['payload must be an object']
    out: list[str] = []
    if payload.get('schema') != PAYLOAD_SCHEMA:
        out.append(f'payload schema must be {PAYLOAD_SCHEMA}, got {payload.get("schema")!r}')
    condition = payload.get('condition')
    if condition not in PAIR_CONDITIONS:
        return out + [f'unknown pair condition: {condition!r}']
    actor = payload.get('robot_id')
    if actor not in PAIR_ROBOTS:
        return out + [f'{actor!r} is not a pair robot {PAIR_ROBOTS}']
    allow = allowlist(condition)
    extra = [k for k in payload if k not in allow]
    if extra:
        out.append(f'key(s) outside the {condition} pair allowlist: {sorted(extra)}')
    missing = [k for k in REQUIRED_KEYS if k not in payload]
    if missing:
        out.append(f'missing required key(s): {missing}')
    time_s = payload.get('sim_time_s')
    if isinstance(time_s, bool) or not isinstance(time_s, (int, float)) or time_s < 0:
        out.append('sim_time_s must be a non-negative number')
    try:
        json.dumps(zc.thaw_for_json(payload), allow_nan=False)
    except (TypeError, ValueError) as error:
        return out + [f'payload is not JSON serialisable: {error}']
    out.extend(zc.forbidden_key_hits(payload))
    out.extend(zc.non_ascii_keys(payload))
    out.extend(zc._value_hits(payload))
    now = time_s if isinstance(time_s, (int, float)) and not isinstance(time_s, bool) else None
    out.extend(zc._static_map_hits(payload))
    out.extend(zc._order_sheet_hits(payload))
    if not isinstance(payload.get('request_id'), str) or not zc.ID_TOKEN.match(str(payload.get('request_id'))):
        out.append('request_id must be a literal id token')
    if 'own_rgb_refs' in payload:
        out.extend(zc._rgb_hits(payload['own_rgb_refs'], 'own_rgb_refs', [actor], now))
    if 'own_command_history' in payload:
        out.extend(zc._history_hits(payload, now))
    if 'self_belief' in payload:
        out.extend(zc._closed(payload['self_belief'], zc.BELIEF_KEYS, 'self_belief'))
        out.extend(zc._typed(payload['self_belief'], 'self_belief', types=zc.BELIEF_TYPES))
    out.extend(_pair_inbox_hits(payload, now))
    channel = payload.get('channel')
    out.extend(zc._closed(channel, zc.CHANNEL_KEYS, 'channel', required=zc.CHANNEL_KEYS))
    if isinstance(channel, Mapping) and channel != pair_channel_section(condition, actor):
        out.append('channel does not match the pair condition rule for this actor')
    sheet = payload.get('order_sheet') if isinstance(payload.get('order_sheet'), Mapping) else {}
    if sheet.get('team_size') != len(PAIR_ROBOTS):
        out.append(f'order_sheet.team_size must be {len(PAIR_ROBOTS)} for the pair')
    if pinned:
        out.extend(zc._pinned_hits(payload, pinned))
    return out


def _pair_inbox_hits(payload: Mapping, now) -> list[str]:
    inbox = payload.get('inbox')
    if inbox is None:
        return []
    spec = zc.condition(payload['condition'])        # the study row: topology / encoding of the message
    hits = zc._inbox_hits(payload, spec, None, now)
    robot = payload.get('robot_id')
    for envelope in inbox if isinstance(inbox, Sequence) and not isinstance(inbox, str) else ():
        if not isinstance(envelope, Mapping):
            continue
        if envelope.get('sender') != partner_of(robot) or list(envelope.get('recipients') or ()) != [robot]:
            hits.append(f'inbox envelope {envelope.get("message_id")} is not partner -> {robot}')
    return hits


# ---------------------------------------------------------------------------
# images + the immutable per-call input

def _uri(data: bytes, mime: str) -> str:
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise zp.ProtocolError('an image must be non-empty bytes')
    return f'data:{mime};base64,' + base64.b64encode(bytes(data)).decode()


def png_or_jpeg(data: bytes) -> str:
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return PNG
    if data[:3] == b'\xff\xd8\xff':
        return JPEG
    raise zp.ProtocolError('image bytes are neither a PNG nor a JPEG')


@dataclass(frozen=True)
class PairInputs:
    """One validated pair payload plus the exactly two images it references.

    The own wrist JPEG is bound to its ``own_rgb_refs`` entry by sha256, the map figure to the PINNED
    schematic of the frozen map bundle (a self-declared ref proves nothing), so another camera's bytes
    cannot be relabelled and the figure is an artefact of the frozen map.
    """

    payload: dict
    wrist_jpeg: bytes
    map_png: bytes
    pinned: dict

    def __post_init__(self):
        set_ = object.__setattr__
        payload = pk.thaw(self.payload)
        problems = payload_violations(payload, pinned=self.pinned)
        if problems:
            raise zp.ProtocolError('payload violates the pair input boundary: ' + '; '.join(problems))
        own = list(payload.get('own_rgb_refs', ()))
        if not own:
            raise zp.ProtocolError('a wrist image needs the own_rgb_ref it was captured for')
        set_(self, 'wrist_jpeg', pk._bound_bytes(self.wrist_jpeg, own[-1], 'wrist_jpeg'))
        if png_or_jpeg(self.wrist_jpeg) != JPEG:
            raise zp.ProtocolError('the own wrist frame must be a JPEG')
        ref = (payload.get('static_map') or {}).get('schematic_ref')
        if not isinstance(ref, Mapping):
            raise zp.ProtocolError('the pair request carries the static map figure: static_map.schematic_ref')
        if not self.pinned or self.pinned.get('schematic_png_sha256') != ref.get('png_sha256'):
            raise zp.ProtocolError('static_map.schematic_ref is not the pinned map schematic')
        set_(self, 'map_png', pk._bound_bytes(self.map_png, {'ref': ref['ref'], 'sha256': ref['png_sha256']},
                                              'map_png'))
        if png_or_jpeg(self.map_png) != PNG:
            raise zp.ProtocolError('the static map figure must be the schematic PNG')
        set_(self, 'payload', pk.freeze(payload))
        set_(self, '_payload_sha256', digest(payload))
        set_(self, 'pinned', dict(self.pinned))

    # -- views --------------------------------------------------------------
    def payload_dict(self) -> dict:
        return pk.thaw(self.payload)

    @property
    def condition(self) -> str:
        return self.payload['condition']

    @property
    def robot_id(self) -> str:
        return self.payload['robot_id']

    @property
    def request_id(self) -> str:
        return self.payload['request_id']

    @property
    def sim_time_s(self) -> float:
        return self.payload['sim_time_s']

    @property
    def payload_sha256(self) -> str:
        return self._payload_sha256

    @property
    def order_sheet(self) -> dict:
        return pk.thaw(self.payload['order_sheet'])

    @property
    def map_public(self) -> dict:
        return pk.thaw(self.payload['static_map']['public_map'])

    @property
    def inbox(self) -> tuple:
        return tuple(pk.thaw(self.payload.get('inbox', ())))

    def order_ids(self) -> tuple:
        return tuple(o['order_id'] for o in self.order_sheet['orders'])

    def item_ids(self) -> tuple:
        return tuple(i for o in self.order_sheet['orders'] for i in o.get('item_ids') or ())

    def roles_by_order(self) -> dict:
        table = self.order_sheet.get('kinds') or {}
        return {o['order_id']: tuple((table.get(o['kind']) or {}).get('roles') or zc.ROLE_NAMES)
                for o in self.order_sheet['orders']}

    def passages(self) -> tuple:
        return tuple(p['id'] for p in self.map_public.get('passages', ()))

    def vocabulary(self):
        return vocabulary(self.order_sheet, self.map_public)

    def location_refs(self) -> tuple:
        return tuple(sorted(self.vocabulary().location_refs))


def image_manifest(inputs: PairInputs) -> list:
    """Which validated reference each attached image belongs to (own frame first, map figure second)."""
    payload = inputs.payload
    own = list(payload['own_rgb_refs'])[-1]
    sheet_ref = payload['static_map']['schematic_ref']
    return [{'label': IMAGE_OWN, 'ref': own['ref'], 'sha256': own['sha256'],
             'captured_at_sim_s': own['captured_at_sim_s'], 'mime': JPEG,
             'bytes_sha256': pk.image_sha256(inputs.wrist_jpeg)},
            {'label': IMAGE_MAP, 'ref': sheet_ref['ref'], 'sha256': sheet_ref['png_sha256'],
             'captured_at_sim_s': None, 'mime': PNG, 'bytes_sha256': pk.image_sha256(inputs.map_png)}]


def request_images(inputs: PairInputs) -> list:
    out = [{'label': IMAGE_OWN, 'image': _uri(inputs.wrist_jpeg, JPEG)},
           {'label': IMAGE_MAP, 'image': _uri(inputs.map_png, PNG)}]
    for item in out:
        if any(token in item['label'].lower() for token in pk.FORBIDDEN_IMAGE_TOKENS):
            raise zp.ProtocolError(f'{item["label"]}: TOP and nav_cam images are not robot input')
    return out


def billed_tokens(tokens: Mapping) -> dict:
    reference = fixed_prompt_reference_tokens()
    return {'policy': pk.FIXED_PROMPT_POLICY, 'tokenizer': tokens['tokenizer'],
            'system_actual': tokens['system'], 'system_billed': reference, 'user': tokens['user'],
            'images': tokens['images'], 'total_text_billed': reference + tokens['user']}


def build_request(inputs: PairInputs, *, window=None) -> dict:
    """One model request: Korean pair system text, the payload JSON, and the two labelled images.

    ``window`` is ``Transport.window_context`` (the transport's real budget). The user message is the
    validated payload verbatim plus ``dialogue_window`` when the channel is open (the budget only, never
    an observation).
    """
    if not isinstance(inputs, PairInputs):
        raise zp.ProtocolError('inputs must be a PairInputs wrapping a validated pair payload')
    condition, rid = inputs.condition, inputs.robot_id
    spec = zp.spec(condition)
    window = dict(window or {})
    window.pop('received', None)                  # the inbox is the payload's, never sent twice
    issued = list(window.pop('sent', None) or ())
    if not spec.channel_open and (issued or window):
        raise zp.ProtocolError(f'{condition} has no dialogue channel: sent and window must be empty')
    body = inputs.payload_dict()
    problems = payload_violations(body, pinned=inputs.pinned)
    if problems or digest(body) != inputs.payload_sha256:
        raise zp.ProtocolError('the payload changed after validation: ' + '; '.join(problems))
    cap_window, cap_robot = spec.max_window_utterances, spec.max_robot_utterances
    if spec.channel_open:
        cap_window = window.pop('max_utterances', spec.max_window_utterances)
        cap_robot = window.pop('max_your_utterances', spec.max_robot_utterances)
        if any(type(cap) is not int or cap < 0 for cap in (cap_window, cap_robot)):
            raise zp.ProtocolError('dialogue caps must be non-negative integers')
        left = window.pop('your_utterances_left', max(0, cap_robot - len(issued)))
        window_id = window.pop('window_id', None)
        if window:
            raise zp.ProtocolError(f'unknown dialogue window fields {sorted(window)}')
        if not zp.is_message_id(window_id or ''):
            raise zp.ProtocolError('an open dialogue window needs its window_id')
        body[pk.WINDOW_KEY] = {'window_id': window_id, 'max_utterances': cap_window,
                               'max_your_utterances': cap_robot, 'your_utterances_left': left, 'sent': issued}
    system = system_prompt(condition, rid, cap_window=cap_window, cap_robot=cap_robot)
    user = json.dumps(body, sort_keys=True, ensure_ascii=False)
    images, manifest = request_images(inputs), image_manifest(inputs)
    for row in manifest:
        if row['bytes_sha256'] != row['sha256']:
            raise zp.ProtocolError(f'{row["label"]}: the attached bytes are not the frame {row["ref"]} names')
    request = {'schema': REQUEST_SCHEMA, 'request_id': inputs.request_id, 'condition': condition, 'actor': rid,
               'prompt_role': 'peer', 'prompt_version': PROMPT_VERSION, 'protocol_version': zp.PROTOCOL_VERSION,
               'payload_schema': PAYLOAD_SCHEMA, 'input_sha256': inputs.payload_sha256,
               'input_profile_id': INPUT_PROFILE['profile_id'],
               'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
               'images': images, 'image_refs': manifest}
    request['request_sha256'] = pk.request_digest_from_refs(system, user, manifest)
    request['tokens'] = pk.request_tokens(system, user, images)
    request['billed_tokens'] = billed_tokens(request['tokens'])
    return request


def wire_images(body: bytes) -> list:
    """Labels, mime types and byte digests of the images in one proxy request body (audit path).

    Reads the body exactly as it left for the proxy (``GeminiProxyCompleter`` writes the user message as
    text part, then a label text part and an ``image_url`` part per image).
    """
    request = json.loads(body)
    out = []
    for message in request.get('messages', ()):
        content = message.get('content')
        if isinstance(content, str):
            continue
        label = None
        for part in content or ():
            if part.get('type') == 'text':
                label = part.get('text')
            elif part.get('type') == 'image_url':
                head, _, data = part['image_url']['url'].partition(',')
                raw = base64.b64decode(data)
                out.append({'label': label, 'mime': head[len('data:'):].split(';')[0], 'bytes': len(raw),
                            'sha256': hashlib.sha256(raw).hexdigest()})
    return out


__all__ = ['PAYLOAD_SCHEMA', 'REQUEST_SCHEMA', 'PAIR_ROBOTS', 'PAIR_ROLES', 'PAIR_CONDITIONS', 'allowlist',
           'pair_channel_section', 'PairSheetSource', 'own_rgb_ref', 'build_payload', 'payload_violations',
           'PairInputs', 'image_manifest', 'request_images', 'build_request', 'wire_images', 'billed_tokens']
