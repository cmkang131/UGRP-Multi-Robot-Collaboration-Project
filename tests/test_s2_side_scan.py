import copy
import json
from types import SimpleNamespace as NS
import numpy as np
import pytest
from harness import zone_solo_cyan_side_scan as m
from harness import zone_s2_side_scan_contract as c


class Base:
    def __init__(self):
        self.robot_id='r3';self.servo={1:2000,3:740,4:2320,5:1320,6:1500}
        self.state='search_move';self.cal_until=9.;self.cal_settled_at=9.
    def step(self,t):return [('r3',dict(kind='mecanum',left=.65,forward=0,turn=0,duration_s=.65))]
    def record(self):return {'unchanged':'base'}
    def on_frames(self,*a):pass


def test_off_exact_actions_and_record():
    r=m.runtime_class(Base)();b=Base()
    assert json.dumps(r.step(1)).encode()==json.dumps(b.step(1)).encode()
    assert json.dumps(r.record()).encode()==json.dumps(b.record()).encode()
    assert not hasattr(r,'side_scan_audit')


def test_diagnostic_withholds_lateral_and_finishes_without_transport():
    r=m.runtime_class(Base)(side_scan=m.OPTION)
    actions=[]
    for t in np.arange(1,13,.05):actions+=r.step(float(t))
    assert r.side_scan_done and r.side_scan_audit['trigger']['withheld'][0][1]['left']==.65
    assert all(a['kind'] in ('hold','arm','look') for _,a in actions)
    assert [a['pan_pulse'] for _,a in actions if a['kind']=='look']==[1500,2300,700,1500]
    assert r.cal_until is None


def test_observation_only_after_settle(monkeypatch):
    r=m.runtime_class(Base)(side_scan=m.OPTION);r.step(1)
    monkeypatch.setattr(m,'orange_candidates',lambda rgb:dict(detected=False))
    f={'r3':({'frame_id':1,'sha256':'image'},np.zeros((480,640,3),np.uint8))}
    r.on_frames(2.95,f);assert not r.side_scan_audit['frames']
    r.on_frames(3.,f);assert len(r.side_scan_audit['frames'])==1


def test_colour_candidate_is_not_free_space_or_identity(monkeypatch):
    from harness import vision_loc_protocol as vp
    monkeypatch.setattr(vp,'load_vis3',lambda:(NS(mp=NS(undistort=lambda x:x)),None))
    rgb=np.full((480,640,3),100,np.uint8)
    assert not m.orange_candidates(rgb)['detected']
    rgb[200:230,100:140]=[230,130,20]
    result=m.orange_candidates(rgb)
    assert result['detected'] and result['components'] and 'no identity' in result['semantics']


def test_bundle_optin_and_non_s2_rejected():
    b=c.bundle('a'*40,side_scan=m.OPTION);c.require_execution(b)
    assert b['task']['seed']==1054 and b['case_cap_s']==45
    assert b['dev_preregistration']['runs']==1 and not b['research_result']
    with pytest.raises(ValueError):c.require_execution(c.bundle('a'*40))
    for key,value in [('scenario','S3'),('research_result',True),('case_cap_s',900)]:
        wrong=copy.deepcopy(b);wrong[key]=value
        with pytest.raises(ValueError):c.require_execution(wrong)


def test_real_runtime_factory_side_postures_have_fixed_calibration():
    from scripts.run_s2_side_scan import runtime_factory
    from harness import zone_solo_cyan_contract_v106 as old
    b=c.bundle('a'*40,side_scan=m.OPTION)
    runtime=runtime_factory(b)(old.hp.resolve(old.MAP_ID)[0],old.ROOT/old.CALIBRATION,old.CALIBRATION_SHA,**b['task'])
    try:
        pf=runtime.pose.provider.loc._pf
        for p in (700,1500,2300):
            camera=pf.column_model_for({**m.LOOK_P20,6:p})
            assert np.isfinite(camera.origin).all()
        assert runtime.bias_tempering_audit['forward_scale']=='forward_scale_v1'
    finally:runtime.close()
