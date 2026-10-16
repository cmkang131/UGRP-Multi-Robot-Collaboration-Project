"""Nonphysical regression of upstream numerical ports and safe initialization."""
import math
import numpy as np
from harness.mapbuild_amcl_vendor import algorithms as n
from harness.mapbuild_amcl import StaticAMCL,StaticField,OPTION

STATIC=dict(bounds_m=[-1,1,-1,1],obstacles=[dict(id='wall_top',center_m=[0,.9],half_extents_m=[1,.02])])
REQ=dict(handoff=dict(position_error_m=.2007512557246549,yaw_error_rad=.3739074138060199,nominal_target_range_m=.8483145702460003))
CAL=dict(truth_inputs=0,alphas=[.1,.2,.3,.4])


def test_motion_matches_scalar_nav2_forward_backward_and_turn():
    for d in ([.3,.1,.15],[-.3,.1,-.4],[.001,.002,.3]):
        p=np.array([[1.,2.,.1],[-1.,.5,-2.]])
        expected=p.copy();draws=np.random.default_rng(42).normal(size=(2,3))
        tr=math.hypot(d[0],d[1]);r1=0 if tr<.01 else math.atan2(d[1],d[0]);r2=float(n.wrap(d[2]-r1))
        a=min(abs(float(n.wrap(r1))),abs(float(n.wrap(r1-math.pi))))
        b=min(abs(float(n.wrap(r2))),abs(float(n.wrap(r2-math.pi))))
        for i in range(2):
            u=float(n.wrap(r1-draws[i,0]*math.sqrt(.1*a*a+.2*tr*tr)))
            v=tr-draws[i,1]*math.sqrt(.3*tr*tr+.4*(a*a+b*b))
            w=float(n.wrap(r2-draws[i,2]*math.sqrt(.1*b*b+.2*tr*tr)))
            expected[i,0]+=v*math.cos(expected[i,2]+u);expected[i,1]+=v*math.sin(expected[i,2]+u)
            expected[i,2]=n.wrap(expected[i,2]+u+w)
        n.motion(p,d,[.1,.2,.3,.4],np.random.default_rng(42))
        np.testing.assert_allclose(p,expected,atol=1e-14)


def test_likelihood_retains_nav2_cubic_and_unknown_is_uninformative():
    f=StaticField(STATIC);p=np.array([[0.,0.,0.],[0.,-.5,0.]])
    v=n.likelihood(f,p,[[0.,.9]],.0202)
    assert v[0]>v[1]
    assert abs(v[0]-(1+(.5+.5/100)**3))<1e-12
    np.testing.assert_array_equal(n.likelihood(f,p,[],.0202),[1,1])


def test_global_free_initialization_and_two_modes_cannot_handoff():
    m=StaticAMCL(STATIC,CAL,REQ,option=OPTION)
    assert len(m.particles)==100000
    assert np.ptp(m.particles[:,0])>1.9 and np.ptp(m.particles[:,2])>6.2
    assert (m.field.distances(m.particles[:,:2])>0).all()
    m.particles=np.array([[0,0,0],[0,0,np.pi]],float);m.weights=np.array([.5,.5])
    assert not m.belief()['ready_for_handoff']
    assert not m.local_map


def test_off_never_adopts_and_causal_map_does_not_feed_field():
    m=StaticAMCL(STATIC,CAL,REQ)
    before=m.field.dist.copy()
    scan=dict(segments=[[[.1,.3],[.2,.3]]])
    r=m.step(0,0,[0,0,0],scan)
    assert r['reason']=='off' and r['adopted_pose'] is None
    assert len(m.local_map)==1
    np.testing.assert_array_equal(before,m.field.dist)


def test_kld_strict_count_single_bin_and_determinism():
    assert n.sample_limit(1,5,100)==100
    p=np.zeros((5,3));w=np.ones(5)/5
    out,stats=n.resample(p,w,np.random.default_rng(2),lambda k:np.zeros((k,3)),0,5,100)
    assert len(out)==100 and stats['occupied_bins']==1
    p=np.array([[0,0,0],[2,2,0]],float);w=np.array([.5,.5])
    args=(p,w)
    a,sa=n.resample(*args,np.random.default_rng(7),lambda k:np.zeros((k,3)),0,5,100)
    b,sb=n.resample(*args,np.random.default_rng(7),lambda k:np.zeros((k,3)),0,5,100)
    np.testing.assert_array_equal(a,b);assert sa==sb


def test_equal_weight_resampling_cannot_fake_good_sensor_ess(monkeypatch):
    m=StaticAMCL(STATIC,CAL,REQ,option=OPTION)
    m.particles=np.array([[0.,0.,0.],[.5,0.,0.],[-.5,0.,0.]])
    m.weights=np.ones(3)/3
    monkeypatch.setattr(n,'likelihood',lambda *args:np.array([1e6,1.,1.]))
    monkeypatch.setattr(n,'resample',lambda *args,**kwargs:(np.zeros((3,3)),dict(samples=3)))
    row=m.step(0,0,[0,0,0],dict(segments=[[[0,.9],[.1,.9]]]))
    assert row['post_resample_ess']==3 and row['pre_resample_ess']<1.01
    assert not row['converged'] and row['adopted_pose'] is None


def test_compact_belief_in_failed_profile_is_never_live_handoff_admission(monkeypatch):
    m=StaticAMCL(STATIC,CAL,REQ,option=OPTION)
    m.particles=np.zeros((4,3));m.weights=np.ones(4)/4
    monkeypatch.setattr(n,'likelihood',lambda *args:np.ones(4))
    monkeypatch.setattr(n,'resample',lambda *args,**kwargs:(np.zeros((4,3)),dict(samples=4)))
    row=m.step(0,0,[0,0,0],dict(segments=[[[0,.9],[.1,.9]]]))
    assert row['converged']
    assert not row['runtime_qualified'] and not row['ready_for_handoff']
    assert row['adopted_pose'] is None and row['proposal_pose']==[0,0,0]


def test_probability_field_uses_upstream_beam_product_and_ceil_stride():
    f=StaticField(STATIC);p=np.array([[0.,0.,0.],[0.,-.5,0.]])
    points=np.tile([0.,.9],(96,1))
    value=n.likelihood_product(f,p,points,.0202)
    np.testing.assert_allclose(value,[.505**48,.005**48],rtol=1e-12,atol=0)
    np.testing.assert_array_equal(n.likelihood_product(f,p,[],.0202),[1,1])


def test_missing_beam_slots_are_not_packed_before_official_stride():
    f=StaticField(STATIC);p=np.array([[0.,0.,0.],[0.,-.5,0.]])
    points=np.full((96,2),np.nan);points[1::2]=[0.,.9]
    # Original ceil(96/60)=2 selects only unknown even columns. They carry
    # no evidence. Packing 48 known odd columns would invent a different scan.
    np.testing.assert_array_equal(n.likelihood_product(f,p,points,.0202),[1,1])
    assert n.likelihood(f,p,points,.0202)[0]>1
