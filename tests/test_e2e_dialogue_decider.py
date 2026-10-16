"""d1 -> speech -> unchanged protocol gate; no provider, physics, or credentials."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from harness import e2e_dialogue_decider as dd
from harness import e2e_s4_live as live
from harness.e2e_own_inputs import ContractViolation
from harness.s4_event_policy import Options
from scripts.d1_dialogue_upstream import D1
from tests.test_e2e_vote_ref import opened, ctx
from tests.test_pair_llm_s4_host import setup_data, no_external_work  # noqa: F401


def fixture():
    value = json.loads(Path('experiments/2026-10-13-e2e18-llmmemory/call-0021-fixture.json').read_text())
    return value


def user():
    from harness import e2e_llm_memory as lm
    f = fixture()
    # Same actual captured call as the older memory regression.
    b = copy.deepcopy(f['body'])
    b['own_decision_log'] = []
    b['dialogue_decider'] = dd.MODE
    lm.filter_actions(b)
    return b


def request(b):
    return dict(model='gemma-4-31b-it', messages=[dict(role='system', content='legacy'),
        dict(role='user', content=[dict(type='text', text=json.dumps(b)),
            dict(type='image_url', image_url=dict(url='data:image/jpeg;base64,AA=='))])])


def answer(body, action='GO', grip='holding'):
    selections = dict(action=action, own_grip=grip, own_alignment='unknown')
    return dict(model='d1', answers={k: dict(choice=selections[k],
        probabilities={c: float(c == selections[k]) for c in q['criteria']}, confidence=1.)
        for k, q in body['questions'].items()}, usage=dict(cost=.0001))


def speech(text='Ready for this segment; awaiting mutual agreement.', **extra):
    return dict(model='google/gemma-4-31b-it', choices=[dict(finish_reason='stop',
        message=dict(content=json.dumps(dict(text=text, **extra))))], usage=dict(cost=.0002))


def test_current_candidates_exact_refs_and_prior_claim():
    b = user(); assert b['dialogue']['own_claim']
    assert set(dd.candidates(b)) == {'WAIT', 'WAIT_UNCERTAIN', 'GO'}
    d = b['dialogue']; d['own_go_sent'] = True
    assert set(dd.candidates(b)) == {'WAIT', 'WAIT_UNCERTAIN'}
    d['peer_go_ref'] = 'actual-peer-call'
    assert dd.candidates(b)['ACK']['peer_go_ref'] == 'actual-peer-call'
    assert 'GO' not in dd.candidates(b)
    d['vote_ref'] = 'vabcdef'
    assert dd.candidates(b)['ACK'] == dict(kind='route_vote', choice='ACK', vote_ref='vabcdef')
    d['own_ack_sent'] = True
    assert set(dd.candidates(b)) == {'WAIT', 'WAIT_UNCERTAIN'}


def test_state_keeps_peer_original_and_age_without_map_geometry():
    b = user(); original = copy.deepcopy(b)
    b['peer_reports'][0]['received_at_sim_s'] = 539.
    s = dd.state(b)
    assert s['peer_reports'][0]['body'] == original['peer_reports'][0]['body']
    assert s['peer_reports'][0]['received_age_s'] == pytest.approx(b['sim_time_s'] - 539.)
    assert 'own_map_summary' not in s and 'waypoints' not in json.dumps(s)
    assert s['self_observation']['source'] == 'd1 estimate from attached own wrist RGB only'
    b['truth'] = [1, 2]
    with pytest.raises(ContractViolation, match='PRIVILEGED'):
        dd.state(b)


def test_stale_captured_image_or_epoch_removes_votes():
    b=user();b['dialogue_epoch_age_s']=20.
    assert set(dd.candidates(b))=={'WAIT','WAIT_UNCERTAIN'}
    b=user();b['sim_time_s']=b['own_rgb']['t_sim']+10.
    assert set(dd.candidates(b))=={'WAIT','WAIT_UNCERTAIN'}


@pytest.mark.parametrize('condition,encoding,recipients', [
    ('peer_en','free_en',['r2','r3']), ('leader_en','free_en',['r3']),
    ('structured','schema',['r2','r3']), ('no_comm','none',[])])
def test_same_d1_before_speech_all_conditions(tmp_path, condition, encoding, recipients):
    b = user(); b['condition'] = condition; b['channel'].update(encoding=encoding, can_send_to=recipients)
    if condition == 'no_comm': b['peer_reports'] = []
    calls = []
    def select(body, url, key, timeout):
        calls.append('vision' if 'own_grip' in body['questions'] else 'd1'); assert body['images'] == ['data:image/jpeg;base64,AA==']
        return dict(status='ok', latency_s=.3, body=answer(body))
    def speak(req):
        calls.append('gemma'); data=json.loads(req['messages'][1]['content'])
        assert data['fixed_action']['choice'] == 'GO'
        assert data['selected_protocol_action'] == 'GO'
        return speech()
    out = D1(tmp_path, key='test-secret', send=select).complete(request(b), 'test', speak)
    payload = json.loads(out['choices'][0]['message']['content'])
    assert payload['action'] == dd.candidates(b)['GO']
    if condition == 'no_comm':
        assert calls == ['vision','d1'] and payload['messages'] == []
    elif encoding == 'schema':
        from harness.zone_study_contract import structured_violations
        assert calls == ['vision','d1'] and 'text' not in payload['messages'][0]
        assert not structured_violations(payload['messages'][0]['message'])
    else:
        assert calls == ['vision','d1','gemma']
        assert payload['messages'][0]['text'] == 'Ready for this segment; awaiting mutual agreement.'
        assert set(payload['messages'][0]['recipients']) <= set(recipients)


def test_speech_cannot_override_action_and_invalid_d1_fails_before_speech(tmp_path):
    req = request(user())
    client = D1(tmp_path, key='test-secret', send=lambda b,*a: dict(status='ok',latency_s=.1,body=answer(b)))
    with pytest.raises(ValueError, match='SPEECH_ONLY_SCHEMA'):
        client.complete(req,'override',lambda r:speech(action=dict(kind='claim')))
    client.send=lambda b,*a:dict(status='ok',latency_s=.1,body=answer(b, action='ACK'))
    with pytest.raises(ValueError, match='CANDIDATE_MISMATCH'):
        client.complete(req,'impossible',lambda r:pytest.fail('Gemma must not run'))
    client.send=lambda *a:dict(status='http_error',latency_s=.1,http_status=429)
    with pytest.raises(ValueError, match='D1_VISUAL_UPSTREAM_FAILURE'):
        client.complete(req,'failure',lambda r:pytest.fail('Gemma must not run'))


def test_actual_host_projection_and_final_validator(tmp_path, setup_data):
    host,d = opened(tmp_path,setup_data,'off')
    call=SimpleNamespace(call_id='d1-live',actor='r1',started_sim_s=6.)
    host.trial.snapshot(call)
    original=host.trial.prepare_call(call).request
    request_=live.project(original,options=Options(True,True,'en'),llm_memory='v1_commands',
        memory=dict(decisions=[],windows=[],commands=[]),dialogue_decider=dd.MODE)
    b=json.loads(request_['messages'][1]['content'])
    assert b['dialogue_decider']==dd.MODE and request_['image_refs']==original['image_refs']
    go=dd.candidates(b)['GO'];d.check_action(go,ctx(d),6.5)
    # Late release remains rejected by the existing host (no automatic vote repair).
    with pytest.raises(ContractViolation, match='STALE'):
        d.check_action(go,ctx(d),100.)


def test_default_unchanged_and_new_bundle_admitted(monkeypatch):
    from tests import test_e2e_camera_hold as p
    from scripts.run_e2e_ownmap_live import bundle, ROOT
    from harness.e2e_runtime_registration import require_current
    args,kw=[],{}
    def capture(*a,**k):
        args.extend(a);kw.update(k);return bundle(*a,**k)
    monkeypatch.setattr(p,'bundle',capture)
    p.test_registered_wheel_wait_candidate('zero_wheel_v1',276,'range_wall_v1')
    kw.update(stage_physics='release_dt1_v1',relook_giveup='dev_light_rest_v1',post_relook='carry_nominal_v1',
              perception_fast='shadow_axes_v1',controller_timing='phase_v1',llm_memory='v1_commands')
    old=bundle(*args,**kw)
    assert bundle(*args,**kw,dialogue_decider='gemma_v0')==old
    new=bundle(*args,**kw,dialogue_decider=dd.MODE)
    assert new['execution_bundle_id']=='e2e18-v338' and new['workflow_version']=='7.231.0'
    require_current(new,ROOT)
    code=bundle(*args,**kw,dialogue_decider=dd.CODE_MODE)
    assert code['execution_bundle_id']=='e2e18-v346' and code['workflow_version']=='7.239.0'
    assert code['e2e_options']['dialogue_decider']=='code_v1'
    require_current(code,ROOT)
    bad=copy.deepcopy(new);bad['e2e_options']['dialogue_decider']='gemma_v0'
    with pytest.raises(ValueError):require_current(bad,ROOT)


def test_visual_uncertainty_removes_go_and_real_journal_accepts_speech_key(tmp_path):
    from scripts.s4_proxy_relay import speech_idempotency_key, request_dialogue_mode
    from harness.s4_relay_journal import Journal
    for grip in ('unknown','slipping','not_held'):
        q=dd.decision_request(request(user()),dict(own_grip=grip,own_alignment='unknown'))
        assert set(q['questions']['action']['criteria'])=={'WAIT','WAIT_UNCERTAIN'}
    journal=Journal(tmp_path/'journal');key=speech_idempotency_key('a'*64)
    value,disposition=journal.call(key,b'request',lambda:(200,b'ok',None))
    assert value[0]==200 and disposition=='forwarded'
    value,disposition=journal.call(key,b'request',lambda:pytest.fail('must reuse'))
    assert disposition=='cached'
    assert request_dialogue_mode(dict(messages=[{},dict(content='ordinary chat')]))=='gemma_v0'
    assert request_dialogue_mode(request(user()))==dd.MODE


@pytest.mark.parametrize('port',(18391,18393))
@pytest.mark.parametrize('mode',(dd.MODE,dd.CODE_MODE))
def test_live_receipt_pins_d1_source_and_selects_its_registered_port(port,mode):
    import hashlib
    from scripts.run_e2e_ownmap_live import relay_url
    from scripts.openrouter_upstream import config
    from harness.s4_live_transport import validate_receipt
    from harness.zone_study_llm_driver import HostError
    h=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    url=f'http://127.0.0.1:{port}/v1/chat/completions'
    upstream=h('scripts/openrouter_upstream.py')
    r=dict(schema='ugrp.s4_ssh_proxy.v1',remote_url=url,proxy=dict(source_sha256=upstream),
        checked_unix=100.,valid_for_s=3600,audit_per_post=True,
        authentication='existing_mac_proxy_no_credentials_transferred',driver_profile='study_gemma4_31b_v1',
        upstream='openrouter_v1',single_model=True,fallback_enabled=False,
        openrouter_v1=dict(config(),source_sha256=upstream),dialogue_decider=mode,
        d1_dialogue_source_sha256={p:h(p) for p in ('scripts/d1_dialogue_upstream.py','harness/e2e_dialogue_decider.py','harness/e2e_llm_memory.py')})
    assert validate_receipt(r,now=101.,remote_url=url)==r
    assert relay_url('study_gemma4_31b_v1',dialogue_decider=mode,receipt=r)==url
    assert relay_url('study_gemma4_31b_v1')=='http://127.0.0.1:18393/v1/chat/completions'
    bad=copy.deepcopy(r);bad['d1_dialogue_source_sha256']['harness/e2e_dialogue_decider.py']='0'*64
    with pytest.raises(HostError,match='pinned d1'):
        validate_receipt(bad,now=101.,remote_url=url)
    with pytest.raises(ValueError,match='REGISTERED_RELAY'):
        relay_url('study_gemma4_31b_v1',dialogue_decider=mode,receipt={**r,'remote_url':'https://example.com/api'})


def test_code_contract_go_ack_rejection_and_veto_ages():
    b=user(); b['dialogue_decider']=dd.CODE_MODE
    assert dd.code_select(b)['action']=='GO'
    assert dd.code_select(b)['own_grip']=='unknown'
    b['dialogue']['own_go_sent']=True
    assert dd.code_select(b)['action']=='WAIT'
    b['dialogue']['peer_go_ref']='current-peer-call'
    assert dd.code_select(b)['action']=='ACK'
    assert dd.candidates(b)['ACK']['peer_go_ref']=='current-peer-call'
    b['dialogue']['vote_ref']='vcurrent'
    assert dd.candidates(b)['ACK']==dict(kind='route_vote',choice='ACK',vote_ref='vcurrent')
    b['dialogue']['own_ack_sent']=True
    assert dd.code_select(b)['action']=='WAIT'
    b=user(); b['dialogue_decider']=dd.CODE_MODE
    for grip,alignment,command in [('slipping','unknown','closed'),('unknown','misaligned','closed'),('unknown','unknown','open')]:
        b['own_protocol_observation']=dict(own_grip=grip,own_alignment=alignment,gripper_command=command)
        assert dd.code_select(b)['action']=='WAIT_UNCERTAIN'
    b.pop('own_protocol_observation')
    report=b['peer_reports'][-1]; b['peer_reports']=[report]
    report.update(previous_segment=False,created_at_sim_s=b['sim_time_s']-1,received_at_sim_s=b['sim_time_s']-.5)
    report['body']={'text':'Stop: my grip is slipping.'}
    assert dd.code_select(b)['action']=='WAIT_UNCERTAIN'
    report['previous_segment']=True
    assert dd.code_select(b)['action']=='GO'
    report['previous_segment']=False;report['received_at_sim_s']=None
    assert dd.code_select(b)['action']=='GO'
    report['received_at_sim_s']=b['sim_time_s']-.5;report['body']['text']='Ready, waiting for mutual agreement.'
    assert dd.code_select(b)['action']=='GO'
    report.update(encoding='schema',body={'state':'blocked'})
    assert dd.code_select(b)['action']=='WAIT_UNCERTAIN'
    report['body']['state']='unknown'
    b['dialogue_epoch_age_s']=20
    assert dd.code_select(b)['action']=='WAIT'


@pytest.mark.parametrize('condition,encoding,recipients', [
    ('peer_en','free_en',['r2','r3']), ('leader_en','free_en',['r3']),
    ('structured','schema',['r2','r3']), ('no_comm','none',[])])
def test_code_same_path_no_decision_provider_or_keychain(tmp_path,monkeypatch,condition,encoding,recipients):
    from scripts import d1_dialogue_upstream as upstream
    monkeypatch.setattr(upstream.subprocess,'run',lambda *a,**k:pytest.fail('no Keychain/model command'))
    monkeypatch.setattr(upstream.D1,'select',lambda *a,**k:pytest.fail('no D1 invocation'))
    b=user();b['dialogue_decider']=dd.CODE_MODE
    b['condition']=condition;b['channel'].update(encoding=encoding,can_send_to=recipients)
    if condition=='no_comm':b['peer_reports']=[]
    called=[]
    def speak(req):
        s=json.loads(req['messages'][1]['content'])
        assert s['selected_protocol_action']=='GO' and s['fixed_action']['choice']=='GO'
        assert s['own_grip']=='unknown'
        called.append(req)
        return speech()
    client=upstream.Code(tmp_path)
    raw=client.complete(request(b),'code-call',speak)
    value=json.loads(raw['choices'][0]['message']['content'])
    assert value['action']['choice']=='GO'
    assert raw['ugrp_code_dialogue']['decision_model_calls']==0
    if condition=='no_comm':assert not value['messages'] and not called
    elif encoding=='schema':
        from harness.zone_study_protocol import structured_violations
        assert not called and not structured_violations(value['messages'][0]['message'])
    else:
        assert len(called)==1 and value['messages'][0]['text']=='Ready for this segment; awaiting mutual agreement.'
        with pytest.raises(ValueError,match='SPEECH_ONLY_SCHEMA'):
            client.complete(request(b),'code-injection',lambda _:speech(action={'kind':'claim'}))


def test_code_role_claim_once_and_actual_host_ack(tmp_path,setup_data):
    b=user();b['dialogue_decider']=dd.CODE_MODE
    b['dialogue'].update(key=None,own_claim=False,own_go_sent=False)
    # Start from full projected contract (the fixture has already pruned claim).
    b['action_message_contract']['actions'].append({'kind':'claim'})
    assert dd.code_select(b)['action']=='claim'
    b['dialogue']['own_claim']=True
    assert dd.code_select(b)['action']=='WAIT'
    host,d=opened(tmp_path,setup_data,'off')
    call=SimpleNamespace(call_id='code-live',actor='r1',started_sim_s=6.)
    host.trial.snapshot(call)
    projected=live.project(host.trial.prepare_call(call).request,options=Options(True,True,'en'),
        llm_memory='v1_commands',memory=dict(decisions=[],windows=[],commands=[]),dialogue_decider=dd.CODE_MODE,
        own_protocol_observation=dict(own_grip='unknown',own_alignment='unknown'))
    actual=json.loads(projected['messages'][1]['content'])
    assert actual['own_protocol_observation']['own_grip']=='unknown'
    selected=dd.code_select(actual)
    assert selected['action']=='GO'
    d.check_action(dd.candidates(actual)['GO'],ctx(d),6.5)
    d.votes['r1']=dict(GO=dict(call_id='self-go',at=6.,frame_t=5.9))
    d.votes['r2']=dict(GO=dict(call_id='peer-go',at=6.,frame_t=5.9))
    actual['dialogue']=d.view('r1',7.)
    actual['sim_time_s']=7.
    assert dd.code_select(actual)['action']=='ACK'
    ack=dd.candidates(actual)['ACK']
    assert ack['peer_go_ref']=='peer-go'
    d.check_action(ack,ctx(d,now=7.),7.5)
    d.votes['r1']['ACK']=dict(call_id='self-ack',at=7.5,frame_t=6.9)
    with pytest.raises(ContractViolation,match='MATCHING_CURRENT'):
        d.check_action(ack,ctx(d,now=8.),8.5)


def test_code_own_rgb_hypothesis_and_retry_preserve_slip(monkeypatch):
    import numpy as np
    from harness import owncam_pair_beam as beam
    monkeypatch.setattr(beam,'held_signature',lambda jpeg:np.full((8,8),jpeg==b'visible',dtype=bool))
    robot=SimpleNamespace(servo={1:1500,6:1500},frame=SimpleNamespace(jpeg=None))
    observer=dd.CodeObservation()
    assert observer.observe('r1',robot)['own_grip']=='unknown'  # Closing is not proof.
    robot.frame.jpeg=b'visible'
    observation=observer.observe('r1',robot,aligned=True)
    assert observation['own_grip']=='holding' and observation['own_alignment']=='aligned'
    robot.frame.jpeg=b'vanished'
    assert observer.observe('r1',robot)['own_grip']=='slipping'
    assert observer.observe('r1',robot)['own_grip']=='slipping'  # Repeated call, same image.
    robot.servo[6]=1600
    assert observer.observe('r1',robot)['own_grip']=='unknown'  # Camera motion is not slip.
    robot.servo[1]=500
    assert observer.observe('r1',robot)['gripper_command']=='open'
