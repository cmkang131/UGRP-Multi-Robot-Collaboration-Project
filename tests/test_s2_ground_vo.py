import copy,json
from types import SimpleNamespace as NS
import numpy as np
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision
from test_s2_slip_detect import item
from harness import zone_solo_cyan_ground_vo as m


def test_default_off_bytes_and_invalid_option(static,cal):
    rs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),vision_factory=FakeVision,**kw)
        for cls,kw in [(m.Previous,{}),(m.Runtime,{}),(m.Runtime,dict(odom_source='off'))]]
    try:
        rows=[r.initial_commands(0.,{'r3':{1:2000,3:600,4:2200,5:1400,6:1500}}) for r in rs]
        assert len(set(json.dumps(x).encode() for x in rows))==1
        assert len(set(json.dumps(r.record()).encode() for r in rs))==1
    finally:
        for r in rs:r.close()
    for kw in (dict(odom_source='bad'),dict(odom_source=m.OPTION),dict(odom_source=m.OPTION,slip_detection=m.slip.OPTION)):
        with pytest.raises(ValueError):m.Runtime(static,None,None,**kw)


def test_homography_matches_metric_ground_projection_and_rotation():
    cm=NS(origin=np.array([.15,0,.22]),_rot=np.array([[0.,0.,1.],[-1.,0.,0.],[0.,-1.,0.]]))
    delta=np.array([.02,-.01,.07]);c,s=np.cos(delta[2]),np.sin(delta[2]);r=np.array([[c,-s],[s,c]])
    after=np.array([[.5,.2],[.7,-.1],[1.2,.15],[.9,-.3]])
    before=after@r.T+delta[:2]
    def uv(points):
        p=(np.c_[points,np.zeros(len(points))]-cm.origin)@cm._rot@m.K.T
        return p/p[:,2,None]
    pred=uv(after)@m.plane_homography(cm,delta).T;pred/=pred[:,2,None]
    assert np.allclose(pred,uv(before),atol=1e-10)


def test_normal_slip_turn_all_use_measured_delta_once_and_radial_scale(monkeypatch):
    p=item();p['before']=(1.,np.array([0.]));frames=[(1.+i*.05,np.array([i])) for i in range(1,16)]
    delta=np.array([0.,.012,0.])
    monkeypatch.setattr(m,'ground_pair',lambda *a,**k:dict(status='measured',delta=delta.tolist(),covariance=(np.eye(3)*1e-8).tolist()))
    def scale(obs,cm,angle):
        d=np.array(obs['delta']);d[:2]*=1+3*angle;return d
    monkeypatch.setattr(m.slip,'scale_delta',scale)
    out,row=m.observed_pulse(p,frames,{},.3)
    assert row['status']=='normal_measured' and row['prediction_replaced']
    assert out['mean_delta'][1]==pytest.approx(.18) # not command .167 + .18
    assert not row['command_double_counted']
    delta[:]=[.0001,.0003,0.]
    out,row=m.observed_pulse(p,frames,{},.3)
    assert row['status']=='slip_replaced' and out['mean_delta'][1]==pytest.approx(.0045)
    q=np.array(row['pitch_radial_covariance']);perp=np.r_[-delta[1],delta[0],0.]
    assert np.linalg.norm(q@perp)<1e-20 and q[2,2]==0
    assert np.linalg.eigvalsh(out['prediction_covariance']).min()>=0
    delta[:]=[0.,0.,.01];p['profile']['mean_delta']=[0,0,.18]
    out,row=m.observed_pulse(p,frames,{},.3)
    assert row['status']=='normal_measured' and out['mean_delta'][2]==pytest.approx(.15)


def test_unknown_identical_and_missing_frames_keep_prediction_exact(monkeypatch):
    p=item();frames=[(1.+i*.05,np.array([i])) for i in range(1,16)]
    for status in ('unknown_texture','unknown_identical_rgb'):
        monkeypatch.setattr(m,'ground_pair',lambda *a,**k:dict(status=status))
        out,row=m.observed_pulse(p,frames,{},2.8)
        assert json.dumps(out).encode()==json.dumps(p['profile']).encode()
        assert row['source']=='command_prediction_fallback' and row['visual_delta'] is None
    out,row=m.observed_pulse(p,[],{},2.8)
    assert out==p['profile'] and not row['complete_visual']


def test_all_load_axis_profiles_buffer_causally_and_restore(monkeypatch):
    p=item();p['profile'].update(axis='turn',loaded=False,mean_delta=[0,0,.1])
    key='0:turn:0.35:0.65';profiles={key:p['profile']};events=[];applied=[]
    def command(row):events.append(('command',row['t']));applied.append(copy.deepcopy(profiles[key]))
    inner=NS(on_command=command,on_frame=lambda t,im:events.append(('frame',t)),report=lambda t:t,
        servo={},loc=NS(_pf=NS(load=NS(loaded=False),column_model_for=lambda x:None)))
    buf=m.GroundBuffer(inner,profiles,lambda pose:True,{},calibration=dict(pitch_scale_bound_deg=.3))
    buf.last=(1.,np.array([0.]));cmd=dict(kind='mecanum',t=1.,forward=0,left=0,turn=.35,duration_s=.65)
    inner.on_command(cmd)
    assert not events and inner.report(1.5)==1.
    replacement=copy.deepcopy(p['profile']);replacement['mean_delta']=[0,0,.07]
    monkeypatch.setattr(m,'observed_pulse',lambda *a:(replacement,dict(prediction_replaced=True)))
    inner.on_frame(1.75,np.array([1.]))
    assert events==[('command',1.),('frame',1.75)] and applied==[replacement]
    assert profiles[key]==p['profile'] and inner.report(1.75)==1.75
    assert buf.pending is None and buf.audit['wall_frames_dropped']==0
