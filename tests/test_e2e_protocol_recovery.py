"""Real scheduler/parser/dispatch with fake provider; no physics/provider."""
import copy,json,io
from types import SimpleNamespace
import pytest
from harness import e2e_s4_live as live
from harness.e2e_protocol_recovery import Recovery,OPTION
from harness.s4_event_policy import Options
from harness.zone_final_pair_binding import bind
from tests.test_e2e_dialogue import build,Wire
from tests.test_pair_llm_s4_host import setup_data,no_external_work,advance


def factory(*args,**kwargs):
    for link in kwargs['links'].values():
        link.inner.study_options=Options(True,True,'en');link.inner.protocol_recovery=OPTION
    return live.Host(*args,**kwargs)


def test_actual_invalid_envelope_is_rejected_then_fresh_reask_delivers(tmp_path,setup_data,monkeypatch):
    original=Wire.__call__
    def malformed_once(self,request,**kwargs):
        response=json.loads(original(self,request,**kwargs).read())
        value=json.loads(response['choices'][0]['message']['content'])
        if value['messages'] and not getattr(self,'broke_envelope',False):
            self.broke_envelope=True;self.sent.discard('r1')
            value['messages'][0]['contract']=value['messages'][0]['contract']['route']
            response['choices'][0]['message']['content']=json.dumps(value)
        return io.BytesIO(json.dumps(response).encode())
    monkeypatch.setattr(Wire,'__call__',malformed_once)
    host,inner,wire=bind(build,s4=SimpleNamespace(Host=factory))(tmp_path,setup_data)
    advance(host,inner,1,30)
    events=host.trial.protocol_reasks.events
    assert len(events)==1 and events[0]['accepted_action_replayed'] is False
    assert host.trial.scheduler.ledger[events[0]['invalid_call_id']]['status']=='failed'
    assert host.trial.dialogue.proposal is not None and host.trial.dialogue.approved
    assert host.trial.dialogue.claims=={'r1','r2'}
    assert events[0]['invalid_call_id'] not in host.trial.dialogue.outgoing_by_call
    call=SimpleNamespace(call_id='inspect',actor='r1',started_sim_s=31.)
    host.trial.snapshot(call)
    projected=host.trial.prepare_call(call).request
    body=json.loads(projected['messages'][1]['content'])
    assert body['route_contract_example']==body['own_route_proposal']
    assert set(body['route_contract_example'])=={'kind','route','source_message_id'}


@pytest.mark.parametrize('finish,status,retries',[('stop','failed',2),('length','failed',0),('stop','completed',0)])
def test_bounded_pre_epoch_only_retry_and_non_normal_remains_inert(finish,status,retries):
    scheduled=[];calls=[];ledger={};captures={}
    dialogue=SimpleNamespace(captures=captures,key=None,view=lambda *a:dict(route_hash=None,approved=False,own_claim=False))
    trial=SimpleNamespace(dialogue=dialogue,links={'r1':SimpleNamespace(inner=SimpleNamespace(own_inputs_at=lambda t:dict(own_route=dict(route_hash='a'*64))))},scheduler=SimpleNamespace(calls=calls,ledger=ledger,trigger=lambda *a,**k:scheduled.append((a,k))))
    recovery=Recovery()
    for n in range(5):
        cid=str(n);calls.append(SimpleNamespace(call_id=cid,actor='r1',notes={}))
        ledger[cid]=dict(status=status,completion=dict(finish_reason=finish))
        captures[cid]=dict(view=dict(key=None),state=dict(own_route=dict(route_hash='a'*64)))
        recovery.poll(trial,float(n*10));recovery.poll(trial,float(n*10))
    assert len(scheduled)==retries
    dialogue.key=('order-5','a'*64,1,0);recovery.poll(trial,60.)
    assert len(scheduled)==retries
