"""Real controller dispatch, recovery memory and version admission; no physics."""
import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from harness import e2e_approach_efficiency as m
from harness.e2e_carrier_approach import advance
from harness.zone_solo_cyan_pulse_cal import action_of
from harness.public_navigation.costmap import Costmap
from tests.test_e2e_align_progress import setup_transport


def transport():
    tr=setup_transport();tr.approach_efficiency=m.OPTION;tr.state='align'
    r=tr.robots['r1'];r.last_obs.update(sim_time=2.);r.goal.explorer.local_pose=np.array([-2.,0.,0.])
    cm=Costmap(np.zeros((100,100),np.uint8),[-5.,-5.])
    r.goal.explorer.navigator.plan_to=lambda cost,pose,target:[pose[:2].tolist(),list(target)]
    return tr,r,cm


def test_rate_regulation_far_bend_near_and_long_curved_path():
    assert m.pulse_period([.6,0],2.,2.) == .2
    assert m.pulse_period([.1,.2],2.,2.) == .4
    assert m.pulse_period([.1,0],.1,.1) == .4
    assert m.pulse_period([.3,0],.3,2.) == .2  # do not slow on a distant loop


def test_actual_approach_requires_issue_ack_and_one_fresh_safe_continuation(monkeypatch):
    import harness.e2e_carrier_approach as approach
    tr,r,cm=transport()
    monkeypatch.setattr(approach,'from_observed_grid',lambda *a:cm)
    _,actions=advance(tr,'r1',2.)
    assert actions[0]['forward']>0 and actions[0]['duration_s']==.1
    assert not advance(tr,'r1',2.2)[1]  # proposal rejected/delayed by outer body gate
    m.issued(tr,'r1',actions[0],2.)
    assert not advance(tr,'r1',2.15)[1]
    assert advance(tr,'r1',2.2)[1]==actions
    assert not advance(tr,'r1',2.25)[1]
    assert 'own_approach_cruise_continuation' in [e['event'] for e in tr.events]


@pytest.mark.parametrize('blocked',['stale','camera','queue','grip','phase','stop','map'])
def test_extra_pulse_cannot_bypass_freshness_ownership_or_collision(monkeypatch,blocked):
    import harness.e2e_carrier_approach as approach
    tr,r,cm=transport();monkeypatch.setattr(approach,'from_observed_grid',lambda *a:cm)
    _,actions=advance(tr,'r1',2.);m.issued(tr,'r1',actions[0],2.)
    now=2.2
    if blocked=='stale':now=2.5
    if blocked=='camera':r.camera_settle_until=3.
    if blocked=='queue':tr.queue=[(2.5,'r1',dict(kind='look',pan_pulse=1600))]
    if blocked=='grip':r.servo[1]=1500
    if blocked=='phase':tr.state='carry'
    if blocked=='stop':m.issued(tr,'r1',dict(kind='hold'),2.1)
    if blocked=='map':cm.raw[:]=254
    assert not advance(tr,'r1',now)[1]


def test_replan_one_hz_and_invalidated_by_goal_obstacle():
    tr,r,cm=transport();calls=[]
    r.goal.explorer.map_to_odom=np.zeros(3)
    r.goal.explorer.navigator.plan_to=lambda c,p,t:(calls.append(1) or [p[:2].tolist(),list(t)])
    r.carrier_approach={};state={};p=np.zeros(3);target=np.array([1.,0.,0.])
    m.navigation_path(tr,'r1',0.,state,cm,p,target)
    m.navigation_path(tr,'r1',.4,state,cm,p,target)
    assert len(calls)==1 and r.carrier_approach['path_reused']
    m.navigation_path(tr,'r1',1.2,state,cm,p,target);assert len(calls)==2
    m.navigation_path(tr,'r1',1.3,state,cm,p,target+[.2,0,0]);assert len(calls)==3
    cm.costs[:]=254
    m.navigation_path(tr,'r1',1.4,state,cm,p,target+[.2,0,0]);assert len(calls)==4


def test_small_gaze_deadband_preserves_fine_servo_and_off():
    tr,r,_=transport();pose=r.goal.explorer.local_pose
    grip=pose[:2]+[1.,.1]
    assert not m.gaze_needed(tr,'r1',grip)
    assert m.gaze_needed(tr,'r1',pose[:2]+[1.,1.])
    tr.approach['r1']={'fine':True};assert m.gaze_needed(tr,'r1',grip)
    tr.approach_efficiency='off';assert m.gaze_needed(tr,'r1',grip)
    assert m.compose({})==()


def test_search_right_bearing_and_sector_order_survive_explore():
    from harness.e2e_pregrasp_acquire import acquire
    from harness.e2e_acquisition_mobility import explore
    tr,r,_=transport();tr.pregrasp_acquire='remember_scan_v1';tr.acquisition_mobility='resume_v1'
    r.last_beam=dict(rgb=dict(t_sim=0.),pose_own_m=[-1.,-1.,0.]);r.beam=None
    r.goal.explorer.local_pose=np.array([-1.,0.,0.]);state={}
    acquire(tr,'r1',20.,state,None);a=state['acquisition']
    assert a['yaw']==pytest.approx(-math.pi/2) and a['sector_search']['direction']==-1
    yaws=[m.next_yaw(tr,'r1',a,r.goal.explorer.local_pose) for _ in range(3)]
    assert yaws==pytest.approx([-5*math.pi/6,-7*math.pi/6,-3*math.pi/2])
    a.update(phase='explore',cycles=2,mobile_cycle=2,mobile_started=20.,progress_t=28.,progress_xy=np.array([-1.,0.]))
    explore(tr,'r1',28.,a)
    assert a['phase']=='turn' and a['sector_search']['index']==4 and r.beam is None


def test_search_skill_keeps_planned_direction_and_shared_safety():
    from tests.test_e2e_body_code import gate
    from harness import e2e_body_semantics as sem
    g,tr,robots=gate('align');tr.approach_efficiency=m.OPTION
    tr.approach['r1']={'acquisition':{'phase':'turn'}}
    menu,proposal,facts=g.menu_direct('r1',0.,[sem.pulse('turn_right_small')])
    assert proposal=='search_own_beam' and proposal in menu
    safe,choice,facts=g.prepare_decision('r1',0.,'direct',menu,proposal,facts)
    assert choice=='search_own_beam'
    facts['partner_stop']=True
    _,choice,_=g.prepare_decision('r1',0.,'direct',menu,proposal,facts)
    assert choice in ('hold_and_reobserve','hold_and_wait')


def test_scan_waits_for_commanded_posture_and_accepted_settled_image():
    from harness.e2e_pregrasp_acquire import acquire
    tr,r,_=transport();tr.pregrasp_acquire='remember_scan_v1';tr.align_queues='per_robot_v1'
    r.beam=None;r.last_beam=None;state={}
    acquire(tr,'r1',10.,state,None)
    acquire(tr,'r1',10.4,state,None)
    a=state['acquisition'];assert a['view']==0
    r.last_obs['frame_id']+=1
    acquire(tr,'r1',10.8,state,None);assert a['view']==0  # queued
    tr.queue.clear();tr.robot_queue_until['r1']=0.
    acquire(tr,'r1',11.,state,None);assert a['view']==0  # not issued yet
    r.servo.update(a['view_pose']);r.camera_settle_until=12.
    acquire(tr,'r1',11.2,state,None);assert a['view']==0
    acquire(tr,'r1',12.4,state,None);assert a['view']==1 and r.beam is None


def test_v351_parent_registration_default_off_and_tamper(monkeypatch):
    from tests import test_e2e_camera_hold as fixture
    from scripts.run_e2e_ownmap_live import bundle,ROOT
    from harness.e2e_runtime_registration import require_current
    args=[];kw={}
    def capture(*a,**k):args.extend(a);kw.update(k);return bundle(*a,**k)
    monkeypatch.setattr(fixture,'bundle',capture)
    fixture.test_registered_wheel_wait_candidate('zero_wheel_v1',276,'range_wall_v1')
    kw.update(stage_physics='release_dt1_v1',relook_giveup='dev_light_rest_v1',post_relook='carry_through_v1',
              body_controller='jev_v1',body_backend='code_v1',body_protocol_stack='code_v1')
    old=bundle(*args,**kw);new=bundle(*args,**kw,approach_efficiency=m.OPTION)
    assert old['execution_bundle_id']=='e2e18-v350' and new['execution_bundle_id']=='e2e18-v351'
    assert m.parent_for_validation(new)['e2e_options']==old['e2e_options'];require_current(new,ROOT)
    new['approach_efficiency_parameters']['max_extra_per_frame']=2
    with pytest.raises(ValueError,match='APPROACH_EFFICIENCY'):require_current(new,ROOT)
