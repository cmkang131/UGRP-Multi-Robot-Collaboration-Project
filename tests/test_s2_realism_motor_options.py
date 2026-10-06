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
