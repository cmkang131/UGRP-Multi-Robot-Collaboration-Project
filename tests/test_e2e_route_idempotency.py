import json,io,copy
from types import SimpleNamespace
import pytest
from harness import e2e_s4_live as live
from harness.s4_event_policy import Options
from harness.zone_final_pair_binding import bind
from harness.e2e_route_idempotency import origin,OPTION
from tests.test_e2e_dialogue import build,Wire,notification
from tests.test_pair_llm_s4_host import setup_data,no_external_work,advance


@pytest.mark.parametrize('option,completed',[('off',False),(OPTION,True)])
def test_actual_repeated_model_proposal_preserves_received_approval_and_claims(tmp_path,setup_data,monkeypatch,option,completed):
    original=Wire.__call__
    def repeat(self,request,**kwargs):
        response=json.loads(original(self,request,**kwargs).read());value=json.loads(response['choices'][0]['message']['content'])
        body=json.loads(request.data);payload=json.loads(next(x['text'] for x in body['messages'][-1]['content'] if x['type']=='text'))
        if payload['robot_id']=='r1' and payload.get('own_route_proposal') and value['action']['kind']=='continue':
            value['messages']=[notification(self.arm,'r2',payload['own_route_proposal'])]
            response['choices'][0]['message']['content']=json.dumps(value)
        return io.BytesIO(json.dumps(response).encode())
    monkeypatch.setattr(Wire,'__call__',repeat)
    def factory(*args,**kw):
        for link in kw['links'].values():
            link.inner.study_options=Options(True,True,'en');link.inner.protocol_progress='stage_retry_v1'
        host=live.Host(*args,**kw);host.trial.dialogue.protocol_idempotency=option;return host
    host,inner,wire=bind(build,s4=SimpleNamespace(Host=factory))(tmp_path,setup_data)
    advance(host,inner,1,55)
    d=host.trial.dialogue
    assert (d.approved and d.claims=={'r1','r2'})==completed, (d.events,host.trial.scheduler.ledger)
    if completed:
        assert len(d.outgoing_by_call)>1 and len(set(d.outgoing_by_call.values()))==1
        assert d.proposal['message_id'] in d.origins
        assert {x['robot_id'] for x in d.events if x['kind']=='claim'}=={'r1','r2'}


def test_distinct_route_or_leader_forward_is_not_collapsed():
    route={'route_hash':'a','map_version':1};d=SimpleNamespace(proposal=dict(route=route,origin='old'),protocol_idempotency=OPTION)
    assert origin(d,dict(route=copy.deepcopy(route),source_message_id=None),'new')=='old'
    assert origin(d,dict(route={'route_hash':'b','map_version':2},source_message_id=None),'new')=='new'
    assert origin(d,dict(route=route,source_message_id='leader-forward'),'new')=='new'
