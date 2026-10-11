"""Regression for the two saved v147 mixed-axis commands, no physics or truth."""
import math
from types import SimpleNamespace
import pytest
from harness import zone_s3_pair_heading as heading
from harness import zone_s3_no_prior_contract as contract
from harness.zone_solo_cyan_pulse_cal import profile_key


@pytest.fixture(scope='module')
def profiles():
    return contract.controller_config()['pulse_calibration']['profiles']


def test_off_identity():
    obj=object()
    assert heading.attach_driver(obj,None) is obj


@pytest.mark.parametrize('left,turn',[(.021079902479462034,0.),(.02109973424044228,.00009277001542615792)])
def test_saved_mixed_command_is_replaced_before_pulse_model(profiles,left,turn):
    old=dict(kind='mecanum',forward=.11575916745889646,left=left,turn=turn,duration_s=.15)
    with pytest.raises(ValueError,match='one axis'):profile_key(old,False)
    action,p,score=heading.approach_proposal(profiles,(1.,0.,0.),(2.,.5),(2.,.5),math.pi)
    assert action['turn']!=0. and action['forward']==action['left']==0.
    assert profiles[profile_key(action,False)]==p
    assert score['phase']=='rotate_path'


def test_lateral_is_only_final_task_alignment_not_intermediate_waypoint(profiles):
    action,p,score=heading.approach_proposal(profiles,(0.,0.,0.),(.01,.05),(2.,0.),0.)
    assert action.get('left',0)==0
    lateral=next(p for p in profiles.values() if not p['loaded'] and p['axis']=='left' and p['duration_s']>=.10)
    from harness.zone_solo_cyan_pulse_cal import action_of
    a=action_of(lateral)
    for distance,alignment in [(.101,True),(.05,False)]:
        with pytest.raises(ValueError,match='final 0.10'):
            heading.validate_pulse(a,profiles,loaded=False,goal_distance=distance,alignment=alignment)
    heading.validate_pulse(a,profiles,loaded=False,goal_distance=.10,alignment=True)


def test_driver_waits_for_full_pulse_coast_and_delayed_feedback(profiles):
    calls=[]
    raw=dict(kind='mecanum',forward=.12,left=.08,turn=.1,duration_s=.15)
    d=SimpleNamespace(outcome=None,path=[(1.,1.)],goal=(1.,1.),goal_yaw=math.pi,
        tick=lambda t: calls.append(t) or [raw],
        loc=SimpleNamespace(estimate=lambda:dict(x=0.,y=0.,yaw=0.)))
    own=SimpleNamespace(pulse_profiles=profiles,last_report=SimpleNamespace(t_est=0.))
    heading.attach_driver(d,own,pair_heading=heading.OPTION)
    a=d.tick(1.)[0];p=profiles[profile_key(a,False)]
    assert d.tick(1.05)==[] and calls==[1.]
    assert d.tick(1.+p['duration_s'])==[dict(kind='hold')]
    end=1.+p['times'][-1]
    assert d.tick(end)==[]  # wall clock alone is insufficient
    own.last_report.t_est=end
    assert heading.moving(d.tick(end)[0]) and len(calls)==2


def test_actual_pair_driver_replaces_transit_mixture_and_keeps_dev_sigma(profiles):
    from tests.test_highpose_relook import executor, StuckPose
    from tests.test_zone_own_executor import Driver
    from harness.zone_own_driver import GuardedDriver
    from harness.zone_s3_dev_light import attach_driver, Audit
    own=executor('r2',StuckPose(sx=.2,sy=.2));fixture=Driver(own);fixture.frame()
    est=dict(initialized=True,x=-.9,y=-.85,yaw=0.,std_xy_m=.28,std_yaw_rad=.1,
        fix_age_s=.1,t=0.,last_fix_t=0.)
    loc=SimpleNamespace(predict_to=lambda t:est.update(t=t),estimate=lambda:dict(est))
    driver=GuardedDriver(loc,own.map,own.params,loaded=False,goal_xy=(-.4,-.6),
        door_xy=own.door_xy,initial_servo=dict(fixture.servo),seed=5,gate=own.gate,guard=own.guard)
    attach_driver(driver,own,Audit());driver.state='drive';driver.state_since=fixture.t
    driver.goal_yaw=0.
    localizer=SimpleNamespace(pulse_profiles=profiles,last_report=SimpleNamespace(t_est=fixture.t))
    heading.attach_driver(driver,localizer,pair_heading=heading.OPTION)
    rows=driver.tick(fixture.t)
    movement=[a for a in rows if heading.moving(a)]
    assert len(movement)==1 and profile_key(movement[0],False) in profiles
    assert sum(bool(movement[0].get(k)) for k in ('forward','left','turn'))==1
    assert movement[0]['left']==0 and est['std_xy_m']==.28


def test_actual_pair_submission_attaches_heading_before_any_control():
    from dataclasses import replace
    from harness.zone_s3_motion_runtime import Runtime
    from tests.test_solo_cyan_v106 import observation
    from harness.zone_s3_dev_light import OPTION as DEV
    config=contract.controller_config()
    config['options'].update(s3_dev_light=DEV,pair_heading=heading.OPTION)
    runtime=Runtime(contract.hp.resolve(contract.old.solo.MAP_ID)[0],contract.inputs()[2]['orders'],
        contract.ROOT/contract.old.solo.CALIBRATION,contract.old.solo.CALIBRATION_SHA,seed=14201,config=config)
    try:
        runtime.initial_commands(0.,{r:{1:2000,3:740,4:2320,5:1320,6:1500} for r in runtime.localizers})
        runtime.boot_finished_at=.1
        runtime.on_frames(.2,{r:observation(.2,1,rid=r) for r in runtime.localizers})
        pair=runtime.pair.producer
        for own in pair.actors.values():
            own.last_report=replace(own.last_report,x_m=-.9,y_m=-.85,yaw_rad=0.,std_xy_m=.28,std_yaw_rad=.01)
        for rid,partner in [('r1','r2'),('r2','r1')]:
            assert runtime.links[rid].submit(rid,'cargoX','B',partner,now=.2)['accepted']
        endpoints=pair.team.sessions[0]['endpoints']
        assert all(hasattr(ep.controller.driver,'s3_heading_audit') for ep in endpoints.values())
        assert pair.record()['pair_heading']['option']==heading.OPTION
        ep=endpoints['r2'];ctl=ep.controller;ctl.state='align';ep.own.now=.2
        from harness.zone_final_pair_vision import GRASP_RADIUS_M
        ob=ctl._align.__func__.__globals__['ob']
        cmd=ob.align_command(dict(grip_base_m=[GRASP_RADIUS_M,.04],axis_heading_rad=0.))
        ctl.drive(cmd,.2)
        assert ep.port.commands[-1]['turn']==.35 and ep.port.commands[-1]['duration_s']==.10
        count=len(ep.port.commands)
        ctl.tick(.25);assert len(ep.port.commands)==count
        ctl.tick(.3);assert ep.port.commands[-1]==dict(kind='hold')
        with pytest.raises(ValueError,match='alignment proof'):
            ep.port.apply(dict(kind='mecanum',forward=0.,left=.35,turn=0.,duration_s=.06),1.)
    finally:
        runtime.close()


def test_all_new_options_off_preserve_own_particles_commands_and_pose_bytes():
    import json
    import numpy as np
    from harness.zone_s3_continue import solo_factory as before
    from harness.zone_s3_motion_runtime import solo_factory as after
    from tests.test_solo_cyan_v106 import observation
    config=contract.controller_config()
    args=(contract.hp.resolve(contract.old.solo.MAP_ID)[0],contract.ROOT/contract.old.solo.CALIBRATION,contract.old.solo.CALIBRATION_SHA)
    old=before(config)(*args,seed=14201,robot_id='r1')
    config['options'].update(pair_heading='off',s3_exact_cache='off',s3_io='off')
    new=after(config)(*args,seed=14201,robot_id='r1')
    try:
        outputs=[]
        for own in (old,new):
            own.initial_commands(0.,{'r1':{1:2000,3:740,4:2320,5:1320,6:1500}})
            own.on_frames(.05,{'r1':observation(.05,1,rid='r1')})
            outputs.append(json.dumps(dict(commands=own.step(.05),poses=own.pose_log),sort_keys=True))
        assert outputs[0]==outputs[1]
        a,b=(o.pose.provider.loc._pf for o in (old,new))
        np.testing.assert_array_equal(a.px,b.px)
        np.testing.assert_array_equal(a.logw,b.logw)
        assert a.rng.bit_generator.state==b.rng.bit_generator.state
        assert old.pose.provider.identity_sha256==new.pose.provider.identity_sha256
    finally:
        old.close();new.close()


def test_host_pair_ports_match_s2_heading_primitive_and_native_expiry(tmp_path, profiles):
    from sim.s3_motion_ports import attach
    from sim.camera_robot_port import CameraRobotPort
    from sim.s2_align_pulse import FinePulsePort
    robots={r:SimpleNamespace(servo_command_pulses={1:2000,3:740,4:2320,5:1320,6:1500},
        set_motor_commands=lambda motors:None) for r in ('r1','r2','r3')}
    world=SimpleNamespace(robot=lambda rid:robots[rid],data=SimpleNamespace(time=0.))
    backend=SimpleNamespace(world=world,out=tmp_path,commands={},ports={r:CameraRobotPort(world,r,
        allow_reverse=True,allow_mecanum=True) for r in robots})
    original=dict(backend.ports)
    assert attach(backend) is backend and backend.ports==original and not list(tmp_path.iterdir())
    action,_,_=heading.approach_proposal(profiles,(0.,0.,0.),(1.,1.),(1.,1.),0.)
    with pytest.raises(ValueError):original['r2'].apply(action,0.)  # old port capped turn at .15
    attach(backend,pair_heading=heading.OPTION)
    for rid in ('r1','r2'):
        port=backend.ports[rid];assert isinstance(port,FinePulsePort)
        ack=port.apply(action,0.)
        assert all(abs(v)==.35 for v in ack['actuator_state']['motor_commands'])
        port.tick(action['duration_s'])
        assert not any(port._motor_commands)
    assert isinstance(backend.ports['r3'],FinePulsePort)
    backend.ports['r3'].apply(action,0.)


@pytest.mark.parametrize('enabled',[False,True])
def test_saved_v148_command_after_real_integer_clock_port_rebuild(tmp_path,monkeypatch,enabled):
    import json
    from pathlib import Path
    from sim.s3_motion_ports import PhysicsBackend, Previous, attach, PairPhasePort
    from sim.final_pair_highpose_clock import IntegerClock
    from sim.final_environment_checks import PhysicsBackend as BaseBackend
    from sim.camera_robot_port import CameraRobotPort
    from sim.s2_align_pulse import FinePulsePort
    saved=json.loads((Path(__file__).parent/'fixtures/path_heading/s3-v148-reset.json').read_text())
    robots={r:SimpleNamespace(servo_command_pulses={1:2000,3:740,4:2320,5:1320,6:1500},
        set_motor_commands=lambda motors:None) for r in ('r1','r2','r3')}
    backend=PhysicsBackend.__new__(PhysicsBackend)
    backend.world=SimpleNamespace(robot=lambda rid:robots[rid],data=SimpleNamespace(time=1.3000000000000178))
    backend.dt=.00025;backend.out=tmp_path
    backend.commands={r:dict(robot.servo_command_pulses) for r,robot in robots.items()}
    backend.bundle={'options':{'pair_heading':heading.OPTION if enabled else 'off'}}
    backend.ports={r:CameraRobotPort(backend.world,r,allow_reverse=True,allow_mecanum=True) for r in robots}
    rows=[];backend._append=lambda path,row:rows.append((path,row))
    monkeypatch.setattr(BaseBackend,'reset',lambda self,cap:self.now)  # no physics, issued reset clock only
    monkeypatch.setattr(Previous,'reset',IntegerClock.reset)
    # Reproduce the old constructor-only binding being lost by the REAL reset.
    attach(backend,pair_heading=heading.OPTION)
    IntegerClock.reset(backend,5.)
    assert all(type(p) is CameraRobotPort for p in backend.ports.values())
    with pytest.raises(ValueError,match='turn must be between'):
        backend.issue(saved['robot'],saved['action'])
    assert backend.reset(5.)==1.3
    if not enabled:
        assert all(type(p) is CameraRobotPort for p in backend.ports.values())
        with pytest.raises(ValueError,match='turn must be between'):
            backend.issue(saved['robot'],saved['action'])
        return
    assert all(isinstance(backend.ports[r],PairPhasePort) for r in ['r1','r2'])
    assert isinstance(backend.ports['r3'],FinePulsePort)
    backend.issue(saved['robot'],saved['action'])
    assert rows[-1][1]=={'t':1.3,**saved['action']}
    assert backend.ports['r2']._motor_commands==(-.35,.35,-.35,.35)
    assert backend.ports['r2']._drive_expires_at==pytest.approx(1.4)
    backend.ports['r2'].tick(1.40025)  # native substep after floating-point expiry
    assert not any(backend.ports['r2']._motor_commands)
    backend.issue('r3',saved['action'])
    assert backend.ports['r3']._motor_commands==(-.35,.35,-.35,.35)
    receipt=json.loads((tmp_path/'eval_only/pair-motion-ports.json').read_text())
    assert receipt['applied_after']=='IntegerClock.reset and grid snap'


def test_rgb_alignment_heading_uses_final_distance_and_preserves_nonarrival(profiles):
    from harness.zone_s3_pair_alignment import project
    far,p,s=project(profiles,(.3,.2,0.))
    assert far['turn'] and not far['forward'] and not far['left']
    final,p,s=project(profiles,(0.,.04,0.))
    assert final['turn'] and final['duration_s']==.10
    unresolved,p,s=project(profiles,(0.,0.,0.))
    assert p is None and unresolved is not None and not heading.moving(unresolved)


def test_coupled_exception_requires_pair_role_own_grasp_and_live_carry_enum():
    from harness.zone_s3_coupled_motion import authorized, HEADING_EXCEPTIONS
    pf=SimpleNamespace(load=SimpleNamespace(loaded=True))
    peers={'r2':dict(alive=True,state='carry')}
    ep=SimpleNamespace(own=SimpleNamespace(robot_id='r1',pose=SimpleNamespace(localizer=
        SimpleNamespace(pose=SimpleNamespace(provider=SimpleNamespace(loc=SimpleNamespace(_pf=pf)))))),
        controller=SimpleNamespace(state='carry'),status=SimpleNamespace(channel=
        SimpleNamespace(partner_view=lambda *a:peers)))
    assert list(HEADING_EXCEPTIONS)==['coupled_beam_carry'] and authorized(ep,1.)
    for state in ('approach','align','wait_carry'):
        ep.controller.state=state;assert not authorized(ep,1.)
    ep.controller.state='carry';peers['r2']['alive']=False;assert not authorized(ep,1.)
    peers['r2']['alive']=True;pf.load.loaded=False;assert not authorized(ep,1.)
    pf.load.loaded=True;ep.own.robot_id='r3';assert not authorized(ep,1.)


def test_coupled_native_port_keeps_legacy_mixture_only_when_both_grips_closed():
    from sim.s3_motion_ports import PairPhasePort
    from sim.camera_robot_port import CameraRobotPort
    robot=SimpleNamespace(servo_command_pulses={1:2000,3:740,4:2320,5:1320,6:1500},
        set_motor_commands=lambda motors:None)
    world=SimpleNamespace(robot=lambda rid:robot,data=SimpleNamespace(time=0.))
    closed={'r1':True,'r2':False}
    port=PairPhasePort(world,'r1',allow_reverse=True,allow_mecanum=True,
        min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1',coupled=lambda:all(closed.values()))
    old=CameraRobotPort(world,'r1',allow_reverse=True,allow_mecanum=True)
    action=dict(kind='mecanum',forward=.005,left=.02,turn=.001,duration_s=.15)
    with pytest.raises(ValueError,match='one axis'):port.apply(action,1.)
    closed['r2']=True
    assert port.apply(action,1.)==old.apply(action,1.)
    assert port._motor_commands==old._motor_commands
    port.tick(1.15);old.tick(1.15)
    assert port._motor_commands==old._motor_commands


def test_actual_coupled_predictor_keeps_posterior_and_legacy_continuous_command():
    import copy
    import numpy as np
    from harness.zone_s3_motion_runtime import solo_factory
    from harness.zone_s3_coupled_motion import attach_prediction
    from harness.zone_final_pair_vision import grasp_postures
    args=(contract.hp.resolve(contract.old.solo.MAP_ID)[0],contract.ROOT/contract.old.solo.CALIBRATION,
          contract.old.solo.CALIBRATION_SHA)
    runtime=solo_factory(contract.controller_config())(*args,seed=14201,robot_id='r1')
    try:
        pf=runtime.pose.provider.loc._pf
        px,w=pf.px.copy(),pf.logw.copy();rng=copy.deepcopy(pf.rng.bit_generator.state)
        attach_prediction(runtime,runtime.pose.provider.calibration['params'])
        np.testing.assert_array_equal(pf.px,px);np.testing.assert_array_equal(pf.logw,w)
        assert pf.rng.bit_generator.state==rng
        _,path=grasp_postures()
        pf.command(dict(t=0.,kind='initial_servo_command',pulses={**path[-1],1:2000,6:1500}))
        pf.command(dict(t=.1,kind='arm',servo_id=1,pulse=1420))
        assert pf.load.loaded and not runtime.flow.supported(runtime.pose.provider.servo)
        action=dict(t=.2,kind='mecanum',forward=.005,left=.02,turn=.001,duration_s=.15)
        pf.command(action);np.testing.assert_array_equal(pf.cmd,[.005,.02,.001])
        pf.predict_to(.35)
        assert pf.t==pytest.approx(.35) and pf.vel[1]>0
        pf.command(dict(t=.35,kind='hold'))
        pf.command(dict(t=.5,kind='arm',servo_id=1,pulse=2000))
        assert not pf.load.loaded
        pulse=dict(t=.6,kind='mecanum',forward=.35,left=0.,turn=0.,duration_s=.1)
        pf.command(pulse);pf.predict_to(.8)
        assert pf.t==pytest.approx(.8) and pf.vel[0]>0
        assert [r['mode'] for r in runtime.s3_coupled_motion['transitions']]==[
            'coupled_continuous','heading_pulse']
    finally:
        runtime.close()


def test_v148_bundle_and_standard_workflow_plan_do_not_execute(monkeypatch,capsys):
    import json
    from harness import zone_s3_motion_contract as c
    from scripts import run_s3_motion as runner
    from harness.zone_s3_coupled_motion import HEADING_EXCEPTIONS
    b=c.bundle('a'*40);c.verify(b)
    assert b['execution_bundle_id']=='zone-s3-motion-v148'
    assert b['heading_exceptions']==HEADING_EXCEPTIONS
    assert b['options']['heading_mode']=='path_tangent_v1'
    assert b['options']['pair_heading']==heading.OPTION
    assert b['s3_camera_binding']=='v3_persistent_v1'
    assert b['runtime_speedups_required']=='relay-cache-v1'
    assert not b['convergence_thresholds_changed']
    monkeypatch.setattr(runner,'run',lambda *a,**kw:pytest.fail('plan executed'))
    assert runner.main(['--expected-source-sha','a'*40,'--output','/nonexistent/plan'])==0
    assert not json.loads(capsys.readouterr().out)['execution_started']
