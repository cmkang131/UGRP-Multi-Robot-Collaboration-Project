"""Synthetic VIS5 regressions only: no model calls, renderer or physics steps."""
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'experiments/2026-09-26-vision-loc'
OFF_FIXTURES=ROOT/'tests/fixtures/vision_loc_v5_off'
# Byte-for-byte historical sources; never regenerate from HEAD at test time.
OFF_SOURCE_HASHES={
    'vision_pf_vis4.py.txt':'97a207dbda2fe31df32809b48baa4db1859ef0e1f30a196f5810b338c955b8f7',
    'owncam_localizer_m1.py.txt':'0304d7c491dfe6ae68cea6550f7a13e3c99e8e1d3f8e8b6c4b7b1d06893b1d63',
}
sys.path.insert(0,str(HERE))
import compare_v5 as comp
import route_audit_v5 as route
import vision_loc as vl
import vision_pf_v5 as pf
import vision_report_v5 as v5


def cfg(**kwargs):
    return {'enabled':True,**kwargs}


def step(h,t=1.,scan=1.,score=1.,xy=.001,yaw=.001,loaded=False,settled=True,available=True):
    return h.step(raw_xy_var=xy,raw_yaw_var=yaw,t=float(t),last_scan=scan,loaded=loaded,settled=settled,
        observation={'available':available,'score':score,'yaw_delta':.01})


@pytest.mark.parametrize('bad',[[],{'foo':1},{'enabled':1},{'enabled':False,'refine_yaw':False},
    cfg(refine_yaw=1),cfg(mode_threshold=float('nan')),cfg(mode_threshold=-1),
    cfg(yaw_states={}),cfg(yaw_states={k:{'a':1,'b_rad2':float('nan')} for k in v5.STATES})])
def test_configuration_rejected(bad):
    with pytest.raises(ValueError): v5.ReportHead(bad)


def test_off_is_exact_identity_and_no_state():
    e={'initialized':True,'arbitrary':'unchanged'}
    for c in (None,{'enabled':False}):
        h=v5.ReportHead(c)
        assert h.report(e,t=-100,last_scan=None,loaded=False,settled=True,observation={}) is e
        assert h.t is None and h._last_output is None


def frozen_module(name):
    path=OFF_FIXTURES/name
    if not path.is_file():
        pytest.fail(f'Missing required VIS4 regression fixture: {path}; restore tests/fixtures/vision_loc_v5_off')
    source=path.read_bytes()
    assert hashlib.sha256(source).hexdigest()==OFF_SOURCE_HASHES[name], f'VIS4 fixture hash mismatch: {name}'
    module=ModuleType(name.removesuffix('.py.txt'))
    module.__file__=str(path)
    exec(compile(source,str(path),'exec'),module.__dict__)
    return module


def make_pf(module,option=None):
    # The historical M1 loader also used git show. Freeze that dependency so
    # these tests work in shallow/sparse checkouts and source-only exports.
    m1=frozen_module('owncam_localizer_m1.py.txt')
    for rel,want in vl.mp.SHARED_RUNTIME_SHA256.items():
        assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==want, f'M1 runtime hash mismatch: {rel}'
    p=copy.deepcopy(m1.DEFAULT_PARAMS); p['particles']=32
    cal=json.loads((HERE/'calibration_train.json').read_text())
    return module.make_robust_pf(m1,json.loads((HERE/'maps/zone_wide_door_walls_v3_notags.json').read_text()),
        p,{}, {},cal['sag'],seed=42,**({} if option is None else {'report_v5':option}))


def assert_matches_vis4(candidate):
    baseline=make_pf(frozen_module('vision_pf_vis4.py.txt'))
    locs=[baseline,candidate]
    for loc in locs:
        loc.init_gaussian([0.,0.,0.],[.05,.03,.02])
        loc.command({'t':0.,'kind':'initial_servo_command','pulses':{1:2000,3:740,4:2320,5:1320,6:1500}})
    n=len(baseline.columns)
    scan=vl.ColumnObs(baseline.columns,np.full(n,vl.EDGE),np.full(n,200.),np.full(n,200.),
        np.full(n,vl.NONE),np.full(n,np.nan),np.full(n,np.nan))
    for t in (.1,.4,1.):
        reports=[loc.update_obs(t,None if t<.2 else scan,loc.servo) for loc in locs]
        assert reports[0]==reports[1], f'VIS4 report mismatch at t={t}'
        for loc in locs[1:]:
            assert np.array_equal(baseline.px,loc.px)
            assert np.array_equal(baseline.logw,loc.logw)
            assert baseline.rng.bit_generator.state==loc.rng.bit_generator.state


@pytest.mark.parametrize('option',[None,{'enabled':False}],ids=['default','explicit-off'])
def test_disabled_matches_pre_vis5_source_rng_particles_and_every_report(option,monkeypatch):
    def no_subprocess(*args,**kwargs):
        pytest.fail('VIS4 regression must run without Git or subprocesses')
    monkeypatch.setattr(subprocess,'Popen',no_subprocess)
    assert_matches_vis4(make_pf(pf,option))


@pytest.mark.parametrize('option',[None,{'enabled':False}],ids=['default','explicit-off'])
def test_disabled_regression_rejects_one_metre_report_error(option,monkeypatch):
    candidate=make_pf(pf,option)
    estimate=candidate.estimate

    def shifted_estimate():
        report=estimate()
        return {**report,'x':report['x']+1.}

    # Mutate only the current implementation; the VIS4 reference is immutable.
    monkeypatch.setattr(candidate,'estimate',shifted_estimate)
    with pytest.raises(AssertionError,match='VIS4 report mismatch'):
        assert_matches_vis4(candidate)


@pytest.mark.parametrize('name',OFF_SOURCE_HASHES)
@pytest.mark.parametrize('corrupt',[False,True],ids=['missing','corrupt'])
def test_required_off_fixture_fails_closed(name,corrupt,tmp_path,monkeypatch):
    monkeypatch.setattr(sys.modules[__name__],'OFF_FIXTURES',tmp_path)
    if corrupt:
        (tmp_path/name).write_text('# not the frozen source\n')
        with pytest.raises(AssertionError,match='VIS4 fixture hash mismatch'):
            frozen_module(name)
    else:
        with pytest.raises(pytest.fail.Exception,match='Missing required VIS4 regression fixture'):
            frozen_module(name)


def test_scan_refiner_is_own_input_only_and_flat_scan_does_not_change_yaw():
    obs=vl.ColumnObs(np.array([1]),np.array([vl.EDGE]),np.array([20.]),np.array([20.]),
        np.array([vl.NONE]),np.array([np.nan]),np.array([np.nan]))
    fake=SimpleNamespace(n=100,expected=lambda px,pose:(np.ones((len(px),1))*20,np.ones((len(px),1))*20),
        measurement={**vl.DEFAULT_MEASUREMENT,'min_columns':1},obs_params={'use_top_edge':False})
    e={'x':1.,'y':2.,'yaw':0.,'std_yaw_rad':.02}
    f=v5.features(fake,e,obs,{},measured=True,ess_pre=50.)
    assert f['available'] and f['yaw_delta']==0 and f['residual_rms_sigma']==0
    assert f['score']==.5
    assert not v5.features(fake,e,obs,{},measured=True,ess_pre=None)['available']


def test_enabled_runtime_matches_shadow_head_without_changing_particles():
    config=cfg(refine_yaw=True,yaw_states={s:{'a':4.,'b_rad2':.001} for s in v5.STATES},mode_threshold=.5)
    base=make_pf(pf); candidate=make_pf(pf,config); shadow=v5.ReportHead(config)
    pose={1:2000,3:740,4:2320,5:1320,6:1500}
    for loc in (base,candidate):
        loc.init_gaussian([0.,0.,0.],[.05,.03,.02])
        loc.command({'t':0.,'kind':'initial_servo_command','pulses':pose})
    cols=base.columns; n=len(cols)
    obs=vl.ColumnObs(cols,np.full(n,vl.EDGE),np.full(n,200.),np.full(n,200.),
        np.full(n,vl.NONE),np.full(n,np.nan),np.full(n,np.nan))
    for t in (.4,.6,.8,1.):
        b=base.update_obs(t,obs,pose); c=candidate.update_obs(t,obs,pose)
        f=v5.features(base,b,obs,pose,measured=True,ess_pre=base.diag['ess_pre'])
        expected=shadow.report(b,t=base.t,last_scan=t,loaded=False,settled=True,observation=f)
        assert c['vis5']==expected['vis5'] and c['cov']==expected['cov'] and c['yaw']==expected['yaw']
        assert np.array_equal(base.px,candidate.px) and np.array_equal(base.logw,candidate.logw)
        assert base.rng.bit_generator.state==candidate.rng.bit_generator.state
        assert candidate.estimate()['vis5']==c['vis5']


def test_interval_residual_preserves_open_end_and_ignores_absent_terms():
    obs=vl.ColumnObs(np.array([1,2,3]),np.array([vl.INTERVAL,vl.EDGE,vl.NONE]),
        np.array([vl.NEG_INF,10.,np.nan]),np.array([20.,10.,np.nan]),
        np.zeros(3,int),np.full(3,np.nan),np.full(3,np.nan))
    rms,n=v5.edge_residual(np.array([vl.NEG_INF,15.,vl.POS_INF]),np.zeros(3),obs,{'sigma_px':2.5,'use_top_edge':False})
    assert n==2 and rms==pytest.approx(math.sqrt(2))


def test_alarm_hysteresis_missing_observations_and_repeated_reports():
    h=v5.ReportHead(cfg(mode_threshold=.5))
    assert not step(h)['mode_alarm']
    assert not step(h,t=2.,scan=2.)['mode_alarm']
    third=step(h,t=3.,scan=3.)
    assert third['mode_alarm'] and third['xy_var']==.09
    assert step(h,t=3.,scan=3.)==third and h.high==3
    assert step(h,t=4.,scan=3.,available=False)['mode_alarm']
    for t in range(5,9): assert step(h,t=t,scan=t,score=.1)['mode_alarm']
    assert not step(h,t=9,scan=9,score=.1)['mode_alarm']


def test_stale_yaw_envelope_cannot_be_reset_by_load_or_arm_change():
    states={s:{'a':1.,'b_rad2':.001} for s in v5.STATES}
    states['loaded_unsettled']={'a':.0625,'b_rad2':0.}
    h=v5.ReportHead(cfg(yaw_states=states))
    initial=step(h)['yaw_var']
    got=step(h,t=3.,scan=1.,yaw=.0001,loaded=True,settled=False,available=False)
    assert got['yaw_var']==pytest.approx(initial+2*v5.Q)
    assert step(h,t=4.,scan=4.,yaw=.0001,loaded=True,settled=False)['yaw_var']<initial


@pytest.mark.parametrize('t,scan',[(0.,0.),(2.,None),(2.,.5),(2.,3.)])
def test_time_reversal_or_future_scan_rejected(t,scan):
    h=v5.ReportHead(cfg()); step(h)
    with pytest.raises(ValueError): step(h,t=t,scan=scan)


def test_distinct_frames_at_same_timestamp_kept_without_double_evidence():
    states={s:{'a':1.,'b_rad2':.001} for s in v5.STATES}
    h=v5.ReportHead(cfg(yaw_states=states,mode_threshold=.5,refine_yaw=True)); a=step(h)
    b=step(h,xy=.1,yaw=.00001)
    assert b['xy_var']==.1 and b['yaw_var']==a['yaw_var']
    assert b['yaw_delta']==0 and h.high==1 and not b['mode_alarm']


def test_covariance_scaling_preserves_psd_cross_terms_and_xy_mean():
    states={s:{'a':4.,'b_rad2':.001} for s in v5.STATES}
    h=v5.ReportHead(cfg(yaw_states=states,refine_yaw=True))
    cov=np.array([[.04,.002,.001],[.002,.01,.002],[.001,.002,.004]])
    e=dict(initialized=True,x=1.,y=2.,yaw=math.pi-.005,cov=cov.tolist(),std_xy_m=math.sqrt(.05),std_yaw_rad=math.sqrt(.004))
    before=copy.deepcopy(e)
    got=h.report(e,t=1.,last_scan=1.,loaded=False,settled=True,observation={'available':True,'yaw_delta':.01})
    assert e==before and got['x']==1 and got['y']==2 and got['yaw']<0
    assert np.linalg.eigvalsh(got['cov']).min()>0
    assert got['cov'][2][2]==pytest.approx(.017)
    assert got['cov'][0][2]==pytest.approx(.001*math.sqrt(.017/.004))


def test_continuous_path_catches_collision_between_safe_endpoints():
    wall=np.array([[0.,0.,.02,1.]])
    assert route.swept_clearance([-1,0,0],[-1,0,0],wall)['footprint_lower_m']>0
    assert route.swept_clearance([1,0,0],[1,0,0],wall)['footprint_lower_m']>0
    assert route.swept_clearance([-1,0,0],[1,0,0],wall)['footprint_lower_m']==0


def test_door_center_footprint_and_sigma_budget():
    walls=np.array([[2.2,-.7,.025,.5],[2.2,.8,.025,.5]])  # gap [-.2,.3]
    a=route.audit_segment([1.8,.05,0],[2.6,.05,0],.01,.01,walls)
    assert a['footprint_lower_m']==pytest.approx(.10)
    assert a['sigma_clearance_nonnegative']
    b=route.audit_segment([1.8,.05,0],[2.6,.05,0],.07,.05,walls)
    assert b['adjusted_lower_m']<0 and not b['sigma_clearance_nonnegative']


def test_rotation_sweep_bound_is_conservative_against_dense_oracle_geometry():
    walls=np.array([[0.,.5,.3,.02]])
    start=np.array([0.,0.,-.2]); end=np.array([.1,.05,.3])
    lower=route.swept_clearance(start,end,walls)['footprint_lower_m']
    distances=[]
    for t in np.linspace(0,1,301):
        p=start*(1-t)+end*t; c,s=math.cos(p[2]),math.sin(p[2])
        poly=route.CORNERS@np.array([[c,s],[-s,c]])+p[:2]
        distances.append(route.polygon_distance(poly,route.rectangle(walls[0])))
    assert lower<=min(distances)+1e-12 and min(distances)-lower<.001


def test_event_definition_splits_gaps_and_counts_clusters():
    rows=[{'frame':i,'t':t} for i,t in enumerate([0,.2,.4,2.,2.2,2.4])]
    assert comp.events([True,True,False,True,True,True],rows)=={'events':2,'longest_s':pytest.approx(.4),'longest_frames':3}


def test_plan_dev_only_disjoint_and_defaults_unchanged(tmp_path):
    p=comp.plan_load(); assert not set(p['fit_episodes'])&set(p['validation_episodes'])
    assert 'report_v5' not in json.loads((HERE/'selected_config_v3.json').read_text())
    p['validation_episodes']=[p['fit_episodes'][0]]
    path=tmp_path/'plan.json'; path.write_text(json.dumps(p))
    with pytest.raises(ValueError): comp.plan_load(path)
    p['validation_episodes']=['vl3-test-s961']; path.write_text(json.dumps(p))
    with pytest.raises((ValueError,SystemExit)): comp.plan_load(path)


def test_no_overwrite(tmp_path):
    p=tmp_path/'result.json'; comp.save(p,{'x':1})
    with pytest.raises(FileExistsError): comp.save(p,{'x':2})
    assert json.loads(p.read_text())=={'x':1}


def test_fit_does_not_consult_validation(tmp_path):
    # API accepts only explicit training sequences; fit metadata is reproducible.
    r={'frame':0,'t':1.,'loaded':False,'settled':True,'point':[0.,0.,.1],
       'raw_xy_var':.01,'raw_yaw_var':.01,'last_scan':1.,'observation':{'available':False,'yaw_delta':0.}}
    s={'name':'synthetic-fit','rows':[r], 'truth':{0:{'gt':[0.,0.,0.]}}}
    p=comp.plan_load(); a,_=comp.fit_yaw([s],False,p)
    s['truth'][0]['gt'][2]=.5
    b,_=comp.fit_yaw([s],False,p)
    assert a!=b


def test_extract_function_contains_no_truth_reads():
    import inspect
    source=inspect.getsource(comp.extract)+inspect.getsource(comp.inventory)
    assert 'eval_only' not in source and 'frames_eval' not in source


def test_selection_rejects_inflated_sigma_even_with_good_coverage():
    plan=comp.plan_load()
    b={'n':100,'pos_p90_m':.05,'yaw_p90_deg':2.,'yaw_nll':1.,
       'episode_balanced_yaw_nll':1.,'episode_balanced_xy_nll_iso':1.,
       'yaw_coverage95':.7,'xy_coverage95_iso':.7,'yaw_over3_fraction':.2,'xy_over3_fraction':.2,
       'overconfident_frames':20,'overconfident_fraction':.2,'overconfident_events':3,
       'xy_sigma_p50_m':.03,'yaw_sigma_p90_deg':1.}
    baseline={'cohorts':{c:{g:dict(b) for g in ('all','door_loaded','loaded_transport')}
                        for c in ('validation','all_teacher')},
              'episodes':{ep:{'all':dict(b)} for ep in plan['validation_episodes']}}
    results={name:copy.deepcopy(baseline) for name in ('b0u0','y1','s1','y2','m1')}
    for name in ('s1','y2','m1'):
        for groups in results[name]['cohorts'].values():
            for m in groups.values():
                m.update(yaw_coverage95=.95,yaw_over3_fraction=0.,episode_balanced_yaw_nll=0.,
                         yaw_sigma_p90_deg=30.)
    decision=comp.select(results,{'validation':{'pooled':{'recall':1.,'normal_fpr':0.}}},1.,plan)
    assert decision['shadow_selected']=='b0u0' and not decision['deployment_enabled']
    assert 'yaw_sigma_overinflation' in decision['checks']['y2']['reasons']
    assert 'y2_ineligible' in decision['checks']['m1']['reasons']
