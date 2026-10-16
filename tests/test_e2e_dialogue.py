"""Actual S4 scheduler/receipts/parser/ledger; fake wire, no model or physics."""
import copy
import io
import json
from types import SimpleNamespace

import pytest

from harness import e2e_dialogue as dialogue
from harness import e2e_own_inputs as own
from harness import s4_llm_host as s4
from harness.zone_environment_registry import load_scenario, bundle_for
from harness.zone_send_ledger import completion_body
from harness.zone_study_contract import ContractViolation, digest, leader_for_seed
from tests.test_e2e_own_inputs import state, route
from tests.test_pair_llm_s4_host import make_host, setup_data, no_external_work, advance


def notification(arm, target, contract=None, reply_to=None):
    value = dict(recipients=[target], reply_to=reply_to)
    if arm == 'structured':
        value['message'] = dict(act='inform', item='order-5', zone='B', role='end_neg',
            passage=None, location_ref=None, state='unknown', confidence='low', observed_at_sim_s=1., reply_to=reply_to)
    else:
        value['text'] = '자기 영상으로 기억한 목적지의 경로를 제안합니다. 수신한 경로를 확인해 주세요.'
    if contract is not None:
        value['contract'] = copy.deepcopy(contract)
    return value


class Wire:
    def __init__(self, arm, seed, *, fault=None, always=False, finish_reason='stop'):
        self.arm, self.seed, self.fault, self.always = arm, seed, fault, always
        self.finish_reason = finish_reason
        self.requests, self.responses, self.sent, self.faults = [], [], set(), 0

    def __call__(self, request, **kwargs):
        self.requests.append(bytes(request.data))
        body = json.loads(request.data)
        payload = json.loads(next(p['text'] for p in body['messages'][-1]['content'] if p['type'] == 'text'))
        actor = payload['robot_id'];view = payload['dialogue'];inbox = payload['peer_reports'] or []
        action, messages, sources = dict(kind='continue'), [], ['own_rgb', 'own_belief']
        leader = leader_for_seed('leader_ko', self.seed) if self.arm == 'leader_ko' else None
        if actor == 'r1' and actor not in self.sent:
            self.sent.add(actor)
            if self.arm != 'no_comm' and self.fault != 'remove_B_message':
                contract = payload['own_route_proposal']
                if self.fault == 'missing_B_source':contract['route']['B_rgb_sources']=[]
                if self.fault == 'wrong_map_version':contract['route']['map_version']+=1
                if self.fault == 'invented_path':contract['route']['waypoints'][1]=[4.6,-2.1]
                if self.fault in ('missing_B_source','wrong_map_version','invented_path'):
                    contract['route']['route_hash']=digest({k:v for k,v in contract['route'].items() if k!='route_hash'})
                messages = [notification(self.arm, leader if leader == 'r3' else 'r2', contract)]
        elif actor == 'r3' and leader == actor and inbox and actor not in self.sent:
            source = next((e for e in inbox if 'contract' in e['body']), None)
            if source:
                self.sent.add(actor);contract = copy.deepcopy(source['body']['contract'])
                contract['source_message_id'] = source['message_id']
                messages = [notification(self.arm, 'r2', contract)]
        elif actor == 'r2' and view['proposal_message_id'] and not view['approved']:
            action = dict(kind='approve_route', route_hash=view['route_hash'], proposal_message_id=view['proposal_message_id'])
            sources += ['message']
            if self.fault == 'unreceived_approval':action['proposal_message_id'] = 'missing'
        elif actor in dialogue.PAIR and view['approved'] and not view['own_claim']:
            action = dict(kind='claim', order_id='order-5', destination_zone='B', role=own.TASK['fixed_roles'][actor])
        elif actor in dialogue.PAIR and view['key']:
            choice = 'GO' if not view['own_go_sent'] else 'ACK' if view['peer_go_ref'] and not view['own_ack_sent'] else None
            if choice:
                action = dict(kind='route_vote', choice=choice, **dict(zip(
                    ('order_id', 'route_hash', 'grip_epoch', 'seg'), view['key'])),
                    peer_go_ref=view['peer_go_ref'] if choice == 'ACK' else None)
                if actor == 'r1' and choice == 'ACK' and self.fault == 'invalid_ack' and (not self.faults or self.always):
                    self.faults += 1;action['route_hash'] = 'f'*64
        raw = json.dumps(dict(request_id=payload['request_id'], action=action, decision_sources=sources, messages=messages))
        reply = json.loads(completion_body(raw, usage={'prompt_tokens':3100,'completion_tokens':70,'total_tokens':3170}, model='fixture-model'))
        reply['choices'][0]['finish_reason'] = self.finish_reason
        encoded = json.dumps(reply).encode();self.responses.append(encoded)
        return io.BytesIO(encoded)


def build(tmp_path, setup_data, arm='peer_ko', seed=61001, **kwargs):
    wire = Wire(arm, seed, **kwargs)
    legacy, inner, _, budget = make_host(tmp_path, setup_data, arm=arm, wire=wire)
    scenario = load_scenario('e2e_one_beam_ownmap')
    from harness import pair_llm_contract, pair_llm_live
    ledger = pair_llm_live.PairLiveLedger(store_dir=tmp_path/'own-wire',budget=budget,run_key='s4-fixture-run',
        profile=pair_llm_contract.driver_profile(),wire=wire,pacer=SimpleNamespace(wait=lambda:None))
    adapter = SimpleNamespace(client_factory=legacy.trial.client_factory, send_ledger=ledger)
    for rid, link in inner.items():
        mapped, refs, _ = state(rid)
        # References must match the own bytes actually captured by the stub.
        refs[0]['sha256'] = link.sha
        if rid != 'r1':mapped['goal'] = None
        planned = None
        if rid == 'r1':
            planned,_ = route();planned['own_map']=mapped;planned['B_rgb_sources']=refs
            planned['route_hash']=digest({k:v for k,v in planned.items() if k!='route_hash'})
        link.own_inputs_at = lambda now,m=mapped,r=refs,s=link.sha,rid=rid,p=planned:dict(own_map=m,
            observed_rgb=r+[dict(robot_id=rid,frame_id=int(now*10),t_sim=now,sha256=s)],own_route=p)
    host = s4.Host(scenario, condition=arm, links=legacy.links, seed=seed, map_bundle=bundle_for(scenario),
        model_adapter=adapter, e2e_own_inputs_v1='on_v1', e2e_dialogue_v1='on_v1')
    host.begin(1.)
    return host, inner, wire


def trigger(host, inner, actors, now):
    for actor in actors:host.trial.scheduler.trigger(actor, 'idle', at=now)
    advance(host, inner, now, now+4)


def claim_phase(host, inner):
    advance(host, inner, 1, 11)
    for t in (11, 15, 19, 23):trigger(host, inner, dialogue.PAIR, t)


@pytest.mark.parametrize('arm,seed', [('peer_ko',61001),('structured',61001),('leader_ko',61002),
                                     ('leader_ko',61000),('leader_ko',61001),('no_comm',61001)])
def test_actual_condition_deliveries_approval_claim_and_epoch(tmp_path, setup_data, arm, seed):
    host, inner, wire = build(tmp_path, setup_data, arm, seed)
    claim_phase(host, inner)
    gate = host.trial.dialogue
    assert all(not link.calls for link in inner.values())
    if arm == 'no_comm':
        assert not gate.approved and not gate.claims and not gate.received
        assert all(json.loads(r['user'])['peer_reports'] is None for r in host.trial.requests)
        return
    assert gate.approved and gate.claims == set(dialogue.PAIR), str([(r['robot'],r['status'],r.get('error')) for r in host.trial.requests])+str(gate.events)
    assert gate.proposal['route']['B_rgb_sources'][0]['robot_id'] == 'r1'
    if arm == 'leader_ko' and seed % 3 == 2:
        assert {(e['robot_id']) for e in gate.events if e['kind']=='route_received'} == {'r2','r3'}
        assert gate.origins[gate.proposal['message_id']] != gate.proposal['message_id']
    h = gate.proposal['route']['route_hash']
    t = host.trial.scheduler.clock
    gate.begin_epoch(order_id='order-5', route_hash=h, grip_epoch=1, seg=0, now=t)
    trigger(host, inner, dialogue.PAIR, t)
    assert not gate.allowed(gate.key,t+4)
    trigger(host, inner, dialogue.PAIR, t+4)
    assert gate.allowed(gate.key,t+8), (gate.votes,[(r['status'],r.get('error')) for r in host.trial.requests])
    old = gate.key
    gate.begin_epoch(order_id='order-5', route_hash=h, grip_epoch=2, seg=0, now=t+8)
    assert not gate.allowed(old,t+8) and not gate.allowed(gate.key,t+8)
    trigger(host, inner, dialogue.PAIR,t+8)
    trigger(host, inner, dialogue.PAIR,t+12)
    assert gate.allowed(gate.key,t+16)
    host.save(tmp_path/'evidence')
    saved = json.loads((tmp_path/'evidence/dialogue.json').read_text())
    assert saved['events'] and saved['motion_connected'] is False
    assert len(wire.requests) == len(host.trial.send_ledger.entries)
    assert all(not link.calls for link in inner.values())


@pytest.mark.parametrize('fault', ['remove_B_message','unreceived_approval','missing_B_source','wrong_map_version','invented_path'])
def test_removed_B_or_unreceived_approval_never_claims(tmp_path, setup_data, fault):
    host, inner, _ = build(tmp_path, setup_data, fault=fault)
    claim_phase(host, inner)
    gate = host.trial.dialogue
    assert not gate.approved and not gate.claims and not gate.allowed(gate.key,20.)
    assert all(not link.calls for link in inner.values())


@pytest.mark.parametrize('fault', ['old_epoch','relabeled_old_response','stale','wrong_order','wrong_route','wrong_seg','ack_without_GO'])
def test_invalid_transition_with_real_captured_request(tmp_path, setup_data, fault):
    host, inner, _ = build(tmp_path, setup_data)
    claim_phase(host, inner);gate = host.trial.dialogue;h = gate.proposal['route']['route_hash']
    t = host.trial.scheduler.clock
    gate.begin_epoch(order_id='order-5', route_hash=h, grip_epoch=1, seg=0, now=t)
    call = SimpleNamespace(call_id='held-r1',actor='r1',started_sim_s=t)
    frame = inner['r1'].frame_at(t)
    gate.capture(call,inner['r1'].own_inputs_at(t),frame,[])
    action = dict(kind='route_vote',choice='GO',order_id='order-5',route_hash=h,grip_epoch=1,seg=0,peer_go_ref=None)
    now = t+.5
    if fault in ('old_epoch','relabeled_old_response'):
        gate.begin_epoch(order_id='order-5',route_hash=h,grip_epoch=2,seg=0,now=t+.1)
        if fault=='relabeled_old_response':action['grip_epoch']=2
    elif fault=='stale':now=t+10
    elif fault=='wrong_order':action['order_id']='order-1'
    elif fault=='wrong_route':action['route_hash']='f'*64
    elif fault=='wrong_seg':action['seg']=1
    else:action['choice']='ACK';action['peer_go_ref']='imagined'
    with pytest.raises(ContractViolation):gate.apply(call.call_id,action,now)
    assert not gate.votes and not gate.allowed(gate.key,now)


@pytest.mark.parametrize('always,permits', [(False,True),(True,False)])
def test_invalid_normal_ack_reasks_once_fresh_without_motion(tmp_path, setup_data, always, permits):
    host, inner, wire = build(tmp_path,setup_data,fault='invalid_ack',always=always)
    claim_phase(host,inner);gate=host.trial.dialogue;h=gate.proposal['route']['route_hash']
    t = host.trial.scheduler.clock
    gate.begin_epoch(order_id='order-5',route_hash=h,grip_epoch=1,seg=0,now=t)
    trigger(host,inner,dialogue.PAIR,t)
    trigger(host,inner,dialogue.PAIR,t+4)
    advance(host,inner,t+8,t+13)
    assert gate.allowed(gate.key,t+13) is permits
    assert len(gate.retry_events)==1 and wire.faults==(2 if always else 1)
    event=gate.retry_events[0];old=gate.captures[event['invalid_call_id']]
    fresh=[c for c in gate.captures.values() if c['actor']=='r1' and c['requested_at']>=event['at']]
    assert fresh and all(c['frame_t']>old['frame_t'] for c in fresh)
    assert all(not link.calls for link in inner.values())


def test_toggle_default_off_requires_own_inputs(tmp_path,setup_data):
    host, _, _, _ = make_host(tmp_path,setup_data)
    assert host.trial.dialogue is None and host.trial.e2e_dialogue_v1=='off'
    with pytest.raises(ContractViolation,match='REQUIRES_OWN'):
        s4.Trial(setup_data[0],arm='peer_ko',links=host.links,seed=601,horizon_s=120,
            map_bundle=setup_data[1],model_adapter=SimpleNamespace(
                client_factory=host.trial.client_factory,send_ledger=host.trial.send_ledger),e2e_dialogue_v1='on_v1')


@pytest.mark.parametrize('finish_reason',['length','content_filter'])
def test_non_normal_completion_never_votes_or_reasks(tmp_path,setup_data,finish_reason):
    host,inner,wire=build(tmp_path,setup_data)
    claim_phase(host,inner);gate=host.trial.dialogue;t=host.trial.scheduler.clock
    gate.begin_epoch(order_id='order-5',route_hash=gate.proposal['route']['route_hash'],grip_epoch=1,seg=0,now=t)
    wire.finish_reason=finish_reason
    trigger(host,inner,dialogue.PAIR,t)
    advance(host,inner,t+4,t+8)
    assert not gate.votes and not gate.retry_events and not gate.allowed(gate.key,t+8)
    assert all(not link.calls for link in inner.values())


def test_uncommitted_tampered_route_and_replayed_response_are_rejected(tmp_path,setup_data):
    host,inner,_=build(tmp_path,setup_data)
    claim_phase(host,inner);gate=host.trial.dialogue;t=host.trial.scheduler.clock
    envelope=copy.deepcopy(gate.received[(gate.proposal['message_id'],'r2')])
    envelope['body']['contract']['route']['waypoints'][1]=[9.,9.]
    with pytest.raises(ContractViolation,match='ACTUAL_COMMITTED'):
        gate.receive('r2',envelope,t)
    gate.begin_epoch(order_id='order-5',route_hash=gate.proposal['route']['route_hash'],grip_epoch=1,seg=0,now=t)
    trigger(host,inner,dialogue.PAIR,t)
    trigger(host,inner,dialogue.PAIR,t+4)
    assert gate.allowed(gate.key,t+8) and not gate.allowed(gate.key,t)
    call_id=gate.votes['r1']['ACK']['call_id']
    action=next(e['action'] for e in gate.events if e.get('call_id')==call_id)
    with pytest.raises(ContractViolation):gate.apply(call_id,action,t+8)
    assert not gate.allowed(gate.key,t+15)
