"""Default-off e2e4a dialogue admission; no executor, simulator or model calls.

Typed OwnRoute bytes travel INSIDE the existing costed condition envelope.
This opt-in wire extends the structured schema; it is not a historical baseline.
Only the scheduler's committed deliveries and released responses change state.
"""
import copy
from dataclasses import dataclass, replace

from harness import e2e_own_inputs as own
from harness import pair_llm_dispatch as pair
from harness import zone_study_protocol as zp
from harness.zone_final_pair_binding import bind
from harness.zone_sim_cost import Attempt, call_cost
from harness.zone_study_contract import ContractViolation, digest, leader_for_seed

SCHEMA = 'ugrp.e2e_dialogue.v1'
WINDOW_S = 10.
EPOCH_WINDOW_S = 20.
SIGNAL_DELAY_S = .1
PAIR = ('r1', 'r2')
PROMPT = '''e2e_dialogue_v1: 경로·claim·운반 허가만 검사하며 실제 모션은 아직 연결되지 않았습니다.
r1은 자기 지도 어댑터의 own_route_proposal을 그대로 메시지 contract로 복사하여 제안합니다:
{"kind":"OwnRoute","route":OwnRoute,"source_message_id":null}.
OwnRoute는 schema=ugrp.e2e_route_message.v1, robot_id=r1, frame_id, map_version,
B_rgb_sources, waypoints, route_hash를 가집니다. 해시는 어댑터가 만들며 모델이 계산하거나 경로를 고치지 않습니다.
peer_ko는 한국어 설명+contract, structured는 기존 정형 message+contract(자유문장 금지)를 씁니다.
leader_ko는 기존 지휘자 경유만 허용합니다. 지휘자는 실제 수신 contract의 route를 그대로 전달하고
source_message_id에 받은 message_id를 씁니다. r2만 승인합니다. r3는 운반 idle이나 지휘자이면 중계합니다.
no_comm은 messages=[]이며 B 경로 전달·r2 승인·claim이 열리지 않습니다.
수신 후 action={"kind":"approve_route","route_hash":해시,"proposal_message_id":수신ID}로 승인합니다.
이후 기존 claim을 각자 선택합니다. 현재 dialogue.key가 있을 때만
action={"kind":"route_vote","choice":"GO"|"ACK","order_id":"order-5","route_hash":해시,
"grip_epoch":현재값,"seg":현재값,"peer_go_ref":null|상대GO요청ID}를 씁니다.
ACK는 요청에 보인 상대 GO를 확인하며 GO는 자기 RGB가 필요합니다. 승인에는 message 출처가 필요합니다.
재파지·새 구간은 양쪽의 새 GO/ACK가 필요합니다. 이전 요청·epoch 응답을 재사용하지 마십시오.
무효 GO/ACK의 정상 응답만 같은 epoch에서 로봇당 한 번 새 영상으로 재질의합니다.'''


def route_contract(value):
    own.closed(value, ('kind', 'route', 'source_message_id'), 'OWN_ROUTE_MESSAGE')
    if value['kind'] != 'OwnRoute' or (value['source_message_id'] is not None
            and not zp.is_message_id(value['source_message_id'])):
        raise ContractViolation('OWN_ROUTE_MESSAGE_ID_REQUIRED')
    route = value['route']
    own.closed(route, ('schema','robot_id','frame_id','map_version','B_rgb_sources','waypoints','route_hash'), 'WIRE_OWN_ROUTE')
    if (route['schema'] != 'ugrp.e2e_route_message.v1' or route['robot_id'] != 'r1'
            or type(route['map_version']) is not int or route['map_version'] < 0
            or type(route['frame_id']) is not int or route['frame_id'] < 0
            or not isinstance(route['B_rgb_sources'],list) or not route['B_rgb_sources']
            or not isinstance(route['waypoints'],list) or len(route['waypoints']) < 2):
        raise ContractViolation('B_RGB_WAYPOINTS_REQUIRED')
    for ref in route['B_rgb_sources']:
        own.rgb_ref(ref, 'r1', ref['t_sim'], route['B_rgb_sources'])
    for xy in route['waypoints']:
        own.numbers(xy,2,'WAYPOINT')
    if route['route_hash'] != digest({k:v for k,v in route.items() if k != 'route_hash'}):
        raise ContractViolation('ROUTE_HASH_MISMATCH')
    own.scan(route)
    if len(route['waypoints']) > 64 or len(str(value).encode()) > 32768:
        raise ContractViolation('OWN_ROUTE_MESSAGE_SIZE_LIMIT')
    return copy.deepcopy(value)


def wire_route(route):
    """Small wire projection; the sender's entire own map is not retransmitted."""
    value = {k:copy.deepcopy(route[k]) for k in ('robot_id','frame_id','map_version','B_rgb_sources','waypoints')}
    value['schema'] = 'ugrp.e2e_route_message.v1'
    value['route_hash'] = digest(value)
    return value


def legacy_inbox(inbox):
    """Validate typed bytes separately, retaining the sealed envelope checks."""
    result = copy.deepcopy(inbox)
    for envelope in result or ():
        contract = envelope.get('body', {}).pop('contract', None)
        if contract is not None:
            route_contract(contract)
    return result


@dataclass(frozen=True)
class Envelope:
    base: object
    contract: dict

    def __getattr__(self, name):
        return getattr(self.base, name)

    def body(self):
        return {**self.base.body(), 'contract': copy.deepcopy(self.contract)}

    def record(self, **kwargs):
        return {**self.base.record(**kwargs), 'body': self.body()}


class Transport(zp.Transport):
    def send(self, sender, *, contract=None, **kwargs):
        if contract is not None:
            contract = route_contract(contract)
        receipt = super().send(sender, **kwargs)
        if receipt.accepted and contract is not None:
            if self.delivery_owner is None:
                raise ContractViolation('E2E_REQUIRES_SCHEDULER_DELIVERY_OWNER')
            envelope = Envelope(receipt.envelope, contract)
            self.pending[envelope.message_id] = envelope
            receipt = replace(receipt, envelope=envelope)
        return receipt


class Dialogue:
    def __init__(self, trial):
        self.trial = trial
        self.captures, self.origins, self.received, self.outgoing_by_call = {}, {}, {}, {}
        self.proposal = None
        self.approved, self.claims, self.votes = False, set(), {}
        self.key, self.opened = None, None
        self.last_epoch = None
        self.latest_origin = None
        self.events, self.retry_events = [], []
        self.retry_used, self.examined, self.used_responses = set(), set(), set()

    def capture(self, call, state, frame, inbox):
        view = self.view(call.actor, call.started_sim_s)
        self.captures[call.call_id] = copy.deepcopy(dict(actor=call.actor, requested_at=call.started_sim_s,
            frame_t=frame.t, state=state, inbox=inbox, view=view))
        return view

    def view(self, actor, now):
        visible = actor == 'r1' or (actor == 'r2' and self.proposal is not None)
        peer = next((v for r, v in self.votes.items() if r != actor and 'GO' in v
                     and v['GO']['at'] + SIGNAL_DELAY_S <= now), None)
        return dict(schema=SCHEMA, proposal_message_id=self.proposal['message_id'] if visible and self.proposal else None,
            route_hash=self.proposal['route']['route_hash'] if visible and self.proposal else None,
            approved=bool(visible and self.approved), own_claim=actor in self.claims,
            key=list(self.key) if visible and self.key else None,
            own_go_sent='GO' in self.votes.get(actor, {}), own_ack_sent='ACK' in self.votes.get(actor, {}),
            peer_go_ref=peer['GO']['call_id'] if visible and peer else None,
            transport_admitted=bool(visible and self.allowed(self.key, now)), motion_connected=False)

    def fresh(self, context, now):
        return context['frame_t'] <= context['requested_at'] <= now < context['frame_t'] + WINDOW_S

    def outgoing(self, contract, context):
        contract = route_contract(contract)
        actor, source = context['actor'], contract['source_message_id']
        if source is None:
            mapped = context['state']['own_map'];route = contract['route']
            planned = context['state'].get('own_route')
            if planned is None:
                raise ContractViolation('E2E_OWN_ROUTE_ADAPTER_REQUIRED')
            own.validate_route(planned,actor,context['requested_at'],context['state']['observed_rgb'])
            if (actor != 'r1' or route['map_version'] != mapped['map_version'] or mapped['goal'] is None
                    or route['B_rgb_sources'] != mapped['goal']['sources']
                    or route['frame_id'] != max(r['frame_id'] for r in mapped['sources'])
                    or planned['own_map'] != mapped or route != wire_route(planned)):
                raise ContractViolation('R1_CAPTURED_OWN_MAP_ROUTE_REQUIRED')
            own.validate_map(mapped,actor,context['requested_at'],context['state']['observed_rgb'])
            for ref in route['B_rgb_sources']:
                own.rgb_ref(ref,actor,context['requested_at'],context['state']['observed_rgb'])
        else:
            if self.trial.arm != 'leader_ko' or actor != leader_for_seed('leader_ko', self.trial.seed):
                raise ContractViolation('ONLY_LEADER_MAY_FORWARD_OWN_ROUTE')
            message = next((e for e in context['inbox'] or () if e['message_id'] == source), None)
            previous = message.get('body', {}).get('contract') if message else None
            if not previous or previous['route'] != contract['route'] or (source, actor) not in self.received:
                raise ContractViolation('RECEIVED_UNCHANGED_ROUTE_REQUIRED')
        return contract

    def relay(self, transport, actor, value, *, at_sim_s, call_id):
        receipts = []
        for message in value['messages']:
            contract = message.get('contract')
            receipt = transport.send(actor, recipients=message['recipients'], text=message.get('text'),
                structured=message.get('message'), reply_to=message['reply_to'], at_sim_s=at_sim_s, contract=contract)
            receipts.append(receipt)
            if receipt.accepted and contract is not None:
                source = contract['source_message_id']
                origin = self.origins[source] if source else receipt.envelope.message_id
                self.origins[receipt.envelope.message_id] = origin
                if source is None:
                    self.outgoing_by_call[call_id] = origin
        return tuple(receipts)

    def receive(self, actor, envelope, now):
        contract = envelope['body'].get('contract')
        if contract is None:
            return
        # Callback is downstream of commit_delivery; exact delivered bytes required.
        if envelope not in self.trial.channel.inbox(actor, now_sim_s=now):
            raise ContractViolation('ACTUAL_COMMITTED_ROUTE_DELIVERY_REQUIRED')
        message_id = envelope['message_id']
        self.received[(message_id, actor)] = copy.deepcopy(envelope)
        origin = self.origins[message_id]
        if actor == 'r2' and origin == self.latest_origin:
            if self.proposal is None or self.proposal['origin'] != origin:
                self.proposal = dict(message_id=message_id, origin=origin, route=copy.deepcopy(contract['route']))
                self.approved, self.claims, self.votes, self.key = False, set(), {}, None
        self.events.append(dict(kind='route_received', robot_id=actor, message_id=message_id,
                                route_hash=contract['route']['route_hash'], at=now))

    def begin_epoch(self, *, order_id, route_hash, grip_epoch, seg, now):
        if (not self.approved or self.claims != set(PAIR) or order_id != 'order-5'
                or route_hash != self.proposal['route']['route_hash'] or type(grip_epoch) is not int
                or grip_epoch < 1 or type(seg) is not int or seg < 0):
            raise ContractViolation('APPROVED_CLAIMED_ROUTE_EPOCH_REQUIRED')
        epoch = (grip_epoch, seg)
        if self.last_epoch is not None and epoch <= self.last_epoch:
            raise ContractViolation('NEW_GRIP_EPOCH_OR_SEGMENT_REQUIRED')
        if type(now) not in (int, float) or not 0 <= now < float('inf'):
            raise ContractViolation('CAUSAL_EPOCH_CLOCK_REQUIRED')
        self.key = (order_id, route_hash, grip_epoch, seg)
        self.last_epoch, self.opened, self.votes = epoch, now, {}
        self.events.append(dict(kind='epoch_open', key=list(self.key), at=now))

    def check_action(self, action, context, now):
        kind, actor = action['kind'], context['actor']
        if kind == 'continue':
            return
        if not self.fresh(context, now):
            raise ContractViolation('STALE_OWN_RGB_RESPONSE')
        if actor not in PAIR or self.proposal is None:
            raise ContractViolation('RECEIVED_B_ROUTE_REQUIRED')
        if kind == 'approve_route':
            own.closed(action, ('kind', 'route_hash', 'proposal_message_id'), 'ROUTE_APPROVAL')
            message_id = action['proposal_message_id']
            if (actor != 'r2' or message_id != self.proposal['message_id']
                    or action['route_hash'] != self.proposal['route']['route_hash']
                    or not any(e['message_id'] == message_id for e in context['inbox'] or ())):
                raise ContractViolation('CAPTURED_RECEIVED_R2_APPROVAL_REQUIRED')
        elif kind == 'claim':
            if (not self.approved or not context['view']['approved'] or actor in self.claims
                    or action['order_id'] != 'order-5' or action['destination_zone'] != 'B'
                    or action['role'] != own.TASK['fixed_roles'][actor]
                    or context['view']['route_hash'] != self.proposal['route']['route_hash']):
                raise ContractViolation('CURRENT_APPROVED_OWN_ROLE_CLAIM_REQUIRED')
        elif kind == 'route_vote':
            own.closed(action, ('kind', 'choice', 'order_id', 'route_hash', 'grip_epoch', 'seg', 'peer_go_ref'), 'ROUTE_VOTE')
            key = tuple(action[k] for k in ('order_id', 'route_hash', 'grip_epoch', 'seg'))
            choice = action['choice']
            if (choice not in ('GO', 'ACK') or type(action['grip_epoch']) is not int
                    or type(action['seg']) is not int or key != self.key
                    or list(key) != context['view']['key'] or context['requested_at'] < self.opened
                    or now >= self.opened + EPOCH_WINDOW_S or choice in self.votes.get(actor, {})):
                raise ContractViolation('MATCHING_CURRENT_GO_ACK_REQUIRED')
            if choice == 'ACK':
                peer = next((v['GO'] for r, v in self.votes.items() if r != actor and 'GO' in v), None)
                if ('GO' not in self.votes.get(actor, {}) or not peer or action['peer_go_ref'] != peer['call_id']
                        or action['peer_go_ref'] != context['view']['peer_go_ref']):
                    raise ContractViolation('CAPTURED_PEER_GO_REQUIRED')
            elif action['peer_go_ref'] is not None:
                raise ContractViolation('GO_HAS_NO_ACK_REFERENCE')
        else:
            raise ContractViolation('E2E_DIALOGUE_ACTION_NOT_CONNECTED')

    def apply(self, call_id, action, now):
        context = self.captures[call_id]
        self.check_action(action, context, now)
        if call_id in self.used_responses:
            raise ContractViolation('MODEL_RESPONSE_ALREADY_RELEASED')
        self.used_responses.add(call_id)
        actor, kind = context['actor'], action['kind']
        if call_id in self.outgoing_by_call:
            self.latest_origin = self.outgoing_by_call[call_id]
            self.proposal, self.approved, self.key = None, False, None
            self.claims, self.votes = set(), {}
        if kind == 'approve_route':
            self.approved = True
        elif kind == 'claim':
            self.claims.add(actor)
        elif kind == 'route_vote':
            self.votes.setdefault(actor, {})[action['choice']] = dict(call_id=call_id, at=now, frame_t=context['frame_t'])
        self.events.append(dict(kind=kind, robot_id=actor, call_id=call_id, at=now, action=copy.deepcopy(action)))

    def allowed(self, key, now):
        return bool(key is not None and tuple(key) == self.key and self.approved and self.claims == set(PAIR)
            and all(set(self.votes.get(r, {})) == {'GO', 'ACK'} for r in PAIR)
            and all(votes['ACK']['at'] <= now < votes['ACK']['frame_t'] + WINDOW_S for votes in self.votes.values()))

    def finish_call(self, trial, call, prepared, raw, **kwargs):
        context = self.captures[call.call_id]
        def validate(value, **checks):
            try:
                value = zp.parse(value) if isinstance(value, str) else copy.deepcopy(value)
                clean = copy.deepcopy(value)
                contracts = [m.pop('contract', None) for m in clean['messages']]
                if sum(c is not None for c in contracts) > 1:
                    raise ContractViolation('ONE_ROUTE_PROPOSAL_PER_RESPONSE')
                special = value['action']['kind'] in ('approve_route', 'route_vote')
                if special:
                    clean['action'] = {'kind': 'continue'}
                checked = pair.validate_reply(clean, **checks)
                checked['action'] = value['action']
                for message, contract in zip(checked['messages'], contracts):
                    if contract is not None:
                        if checked['action']['kind'] != 'continue':
                            raise ContractViolation('ROUTE_PROPOSAL_MUST_PRECEDE_APPROVAL_AND_CLAIM')
                        message['contract'] = self.outgoing(contract, context)
                cost = call_cost((Attempt(outcome='ok', input_tokens=prepared.request['billed_tokens']['total_billed'],
                    output_tokens=trial.sim_output_tokens(raw, len(checked['messages'])),
                    utterances=len(checked['messages'])),), trial.params)
                self.check_action(checked['action'], context, round(call.started_sim_s + cost.sim_s, 6))
                if checked['action']['kind'] == 'approve_route' and 'message' not in checked['decision_sources']:
                    raise ContractViolation('APPROVAL_MESSAGE_SOURCE_REQUIRED')
                if checked['action']['kind'] == 'route_vote' and 'own_rgb' not in checked['decision_sources']:
                    raise ContractViolation('GO_ACK_OWN_RGB_SOURCE_REQUIRED')
                return checked
            except (ContractViolation, KeyError, TypeError, ValueError) as exc:
                raise zp.ProtocolError(str(exc)) from exc
        private_zp = type('Protocol', (), {'relay': lambda transport, actor, value, **kw:
            self.relay(transport, actor, value, call_id=call.call_id, **kw), 'ProtocolError': zp.ProtocolError})
        return bind(pair.PairTrial.finish_call, validate_reply=validate, zp=private_zp)(
            trial, call, prepared, raw, robots=trial.actors, **kwargs)

    def poll_retries(self, now):
        """s4live9 rule: normal invalid response only, once per robot/current key."""
        scheduler = self.trial.scheduler
        for call in scheduler.calls:
            entry = scheduler.ledger[call.call_id]
            if call.call_id in self.examined or entry['status'] == 'outstanding':
                continue
            self.examined.add(call.call_id)
            context = self.captures.get(call.call_id)
            completion = entry.get('completion') or {}
            if (not context or entry['status'] != 'failed' or call.notes.get('send_violation')
                    or completion.get('finish_reason') != 'stop' or context['view']['key'] is None
                    or tuple(context['view']['key']) != self.key or call.actor not in PAIR
                    or context['view']['own_ack_sent']
                    or now >= self.opened + EPOCH_WINDOW_S or self.allowed(self.key, now)):
                continue
            once = (call.actor, self.key)
            if once in self.retry_used:
                continue
            self.retry_used.add(once)
            scheduler.trigger(call.actor, 'idle', at=now)
            self.retry_events.append(dict(robot_id=call.actor, key=list(self.key), invalid_call_id=call.call_id,
                at=now, transport_retry=False, accepted_action_replayed=False))
