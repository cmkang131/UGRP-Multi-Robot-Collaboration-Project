import json,pytest
from harness.task_planner_model import DEEPSEEK,ModelSelection,ModelBudgetExceeded
from scripts.openrouter_upstream import upstream_body,OpenRouter

def test_pinned_fp8_reasoning_off_json_and_legacy_defaults():
    body=upstream_body({'model':DEEPSEEK.wire_model,'messages':[],'max_tokens':768},selection=DEEPSEEK)
    assert body['provider']=={'order':['deepinfra/fp8'],'allow_fallbacks':False,'require_parameters':True}
    assert body['reasoning']=={'enabled':False} and body['response_format']=={'type':'json_object'}
    assert DEEPSEEK.response_provider=='DeepInfra'
    assert ModelSelection().model=='google/gemma-4-31b-it'
    from scripts.openrouter_ling_policy import reserve_cost
    assert reserve_cost(body,DEEPSEEK)==pytest.approx((len(json.dumps(body,ensure_ascii=True).encode())+4096)*.00000014+768*.00000042)

def test_deepseek_http_cap_checked_before_send_and_identity(tmp_path):
    calls=[]
    def send(body,key):
        calls.append(body)
        return 200,json.dumps({'model':DEEPSEEK.model,'provider':'DeepInfra','choices':[{}],'usage':{'cost':.0001}}).encode(),None,{}
    m=OpenRouter(tmp_path,key='fixture',selection=DEEPSEEK,send=send,max_attempts=3,max_calls=1,max_usd=.30,
                 rate_limit_policy='planner_rate_limit_v1',sleep=lambda _:None)
    raw=json.dumps({'model':DEEPSEEK.wire_model,'messages':[],'max_tokens':768}).encode()
    assert m.complete(raw,'first')[0]==200
    with pytest.raises(ModelBudgetExceeded):m.complete(raw,'second')
    assert len(calls)==1

def test_abnormal_json_included_in_format_guard_without_changing_legacy(monkeypatch):
    from scripts import check_task_planner_ling as c
    monkeypatch.setattr(c,'COUNT_ABNORMAL_FORMAT',True)
    monkeypatch.setattr(c,'RESPONSE_PARSER','first_object_v1')
    monkeypatch.setattr(c,'MIN_RATE_DECISIONS',20)
    bad={'request':{'input':{'candidates':[]}},'response':'{"act":','failure':'RuntimeError'}
    assert c.format_error(bad)
    row={'called':True,'wall_s':1,'fallback':False,'audit':[]}
    assert c.guard([row]*18+[{**row,'audit':[bad]}]*2)=='FORMAT_ERROR_RATE_OVER_5_PERCENT'
    monkeypatch.setattr(c,'COUNT_ABNORMAL_FORMAT',False)
    assert not c.format_error(bad)

def test_deepseek_image_hash_and_end_position():
    import base64,hashlib
    from harness.task_planner_gemma import Gemma,Budget
    client=Gemma.__new__(Gemma);client.selection=DEEPSEEK;client.planner_prompt_order='static_first_v2';client.budget=Budget();client.run_id='test'
    sent=[]
    def post(path,**kwargs):
        sent.append(kwargs['body'])
        return dict(model=DEEPSEEK.model,provider='DeepInfra',usage={'cost':0},choices=[{'message':{'content':'{}'},'finish_reason':'stop'}])
    client._json=post;image=b'own-image'
    req={'system':'s','input':{'own':{'rgb':{'sha256':hashlib.sha256(image).hexdigest(),'image_b64':base64.b64encode(image).decode()}}}}
    client(req,timeout_s=1)
    assert sent[0]['messages'][-1]['content'][-1]['type']=='image_url'
    assert sent[0]['reasoning']=={'enabled':False}
    req['input']['own']['rgb']['sha256']='wrong'
    with pytest.raises(ValueError):client(req,timeout_s=1)
    assert len(sent)==1
