import copy,json
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision
from harness import zone_solo_cyan_slip_detect as m
from harness.zone_solo_cyan_pulse_cal import install


def item():
    p=dict(axis='left',loaded=True,u=.65,duration_s=.65,times=[0,.75],mean_curve=[[0,0,0],[0,.167,0]],mean_delta=[0,.167,0],prediction_variance=[1e-5]*3)
    return dict(t=1.,key='1:left:0.65:0.65',profile=p,cm=None,pose={},before=(1.,np.array([1.])),command=dict(left=.65))


def test_default_off_wire_and_record_bytes(static,cal):
    rs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),vision_factory=FakeVision,**kw)
        for cls,kw in [(m.flow.Runtime,{}),(m.Runtime,{}),(m.Runtime,dict(slip_detection='off'))]]
    try:
        rows=[r.initial_commands(0.,{'r3':{1:2000,3:600,4:2200,5:1400,6:1500}}) for r in rs]
        assert len(set(json.dumps(x).encode() for x in rows))==1
        assert len(set(json.dumps(r.record()).encode() for r in rs))==1
    finally:
        for r in rs:r.close()


def test_slip_replaces_only_low_progress_and_scale_is_radial(monkeypatch):
    p=item();frames=[(1.+i*.05,np.array([1.])) for i in range(1,16)]
    d=np.array([.0001,.0003,0.])
    monkeypatch.setattr(m,'pair',lambda *a,**k:dict(status='measured',delta=d.tolist(),covariance=(np.eye(3)*1e-8).tolist()))
    def scale(obs,cm,angle):
        v=np.array(obs['delta']);v[:2]*=1+3*angle;return v
    monkeypatch.setattr(m,'scale_delta',scale)
    out,row=m.observed_pulse(p,frames,{})
    assert row['status']=='slip_replaced' and row['coverage']==1 and row['progress_ratio']<.5
    assert np.allclose(out['mean_delta'],d*15)
    pc=np.array(row['pitch_radial_covariance']);direction=(d*15)[:2];perp=np.array([-direction[1],direction[0],0.])
    assert np.linalg.norm(pc@perp)<1e-16 and np.array_equal(pc[2],[0,0,0])
    assert np.linalg.eigvalsh(out['prediction_covariance']).min()>=0
    json.dumps(row)
    d[:]=[0,.012,0] # ordinary travel keeps original profile exactly
    out,row=m.observed_pulse(p,frames,{})
    assert row['status']=='normal_preserved' and json.dumps(out).encode()==json.dumps(p['profile']).encode()


def test_unknown_is_not_zero_or_command_filled_vo_and_bridges_are_bounded(monkeypatch):
    p=item();frames=[(1.+i*.05,np.array([i])) for i in range(1,16)]
    def pair(a,b,*args,**kw):
        if b[0] in (2,):return dict(status='unknown_texture')
        return dict(status='measured',delta=[0,(b[0]-max(0,a[0]))*.001,0],covariance=(np.eye(3)*1e-8).tolist())
    p['before']=(1.,np.array([0]));monkeypatch.setattr(m,'pair',pair)
    monkeypatch.setattr(m,'scale_delta',lambda o,c,a:np.array(o['delta']))
    out,row=m.observed_pulse(p,frames,{})
    assert row['complete_visual'] and out['mean_delta'][1]==pytest.approx(.015)
    assert any(abs(i['t']-i['from_t']-.1)<1e-7 for i in row['intervals'] if i['status']=='measured')
    monkeypatch.setattr(m,'pair',lambda *a,**k:dict(status='unknown_texture'))
    out,row=m.observed_pulse(p,frames,{})
    assert out==p['profile'] and row['coverage']==0 and row['visual_delta'] is None


def test_full_covariance_predictor_preserves_radial_scale_direction():
    p=item()['profile'];p=copy.deepcopy(p);p.update(mean_delta=[.01,.02,0.],mean_curve=[[0,0,0],[.01,.02,0.]])
    radial=np.array([.01,.02,0.]);p['prediction_covariance']=(np.outer(radial,radial)*.04).tolist()
    pf=NS(t=0.,load=NS(loaded=True),command=lambda row:None,vel=np.zeros(3),n=2000,initialized=True,
        px=np.zeros((2000,3)),logw=np.zeros(2000),rng=np.random.default_rng(11),_map_logprior=lambda x:np.zeros(len(x)))
    install(pf,dict(option='v7_pulse_cal_v1',profiles={'1:left:0.65:0.65':p}))
    pf.command(dict(t=0.,kind='mecanum',left=.65,duration_s=.65));pf.predict_to(.75)
    assert abs(pf.px[:,0].std()-.002)<.0002
    assert np.max(abs(pf.px[:,1]-2*pf.px[:,0]))<1e-9 and np.array_equal(pf.px[:,2],np.zeros(2000))


def test_registration_and_incompatible_options(static):
    c=json.loads(Path('experiments/2026-10-06-s2-realism/slip-detect-criteria.json').read_text())
    assert c['parameters']==m.PARAMS
    for kw in [dict(slip_detection='bad'),dict(slip_detection=m.OPTION),dict(slip_detection=m.OPTION,visual_odometry=m.flow.VO)]:
        with pytest.raises(ValueError):m.Runtime(static,None,None,**kw)
