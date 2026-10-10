import copy,json
from types import SimpleNamespace as NS
import numpy as np
import pytest
from harness import zone_solo_cyan_approach_vo as m
from harness import zone_solo_cyan_ground_vo as ground_vo


def fixture():
    p=dict(axis='left',loaded=False,u=.65,duration_s=.65,times=[0,.75],
        mean_curve=[[0,0,0],[0,.167,-.01]],mean_delta=[0,.167,-.01],prediction_variance=[1e-5]*3)
    profiles={'0:left:0.65:0.65':p};seen=[];applied=[]
    def command(row):seen.append(('command',row['t']));applied.append(copy.deepcopy(profiles))
    pf=NS(load=NS(loaded=False),settled=lambda t:True,column_model_for=lambda pose:None)
    inner=NS(servo=dict(m.SEARCH),loc=NS(_pf=pf),on_command=command,
        on_frame=lambda t,im:seen.append(('frame',t)),report=lambda t:t,
        calibration={'camera_models':{'unloaded':{'740,2320,1320,1500':{}},'loaded':{}}})
    b=m.ApproachBuffer(inner,profiles,lambda p:True,{})
    b.calibration={'pitch_scale_bound_deg':.3};b.last=(1.,np.array([0.]))
    cmd=dict(kind='mecanum',t=1.,left=.65,forward=0,turn=0,duration_s=.65)
    return b,inner,cmd,seen,applied


def test_off_no_access_and_bytes_identical():
    r=NS(record=lambda:dict(existing=['unchanged'],number=.1));before=vars(r).copy();serialized=json.dumps(r.record()).encode()
    assert m.attach(r) is r and vars(r)==before and json.dumps(r.record()).encode()==serialized
    with pytest.raises(ValueError):m.attach(r,ground_motion='invalid')
    with pytest.raises(ValueError):m.attach(r,ground_motion=m.OPTION)


def test_scope_excludes_loaded_fine_turn_unsettled_and_other_pose():
    b,i,c,_,_=fixture();p=b.profiles['0:left:0.65:0.65']
    assert m.eligible(i,p,1.)
    for change in ({'loaded':True},{'axis':'turn'},{'mean_delta':[0,.01,0]}):
        assert not m.eligible(i,{**p,**change},1.)
    i.loc._pf.load.loaded=True;assert not m.eligible(i,p,1.);i.loc._pf.load.loaded=False
    i.servo[3]+=1;assert not m.eligible(i,p,1.);i.servo=dict(m.SEARCH)
    i.loc._pf.settled=lambda t:False;assert not m.eligible(i,p,1.)


def test_full_se2_replaces_once_with_order_no_dropped_observations(monkeypatch):
    b,i,c,seen,applied=fixture();original=copy.deepcopy(b.profiles)
    repl=copy.deepcopy(original['0:left:0.65:0.65']);repl['mean_delta']=[.003,.112,.33]
    monkeypatch.setattr(ground_vo,'observed_pulse',lambda *a:(repl,dict(prediction_replaced=True)))
    i.on_command(c);i.on_frame(1.05,np.array([1.]));assert not seen and i.report(1.5)==1.
    i.on_command(dict(kind='hold',t=1.65));i.on_frame(1.75,np.array([2.]))
    assert seen==[('command',1.),('frame',1.05),('command',1.65),('frame',1.75)]
    assert applied[0]['0:left:0.65:0.65']['mean_delta']==[.003,.112,.33]
    assert b.profiles==original and b.pending is None and b.audit['wall_frames_dropped']==0
    assert b.audit['rows'][0]['unloaded_coarse_vo']


def test_interrupted_or_incomplete_never_fabricates_zero_displacement(monkeypatch):
    b,i,c,seen,applied=fixture();original=copy.deepcopy(b.profiles)
    monkeypatch.setattr(ground_vo,'observed_pulse',lambda item,*a:(item['profile'],dict(prediction_replaced=False)))
    i.on_command(c);i.on_frame(1.75,np.array([1.]));assert applied[0]==original
    c['t']=2.;b.last=(2.,np.array([2.]));i.on_command(c)
    i.on_command(dict(kind='arm',t=2.1,servo_id=3,pulse=800))
    assert b.pending is None and b.profiles==original
    assert b.audit['rows'][-1]['status']=='interrupted' and not b.audit['rows'][-1]['prediction_replaced']


def test_loaded_slip_path_dispatch_is_unchanged(monkeypatch):
    b,i,_,_,_=fixture();b.pending={'profile':{'loaded':True}}
    seen=[];monkeypatch.setattr(m.SlipBuffer,'flush',lambda self,done:seen.append((self.pending,done)))
    b.flush(True);assert seen==[({'profile':{'loaded':True}},True)]


def test_buffered_landmarks_capture_each_original_frame_time(monkeypatch):
    b,i,c,seen,applied=fixture();captures=[];original=b.frame0
    def capture(t,rgb):captures.append((t,rgb[0]));return original(t,rgb)
    b.landmark_replay=capture
    monkeypatch.setattr(ground_vo,'observed_pulse',lambda item,*a:(item['profile'],dict(prediction_replaced=False)))
    i.on_command(c);i.on_frame(1.05,np.array([1.]));i.on_frame(1.75,np.array([2.]))
    assert captures==[(1.05,1.),(1.75,2.)] and b.frame0 is original
