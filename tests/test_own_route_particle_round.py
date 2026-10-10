import json,pickle
from types import SimpleNamespace
import numpy as np
import pytest
from harness.active_navfn_start import StartCycleNavigator
from harness.active_frontier_cycle import CycleNavigator
from harness.goal_candidate_preemption import install,OPTION
from harness.rbpf_candidate_audit import install as audit
from harness.rbpf_stage_candidates import install as candidate,LOCAL
from test_rbpf_stage_candidates import grid,scan
from harness.self_map_csm import CSMOptions
from scripts import run_own_route_particle_round as runner


def test_default_off_leaves_navigator_state_and_output_bytes():
    n=StartCycleNavigator();before=pickle.dumps(n)
    assert install(n) is n and pickle.dumps(n)==before


def test_new_candidate_preempts_sweep_and_existing_frontier(monkeypatch):
    n=install(StartCycleNavigator(),goal_preemption=OPTION)
    n.phase='sensor_sweep';n.locked=True;n.target=np.array([3.,0.]);n.frontier=n.target.copy()
    observed=[]
    # Observe the parent boundary without native planning/physics.
    def parent(self,costmap,pose,t,static_goal=None):
        observed.append((self.phase,self.sweep_pending,self.locked,self.target.tolist()))
        self.requested_goal=np.asarray(static_goal) if static_goal is not None else None
        return {'status':'parent'}
    monkeypatch.setattr(CycleNavigator,'update',parent)
    n=install(StartCycleNavigator(),goal_preemption=OPTION)
    n.phase='sensor_sweep';n.locked=True;n.target=np.array([3.,0.])
    n.update(None,np.zeros(3),1.,np.array([.12,0.]))
    assert observed[-1]==(None,None,False,[.12,0.])
    n.update(None,np.zeros(3),2.,np.array([.2,0.]))
    assert observed[-1][3]==[.2,0.]


def test_no_candidate_does_not_interrupt_initial_sweep(monkeypatch):
    n=install(StartCycleNavigator(),goal_preemption=OPTION)
    result=n.update(None,np.zeros(3),1.)
    assert result['status']=='sensor_sweep' and n.phase=='sensor_sweep'


def test_b_real_callback_differs_from_baseline_and_audit_preserves_samples():
    p,f=scan();args=(f,p,np.zeros(2),np.zeros(3),np.diag([.02,.02,.01]))
    a=grid();b=grid();candidate(b,rbpf_local_search=LOCAL)
    old=a._selective_proposal(*args,np.random.default_rng(8),CSMOptions())
    audit(a);audit(b)
    new=a._selective_proposal(*args,np.random.default_rng(8),CSMOptions())
    local=b._selective_proposal(*args,np.random.default_rng(8),CSMOptions())
    assert old[0].tobytes()==new[0].tobytes() and json.dumps(old[1:],sort_keys=True)==json.dumps(new[1:],sort_keys=True)
    assert a._candidate_audit['proposal_calls']==b._candidate_audit['proposal_calls']==1
    assert b._candidate_audit['translation_window_m']==.1
    assert local[2]['candidates']<new[2]['candidates']
    assert b.export()['candidate_audit']['candidates_total']==local[2]['candidates']
    audit(a)
    assert a._candidate_audit['proposal_calls']==0


def test_six_seeds_all_profiles_registered_no_threshold_change(tmp_path):
    plan=runner.plan(tmp_path)
    assert len(plan)==30 and sum(j['mode']=='prepare' for j in plan)==6
    assert len({j['seed'] for j in plan})==6
    assert len({j['output'] for j in plan})==30
    for seed in runner.SEEDS:
        for profile in runner.old.PROFILES:
            b=runner.bundle(seed,'a'*40,profile,'stage')
            assert b['task']['seed']==seed and b['case_cap_s']==120
            assert b['options']['goal_preemption']==OPTION
        assert runner.bundle(seed,'a'*40,'baseline','prepare')['case_cap_s']==150
    with pytest.raises(ValueError):runner.bundle(60011,'a'*40,'b','stage')


def test_no_mac_batch(tmp_path,monkeypatch):
    monkeypatch.setattr(runner.platform,'system',lambda:'Darwin')
    with pytest.raises(RuntimeError,match='ORACLE_ONLY'):runner.batch(SimpleNamespace(output=tmp_path))


def test_composed_rbpf_update_calls_b_window_and_local_map():
    from harness.rbpf_rejection import _proposals
    p,_=scan();g=grid()
    for m in g.maps:m.insert([0,0],[np.array([[1.,-.7],[1.,.7]])])
    g.pending_cov[:]=np.diag([.02,.02,.01])
    candidate(g,rbpf_local_search=LOCAL);audit(g)
    g._selective_proposals(g,p,np.zeros(2),True)
    s=g._candidate_audit
    assert s['proposal_calls']>=1 and s['reference_calls']>=s['proposal_calls']
    assert s['candidates_max']<1000 and s['translation_window_m']==.1
