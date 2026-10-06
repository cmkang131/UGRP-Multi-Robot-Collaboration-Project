import copy
import json
from types import SimpleNamespace as NS
import numpy as np
import pytest
from test_solo_cyan_v106 import static, cal, FakePose, FakeVision, rt
from harness.zone_solo_cyan_real_output import Runtime, primitive
from sim.s2_real_output import RealPrimitivePort, StagnationGuard
from sim.camera_robot_port import CameraRobotPort


def test_off_runtime_commands_and_records_are_byte_identical(static, cal):
    old = rt.Runtime(static,None,None,provider_factory=lambda *a,**k:FakePose(cal),vision_factory=FakeVision)
    new = Runtime(static,None,None,provider_factory=lambda *a,**k:FakePose(cal),vision_factory=FakeVision)
    for r in (old,new):
        r.initial_commands(0.,{'r3':{1:1500,**rt.high.HIGH}})
        r.last_report=r.pose.report(1.);r.state='carry';r.receipt=True
        r.drive=lambda *a,**k:([{'kind':'mecanum','forward':.123456789,'left':-.003,'turn':-.0,'duration_s':.1}],False)
    for t in (1.,1.05,1.1,1.2):
        a,b=old.step(t),new.step(t)
        assert json.dumps(a).encode()==json.dumps(b).encode()
        for r,rows in ((old,a),(new,b)):
            for rid,action in rows:r.on_command(rid,t,action)
    assert json.dumps(old.record()).encode()==json.dumps(new.record()).encode()
    old.close();new.close()


def port(cls, **kwargs):
    c=NS(servo_command_pulses={1:2000,3:740,4:2320,5:1320,6:1500},set_motor_commands=lambda x:None)
    w=NS(robot=lambda rid:c,data=NS(time=0.))
    return cls(w,'r3',allow_reverse=True,allow_mecanum=True,**kwargs)


def test_off_port_ack_and_actual_wheel_bytes_unchanged():
    a,b=port(CameraRobotPort),port(RealPrimitivePort)
    for i,u in enumerate((.0,.03,.123456789,-.04)):
        row=dict(kind='mecanum',forward=u,left=.009,turn=-.07,duration_s=.1)
        assert primitive(row) is row
        assert json.dumps(a.apply(row,float(i))).encode()==json.dumps(b.apply(row,float(i))).encode()
        a.tick(i+.1);b.tick(i+.1)
        assert a._motor_commands==b._motor_commands==(0.,0.,0.,0.)


def test_real_signed_primitive_basis_duration_and_expiry():
    for axis,value,duration in [('forward',-.04,.1),('left',.08,.65),('turn',-.12,.1)]:
        p=port(RealPrimitivePort,min_wheel_cmd='real_v1')
        a=dict(kind='mecanum',forward=0.,left=0.,turn=0.,duration_s=.1);a[axis]=value
        b=primitive(a,'real_v1');assert b[axis]*value>0 and b['duration_s']==duration
        ack=p.apply(b,0.)
        expected=.65 if axis=='left' else .35
        assert all(abs(x)==expected for x in ack['actuator_state']['motor_commands'])
        p.tick(duration);assert not any(p._motor_commands)
    with pytest.raises(ValueError):p.apply(dict(kind='mecanum',forward=.35,left=.65,turn=0.,duration_s=.65),1.)


def test_real_pulse_is_not_overwritten_and_stop_precedes_next_command(static,cal):
    r=Runtime(static,None,None,min_wheel_cmd='real_v1',provider_factory=lambda *a,**k:FakePose(cal),vision_factory=FakeVision)
    r.initial_commands(0.,{'r3':{1:1500,**rt.high.HIGH}})
    r.last_report=r.pose.report(1.);r.state='carry';r.receipt=True
    r.drive=lambda *a,**k:([dict(kind='mecanum',forward=0.,left=.08,turn=0.,duration_s=.1)],False)
    assert r.step(1.)[0][1]['left']==.65
    assert r.step(1.1)==[] and r.step(1.6)==[]
    assert r.step(1.65)==[('r3',{'kind':'hold'})]
    assert r.step(1.7)==[]
    assert r.step(1.75)[0][1]['left']==.65
    r.close()


def test_eval_stagnation_disabled_and_strict_time_distance_boundaries():
    pytest.importorskip('mujoco')
    from sim.s2_realism import PhysicalStop
    off=StagnationGuard();on=StagnationGuard('window120_v1')
    for t in (0.,119.99):
        row=dict(t=t,robot_xyz_m=[0,0,0]);off.check(row);on.check(row)
    with pytest.raises(PhysicalStop,match='STAGNATION'):
        on.check(dict(t=120.,robot_xyz_m=[.0099,0,0]))
    off.check(dict(t=900.,robot_xyz_m=[0,0,0]))
    moving=StagnationGuard('window120_v1')
    for t,x in [(0,0),(60,.011),(120,0)]:moving.check(dict(t=t,robot_xyz_m=[x,0,0]))
    edge=StagnationGuard('window120_v1')
    edge.check(dict(t=0,robot_xyz_m=[0,0,0]));edge.check(dict(t=120,robot_xyz_m=[.01,0,0]))


def test_diagnostic_numpy_scalars_serialize_without_losing_boolean_type(tmp_path):
    from scripts.diagnose_s2_real_output_v112 import write
    p=tmp_path/'result.json'
    write(p,dict(refit_required=np.bool_(True),relative_main_axis_error=np.float64(2.),samples=np.int64(411)))
    assert json.loads(p.read_text())==dict(refit_required=True,relative_main_axis_error=2.,samples=411)


def test_replacement_diagnostic_preserves_used_seed_and_reserves_new_forward():
    from harness.s2_real_output_diagnostic_v112 import bundle,ROOT
    from sim.workflow_manager import catalog
    b=bundle('a'*40,min_wheel_cmd='real_v1')
    assert [r['seed'] for r in b['task']['runs']]==[1038,1035,1036]
    assert any(r['id']==b['execution_bundle_id'] and r['version']=='7.5.0' for r in catalog(ROOT)[0]['workflows'])
    assert b['options']['dead_reckoning']=='off'


def test_v113_options_default_off_and_registered_model_hash():
    from harness import zone_s2_realism_contract_v113 as c
    from scripts.run_s2_realism_v113 import parser
    a=parser().parse_args(['--expected-source-sha','a'*40,'--output','/tmp/not-running','--seed','1037'])
    assert all(getattr(a,k)=='off' for k in c.NEW_OPTIONS)
    off=c.bundle('a'*40,seed=1037,stage_probe='pick',pickup_slot='P1-2')
    on=c.bundle('a'*40,seed=1037,stage_probe='pick',pickup_slot='P1-2',**c.NEW_OPTIONS)
    assert off['motion_model'] is None and on['motion_model']['option']=='v7_diag_v1'
    assert on['supervisor']['stagnation']['window_sim_s']==120
    assert on['options']['setdown_relook']=='off' and on['options']['grasp_check']=='pickup_site_v1'
    with pytest.raises(ValueError):c.bundle('a'*40,seed=1033,stage_probe='pick',pickup_slot='P1-2')


def test_fixed_v7_model_drives_real_pf_recursion_and_keeps_old_provider(static):
    from harness.zone_solo_cyan_v7_motion import Runtime as NewRuntime
    from harness import zone_s2_realism_contract_v113 as c
    from harness.zone_solo_cyan_camera_v3 import build_provider
    model=json.loads((c.ROOT/c.MOTION_MODEL).read_text())
    r=NewRuntime(static,c.ROOT/c.old.CALIBRATION,c.old.CALIBRATION_SHA,min_wheel_cmd='real_v1',
                 dead_reckoning='v7_diag_v1',motion_model=model,camera_profile=c.camera.PROFILE_ID,
                 grasp_check='pickup_site_v1',setdown_relook='off')
    baseline=build_provider(static,c.ROOT/c.old.CALIBRATION,c.old.CALIBRATION_SHA)
    try:
        pf=r.pose.provider.loc._pf;old=baseline.provider.loc._pf
        assert 'real_v7_motion' not in vars(old) and 'deadband' in old.params['motion_loaded']
        for loaded in (False,True):
            pf.t=0.;pf.vel=np.zeros(3);pf.initialized=False;pf.load.loaded=loaded
            pf.command(dict(t=0.,kind='mecanum',forward=.35,left=0.,turn=0.,duration_s=.1))
            pf.predict_to(.05)
            expected=(1-np.exp(-.05/np.array(model['tau_axis_s'])))*(np.array(model['gain'])@np.array([.35,0,0]))
            np.testing.assert_allclose(pf.vel,expected,atol=1e-12)
        assert r.pose.source!=baseline.source and 'v7_motion_option' in r.pose.provider.runtime_contract
    finally:r.close();baseline.close()
