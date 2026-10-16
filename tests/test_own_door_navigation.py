import copy,json,math
from types import SimpleNamespace
import numpy as np
import pytest
from harness.own_door_memory import DoorMemory,candidates,geometry,floor_connection
from harness.own_door_navigation import attach,attach_return,DoorSystem,DoorNavigator,topology,door_route
from harness.own_map_navigation import ObservedGrid
from harness.active_wall_mapping import inverse
from harness.self_odom_grid import transform


def observation(pose=(0,0,0)):
    lines=[[[2,-1],[2,-.4]],[[3,-.55],[3,.55]],[[2,.4],[2,1]]]
    floor=np.array([[x,y] for x in np.arange(.2,3.2,.025) for y in np.arange(-.5,.51,.025)])
    return dict(segments=[transform(p,inverse(pose)).tolist() for p in lines],
        floor_xy=transform(floor,inverse(pose)).tolist(),camera=[0.,0.])


def test_complete_points_reject_terminal_and_occluded_back_wall():
    c=candidates(observation()['segments'])
    assert len(c)==1 and c[0]['kind']=='type_I'
    np.testing.assert_allclose(geometry(c[0])[0],[2,0])
    assert candidates([[[2,-1],[2,-.4]],[[2,.4],[2,1]]])==[] # no farther return: one CP only
    assert candidates([[[5,-1],[5,-.4]],[[6,-.55],[6,.55]],[[5,.4],[5,1]]])==[]


def test_type_ii_cp_to_perpendicular_observed_line():
    segs=[[[2,-1],[2,0]],[[3,.1],[3,1]],[[1,1],[2.5,1]]]
    assert any(c['kind']=='type_II' for c in candidates(segs))


def test_fresh_frontal_floor_evidence_and_provenance():
    m=DoorMemory('r3');o=observation()
    m.observe(robot_id='r3',t=0,frame_id=1,pose=[0,0,0],observation=o)
    assert m.tracks[0]['confirmed_t'] is None
    p=[.1,0,0];o=observation(p)
    m.observe(robot_id='r3',t=1,frame_id=2,pose=p,observation=o)
    d=m.tracks[0];assert d['confirmed_t']==1 and d['confidence']==1
    assert d['confirmation_evidence']['direct_floor'] and len(d['observations'])==2
    assert len(m.tracks)==1 and m.raw_candidates==2
    with pytest.raises(ValueError):m.observe(robot_id='r3',t=2,frame_id=2,pose=p,observation=o)
    with pytest.raises(ValueError):m.observe(robot_id='r2',t=2,frame_id=3,pose=p,observation=o)
    assert m.snapshot([1,0,0])[0]['endpoints']!=m.tracks[0]['endpoints']


def test_unknown_floor_or_current_obstacle_never_confirms():
    o=observation();d=candidates(o['segments'])[0]
    assert not floor_connection(d,[0,0,0],[],[0,0],o['segments'])[0]
    assert not floor_connection(d,[0,0,0],o['floor_xy'],[0,0],o['segments']+[[[2,-.1],[2,.1]]])[0]
    m=DoorMemory('r3')
    for i in range(2):m.observe(robot_id='r3',t=i,frame_id=i,pose=[0,0,0],observation=o)
    assert m.tracks[0]['confirmed_t'] is None # duplicate viewpoint not independent evidence


def grid():
    g=ObservedGrid('r3',.05)
    for x in range(-40,41):
        for y in range(-40,41):
            c=(x,y);g.odds[c]=1. if x==0 and abs(y)>=8 else -1.;g.floor_frames[c]={1}
    return g


def test_topology_confirmed_cut_and_unknown_not_a_room():
    g=grid();d=dict(id='own:1',endpoints=[[0,-.4],[0,.4]],confirmed_t=1)
    graph,room=topology(g,[d],[-1,0,0])
    assert len(graph['edges'])==1
    assert door_route(graph,room([-1,0]),room([1,0]))[0][0]['door']=='own:1'
    assert door_route(graph,room([-1,0]),room([20,0])) is None
    graph,room=topology(g,[dict(d,confirmed_t=None)],[-1,0,0])
    assert not graph['edges'] and room([-1,0])==room([1,0])


def test_mission_not_blacklisted_and_local_waypoint_failure_recorded():
    s=DoorSystem('r3','room_doors_v1');n=DoorNavigator(s)
    n.mission=np.array([2.,0]);n.target=n.mission.copy();n.requested_goal=n.mission.copy()
    n.action_failed(2,'recovery_exhausted')
    assert n.mission.tolist()==[2,0] and not n.blacklist
    n.target=np.array([1.,0]);n.local_id='own:1';n.action_failed(3,'no_path')
    assert len(n.blacklist)==1 and 'own:1' in n.viewed
    assert n.events[-1]['reason']=='mission_retained_local_action_failed'


def test_options_off_identity_and_wrong_option_fail():
    class Poison:
        def __getattribute__(self,k):raise AssertionError(k)
    p=Poison();assert attach(p) is p and attach_return(p) is p
    with pytest.raises(ValueError):attach(p,door_navigation='room_doors_v1')


def test_off_original_trace_bytes_and_on_hook():
    from tests.test_active_navfn_start import ARGS
    from harness.active_navfn_start import make_mapper
    from harness.active_camera import SEARCH
    a=make_mapper('r3',0,SEARCH,navigation_start='navfn_recovery_v1',frontier_observation='yamauchi_cycle_v1',**ARGS)
    b=attach(make_mapper('r3',0,SEARCH,navigation_start='navfn_recovery_v1',frontier_observation='yamauchi_cycle_v1',**ARGS))
    obs=dict(segments=[],features=[],floor_xy=[[.7,-.2],[.7,.2]],camera=[.124,0.]);rgb=np.zeros((480,640,3),np.uint8)
    kw=dict(robot_id='r3',t=2.,frame_id=1,rgb=rgb,servo=SEARCH,observation=obs)
    assert json.dumps(a.receive(**kw))==json.dumps(b.receive(**kw))
    c=attach(make_mapper('r3',0,SEARCH,navigation_start='navfn_recovery_v1',frontier_observation='yamauchi_cycle_v1',**ARGS),
        door_detector='complete_points_v1',door_navigation='room_doors_v1')
    _,trace=c.receive(**kw)
    assert c.door_system.memory.seen=={1} and trace['doors']==[]


def test_confirmed_door_route_and_frontal_view_selection():
    from harness.public_navigation_unknown import from_observed_grid
    s=DoorSystem('r3','room_doors_v1');s.grid=grid();n=DoorNavigator(s);p=np.array([-1.,0.,0.])
    d=dict(id='own:1',endpoints=[[0,-.4],[0,.4]],width_m=.8,first_t=0.,confirmed_t=1)
    s.memory.tracks=[d];cm=from_observed_grid(s.grid,p,{},set())
    target,key,heading=n.choose(cm,p,1,[1,0])
    assert key=='own:1' and target[0]>.0 and heading is None
    s.memory.tracks[0]['confirmed_t']=None
    target,key,heading=n.choose(cm,p,2,None)
    assert key=='own:1' and heading==pytest.approx(0) and target[0]==pytest.approx(-1)
    s.sigma=.1;n.update(cm,p,2,None)
    assert n.look is not None and not n.full_look
    command=n.command(cm,p,{},2.2)
    assert command['turn']==0 and 'own:1' in n.viewed


def test_evaluation_unique_match_denominator():
    import importlib.util
    from pathlib import Path
    path=Path(__file__).parents[1]/'experiments/2026-10-08-own-door-navigation/code/offline.py'
    spec=importlib.util.spec_from_file_location('door_score',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    d=dict(id='D',axis='x',width_m=.8,center_m=[2,0])
    pred=dict(id='own:1',first_t=1.,endpoints=[[2,-.4],[2,.4]],width_m=.8)
    r=m.metrics([pred,dict(pred,id='duplicate')],[d],[0,0,0],[0])
    assert r['tp']==1 and r['fp']==1 and r['precision']==.5 and r['recall_visible']==1.


def test_unconfirmed_gap_on_mission_path_requests_view_before_crossing():
    from harness.public_navigation_unknown import from_observed_grid
    s=DoorSystem('r3','room_doors_v1');s.grid=grid();n=DoorNavigator(s);p=np.array([-1.,0.,0.])
    d=dict(id='own:1',endpoints=[[0,-.4],[0,.4]],width_m=.8,first_t=0.,confirmed_t=None)
    s.memory.tracks=[d];cm=from_observed_grid(s.grid,p,{},set())
    target,key,heading=n.choose(cm,p,1,[1,0])
    assert key=='own:1' and target[0]<0 and heading==pytest.approx(0)
    n.viewed.add(key)
    assert n.choose(cm,p,2,[1,0])==(None,None,None)
