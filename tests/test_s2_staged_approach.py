import copy,json,math
from types import SimpleNamespace as NS
import numpy as np
import pytest
from harness import zone_solo_cyan_staged_approach as stage
from harness import zone_solo_cyan_look_before_move as look

class Base:
    def __init__(self):
        self.robot_id='r3';self.state='align';self.servo={1:1430,3:740,4:2320,5:1320,6:1500}
        self.cal_until=None;self.cal_settled_at=0.;self.cal_rows=[];self.terminal=False
        self.pulse_profiles={'0:left:-0.35:0.06':dict(axis='left',u=-.35,duration_s=.06,loaded=False,
            times=[0,.06,.18],mean_curve=[[0,0,0],[0,-.01,0],[0,-.01,0]])}
        self.pose=NS(provider=NS(loc=NS(_pf=NS(load=NS(loaded=False)))));self.commands=[];self.path=[]
    def step(self,t):return [('r3',look.action_of(self.pulse_profiles['0:left:-0.35:0.06']))]
    def record(self):return {'state':self.state,'commands':self.commands}
    def on_command(self,r,t,a):self.commands.append(copy.deepcopy(a))
    def on_frames(self,*a):pass
    def drive(self,*a,**k):return [],False
    def soft(self,*a):pass

def runtime():
    r=look.attach(Base(),look_before_move=look.OPTION,final_approach=stage.OPTION,floor_table={})
    r.final_approach_monitor.last_t=1.;r.final_approach_monitor.last={'points':0,'image_sha256':'a'*64}
    return r

def test_final_unknown_passes_exact_base_commands_without_a_free_claim():
    r=runtime();assert not r.look_memory.assess(1,next(iter(r.pulse_profiles.values())))['clear']
    a=r.step(1);assert a==Base().step(1);r.on_command('r3',1,a[0][1])
    assert r.final_approach_monitor.audit['checks'][-1]['free_space_claim'] is False
    assert not r.look_before_move_audit['scans']

def test_navigation_still_vetoes_unknown_and_cannot_escape_boundary():
    r=runtime();r.state='search_move';a=r.step(1)
    assert not any(look.lateral(x) for _,x in a)
    with pytest.raises(RuntimeError):r.on_command('r3',1,Base().step(1)[0][1])
    assert 'carry' not in stage.FINAL_STATES

def test_observed_peer_stops_new_and_active_pulse_without_opening_grip():
    r=runtime();r.final_approach_monitor.last['points']=stage.PARAMS['min_points']
    assert r.step(1)==[('r3',{'kind':'hold'})]
    r.cal_until=2.;assert r.step(1.1)==[('r3',{'kind':'hold'})]
    assert r.cal_until is None and r.servo[1]==1430
    with pytest.raises(RuntimeError):r.on_command('r3',1,Base().step(1)[0][1])

def test_fresh_empty_and_missing_source_are_distinct_and_boundary_fixed():
    m=stage.Monitor();assert m.assess(0)['reason']=='RGB_SOURCE_TIMEOUT'
    m.last_t=1.;m.last={'points':0,'image_sha256':'b'*64}
    assert not m.assess(3)['stop'];assert m.assess(3.00001)['stop']
    m.last['points']=3;assert not m.assess(1)['stop']
    m.last['points']=4;assert m.assess(1)['stop']

def test_self_mask_and_existing_orange_threshold(monkeypatch):
    from harness import vision_loc_protocol as vp
    monkeypatch.setattr(vp,'load_vis3',lambda:(NS(mp=NS(undistort=lambda x:x)),None))
    rgb=np.full((480,640,3),100,np.uint8);rgb[200:220,300:320]=[230,130,20]
    cm=NS(origin=np.zeros(3),_rot=np.eye(3));servo={1:1430};key=(tuple(servo.items()),cm.origin.tobytes(),cm._rot.tobytes())
    assert stage.observed_peer_pixels(rgb,cm,servo,{key:np.full((480,640),np.inf)})['points']>=4
    assert stage.observed_peer_pixels(rgb,cm,servo,{key:np.zeros((480,640))})['points']==0

def test_default_off_identity_and_explicit_off_equal_previous_adapter():
    r=Base();before=(r.step,r.on_command,r.on_frames,r.record);b=json.dumps(r.record())
    assert look.attach(r) is r and before==(r.step,r.on_command,r.on_frames,r.record) and json.dumps(r.record())==b
    a=look.attach(Base(),look_before_move=look.OPTION,floor_table={})
    b=look.attach(Base(),look_before_move=look.OPTION,final_approach='off',floor_table={})
    for t in np.arange(0,8,.1):assert a.step(float(t))==b.step(float(t))
    assert json.dumps(a.record(),sort_keys=True)==json.dumps(b.record(),sort_keys=True)

def test_contract_runtime_and_conditional_regression():
    from harness import zone_s2_staged_approach_contract as c
    from harness import zone_solo_cyan_contract_v106 as legacy
    from scripts.run_s2_staged_approach import runtime_factory
    b=c.bundle('a'*40,1054,look_before_move=look.OPTION,final_approach=stage.OPTION);c.require_execution(b)
    older=c.old.bundle('a'*40,1054,look_before_move=look.OPTION)
    assert {k:v for k,v in b['options'].items() if k!='final_approach'}==older['options']
    with pytest.raises(ValueError):c.require_execution(c.bundle('a'*40,1054,look_before_move=look.OPTION))
    with pytest.raises(ValueError):c.require_execution(c.bundle('a'*40,1053,look_before_move=look.OPTION,final_approach=stage.OPTION))
    r=runtime_factory(b)(legacy.hp.resolve(legacy.MAP_ID)[0],legacy.ROOT/legacy.CALIBRATION,legacy.CALIBRATION_SHA,**b['task'])
    try:assert r.final_approach_monitor.audit['option']==stage.OPTION
    finally:r.close()
