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


def test_relay_idempotency_header_is_64_hex_and_unique():
    import re
    from harness.task_planner_gemma import Gemma,Budget
    m=Gemma.__new__(Gemma);m.budget=Budget();m.run_id='test';seen=[]
    def post(path,**kwargs):
        seen.append(kwargs['headers'])
        return {'model':'google/gemma-4-31b-it','provider':'DeepInfra','usage':{'cost':0},
                'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}]}
    m._json=post
    for _ in range(2):m({'system':'test','input':{}},timeout_s=1)
    assert all(re.fullmatch('[a-f0-9]{64}',h['X-UGRP-Idempotency-Key']) for h in seen)
    assert seen[0]['X-UGRP-Idempotency-Key']!=seen[1]['X-UGRP-Idempotency-Key']


def test_age_cost_preview_uses_channel_only_and_no_gold():
    from harness.task_planner_cost_rules import SPECS
    r=row();v=r['input'];v['task']=SPECS['route']['task']
    v['self_state']['travel_estimates']=dict(c_narrow=5,c_wide=20,c_inspect=25,failed_trip=34)
    v['messages'][0].update(observation_time_s=40,body='Door_narrow is not blocked; the opening is clear.')
    _,ctx,_=adapt(r,'peer_en')
    assert ctx['evidence_assessment']['reports'][0]['age_s']==60
    assert ctx['evidence_assessment']['reports'][0]['last_directly_observed_at'] is None
    assert ctx['candidates'][0]['preview']['estimated_cost']==22
    _,none,_=adapt(r,'no_comm')
    assert none['evidence_assessment']['reports']==[]
    assert [c['preview']['estimated_cost'] for c in ctx['candidates']]==[c['preview']['estimated_cost'] for c in none['candidates']]
