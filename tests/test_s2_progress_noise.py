import copy,json
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision
from harness import zone_solo_cyan_progress_noise as m


def test_default_off_wire_and_record_bytes(static,cal):
    rs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),vision_factory=FakeVision,**kw)
        for cls,kw in [(m.Previous,{}),(m.Runtime,{}),(m.Runtime,dict(visual_progress='off'))]]
    try:
        commands=[]
        for r in rs:
            commands.append(r.initial_commands(0.,{'r3':{1:2000,3:600,4:2200,5:1400,6:1500}}))
            r.fail('CYAN_NOT_UNIQUELY_VISIBLE',1.)
        assert len(set(json.dumps(x).encode() for x in commands))==1
        assert len(set(json.dumps(r.record()).encode() for r in rs))==1
    finally:
        for r in rs:r.close()


def test_rigid_plane_vo_recovers_rotation_slip_and_rejects_outliers():
    rng=np.random.default_rng(24);before=rng.uniform(-.4,.4,(40,2))
    angle=.18;rot=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
    shift=np.array([.003,.012]);after=(before-shift)@rot
    after[-10:]+=rng.uniform(.2,.5,(10,2))
    found,d,inliers=m.rigid_ransac(before,after)
    assert inliers.sum()==30 and np.allclose(found,rot) and np.allclose(d,shift)
    assert m.rigid_ransac(before[:5],after[:5]) is None
    assert m.rigid_ransac(before,rng.uniform(-2,2,(40,2))) is None


def test_nominal_q_scaling_equation_and_unknown_texture():
    q=np.array([.01,.02,.03]);p=np.array([.1,.2,.3]);r=np.eye(3)*.001
    new,alpha=m.scaled_variance(p,q,p+[1,0,0],r)
    assert alpha==pytest.approx((1-.003)/.06)
    assert np.allclose(new,q*np.sqrt(alpha))
    assert np.array_equal(m.scaled_variance(p,q,p,r)[0],q)
    # ±pi is a small angular innovation, not a complete turn.
    assert np.array_equal(m.scaled_variance([0,0,np.pi-.001],q,[0,0,-np.pi+.001],r)[0],q)
    table=json.loads(Path('configs/calibration/s2_floor_appearance_v1.json').read_text())
    out=m.pair(np.zeros((480,640,3),np.uint8),np.zeros((480,640,3),np.uint8),None,{},table)
    assert out['status']=='unknown_texture' and 'delta' not in out


def test_injection_on_capture_clock_after_horizon_keeps_rgb(monkeypatch):
    rng=np.random.default_rng(0);frames=[];predictions=[]
    pf=NS(load=NS(loaded=True),n=6000,px=np.zeros((6000,3)),rng=rng,logw=np.zeros(6000),
        column_model_for=lambda p:None,predict_to=lambda t:predictions.append(t),_map_logprior=lambda p:np.zeros(len(p)))
    inner=NS(loc=NS(_pf=pf),servo={1:1500},on_command=lambda row:None,
        on_frame=lambda t,rgb:frames.append((t,rgb)))
    profile=dict(mean_delta=[0,.17,0],prediction_variance=[1e-5]*3,times=[0,.75])
    audit=m.install(inner,{'1:left:0.65:0.65':profile},lambda pose:True,{})
    rgb=np.ones((480,640,3),np.uint8)
    monkeypatch.setattr(m,'pair',lambda *args:dict(status='measured',delta=[0,0,0],covariance=(np.eye(3)*1e-7).tolist()))
    inner.on_frame(1.,rgb)
    inner.on_command(dict(t=1.,kind='mecanum',left=.65,duration_s=.65))
    inner.on_frame(1.70,rgb);assert not predictions and not audit['rows']
    inner.on_frame(1.75,rgb)
    assert predictions==[1.75] and len(audit['rows'])==1
    assert all(frame is rgb for _,frame in frames)
    assert np.linalg.norm(pf.px[:,:2].mean(0))<.001
    assert np.var(pf.px[:,1])>1e-4
    old=pf.px.copy();inner.on_frame(1.80,rgb);assert np.array_equal(old,pf.px)
    # Missing texture does not inject a zero-motion measurement or noise.
    monkeypatch.setattr(m,'pair',lambda *args:dict(status='unknown_texture'))
    inner.on_command(dict(t=1.80,kind='mecanum',left=.65,duration_s=.65))
    inner.on_frame(2.55,rgb);assert np.array_equal(old,pf.px)


def test_registered_parameters_and_option_validation(static):
    c=json.loads(Path('experiments/2026-10-06-s2-realism/blocked-pulse-criteria.json').read_text())
    assert c['parameters']==m.PARAMS
    for kwargs in [dict(visual_progress='bad'),dict(visual_progress=m.OPTION)]:
        with pytest.raises(ValueError):m.Runtime(static,None,None,**kwargs)
