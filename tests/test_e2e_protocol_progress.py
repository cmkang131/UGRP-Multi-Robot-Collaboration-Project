import io,json,copy
from types import SimpleNamespace
import pytest
from harness import e2e_s4_live as live
from harness.e2e_protocol_progress import prompt,phase,Reminders,OPTION
from harness.s4_event_policy import Options
from harness.zone_final_pair_binding import bind
from tests.test_e2e_dialogue import build,Wire
from tests.test_pair_llm_s4_host import setup_data,no_external_work,advance


def test_actual_valid_continue_gets_fresh_reminder_then_model_claim(tmp_path,setup_data,monkeypatch):
    original=Wire.__call__
    def uncertain_once(self,request,**kwargs):
        response=json.loads(original(self,request,**kwargs).read());value=json.loads(response['choices'][0]['message']['content'])
        if value['action']['kind']=='claim' and not getattr(self,'delayed_claim',False):
            self.delayed_claim=True;value['action']={'kind':'continue'}
            response['choices'][0]['message']['content']=json.dumps(value)
        return io.BytesIO(json.dumps(response).encode())
    monkeypatch.setattr(Wire,'__call__',uncertain_once)
    def factory(*args,**kw):
        for link in kw['links'].values():
            link.inner.study_options=Options(True,True,'en');link.inner.protocol_progress=OPTION
        return live.Host(*args,**kw)
    host,inner,wire=bind(build,s4=SimpleNamespace(Host=factory))(tmp_path,setup_data)
    advance(host,inner,1,55)
    assert host.trial.dialogue.claims=={'r1','r2'}
    assert host.trial.protocol_reminders.events
    assert all(e['model_decision_required'] and not e['accepted_action_replayed'] for e in host.trial.protocol_reminders.events)
    bodies=[json.loads(json.loads(r)['messages'][-1]['content'][0]['text']) for r in wire.requests]
    claims=[b['current_protocol_step'] for b in bodies if b.get('current_protocol_step',{}).get('step')=='claim']
    assert claims and all(v['action_syntax']['kind']=='claim' for v in claims)


def test_no_peer_state_is_invented_and_reminders_are_bounded():
    view=dict(key=None,own_claim=False,approved=True,route_hash='a'*64,proposal_message_id='real-message')
    body=dict(robot_id='r2',dialogue=view,own_route_proposal=None,task=dict(fixed_roles={'r2':'end_pos'}))
    before=copy.deepcopy(body);prompt(body,'')
    assert body['dialogue']==before['dialogue'] and body['current_protocol_step']['action_syntax']['role']=='end_pos'
    assert phase('r3',view) is None
    assert phase('r2',{**view,'key':['o','a',1,0]}) is None
    scheduled=[];row=dict(status='done',completion=dict(finish_reason='stop'))
    trial=SimpleNamespace(dialogue=SimpleNamespace(view=lambda *args:view),links={r:SimpleNamespace(inner=SimpleNamespace(own_inputs_at=lambda t:{'own_route':None})) for r in ('r1','r2')},scheduler=SimpleNamespace(calls=[SimpleNamespace(actor=r,call_id=r) for r in ('r1','r2')],ledger={r:copy.deepcopy(row) for r in ('r1','r2')},trigger=lambda *a,**k:scheduled.append(a)))
    reminders=Reminders()
    for t in range(0,200):reminders.poll(trial,float(t))
    assert len(scheduled)==6
    view['own_claim']=True;reminders.poll(trial,201.);assert not reminders.states
