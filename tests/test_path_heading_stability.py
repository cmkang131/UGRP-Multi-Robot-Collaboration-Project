import copy,json,math
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from harness.path_heading_stability import ALL,OPTION,Options,Selector,SettleGate,install
from harness.goal_route_heading import Host
from harness.self_pulse_rotation import selected_model
from harness.zone_solo_cyan_path_heading import select_waypoint,command_reason
from scripts import run_own_route_heading_stability as runner


def profiles():return selected_model('s2_pulse_v122_rotL_v1')['profiles']

def test_off_has_identity_state_and_byte_equivalent_host_outputs():
    a=Host('r3','s2_pulse_v122_rotL_v1');b=copy.deepcopy(a)
    before=dict(b.__dict__);fn=b.command.__func__
    assert install(b,heading_stability='off') is b and b.command.__func__ is fn and b.__dict__==before
    kw=dict(path=[[.2,0]],goal=[2,0],costmap=SimpleNamespace(pose_clear=lambda p:True),core=SimpleNamespace(collision_time=lambda *x:-1),points=[],map_pose=[0,0,0],dev_light=True)
    for i,yaw in enumerate([.3,.15,.04,.08,-.08,.03]):
        x=a.command(t=i*.2,pose=[0,0,yaw],**kw);y=b.command(t=i*.2,pose=[0,0,yaw],**kw)
        assert json.dumps(x)==json.dumps(y)
    assert json.dumps(a.rows)==json.dumps(b.rows)


def test_hysteresis_uses_original_deadband_and_separate_reentry():
    s=Selector(Options(deadband_hysteresis=True));p=profiles()
    for i,(error,turn) in enumerate([(.04,False),(.075,False),(.10,True),(.075,True),(.05,False)]):
        s.now=i
        pulse,_=s(p,False,(0,0,0),(math.cos(error),math.sin(error)),(2,0))
        assert (pulse['axis']=='turn') is turn
    assert s.info['latched']


def test_circular_lowpass_does_not_cross_zero_at_pi():
    s=Selector(Options(target_lowpass=True));p=profiles()
    s.now=0;s(p,False,(0,0,0),(-1,.01),(-2,0))
    s.now=.2;s(p,False,(0,0,0),(-1,-.01),(-2,0))
    assert abs(s.filtered)>3.1 and s.info['filter_alpha']==pytest.approx(.2/.7)
    assert math.dist([0,0],s.info['virtual_waypoint'])==pytest.approx(math.hypot(1,.01))


def test_s3_settle_gate_requires_time_and_fresh_observation():
    gate=SettleGate();p={'times':[0,.2]}
    assert gate.ready(0,None)
    gate.issued(1,p,{'frame_id':3})
    assert not gate.ready(1.4,{'sim_time':1.4,'frame_id':4})
    assert not gate.ready(1.5,{'sim_time':1.5,'frame_id':3})
    assert not gate.ready(1.5,{'sim_time':1.4,'frame_id':4})
    assert gate.ready(1.5,{'sim_time':1.5,'frame_id':4})


def test_real_host_on_settles_and_uses_shared_legal_pulses():
    h=install(Host('r3','s2_pulse_v122_rotL_v1'),heading_stability=OPTION)
    kw=dict(pose=[0,0,.3],path=[[.2,0]],goal=[2,0],costmap=SimpleNamespace(pose_clear=lambda p:True),core=SimpleNamespace(collision_time=lambda *x:-1),points=[],map_pose=[0,0,0],dev_light=True)
    cmd,info=h.command(t=0,**kw)
    assert cmd['turn']<0 and command_reason(cmd) is None and info['heading_stability']['option']==OPTION
    cmd,info=h.command(t=.2,**kw);assert cmd['kind']=='hold' and info['reason']=='heading_stability_settle'
    cmd,info=h.command(t=.6,**kw);assert cmd['turn']<0 and len(h.rows)==2
    assert h.heading_stability['runtime_gt'] is False


def test_no_options_selector_is_exact_old_selector():
    s=Selector();p=profiles()
    for yaw in [-3.14,-.2,0,.2,3.14]:
        assert s(p,False,(0,0,yaw),(.3,.02),(2,0))==select_waypoint(p,False,(0,0,yaw),(.3,.02),(2,0))


def test_frozen_24_conditions_and_alarm_are_common(tmp_path):
    jobs=runner.plan(tmp_path)
    assert len(jobs)==len({j['output'] for j in jobs})==24
    assert {j['heading_stability'] for j in jobs}=={'off',OPTION}
    assert runner.alarm_seconds()==7873
    assert runner.alarm_seconds(8)==413
    for j in jobs:
        b=runner.bundle(j['seed'],'a'*40,j['profile'],'stage',heading_stability=j['heading_stability'])
        old=runner.previous.bundle(j['seed'],'a'*40,j['profile'],'stage')
        assert {k:v for k,v in b['options'].items() if k!='heading_stability'}==old['options']
        assert b['host_alarm_s']==7873 and b['case_cap_s']==540


def test_runtime_admission_and_real_wrapper_install_no_physics(tmp_path,monkeypatch):
    # Execute new binding into the actual old runner entry without any backend.
    host=Host('r3','s2_pulse_v122_rotL_v1');c=SimpleNamespace(heading_host=host)
    fake=lambda *a:('backend',c,0.,10,{'fixture':True})
    monkeypatch.setattr(runner.old,'checkpoint_load',fake)
    def old_run(a):
        b=bundle(a.seed,'a'*40,a.profile,a.mode)
        _,c,*_=checkpoint_load(None,None)
        assert c.heading_host.heading_stability['option']==OPTION
        assert b['host_alarm_s']==7873
        signal.alarm(3600);signal.alarm(0)
        return {'status':'RECORDED'}
    alarm=Mock();monkeypatch.setattr(runner.signal,'alarm',alarm);monkeypatch.setattr(runner.old,'run',old_run)
    a=SimpleNamespace(seed=63001,profile='a',mode='stage',heading_stability=OPTION)
    assert runner.run(a)['status']=='RECORDED'
    assert [x.args for x in alarm.call_args_list]==[(7873,),(0,)]


def test_no_mac_batch(monkeypatch,tmp_path):
    monkeypatch.setattr(runner.platform,'system',lambda:'Darwin')
    with pytest.raises(RuntimeError,match='ORACLE_ONLY'):runner.batch(SimpleNamespace(output=tmp_path))
