import copy
import json
from types import SimpleNamespace as NS
import numpy as np
import pytest
from tests.s2_ci_inputs import portable_s2_inputs

pytestmark = pytest.mark.usefixtures("portable_s2_inputs")
from harness import zone_solo_cyan_look_before_move as m

def profile():
    return dict(axis='left',u=.65,duration_s=.65,loaded=False,times=[0,.65,.85],
        mean_curve=[[0,0,0],[0,.16,0],[0,.17,0]],mean_delta=[0,.17,0])

class Base:
    def __init__(self):
        self.robot_id='r3';self.servo={1:2000,3:740,4:2320,5:1320,6:1500}
        self.state='align';self.cal_until=2.;self.cal_settled_at=2.;self.cal_rows=[]
        self.pose=NS(provider=NS(loc=NS(_pf=NS(load=NS(loaded=False)))))
        self.pulse_profiles={'0:left:0.65:0.65':profile()};self.terminal=False
    def step(self,t):return [('r3',m.action_of(profile()))]
    def record(self):return {'original':True}
    def on_command(self,*a):pass
    def on_frames(self,*a):pass
    def soft(self,*a):pass
    def drive(self,*a,**kw):return [],False

def test_off_is_identical_object_and_bound_methods_bytes():
    r=Base();before=(r.step,r.record,r.on_command,r.on_frames)
    actions=json.dumps([r.step(t) for t in range(20)]).encode();record=json.dumps(r.record()).encode()
    assert m.attach(r) is r
    assert before==(r.step,r.record,r.on_command,r.on_frames)
    assert actions==json.dumps([r.step(t) for t in range(20)]).encode()
    assert record==json.dumps(r.record()).encode()

def test_unknown_veto_scan_restore_hold_and_no_gripper_open():
    base=Base();base.servo[1]=1430
    r=m.attach(base,look_before_move=m.OPTION,floor_table={})
    emitted=[]
    for t in np.arange(0,8,.05):
        emitted+=r.step(float(t))
    assert all(not m.lateral(a) for _,a in emitted)
    assert all(a.get('pulse')==1430 for _,a in emitted if a.get('servo_id')==1)
    assert len(r.look_before_move_audit['scans'])==1
    assert r.look_before_move_audit['denied']>0
    with pytest.raises(RuntimeError):r.on_command('r3',10,m.action_of(profile()))
    assert r.look_before_move_audit['unconfirmed_lateral_issued']==1

def test_verified_corridor_passes_original_proposal(monkeypatch):
    r=m.attach(Base(),look_before_move=m.OPTION,floor_table={})
    monkeypatch.setattr(r.look_memory,'assess',lambda *a:dict(clear=True))
    a=r.step(1)
    assert a==Base().step(1)
    r.on_command('r3',1,a[0][1])
    assert r.look_before_move_audit['unconfirmed_lateral_issued']==0

def test_sweep_includes_mid_curve_and_padding_but_not_current_robot():
    p=profile();p['mean_curve']=[[0,0,0],[0,.30,0],[0,.17,0]]
    points=m.swept_points(p)
    assert points[:,1].max()>.49
    assert not (((points[:,0]>=-.18)&(points[:,0]<=.28)&(points[:,1]>=-.18)&(points[:,1]<=.18)).any())
    memory=m.Memory({});assert memory.assess(0,p)['unknown']==len(points)
    memory.views.append({'t':0});memory.expire(3.01);assert not memory.views

def test_non_detection_never_implies_free_and_lowest_obstacle_occludes(monkeypatch):
    from harness import vision_loc_protocol as vp
    monkeypatch.setattr(vp,'load_vis3',lambda:(NS(mp=NS(undistort=lambda x:x)),None))
    rgb=np.full((480,640,3),100,np.uint8)
    monkeypatch.setattr(m,'floor_pixels',lambda image,table:np.zeros((480,640),bool))
    assert not m.classify(rgb,{})[0].any()
    monkeypatch.setattr(m,'floor_pixels',lambda image,table:np.ones((480,640),bool))
    rgb[300:330,100:140]=[230,130,20]
    free,blocked,valid=m.classify(rgb,{})
    assert blocked[315,120] and not free[:330,120].any() and free[400,120]

def test_v135_admission_and_real_runtime_fixed_loaded_camera():
    from harness import zone_s2_look_before_move_contract as c
    from harness import zone_solo_cyan_contract_v106 as old
    from scripts.run_s2_look_before_move import runtime_factory
    b=c.bundle('a'*40,1054,look_before_move=m.OPTION);c.require_execution(b)
    with pytest.raises(ValueError):c.require_execution(c.bundle('a'*40,1054))
    with pytest.raises(ValueError):c.bundle('a'*40,1051)
    wrong=copy.deepcopy(b);wrong['scenario']='S3'
    with pytest.raises(ValueError):c.require_execution(wrong)
    r=runtime_factory(b)(old.hp.resolve(old.MAP_ID)[0],old.ROOT/old.CALIBRATION,old.CALIBRATION_SHA,**b['task'])
    try:
        assert r.bias_tempering_audit['alpha']==.5
        pf=r.pose.provider.loc._pf
        for loaded in (False,True):
            pf.load.loaded=loaded
            for pan in (700,1500,2300):
                cm=pf.column_model_for({**m.LOOK_P20,6:pan})
                assert np.isfinite(cm.origin).all()
    finally:r.close()
