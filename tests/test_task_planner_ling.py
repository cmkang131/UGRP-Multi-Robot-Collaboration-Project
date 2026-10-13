import concurrent.futures
import copy
import json
import pytest
from harness.task_planner_model import ModelSelection, ModelBudgetExceeded
from scripts.openrouter_upstream import OpenRouter, upstream_body
from scripts.check_task_planner_ling import SharedBudget, ModelBudget, frozen, MAX_CALLS


def test_selected_request_and_model_provider_validation(tmp_path):
    selection=ModelSelection('inclusionai/ling-3.0-flash-vl','Novita','off')
    request=dict(model=selection.wire_model,messages=[],temperature=0,max_tokens=768)
    payload=upstream_body(request,selection=selection)
    assert payload['reasoning']=={'enabled':False}
    assert payload['provider']=={'order':['Novita'],'allow_fallbacks':False}
    assert payload['model']==selection.model
    sent=[]
    def send(body,key):
        sent.append(body)
        return 200,json.dumps(dict(model='wrong',provider='Novita',choices=[{}])).encode(),None
    m=OpenRouter(tmp_path,key='fake',send=send,selection=selection,max_attempts=1,max_calls=440)
    assert m.complete(json.dumps(request).encode(),'one')[0]==502
    assert len(sent)==1


def test_actual_http_440_boundary_persists_and_no_hidden_retry(tmp_path):
    sent=[]
    def send(body,key):sent.append(1);return 503,b'{}',None
    m=OpenRouter(tmp_path,key='fake',send=send,max_attempts=1,max_calls=440)
    raw=b'{"model":"gemma-4-31b-it"}'
    for i in range(440):m.complete(raw,str(i))
    with pytest.raises(ModelBudgetExceeded):m.complete(raw,'441')
    assert len(sent)==440
    restarted=OpenRouter(tmp_path,key='fake',send=send,max_attempts=1,max_calls=440)
    with pytest.raises(ModelBudgetExceeded):restarted.complete(raw,'restart')
    assert len(sent)==440


def test_shared_spending_and_concurrent_call_cap():
    shared=SharedBudget(lambda:{'limit_remaining':10})
    budget=ModelBudget(shared,.00001)
    def call(_):
        try:budget.reserve();budget.reconcile(.000001);return True
        except ModelBudgetExceeded:return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:accepted=list(pool.map(call,range(700)))
    assert sum(accepted)==MAX_CALLS==budget.calls
    assert shared.actual==pytest.approx(.0006)
    for i in range(0):budget.repair()
    with pytest.raises(ValueError):budget.repair()
    # Missing usage retains its entire reservation, never counts as zero cost.
    shared=SharedBudget(lambda:{'limit_remaining':10});shared.reserve(.05);shared.reconcile(.05,None)
    with pytest.raises(ModelBudgetExceeded):shared.reserve(.04)
    assert shared.unknown==1 and shared.actual==0 and shared.charged==.05
    floor=SharedBudget(lambda:{'limit_remaining':1.57})
    with pytest.raises(ModelBudgetExceeded):floor.reserve(.001)


def test_budget_stop_escapes_planner_before_fallback():
    from harness.task_planner import Planner,candidate
    p=Planner('r1','no_comm')
    ctx=p.context(now=0,orders=[],static_map={},own={"robot_id":"r1"},candidates=[candidate('search',dict(area='door'))],task='Look')
    def stop(*args,**kwargs):raise ModelBudgetExceeded('stop')
    with pytest.raises(ModelBudgetExceeded):p.decide(ctx,stop)


def test_r4_input_and_rules_are_frozen_when_local_evidence_available():
    from scripts.check_task_planner_ling import BASELINE
    if not (BASELINE/'calls.jsonl.zst').exists():pytest.skip('local preserved r4 evidence not in CI')
    from harness.task_planner import Planner,ModelReply
    rows,manifest=frozen()
    for r in rows:
        req=r['audit'][0]['request'];ctx=req['input'];p=Planner('r1',r['condition'],planner_evidence_gate='on_v1')
        def echo(request,**kwargs):
            assert request==req
            c=ctx['candidates'][0]
            return ModelReply(json.dumps(dict(act=c['act'],args=c['args'],message='',reason='test')),'stop',0,{})
        p.decide(copy.deepcopy(ctx),echo)
    assert manifest['decisions_per_model']==400
    assert sum(manifest['expected_usd_from_gemma_tokens'].values())<.15


def test_static_first_preserves_all_content_and_off_bytes():
    from harness.task_planner_model import ordered_context,STATIC_KEYS,DYNAMIC_KEYS
    ctx={'now_s':1,'schema':'s','own':{'x':2},'task':'go','robot_id':'r1','condition':'peer_en','events':[],
         'order_sheet':[],'static_map':{},'public_rules':{},'can_send_to':[],'candidates':[],
         'own_act_results':[],'received_messages':[],'evidence_gate':{'reports':[]}}
    before=json.dumps(ctx)
    assert json.dumps(ordered_context(ctx,'off'))==before
    ordered=ordered_context(ctx,'static_first_v1')
    assert ordered==ctx and tuple(ordered)[:len(STATIC_KEYS)+len(DYNAMIC_KEYS)]==STATIC_KEYS+DYNAMIC_KEYS


def test_ling_image_hash_wire_and_usage():
    import base64,hashlib
    from harness.task_planner_gemma import Gemma,Budget
    from harness.task_planner_model import LING
    m=Gemma.__new__(Gemma);m.budget=Budget();m.run_id='test';m.selection=LING;m.planner_prompt_order='static_first_v1'
    seen=[]
    def post(path,**kwargs):
        seen.append(kwargs['body'])
        return dict(model=LING.model,provider=LING.provider,usage=dict(cost=0,prompt_tokens=100,prompt_tokens_details={'cached_tokens':50}),
            choices=[dict(message=dict(content='{}'),finish_reason='stop')])
    m._json=post
    raw=b'fixture-image';req=dict(system='s',input=dict(now_s=1,schema='s',own=dict(rgb=dict(image_b64=base64.b64encode(raw).decode(),sha256=hashlib.sha256(raw).hexdigest()))))
    reply=m(req,timeout_s=1)
    assert seen[0]['model']==LING.model and seen[0]['reasoning']=={'enabled':False}
    assert seen[0]['messages'][1]['content'][1]['type']=='image_url'
    assert reply.usage['prompt_tokens_details']['cached_tokens']==50
    req['input']['own']['rgb']['sha256']='bad'
    with pytest.raises(ValueError):m(req,timeout_s=1)
    assert len(seen)==1


def test_stop_thresholds():
    from scripts.check_task_planner_ling import guard
    good={'called':True,'wall_s':1,'audit':[{'request':{}}]}
    bad={'called':True,'wall_s':1,'audit':[{'request':{},'rejection':'shape'}]}
    assert guard([good]*19+[bad]) is None
    assert guard([good]*18+[bad])=='FORMAT_ERROR_RATE_OVER_5_PERCENT'
    assert guard([{**good,'wall_s':8.1}])=='MEDIAN_LATENCY_OVER_8_SECONDS'


def test_ling_receipt_is_only_admitted_with_matching_explicit_selection():
    import hashlib
    from pathlib import Path
    from harness.task_planner_model import LING
    from harness.s4_live_transport import validate_receipt
    from harness.zone_study_llm_driver import HostError
    from scripts import openrouter_upstream as orp
    root=Path(orp.__file__).resolve().parents[1];sha=hashlib.sha256(Path(orp.__file__).read_bytes()).hexdigest()
    cfg=dict(orp.config(selection=LING,max_attempts=1),source_sha256=sha,
        selection_source_sha256=hashlib.sha256((root/'harness/task_planner_model.py').read_bytes()).hexdigest())
    r=dict(schema='ugrp.s4_ssh_proxy.v1',remote_url='http://127.0.0.1:18393/v1/chat/completions',
        proxy=dict(source_sha256=sha),driver_profile='study_gemma4_31b_v1',single_model=True,
        fallback_enabled=False,task_planner_v1=True,upstream='openrouter_v1',openrouter_v1=cfg,
        checked_unix=100,valid_for_s=3600,audit_per_post=True,
        authentication='existing_mac_proxy_no_credentials_transferred')
    assert validate_receipt(r,now=101,remote_url=r['remote_url'],planner_selection=LING)==r
    with pytest.raises(HostError):validate_receipt(r,now=101,remote_url=r['remote_url'])


def test_retry_after_pacing_safe_errors_and_cost_ledger(tmp_path):
    from scripts.openrouter_upstream import OpenRouter
    from harness.task_planner_model import LING
    now=[0.];waits=[];sent=[]
    def sleep(delay):waits.append(delay);now[0]+=delay
    def send(body,key):
        sent.append(now[0]);now[0]+=.1
        if len(sent)==1:
            return 429,json.dumps({'error':{'message':'Bearer SECRET sk-or-secret','metadata':{'provider_name':'Novita'}}}).encode(),'4',{'Retry-After':'4','X-RateLimit-Limit':'30','Authorization':'SECRET','Set-Cookie':'SECRET'}
        return 200,json.dumps(dict(model=LING.model,provider='Novita',choices=[{}],usage={'cost':.0001})).encode(),None,{}
    m=OpenRouter(tmp_path,key='SECRET',selection=LING,send=send,sleep=sleep,monotonic=lambda:now[0],
        random_fn=lambda:.5,max_attempts=3,max_calls=600,max_usd=.08,rate_limit_policy='ling_rate_limit_v1')
    raw=json.dumps({'model':LING.model,'max_tokens':768,'messages':[]}).encode()
    assert m.complete(raw,'one')[0]==200
    assert sent==[0,4.1] and waits==[4]
    m.complete(raw,'two')
    assert sent[2]>=6.1
    evidence=(tmp_path/'http_responses.jsonl').read_text()
    assert 'SECRET' not in evidence and 'sk-or-secret' not in evidence and 'set-cookie' not in evidence
    rows=[json.loads(x) for x in evidence.splitlines()]
    assert rows[0]['headers']['x-ratelimit-limit']=='30' and rows[0]['retry_wait_source']=='retry_after'
    assert rows[0]['error_body']['error']['metadata']['provider_name']=='Novita'
    assert m.actual_cost==pytest.approx(.0002) and m.calls==3
    restarted=OpenRouter(tmp_path,key='SECRET',selection=LING,send=send,rate_limit_policy='ling_rate_limit_v1',max_usd=.08)
    assert restarted.calls==3 and restarted.accounted==pytest.approx(m.accounted)


def test_ling_exponential_jitter_and_bounded_retry(tmp_path):
    from scripts.openrouter_upstream import OpenRouter
    from scripts.openrouter_ling_policy import retry_delay
    from harness.task_planner_model import LING
    assert retry_delay(1,{},.5,0)==(1.,'exponential_full_jitter')
    assert retry_delay(2,{},.5,0)==(2.,'exponential_full_jitter')
    assert retry_delay(1,{'retry-after':'Thu, 01 Jan 1970 00:00:10 GMT'},.5,0)==(10.,'retry_after')
    n=[];clock=[0.]
    def send(body,key):n.append(1);return 503,b'{"error":{"message":"capacity"}}',None,{}
    m=OpenRouter(tmp_path,key='fake',selection=LING,send=send,rate_limit_policy='ling_rate_limit_v1',max_calls=600,max_attempts=3,
        sleep=lambda s:clock.__setitem__(0,clock[0]+s),monotonic=lambda:clock[0],random_fn=lambda:.5)
    assert m.complete(json.dumps({'model':LING.model}).encode(),'one')[0]==503
    assert len(n)==3 and m.calls==3
    with pytest.raises(ValueError):OpenRouter(tmp_path/'bad',key='fake',rate_limit_policy='ling_rate_limit_v1')


def test_fallback_stop_counts_actual_called_decisions():
    from scripts.check_task_planner_ling import guard
    good={'called':True,'fallback':False,'wall_s':1,'audit':[{'request':{}}]}
    bad={**good,'fallback':True}
    assert guard([good]*19+[bad]) is None
    assert guard([good]*18+[bad])=='FALLBACK_RATE_OVER_5_PERCENT'


def test_gemma_fp4_tag_and_returned_provider_are_separate(tmp_path):
    from harness.task_planner_model import GEMMA_FP4
    from scripts.openrouter_ling_policy import reserve_cost
    from scripts.openrouter_upstream import config
    request=dict(model=GEMMA_FP4.wire_model,messages=[],temperature=0,max_tokens=768)
    body=upstream_body(request,selection=GEMMA_FP4)
    assert body['provider']=={'order':['deepinfra/turbo'],'allow_fallbacks':False}
    assert GEMMA_FP4.response_provider=='DeepInfra'
    assert reserve_cost(body,GEMMA_FP4)>reserve_cost(body)
    assert config(selection=GEMMA_FP4,rate_limit_policy='planner_rate_limit_v1')['rate_limit_parameters']['max_concurrent']==1
    def send(body,key):
        return 200,json.dumps(dict(model=GEMMA_FP4.model,provider='DeepInfra',choices=[{}],usage={'cost':.0004})).encode(),None
    m=OpenRouter(tmp_path,key='fake',send=send,selection=GEMMA_FP4,max_calls=600,max_usd=.3,rate_limit_policy='planner_rate_limit_v1')
    assert m.complete(json.dumps(request).encode(),'fp4')[0]==200
    assert m.calls==1 and m.actual_cost==pytest.approx(.0004)
    def wrong(body,key):return 200,json.dumps(dict(model=GEMMA_FP4.model,provider='Novita',choices=[{}])).encode(),None
    m=OpenRouter(tmp_path/'wrong',key='fake',send=wrong,selection=GEMMA_FP4,max_attempts=1)
    assert m.complete(json.dumps(request).encode(),'wrong')[0]==502


def test_zero_http_start_failure_can_be_reported(tmp_path):
    from scripts.check_task_planner_ling import read_ledger
    assert read_ledger(tmp_path/'http_responses.jsonl')==[]
