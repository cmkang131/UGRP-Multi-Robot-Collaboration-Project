"""Real S4 prepare_call and S3 three-path input scan; no model/network/physics."""
import copy
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from harness import e2e_own_inputs as own
from harness import s4_llm_host as s4
from harness.zone_study_contract import ContractViolation,digest
from harness.zone_study_integration import OwnFrame
from tests.test_pair_llm_s4_host import make_host,setup_data,no_external_work

ROOT=Path(__file__).resolve().parents[1]


def state(rid='r1'):
    b=io.BytesIO();Image.new('RGB',(8,8),'blue').save(b,'JPEG');jpeg=b.getvalue()
    ref=dict(robot_id=rid,frame_id=1,t_sim=1.,sha256=hashlib.sha256(jpeg).hexdigest())
    mapped=dict(robot_id=rid,frame=rid+'/own_start',map_version=1,
        pose=dict(mean=[0.,0.,0.],covariance=[[.01,0.,0.],[0.,.01,0.],[0.,0.,.01]],sources=[ref]),
        walls=[dict(a=[-1.,1.],b=[1.,1.],sources=[ref])],goal=dict(label='B',sources=[ref]),sources=[ref])
    return mapped,[ref],OwnFrame(1,1.,jpeg,ref['sha256'])


def route():
    mapped,refs,_=state()
    value=dict(schema=own.ROUTE_SCHEMA,robot_id='r1',frame_id=1,map_version=1,own_map=mapped,
        B_rgb_sources=refs,waypoints=[[0.,0.],[.5,0.]],route_hash=None)
    value['route_hash']=digest({k:v for k,v in value.items() if k!='route_hash'})
    return value,refs


def test_actual_s4_prepare_has_only_own_image_and_sources(tmp_path,setup_data,monkeypatch):
    host,inner,_,budget=make_host(tmp_path,setup_data,arm='peer_ko')
    from harness.zone_environment_registry import load_scenario,bundle_for
    scenario=load_scenario('e2e_one_beam_ownmap')
    monkeypatch.setattr(s4.pair,'map_figure',lambda *a:pytest.fail('authored map image'))
    from harness import pair_llm_live, pair_llm_contract
    ledger=pair_llm_live.PairLiveLedger(store_dir=tmp_path/'own-wire',budget=budget,run_key='s4-fixture-run',
        profile=pair_llm_contract.driver_profile(),wire=lambda *a,**k:pytest.fail('model send forbidden'),
        pacer=SimpleNamespace(wait=lambda:None))
    host=s4.Host(scenario,condition='peer_ko',links=host.links,seed=61001,
        map_bundle=bundle_for(scenario),model_adapter=SimpleNamespace(
            client_factory=host.trial.client_factory,send_ledger=ledger),
        e2e_own_inputs_v1='on_v1')
    trial=host.trial
    assert trial.map_png is None and trial.static_map is None
    assert trial.sheet==own.TASK
    assert trial.study_config()['fixed_roles']['r3']=='idle'
    assert trial.study_config()['stage1_only']
    # Poison every old fallback, including LLM stop estimates from static PF.
    monkeypatch.setattr(s4.zi.IntegratedTrial,'snapshot',lambda *a:pytest.fail('legacy snapshot'))
    monkeypatch.setattr(s4.zi.IntegratedTrial,'build_inputs',lambda *a,**k:pytest.fail('legacy payload'))
    for rid in ('r1','r2','r3'):
        mapped,refs,frame=state(rid)
        if rid!='r1':mapped['goal']=None
        inner[rid].own_inputs_at=lambda now,m=mapped,r=refs:dict(own_map=m,observed_rgb=r)
        inner[rid].frame_at=lambda t,f=frame:f
        inner[rid].belief=lambda:pytest.fail('legacy belief')
        call=SimpleNamespace(actor=rid,started_sim_s=1.,call_id='e2e-'+rid)
        trial.snapshot(call);prepared=trial.prepare_call(call)
        payload=json.loads(prepared.request['messages'][1]['content'])
        own.scan(payload)
        assert payload['task']['fixed_roles']['r3']=='idle'
        assert 'initial_location' not in json.dumps(payload)
        assert 'P2-3' not in json.dumps(payload)
        assert '[4.6, -2.1]' not in json.dumps(payload)
        raw=json.dumps(dict(request_id=prepared.request_id,action={'kind':'continue'},
            decision_sources=['own_rgb','own_belief'],messages=[]))
        reply=trial.finish_call(call,prepared,raw)
        assert reply.action=={'kind':'continue'}
        assert trial.requests[-1]['payload_validated']
        assert len(prepared.request['images'])==1
        assert prepared.request['image_refs'][0]['sha256']==frame.sha256
        assert payload['own_map']['goal'] is None if rid!='r1' else payload['own_map']['goal']['label']=='B'


def test_s3_planner_guard_provider_do_not_touch_static():
    from harness.zone_final_pair_skill import make_plan
    value,refs=route()
    class Poison:
        def __getitem__(self,k):pytest.fail('static/sheet accessed')
    result=make_plan(Poison(),Poison(),'B',e2e_own_inputs_v1='on_v1',own_route=value,robot_id='r1',now=1.,observed_rgb=refs)
    own.scan(result)
    assert set(result)=={'schema','planner','guard','provider','transport_admitted'}
    assert result['transport_admitted'] is False
    for payload in (result['planner'],result['guard'],result['provider']):
        assert '[4.6, -2.1]' not in json.dumps(payload)
    from harness.zone_s3_recovery_runtime import Runtime
    with pytest.raises(ValueError,match='legacy static'):
        Runtime(Poison(),config={'options':{'e2e_own_inputs_v1':'on_v1'}})
    from harness.zone_s3_route_binding import configure
    with pytest.raises(ValueError,match='STATIC_ROUTE_OVERLAY'):
        configure(Poison(),[],None,e2e_own_inputs_v1='on_v1')


@pytest.mark.parametrize('field',['static_map','eval','initial_location','world_alignment','B_coordinates'])
def test_nested_privileged_input_rejected(field):
    value,refs=route();value['own_map'][field]={'center_m':[4.6,-2.1]}
    value['route_hash']=digest({k:v for k,v in value.items() if k!='route_hash'})
    with pytest.raises(ContractViolation):own.s3_inputs(value,rid='r1',now=1.,observed=refs)


@pytest.mark.parametrize('fault',['future','foreign','unknown_sha','wrong_frame','stale_hash'])
def test_source_and_frame_integrity(fault):
    value,refs=route()
    if fault=='future':refs[0]['t_sim']=2.
    if fault=='foreign':refs[0]['robot_id']='r2'
    if fault=='unknown_sha':refs=[]
    if fault=='wrong_frame':value['own_map']['frame']='world'
    if fault=='stale_hash':value['waypoints'][1]=[.6,0.]
    with pytest.raises(ContractViolation):own.s3_inputs(value,rid='r1',now=1.,observed=refs)


def test_approval_and_epoch_contract():
    gate=own.Agreement();h='a'*64
    with pytest.raises(ContractViolation):gate.propose(h,'missing',delivered_ids=[])
    gate.propose(h,'m1',delivered_ids=['m1'])
    with pytest.raises(ContractViolation):gate.approve(h,'missing',robot_id='r2',response_id='c2',model_response_ids=['c2'])
    gate.approve(h,'m1',robot_id='r2',response_id='c2',model_response_ids=['c2'])
    gate.begin_epoch(order_id='order-5',route_hash=h,grip_epoch=1,seg=0)
    key=('order-5',h,1,0)
    for r in ('r1','r2'):
        gate.vote(r,'GO',key,response_id=r,model_response_ids=[r])
        if r=='r1':assert not gate.ready
        gate.vote(r,'ACK',key,response_id=r,model_response_ids=[r])
    assert gate.ready
    gate.begin_epoch(order_id='order-5',route_hash=h,grip_epoch=2,seg=0)
    assert not gate.ready
    with pytest.raises(ContractViolation):gate.vote('r1','GO',key,response_id='r1',model_response_ids=['r1'])


def test_new_map_only_B_floor_and_scenario():
    from harness.e2e_environment import resolve,MAP_ID
    from harness.zone_environment_registry import load_scenario,validate
    from harness.zone_final_environment import provider_spec
    mapped,row,contract=resolve();parent=json.loads((ROOT/row['parent_file']).read_text())
    expected=copy.deepcopy(parent);expected.update(map_id=MAP_ID,version=6)
    expected['regions']['zone_B']['half_extents_m']=[.4,.7]
    assert mapped==expected and contract['status']=='UNMEASURED_NEW_MAP'
    scenario=load_scenario('e2e_one_beam_ownmap')
    assert len(scenario['orders'])==len(scenario['eval']['setup']['placements'])==1
    assert scenario['eval']['setup']['placements'][0]['pose_m']==[1.275,.05,0.]
    assert validate(scenario).ok
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    scene=ScenarioFinalV3Scene.from_scenario('e2e_one_beam_ownmap',61001)
    assert len(scene.cargo)==1 and scene.cargo[0].item_id=='beam_1'
    assert scene.config['setup_only']['spawns']==scenario['eval']['setup']['robot_spawns']
    with pytest.raises(ValueError,match='STATIC_PROVIDER_FORBIDDEN'):provider_spec(MAP_ID)


def test_payload_mutation_and_window_injection_rejected():
    mapped,refs,frame=state()
    bundled=own.build_inputs(rid='r1',now=1.,request_id='req_1',frame=frame,
        own_map=mapped,observed=refs,history=[],inbox=None,arm='no_comm',seed=61001)
    request=own.build_request(bundled)
    from harness.zone_study_prompts_ko import archive_request,verify_archived_request
    assert verify_archived_request(archive_request(request))==[]
    with pytest.raises(ContractViolation):own.build_request(bundled,window={'eval':{'success':True}})
    bundled.data['own_map']['pose']['mean']=[4.6,-2.1,0.]
    with pytest.raises(ContractViolation,match='MUTATED'):own.build_request(bundled)


@pytest.mark.parametrize('fault',[None,'unreceived','future','world_transform'])
def test_r2_received_B_route_uses_RGB_beam_alignment_only(fault):
    from harness.zone_final_pair_skill import make_plan
    remote,refs=route();mapped,local_refs,_=state('r2');mapped['goal']=None
    report=dict(schema='ugrp.e2e_peer_route.v1',sender='r1',recipient='r2',message_id='m1',route=remote,
        beam_alignment=dict(beam_ref='shared_visual_beam',own_rgb=local_refs[0],peer_rgb=refs[0],
            own_beam_pose=[1.,.1,0.],peer_beam_pose=[.3,.2,0.],
            covariance=[[.01,0.,0.],[0.,.01,0.],[0.,0.,.01]]))
    if fault=='world_transform':report['beam_alignment']['world_alignment']=[4.6,-2.1]
    received={'m1':dict(report_sha256=digest(report),delivered_at_sim_s=1.)}
    if fault=='unreceived':received={}
    if fault=='future':received['m1']['delivered_at_sim_s']=2.
    def invoke():
        return make_plan(None,None,None,e2e_own_inputs_v1='on_v1',peer_report=report,
            own_map=mapped,robot_id='r2',now=1.,observed_rgb=local_refs,received_reports=received)
    if fault:
        with pytest.raises(ContractViolation):invoke()
    else:
        result=invoke();own.scan(result)
        assert result['provider']['goal'] is None
        assert result['planner']['peer_report']['route']['B_rgb_sources'][0]['robot_id']=='r1'
        assert result['planner']['waypoints']==[[.7,-.1],[1.2,-.1]]
        assert result['transport_admitted'] is False
