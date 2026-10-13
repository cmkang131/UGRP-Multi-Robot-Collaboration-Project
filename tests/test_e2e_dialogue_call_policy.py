"""Offline admission, real scheduler/protocol fixtures; never physics/provider."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from harness import e2e_dialogue_call_policy as m
from harness import e2e_s4_live as live
from harness.s4_event_policy import Options
from harness.zone_final_pair_binding import bind
from tests.test_e2e_dialogue import build, trigger, claim_phase
from tests.test_pair_llm_s4_host import setup_data, no_external_work, advance


def report(text, t=0., sender='r2', mid='m1'):
    return dict(message_id=mid, sender=sender, encoding='free_en', body=dict(text=text), created_at_sim_s=t)


def test_repeat_ack_paraphrase_new_facts_and_safety():
    p=m.Policy(); own=dict(stage='approach'); proto=dict(key=None)
    assert p.decide('r1',0,own,proto,[])['admitted']
    for t,text in enumerate(['OK', 'I am holding and waiting for protocol updates.', 'Still holding position.'],1):
        r=p.decide('r1',t,own,proto,[report(text,t)])
        assert not r['admitted'] and r['reason']=='same_state_no_new_fact'
    assert not p.decide('r1',4,own,proto,[report('B is visible on the left')])['admitted']
    assert p.decide('r1',15,own,proto,[report('B is visible on the left')])['admitted']
    assert not p.decide('r1',30,own,proto,[report('B is visible on the left',30,mid='m9')])['admitted']
    assert p.decide('r1',31,own,proto,[report('Please stop, beam slipping!')])['admitted']
    assert p.decide('r1',32,own,dict(key=['order', 'hash', 1, 0]),[])['admitted']


def test_state_throttle_is_per_actor_and_same_hash_never_heartbeat():
    p=m.Policy()
    assert p.decide('r1',0,{'stage':'map'},{},[])['admitted']
    assert p.decide('r2',1,{'stage':'map'},{},[])['admitted']
    r=p.decide('r1',3,{'stage':'align'},{},[])
    assert r['reason']=='observation_min_interval' and r['retry_at_sim_s']==15
    assert p.decide('r1',15,{'stage':'align'},{},[])['admitted']
    assert not p.decide('r1',600,{'stage':'align'},{},[])['admitted']
    with pytest.raises(ValueError):p.decide('r1',601,{'truth':1},{},[])


def test_prompt_bound_and_pinned_actual_route():
    body=dict(robot_id='r2',sim_time_s=100,dialogue=dict(approved=False,proposal_message_id='route'),
        dialogue_window=dict(sent=['x']*10000), own_command_history=[{'x':i} for i in range(100)],
        own_decision_log=[{'x':i} for i in range(100)],peer_reports=[dict(report('proposal',mid='route'),body={'contract':{'kind':'OwnRoute','route':{'route_hash':'h'}}})]+
        [report('Holding.',i,mid=str(i)) for i in range(20)])
    new,system=m.compact(body,'rules')
    assert new['dialogue_window']=={'sent_count':10000}
    assert len(new['own_command_history'])==len(new['own_decision_log'])==8
    assert len(new['peer_reports'])==6 and all('age_sim_s' in r for r in new['peer_reports'])
    assert new['active_route_report']['message_id']=='route'
    assert len(body['dialogue_window']['sent'])==10000
    assert len((system+json.dumps(new,separators=(',',':'))).encode())<=m.PARAMETERS['prompt_utf8_bytes']
    body['peer_reports'][0]['body']['contract']['huge']='x'*15000
    with pytest.raises(ValueError,match='PROMPT_CAP'):m.compact(body,'rules')


def test_token_forecast_unknown_usage_and_zero_time():
    usage=dict(charged_tokens=400000,known_tokens=384000,usage_unknown_requests=1,token_cap=800000)
    assert m.token_health(usage,200)['cap_expected_sim_s']==400
    assert m.token_health(usage,200)['warning_before_600']
    assert not m.token_health(usage,300)['warning_before_600']
    assert m.token_health(usage,0)['cap_expected_sim_s'] is None


def make_event_host(tmp_path, setup_data, arm='peer_ko', seed=61001, option='event_v1'):
    def factory(*args,**kw):
        for link in kw['links'].values():link.inner.study_options=Options(True,True,'en')
        host=live.Host(*args,**kw)
        host.trial.dialogue_call_policy=option
        return host
    return bind(build,s4=SimpleNamespace(Host=factory))(tmp_path,setup_data,arm,seed)


@pytest.mark.parametrize('option',['off','event_v1'])
@pytest.mark.parametrize('arm,seed',[('no_comm',61001),('structured',61001),('peer_ko',61001),('leader_ko',61001)])
def test_native_scheduler_route_claim_go_ack_and_600s_repeat_fixture(tmp_path,setup_data,arm,seed,option,record_property):
    host,inner,wire=make_event_host(tmp_path,setup_data,arm,seed,option)
    claim_phase(host,inner)
    d=host.trial.dialogue
    if arm!='no_comm':
        assert d.approved and d.claims=={'r1','r2'}
        t=host.trial.scheduler.clock
        d.begin_epoch(order_id='order-5',route_hash=d.proposal['route']['route_hash'],grip_epoch=1,seg=0,now=t)
        trigger(host,inner,('r1','r2'),t)
        trigger(host,inner,('r1','r2'),t+4)
        advance(host,inner,t+8,t+12)
        assert d.allowed(d.key,t+12), (d.votes,[(r['robot'],r['status'],r.get('error')) for r in host.trial.requests], host.trial.call_events.events[-12:])
        assert all(set(d.votes[r])=={'GO','ACK'} for r in ('r1','r2'))
    else:
        assert not d.approved and not d.received
    # The r76 failure mode: unchanged state repeatedly asks for a call.
    # Use the real scheduler admission path, not a disconnected predicate test.
    for t in range(40,600,3):
        for r in ('r1','r2'):host.trial.scheduler.trigger(r,'report',at=t)
        advance(host,inner,t,t+1)
    advance(host,inner,599,600)
    rows=host.trial.send_ledger.entries
    tokens=sum(e['provider_usage']['total_tokens'] for e in rows)
    record_property('condition',arm);record_property('policy',option)
    record_property('calls',len(wire.requests));record_property('fixture_tokens',tokens)
    if option=='event_v1':
        assert len(wire.requests)<=40 and tokens<=200000
        assert any(not e['admitted'] for e in host.trial.call_events.events)
        from harness.e2e_dialogue_decider import unpack
        for raw in wire.requests:
            req=json.loads(raw);body,_=unpack(req)
            system=req['messages'][0]['content']
            assert len((system+json.dumps(body,separators=(',',':'),ensure_ascii=False)).encode())<=m.PARAMETERS['prompt_utf8_bytes']
    assert not host.trial.scheduler.unsent_calls
    assert all(not r.calls for r in inner.values())
    host.save(tmp_path/'saved')
    assert (tmp_path/'saved/dialogue_call_policy.json').is_file()==(option=='event_v1')


def test_four_registered_children_keep_parent_options_and_cap(monkeypatch):
    from tests import test_e2e_camera_hold as p
    from scripts.run_e2e_ownmap_live import bundle,ROOT
    from harness.e2e_runtime_registration import require_current
    from scripts.s4_proxy_relay import accepted_call_id
    args,kw=[],{}
    def capture(*a,**k): args.extend(a);kw.update(k);return bundle(*a,**k)
    monkeypatch.setattr(p,'bundle',capture)
    p.test_registered_wheel_wait_candidate('zero_wheel_v1',276,'range_wall_v1')
    args[1]=61013;kw.update(stage_physics='release_dt1_v1',relook_giveup='dev_light_rest_v1')
    from harness.e2e_boundary_lifecycle import VERSIONS
    for (parent,option),version in VERSIONS.items():
        if parent=='e2e18-v350':
            flags=dict(post_relook='carry_through_v1',body_controller='jev_v1',body_backend='code_v1',body_protocol_stack='code_v1')
        else:
            flags=dict(post_relook='carry_nominal_v1',perception_fast='shadow_axes_v1',controller_timing='phase_v1',llm_memory='v1_commands',dialogue_decider='code_v1',explore_idle='idle5_v1' if parent.endswith('347') else 'idle10_v1')
        b=bundle(*args,**kw,**flags,boundary_lifecycle=option,dialogue_call_policy='event_v1')
        require_current(b,ROOT)
        assert b['execution_bundle_id']==f'e2e18-v{version+9}'
        assert m.parent_for_validation(b)['e2e_options']==bundle(*args,**kw,**flags,boundary_lifecycle=option)['e2e_options']
        assert accepted_call_id(b['execution_bundle_id']+'-s61013-r77:call-0001-r1:1')
        bad=copy.deepcopy(b);bad['dialogue_call_policy_parameters']['observation_interval_sim_s']=0
        with pytest.raises(ValueError):require_current(bad,ROOT)


def test_observation_message_spacing_protocol_and_wait_bypass():
    p=m.Policy();cont={'kind':'continue'}
    message=lambda text:dict(text=text,reply_to=None,recipients=['r2'])
    assert not p.allow_message('r1',0,cont,message('Holding position.'))
    first=message('The blue B marker is visible to the left.')
    assert p.allow_message('r1',0,cont,first);p.message_sent('r1',0,first)
    assert not p.allow_message('r1',1,cont,message('The beam is visible on the right.'))
    assert p.allow_message('r1',1,{'kind':'route_vote','choice':'GO'},message('Ready.'))
    assert p.allow_message('r1',1,cont,message('Please wait, grip is uncertain.'))
    assert p.allow_message('r1',15,cont,message('The beam is visible on the right.'))
    assert m.fact(report('I see no beam'))!=m.fact(report('I see beam'))


def test_relay_rejects_observation_without_erasing_generated_utterance():
    from harness.e2e_dialogue import Dialogue
    from harness.zone_study_protocol import Receipt
    policy=m.Policy();trial=SimpleNamespace(dialogue_call_policy='event_v1',call_events=policy)
    d=Dialogue(trial); sent=[]
    def send(*a,**kw):sent.append(kw);return Receipt(False,rejection='fixture_transport')
    bus=SimpleNamespace(send=send)
    value=dict(action={'kind':'continue'},messages=[dict(text='Holding position.',recipients=['r2'],reply_to=None)])
    receipts=d.relay(bus,'r1',value,at_sim_s=1,call_id='c1')
    assert len(receipts)==len(value['messages'])==1 and not sent
    assert receipts[0].rejection=='EVENT_OBSERVATION_SUPPRESSED'
    value['action']={'kind':'route_vote','choice':'ACK'}
    assert len(d.relay(bus,'r1',value,at_sim_s=2,call_id='c2'))==1 and len(sent)==1


def test_health_progress_writes_early_budget_warning(tmp_path):
    from scripts.run_e2e_ownmap_live import health
    usage=dict(charged_tokens=400000,known_tokens=384000,usage_unknown_requests=1,token_cap=800000)
    budget=SimpleNamespace(usage=lambda _:usage)
    trial=SimpleNamespace(send_ledger=SimpleNamespace(entries=[]),
        token_progress=lambda t:m.budget_progress(budget,'run',t,tmp_path))
    progress=health({},SimpleNamespace(trial=trial),None,200,10,0)
    assert progress['token_progress']['cap_expected_sim_s']==400
    warning=json.loads((tmp_path/'TOKEN_RATE_WARNING.json').read_text())
    assert warning['cumulative_tokens']==400000 and warning['usage_unknown_requests']==1


def test_upstream_speech_is_also_bounded():
    from harness.e2e_dialogue_decider import speech_request
    # Explicitly oversized necessary context cannot bypass the second boundary.
    user=dict(dialogue_call_policy='event_v1',request_id='r',robot_id='r1',
        task=dict(fixed_roles={'r1':'end_neg'},description='x'*15000),condition='no_comm',
        sim_time_s=1,own_rgb={'t_sim':1},channel={'can_send_to':[]},peer_reports=[],
        dialogue=dict(key=None,approved=False,own_claim=False,own_go_sent=False,own_ack_sent=False,peer_go_ref=None),
        action_message_contract={'actions':[{'kind':'continue'}]})
    request={'messages':[{'content':'system'},{'content':json.dumps(user)}]}
    selected=dict(action='WAIT',own_grip='unknown',own_alignment='unknown')
    with pytest.raises(ValueError,match='PROMPT_CAP'):speech_request(request,selected)


def test_alternating_old_observations_do_not_restart_dialogue():
    p=m.Policy();a=report('B is visible to the left',0,mid='a');b=report('Beam on the right',1,mid='b')
    assert p.decide('r1',0,{}, {},[a,b])['admitted']
    for i in range(1,5):
        duplicate=dict(a if i%2 else b,message_id=f'copy{i}',created_at_sim_s=i*20)
        assert not p.decide('r1',i*20,{}, {},[a,b,duplicate])['admitted']
