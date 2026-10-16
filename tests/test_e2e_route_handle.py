import copy,io,json
from types import SimpleNamespace
import pytest
from harness import e2e_s4_live as live
from harness.e2e_route_handle import expand,OPTION
from harness.s4_event_policy import Options
from harness.zone_final_pair_binding import bind
from tests.test_e2e_dialogue import build,Wire
from tests.test_pair_llm_s4_host import setup_data,no_external_work,advance


@pytest.mark.parametrize('finish,wrong,admitted',[('stop',False,True),('length',False,False),('stop',True,False)])
def test_model_handle_relay_keeps_exact_route_and_requires_model_approval(tmp_path,setup_data,monkeypatch,finish,wrong,admitted):
    original=Wire.__call__
    def reference(self,request,**kwargs):
        response=json.loads(original(self,request,**kwargs).read());value=json.loads(response['choices'][0]['message']['content'])
        for message in value['messages']:
            if message.get('contract'):
                full=message['contract'];message['contract']=dict(kind='OwnRouteRef',route_hash='f'*64 if wrong else full['route']['route_hash'])
                response['choices'][0]['finish_reason']=finish
        response['choices'][0]['message']['content']=json.dumps(value)
        return io.BytesIO(json.dumps(response).encode())
    monkeypatch.setattr(Wire,'__call__',reference)
    def factory(*args,**kw):
        for link in kw['links'].values():
            link.inner.study_options=Options(True,True,'en');link.inner.protocol_progress='stage_retry_v1'
        host=live.Host(*args,**kw);host.trial.dialogue.route_handle=OPTION;return host
    host,inner,wire=bind(build,s4=SimpleNamespace(Host=factory))(tmp_path,setup_data)
    advance(host,inner,1,40)
    d=host.trial.dialogue
    assert (d.proposal is not None)==admitted
    if admitted:
        assert d.approved and d.claims=={'r1','r2'}
        body=json.loads(json.loads(wire.requests[0])['messages'][-1]['content'][0]['text'])
        assert d.proposal['route']==body['own_route_proposal']['route']
        assert body['route_contract_example']==dict(kind='OwnRouteRef',route_hash=d.proposal['route']['route_hash'])
        assert body['reply_format_example']['messages'][0]['contract']==body['route_contract_example']
        assert 'ENTIRE own_route_proposal' not in json.loads(wire.requests[0])['messages'][0]['content']
        assert {e['robot_id'] for e in d.events if e['kind']=='claim'}=={'r1','r2'}


def test_unenabled_peer_or_unknown_handle_cannot_expand():
    value=dict(kind='OwnRouteRef',route_hash='a'*64)
    with pytest.raises(ValueError,match='NOT_ENABLED'):expand(SimpleNamespace(),value,{})
    with pytest.raises(ValueError,match='CAPTURED_R1'):expand(SimpleNamespace(route_handle=OPTION,boundary_frame="observed_own_v1"),value,dict(actor='r2',state={'own_route':None}))
    old=dict(kind='OwnRoute',route={},source_message_id=None)
    assert expand(SimpleNamespace(),old,{}) is old


def test_v233_bundle_registration():
    from scripts.run_e2e_ownmap_live import bundle
    from tests.test_e2e18 import options,ROOT
    from harness.e2e_runtime_registration import require_current
    kw=dict(speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1',camera_load='nominal_command_v1',route_tokens='1600_v1',protocol_progress='stage_retry_v1',route_cost='bounded_morphology_v1',align_progress='dev_continue_v1',pregrasp_recovery='bounded_search_v1',pregrasp_gaze='own_bearing_v1',search_bearing='last_seen_v1',pulse_admission='finish_active_v1',event_projection='route_hash_v1',pregrasp_progress='backup_replan_v1',gaze_cadence='settled_frames_v1',stage_physics='pregrasp_dt1_v1',protocol_idempotency='same_route_v1',route_handle=OPTION,boundary_frame="observed_own_v1")
    b=bundle('a'*40,61009,'study_gemma4_31b_v1',**options(),**kw);require_current(b,ROOT)
    assert b['execution_bundle_id']=='e2e18-v233' and 'harness/e2e_route_handle.py' in b['source_sha256']
    b['e2e_options']['route_handle']='off'
    with pytest.raises(ValueError):require_current(b,ROOT)
