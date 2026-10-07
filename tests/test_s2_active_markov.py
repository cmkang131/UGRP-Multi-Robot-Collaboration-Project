import copy,json,math
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest

from harness import zone_solo_cyan_active_markov as m
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision


def test_default_off_preserves_command_and_record_bytes(static,cal):
    rs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),
        vision_factory=FakeVision,**kw) for cls,kw in [(m.kld.Runtime,{}),(m.Runtime,{}),(m.Runtime,dict(start_localization='off'))]]
    try:
        for r in rs:r.initial_commands(0.,{'r3':{1:2000,3:740,4:2320,5:1320,6:1500}})
        for t in (1.,1.05,1.65):
            commands=[r.step(t) for r in rs]
            assert len({json.dumps(c).encode() for c in commands})==1
            for r,issued in zip(rs,commands):
                for rid,cmd in issued:r.on_command(rid,t,cmd)
        assert len({json.dumps(r.record()).encode() for r in rs})==1
    finally:
        for r in rs:r.close()


def test_conditional_entropy_prefers_discriminating_action_and_counts_unknown():
    p=np.array([[0.,0.,0.],[1.,0.,0.]]);w=np.array([.5,.5])
    assert m.expected_posterior_entropy(p,w,np.eye(2))==pytest.approx(0.)
    assert m.expected_posterior_entropy(p,w,np.ones((2,1)))==pytest.approx(math.log(2))
    # Identical-state duplicates must not manufacture extra entropy.
    assert m.expected_posterior_entropy(np.zeros((2,3)),w,np.ones((2,1)))==pytest.approx(0.)


def test_motion_cubature_preserves_mean_and_covariance():
    delta=np.array([.07,0.,.2]);cov=np.diag([.0001,.0004,.0009])
    p=m.predicted_samples(np.zeros((1,3)),delta,cov)
    np.testing.assert_allclose(p.mean(0),delta,atol=1e-15)
    np.testing.assert_allclose((p-delta).T@(p-delta)/6,cov,atol=1e-15)


def test_ranking_selects_max_expected_reduction(monkeypatch):
    from harness import vision_loc_protocol as vp
    fake=NS(expected_rows=lambda g,p,c:(np.where(p[:,0:1]<.5,100.,400.),None))
    monkeypatch.setattr(vp,'load_vis3',lambda:(fake,None))
    pf=NS(px=np.array([[0.,0.,0.],[1.,0.,0.]]),_weights=lambda:np.array([.5,.5]),
        geometry=None,column_model_for=lambda *a,**k:None,measurement={'sigma_px':2.5},
        _map_logprior=lambda p:np.zeros(len(p)))
    actions=[dict(name=name,delta=[dx,0.,0.],covariance=np.zeros((3,3)))
             for name,dx in [('uninformative',5.),('informative',0.)]]
    ranking=m.rank_actions(pf,{},actions)
    assert ranking[0]['name']=='informative'
    assert ranking[0]['expected_reduction_nats']>ranking[1]['expected_reduction_nats']+.1


def test_candidates_use_only_frozen_pulses_and_full_stop_horizons():
    # This small fixed profile table is in the tracked v122 calibration.
    from harness import zone_s2_realism_contract_v122 as contract
    model=contract.old.hp.base.read(contract.ROOT/contract.PULSE_MODEL)
    actions=m.candidates(model['profiles'])
    assert len(actions)==8
    for a in actions:
        assert a['horizon_s']==pytest.approx(a['pulses']*a['pulse_horizon_s'])
        assert a['pulse_horizon_s']>=a['command']['duration_s']
        assert sum(bool(a['command'][k]) for k in ('forward','left','turn'))==1
    assert .06<abs(actions[-1]['delta'][1])<.08


def fake_active():
    r=object.__new__(m.Runtime);r.active_markov_option=m.OPTION;r.robot_id='r3';r.started_at=1.3
    r.state='active_start';r.active_audit=dict(reason=None,decisions=[]);r.events=[]
    r.pose=NS(provider=NS(loc=NS(_pf=NS(last_scan_t=5.,estimate=lambda:dict(std_xy_m=.09,std_yaw_rad=.04)))))
    r.set_state=lambda state,t:setattr(r,'state',state)
    return r


def test_deadline_and_sigma_stop_without_cargo_or_gt():
    r=fake_active();r.active_phase='observe';r.observe_after=4.
    assert r.step(5.)==[('r3',{'kind':'hold'})]
    assert r.active_audit['reason']=='SIGMA_REACHED'
    r=fake_active();r.active_phase='moving';r.active_next=100.;r.active_queue=[object()]
    r.step(31.3)
    assert r.terminal and r.active_audit['reason']=='TIME_CAP' and len(r.active_queue)==1


def test_active_commands_do_not_trigger_kld_navigation_handoff(monkeypatch):
    r=fake_active();r.kld_audit=dict(handoff=None);seen=[]
    monkeypatch.setattr(m.legacy.Runtime,'on_command',lambda *args:seen.append(args[-1]))
    r.on_command('r3',2.,dict(kind='mecanum',turn=.35))
    assert seen and r.kld_audit['handoff'] is None


def test_option_requires_kld_augmented_and_calibration(static):
    with pytest.raises(ValueError):m.Runtime(static,None,None,start_localization=m.OPTION)


def test_episode_has_hard_30s_budget_and_no_eval_feedback(monkeypatch):
    from scripts.run_s2_active_markov_start import episode
    class Backend:
        now=1.3;commands={'r3':{1:2000}};issued=[];samples=0
        def reset(self,cap):pass
        def set_deadline(self,t):self.deadline=t
        def advance_to(self,t):assert t<=self.deadline+1e-8;self.now=t
        def eval_sample(self):self.samples+=1
        def capture(self):return {'own':'RGB'}
        def issue(self,rid,action):self.issued.append(action)
    class Runtime:
        state='active_start';terminal=False
        def initial_commands(self,*a):pass
        def on_frames(self,now,frames):assert frames=={'own':'RGB'}
        def step(self,now):self.terminal=now>=31.3-1e-8;return [('r3',dict(kind='hold'))]
        def on_command(self,*a):pass
    b=Backend();assert episode(b,Runtime())==pytest.approx(30.)
    assert b.samples==601 and all(a['kind']=='hold' for a in b.issued)
