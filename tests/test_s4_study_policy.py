"""No physics/render/provider: real scheduler plus own-input policy contracts."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from harness import s4_compact_prompt as cp
from harness.s4_event_policy import Events,Options,Trial,Host,Driver
from harness.s4_gemma_quota import SharedQuota,TPM,RPM
from harness.zone_study_contract import STRUCTURED_ACTS,STRUCTURED_STATES
from tests.test_pair_llm_s4_host import setup_data,no_external_work
from tests import test_pair_llm_s4_pair as fx


def payload(condition='peer_ko'):
    return dict(robot_id='r1',condition=condition,request_id='req1',sim_time_s=0,
        channel=dict(condition=condition,encoding='schema' if condition=='structured' else 'free_ko',
                     free_text_allowed=condition not in ('no_comm','structured'),can_send_to=['r2']),
        static_map={'truth_not_admitted':'map'},order_sheet={'note_ko':'옛 주문','orders':[{'initial_location':{'x':1},'order_id':'order-5'}]},
        self_belief={'sources':['static_map'],'region':'east'},
        own_belief={'over_budget':False},own_command_history=[{'command_id':f'cmd{i}'} for i in range(30)],
        inbox=[{'message_id':f'm{i}'} for i in range(8)],dialogue_window={'sent':[f'm{i}' for i in range(31)]},
        pair_handshake=dict(phase='wait_go',epoch=1,own_go_sent=False,own_ack_sent=False,peer_go_ref=None,own_executor_phase='wait_carry'),
        decision_window=None)


def test_defaults_legacy_exact_and_english_cohort_identity():
    assert Options()==Options(False,False,'en')
    b=payload();assert cp.project(b,lang='ko')==b
    r={'sentinel':1};assert cp.transform(r,lang='ko')==r
    assert cp.external_condition('peer_ko')=='peer_en'
    assert cp.external_condition('leader_ko')=='leader_en'
    with pytest.raises(ValueError):cp.external_condition('peer_en','ko')


def test_coalescer_progress_inbox_deadline_and_critical_edges():
    from harness.s4_event_coalesce import Coalescer
    traces=[]
    for condition in ('no_comm','peer_ko','leader_ko','structured'):
        policy=Coalescer();b=payload(condition);b['inbox']=[]
        assert 'initial_claim' in policy.observe('r1',b);policy.acknowledge('r1')
        b['pair_handshake'].update(phase='carry',own_executor_phase='lower')
        assert policy.observe('r1',b)==[]
        b['inbox']=[{'message_id':'msg1'}];b['sim_time_s']=1
        assert policy.observe('r1',b)==[]
        b['sim_time_s']=60;assert policy.observe('r1',b)==[]
        b['sim_time_s']=61;assert policy.observe('r1',b)==['inbox_max_wait']
        policy.acknowledge('r1')
        b['decision_window']={'kind':'post_look_decision','opened_at_sim_s':61,'latch_until_sim_s':70}
        assert policy.observe('r1',b)==['decision_window'];policy.acknowledge('r1')
        b['sim_time_s']=62;assert policy.observe('r1',b)==[]
        b['visual_monitor']={'state':'grip_lost'}
        assert policy.observe('r1',b)==['own_observation_abnormal']
        traces.append(policy.trace)
    assert traces.count(traces[0])==4
    with pytest.raises(ValueError):Options(event_coalesce_v1=True)


def test_coalescer_rejected_decision_gets_one_correction_in_own_live_window():
    from harness.s4_event_coalesce import Coalescer
    e=Coalescer();b=payload();b['inbox']=[]
    b['decision_window']={'kind':'carry_decision','opened_at_sim_s':0.,'latch_until_sim_s':9.}
    e.observe('r1',b);e.acknowledge('r1')
    b['own_command_history']=[dict(command_id='failed1',local_state='command_rejected',issued_at_sim_s=2.)]
    b['sim_time_s']=2.;assert e.observe('r1',b)==['own_command_rejected'];e.acknowledge('r1')
    b['own_command_history'][-1]['command_id']='failed2'
    b['sim_time_s']=3.;assert e.observe('r1',b)==[]
    b['decision_window']['opened_at_sim_s']=10.;b['decision_window']['latch_until_sim_s']=19.
    b['sim_time_s']=11.;assert e.observe('r1',b)==['decision_window'];e.acknowledge('r1')
    b['own_command_history'][-1]['issued_at_sim_s']=12.
    b['sim_time_s']=20.;assert e.observe('r1',b)==[]


def test_extractively_trim_read_history_preserves_all_unread_and_failures():
    b=payload();b['inbox']=[dict(message_id=f'm{i}',sender='r2',body={'text':f'opaque {i}'},
        created_at_sim_s=i,reply_to=None,schema='redundant') for i in range(9)]
    b['own_command_history']=[dict(command_id='move',kind='move',arguments={'distance':1}),
        dict(command_id='heartbeat',kind='noop',arguments={'reason_code':'held'}),
        dict(command_id='reject',kind='noop',local_state='command_rejected',arguments={'reason_code':'stale'})]
    x=cp.project(b,compact=True,context_trim_v1=True,seen_message_ids={'m0','m1'})
    assert [m['message_id'] for m in x['inbox']]==[f'm{i}' for i in range(2,9)]
    assert all(m['body']==b['inbox'][i+2]['body'] for i,m in enumerate(x['inbox']))
    assert x['own_command_history']==[b['own_command_history'][0],b['own_command_history'][2]]
    assert x['history_summary']['omitted_read_messages']==2


def test_invalid_reply_does_not_acknowledge_trimmed_inbox(monkeypatch):
    from harness import s4_event_policy as policy
    from types import SimpleNamespace
    trial=object.__new__(Trial);trial.prompt_seen={}
    prepared=SimpleNamespace(bundled=SimpleNamespace(payload_dict=lambda:{'inbox':[{'message_id':'unread'}]}))
    call=SimpleNamespace(actor='r1')
    result=SimpleNamespace(action=None)
    monkeypatch.setattr(policy,'bind',lambda *a,**kw:lambda *a,**kw:result)
    assert trial.finish_call(call,prepared,'bad') is result
    assert trial.prompt_seen=={}
    result.action={'kind':'continue'}
    trial.finish_call(call,prepared,'valid')
    assert trial.prompt_seen=={'r1':{'unread'}}


def test_map_image_toggle_preserves_existing_figure_only_in_legacy_diagnostic():
    b=payload();r=dict(messages=[{'role':'system','content':'old'},{'role':'user','content':json.dumps(b)}],
        images=[{'label':'CURRENT OWN WRIST RGB','image':'data:image/jpeg;base64,YQ=='},
                {'label':'STATIC MAP FIGURE','image':'data:image/png;base64,Yg=='}],
        image_refs=[{'label':'CURRENT OWN WRIST RGB','bytes_sha256':'a'*64},
                    {'label':'STATIC MAP FIGURE','bytes_sha256':'b'*64}])
    legacy=cp.transform(r,map_as_image_v1=True)
    assert legacy['images']==r['images'] and 'static_map' not in json.loads(legacy['messages'][1]['content'])
    own=cp.transform(r,compact=True,map_as_image_v1=True)
    assert len(own['images'])==1 and own['map_image_scope']=='omitted_authored_map_for_own_input'
    assert json.loads(own['messages'][1]['content'])['self_belief']['status']=='unknown'


@pytest.mark.parametrize('lang',['ko','en'])
def test_compact_preserves_safety_contracts_and_no_map(lang):
    b=payload('structured');original=copy.deepcopy(b)
    x=cp.project(b,compact=True,lang=lang)
    assert b==original and 'static_map' not in x and 'initial_location' not in x['order_sheet']['orders'][0]
    assert x['self_belief']['status']=='unknown'
    assert len(x['inbox'])==len(x['own_command_history'])==len(x['dialogue_window']['sent'])==2
    assert x['history_summary']['inbox']['omitted_count']==6
    assert x['pair_handshake']==b['pair_handshake'] and x['decision_window']==b['decision_window']
    m=x['action_message_contract']['message']['message']
    assert m['act']==list(STRUCTURED_ACTS) and m['state']==[*STRUCTURED_STATES,None]
    assert len(cp.system('r1',lang))<=1500
    # Shared machine-readable semantics: all legal actions, limits and enum sets.
    other=cp.project(b,compact=True,lang='en' if lang=='ko' else 'ko')
    assert other['action_message_contract']==x['action_message_contract']
    for concept in ('request_id','decision_sources','GO','ACK','peer_go_ref','unknown','10','continue'):
        assert concept in cp.system('r1',lang)


def test_events_do_not_depend_on_condition_or_frame_clock_and_never_drop_messages():
    all_traces=[]
    for c in ('no_comm','peer_ko','leader_ko','structured'):
        e=Events();b=payload(c);b['inbox']=[];trace=[e.observe('r1',b)]
        b['sim_time_s']=100;b['pair_handshake']['response_deadline_sim_s']=110
        assert e.observe('r1',b)==[]
        b['pair_handshake'].update(own_go_sent=True,peer_go_ref='peer-go')
        trace.append(e.observe('r1',b));assert 'go_ack_epoch' in trace[-1]
        b['pair_handshake'].update(own_ack_sent=True,phase='carry',own_executor_phase='carry')
        trace.append(e.observe('r1',b))
        b['decision_window']={'kind':'carry_decision','latch_until_sim_s':120}
        trace.append(e.observe('r1',b));assert 'decision_window' in trace[-1]
        assert e.observe('r1',b)==[]
        b['inbox']=[{'message_id':'new1'}];assert e.observe('r1',b)==['received_message']
        b['inbox'].append({'message_id':'new2'});assert e.observe('r1',b)==['received_message']
        all_traces.append(trace)
    assert all(x==all_traces[0] for x in all_traces)


def test_quota_shared_restart_tpm_rpm_daily_and_no_refund(tmp_path):
    clock=[1791740000.];q=SharedQuota(tmp_path,clock=lambda:clock[0])
    for i in range(4):assert q.reserve(3300,request_id=str(i),request_sha256='a'*64)['admitted']
    q2=SharedQuota(tmp_path,clock=lambda:clock[0])
    assert q2.reserve(3300,request_id='fifth',request_sha256='b'*64)['retry_after_s']==60
    clock[0]+=60;assert q2.reserve(3300,request_id='fifth',request_sha256='b'*64)['admitted']
    for i in range(26):assert q.reserve(1,request_id=str(i),request_sha256='c'*64)['admitted']
    assert not q.reserve(1,request_id='rpm',request_sha256='d'*64)['admitted']
    with q.locked() as s:s['day_requests']=12960
    clock[0]+=61;assert q.reserve(1,request_id='day',request_sha256='d'*64)['retry_after_s']>60


@pytest.mark.parametrize('condition',['no_comm','peer_ko','leader_ko','structured'])
@pytest.mark.parametrize('coalesce',[False,True])
def test_real_scheduler_english_compact_single_claim_no_timer(tmp_path,setup_data,monkeypatch,condition,coalesce):
    from harness import s4_pair_epochs as ep
    def handshake(**kwargs):
        h=ep.Handshake(carry_lease_renewal=ep.hs.ACTIVE_PHASE_HEARTBEAT,epoch_reconnect=True,go_ack_rounds=True)
        h.study_options=Options(True,True,'en',event_coalesce_v1=coalesce,context_trim_v1=coalesce);h.reply_contract=True;return h
    monkeypatch.setattr(fx.hs,'Handshake',handshake)
    monkeypatch.setattr(fx.stage,'Host',Host)
    host,driver,inner=fx.build(tmp_path,setup_data,condition)
    assert host.condition==cp.external_condition(condition)
    host.begin()
    for i in range(1,51):
        t=i/10
        for o in inner.values():o.now=t
        for link in host.links.values():link.capture_frame()
        host.step_to(t)
    assert len(host.trial.scheduler.calls)==3
    assert all(not host.trial.scheduler.reask_pending(r) for r in inner)
    assert len(host.trial.handshake.claims)==2
    for r in host.trial.requests:
        b=json.loads(r['user']);assert 'static_map' not in b
        assert 'static_map' not in r['input_keys']
        assert len(r['image_refs'])==1 and '당신' not in r['system']
        assert b['condition']==cp.external_condition(condition)
    assert not host.trial.scheduler.send_violations


def test_new_entrypoint_defaults_and_no_execution(tmp_path):
    from scripts import run_s4_study_v184 as run
    b=run.bundle('a'*40,'peer_en',options=Options(True,True))
    assert b['driver_profile']=='study_gemma4_31b_v1' and b['condition']=='peer_en'
    assert b['study_options']['prompt_lang']=='en' and b['execution_admitted'] is False
    with pytest.raises(ValueError,match='ADMISSION_REQUIRED'):
        run.main(['--condition','no_comm','--expected-source-sha','a'*40,'--execute'])


def test_global_quota_429_holds_same_sim_and_request_then_claim_once(tmp_path,setup_data,monkeypatch):
    import io
    from urllib.error import HTTPError
    from harness.s4_call_recovery import RetryMixin
    calls=[];waits=[];state={'sim_s':1.,'commands':0}
    class Base:
        def __init__(self):self.entries=[];self.run_key='fixture';self.store_dir=None
        def _send(self,*args):
            calls.append(args);self.entries.append(dict(seq=len(calls),body_sha256='a'*64,error_response={'retry_after':'60'}))
            if len(calls)==1:raise HTTPError('http://fixture',429,'global_bucket',{},io.BytesIO())
            return 'one response'
    class Ledger(RetryMixin,Base):pass
    ledger=Ledger(retry_429=True,sleep=waits.append)
    ledger.retry_snapshot=lambda:copy.deepcopy(state)
    assert ledger._send('same-call','r1',b'identical request',180)=='one response'
    assert waits==[60.] and calls[0]==calls[1]
    resumed=[r for r in ledger.retry_events if r['status']=='RESUMED']
    assert resumed and all(r['hold_verified'] and r['before']==r['after'] for r in resumed)


@pytest.mark.parametrize('coalesce',[False,True])
@pytest.mark.parametrize('condition',['no_comm','peer_ko'])
def test_event_driver_go_ack_then_controller_heartbeat_no_model_timer(tmp_path,setup_data,monkeypatch,coalesce,condition):
    from harness import s4_pair_epochs as ep,s4_grip_visual
    def handshake(**kwargs):
        h=ep.Handshake(carry_lease_renewal=ep.hs.ACTIVE_PHASE_HEARTBEAT,epoch_reconnect=True,go_ack_rounds=True)
        h.study_options=Options(True,True,'en',event_coalesce_v1=coalesce);h.reply_contract=True;return h
    monkeypatch.setattr(fx.hs,'Handshake',handshake);monkeypatch.setattr(fx.stage,'Host',Host)
    host,old,inner=fx.build(tmp_path,setup_data,condition)
    driver=Driver(host,old.runtime)
    class Monitor:
        def __init__(self,**kwargs):pass
        def observe(self,*args):return {'state':'held','reason':'fixture own RGB'}
    monkeypatch.setattr(s4_grip_visual,'GripMonitor',Monitor)
    host.begin();commands=[]
    for i in range(1,351):
        t=i/10
        for rid,o in inner.items():o.now=t;host.links[rid].capture_frame()
        driver.poll(t);host.step_to(t);commands.extend(driver.step(t))
    h=driver.handshake
    assert len(h.permits)==1 and not h.failure
    assert driver.heartbeat_trace and all(not r['command_replayed'] for r in driver.heartbeat_trace)
    assert len(host.trial.scheduler.calls)<16
    assert any(c['kind']=='mecanum' for rid,c in commands)
    # A new unknown RGB result stops motion; no stale held result is reused.
    monkeypatch.setattr(Monitor,'observe',lambda *a:{'state':'unknown','reason':'fixture loss of visibility'})
    for rid,o in inner.items():o.now=35.1;host.links[rid].capture_frame()
    driver.poll(35.1)
    assert h.failure=='EVENT_RGB_UNKNOWN'
    assert all(c['kind']=='hold' for rid,c in driver.step(35.1))
