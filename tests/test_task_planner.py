import copy
import json
import threading
import time
from types import SimpleNamespace
import pytest
from harness.task_planner import Planner, ModelReply, candidate, fixed_signal, strong_rule
from harness.task_planner_runtime import ActPort, Channel, Runtime, build_candidates
from scripts.evaluate_task_planner import supplements


def wait(): return candidate('wait', dict(until='new_observation_or_message', max_s=5), expected_s=5)
def reply(c, **kw): return ModelReply(json.dumps(dict(act=c['act'],args=c['args'],message='Ready.',reason='Current feasible choice.')), **kw)
def context(p, menu=None):
    return p.context(now=1,orders=[],static_map={},own=dict(robot_id=p.robot_id),candidates=menu or [wait()])


def test_one_call_preserves_full_solo_destination_route_approach():
    for p,ctx,best in supplements():
        choice = min(ctx['candidates'],key=lambda c:c['preview']['expected_s'])
        seen=[]
        port=ActPort({'carry':lambda **args:seen.append(args) or {'accepted':True}}, lambda value:None)
        out=p.decide(ctx,lambda r,**kw:reply(choice),port)
        assert len(p.audit)==1 and not out['fallback']
        assert seen==[choice['args']]
        assert out['messages']==[]


def test_refusal_reasks_once_with_reason_and_never_rewrites_choice():
    p=Planner('r1','peer_en');c=wait(); requests=[];ran=[]
    def model(req,**kw):
        requests.append(copy.deepcopy(req))
        if len(requests)==1: return ModelReply('{"act":"go_to","args":{"station":"secret"},"message":"x","reason":"x"}')
        return reply(c)
    port=ActPort({'wait':lambda **args:ran.append(args) or {'accepted':True}}, lambda v:None)
    result=p.decide(context(p),model,port)
    assert len(requests)==2 and 'ACT_NOT_IN_FEASIBLE_MENU' in requests[1]['input']['refusals'][0]['reason']
    assert ran==[c['args']] and not result['fallback']


@pytest.mark.parametrize('finish,elapsed', [('length',0),('stop',31)])
def test_non_normal_or_late_never_executes_model_action(finish,elapsed):
    p=Planner('r1','no_comm');r=p.decide(context(p),lambda req,**kw:reply(wait(),finish_reason=finish,elapsed_s=elapsed))
    assert r['fallback'] and len(p.audit)==2


def test_provider_failure_and_two_invalid_responses_are_bounded():
    p=Planner('r1','peer_en')
    def fail(*a,**k): raise TimeoutError('fake secret should not appear')
    p.decide(context(p),fail)
    assert 'fake secret' not in json.dumps(p.audit)
    p=Planner('r1','peer_en');p.decide(context(p),lambda *a,**k:ModelReply('bad'))
    assert len(p.audit)==3 and p.audit[-1]['fallback']


def envelope(sender='r2',recipient='r1',body='I am delayed.',id='m1'):
    return dict(id=id,sender=sender,recipient=recipient,sent_at=0,delivered_at=.1,body=body)


def test_condition_topology_and_no_structured_bypass():
    p=Planner('r1','no_comm')
    with pytest.raises(ValueError):p.receive(envelope(),1)
    p=Planner('r3','leader_en',leader='r1')
    with pytest.raises(ValueError):p.receive(envelope(recipient='r3'),1)
    assert p.receive(envelope(sender='r1',recipient='r3'),1)
    assert not p.receive(envelope(sender='r1',recipient='r3'),1)
    p=Planner('r1','structured')
    with pytest.raises(ValueError):p.receive(envelope(),1)
    assert p.receive(envelope(body=fixed_signal(wait())),1)
    for key in ('peer_go_ref','peer_reports','eval_only','measured_joints'):
        with pytest.raises(ValueError):p.context(now=1,orders=[],static_map={},own=dict(robot_id='r1',**{key:{}}),candidates=[wait()])
    assert 'message' not in fixed_signal(dict(act='report',args={'fact':'free prose'}))


@pytest.mark.parametrize('kind',['start','act_success','act_failure','act_refused','partner_message','s2_blocked','s3_partner_delayed','s4_occupied','s5_missing','grip_anomaly'])
def test_all_event_triggers(kind):
    p=Planner('r1','peer_en');p.trigger(kind,1,'own observation')
    assert context(p)['events'][-1]['kind']==kind


def test_failed_act_memory_is_robot_private_and_bounded():
    p=Planner('r1','peer_en');q=Planner('r2','peer_en')
    for i in range(12):p.feedback(wait(),'failure','blocked',i)
    assert len(p.memory)==8 and not q.memory


def test_message_changes_fallback_and_stale_report_does_not():
    p=Planner('r1','peer_en')
    helper=candidate('help',dict(partner='r2',cargo='beam',side='left'),expected_s=10)
    ctx=context(p,[helper,wait()]);assert strong_rule(ctx)['act']=='wait'
    p.receive(envelope(body='I need a second carrier.'),1)
    assert strong_rule(context(p,[helper,wait()]))['act']=='help'
    ctx=context(p,[helper,wait()]);ctx['now_s']=100
    assert strong_rule(ctx)['act']=='wait'


def test_three_actors_really_call_concurrently_and_commit_on_main_thread():
    barrier=threading.Barrier(3); ids=[]; motors=[];main=threading.get_ident()
    def model(req,**kwargs):
        ids.append(req['input']['robot_id']);barrier.wait(timeout=2);return reply(wait())
    ports={r:ActPort({'wait':lambda **a:motors.append(threading.get_ident()) or {'accepted':True}},lambda v:None) for r in ('r1','r2','r3')}
    rt=Runtime(arm='no_comm',models={r:model for r in ports},ports=ports,
        snapshots={r:(lambda now,_r=r:dict(orders=[],static_map={},own={'robot_id':_r},candidates=[wait()])) for r in ports})
    try:
        rt.step(0)
        for _,p in rt.planners.items(): p.trigger('s2_blocked',.1,'during model call')
        until=time.monotonic()+3
        while not motors and time.monotonic()<until:
            time.sleep(.01);rt.step(.2)
        assert set(ids)==set(ports) and motors and all(i==main for i in motors)
        assert all(p.robot_id==r for r,p in rt.planners.items())
    finally:rt.close()


def test_candidate_enumeration_keeps_all_solo_choices():
    port=ActPort({'carry':lambda **a:{'accepted':True}},lambda v:None)
    static=dict(stations={'A1':[1,0],'A2':[2,0]},routes=[{'id':'west','waypoints':[[0,1]]},{'id':'east','waypoints':[[0,-1]]}],search_areas=[])
    orders=[dict(order_id='box',required_robots=1,destinations=['A1','A2'],approaches=['north','south'],pickup_xy=[0,0])]
    menu=build_candidates(orders,static,dict(robot_id='r1',pose={'xy':[0,0]}),port)
    assert len(menu)==8
    assert all(c['preview']['distance_m']>0 and c['preview']['unloading_empty']=='unknown' for c in menu)
