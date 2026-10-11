"""Real protocol integration plus mocked upstream; no physics or live model calls."""
import copy
import io
import json
from types import SimpleNamespace
import pytest
from harness import e2e_jev_decider as jev, e2e_s4_live as live
from harness import jev_decider_eval as ev
from harness.s4_event_policy import Options
from harness.zone_final_pair_binding import bind
from harness.llm_completion import assess_completion,normal_completion
from tests.test_e2e_dialogue import build,Wire
from tests.test_pair_llm_s4_host import setup_data,no_external_work,advance


def selected(choice='continue',model=ev.JEV_MODEL):
    options=ev.options_for('dialogue')
    return dict(status='ok',latency_s=.3,body=dict(model=model,usage=dict(input_tokens=123,output_tokens=9),
        answers={'action':dict(type='choice',choice=choice,confidence=.99,probabilities={k:float(k==choice) for k in options})}))


def projected(tmp_path,setup_data,arm='peer_ko'):
    host,inner,wire=build(tmp_path,setup_data,arm=arm)
    c=SimpleNamespace(call_id='jev-test-r1',actor='r1',started_sim_s=1.)
    host.trial.snapshot(c)
    r=live.project(host.trial.prepare_call(c).request,options=Options(True,True,'en'),decider='jev_v1')
    u=json.loads(r['messages'][1]['content'])
    g={**u['reply_format_example'],'own_rgb_grip':'holding'}
    response=dict(choices=[dict(finish_reason='stop',message=dict(content='```json\n'+json.dumps(g)+'\n```'))])
    return r,u,response


@pytest.mark.parametrize('arm',['peer_ko','structured','leader_ko','no_comm'])
def test_same_semantic_boundary_and_fence_in_all_conditions(tmp_path,setup_data,arm):
    r,u,g=projected(tmp_path,setup_data,arm)
    calls=[]
    def select(b):calls.append(b);return selected()
    out=jev.transform(r,g,select)
    assert normal_completion(assess_completion(out,study_json=True))
    v=json.loads(out['choices'][0]['message']['content'])
    assert v['messages']==u['reply_format_example']['messages']
    assert out['ugrp_jev']['confidence']==.99 and out['ugrp_jev']['usage']['input_tokens']==123
    assert calls[0]['state']['own_rgb_supports_grip']=='yes'
    assert 'image' not in json.dumps(calls[0]) and calls[0]['model']==ev.JEV_MODEL
    assert calls[0]['questions']['action']['criteria']==ev.options_for('dialogue',ev.IMPROVED)


def test_bind_identifiers_and_preserve_full_delivered_peer_text(tmp_path,setup_data):
    r,u,g=projected(tmp_path,setup_data)
    u['dialogue'].update(key=['order-5','f'*64,7,2],peer_go_ref='req_peer',own_go_sent=True)
    u['dialogue_epoch_age_s']=3.
    long='previously slipping but recovered; '+('holding now. '*80)
    u['peer_reports']=[dict(sender='r2',message_id='m1',created_at_sim_s=0.,body={'text':long})]
    r['messages'][1]['content']=json.dumps(u)
    out=jev.transform(r,g,lambda b:selected('ACK'))
    a=json.loads(out['choices'][0]['message']['content'])['action']
    assert a==dict(kind='route_vote',choice='ACK',order_id='order-5',route_hash='f'*64,grip_epoch=7,seg=2,peer_go_ref='req_peer')
    receipt=out['ugrp_jev']
    assert receipt['disagreement'] and receipt['gemma_shadow_action']=={'kind':'continue'}
    assert receipt['request']['state']['peer_reports'][0]['text']==long
    assert receipt['request']['state']['epoch_window_open'] is True


@pytest.mark.parametrize('fault',['length','missing_grip','wrong_model','missing_choice','refusal'])
def test_untrusted_outputs_fail_closed_before_execution(tmp_path,setup_data,fault):
    r,u,g=projected(tmp_path,setup_data);result=selected()
    if fault=='length':g['choices'][0]['finish_reason']='length'
    elif fault=='missing_grip':
        raw=copy.deepcopy(u['reply_format_example']);raw.pop('own_rgb_grip');g['choices'][0]['message']['content']=json.dumps(raw)
    elif fault=='wrong_model':result['body']['model']='other'
    elif fault=='missing_choice':result['body']['answers']['action']['choice']='invented'
    elif fault=='refusal':g['choices'][0]['message']['refusal']='refused'
    with pytest.raises(ValueError):jev.transform(r,g,lambda b:result)


def test_key_stays_in_relay_memory_and_call_journal_records_tokens(tmp_path,setup_data):
    from scripts.jev_relay_upstream import Jev
    r,u,g=projected(tmp_path/'fixture',setup_data)
    def send(body,url,key,timeout):
        assert url=='https://api.typesafe.ai/v1/systemone' and key=='TEST_SECRET' and timeout==30
        return selected()
    relay=Jev(tmp_path/'relay',key='TEST_SECRET',send=send)
    out=relay.complete(r,g,'e2e8-b-s61001:call-0001-r1:1')
    record=(tmp_path/'relay/calls.jsonl').read_text()
    assert 'TEST_SECRET' not in record and 'input_tokens' in record
    assert out['ugrp_jev']['cost'] is None


def test_actual_check_action_converts_unreceived_route_go_to_continue(tmp_path,setup_data):
    class BadChoiceWire(Wire):
        def __call__(self,request,**kwargs):
            original=json.loads(super().__call__(request,**kwargs).read())
            g=json.loads(original['choices'][0]['message']['content']);g['own_rgb_grip']='holding'
            original['choices'][0]['message']['content']=json.dumps(g)
            transformed=jev.transform(json.loads(request.data),original,lambda b:selected('GO'))
            return io.BytesIO(json.dumps(transformed).encode())
    def factory(*args,**kwargs):
        for link in kwargs['links'].values():link.inner.study_options=Options(True,True,'en');link.inner.decider='jev_v1'
        return live.Host(*args,**kwargs)
    host,inner,_=bind(build,s4=SimpleNamespace(Host=factory),Wire=BadChoiceWire)(tmp_path,setup_data)
    advance(host,inner,1,5)
    assert host.trial.jev_guard_events
    assert all(e['replacement']=={'kind':'continue'} for e in host.trial.jev_guard_events)
    assert not host.trial.dialogue.votes and not host.trial.dialogue.allowed(None,5)
    assert all(not r.calls for r in inner.values())


def test_default_off_and_distinct_hashed_bundle():
    from scripts.run_e2e_ownmap_live import bundle
    a=bundle('a'*40,61001,'study_gemma4_31b_v1')
    b=bundle('a'*40,61001,'study_gemma4_31b_v1',decider='jev_v1')
    assert a['e2e_options']['decider']=='off' and a['execution_bundle_id']=='e2e-ownmap-live-v185'
    assert b['execution_bundle_id']=='e2e-ownmap-jev-v192'
    assert 'harness/e2e_jev_decider.py' in b['source_sha256']


def test_paired_gemma_and_jev_use_independent_admitted_loopback_ports():
    from scripts.run_e2e_ownmap_live import relay_url
    from harness.s4_live_transport import URL
    assert relay_url('study_gemma4_31b_v1') == 'http://127.0.0.1:18393/v1/chat/completions'
    assert relay_url('study_gemma4_31b_v1', 'jev_v1') == URL
    assert relay_url('main_study_gemini_v1') == URL


def test_jump_metrics_and_absent_run_are_not_success(tmp_path):
    from scripts.evaluate_e2e8 import jumps,inspect
    x=jumps([[0,0,0],[.06,0,3],[.27,0,0]])
    assert x==dict(intervals=2,over_5cm=2,over_20cm=1,max_m=.21000000000000002)
    empty=inspect(tmp_path)
    assert not empty['passed'] and not empty['checks']['deepinfra_normal']
    assert empty['actual_displacement_m']['r1'] is None
