import copy,json,math
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from harness import goal_route_continuous as m
from harness.active_camera import SEARCH
from harness.own_traversal_graph import heading_twist
from test_own_traversal_graph import sample


def test_off_is_identity_without_reading_inputs():
    class Poison:
        def __getattribute__(self,k):raise AssertionError(k)
    p=Poison();assert m.attach(p) is p
    cal=m.StationaryPitch();assert cal.observe(p,t=0,reading=None,servo=None,observation=None,last_command=None) is p
    assert cal.camera(p) is p
    with pytest.raises(ValueError):m.attach(p,goal_route='bad')
    with pytest.raises(ValueError):m.StationaryPitch(pitch_calibration=m.PITCH)


def test_extracted_heading_is_byte_identical_to_previous_law():
    rng=np.random.default_rng(4)
    for _ in range(100):
        pose=rng.normal(size=3);target=rng.normal(size=2);d=target-pose[:2]
        angle=float(m.wrap(math.atan2(d[1],d[0])-pose[2]))
        expected=(np.array([0.,0.,float(np.clip(angle/.1,-.5,.5))]),'traversal_rotate_forward') if abs(angle)>math.radians(10) else (np.array([min(.12,float(np.linalg.norm(d))/.2),0.,0.]),'traversal_forward')
        got=heading_twist(pose,target)
        assert got[0].tobytes()==expected[0].tobytes() and got[1]==expected[1]


def fake_controller():
    goal=SimpleNamespace(observe=lambda *a,**kw:([],None,{}),detector=lambda *a,**kw:([],np.zeros((3,3),int),{}),options=SimpleNamespace(min_pixels=1))
    e=SimpleNamespace(robot_id='r3',started=0.,goal=goal,navigator=SimpleNamespace(reset_action=lambda:None))
    return m.GoalRoute(e)


def test_seen_not_reached_and_goal_stops_frontier_immediately():
    c=fake_controller();c.graph.observe(sample(1))
    c._entity('B',[2,0],1,1,'x');c._select(1)
    assert c.stage=='approach' and c.active=='B' and c.leg_start==0
    c.current_patches=[{'confirmed_t':1}];c.labels=np.ones((3,3))
    for i in range(2,10):c._arrival(i,i,np.zeros(3),False)
    assert not c.reached
    # Current near RGB is mandatory, stale remembered B is insufficient.
    c.current_patches=[]
    for i in range(10,16):c._arrival(i,i,np.array([2,0,0]),False)
    assert not c.reached
    c.current_patches=[{'confirmed_t':1}]
    for i in range(16,21):c._arrival(i,i,np.array([2,0,0]),False)
    assert 'B' in c.reached and c.stage=='explore' and c.leg_start==20


def test_continuous_temporal_return_after_both_arrivals_and_terminal_sixth_frame():
    c=fake_controller();c.graph.observe(sample(1));c.graph.observe(sample(2,.32))
    c._entity('B',[.32,0],2,2,'x');c._entity('box',[.32,0],2,2,'x')
    c.current_patches=[{'confirmed_t':2}];c.labels=np.ones((3,3))
    c._select(2)
    for t in range(3,8):c._arrival(t,t,np.array([.32,0,0]),True)
    c._select(8)
    for t in range(8,13):c._arrival(t,t,np.array([.32,0,0]),True)
    assert c.stage=='return' and c.graph.sealed and c.route['nodes']==[1,0]
    assert all(e['kind']=='temporal' for e in c.graph.edges)
    c.done=c.declared=True;c.stage='declared';c.last_trace={'tracking_reset':False}
    for i in range(6):
        cmd,tr=c.receive(robot_id='r3',t=20+i,frame_id=20+i,rgb=None,servo=None,observation=None,frame_sha256='x')
        assert cmd['kind']=='hold' and tr['stage']=='declared' and c.declared


def test_stationary_pitch_uses_only_settled_own_input_and_60s_bound():
    c=m.StationaryPitch(pitch_calibration=m.PITCH,ultrasonic_front='on_v1')
    obs={'segments':[[[1.,-.3],[1.,.3]]],'camera_origin':[0,0,.23]}
    reading={'valid':True,'range_m':1.2}
    e=c.observe(None,t=0,reading=reading,servo=SEARCH,observation=obs,last_command={'kind':'mecanum','t':0,'duration_s':.2})
    assert e['reason']=='command_not_settled'
    e=c.observe(None,t=1,reading=reading,servo=SEARCH,observation=obs,last_command={'kind':'hold','t':.8})
    assert e['accepted'] and c.offset is not None
    before=copy.deepcopy(c.values)
    assert c.observe(None,t=61,reading=None,servo=None,observation=None,last_command=None)['done']
    assert c.values==before


def test_localization_only_on_existing_uncertainty_or_repeat_not_forced_loss(monkeypatch):
    c=fake_controller();c.graph.observe(sample(1));g=SimpleNamespace(odom=SimpleNamespace(covariance=np.eye(3)*1e-6))
    c.explorer.memory=SimpleNamespace(self_map=g)
    calls=[]
    monkeypatch.setattr(c.graph,'match',lambda *args:(calls.append(args) or {'status':'rejected','reason':'unobservable'}))
    c.dev_light=True
    c._localize(sample(2),360);assert calls==[]
    g.odom.covariance=np.diag([.15**2,.01,.0001]);c._localize(sample(3),361)
    assert len(calls)==1 and c.events[-1]['reason']=='would_stop_tracking_uncertain' and not c.events[-1]['reset']


def test_persistent_mission_is_not_blacklisted():
    n=m.MissionNavigator();n.mission=np.array([1.,2.]);n.target=n.mission.copy();n.requested_goal=n.mission.copy()
    n.action_failed(3,'recovery_exhausted')
    assert not n.blocked(n.mission,.05) and n.events[-1]['reason']=='mission_retained_local_action_failed'


def test_registered_cohort_workflow_and_no_reset():
    from scripts.run_goal_route_continuous import bundle,SEEDS
    from sim.workflow_manager import plan
    for i in SEEDS:
        b=bundle(i,'a'*40)
        assert b['map_id']=='zone_wide_door_geometry_v3' and not b['schedule']['forced_loss']
        assert b['options']['pitch_calibration']=='off' and b['schedule']['leg_cap_s']==270
        assert all(b['options'][k]=='off' for k in ('route_hygiene','scan_accumulation','place_gate'))
    p=plan(Path(__file__).parents[1],'goal-route-continuous-dev',['--seed','55001','--output','/tmp/no-physics','--expected-source-sha','a'*40])
    assert 'scripts.run_goal_route_continuous' in p['command']


def test_standard_p1_scene_registry_spawn_without_physics():
    from scripts.run_goal_route_continuous import bundle
    from sim.goal_route_continuous import make_scene
    for seed in range(55001,55010):
        b=bundle(seed,'a'*40);scene=make_scene(b,seed)
        assert scene.config['static_map']['map_id']==b['map_id']
        p=scene.config['setup_only']['spawns']['r3']
        assert [p[0],p[1],p[3]]==b['spawn']
        assert scene.config['robot_model']=='masterpi_v3'
        sp=list(scene.config['setup_only']['spawns'].values())
        assert all(math.dist(a[:2],b[:2])>.3 for i,a in enumerate(sp) for b in sp[i+1:])


def test_completed_B_is_still_measured_but_no_longer_overrides_frontier():
    goal=SimpleNamespace(detector=lambda *a,**kw:([],None,{}),observe=lambda *a,**kw:([{'center_odom_m':[1,1]}],None,{}))
    e=SimpleNamespace(robot_id='r3',started=0.,goal=goal)
    c=m.GoalRoute(e)
    assert len(e.goal.observe()[0])==1
    c.reached['B']={'t':10}
    assert e.goal.observe()[0]==[]


def test_actual_factory_hold_command_and_continuous_issue_contract(monkeypatch):
    from scripts.run_goal_route_continuous import actor,controller
    e=actor('r3',0.,SEARCH,active_mapping='frontier_rbpf_v1',active_loop='information_gain_v1',seed=55001,
        active_recovery='nav2_frontier_v1',navigation_map='public_ros_v8',motion_model='s2_pulse_v122_rotL_v1')
    c=controller(e);e.navigator.phase='wait'
    monkeypatch.setattr(e,'receive',lambda **kw:({'t':kw['t'],'kind':'hold'},dict(t=kw['t'],frame_id=kw['frame_id'],
        local_pose=[0,0,0],pose=[0,0,0],status='recover_wait',path=[],goal={'robot_id':'r3','coordinate_frame':'r3/own_odom','candidates':[]})))
    monkeypatch.setattr(m,'own_measurement',lambda *a:{})
    monkeypatch.setattr(c.sensor,'measure',lambda *a:[])
    monkeypatch.setattr(c,'detect_boxes',lambda *a:[])
    cmd,tr=c.receive(robot_id='r3',t=1.,frame_id=1,rgb=np.zeros((480,640,3),np.uint8),servo=SEARCH,
        observation={'segments':[],'camera':[0,0]},frame_sha256='x')
    assert cmd['kind']=='hold' and not tr['tracking_reset'] and c.graph.frames==1
    calls=[];monkeypatch.setattr(e,'command',lambda cmd:calls.append(cmd))
    c.stage='approach';c.command(cmd);c.stage='return';c.command(cmd)
    assert calls==[cmd,cmd]


def test_evaluation_shortest_path_respects_wall_and_door():
    import importlib.util
    path=Path(__file__).parents[1]/'experiments/2026-10-09-goal-route-continuous/code/report.py'
    spec=importlib.util.spec_from_file_location('goal_route_report',path);report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)
    static={'obstacles':[{'center_m':[0,-1],'half_extents_m':[2,.05]},
        {'center_m':[0,1],'half_extents_m':[2,.05]}, {'center_m':[-2,0],'half_extents_m':[.05,1]},
        {'center_m':[2,0],'half_extents_m':[.05,1]}, {'center_m':[0,-.4],'half_extents_m':[.05,.6]}]}
    dist=report.shortest(static,[-1,0],[1,0])
    assert dist is not None and dist>2


def test_own_range_channel_contains_no_hit_identity_and_off_no_reads():
    from sim.goal_route_continuous import PhysicsBackend
    b=PhysicsBackend.__new__(PhysicsBackend);b.range_rig=None
    assert b.own_range() is None
    class Rig:
        def tick(self,t):self.tick_time=t
        def provider(self,rid):
            assert rid=='r3'
            return SimpleNamespace(report=lambda t:SimpleNamespace(t_meas=t,range_m=1.2,valid=True,status='ok'))
    b.range_rig=Rig();b.world=SimpleNamespace(data=SimpleNamespace(time=3.2))
    reading=b.own_range()
    assert reading==dict(t=3.2,range_m=1.2,valid=True,status='ok')
    assert set(reading)=={'t','range_m','valid','status'}
