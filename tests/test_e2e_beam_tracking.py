"""Own-RGB memory and actual skill/gaze boundaries; no physics or paid calls."""
import copy
from types import SimpleNamespace as NS
import numpy as np
from harness import e2e_beam_tracking as m
from harness import e2e_approach_commit as commit


def robot(option='view_return_v1'):
    return NS(beam_tracking=option,goal=NS(explorer=NS(local_pose=np.array([1.,2.,0.]),map_to_odom=np.array([3.,4.,0.]))),
        beam=None,last_beam=None,grasp_track=None,servo={6:1500},last_obs={'sim_time':1.,'frame_id':1},
        beam_observation={'result':{'visible':True,'end_visible':False,'points':40,'grip_base_m':[1.,.3],'lateral_spread_m':.06},
        'rgb':{'t_sim':1.,'frame_id':1,'sha256':'own'}},grasp_once='off')


def test_partial_body_updates_search_memory_without_grasp_permission():
    r=robot();m.observe(r,1.)
    assert np.allclose(r.beam_memory['point_own_m'],[2.,2.3])
    assert np.allclose(r.beam_memory['point_map_m'],[5.,6.3])
    assert r.beam is r.last_beam is r.grasp_track is None
    assert not r.beam_memory['end_qualified']
    r.beam_observation['rgb'].update(t_sim=2.,frame_id=2)
    r.beam_observation['result']['grip_base_m']=[.5,.3];m.observe(r,2.)
    assert r.beam_memory['seen']==2 and r.beam_memory['point_own_m'][0]==1.5


def test_off_is_noop_and_old_frame_cannot_refresh_memory():
    r=robot('off');before=copy.deepcopy(vars(r));m.observe(r,1.);assert not hasattr(r,'beam_memory')
    assert r.beam is None and r.servo==before['servo']
    r.beam_tracking='view_return_v1';m.observe(r,1.);m.observe(r,200.)
    assert r.beam_memory['seen']==1. and m.memory(r,302.) is None


def test_lost_grasp_keeps_gaze_but_never_sets_end_station():
    r=robot();m.observe(r,1.);r.last_obs['sim_time']=121.
    tr=NS(robots={'r1':r},approach={'r1':{}},approach_commit='memory60_view_v1')
    assert np.allclose(commit.gaze_target(tr,'r1',False,[8.,8.]),[2.,2.3])
    assert tr.approach=={'r1':{}} and r.beam is None
    g=m.pan_geometry(r,[-1.,2.]);assert not g['reachable'] and 800<=g['target_pwm']<=2200


def test_pan_during_turn_settles_and_does_not_override_fine():
    r=robot();m.observe(r,1.);r.beam_memory['point_own_m']=[1.,4.]
    r2=robot('off');events=[]
    tr=NS(beam_tracking='view_return_v1',robots={'r1':r,'r2':r2},beam_search={'r1':{},'r2':{}},
        approach={'r1':{},'r2':{}},state='align',event=lambda *a,**k:events.append((a,k)))
    actions=[('r1',{'kind':'mecanum','turn':.35})]
    out=m.decorate_gaze(tr,1.,actions)
    assert any(a['kind']=='look' for _,a in out) and not any(a['kind']=='mecanum' for _,a in out)
    assert not events[-1][1]['reachable']
    tr.approach['r1']['fine']=True
    assert m.decorate_gaze(tr,3.,actions)==actions


def test_three_unchanged_choices_are_removed(monkeypatch):
    r=robot();m.observe(r,1.);tr=NS(robots={'r1':r},event=lambda *a,**k:None)
    state={'blocked':set(),'failures':{},'coverage':[]}
    for n in range(3):
        state.update(choice='return_memory',start_pose=[1.,2.,0.],started=2.)
        m.finish(tr,'r1',3.,state,'no_progress')
    assert 'return_memory' in state['blocked']
    tr.beam_tracking='view_return_v1';monkeypatch.setattr(m,'path_to',lambda r,p:(None,None,[[1.,2.],[2.,2.]],None))
    offered=m.candidates(tr,'r1',3.,state)
    assert 'return_memory' not in {x['id'] for x in offered}
    assert {'scan','explore'}<={x['id'] for x in offered}


def test_stale_model_reply_never_bypasses_fresh_grasp_gate():
    r=robot();m.observe(r,1.);r.frame=NS(jpeg=b'own',sha256='own');r.nav_command={'kind':'hold'}
    class Client:
        future=None
        def poll(self):return {'decision':{'choice':'return_memory','message':'','reason':'return'}}
    events=[];state={'offered':[{'id':'return_memory','goal_own_m':[1.,2.]}],'blocked':set(),'failures':{},'coverage':[]}
    tr=NS(beam_tracking='view_return_v1',robots={'r1':r},beam_search={'r1':state},beam_clients={'r1':Client()},event=lambda *a,**k:events.append((a,k)))
    # Hold at return-to-view completion still must not report fine/held.
    import pytest
    from unittest.mock import patch
    with patch.object(m,'path_to',return_value=(None,None,[],None)):
        fine,actions=m.step(tr,'r1',3.,{})
    assert not fine and r.beam is None and actions==[{'kind':'hold'}]
    assert state['phase']=='turn'


def test_relay_budget_reserves_before_attempt_and_retains_unknown(tmp_path):
    from scripts.e2e_beam_track_relay import Budget
    b=Budget(tmp_path/'ledger',attempts=2,usd=.30)
    a=b.admit();b.finish(a,None,{'error_type':'TimeoutError'})
    assert b.charged==b.reserve_usd and b.admit()==2 and b.admit() is None


def test_partial_band_uses_code_geometry_and_does_not_approve_grasp(monkeypatch):
    r=robot();r.beam_observation['result']={'visible':False,'band_visible':True,'color_components':[{'center_px':[320,300]}]}
    monkeypatch.setattr(m,'partial_band_point',lambda r,b:[.7,.1])
    m.observe(r,1.)
    assert r.beam_memory['kind']=='partial_band_point_not_grasp'
    assert r.beam is None and not r.beam_memory['end_qualified']


def test_new_reacquisition_is_not_reported_first_attempt():
    from scripts.run_e2e_stage_probe import stage_metrics
    result=stage_metrics([{'event':'beam_tracking_reacquire_begin','robot_id':'r1'}],{'r1':10.,'r2':10.},True,10.)
    assert result['both_held'] and not result['first_attempt_success']
