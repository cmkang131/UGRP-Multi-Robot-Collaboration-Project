import copy,json
from types import SimpleNamespace as NS
import numpy as np
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision,rt
from harness.zone_solo_cyan_amcl_update import Runtime,Previous,install,moved,probability_loglik,converged
from harness.zone_solo_cyan_likelihood_field import PARAMS


def make(cls,static,cal,**kw):
    return cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),vision_factory=FakeVision,**kw)


def test_off_commands_record_and_search_failure_byte_equal(static,cal):
    rs=[make(cls,static,cal,**kw) for cls,kw in [(Previous,{}),(Runtime,{}),(Runtime,dict(amcl_update='off',dev_search='off'))]]
    try:
        for r in rs:r.initial_commands(0.,{'r3':{1:2000,**rt.pose_of('search')}})
        for r in rs:r.fail('CYAN_NOT_UNIQUELY_VISIBLE',1.)
        assert len(set(json.dumps(r.record()).encode() for r in rs))==1
    finally:
        for r in rs:r.close()


def test_strict_motion_gate_no_resample_for_repeated_or_changed_arm(monkeypatch,static):
    import harness.zone_solo_cyan_amcl_update as m
    pf=NS(t=0.,n=20,initialized=True,px=np.c_[np.linspace(-.2,.2,20),np.zeros((20,2))],
          logw=np.zeros(20),vel=np.zeros(3),stats={'resamples':0,'scan_updates':0,'scan_columns':0},
          rng=np.random.default_rng(6),load=NS(loaded=False),last_scan_t=None,
          robust={'info_gain_min':.1},last_info_t={},_inject=0.)
    pf.predict_to=lambda t:setattr(pf,'t',t)
    pf.settled=lambda t:True;pf.column_model_for=lambda p:None
    pf.estimate=lambda:dict(x=float(pf.px[:,0].mean()))
    pf._weights=lambda:np.exp(pf.logw-np.max(pf.logw))/np.exp(pf.logw-np.max(pf.logw)).sum()
    pf._gains=lambda a,b:{}
    monkeypatch.setattr(m,'endpoints',lambda *a:np.array([[0.,0.]]))
    a=install(pf,static,preset='ros_motion_v1');pf.update_obs(0.,object(),{6:1500})
    before=(pf.px.copy(),pf.logw.copy(),copy.deepcopy(pf.rng.bit_generator.state))
    for t in np.arange(.05,1.01,.05):pf.update_obs(t,object(),{6:int(1500+100*t)})
    assert a['candidates']==a['resamples']==1
    np.testing.assert_array_equal(pf.px,before[0]);np.testing.assert_array_equal(pf.logw,before[1])
    assert pf.rng.bit_generator.state==before[2]
    assert not moved(np.array([.25,0.,.2])) and moved(np.array([.250001,0.,0.]))
    pf.vel=np.array([1.,0.,0.]);pf.update_obs(1.3,object(),{})
    assert a['candidates']==a['resamples']==2
    pf.update_obs(1.35,None,{})
    assert a['resamples']==2


def test_nav2_prob_mixture_converged_beam_skip_and_fallback():
    class Field:
        def __init__(self,d):self.d=np.array(d)
        def distances(self,p):return self.d
    d=np.array([[0.,2.,.1],[0.,2.,.1],[0.,2.,.1],[0.,2.,.1]])
    px=np.zeros((4,3));points=np.zeros((3,2));expected=.5*np.exp(-d*d/(2*.2**2))+.005
    ll,q=probability_loglik(Field(d),px,points,is_converged=False)
    np.testing.assert_allclose(ll,np.log(expected).sum(1));assert q['skipped']==0
    ll,q=probability_loglik(Field(d),px,points,is_converged=True)
    np.testing.assert_allclose(ll,np.log(expected[:,[0,2]]).sum(1));assert q['skipped']==1 and not q['fallback_all']
    ll,q=probability_loglik(Field(np.ones((4,3))*2),px,points,is_converged=True)
    assert q['fallback_all'] and q['skipped']==0
    assert converged(px) and not converged(np.array([[0,0,0],[1.01,0,0]]))


@pytest.mark.parametrize('code',['CYAN_NOT_UNIQUELY_VISIBLE','CYAN_REGRASP_NOT_UNIQUELY_VISIBLE','CYAN_ALIGN_VIEW_LOST'])
def test_search_unknown_logs_then_repeats_without_faking_target_or_receipt(static,cal,code):
    r=make(Runtime,static,cal,dev_search='repeat_views_v1')
    try:
        r.initial_commands(0.,{'r3':{1:2000,**rt.pose_of('search')}})
        r.state='search';r.search_i=1;r.target=None
        assert r.fail(code,2.)==[{'kind':'hold'}]
        assert not r.terminal and r.failure is None and r.target is None and not r.receipt
        assert r.state=='search_move' and r.search_i==0
        assert r.soft_counts[code]==1
        r._control(rt.CAP_S+1.,True)
        assert r.failure=='LOCAL_TIMEOUT'
    finally:r.close()


def test_v125_requires_passing_fixed_candidate_and_new_seed(tmp_path):
    from harness import zone_s2_realism_contract_v125 as c
    from scripts import run_s2_realism_v125 as runner
    b=c.bundle('a'*40,seed=1050,**c.NEW_OPTIONS);c.require_execution(b)
    for key,value in [('amcl_update','off'),('dev_search','off')]:
        bad=copy.deepcopy(b);bad['options'][key]=value
        with pytest.raises(ValueError):c.require_execution(bad)
    for seed in (1047,1049):
        bad=copy.deepcopy(b);bad['task']['seed']=seed
        with pytest.raises(ValueError):c.require_execution(bad)
    bad=copy.deepcopy(b);bad['research_result']=True
    with pytest.raises(ValueError):c.require_execution(bad)
    a=runner.parser().parse_args(['--expected-source-sha','a'*40,'--output',str(tmp_path)])
    assert a.amcl_update==a.dev_search=='off'


def test_search_policy_keeps_command_state_failure_terminal(static,cal):
    r=make(Runtime,static,cal,dev_search='repeat_views_v1')
    try:
        r.initial_commands(0.,{'r3':{1:2000,**rt.pose_of('search')}})
        r.fail('LOADED_COMMAND_STATE_LOST',1.)
        assert r.terminal and r.failure=='LOADED_COMMAND_STATE_LOST'
    finally:r.close()
