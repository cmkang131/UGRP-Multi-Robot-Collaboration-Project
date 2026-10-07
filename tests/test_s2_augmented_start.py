import copy,json,math
from types import SimpleNamespace as NS
import numpy as np
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision
from harness import zone_solo_cyan_augmented_start as m


def test_off_bytes_match_existing_controller(static,cal):
    runs=[c(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),
        vision_factory=FakeVision,**kw) for c,kw in [(m.Previous,{}),(m.Runtime,{}),
        (m.Runtime,dict(global_localization='off'))]]
    try:
        for r in runs:r.initial_commands(0.,{'r3':{1:2000,3:600,4:2200,5:1400,6:1500}})
        assert len({json.dumps(r.record()).encode() for r in runs})==1
    finally:
        for r in runs:r.close()


def particle_filter(n=100):
    pf=NS(n=n,px=np.c_[np.arange(n),np.zeros((n,2))],logw=np.zeros(n),
        rng=np.random.default_rng(16),stats={'resamples':0},_inject=0.)
    pf._weights=lambda:np.exp(pf.logw-np.max(pf.logw))/np.exp(pf.logw-np.max(pf.logw)).sum()
    pf._uniform_free=lambda k:np.full((k,3),-99.)
    return pf


def test_weak_observation_keeps_low_mass_alternative_and_true_ema_scale():
    pf=particle_filter();p=m.Policy();prior=pf._weights();likelihood=np.linspace(1,2,100)
    pf.logw=np.log(prior*likelihood);before=pf.px.copy();rng=copy.deepcopy(pf.rng.bit_generator.state)
    q=p.measure(pf,prior,np.log(likelihood),{3:1,4:2,5:3,6:1500},True)
    assert not q['resampled'] and q['ess']>50 and np.array_equal(before,pf.px)
    assert rng==pf.rng.bit_generator.state and q['w_avg']==pytest.approx(.015)
    assert not p.new_view({3:1,4:2,5:3,6:1500}) and p.new_view({3:1,4:2,5:3,6:1230})


def test_recovery_uses_likelihood_drop_and_global_draws_resets_ema():
    pf=particle_filter();p=m.Policy();p.slow=1.;p.fast=.01
    prior=pf._weights();pf.logw[1:]=-1000
    q=p.measure(pf,prior,np.log(np.full(100,.1)),{3:1,4:2,5:3,6:1500},True)
    assert q['resampled'] and q['injected']>90 and q['injection_probability']>.98
    assert np.count_nonzero(pf.px[:,0]==-99)==q['injected']
    assert p.slow==p.fast==0 and pf.stats['resamples']==1
    assert np.allclose(pf._weights(),.01)


def test_symmetric_rows_remain_unresolved_instead_of_connected_cluster_confidence():
    p=np.array([[0.,-.85,0.]]*80+[[0.,-2.25,0.]]*20)
    mean,cov,modes=m.belief_report(p,np.full(100,.01))
    assert modes['resolved'] is False and modes['bin_count']==2
    assert modes['leading_bins'][0]['weight']==pytest.approx(.8)
    assert cov[1,1]>.25 and mean[1]==pytest.approx(-1.13)


def test_entropy_selects_discriminating_view_and_unknown_is_not_fake_range():
    weights=np.array([.5,.5])
    same=m.sensor_probabilities(np.array([100.,100.]),2.5)
    distinct=m.sensor_probabilities(np.array([100.,400.]),2.5)
    unknown=m.sensor_probabilities(np.array([np.inf,np.nan]),2.5)
    assert m.information_gain(weights,distinct)>.2
    assert m.information_gain(weights,same)==pytest.approx(0.)
    assert np.allclose(unknown.sum(1),1) and unknown[0,-1]>.5
    assert m.information_gain(weights,unknown)==pytest.approx(0.)


def test_registration_and_invalid_combinations(static):
    from pathlib import Path
    c=json.loads(Path('experiments/2026-10-06-s2-realism/dock-augmented-criteria.json').read_text())
    assert (c['parameters']['alpha_slow'],c['parameters']['alpha_fast'])==(m.ALPHA_SLOW,m.ALPHA_FAST)
    assert c['parameters']['active_pans']==list(m.PANS)
    for kw in [dict(global_localization='bad'),dict(global_localization=m.OPTION),
        dict(global_localization=m.OPTION,amcl_update='ros_motion_v1',start_localization='amcl_global_active_v1')]:
        with pytest.raises(ValueError):m.Runtime(static,None,None,**kw)


def test_only_new_settled_pan_counts_and_tracking_restores_motion_gate(monkeypatch,static):
    pf=particle_filter(20);pf.t=0.;pf.initialized=True;pf.vel=np.zeros(3)
    pf.stats.update(scan_updates=0,scan_columns=0);pf.load=NS(loaded=False)
    pf.last_scan_t=None;pf.robust={'info_gain_min':.1};pf.last_info_t={}
    pf.predict_to=lambda t:setattr(pf,'t',t);pf.settled=lambda t:True
    pf.column_model_for=lambda p:None;pf.estimate=lambda:dict(x=0.)
    pf._gains=lambda a,b:{};pf.s2_global_policy=m.Policy()
    monkeypatch.setattr(m,'endpoints',lambda *a:np.array([[0.,0.]]))
    audit=m.install_global_update(pf,static,preset='ros_motion_v1')
    pose={3:1072,4:2400,5:1482,6:1500}
    pf.update_obs(0.,object(),pose);pf.update_obs(.05,object(),pose)
    pf.update_obs(.1,object(),{**pose,6:1230})
    pf.update_obs(.15,object(),pose)
    assert audit['candidates']==2
    del pf.s2_global_policy
    pf.update_obs(.2,object(),{**pose,6:970})
    assert audit['candidates']==2
