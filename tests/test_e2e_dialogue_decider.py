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
    bad=copy.deepcopy(new);bad['e2e_options']['dialogue_decider']='gemma_v0'
    with pytest.raises(ValueError):require_current(bad,ROOT)


def test_visual_uncertainty_removes_go_and_real_journal_accepts_speech_key(tmp_path):
    from scripts.s4_proxy_relay import speech_idempotency_key
    from harness.s4_relay_journal import Journal
    for grip in ('unknown','slipping','not_held'):
        q=dd.decision_request(request(user()),dict(own_grip=grip,own_alignment='unknown'))
        assert set(q['questions']['action']['criteria'])=={'WAIT','WAIT_UNCERTAIN'}
    journal=Journal(tmp_path/'journal');key=speech_idempotency_key('a'*64)
    value,disposition=journal.call(key,b'request',lambda:(200,b'ok',None))
    assert value[0]==200 and disposition=='forwarded'
    value,disposition=journal.call(key,b'request',lambda:pytest.fail('must reuse'))
    assert disposition=='cached'
