import copy,json
from types import SimpleNamespace as NS
from pathlib import Path
import numpy as np
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision
from harness.zone_solo_cyan_load_height import Runtime,Previous,omni_noise,wall_height_support,validate_motion,K


def test_off_commands_record_bytes(static,cal):
    rs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),vision_factory=FakeVision,**kw)
        for cls,kw in [(Previous,{}),(Runtime,{}),(Runtime,dict(load_motion='off',contact_geometry='off'))]]
    try:
        emitted=[]
        for r in rs:
            emitted.append(r.initial_commands(0.,{'r3':{1:2000,3:600,4:2200,5:1400,6:1500}}))
            r.fail('CYAN_NOT_UNIQUELY_VISIBLE',1.)
        assert len(set(json.dumps(x).encode() for x in emitted))==1
        assert len(set(json.dumps(r.record()).encode() for r in rs))==1
    finally:
        for r in rs:r.close()


def test_nav2_omni_covariance_and_fraction():
    # Independent longitudinal, orthogonal, yaw normals, including lateral motion.
    for d in [[2.,0.,.3],[0.,-2.,.3],[0.,0.,.3]]:
        p={'mean_delta':d};a=[.1,.2,.3,.4,.5];n=omni_noise(p,a,np.eye(3),1.)
        trans=d[0]**2+d[1]**2;rot=d[2]**2
        expected=[a[2]*trans+a[3]*rot,a[4]*trans+a[3]*rot,a[0]*rot+a[1]*trans]
        assert np.allclose(np.sum(n*n,axis=1),expected)
        assert np.allclose(omni_noise(p,a,np.eye(3),.25),n*.5)
    z=omni_noise({'mean_delta':[0,0,0]},[0]*5,np.eye(3),1.)
    assert np.allclose(np.sum(z*z,axis=1),[.0005**2,.0005**2,.001**2])


def test_independent_top_edge_and_unknown():
    # Horizontal optical frame. Floor contact x=1.2, y=0, camera z=.2;
    # true top z=.4 maps above the horizon, a floor paint edge does not.
    rot=np.array([[0,0,1],[-1,0,0],[0,-1,0]],float)
    cm=NS(origin=np.array([0,0,.2]),_rot=rot,t_of_row=lambda rows:rows,
        floor_point=lambda rows:np.tile([1.2,0],(len(rows),1)))
    ob=NS(columns=np.array([320]),b_kind=np.array([1]),b_lo=np.array([400.]),t_lo=np.array([0.]))
    blank=np.zeros((480,640),np.uint8)
    keep,top,visible=wall_height_support(cm,ob,blank)
    assert visible.all() and not keep.any()
    u,v=np.rint(top[0]).astype(int);blank[v,u]=255
    assert wall_height_support(cm,ob,blank)[0].all()
    ob.t_lo[:]=v+100 # detector's predicted top is never treated as evidence
    assert wall_height_support(cm,ob,blank)[0].all()
    assert not wall_height_support(cm,ob,None)[0].any()
    cm.floor_point=lambda rows:np.tile([.05,0],(len(rows),1))
    assert not wall_height_support(cm,ob,blank)[0].any()


def test_calibration_validation_and_no_filter_stacking(static,cal):
    table=json.loads(Path('configs/s2_motion_load_conditioned_v1.json').read_text());validate_motion(table)
    for changes in [dict(fit_seed=1051),dict(runtime_gt=True),dict(noise_alpha_1_to_5={'0':[-1]*5,'1':[0]*5})]:
        with pytest.raises(ValueError):validate_motion({**table,**changes})
    for kw in [dict(load_motion='bad'),dict(contact_geometry='wall_height_v1',contact_filter='floor_appearance_v1'),
               dict(load_motion='load_conditioned_v1',load_motion_calibration=table)]:
        with pytest.raises(ValueError):Runtime(static,None,None,**kw)
