import json
from types import SimpleNamespace as NS
import pytest
from test_solo_cyan_v106 import static, cal, FakePose, FakeVision, rt
from test_s2_realism_motor_options import port
from harness.zone_solo_cyan_v7_motion import Runtime as Previous
from harness.zone_solo_cyan_align_pulse import Runtime, alignment_primitive
from sim.s2_real_output import RealPrimitivePort
from sim.s2_align_pulse import FinePulsePort


def request():
    # Saved last s1039 request: the old conversion issued -.65 for .65 s.
    return dict(kind='mecanum',forward=.0198578821776597,left=-.021275135855503044,
                turn=-.00014774986606577487,duration_s=.1)


def make(cls, static, cal, **kw):
    r=cls(static,None,None,min_wheel_cmd='real_v1',provider_factory=lambda *a,**k:FakePose(cal),
          vision_factory=FakeVision,**kw)
    r.initial_commands(0.,{'r3':{1:2000,**rt.high.HIGH}})
    r.last_report=r.pose.report(1.);r.state='align';r.target=[.2493529052,-.0147828454]
    r.last_obs=dict(frame_id=1,sim_time=1.)
    r._control=lambda now,idle:[request()]
    return r


def test_default_off_previous_commands_and_records_byte_identical(static,cal):
    a,b=make(Previous,static,cal),make(Runtime,static,cal)
    try:
        for t in (1.,1.05,1.65,1.7,1.75):
            old,new=a.step(t),b.step(t)
            assert json.dumps(old).encode()==json.dumps(new).encode()
            for obj,rows in ((a,old),(b,new)):
                for rid,action in rows:obj.on_command(rid,t,action)
        assert json.dumps(a.record()).encode()==json.dumps(b.record()).encode()
        action=request();assert alignment_primitive(action) is action
        p,q=port(RealPrimitivePort,min_wheel_cmd='real_v1'),port(FinePulsePort,min_wheel_cmd='real_v1')
        coarse=dict(kind='mecanum',forward=0.,left=-.65,turn=0.,duration_s=.65)
        assert json.dumps(p.apply(coarse,0.)).encode()==json.dumps(q.apply(coarse,0.)).encode()
    finally:a.close();b.close()


def test_saved_loss_request_becomes_short_fixed_signed_pulse_and_expires_between_frames():
    a=alignment_primitive(request(),'real_fine_v1')
    assert a==dict(kind='mecanum',forward=0.,left=-.35,turn=0.,duration_s=.06)
    p=port(FinePulsePort,min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1')
    assert p.apply(a,0.)['actuator_state']['motor_commands']==[.35,-.35,-.35,.35]
    p.tick(.05975);assert any(p._motor_commands)
    p.tick(.06);assert p._motor_commands==(0.,0.,0.,0.)
    for key,value in [('forward',.35),('left',-.65),('duration_s',.05)]:
        bad=dict(a);bad[key]=value
        with pytest.raises(ValueError):p.apply(bad,1.)


def test_fresh_post_stop_frame_required_and_only_alignment_changes(static,cal):
    r=make(Runtime,static,cal,alignment_pulse='real_fine_v1')
    try:
        assert r.step(1.)[0][1]['duration_s']==.06
        assert r.step(1.05)==[]
        assert r.step(1.1)==[('r3',{'kind':'hold'})]
        assert r.step(1.15)==[]
        assert r.step(1.2)==[]  # even now >= deadline, old capture cannot trigger motion
        r.last_obs=dict(frame_id=2,sim_time=1.2)
        assert r.step(1.2)[0][1]['left']==-.35
        r.step(1.3);r.state='carry';r.last_obs=dict(frame_id=3,sim_time=1.5)
        assert r.step(1.5)[0][1]['left']==-.65
        assert len(r.record()['alignment_pulse']['transformations'])==2
    finally:r.close()


def test_fine_port_survives_integer_clock_reset():
    pytest.importorskip('mujoco')
    from sim.final_pair_highpose_clock import IntegerClock
    from sim.s2_real_output_reset import backend_class as old_backend
    from sim.s2_align_pulse import backend_class
    class Parent:
        def reset(self,cap):self.world.data.time=1.3000000000000178
        @property
        def now(self):return float(self.world.data.time)
    class Clock(IntegerClock,Parent):pass
    b=backend_class(old_backend(Clock))()
    robot=NS(servo_command_pulses={1:2000},set_motor_commands=lambda x:None)
    b.world=NS(data=NS(time=0.),robot=lambda rid:robot);b.dt=.00025;b.ports={'r3':None}
    b.bundle=dict(options=dict(min_wheel_cmd='real_v1',stagnation_watch='window120_v1',alignment_pulse='real_fine_v1'))
    assert b.reset(5.)==1.3
    assert isinstance(b.ports['r3'],FinePulsePort)
    assert b.ports['r3'].apply(alignment_primitive(request(),'real_fine_v1'),b.now)['busy_until']==pytest.approx(1.36)


def test_v115_default_off_and_fresh_preregistered_probe():
    from harness import zone_s2_realism_contract_v115 as c
    from scripts.run_s2_realism_v115 import parser
    from sim.workflow_manager import catalog
    args=parser().parse_args(['--expected-source-sha','a'*40,'--output','/tmp/no-run','--seed','1040'])
    assert all(getattr(args,key)=='off' for key in c.NEW_OPTIONS)
    b=c.bundle('a'*40,seed=1040,stage_probe='pick',pickup_slot='P1-2',**c.NEW_OPTIONS)
    assert b['options']['alignment_pulse']=='real_fine_v1'
    assert 'sim/s2_align_pulse.py' in b['source_sha256']
    assert 'harness/zone_solo_cyan_align_pulse.py' in b['source_sha256']
    assert any(w['id']==c.BUNDLE_ID and w['version']=='7.8.0' for w in catalog(c.ROOT)[0]['workflows'])
    with pytest.raises(ValueError):c.bundle('a'*40,seed=1039,stage_probe='pick',pickup_slot='P1-2')


def test_v116_replication_preserves_behavior_and_counts_distinct_causes():
    from harness import zone_s2_realism_contract_v116 as c
    from scripts.run_s2_realism_v116 import parser, CameraRuntime
    from sim.workflow_manager import catalog
    plan=json.loads((c.ROOT/c.PLAN).read_text())
    assert plan['prior_same_cause_failures']=={'CYAN_ALIGN_VIEW_LOST':1,'CYAN_HOVER_UNCONFIRMED':1}
    assert plan['runs'][0]['seed']==1041
    args=parser().parse_args(['--expected-source-sha','a'*40,'--output','/tmp/no-run','--seed','1041'])
    assert all(getattr(args,key)=='off' for key in c.NEW_OPTIONS)
    assert CameraRuntime is Runtime
    b=c.bundle('a'*40,seed=1041,stage_probe='pick',pickup_slot='P1-2',**c.NEW_OPTIONS)
    assert b['options']['alignment_pulse']=='real_fine_v1'
    assert any(w['id']==c.BUNDLE_ID and w['version']=='7.9.0' for w in catalog(c.ROOT)[0]['workflows'])
    with pytest.raises(ValueError):c.bundle('a'*40,seed=1040,stage_probe='pick',pickup_slot='P1-2')
