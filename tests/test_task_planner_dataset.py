import json
from scripts.evaluate_task_planner import adapt, action
from harness.task_planner import ModelReply


def row():
    return dict(case_id='opaque',input=dict(task='Select route',self_state={'robot_id':'r1'},now_s=100,
        public_context={'orders':[],'static_map':{}},candidates={'narrow':'Use narrow','wide':'Use wide','inspect':'Inspect'},
        possibilities=['clear','blocked'],cost_rule='public rule',cost_units='synthetic',evidence_policy='own only',fixed_signal_dictionary='fixed enums',
        messages=[dict(sender='r2',observation_time_s=98,confidence='high',body='Door is blocked.')]))


def test_eval_labels_not_in_request_and_leader_is_explicit_topology():
    r=row();r['best_choices']=['wide'];r['world']='blocked'
    p,ctx,labels=adapt(r,'leader_en')
    assert 'best_choices' not in json.dumps(ctx) and 'world' not in json.dumps(ctx)
    assert ctx['received_messages'][0]['sender']=='r2' and ctx['robot_id']=='r1'
    assert ctx['candidates'][0]['args']=={'via':'door_narrow'}


def test_no_comm_drops_even_supplied_reports():
    p,ctx,_=adapt(row(),'no_comm');assert ctx['received_messages']==[]


def test_legacy_fixed_contract_preserved_without_side_channel():
    r=row();r['input']['messages'][0]['body']={'act':'inform','passage':'door_narrow','state':'blocked','confidence':'high','observed_at_sim_s':98}
    _,ctx,_=adapt(r,'structured')
    assert ctx['received_messages'][0]['body']==r['input']['messages'][0]['body']
