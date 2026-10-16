"""Own-input motion gate regression; no simulator or provider execution."""
import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from harness import e2e_body_controller as m
from harness import e2e_body_semantics as sem


def fixture(phase='align', complete=False, send=None):
    robots={r:NS(servo={1:2000,6:1500},beam_observation=dict(result=dict(visible=True,end_visible=True,
        grip_base_m=[.4,0.],axis_heading_rad=0),rgb=dict(frame_id=1,t_sim=0.,sha256='a'*64)),
        frame=NS(jpeg=None),goal=NS(explorer=NS(local_pose=np.zeros(3)),pose_covariance=lambda:np.eye(3)*.01),packet=None)
        for r in ('r1','r2')}
    d=NS(key=('order-5','a'*64,1,0),approved=True,claims={'r1','r2'})
    d.allowed=lambda key,now:complete
    d.view=lambda rid,now:dict(transport_admitted=complete,key=list(d.key))
    events=[]
    tr=NS(robots=robots,dialogue=d,state=phase,stage_t=0.,epoch=0,seg=0,queue=[],queue_until=0.,
        robot_queue_until={},approach={},failure=None,done=False,aligned={},align={},
        _carry=lambda now:events.append('carry') or True,event=lambda *a,**k:events.append((a,k)))
    tr.set=lambda state,now:setattr(tr,'state',state)
    client=m.Client('jev','test',send=send or (lambda p:dict(status='ok',choice=next(iter(p['candidates'])),latency_s=.2,wall_s=.2)))
    g=m.BodyGate(tr,robots,client,profiles={})
    return g,tr,robots,events


def test_default_backend_and_off_do_not_mutate():
    b={'execution_bundle_id':'old'};original=copy.deepcopy(b)
    assert m.compose(b)==() and b==original
    b={'execution_bundle_id':m.PARENT,'e2e_options':{'dev_light':True}}
    m.compose(b,'jev_v1')
    assert b['execution_bundle_id']=='e2e18-v336' and b['e2e_options']['body_backend']=='liquid_d1'
    assert m.parent_for_validation(b)['execution_bundle_id']==m.PARENT
    b['body_controller_parameters']['phase_budget_s']=61
    with pytest.raises(ValueError):m.parent_for_validation(b)


def test_actual_bundle_registration(monkeypatch):
    from tests import test_e2e_camera_hold as p
    from scripts.run_e2e_ownmap_live import bundle,ROOT
    from harness.e2e_runtime_registration import require_current
    args=[];kw={}
    def capture(*a,**k):
        args.extend(a);kw.update(k);return bundle(*a,**k)
    monkeypatch.setattr(p,'bundle',capture)
    p.test_registered_wheel_wait_candidate('zero_wheel_v1',276,'range_wall_v1')
    kw.update(stage_physics='release_dt1_v1',relook_giveup='dev_light_rest_v1',post_relook='carry_through_v1')
    old=bundle(*args,**kw)
    new=bundle(*args,**kw,body_controller='jev_v1',body_backend='jev')
    assert old['execution_bundle_id']=='e2e18-v321'
    assert new['execution_bundle_id']=='e2e18-v335'
    require_current(new,ROOT)
    assert 'harness/e2e_body_controller.py' in new['source_sha256']
    for backend,version in [('liquid_d1',344),('jev',345)]:
        skill=bundle(*args,**kw,body_controller='jev_v1',body_backend=backend,body_skills='bounded_v1')
        require_current(skill,ROOT)
        assert skill['execution_bundle_id']==f'e2e18-v{version}'
        assert 'harness/e2e_body_skills.py' in skill['source_sha256']
    code=bundle(*args,**kw,body_controller='jev_v1')
    require_current(code,ROOT)
    assert code['execution_bundle_id']=='e2e18-v349'
    assert code['e2e_options']['body_backend']=='code_v1'
    assert 'harness/e2e_body_code.py' in code['source_sha256']


@pytest.mark.parametrize('phase',['mapping','align','relook'])
def test_motion_selected_then_latency_hold_before_emission(phase):
    g,tr,robots,_=fixture(phase,send=lambda p:dict(status='ok',choice='back_short' if 'back_short' in p['candidates'] else 'back_off',wall_s=.2))
    proposed=sem.pulse('forward_short')
    first=g.filter(0.,[('r1',proposed)])
    assert not any(c.get('forward') for _,c in first)
    assert len(g.rows)==1
    assert g.filter(.1,[])==[]
    emitted=g.filter(.2,[])
    assert any(c.get('forward',0)<0 for _,c in emitted)
    assert len(g.rows)==1


def test_mapping_candidate_freezes_selected_command():
    g,_,_,_=fixture('mapping')
    g.filter(0.,[('r1',sem.pulse('forward_short'))])
    emitted=g.filter(.2,[('r1',sem.pulse('back_short'))])
    assert any(c.get('forward',0)>0 for _,c in emitted)
    assert not any(c.get('forward',0)<0 for _,c in emitted)


@pytest.mark.parametrize('failure',[{'status':'failed'},{'status':'ok','choice':'not_offered'}, {'status':'ok','choice':'forward_short','wall_s':99}])
def test_failure_never_executes_and_reasks(failure):
    g,_,_,_=fixture(send=lambda p:copy.deepcopy(failure))
    c=sem.pulse('forward_short')
    assert all(m.stop_like(x) for _,x in g.filter(0.,[('r1',c)]))
    g.filter(.5,[('r1',c)]);assert len(g.rows)==1
    g.filter(27.,[('r1',c)]);assert len(g.rows)==2


def test_sonar_collision_removed_before_model_and_checked_after_delay():
    g,_,robots,_=fixture()
    reading={'status':'ok','valid':True,'range_m':.1,'age_s':0.}
    robots['r1'].range_provider=NS(report=lambda now:NS(as_dict=lambda:reading))
    menu,_,facts=g.menu_direct('r1',0.,[sem.pulse('forward_short')])
    assert 'forward_short' not in menu
    reading['range_m']=1.
    g.client.send=lambda p:dict(status='ok',choice='forward_short',wall_s=.2)
    g.filter(0.,[('r1',sem.pulse('forward_short'))])
    reading['range_m']=.1
    assert all(m.stop_like(c) for _,c in g.filter(.2,[]))


def test_loop_removes_proposal_alias_and_offers_recovery():
    g,_,_,_=fixture()
    for i in range(8):g.history['r1'].append(sem.pulse('turn_left_small' if i%2 else 'turn_right_small'))
    menu,_,f=g.menu_direct('r1',0.,[dict(kind='mecanum',forward=0,left=0,turn=.3,duration_s=.2)])
    assert 'recover_wide_view' in menu
    assert 'own_plan_step' not in menu and 'turn_left_small' not in menu
    assert f['left_right_loop']


def test_lost_search_only_last_seen_rotation_direction():
    g,_,robots,_=fixture()
    robots['r1'].beam_observation['result']['grip_base_m']=[.3,-.4]
    g.context('r1',0.)
    robots['r1'].beam_observation=dict(result={'visible':False},rgb=dict(frame_id=2,t_sim=1.,sha256='b'*64))
    menu,_,_=g.menu_direct('r1',1.,[sem.pulse('turn_left_small')])
    assert 'turn_left_small' not in menu
    assert 'turn_right_small' in menu


def test_no_carry_query_without_agreement():
    g,tr,robots,events=fixture('wait_go_ack')
    assert not tr._carry(0.) and g.rows==[] and events==[]


def test_carry_obstacle_no_reverse_escape():
    g,tr,robots,events=fixture('wait_go_ack',True)
    for robot in robots.values():
        robot.servo[1]=1500
        robot.range_provider=NS(report=lambda now:NS(as_dict=lambda:dict(status='ok',valid=True,range_m=.1,age_s=0.)))
    assert not tr._carry(0.)
    assert all(set(row['candidates'])=={'hold_and_wait'} for row in g.rows)
    assert 'carry' not in events


def test_no_cross_robot_private_geometry():
    g,tr,robots,_=fixture()
    tr.approach['r2']=dict(station=np.array([987.,654.,321.]),grip=np.array([222.,333.]),last_seen=0)
    text=sem.state_text('r1','align',g.facts('r1',0.)[0])
    assert all(x not in text for x in ['987.','654.','222.','333.'])
    assert 'Rules, in priority order' in text and 'recent decisions' in text


def test_memory_tracks_outcomes_and_20_second_stall():
    mem=sem.DecisionMemory()
    for i in range(25):
        mem.observe('align',i,'visible',1.,-20,False,i)
        mem.selected(i,'forward_short','visible',1.,.2,'ok')
    c=mem.context(24)
    assert c['no_progress_20s'] and len(c['recent_decisions'])==10
    assert c['recent_decisions'][-1]['distance_change_m']==0
    mem.observe('align',25,'not_visible',None,None,False,25)
    mem.observe('align',26,'visible',.9,20,True,26)
    assert mem.reacquisitions==1 and mem.losses==1 and mem.oscillations==1
    mem.observe('carry',27,'visible',.5,0,False,27)
    assert not mem.history and not mem.context(27)['budget_exceeded']


def test_recovery_order_excludes_attempted_strategies():
    g,tr,robots,_=fixture()
    g.context('r1',0.)
    menu,_,f=g.menu_direct('r1',61.,[sem.pulse('forward_short')])
    assert set(menu)<= {'recover_wide_view','hold_and_reobserve'}
    g.memory['r1'].tried.append('recover_wide_view')
    menu,_,_=g.menu_direct('r1',62.,[sem.pulse('forward_short')])
    assert 'recover_camera_pan' in menu and 'recover_wide_view' not in menu


def test_queued_camera_requires_decision_once_not_every_interpolation():
    g,tr,_,_=fixture('relook_camera')
    tr.queue=[(.05,'r1',dict(kind='arm',servo_id=5,pulse=1200)),(.1,'r1',dict(kind='look',pan_pulse=1600))]
    tr.queue_until=.7
    g.pre_step(0.);assert len(g.rows)==1
    assert not g.approved
    g.pre_step(.2);assert len(g.rows)==1 and len(g.approved)==2




def test_direction_words_and_predicted_effects_avoid_signed_model_bearings():
    text=sem.state_text('r1','align',dict(own_map={'standoff':{'bearing_deg':-35.,'heading_error_deg':21.}},last_seen_bearing_deg=-60.))
    assert '35.0 degrees to the RIGHT' in text and '21.0 degrees to the LEFT' in text
    assert '-35' not in text and '-60' not in text
    profile={'p':dict(loaded=False,axis='turn',u=-.35,duration_s=.1,mean_delta=[0,0,-.1])}
    prediction=sem.predict_target({'standoff':dict(distance_m=.3,bearing_deg=-30,heading_error_deg=-20)},[(0,sem.pulse('turn_right_small'))],profile)
    assert '24.3 degrees to the RIGHT' in prediction and '14.3 degrees to the RIGHT' in prediction


def test_lift_queue_never_offered_without_current_go_ack():
    g,tr,robots,_=fixture('grasp_lift',False)
    tr.queue=[(.05,r,dict(kind='arm',servo_id=5,pulse=1700)) for r in sem.PAIR]
    g.pre_step(0.)
    assert len(g.rows)==2 and all('grasp_and_lift' not in r['candidates'] for r in g.rows)
    assert not g.approved


def skill_fixture(phase='mapping',send=None):
    from harness.e2e_body_skills import SkillsBodyGate
    gate,tr,robots,events=fixture(phase,send=send)
    g=SkillsBodyGate(tr,robots,gate.client,profiles={})
    for r in robots.values():r.nav_command=sem.pulse('forward_short')
    return g,tr,robots,events


def test_skills_default_d1_and_jev_comparison_registration():
    from harness import e2e_body_skills as sk
    for backend,version,parent in [('liquid_d1',344,336),('jev',345,335)]:
        b={'execution_bundle_id':m.PARENT,'e2e_options':{'dev_light':True}}
        m.compose(b,'jev_v1',backend);sk.compose(b,'bounded_v1')
        assert b['execution_bundle_id']==f'e2e18-v{version}'
        assert sk.parent_for_validation(b)['execution_bundle_id']==f'e2e18-v{parent}'


def test_peer_path_uses_candidate_direction_not_image_center():
    peer=dict(visible=True,distance='near',direction='left',bearing_deg=80.,half_width_deg=10.)
    assert not sem.peer_for_path(peer,sem.pulse('forward_short'))['in_path']
    assert sem.peer_for_path(peer,sem.pulse('strafe_left_small'))['in_path']
    assert not sem.peer_for_path(peer,sem.pulse('strafe_right_small'))['in_path']
    assert not sem.peer_for_path(peer,sem.pulse('turn_left_small'))['in_path']


def test_thin_orange_strip_is_not_near_peer():
    import cv2
    rgb=np.zeros((480,640,3),np.uint8);rgb[50:60,180:430]=[0,140,255]
    jpeg=cv2.imencode('.jpg',rgb)[1].tobytes()
    assert sem.peer_appearance(jpeg)['distance']=='near'
    assert sem.peer_appearance_v2(jpeg,{1:2000,3:740,4:2320,5:1320,6:1500})['visible'] is False


def test_blocked_menu_has_detours_and_filtered_proposal(monkeypatch):
    g,tr,robots,_=skill_fixture()
    monkeypatch.setattr(sem,'peer_appearance_v2',lambda *a:dict(visible=True,distance='near',direction='ahead',bearing_deg=0.,half_width_deg=12.,in_path=True))
    menu,proposal,facts=g.menu_direct('r1',0.,[sem.pulse('forward_short')])
    assert 'follow_own_path' not in menu
    assert {'detour_left','detour_right','back_off_and_replan'}<=set(menu)
    assert proposal in menu
    assert 'ahead, near' in facts['blocking_observation']


def test_three_unchanged_waits_removed_without_removing_safe_alternatives():
    g,tr,robots,_=skill_fixture()
    facts=g.facts('r1',0.)[0]
    for t in (0.,1.,2.):g.rows.append(dict(t=t,robot_id='r1',phase='mapping',choice='stop_and_look',facts=copy.deepcopy(facts)))
    menu,proposal,facts=g.menu_direct('r1',3.,[sem.pulse('forward_short')])
    assert facts['blocked_persistently']
    assert 'hold_and_reobserve' not in menu and proposal in menu
    assert 'follow_own_path' in menu


def test_bounded_feedback_skill_runs_multiple_commands_with_one_decision():
    g,tr,robots,_=skill_fixture(send=lambda p:dict(status='ok',choice='follow_own_path',wall_s=.2))
    proposed=sem.pulse('forward_short');g.filter(0.,[('r1',proposed)])
    for t in (.2,.4,.6):
        robots['r1'].beam_observation['rgb']['t_sim']=t
        out=g.filter(t,[('r1',copy.deepcopy(proposed))])
        assert any(c.get('forward',0)>0 for _,c in out)
    assert len(g.rows)==1
    robots['r1'].range_provider=NS(report=lambda now:NS(as_dict=lambda:dict(valid=True,status='ok',range_m=.1,age_s=0.)))
    assert all(m.stop_like(c) for _,c in g.filter(.8,[('r1',proposed)]))
    assert 'r1' not in g.units


def test_cost_absent_is_unknown_and_visual_calls_are_counted():
    g,tr,robots,_=fixture()
    g.filter(0.,[('r1',sem.pulse('forward_short'))])
    g.visual_rows.append(dict(usage={'cost':.1}))
    x=g.summary()
    assert x['cost_usd'] is None and x['reported_cost_usd']==.1
    assert x['visual_crosscheck_calls']==1 and x['cost_unknown_calls']==1
