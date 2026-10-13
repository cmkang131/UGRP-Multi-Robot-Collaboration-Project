"""Finite synthetic own grids and actual route compiler; no physics/render/provider."""
import copy
import json
from types import SimpleNamespace
import numpy as np
import pytest
from harness import e2e_route_recovery as m
from harness import e2e_route_stage_probe as sp
from harness.e2e_goal_route import OPTION
from harness.own_map_navigation import ObservedGrid
from tests.test_e2e_goal_route import controller,ref,pulse_fixture


def scene(kind='free'):
    c=controller(own_route=OPTION);c.dev_light=True
    c.e2e_route_guard='dev_nominal_v1';c.e2e_route_coverage='native_v1';c.e2e_route_extent='goal_envelope_v1'
    g=c.explorer.grid
    if kind=='unknown':
        for cell in list(g.odds):
            if 7<=cell[0]<=12:g.odds.pop(cell);g.floor_frames.pop(cell)
    elif kind=='start':g.odds[(0,0)]=1.;g.wall_frames[(0,0)]={3}
    elif kind=='goal':g.odds[(20,0)]=1.;g.wall_frames[(20,0)]={3}
    elif kind=='snap':g.odds[(20,2)]=1.;g.wall_frames[(20,2)]={3}
    elif kind in ('narrow','wall'):
        for y in range(-15,16):
            if kind=='wall' or abs(y)>1:
                g.odds[(10,y)]=1.;g.wall_frames[(10,y)]={3}
    elif kind=='sigma':c.explorer.memory.self_map.odom.covariance=np.eye(3)*.1
    return c


def state(kind='free'):
    c=scene(kind)
    return sp.capture(c,dict(rgb=ref(3),pose_own_m=[0.,0.,0.]),now=1.3,profiles=pulse_fixture()[1]['profiles'])


@pytest.mark.parametrize('kind,expected', [('free',True),('unknown',False),('start',False),('goal',False),('narrow',False),('wall',False),('sigma',True),('snap',True)])
def test_same_state_routes_preserve_observation_and_carrier(kind,expected):
    s=state(kind);before=copy.deepcopy(s)
    baseline=sp.replay(s);candidate=sp.replay(s,m.OPTION)
    assert s==before
    assert candidate['generated']==expected
    assert candidate['input_sha256']==baseline['input_sha256']
    if kind=='unknown':
        assert baseline['generated'] and not baseline['observed_complete']
        assert candidate['diagnostics']['reason']=='UNKNOWN_CORRIDOR'
        assert candidate['diagnostics']['blocking_unknown_cells']>0
    if kind=='start':assert candidate['diagnostics']['reason']=='START_OCCUPIED'
    if kind=='sigma':assert candidate['diagnostics']['would_stop_sigma']
    if kind=='snap':
        assert not baseline['generated']
        assert 0 < candidate['diagnostics']['goal_shift_m'] <= .125
        assert candidate['route']['waypoints'][-1] != [2.,0.]


def test_nearest_goal_is_reachable_and_no_start_teleport():
    a=np.ones((9,14),bool);a[:,7]=False;a[4,6]=False
    result,target=m.nearest_path(a,np.ones_like(a,float),(2,4),(6,4),[.65,.45],np.zeros(2,int),.1,.125)
    assert result and tuple(result[-1]) in ((5,4),(6,3),(6,5))
    assert np.linalg.norm(target-[.65,.45])<=.125
    assert m.nearest_path(a,None,(7,4),(6,4),[.65,.45],np.zeros(2,int),.1,.125)[0] is None


def test_unknown_hint_never_loosens_real_wall_or_fixed_yaw_width():
    c=scene('narrow');g=c.explorer.grid
    result,d,focus=m.search(g,[0,0],[2,0],0,.02,dev_light=True)
    assert not result[3]
    assert d['carrier_blocks_observed_point_path']
    assert d['reason']=='UNKNOWN_CORRIDOR'  # possible detour around wall through unknown padding
    # Same corridor with a narrower singleton fits: the rejection is configuration space.
    assert m.astar(g.dense()[0]==-1,np.asarray(g.cell([0,0]))-g.dense()[1],np.asarray(g.cell([2,0]))-g.dense()[1])


def test_production_does_not_relax_sigma():
    s=state('sigma');s['dev_light']=False;s['attrs']['route_guard']='off'
    assert not sp.replay(s,m.OPTION)['generated']


def test_tf_conversion_and_full_compilation():
    s=state();s['map_to_odom']=[.1,.1,0.]
    r=sp.replay(s,m.OPTION)
    assert r['generated'] and r['route']['waypoints'][-1]==pytest.approx([2,0])
    assert r['diagnostics']['map_to_odom']==[.1,.1,0.]


def test_eval_separate_swept_geometry_not_waypoint_only():
    s=state();r=sp.replay(s,m.OPTION)
    e=dict(schema='ugrp.route_eval_rectangles.v1',input_sha256=r['input_sha256'],own_to_world=[0,0,0],bounds_xyxy=[-5,-5,5,5],obstacles_xyxy=[])
    assert sp.evaluate(r,s,e)['collision_free']
    e['obstacles_xyxy']=[[.94,-.03,.96,.03]]
    assert not sp.evaluate(r,s,e)['collision_free']
    assert sp.replay(s,m.OPTION)==r  # labels cannot influence the planner
    with pytest.raises(ValueError):sp.evaluate(r,s,{**e,'input_sha256':'bad'})
    with pytest.raises(Exception):sp.restore({**s,'eval_only':e})


def test_frontier_focus_uses_own_tf_and_expires():
    c=scene('unknown');rows=[np.array([-.5,1,0,0,0,0,0.]),np.array([.5,0,0,0,0,0,0.])]
    core=SimpleNamespace(frontiers=lambda *a:rows)
    c.explorer.navigator=SimpleNamespace(core=core)
    m.install(c);assert core.frontiers(None,None,None,[0,0]) is rows
    m.install(c,m.OPTION)
    c.e2e_route_focus=dict(t=1.3,own_points=[[.9,0.]])
    ranked=core.frontiers(None,None,None,[0,0]);assert ranked[0][0]==.5
    c.e2e_observed[-1]['t_sim']=20.
    assert core.frontiers(None,None,None,[0,0]) is rows


def test_registration_default_off_and_new_bundle(monkeypatch):
    from tests import test_e2e_camera_hold as p
    from scripts.run_e2e_ownmap_live import bundle,ROOT
    from harness.e2e_runtime_registration import require_current
    args,kw=[],{}
    def capture(*a,**k):args.extend(a);kw.update(k);return bundle(*a,**k)
    monkeypatch.setattr(p,'bundle',capture)
    p.test_registered_wheel_wait_candidate('zero_wheel_v1',276,'range_wall_v1')
    kw.update(stage_physics='release_dt1_v1',relook_giveup='dev_light_rest_v1',boundary_lifecycle='abort_v1',dialogue_call_policy='event_v1',call_snapshot='prepared_v1',speech_context='recent4_v1',post_relook='carry_nominal_v1',perception_fast='shadow_axes_v1',controller_timing='phase_v1',llm_memory='v1_commands',dialogue_decider='code_v1',explore_idle='idle5_v1',admission_clock='tick_v1')
    base=bundle(*args,**kw);assert base['execution_bundle_id']=='e2e18-v375'
    candidate=bundle(*args,**kw,route_recovery=m.OPTION);require_current(candidate,ROOT)
    assert candidate['execution_bundle_id']=='e2e18-v381'
    assert m.parent_for_validation(candidate)['e2e_options']==base['e2e_options']
    bad=copy.deepcopy(candidate);bad['route_recovery_parameters']['start_snap']=True
    with pytest.raises(ValueError):require_current(bad,ROOT)


def test_missing_snapshots_stay_in_expected_denominator(tmp_path):
    from scripts.run_e2e_route_stage_probe import run
    result=run({'cases':[dict(case_id='missing',seed=61009,snapshot=str(tmp_path/'missing'),sha256='x',subset='blocked')]})
    assert result['rows'][0]['status']=='HOST_ERROR'
    assert result['metrics']['blocked'][m.OPTION]['expected_N']==1
    assert result['metrics']['blocked'][m.OPTION]['attempted_N']==0


def test_rotated_map_is_not_mistaken_for_own_start_frame():
    from harness.self_odom_grid import transform
    c=scene();old=c.explorer.grid;tf=np.array([.5,-.3,np.pi/2])
    points=transform([old.point(cell) for cell in old.odds],tf)
    g=ObservedGrid('r1',.1)
    for i in (1,2,3):g.observe(robot_id='r1',frame_id=i,pose=[0,0,0],floor_xy=points)
    c.explorer.grid=g;c.explorer.map_to_odom=tf
    snapshot=sp.capture(c,dict(rgb=ref(3),pose_own_m=[0.,0.,0.]),now=1.3,profiles=pulse_fixture()[1]['profiles'])
    result=sp.replay(snapshot,m.OPTION)
    assert result['generated']
    assert result['route']['waypoints'][-1]==pytest.approx([2.,0.])
