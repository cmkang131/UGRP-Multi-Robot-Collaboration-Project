"""Live composition input/dispatch regressions; no physics or provider calls."""
import copy
import json
from types import SimpleNamespace
import pytest
from harness import e2e_s4_live as live
from harness.s4_event_policy import Options
from harness import e2e_own_inputs as own
from tests.test_e2e_dialogue import build, trigger, claim_phase
from tests.test_pair_llm_s4_host import setup_data, no_external_work, advance


def test_compact_projection_keeps_ownroute_contract_and_rgb(tmp_path,setup_data):
    host,inner,wire=build(tmp_path,setup_data)
    advance(host,inner,1,4)
    request=host.trial.requests[0]
    # Take a real sealed request through the actual serializer.
    call=SimpleNamespace(call_id='projection-r1',actor='r1',started_sim_s=4.)
    host.trial.snapshot(call)
    original=host.trial.prepare_call(call).request
    projected=live.project(original,options=Options(True,True,'en'))
    payload=json.loads(projected['messages'][1]['content'])
    own.scan(payload)
    assert payload['own_route_proposal']['route']['B_rgb_sources']
    assert payload['own_map_summary']['own_map_sha256']
    assert 'approve_route' in str(payload['action_message_contract'])
    assert 'route_vote' in str(payload['action_message_contract'])
    assert 'pair_decision' not in str(payload['action_message_contract'])
    assert len(projected['images'])==len(original['images'])==1
    assert projected['image_refs']==original['image_refs']
    assert payload['condition']=='peer_en' and payload['task']['fixed_roles']['r3']=='idle'


@pytest.mark.parametrize('key', sorted(own.FORBIDDEN))
def test_no_privileged_projection_escape(tmp_path,setup_data,key):
    host,inner,_=build(tmp_path,setup_data)
    call=SimpleNamespace(call_id='attack-r1',actor='r1',started_sim_s=1.)
    host.trial.snapshot(call);request=host.trial.prepare_call(call).request
    body=json.loads(request['messages'][1]['content']);body['own_map'][key]=[4.,-2.]
    request['messages'][1]['content']=json.dumps(body)
    with pytest.raises(own.ContractViolation,match='PRIVILEGED_INPUT'):
        live.project(request,options=Options(True,True,'en'))


def test_real_mapper_constructor_uses_no_authored_inputs():
    from pathlib import Path
    from harness.e2e_live_mapping import Robot
    profile=json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    robot=Robot('r1',601,profile,Options(True,True,'en'),relook='on_v1')
    assert robot.goal.explorer.robot_id=='r1'
    assert robot.goal.e2e_options['own_route']=='goal_route_v1'
    assert robot.goal.e2e_relook.receipt is None
    with pytest.raises(own.ContractViolation,match='NOT_YET_RECEIVED'):robot.own_inputs_at(0.)


def test_live_trial_preserves_native_dialogue_validation(tmp_path,setup_data):
    from harness.zone_final_pair_binding import bind
    def factory(*args,**kw):
        for link in kw['links'].values():link.inner.study_options=Options(True,True,'en')
        return live.Host(*args,**kw)
    host,inner,wire=bind(build,s4=SimpleNamespace(Host=factory))(tmp_path,setup_data)
    claim_phase(host,inner)
    assert host.trial.dialogue.approved and host.trial.dialogue.claims=={'r1','r2'}
    assert not host.trial.dialogue.allowed(None,30.)
    assert all(not link.calls for link in inner.values())


def test_native_rgb_mapping_and_model_snapshot_no_scene_input(monkeypatch):
    import base64,hashlib,cv2,numpy as np,sys
    # The fixed CAD XML builder imports type definitions from the simulation
    # package. Permit import, but forbid constructing either a model or state.
    monkeypatch.delitem(sys.modules,'mujoco',raising=False)
    monkeypatch.delitem(sys.modules,'sim.multi_masterpi_production',raising=False)
    monkeypatch.delitem(sys.modules,'torch',raising=False)
    import mujoco
    monkeypatch.setattr(mujoco,'MjModel',SimpleNamespace(from_xml_string=lambda *a,**k:pytest.fail('physics model forbidden')))
    monkeypatch.setattr(mujoco,'MjData',lambda *a,**k:pytest.fail('physics state forbidden'))
    from pathlib import Path
    from harness.e2e_live_mapping import Robot,Link
    profile=json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    robot=Robot('r1',601,profile,Options(True,True,'en'),relook='on_v1')
    rgb=np.zeros((480,640,3),np.uint8)
    _,encoded=cv2.imencode('.jpg',rgb)
    jpeg=encoded.tobytes();sha=hashlib.sha256(jpeg).hexdigest()
    for i in range(2):
        obs=dict(frame_id=i,sim_time=i*.2,sha256=sha,image=base64.b64encode(jpeg).decode())
        robot.receive(obs,rgb)
    state=robot.own_inputs_at(.2)
    own.scan(state)
    assert len(state['observed_rgb'])==2 and state['own_map']['goal'] is None
    assert robot.beam is None and robot.packet is None
    assert Link.build(robot,'peer_en').frame_at(.2).jpeg==jpeg


def test_separate_loopback_relays_and_azure_reconnect():
    from scripts.s4_reverse_tunnel import command
    from harness.s4_live_transport import validate_receipt
    from harness.zone_study_llm_driver import HostError
    cmd=command(60,host='azure',dual_model=True)
    assert 'oracle-x86' not in cmd and cmd[-2]=='azure'
    assert '127.0.0.1:18393:127.0.0.1:18394' in cmd
    with pytest.raises(HostError):validate_receipt({},remote_url='http://public.invalid/v1/chat/completions')


def test_bundle_switches_off_and_standard_source_has_no_fixture_entry():
    from scripts.run_e2e_ownmap_live import bundle,run
    b=bundle('a'*40,61001,'study_gemma4_31b_v1')
    assert not b['e2e_options']['enabled'] and not b['fixture_restore']
    assert not b['study_options']['event_driven_llm']
    with pytest.raises(ValueError,match='TOGGLE_OFF'):run(b,None,None)
    from pathlib import Path
    text=Path('sim/e2e_ownmap_live.py').read_text()
    assert 'restore_scene' not in text and 'test_scenario' not in text


def test_native_s3_schedule_requires_current_dialogue_and_exact_pulses():
    from harness.e2e_live_transport import Transport
    from tests.test_s3_coarse_fine import profiles
    from tests.test_e2e_goal_route import controller,ref
    g=controller(own_route='goal_route_v1')
    packet=g.route_to_B(dict(rgb=ref(3),pose_own_m=[0.,0.,0.]),now=1.3,profiles=profiles(),pulse_budget='fractional_duration_v1')
    key=('order-5',packet['proposal']['route']['route_hash'],1,0)
    gate=SimpleNamespace(key=key,allowed=lambda k,t:False)
    robots={r:SimpleNamespace(servo={1:1500}) for r in ('r1','r2')}
    transport=Transport(robots,gate,profiles(),pulse_budget='fractional_duration_v1')
    transport.plan=packet['s3_plan'];transport.epoch=1
    assert not transport._carry(2.) and not transport.queue
    gate.allowed=lambda k,t:k==key
    assert transport._carry(2.)
    first=transport.queue[0];t,rid,a=first
    assert not transport.authorize(rid,{**a,'duration_s':.999},t)
    assert transport.authorize(rid,a,t)
    assert not transport.authorize(rid,a,t)
    t,rid,a=transport.queue[1]
    gate.key=(*key[:2],2,0)
    assert not transport.authorize(rid,a,t)


def test_post_run_evaluator_cannot_promote_missing_physics_or_controller(tmp_path):
    from scripts.evaluate_e2e_ownmap_live import evaluate
    empty=evaluate(tmp_path,{'start_to_finish_transport':True},[],0.)
    assert not empty['start_to_finish_transport'] and not empty['B_whole_outline_inside']
    assert empty['feedback_to_controller'] is False


def test_gemini_cached_credential_uses_keychain_only(monkeypatch):
    from scripts import e2e_gemini_keychain as proxy
    store=SimpleNamespace(find=lambda:({'access_token':'test-token','expiry_date':10**16},None))
    monkeypatch.setattr(proxy.urllib.request,'urlopen',lambda *a,**k:pytest.fail('unneeded network call'))
    assert proxy.refresh({},store)=='test-token'


def test_relay_admits_actual_e2e_ledger_id_without_widening_to_arbitrary_runs():
    from scripts.s4_proxy_relay import accepted_call_id
    for model in ('gemma','gemini'):
        assert accepted_call_id(f'e2eaz1-{model}-s61001-on-r1:call-0001-r1:1')
    assert accepted_call_id('s4live1-old-run:call-0001-r2:2')
    assert not accepted_call_id('arbitrary:call-0001-r1:1')
    assert not accepted_call_id('e2eaz1-gemma-s99999-on:call-0001-r1:1')
