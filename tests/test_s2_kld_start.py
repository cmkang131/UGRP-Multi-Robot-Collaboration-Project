import copy,json,math
from types import SimpleNamespace as NS
import numpy as np
import pytest
from harness import zone_solo_cyan_kld_start as m
from test_s2_augmented_start import particle_filter
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision


def test_default_off_command_and_record_bytes(static,cal):
    runs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),
        vision_factory=FakeVision,**kw) for cls,kw in
        [(m.previous.Runtime,{}),(m.Runtime,{}),(m.Runtime,dict(particle_sampling='off'))]]
    try:
        for r in runs:r.initial_commands(0.,{'r3':{1:2000,3:740,4:2320,5:1320,6:1500}})
        for t in (1.,1.05,1.65):
            commands=[r.step(t) for r in runs]
            assert len({json.dumps(c).encode() for c in commands})==1
            for r,issued in zip(runs,commands):
                for rid,cmd in issued:r.on_command(rid,t,cmd)
        assert len({json.dumps(r.record()).encode() for r in runs})==1
    finally:
        for r in runs:r.close()


def test_fox_bound_matches_chi_square_approximation_and_caps():
    from scipy.stats import chi2
    assert m.sample_limit(1)==100000
    assert m.sample_limit(2)==2000
    for k in (250,500,1000):
        assert m.sample_limit(k)==pytest.approx(chi2.ppf(.99,k-1)/(.1),rel=.001)
    assert m.sample_limit(20000)==100000


def test_budget_shrinks_with_support_and_preserves_latent_ancestry():
    p=dict(m.PARAMS,min_samples=20,max_samples=400,epsilon=.1)
    ns=[]
    for spread in (False,True):
        pf=particle_filter(100)
        pf.px[:,0]=np.arange(100) if spread else np.arange(100)%2
        pf.scale=np.c_[np.arange(100)]
        # Include yaw seam and negative-coordinate bins as in Nav2 floor().
        pf.px[:,1]=-.1;pf.px[:,2]=math.pi-.01
        original=pf.px.copy();q=m.resample(pf,parameters=p)
        assert np.array_equal(pf.px,original[pf.scale[:,0]])
        assert len(pf.logw)==pf.n and np.allclose(pf._weights(),1/pf.n)
        ns.append(q['samples'])
    assert ns[0]<ns[1] and ns[1]==400


def test_default_selective_trigger_preserved():
    pf=particle_filter();policy=m.Policy();prior=pf._weights();ll=np.log(np.linspace(1,2,100))
    pf.logw=np.log(prior)+ll;state=copy.deepcopy(pf.rng.bit_generator.state)
    row=policy.measure(pf,prior,ll,{3:1,4:2,5:3,6:1500},True)
    assert not row['resampled'] and pf.n==100 and state==pf.rng.bit_generator.state


def test_unsupported_combination_rejected(static):
    for kw in (dict(particle_sampling='bad'),dict(particle_sampling=m.OPTION)):
        with pytest.raises(ValueError):m.Runtime(static,None,None,**kw)


def test_handoff_restores_fixed_population_before_tracking(monkeypatch):
    r=object.__new__(m.Runtime);r.particle_sampling=m.OPTION
    r.global_policy=NS(active=True);r.kld_audit={};pf=particle_filter(3000)
    r.pose=NS(provider=NS(loc=NS(_pf=pf)))
    monkeypatch.setattr(m.previous.Runtime,'on_command',lambda *a:None)
    r.on_command('r3',1.,dict(kind='look'));assert pf.n==3000
    r.on_command('r3',2.,dict(kind='mecanum',left=.35))
    assert pf.n==2000 and r.kld_audit['handoff']['before']==3000
