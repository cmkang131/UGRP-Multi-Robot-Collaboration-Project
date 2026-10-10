"""e2e1 causal input/state contracts. No simulator or authored map reader.

This is an input handoff, not a runnable transport adapter. Unknown/future
sources and legacy static fallbacks fail closed before an executor is called.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
import math

from harness.zone_study_contract import ContractViolation, Vocabulary, channel_section, digest
from harness import zone_study_prompts_ko as pk

OPTION = 'on_v1'
SCHEMA = 'ugrp.e2e_own_inputs.v1'
ROUTE_SCHEMA = 'ugrp.e2e_own_route.v1'
# Closed nested schemas do the enforcement; this scan also gives useful errors.
FORBIDDEN = {'static_map', 'public_map', 'map_figure', 'initial_location', 'slot', 'pickup_bay',
             'zone_slots', 'beam_xyyaw', 'spawn', 'robot_spawns', 'world_alignment',
             'eval', 'eval_only', 'truth', 'success', 'contact', 'measured_joints', 'static_route',
             'target_coordinates', 'destination_xy', 'B_coordinates'}
TASK = {'orders': [{'order_id': 'order-5', 'kind': 'long_beam', 'count': 1,
                   'required_robots': 2, 'destination_zone': 'B',
                   'roles': ['end_neg', 'end_pos']}],
        'destination_visual_description': '흰 사각형 표지 세 개가 있는 파란 바닥 목적 구역 B',
        'fixed_roles': {'r1': 'end_neg', 'r2': 'end_pos', 'r3': 'idle'}}


def enabled(value):
    if value not in ('off', OPTION):
        raise ContractViolation('UNKNOWN_E2E_OWN_INPUTS_OPTION')
    return value == OPTION


def closed(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ContractViolation(label + ': CLOSED_SCHEMA_REQUIRED')


def scan(value, path='input'):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN:
                raise ContractViolation(path + '.' + key + ': PRIVILEGED_INPUT')
            scan(child, path + '.' + key)
    elif isinstance(value, (list, tuple)):
        for i, child in enumerate(value):
            scan(child, f'{path}[{i}]')
    elif isinstance(value, float) and not math.isfinite(value):
        raise ContractViolation(path + ': NONFINITE_INPUT')


def numbers(value, n, label):
    if (not isinstance(value, list) or len(value) != n or
            any(type(x) not in (int, float) or not math.isfinite(x) for x in value)):
        raise ContractViolation(label + ': FINITE_VECTOR_REQUIRED')


def rgb_ref(ref, rid, now, observed):
    closed(ref, ('robot_id', 'frame_id', 't_sim', 'sha256'), 'RGB_REF')
    if (ref['robot_id'] != rid or type(ref['frame_id']) is not int or ref['frame_id'] < 0
            or type(ref['t_sim']) not in (int, float) or not 0 <= ref['t_sim'] <= now
            or not isinstance(ref['sha256'], str) or len(ref['sha256']) != 64
            or any(c not in '0123456789abcdef' for c in ref['sha256'])):
        raise ContractViolation('OWN_CAUSAL_RGB_REQUIRED')
    if ref not in observed:
        raise ContractViolation('UNOBSERVED_RGB_SOURCE')


def validate_map(value, rid, now, observed):
    closed(value, ('robot_id', 'frame', 'map_version', 'pose', 'walls', 'goal', 'sources'), 'OWN_MAP')
    if (value['robot_id'] != rid or value['frame'] != rid + '/own_start'
            or type(value['map_version']) is not int or value['map_version'] < 0):
        raise ContractViolation('OWN_START_FRAME_REQUIRED')
    if not isinstance(value['sources'], list) or not value['sources']:
        raise ContractViolation('MAP_RGB_SOURCE_REQUIRED')
    for ref in value['sources']: rgb_ref(ref, rid, now, observed)
    pose = value['pose']
    closed(pose, ('mean', 'covariance', 'sources'), 'OWN_POSE')
    numbers(pose['mean'], 3, 'POSE')
    if not isinstance(pose['covariance'], list) or len(pose['covariance']) != 3:
        raise ContractViolation('POSE_COVARIANCE_REQUIRED')
    for row in pose['covariance']: numbers(row, 3, 'COVARIANCE')
    import numpy as np
    cov = np.asarray(pose['covariance'])
    if not np.allclose(cov, cov.T) or np.linalg.eigvalsh(cov).min() < -1e-10:
        raise ContractViolation('POSITIVE_SEMIDEFINITE_COVARIANCE_REQUIRED')
    if not isinstance(pose['sources'], list) or not pose['sources']:
        raise ContractViolation('POSE_RGB_SOURCE_REQUIRED')
    for ref in pose['sources']: rgb_ref(ref, rid, now, observed)
    if not isinstance(value['walls'], list): raise ContractViolation('WALL_LIST_REQUIRED')
    for wall in value['walls']:
        closed(wall, ('a', 'b', 'sources'), 'OWN_WALL')
        numbers(wall['a'], 2, 'WALL'); numbers(wall['b'], 2, 'WALL')
        if not isinstance(wall['sources'], list) or not wall['sources']:
            raise ContractViolation('WALL_RGB_SOURCE_REQUIRED')
        for ref in wall['sources']: rgb_ref(ref, rid, now, observed)
    if value['goal'] is not None:
        closed(value['goal'], ('label', 'sources'), 'OWN_GOAL')
        if value['goal']['label'] != 'B' or not value['goal']['sources']:
            raise ContractViolation('OBSERVED_B_REQUIRED')
        for ref in value['goal']['sources']: rgb_ref(ref, rid, now, observed)
    scan(value)
    return copy.deepcopy(value)


def validate_route(value, rid, now, observed):
    closed(value, ('schema', 'robot_id', 'frame_id', 'map_version', 'own_map',
                   'B_rgb_sources', 'waypoints', 'route_hash'), 'OWN_ROUTE')
    if value['schema'] != ROUTE_SCHEMA or value['robot_id'] != rid:
        raise ContractViolation('OWN_ROUTE_IDENTITY_REQUIRED')
    mapped = validate_map(value['own_map'], rid, now, observed)
    if value['map_version'] != mapped['map_version'] or value['frame_id'] != max(r['frame_id'] for r in mapped['sources']):
        raise ContractViolation('ROUTE_MAP_REVISION_MISMATCH')
    if not value['B_rgb_sources'] or mapped['goal'] is None:
        raise ContractViolation('B_RGB_SOURCE_REQUIRED')
    if value['B_rgb_sources'] != mapped['goal']['sources']:
        raise ContractViolation('ROUTE_B_SOURCE_MISMATCH')
    for ref in value['B_rgb_sources']: rgb_ref(ref, rid, now, observed)
    if not isinstance(value['waypoints'], list) or len(value['waypoints']) < 2:
        raise ContractViolation('OWN_ROUTE_WAYPOINTS_REQUIRED')
    for xy in value['waypoints']: numbers(xy, 2, 'WAYPOINT')
    body = {k: v for k, v in value.items() if k != 'route_hash'}
    if value['route_hash'] != digest(body): raise ContractViolation('ROUTE_HASH_MISMATCH')
    scan(value)
    return copy.deepcopy(value)


class Agreement:
    """Received proposal/approval and epoch/segment GO+ACK state, no motion API.

    Receipt IDs must come from the actual delivered channel. Response IDs must
    come from the actual model ledger. The embedding S4 adapter supplies both.
    """
    def __init__(self):
        self.proposal = None
        self.approved = False
        self.key = None
        self.votes = {}
        self.response_contexts = {}

    def _bind_response(self, response_id, context):
        previous = self.response_contexts.get(response_id)
        if previous is not None and previous != context:
            raise ContractViolation('MODEL_RESPONSE_REUSED_ACROSS_ROUTE_OR_EPOCH')
        self.response_contexts[response_id] = context

    def propose(self, route_hash, message_id, *, delivered_ids):
        if message_id not in delivered_ids or len(route_hash) != 64:
            raise ContractViolation('RECEIVED_ROUTE_PROPOSAL_REQUIRED')
        self.proposal = (route_hash, message_id)
        self.approved = False
        self.key, self.votes = None, {}

    def approve(self, route_hash, reply_to, *, robot_id, response_id, model_response_ids):
        if robot_id != 'r2' or response_id not in model_response_ids or self.proposal != (route_hash, reply_to):
            raise ContractViolation('MATCHING_R2_MODEL_APPROVAL_REQUIRED')
        self._bind_response(response_id, ('r2','approve',self.proposal))
        self.approved = True

    def begin_epoch(self, *, order_id, route_hash, grip_epoch, seg):
        if (not self.approved or route_hash != self.proposal[0] or order_id != 'order-5'
                or type(grip_epoch) is not int or grip_epoch < 1 or type(seg) is not int or seg < 0):
            raise ContractViolation('APPROVED_ROUTE_EPOCH_REQUIRED')
        if self.key is not None and (grip_epoch, seg) <= self.key[2:]:
            raise ContractViolation('NEW_GRIP_EPOCH_OR_SEGMENT_REQUIRED')
        self.key = (order_id, route_hash, grip_epoch, seg)
        self.votes = {}

    def vote(self, rid, kind, key, *, response_id, model_response_ids):
        if rid not in ('r1', 'r2') or kind not in ('GO', 'ACK') or tuple(key) != self.key or response_id not in model_response_ids:
            raise ContractViolation('MATCHING_CURRENT_MODEL_GO_ACK_REQUIRED')
        self._bind_response(response_id, (rid,'vote',self.key))
        self.votes.setdefault(rid, set()).add(kind)

    @property
    def ready(self):
        return self.approved and all(self.votes.get(r) == {'GO', 'ACK'} for r in ('r1', 'r2'))


def vocabulary():
    return Vocabulary(items=frozenset(('order-5','long_beam')), zones=frozenset(('B',)),
        roles=frozenset(('end_neg','end_pos')), passages=frozenset(), location_refs=frozenset(('B',)))


def s3_inputs(route, *, rid, now, observed):
    """Three legacy leak paths share one validated own-coordinate snapshot."""
    route = validate_route(route, rid, now, observed)
    return {'schema': SCHEMA, 'planner': route,
            'guard': {'frame': route['own_map']['frame'], 'walls': copy.deepcopy(route['own_map']['walls']),
                      'pose': copy.deepcopy(route['own_map']['pose'])},
            'provider': copy.deepcopy(route['own_map']), 'transport_admitted': False}


def peer_s3_inputs(report, *, own_map, rid, now, observed, received_reports):
    """r2 may use r1's B report without claiming it saw B itself.

    The receive adapter pins the complete decoded report hash at delivery.
    Alignment is computed ONLY from two RGB estimates of the same beam, each
    in its own start frame; a host/world transform cannot enter this schema.
    """
    closed(report, ('schema','sender','recipient','message_id','route','beam_alignment'), 'PEER_ROUTE')
    if report['schema'] != 'ugrp.e2e_peer_route.v1' or report['sender'] != 'r1' or report['recipient'] != rid or rid != 'r2':
        raise ContractViolation('R1_TO_R2_RECEIVED_ROUTE_REQUIRED')
    receipt = received_reports.get(report['message_id'])
    closed(receipt, ('report_sha256','delivered_at_sim_s'), 'PEER_ROUTE_RECEIPT')
    if (receipt['report_sha256'] != digest(report) or type(receipt['delivered_at_sim_s']) not in (int,float)
            or not 0 <= receipt['delivered_at_sim_s'] <= now):
        raise ContractViolation('RECEIVED_REPORT_BYTES_AND_TIME_REQUIRED')
    local = validate_map(own_map, rid, now, observed)
    alignment = report['beam_alignment']
    closed(alignment, ('beam_ref','own_rgb','peer_rgb','own_beam_pose','peer_beam_pose','covariance'), 'BEAM_ALIGNMENT')
    if alignment['beam_ref'] != 'shared_visual_beam':
        raise ContractViolation('COMMON_VISUAL_BEAM_REQUIRED')
    rgb_ref(alignment['own_rgb'],rid,now,observed)
    # These are received SOURCE REFERENCES, never a peer image attachment.
    peer = report['route']
    peer_refs = peer['own_map']['sources']
    remote = validate_route(peer,'r1',receipt['delivered_at_sim_s'],peer_refs)
    rgb_ref(alignment['peer_rgb'],'r1',receipt['delivered_at_sim_s'],peer_refs)
    for key in ('own_beam_pose','peer_beam_pose'): numbers(alignment[key],3,'RGB_BEAM_POSE')
    covariance = alignment['covariance']
    if not isinstance(covariance,list) or len(covariance)!=3:
        raise ContractViolation('BEAM_ALIGNMENT_COVARIANCE_REQUIRED')
    for row in covariance:numbers(row,3,'BEAM_COVARIANCE')
    import numpy as np
    cov=np.asarray(covariance)
    if not np.allclose(cov,cov.T) or np.linalg.eigvalsh(cov).min() < -1e-10:
        raise ContractViolation('BEAM_ALIGNMENT_COVARIANCE_REQUIRED')
    ax,ay,atheta=alignment['own_beam_pose'];bx,by,btheta=alignment['peer_beam_pose']
    theta=math.atan2(math.sin(atheta-btheta),math.cos(atheta-btheta))
    c,s=math.cos(theta),math.sin(theta)
    translation=[ax-c*bx+s*by,ay-s*bx-c*by]
    waypoints=[[translation[0]+c*x-s*y,translation[1]+s*x+c*y] for x,y in remote['waypoints']]
    result={'schema':SCHEMA,'planner':{'frame':rid+'/own_start','waypoints':waypoints,
        'received_route_hash':remote['route_hash'],'peer_report':copy.deepcopy(report),
        'peer_to_own_from_rgb_beam':{'translation':translation,'yaw':theta,'covariance':copy.deepcopy(covariance)}},
        'guard':{'frame':local['frame'],'walls':copy.deepcopy(local['walls']),'pose':copy.deepcopy(local['pose'])},
        'provider':local,'transport_admitted':False}
    scan(result)
    return result


@dataclass(frozen=True)
class Inputs:
    """S4 parser/ledger compatible input; only the own wrist image is attached."""
    data: dict
    wrist_jpeg: bytes
    seed: int
    arm: str

    def __post_init__(self):
        data = copy.deepcopy(self.data)
        scan(data)
        object.__setattr__(self, 'data', data)
        object.__setattr__(self, '_sealed_digest', digest(data))

    @property
    def request_id(self): return self.data['request_id']
    @property
    def robot_id(self): return self.data['robot_id']
    @property
    def condition(self): return self.data['condition']
    @property
    def sim_time_s(self): return self.data['sim_time_s']
    @property
    def payload(self): return pk.freeze(self.data)
    @property
    def payload_sha256(self): return digest(self.data)
    @property
    def inbox(self): return tuple(self.data['peer_reports'])
    def payload_dict(self): return copy.deepcopy(self.data)
    def order_ids(self): return ('order-5',)
    def item_ids(self): return ()
    def kinds(self): return ('long_beam',)
    def roles_by_order(self): return {'order-5': ('end_neg', 'end_pos')}
    def passages(self): return ()
    def location_refs(self): return ('B',)
    def vocabulary(self):
        return vocabulary()


def build_inputs(*, rid, now, request_id, frame, own_map, observed, history, inbox, arm, seed,
                 e2e_dialogue_v1='off', dialogue_state=None, own_route=None):
    if hashlib.sha256(frame.jpeg).hexdigest() != frame.sha256 or frame.t > now:
        raise ContractViolation('OWN_FRAME_BYTES_OR_TIME_MISMATCH')
    current = {'robot_id': rid, 'frame_id': frame.index, 't_sim': frame.t, 'sha256': frame.sha256}
    rgb_ref(current, rid, now, observed)
    mapped = validate_map(own_map, rid, now, observed)
    # Use the existing closed command/inbox validators; no arbitrary dictionary
    # may be smuggled in through a supposedly own command or delivered envelope.
    from harness.zone_study_contract import _history_hits, _inbox_hits, condition, forbidden_key_hits
    errors = _history_hits({'own_command_history': history}, now)
    # Vocabulary derives only from the fixed task; no static location IDs.
    dialogue_on = enabled(e2e_dialogue_v1)
    checked_inbox = inbox
    if dialogue_on:
        from harness.e2e_dialogue import legacy_inbox
        checked_inbox = legacy_inbox(inbox)
    minimal = {'robot_id': rid, 'inbox': checked_inbox, 'order_sheet': {'orders': TASK['orders']}}
    errors += _inbox_hits(minimal, condition('peer_ko' if arm=='peer_nl' else arm), seed, now)
    errors += forbidden_key_hits(history)
    if errors: raise ContractViolation('; '.join(errors))
    data = {'schema': SCHEMA, 'robot_id': rid, 'request_id': request_id, 'condition': arm,
            'sim_time_s': now, 'task': copy.deepcopy(TASK), 'own_rgb': current,
            'own_map': mapped, 'own_command_history': copy.deepcopy(history),
            'peer_reports': copy.deepcopy(inbox), 'channel': channel_section('peer_ko' if arm=='peer_nl' else arm,rid,seed)}
    if dialogue_on:
        data['dialogue'] = copy.deepcopy(dialogue_state)
        proposal = None
        if own_route is not None:
            from harness.e2e_dialogue import wire_route
            if rid != 'r1' or validate_route(own_route,rid,now,observed)['own_map'] != mapped:
                raise ContractViolation('OWN_ROUTE_CAPTURED_MAP_REQUIRED')
            proposal = dict(kind='OwnRoute',route=wire_route(own_route),source_message_id=None)
        data['own_route_proposal'] = proposal
    scan(data)
    return Inputs(data, frame.jpeg, seed, arm)


def build_request(inputs, *, window=None):
    scan(inputs.data)
    if digest(inputs.data) != inputs._sealed_digest:
        raise ContractViolation('OWN_PAYLOAD_MUTATED_AFTER_VALIDATION')
    parts = pk.prompt_parts('peer_ko' if inputs.arm=='peer_nl' else inputs.arm, inputs.robot_id, seed=inputs.seed)
    system = '\n\n'.join((
        '당신은 로봇 '+inputs.robot_id+'입니다. r1/r2는 빔 하나를 운반하고 r3는 idle입니다. '
        'task의 종류·인원·B 시각 설명, 자기 wrist RGB·자기 명령·own_map과 실제 수신 peer_reports만 사용합니다. '
        '좌표계는 자기 시작 차체 기준입니다. 수신 보고는 자기 관측과 구분합니다. '
        'B 관측 경로의 제안·수신 승인 뒤에만 claim하며, 현재 order_id·route_hash·grip_epoch·seg의 양쪽 GO/ACK이 필요합니다.',
        parts['channel'], pk.KO_OUTPUT_HEAD,
        'action은 claim(order_id,role,destination_zone), continue, release(order_id), look_around 중 하나입니다. '
        'decision_sources는 order_sheet, own_rgb, own_commands, own_belief, message 중 실제 쓴 것만 적습니다. '
        'own_map은 own_belief로 표시합니다.', parts['messages'], parts['language']))
    if 'dialogue' in inputs.data:
        from harness.e2e_dialogue import PROMPT
        system += '\n\n' + PROMPT
    body = inputs.payload_dict()
    if window is not None:
        closed(window, ('window_id','max_utterances','max_your_utterances','your_utterances_left','received','sent'), 'DIALOGUE_WINDOW')
        if window['received'] != list(inputs.inbox):
            raise ContractViolation('DIALOGUE_INBOX_MISMATCH')
        if any(type(window[k]) is not int or window[k] < 0 for k in ('max_utterances','max_your_utterances','your_utterances_left')):
            raise ContractViolation('DIALOGUE_CAP_REQUIRED')
        body[pk.WINDOW_KEY] = {k:copy.deepcopy(v) for k,v in window.items() if k != 'received'}
    scan(body)
    user = json.dumps(body, ensure_ascii=False, sort_keys=True)
    image = {'label': 'own_wrist_rgb', 'image': pk._uri(inputs.wrist_jpeg)}
    sha = hashlib.sha256(inputs.wrist_jpeg).hexdigest()
    refs = [{'label': image['label'], 'ref': f'own-{inputs.robot_id}-{inputs.data["own_rgb"]["frame_id"]}', 'sha256': sha, 'bytes_sha256': sha, 'captured_at_sim_s': inputs.data['own_rgb']['t_sim']}]
    tokens = pk.request_tokens(system, user, [image])
    from harness import pair_llm_billing as billing
    request = {'schema': SCHEMA, 'condition': inputs.arm, 'actor': inputs.robot_id, 'prompt_role': 'peer', 'protocol_version': pk.zp.PROTOCOL_VERSION, 'input_profile_id': SCHEMA,
        'request_id': body['request_id'], 'prompt_version': SCHEMA, 'payload_schema': SCHEMA,
        'input_sha256': inputs.payload_sha256, 'messages': [{'role':'system','content':system},{'role':'user','content':user}],
        'images': [image], 'image_refs': refs, 'tokens': tokens,
        'billed_tokens': billing.billed_tokens(tokens, system_billed=pk.count_tokens(system)),
        'request_sha256': pk.request_digest_from_refs(system,user,refs)}
    return request
