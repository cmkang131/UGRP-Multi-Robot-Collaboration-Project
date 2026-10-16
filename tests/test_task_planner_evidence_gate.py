import copy,json
from harness.task_planner import Planner, candidate, ModelReply, strong_rule
from harness.task_planner_evidence_gate import apply
from harness.task_planner_cost_rules import SPECS
from scripts.evaluate_task_planner import adapt
from tests.test_task_planner_dataset import row


def route(stamp=40, fact=None):
    r=row();v=r['input'];v['task']=SPECS['route']['task']
    v['self_state']['travel_estimates']=dict(c_narrow=5,c_wide=20,c_inspect=25,failed_trip=34)
    v['messages'][0].update(observation_time_s=stamp,body='Door_narrow is clear.')
    if fact:v['self_state']['observed_facts']=[fact]
    return r


def test_off_is_exact_and_gate_is_idempotent_without_changing_actions():
    _,off,_=adapt(route(),'peer_en');_,on,_=adapt(route(),'peer_en','on_v1')
    assert apply(off,'off') is off
    assert apply(on,'on_v1') is on
    assert [(c['act'],c['args']) for c in off['candidates']]==[(c['act'],c['args']) for c in on['candidates']]
    assert on['received_messages']==[]
    c=on['candidates'][0]['preview']['candidate_evidence']
    assert c['status']=='stale' and c['reports'][0]['age_s']==60 and c['own_observed_at'] is None
    assert on['candidates'][1]['preview']['candidate_evidence']['status']=='independent'
    assert strong_rule(on)['args']==strong_rule(off)['args']


def test_conflict_requires_newer_own_and_refreshes_for_rule():
    f=dict(subject='door_narrow',predicate='passage_state',value='blocked',observed_at=99,source='own RGB')
    _,on,_=adapt(route(98,f),'peer_en','on_v1')
    assert on['evidence_gate']['archived_reports'][0]['status']=='conflict'
    assert on['candidates'][0]['preview']['candidate_evidence']['own_observed_at']==99
    assert strong_rule(on)['act']=='search'
    f['observed_at']=97
    _,old,_=adapt(route(98,f),'peer_en','on_v1')
    assert not old['evidence_gate']['archived_reports'] and old['received_messages']
    assert old['evidence_assessment']['reports'][0]['conflicts_with_own_observation'] is False


def test_fresh_wrong_is_not_detectable_from_labels_and_no_comm_has_no_report():
    r=route(98);_,base,_=adapt(r,'peer_en','on_v1')
    r.update(quality='wrong',world='blocked',best_choices=['wide'])
    _,changed,_=adapt(r,'peer_en','on_v1');assert changed==base
    assert base['received_messages'] and not base['evidence_gate']['archived_reports']
    _,none,_=adapt(r,'no_comm','on_v1')
    assert none['received_messages']==[] and none['evidence_gate']['archived_reports']==[]


def test_fixed_signal_conflict_uses_only_delivered_fact():
    r=route(98,dict(subject='door_narrow',predicate='passage_state',value='blocked',observed_at=99))
    r['input']['messages'][0]['body']=dict(act='inform',passage='door_narrow',state='clear',confidence='high',observed_at_sim_s=98)
    _,ctx,_=adapt(r,'structured','on_v1')
    assert ctx['evidence_gate']['archived_reports'][0]['status']=='conflict'


def test_native_age_penalty_and_audit_original_not_in_prompt():
    p=Planner('r1','peer_en',planner_evidence_gate='on_v1')
    p.receive(dict(id='old',sender='r2',recipient='r1',sent_at=0,delivered_at=1,body='I need help with beam_1.'),1)
    menu=[candidate('help',dict(partner='r2',cargo='beam_1',side='end_neg'),expected_s=10),candidate('search',dict(area='beam_1'),expected_s=10)]
    ctx=p.context(now=40,orders=[],static_map={},own=dict(robot_id='r1'),candidates=menu)
    def model(req,**kw):
        got=req['input'];assert got['received_messages']==[]
        assert got['candidates'][0]['preview']['priority_score']<got['candidates'][1]['preview']['priority_score']
        return ModelReply(json.dumps(dict(act='search',args=dict(area='beam_1'),message='',reason='Verify.')))
    result=p.decide(ctx,model)
    assert not result['fallback']
    assert p.audit[0]['channel_evidence_before_gate'][0]['body']=='I need help with beam_1.'
    assert p.inbox[0]['body']=='I need help with beam_1.'


def test_new_confirmation_phrases_and_seed_are_not_r2():
    from scripts import generate_task_planner_confirmation as old, generate_task_planner_confirmation_r3 as new
    old_text={x for d in old.PHRASES.values() for x in d.values()}
    assert not old_text.intersection(x for d in new.PHRASES.values() for x in d.values())


def test_other_passage_clause_cannot_corroborate_this_passage():
    f=dict(subject='door_narrow',predicate='passage_state',value='clear',observed_at=99)
    r=route(98,f);r['input']['messages'][0]['body']='Door_narrow is blocked but door_wide is clear.'
    _,ctx,_=adapt(r,'peer_en','on_v1')
    assert ctx['evidence_gate']['archived_reports'][0]['status']=='conflict'
    r['input']['messages'][0]['body']='Door_narrow is blocked. Door_narrow is clear.'
    _,ctx,_=adapt(r,'peer_en','on_v1')
    assert not ctx['evidence_gate']['archived_reports']  # ambiguous claim stays unknown


def test_unrelated_current_message_does_not_refresh_old_native_evidence():
    p=Planner('r1','peer_en')
    for mid,t,body in [('old',0,'I need help with beam_1.'),('new',39,'I see a blue wall.')]:
        p.receive(dict(id=mid,sender='r2',recipient='r1',sent_at=t,delivered_at=t,body=body),40)
    ctx=p.context(now=40,orders=[],static_map={},own=dict(robot_id='r1',rgb=dict(t_sim=39.5)),
                  candidates=[candidate('help',dict(partner='r2',cargo='beam_1',side='end_neg'))])
    got=apply(ctx,'on_v1')['candidates'][0]['preview']['candidate_evidence']
    assert got['status']=='stale' and got['own_rgb_observed_at']==39.5
