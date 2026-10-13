"""Real scheduler/code-body boundaries with recorded own inputs, no physics/API."""
import copy,json
from types import SimpleNamespace as NS
import pytest
from harness import e2e_task_planner as m
from harness.task_planner import candidate
from tests.test_pair_llm_s4_host import setup_data,no_external_work,advance
from tests.test_e2e_dialogue_call_policy import make_event_host


def test_default_off_and_registration(monkeypatch):
    from tests import test_e2e_camera_hold as p
    from scripts.run_e2e_ownmap_live import bundle,ROOT
    from harness.e2e_runtime_registration import require_current
    args,kw=[],{}
    def capture(*a,**k):args.extend(a);kw.update(k);return bundle(*a,**k)
    monkeypatch.setattr(p,'bundle',capture)
    p.test_registered_wheel_wait_candidate('zero_wheel_v1',276,'range_wall_v1')
    args[1]=61013
    kw.update(stage_physics='release_dt1_v1',relook_giveup='dev_light_rest_v1',boundary_lifecycle='abort_v1',
        dialogue_call_policy='event_v1',post_relook='carry_through_v1',body_controller='jev_v1',
        body_backend='code_v1',body_protocol_stack='code_v1',approach_efficiency='regulated_v1',
        speech_context='recent8_v1',call_snapshot='prepared_v1')
    parent=bundle(*args,**kw)
    assert parent['execution_bundle_id']=='e2e18-v372'
    for mode,v in m.VERSIONS.items():
        b=bundle(*args,**kw,planner=mode);require_current(b,ROOT)
        assert b['execution_bundle_id']==f'e2e18-v{v}'
        assert m.parent_for_validation(b)['e2e_options']==parent['e2e_options']
    for mode,v in m.GATED_VERSIONS.items():
        b=bundle(*args,**kw,planner=mode,planner_evidence_gate='on_v1');require_current(b,ROOT)
        assert b['execution_bundle_id']==f'e2e18-v{v}'
        assert m.parent_for_validation(b)['e2e_options']==parent['e2e_options']
    assert m.compose({})==()


def test_actual_code_body_wait_and_direction_cannot_change_task():
    from tests.test_e2e_body_code import gate
    g,tr,robots=gate()
    tr.task_roles={};tr.approach={};tr.aligned={}
    ex=m.Executive(NS(actors=('r1','r2'),channel=None),tr,g,'gemma_v1',lambda r:None)
    tr.task_planner=ex
    value=dict(act='wait',args=dict(until='view',max_s=5.),message='',reason='check')
    assert ex.start('r1',value,0)['accepted']
    menu,proposal,facts=g.menu_direct('r1',0,[dict(kind='mecanum',forward=.1,left=0,turn=0,duration_s=.1)])
    safe,choice,_=g.prepare_decision('r1',0,'motion',menu,proposal,facts)
    assert choice in ('hold_and_reobserve','wait_and_reobserve','hold_and_wait')
    ex.active['r1']=dict(act='reroute',args=dict(via='detour_left'))
    restricted=ex.restrict('r1',0,'motion',{'detour_left':1,'detour_right':2,'hold_and_wait':3},None,{})
    assert set(restricted)=={'detour_left','hold_and_wait'}


def test_end_choice_changes_actual_station_geometry():
    from harness.e2e_carrier_axes import station
    beam=dict(pose_own_m=[0.,0.,0.],rgb={})
    a,ga,_=station(beam,[2.,0.],'end_neg');b,gb,_=station(beam,[2.,0.],'end_pos')
    assert ga[0]<0<gb[0] and a[2]!=b[2]
    rows=m.menu('r1',{'beam_visible':True})
    assert {c['args']['side'] for c in rows if c['act']=='carry'}=={'end_neg','end_pos'}
    assert all(c['args']['mode']=='joint' for c in rows if c['act']=='carry')
    assert not any(c['act']=='carry' for c in m.menu('r3',{}))


@pytest.mark.parametrize('evidence_gate',['off','on_v1'])
def test_prepared_task_request_excludes_protocol_and_future_owner(tmp_path,setup_data,evidence_gate):
    from harness.e2e_call_snapshot import install
    host,robots,wire=make_event_host(tmp_path,setup_data)
    advance(host,robots,1,6)
    tr=NS(robots=robots,task_roles={},approach={},aligned={},state='mapping')
    body=NS(context=lambda rid,now:{'visual_category':'not_visible','own_grip':'unknown'})
    trial=host.trial;trial.event_projection='route_hash_v1'
    for r in robots.values():
        r.packet=None;r.now=6.;r.goal=NS(stage='explore');r.servo={1:2000}
    ex=m.install(trial,tr,body,'gemma_v1',planner_evidence_gate=evidence_gate)
    install(trial,'prepared_v1')
    call=NS(actor='r1',started_sim_s=6.,call_id='planner-frozen')
    trial.snapshot(call)
    robots['r1'].now=6.1;robots['r1'].goal.stage='future'
    request=trial.prepare_call(call).request
    text=request['messages'][1]['content'];ctx=json.loads(text)
    assert ctx['now_s']==6 and ctx['own']['own_stage']=='explore'
    assert ctx.get('planner_evidence_gate','off')==evidence_gate
    assert 'peer_go_ref' not in text and 'peer_reports' not in text and 'dialogue' not in ctx
    assert ctx['own']['rgb']['t_sim']<=6
    assert request['request_sha256']


def test_relay_opt_in_rule_never_calls_provider():
    from harness.e2e_task_planner_relay import task_request,rule_response
    own=dict(robot_id='r1',beam_visible=True)
    ctx=dict(schema='ugrp.task_planner.v1',planner_backend='rule_v1',own=own,candidates=m.menu('r1',own),received_messages=[],own_act_results=[],now_s=0)
    request={'messages':[{'role':'system','content':'test'},{'role':'user','content':json.dumps(ctx)}]}
    assert task_request(request)==ctx
    response=rule_response(ctx)
    assert response['ugrp_task_planner']['provider_calls']==0 and response['usage']['total_tokens']==0
    assert json.loads(response['choices'][0]['message']['content'])['act']=='carry'


def test_route_and_vote_are_actual_text_not_hidden_contract():
    from tests.test_e2e_own_inputs import route
    from harness.e2e_dialogue import wire_route
    from harness.e2e_task_planner_wire import route_text,read_route,vote_text,read_vote,allowed
    planned,_=route();contract=dict(kind='OwnRoute',route=wire_route(planned),source_message_id=None)
    text=route_text(contract)
    assert read_route(text)==contract and len(text)<=600
    action=dict(kind='route_vote',choice='GO',order_id='order-5',route_hash='a'*64,grip_epoch=1,seg=2)
    assert read_vote('I am ready.'+vote_text(action,'call-0001-r1'))['key']==('order-5','a'*64,1,2)
    d=NS(trial=NS(task_planner=True),votes={'r1':{'GO':{'call_id':'x'},'ACK':{'call_id':'y'}},'r2':{'GO':{'call_id':'z'},'ACK':{'call_id':'q'}}},task_received_votes={})
    assert not allowed(d,('order-5','a'*64,1,2))  # private votes alone never open it


def test_live_scheduler_task_reply_reaches_executive(tmp_path,setup_data,monkeypatch):
    import io
    from harness import e2e_s4_live as live
    from harness.s4_event_policy import Options
    from harness.zone_final_pair_binding import bind
    from harness.zone_send_ledger import completion_body
    from tests import test_e2e_dialogue as fixture
    calls=[];saved={}
    class Wire:
        def __init__(self,*args,**kwargs):self.requests=[];self.responses=[]
        def __call__(self,request,**kwargs):
            data=json.loads(request.data);self.requests.append(data)
            content=data['messages'][-1]['content']
            ctx=json.loads(next(x['text'] for x in content if x['type']=='text'))
            assert ctx['schema']=='ugrp.task_planner.v1'
            rid=ctx['robot_id'];side='end_neg' if rid=='r1' else 'end_pos'
            c=next((c for c in ctx['candidates'] if c['act']=='carry' and c['args']['side']==side and c['args']['approach']=='direct'),ctx['candidates'][0])
            raw=json.dumps(dict(act=c['act'],args=c['args'],message=f'I will take {side} and use my own observations.',reason='Current own task.'))
            return io.BytesIO(completion_body(raw,usage={'prompt_tokens':100,'completion_tokens':60,'total_tokens':160},model='fixture'))
    monkeypatch.setattr(fixture,'Wire',Wire)
    def factory(*args,**kw):
        robots={rid:link.inner for rid,link in kw['links'].items()}
        for rid,r in robots.items():
            r.study_options=Options(True,True,'en');r.goal=NS(stage='explore');r.servo={1:2000}
            r.packet={'route':r.own_inputs_at(1)['own_route']} if rid=='r1' else None
        host=live.Host(*args,**kw);trial=host.trial
        trial.dialogue_call_policy='event_v1';trial.event_projection='route_hash_v1';trial.dialogue_decider='code_v1';trial.llm_memory='v1_commands'
        trial.dialogue.protocol_idempotency='same_route_v1';trial.dialogue.route_handle='typed_ref_v1'
        trial.route_handle='typed_ref_v1'
        trial.protocol_observer=lambda rid:dict(own_grip='unknown',own_alignment='unknown',gripper_command='open',source='fixture own command')
        tr=NS(robots=robots,task_roles={},approach={},aligned={},state='mapping')
        body=NS(context=lambda rid,now:{'visual_category':'not_visible','own_grip':'unknown'})
        ex=m.install(trial,tr,body,'gemma_v1',append=calls.append);saved['ex']=ex
        from harness.e2e_call_snapshot import install
        install(trial,'prepared_v1')
        return host
    host,robots,wire=bind(fixture.build,s4=NS(Host=factory))(tmp_path,setup_data)
    advance(host,robots,1,40)
    assert host.trial.dialogue.approved, json.dumps(dict(events=host.trial.dialogue.events,calls=calls,discarded=host.trial.scheduler.discarded),default=str)
    assert host.trial.dialogue.claims=={'r1','r2'},json.dumps(dict(events=host.trial.dialogue.events,calls=calls),default=str)
    assert len(wire.requests)<30
    d=host.trial.dialogue
    d.begin_epoch(order_id='order-5',route_hash=d.proposal['route']['route_hash'],grip_epoch=1,seg=0,now=40.)
    saved['ex'].body.memory={r:NS(key=('own_joint_command',1,0),history=[]) for r in ('r1','r2')}
    host.trial.protocol_observer=lambda rid:dict(own_grip='holding',own_alignment='aligned',gripper_command='closed',source='fixture own RGB hypothesis')
    for r in ('r1','r2'):robots[r].servo[1]=1500
    advance(host,robots,40,55)
    assert d.allowed(d.key,55),json.dumps(dict(events=d.events,received=getattr(d,'task_received_votes',{})),default=str)
    assert all('contract' not in e['body'] for r in ('r1','r2') for e in host.trial.channel.inbox(r,now_sim_s=55))
    assert any(r['event']=='act_started' for r in calls),json.dumps(host.trial.scheduler.unsent_calls)
    assert not host.trial.scheduler.discarded
    assert all('peer_go_ref' not in json.dumps(r) and 'peer_reports' not in json.dumps(r) for r in wire.requests)


def test_completion_contract_is_explicit_not_legacy_widening():
    from harness.llm_completion import assess_completion,normal_completion
    value=dict(act='wait',args=dict(until='observe',max_s=5),message='',reason='check')
    response=dict(choices=[dict(finish_reason='stop',message=dict(content=json.dumps(value)))])
    assert normal_completion(assess_completion(response,study_json='task_planner_v1'))
    assert not normal_completion(assess_completion(response,study_json=True))
    response['choices'][0]['finish_reason']='length'
    assert not normal_completion(assess_completion(response,study_json='task_planner_v1'))


def test_route_choices_are_different_feasible_cardinal_paths():
    from harness.e2e_goal_route import cardinal_path
    points=[[0.,0.],[1.,1.]]
    a=cardinal_path(points,lambda a,b:True)
    b=cardinal_path(points,lambda a,b:True,y_first=True)
    assert a==[[0.,0.],[1.,0.],[1.,1.]] and b==[[0.,0.],[0.,1.],[1.,1.]]
    assert cardinal_path(points,lambda a,b:a!=[1.,0.] and b!=[1.,0.])==b


def test_stop_cancels_partial_leg_and_requires_new_own_route():
    rows=[]
    d=NS(begin_epoch=lambda **kw:rows.append(kw),claims={'r1','r2'},votes={})
    tr=NS(robots={},state='carry',queue=[(2.,'r1',{'kind':'mecanum'})],queue_until=3.,authorizations={1:2},
        permit=('old',),epoch=1,seg=0,plan={'agreement_route_hash':'a'*64},dialogue=d)
    tr.set=lambda state,now:setattr(tr,'state',state)
    ex=m.Executive(NS(actors=('r1','r2')),tr,NS(),'gemma_v1',lambda r:None)
    ex.interrupt(1.)
    assert tr.state=='planner_regrip_wait' and tr.queue==[] and tr.authorizations=={} and tr.permit is None
    assert tr.epoch==2 and ex.interrupted and rows[0]['grip_epoch']==2
    assert ex.holds==[('r1',{'kind':'hold'}),('r2',{'kind':'hold'})]


def test_long_route_uses_only_counted_channel_fragments():
    from harness.e2e_task_planner_wire import compile_messages,receive_route
    from harness.e2e_dialogue import wire_route
    from tests.test_e2e_own_inputs import route
    planned,_=route();contract=dict(kind='OwnRoute',route=wire_route(planned),source_message_id=None)
    # Enough real route text to exceed one channel utterance; no hidden field.
    contract['route']['waypoints']=[[float(i)/100,0.] for i in range(60)]
    from harness.zone_study_contract import digest
    r=contract['route'];r['route_hash']=digest({k:v for k,v in r.items() if k!='route_hash'})
    messages=compile_messages([dict(text='My selected task.',contract=contract,recipients=['r2'],reply_to=None)])
    assert len(messages)>2 and all(len(m['text'])<=600 for m in messages)
    assert messages[0]['text']=='My selected task.'
    d=NS();decoded=None
    for i,message in enumerate(messages):
        envelope=dict(sender='r1',message_id=str(i),body={'text':message['text']})
        decoded=receive_route(d,'r2',envelope) or decoded
    assert decoded==contract


def test_public_route_alternative_recompiles_selected_geometry():
    from tests.test_e2e_own_inputs import route
    from tests.test_e2e_s3_route import fixture
    from harness.e2e_task_planner_routes import alternatives
    from harness.e2e_s3_route import compile_route
    planned,refs=route();_,args=fixture()
    profiles=args['profiles'];compiled=compile_route(planned,now=1.,observed=refs,profiles=profiles,option='on_v1',source='own_map')
    paths={'direct':[[0.,0.],[.5,0.]],'dogleg':[[0.,0.],[0.,.1],[.5,.1],[.5,0.]]}
    choices=alternatives(dict(route=planned,compiled=compiled),paths,now=1.,observed=refs,profiles=profiles)
    assert set(choices)==set(paths)
    assert choices['direct']['compiled']['length_m']<choices['dogleg']['compiled']['length_m']
    assert choices['direct']['route']['route_hash']!=choices['dogleg']['route']['route_hash']
