import copy,json
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision
from harness import zone_solo_cyan_flow_fusion as m


def test_default_off_command_and_record_bytes(static,cal):
    rs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),vision_factory=FakeVision,**kw)
        for cls,kw in [(m.Previous,{}),(m.Runtime,{}),(m.Runtime,dict(visual_odometry='off',stall_recovery='off'))]]
    try:
        issued=[r.initial_commands(0.,{'r3':{1:2000,3:600,4:2200,5:1400,6:1500}}) for r in rs]
        assert len(set(json.dumps(x).encode() for x in issued))==1
        assert len(set(json.dumps(r.record()).encode() for r in rs))==1
    finally:
        for r in rs:r.close()


def test_velocity_measurement_changes_mean_and_joseph_is_psd():
    f=m.VelocityEKF();cov=np.diag([1e-6,1e-6,1e-5])
    d,p,k=f.update([0,0,0],cov,.05)
    assert np.array_equal(d,[0,0,0]) and np.array_equal(k,np.eye(3))
    for _ in range(30):d,p,k=f.update([.001,.002,.003],cov,.05)
    assert np.allclose(d,[.001,.002,.003],atol=1e-5)
    assert np.linalg.eigvalsh(p).min()>0


def test_pitch_covariance_and_rank_geometry():
    # Horizontal ground camera, rolled into conventional image optical axes.
    cm=NS(origin=np.array([0.,0.,.2]),_rot=np.array([[0,0,1],[-1,0,0],[0,-1,0.]]))
    p=np.array([[150,300],[220,300],[290,300],[360,300],[430,300],[500,300]],float)
    obs=dict(delta=[0.,0.,0.],covariance=(np.eye(3)*1e-8).tolist(),before_uv=p.tolist(),after_uv=p.tolist())
    out=m.pitch_uncertainty(obs,cm)
    assert np.linalg.eigvalsh(np.array(out['covariance'])-np.array(obs['covariance'])).min()>-1e-10
    assert np.allclose(out['pitch_jacobian_common'],0,atol=1e-8)
    assert np.trace(out['covariance'])>np.trace(obs['covariance'])
    # Collinearity does not make SE2 rotation+translation unobservable.
    a=m.ground(cm,p)[0];j=np.zeros((len(a)*2,3));j[::2,0]=1;j[1::2,1]=1;j[::2,2]=-a[:,1];j[1::2,2]=a[:,0]
    assert np.linalg.matrix_rank(j)==3


def test_pulse_buffer_clock_and_no_double_count_or_wall_drop(monkeypatch):
    profile=dict(axis='left',times=[0.,.75],mean_curve=[[0,0,0],[0,.167,0]],mean_delta=[0,.167,0],
        prediction_variance=[1e-5]*3,duration_s=.65)
    key='1:left:0.65:0.65';live={key:profile};events=[];used=[]
    pf=NS(load=NS(loaded=True),column_model_for=lambda p:None)
    def command(row):events.append(('c',row['t']));used.append(copy.deepcopy(live[key]))
    inner=NS(loc=NS(_pf=pf),servo={1:1500},on_command=command,
        on_frame=lambda t,rgb:events.append(('f',t)),report=lambda t:t)
    b=m.PulseBuffer(inner,live,lambda p:True,{})
    rgb=np.zeros((480,640,3),np.uint8)
    monkeypatch.setattr(m,'pair',lambda *a,**kw:dict(status='measured',delta=[0,0,0],covariance=(np.eye(3)*1e-7).tolist(),pitch_common_sigma_delta=[0,0,0]))
    monkeypatch.setattr(m,'pitch_uncertainty',lambda x,cm:x)
    inner.on_frame(1.,rgb);inner.on_command(dict(t=1.,kind='mecanum',left=.65,duration_s=.65))
    for i in range(1,15):
        t=1.+i*.05;assert inner.on_frame(t,rgb)==1.
        if i==13:inner.on_command(dict(t=t,kind='hold'))
    assert events==[('f',1.)] and inner.report(1.74)==1.
    assert inner.on_frame(1.75,rgb)==1.75
    assert len([e for e in events if e[0]=='f'])==16
    assert len([e for e in events if e[0]=='c'])==2
    assert np.allclose(used[0]['mean_delta'],0) and live[key] is profile
    assert b.audit['rows'][0]['coverage']==pytest.approx(1.)
    # Unknown frames keep the original displacement exactly; no fake stop.
    monkeypatch.setattr(m,'pair',lambda *a,**kw:dict(status='unknown_texture'))
    inner.on_command(dict(t=1.75,kind='mecanum',left=.65,duration_s=.65))
    for i in range(1,16):inner.on_frame(1.75+i*.05,rgb)
    row=b.audit['rows'][-1];assert row['coverage']==0 and np.allclose(row['delta'],[0,.167,0])


def test_progress_requires_observed_consecutive_failure_and_emits_inverse(monkeypatch):
    r=m.ProgressRecovery();base=dict(t=1.,end=1.75,direction=[0,1],delta=[0,0,0],variance=[1e-8]*3,coverage=1.)
    r.observe({**base,'coverage':0});assert r.blocked is None
    r.observe(base);r.observe({**base,'t':2.,'end':2.75});assert np.array_equal(r.blocked,[0,1])
    assert r.forbidden(dict(left=.65)) and not r.forbidden(dict(left=-.65))
    from harness import map_goto
    monkeypatch.setattr(map_goto,'plan_path',lambda *a,**kw:{'waypoints_m':[]})
    profiles={'x':dict(loaded=True,axis='left',u=-.35,duration_s=.06)}
    action=r.override(dict(kind='mecanum',left=.65),3.,[0,0],0.,profiles,{},None)
    assert action['left']==-.35 and action['duration_s']==.06
    r.observe({**base,'t':3.,'end':3.2,'delta':[0,-.11,0]})
    assert r.finished
    assert r.override(dict(left=.65),3.3,[0,-.11],0.,profiles,{},None)=={'kind':'hold'}
    r=m.ProgressRecovery();r.observe(base);r.observe({**base,'coverage':0});r.observe({**base,'t':2.,'end':2.75})
    assert r.blocked is None


def test_registration_and_validation(static):
    c=json.loads(Path('experiments/2026-10-06-s2-realism/flow-fusion-criteria.json').read_text())
    assert c['parameters']==m.PARAMS
    for kw in [dict(visual_odometry='bad'),dict(stall_recovery=m.RECOVERY),dict(visual_odometry=m.VO)]:
        with pytest.raises(ValueError):m.Runtime(static,None,None,**kw)
