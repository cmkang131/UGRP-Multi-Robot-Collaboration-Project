import copy,importlib.util,json
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from harness import zone_solo_cyan_bias_tempering as bt
from tests.test_s2_rotation_left import fake_runtime
from harness.zone_solo_cyan_rotation_left import SEARCH
from harness.zone_solo_cyan_pulse_cal import action_of


def test_off_no_access_no_serialization_change():
    r=NS(record=lambda:dict(commands=[{'forward':.35}],value=1.))
    before=vars(r).copy();data=json.dumps(r.record()).encode()
    assert bt.attach(r,calibration=object()) is r
    assert vars(r)==before and json.dumps(r.record()).encode()==data


def test_scale_only_forward_mean_and_exact_scope_with_tail():
    key='0:forward:0.35:0.10';r,pf=fake_runtime(SEARCH,False)
    r.drive=lambda:copy.deepcopy(r.pulse_profiles[key]);base=copy.deepcopy(r.flow.profiles)
    gain=.91;g=bt.group(SEARCH,key)
    import hashlib
    table=dict(base_sha256=hashlib.sha256(bt.BASE.read_bytes()).hexdigest(),fit_seeds=[1,2],holdout=3,groups={g:dict(gain=gain)})
    bt.attach(r,forward_scale=bt.SCALE,calibration=table,servo_stiffness='real_v1')
    p=r.drive();assert p['mean_delta'][0]==pytest.approx(base[key]['mean_delta'][0]*gain)
    assert p['mean_delta'][1:]==base[key]['mean_delta'][1:]
    assert p['prediction_variance']==base[key]['prediction_variance']
    pf.command(dict(t=0.,**action_of(p)));pf.predict_to(.1);pf.command(dict(t=.1,kind='hold'));pf.predict_to(p['times'][-1])
    assert pf.px[:,0]==pytest.approx([p['mean_delta'][0]]*pf.n)
    assert r.flow.profiles==base and r.pulse_profiles==base
    r.pose.provider.servo[3]+=1
    assert r.drive()==base[key]


def test_private_closure_replacement_does_not_change_original():
    def factory():
        selected=lambda x:x*2
        return lambda x:selected(x)
    original=factory();changed=bt.replace_cell(original,'selected',lambda x:x*3)
    assert original(4)==8 and changed(4)==12


def test_ess_and_tempering_preserve_prior_and_increase_diversity():
    x=np.array([[0.,0,0],[1,0,0],[2,0,0]])
    w=np.array([1.,1.,100.]);w/=w.sum();half=np.sqrt(w);half/=half.sum()
    before=x.copy();a=bt.moments(x,w);b=bt.moments(x,half)
    assert b['ess']>a['ess'] and b['xy_trace']>a['xy_trace']
    np.testing.assert_array_equal(x,before)


def test_fit_uses_only_qualified_training_groups():
    spec=importlib.util.spec_from_file_location('fit_bias',Path(__file__).resolve().parents[1]/'experiments/2026-10-06-s2-realism/fit_bias_tempering.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    data=[dict(group='SEARCH',seed=s,exclude=[],predicted=[.02],actual=[.018]) for s in (1,2) for _ in range(10)]
    data.append(dict(group='SEARCH',seed=1,exclude=['wall_contact'],predicted=[.02],actual=[0.]))
    assert m.fit(data,[1,2])['SEARCH']['gain']==pytest.approx(.9)
    assert m.fit(data,[1,3])=={}


def test_scoring_keeps_missing_covariance_in_fixed_denominator(monkeypatch):
    spec=importlib.util.spec_from_file_location('score_bias',Path(__file__).resolve().parents[1]/'experiments/2026-10-06-s2-realism/score_bias_tempering.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    monkeypatch.setattr(m,'decisions',lambda r:[{'t':1.},{'t':2.}])
    p=dict(t=1.,t_est=1.,x=.3,y=0.,std_xy_m=.01,std_yaw_rad=.01,last_fix_t=1.,observation_quality={'diagnostics':{'pose_estimate':{'cluster_count':1,'selected_cluster_cov':np.diag([.00005,.00005,.0001]).tolist()}}})
    q=copy.deepcopy(p);q['t']=q['t_est']=2.;q['observation_quality']={'diagnostics':{}}
    score,_=m.metrics([p,q],{},lambda t:np.zeros(2),0,3,{1.,2.})
    assert score['primary_n']==2 and score['nees_available']==1
    assert score['all_misses']==2 and score['unavailable_times']==[2.]
