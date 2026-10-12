"""DEV Gemini -> Gemma: offline failure/quota/identity tests; no provider or physics."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import gemma_fallback_proxy as gemma
from harness.s4_relay_journal import Journal
from harness.zone_study_llm_driver import usage_summary, load_registry
from harness import zone_study_llm_driver as llm


# Deliberately a fixture name: production has no guessed identifier.
MODEL = {'name': 'models/gemma-4-31b-test-fixture', 'displayName': 'Gemma 4 31B',
         'supportedGenerationMethods': ['generateContent']}
KEYCHAIN_READER = gemma.keychain_key
BODY = json.dumps({'model': 'gemini-3.8-flash', 'messages': [
    {'role': 'system', 'content': 'Use the request_id from the user.'},
    {'role': 'user', 'content': [{'type': 'text', 'text': '{"request_id":"robot-r1"}'},
        {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(b'fixture RGB').decode()}}]}],
    'max_tokens': 1400, 'reasoning_effort': 'none'}).encode()
REPLY = {'modelVersion': 'gemma-4-31b-test-fixture', 'candidates': [
    {'finishReason': 'STOP', 'content': {'parts': [{'text': 'hidden', 'thought': True}, {'text': '{"request_id":"robot-r1"}'}]}}],
    'usageMetadata': {'promptTokenCount': 11, 'candidatesTokenCount': 5, 'thoughtsTokenCount': 3, 'totalTokenCount': 19}}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a, **kw): raise AssertionError('real provider forbidden')
    monkeypatch.setattr(gemma, 'keychain_key', forbidden)


def api(tmp_path, responses=None, now=None):
    calls = []
    replies = list(responses or [(200, copy.deepcopy(REPLY), {})])
    def send(path, payload=None):
        if path.startswith('models?'): return 200, {'models': [MODEL]}, {}
        if path.endswith(':countTokens'):return 200,{'totalTokens':11},{}
        calls.append((path, copy.deepcopy(payload)))
        return replies.pop(0)
    clock=(lambda: now[0]) if now else gemma.time.time
    return gemma.Gemma(tmp_path, send=send, clock=clock,
                       shared_quota=gemma.SharedQuota(tmp_path/'shared',clock=clock)), calls


def test_keychain_missing_never_uses_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gemma.subprocess, 'run', lambda args, **kw: SimpleNamespace(returncode=44, stdout=b''))
    monkeypatch.setattr(gemma, 'keychain_key', KEYCHAIN_READER)
    monkeypatch.setenv('GEMINI_API_KEY', 'must-not-be-used')
    assert gemma.main(['--check', '--output', str(tmp_path)]) == 2
    value=json.loads(capsys.readouterr().out)
    assert value['key_needed'] and value['model_id'] is None
    assert 'must-not-be-used' not in (tmp_path/'check.json').read_text()


def test_default_off_no_key_or_network(capsys):
    assert gemma.main([]) == 0
    assert json.loads(capsys.readouterr().out)['enabled'] is False


def test_models_list_pagination_and_no_substitution():
    paths=[]
    def send(path):
        paths.append(path)
        return (200, {'models': [], 'nextPageToken':'next'} if len(paths)==1 else {'models':[MODEL]}, {})
    model, record=gemma.discover(send)
    assert model==MODEL and record['source']=='models.list' and 'pageToken=next' in paths[1]
    with pytest.raises(ValueError,match='missing_or_ambiguous'):
        gemma.discover(lambda p:(200,{'models':[dict(MODEL,name='models/gemma-3-31b-it',displayName='Gemma 3')]},{}))
    with pytest.raises(ValueError,match='missing_or_ambiguous'):
        gemma.discover(lambda p:(200,{'models':[MODEL,MODEL]},{}))


def test_image_preserved_request_id_and_system():
    result=gemma.generate_body(json.loads(BODY))
    parts=result['contents'][0]['parts']
    assert 'robot-r1' in parts[0]['text']
    assert base64.b64decode(parts[1]['inlineData']['data'])==b'fixture RGB'
    assert result['systemInstruction']['parts'][0]['text'].startswith('Use')
    assert result['generationConfig']['maxOutputTokens']==1400
    remote=json.loads(BODY);remote['messages'][1]['content'][1]['image_url']['url']='http://127.0.0.1/private'
    with pytest.raises(ValueError,match='inline'):gemma.generate_body(remote)


@pytest.mark.parametrize('status',[200,400,401,403,429,500,503])
def test_only_completed_retryable_http_failure_falls_back_once(tmp_path,status):
    engine,calls=api(tmp_path)
    primary_raw=json.dumps({'model':'gemini-real','choices':[], 'error':'bad'}).encode()
    result=gemma.route(lambda:(status,primary_raw,None),BODY,'same-id',fallback=engine)
    assert len(calls)==int(status==429 or status>=500)
    if calls:
        reply=json.loads(result[1]);assert reply['provider']==gemma.PROVIDER and reply['ugrp_route']['request_id']=='same-id'
        assert reply['choices'][0]['message']['content']=='{"request_id":"robot-r1"}'
        assert reply['usage']['completion_tokens']==8
        # Same logical request after a dropped response never reaches Google again.
        cached=json.loads(engine.complete(BODY,'same-id')[1])
        assert cached['choices']==reply['choices'] and cached['id']=='same-id'
        assert len(calls)==1
    else:assert json.loads(result[1])['provider']=='gemini_subscription'


def test_quota_failure_under_403_and_ambiguous_transport(tmp_path):
    engine,calls=api(tmp_path)
    gemma.route(lambda:(403,b'{"error":"quota exhausted"}',None),BODY,'quota-id',fallback=engine)
    assert len(calls)==1
    def ambiguous():raise TimeoutError('no HTTP response')
    with pytest.raises(TimeoutError):gemma.route(ambiguous,BODY,'another',fallback=engine)
    assert len(calls)==1


def test_429_daily_limits_hold_new_requests_and_survive_restart(tmp_path):
    now=[1791712800.]
    quota={'error':{'details':[{'@type':'type.googleapis.com/google.rpc.QuotaFailure',
        'violations':[{'quotaId':'GenerateRequestsPerDayPerProjectPerModel-FreeTier','quotaValue':'1500'}]},
        {'@type':'type.googleapis.com/google.rpc.RetryInfo','retryDelay':'20s'}]}}
    engine,calls=api(tmp_path,[(429,quota,{'Retry-After':'20'})],now)
    assert engine.complete(BODY,'one')[0]==429
    assert engine.complete(BODY,'one')[0]==429 and len(calls)==1
    assert engine.complete(BODY,'two')[0]==429 and len(calls)==1
    engine2,calls2=api(tmp_path,now=now)
    assert engine2.complete(BODY,'three')[0]==429 and not calls2
    state=json.loads((tmp_path/'quota.json').read_text())
    assert state['rpd']==1500 and state['hold_until']==engine.quota.midnight()


def test_observed_rpm_and_rpd_local_reservations(tmp_path):
    now=[1791712800.]
    engine,calls=api(tmp_path,[(200,REPLY,{'X-RateLimit-Limit-Requests-Minute':'1','X-RateLimit-Limit-Requests-Day':'2'}),
                               (200,REPLY,{})],now)
    assert engine.complete(BODY,'one')[0]==200
    assert engine.complete(BODY,'two')[0]==429 and len(calls)==1
    now[0]+=61
    assert engine.complete(BODY,'three')[0]==200 and len(calls)==2
    now[0]+=61
    assert engine.complete(BODY,'four')[0]==429 and len(calls)==2


def test_image_probe_gate_and_non_stop(tmp_path):
    engine,_=api(tmp_path)
    with pytest.raises(ValueError,match='image_probe_required'):engine.require_image_probe()
    gemma.write(tmp_path/'image-probe.json',dict(model_id=engine.model_id,image_input_confirmed=True))
    engine.require_image_probe()
    response=copy.deepcopy(REPLY);response['candidates'][0]['finishReason']='MAX_TOKENS'
    assert gemma.openai_reply(response,engine.model_id,'id')['choices'][0]['finish_reason']=='length'
    del response['usageMetadata']
    assert gemma.openai_reply(response,engine.model_id,'id')['usage'] is None


def test_fallback_journal_429_is_terminal_once(tmp_path):
    journal=Journal(tmp_path,retry_rate_limits=False);calls=[]
    def send():calls.append(1);return 429,b'{}','1'
    key=hashlib.sha256(BODY).hexdigest()
    journal.call(key,BODY,send)
    assert journal.call(key,BODY,send)[1]=='cached' and calls==[1]


def test_registry_main_unchanged_and_study_not_admitted():
    registry=load_registry();dev=registry['driver_profiles'][gemma.PROFILE]
    assert dev['enabled_by_default'] is False and dev['scope']=='DEV_only'
    assert dev['fallback']['model_id_source'].startswith('models.list')
    assert registry['driver_profiles']['main_study_gemini_v1']['proxy_url']=='http://127.0.0.1:8391/v1/chat/completions'
    assert all(gemma.PROFILE not in b['driver_profiles'] for b in registry['bundles'].values())


def test_summary_separates_actual_models():
    def row(provider,model):return dict(status='sent',response_provider=provider,response_model=model,
        provider_usage={'prompt_tokens':11,'completion_tokens':8,'total_tokens':19},usage_known=True,
        latency_ms=10,failure_class=None)
    summary=usage_summary([row('gemini_subscription','gemini-real'),row(gemma.PROVIDER,'gemma-real')])
    assert summary['by_model']['gemini_subscription/gemini-real']['requests']==1
    assert summary['by_model'][gemma.PROVIDER+'/gemma-real']['tokens_total_known']==19


def test_metadata_reaches_real_ledger_and_summary(tmp_path):
    from tests.test_zone_study_llm_driver import budget_for, PROFILE
    from harness.pair_llm_live import PairLiveLedger, live_records
    from harness.zone_send_ledger import completion_body
    from urllib.request import Request
    from urllib.error import HTTPError
    budget=budget_for(tmp_path)
    budget.start_run('dev',cohort_id='pilot-A',bundle_id='fixture-dev',bundle_sha256='b'*64,
                     record={'research_result':False})
    response=json.loads(completion_body('{"request_id":"robot-r1","action":{},"decision_sources":[],"messages":[]}',
        usage={'prompt_tokens':11,'completion_tokens':8,'total_tokens':19},model='gemma-real'))
    response.update(provider=gemma.PROVIDER,ugrp_route={'request_id':'same-id','attempts':[
        {'provider':'gemini_subscription','model':'gemini-real','status':429,'usage':None},
        {'provider':gemma.PROVIDER,'model':'gemma-real','status':200,'usage':response['usage']}]})
    ledger=PairLiveLedger(store_dir=tmp_path/'wire',budget=budget,run_key='dev',profile=PROFILE,
                          wire=lambda *a,**kw:io.BytesIO(json.dumps(response).encode()))
    row={'call_id':'fixture','actor':'r1','seq':1,'body_sha256':hashlib.sha256(BODY).hexdigest(),'bytes':len(BODY),
         'url':PROFILE['proxy_url'],'status':'sent','latency_ms':1}
    ledger.entries.append(row)
    ledger._store(row,'request',BODY)
    ledger._store(row,'response',json.dumps(response).encode())
    record=live_records(ledger)
    assert record['rows'][0]['response_provider']==gemma.PROVIDER
    assert record['usage']['by_model'][gemma.PROVIDER+'/gemma-real']['tokens_total_known']==19
    assert record['usage']['upstream_by_model']['gemini_subscription/gemini-real']['http_errors']==1
    failure=dict(response,error='quota');failure.pop('choices')
    error=HTTPError('http://fixture',429,'quota',{'Retry-After':'60'},io.BytesIO(json.dumps(failure).encode()))
    ledger._keep_error_response('fixture',error)
    assert llm.call_rows(ledger)[0]['response_model']=='gemma-real'


def test_gemma_toggle_dry_run_and_original_admission_still_closed(tmp_path,capsys):
    import inspect
    from scripts import run_s4_pair_live12 as run
    assert inspect.signature(run.bundle).parameters['gemma_fallback'].default is False
    assert run.main(['--expected-source-sha','a'*40,'--condition','no_comm','--seed','601',
        '--output',str(tmp_path/'not-created'),'--relay-receipt',str(tmp_path/'not-read'),
        '--gemma-fallback'])==0
    assert json.loads(capsys.readouterr().out)['gemma_fallback'] is True
    assert not (tmp_path/'not-created').exists()
    with pytest.raises(ValueError,match='OWN_MAP_TRANSPORT_NOT_CONNECTED'):
        run.run({'gemma_fallback':True},tmp_path/'never',tmp_path/'never-read')


def test_key_never_in_url_prompt_or_persisted_error(tmp_path,monkeypatch):
    key='fixture-credential-not-a-real-key'
    monkeypatch.setattr(gemma,'keychain_key',lambda:key)
    seen=[]
    class Opener:
        def open(self,request,**kwargs):
            seen.append(request)
            from urllib.error import HTTPError
            raise HTTPError(request.full_url,429,'quota',{'Retry-After':'60'},
                io.BytesIO(json.dumps({'error':{'message':key}}).encode()))
    monkeypatch.setattr(gemma,'no_redirect_opener',lambda:Opener())
    status,body,headers=gemma.google('models/fixture:generateContent',{'contents':[{'parts':[{'text':'RGB test'}]}]})
    assert status==429 and body['error']['message']=='[REDACTED_SECRET]'
    assert seen[0].get_header('X-goog-api-key')==key
    assert key not in seen[0].full_url and key.encode() not in seen[0].data


def test_ambiguous_google_failure_is_cached_without_another_call(tmp_path):
    calls=[]
    def send(path,payload=None):
        if path.startswith('models?'):return 200,{'models':[MODEL]},{}
        if path.endswith(':countTokens'):return 200,{'totalTokens':11},{}
        calls.append(1);raise TimeoutError('ambiguous Google response')
    engine=gemma.Gemma(tmp_path,send=send,shared_quota=gemma.SharedQuota(tmp_path/'shared'))
    assert engine.complete(BODY,'same-id')[0]==502
    assert engine.complete(BODY,'same-id')[0]==502 and calls==[1]
    assert 'ambiguous' in (tmp_path/'ledger.jsonl').read_text()


def test_same_logical_key_survives_changed_wire_attempt_id(tmp_path):
    engine,calls=api(tmp_path)
    key=hashlib.sha256(b'run:logical-request').hexdigest()
    one=gemma.route(lambda:(429,b'{"error":"quota"}',None),BODY,'wire-attempt-1',fallback=engine,idempotency_key=key)
    two=gemma.route(lambda:(429,b'{"error":"quota"}',None),BODY,'wire-attempt-2',fallback=engine,idempotency_key=key)
    assert len(calls)==1
    assert json.loads(one[1])['choices']==json.loads(two[1])['choices']


def test_standard_model_pin_input_count_cap_and_no_fallback(tmp_path):
    calls=[];count=[2501];model={**MODEL,'version':'001'}
    def send(path,payload=None):
        if path.startswith('models?'):return 200,{'models':[model]},{}
        if path.endswith(':countTokens'):return 200,{'totalTokens':count[0]},{}
        calls.append(path);return 200,REPLY,{}
    with pytest.raises(ValueError,match='version_drift'):
        gemma.Gemma(tmp_path/'bad',send=send,expected_version='002',shared_quota=gemma.SharedQuota(tmp_path/'quota'))
    engine=gemma.Gemma(tmp_path/'good',send=send,standard=True,expected_version='001',shared_quota=gemma.SharedQuota(tmp_path/'quota'))
    with pytest.raises(ValueError,match='single_model_profile_mismatch'):engine.complete(BODY,'wrong-model')
    body=json.loads(BODY);body['model']=engine.model_id
    result=engine.complete(json.dumps(body).encode(),'too-large')
    assert result[0]==400 and not calls
    assert b'2500' in result[1]


def test_global_bucket_hold_can_retry_same_id_without_duplicate_generation(tmp_path):
    now=[1791740000.];engine,calls=api(tmp_path,now=now)
    with engine.shared_quota.locked() as state:
        state.update(updated=now[0],tokens=0,requests=0)
    first=engine.complete(BODY,'queued')
    assert first[0]==429 and not calls
    now[0]+=61
    assert engine.complete(BODY,'queued')[0]==200 and len(calls)==1
    assert engine.complete(BODY,'queued')[0]==200 and len(calls)==1
    value=json.loads(first[1]);assert value['ugrp_upstream_forwarded'] is False and value['usage']['total_tokens']==0
    row=dict(status='sent',response_provider=gemma.PROVIDER,response_model=engine.model_id,
        provider_usage=value['usage'],usage_known=True,latency_ms=1,failure_class=None,
        upstream_forwarded=False,quota_wait=value['quota_wait'])
    report=usage_summary([row]);assert report['upstream_generation_requests_confirmed']==0
    assert report['local_quota_wait_responses']==1 and report['tokens_total_known']==0


def test_concurrent_provider_calls_do_not_hold_quota_lock(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    barrier=threading.Barrier(2);seen=[]
    def send(path,payload=None):
        if path.startswith('models?'):return 200,{'models':[MODEL]},{}
        if path.endswith(':countTokens'):return 200,{'totalTokens':11},{}
        seen.append(path);barrier.wait(timeout=3)
        return 200,REPLY,{}
    engine=gemma.Gemma(tmp_path,send=send,shared_quota=gemma.SharedQuota(tmp_path/'shared'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda i:engine.complete(BODY,'parallel-'+str(i)),range(2)))
    assert [r[0] for r in results]==[200,200] and len(seen)==2
    state=json.loads((tmp_path/'shared/bucket.json').read_text())
    assert state['day_requests']==2 and len(state['window'])==2
