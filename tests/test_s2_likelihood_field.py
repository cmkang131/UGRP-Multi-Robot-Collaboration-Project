import copy,json
import numpy as np
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision,rt
from test_s2_visual_fix import make_provider
from harness.zone_solo_cyan_likelihood_field import Runtime,Previous,Field,likelihood,install,PARAMS
from harness import zone_s2_realism_contract_v123 as c


def test_off_actions_and_record_bytes(static,cal):
    rs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),vision_factory=FakeVision,**kw)
        for cls,kw in [(Previous,{}),(Runtime,{}),(Runtime,dict(measurement_model='off'))]]
    try:
        for r in rs:
            r.initial_commands(0.,{'r3':{1:1500,**rt.high.HIGH}});r.last_report=r.pose.report(1.);r.state='carry';r.receipt=True
        for t in (1.,1.05,1.1,1.2,1.65,1.8):
            actions=[r.step(t) for r in rs]
            assert len(set(json.dumps(x).encode() for x in actions))==1
            for r,rows in zip(rs,actions):
                for rid,a in rows:r.on_command(rid,t,a)
        assert len(set(json.dumps(r.record()).encode() for r in rs))==1
    finally:
        for r in rs:r.close()


def test_amcl_reference_hit_random_cube_and_outside_map():
    field=Field({'obstacles':[dict(kind='wall',center_m=[0,0],half_extents_m=[.02,.02])]})
    poses=np.array([[0,0,0],[.01,0,0],[100,0,0]])
    # First two endpoints hit an occupied cell; off-map uses max_occ_dist=2m.
    expected=1+np.array([.505,.505,.5*np.exp(-2**2/(2*.2**2))+.005])**3
    np.testing.assert_allclose(likelihood(field,poses,[[0,0]]),expected,rtol=1e-15)
    np.testing.assert_array_equal(likelihood(field,poses,[]),np.ones(3))
    field=Field({'obstacles':[dict(kind='wall',center_m=[x,0],half_extents_m=[.02,.2]) for x in (0,.5)]})
    # The endpoint is 10 cm from a wall in a free cell, not the max-distance branch.
    np.testing.assert_allclose(field.distances([[.12,0]]),[.1],atol=1e-14)
    expected=1+(.5*np.exp(-.1**2/(2*.2**2))+.005)**3
    assert likelihood(field,[[.12,0,0]],[[0,0]])[0]==pytest.approx(expected,abs=1e-15)
    assert PARAMS==json.load(open(c.ROOT/'experiments/2026-10-06-s2-realism/soft-mcl-criteria.json'))['parameters']


def observation(pf,vl,offset=20.):
    vb,_=pf.expected(np.array([[1.6,1.,0.]]),rt.high.HIGH)
    n=len(pf.columns);valid=(vb[0]>4)&(vb[0]+offset<470)
    return vl.ColumnObs(pf.columns.copy(),np.where(valid,vl.EDGE,vl.NONE),vb[0]+offset,vb[0]+offset,
                        np.zeros(n,int),np.full(n,np.nan),np.full(n,np.nan))


def test_twenty_pixel_residual_updates_weights_without_absolute_fix_or_repeat():
    src,pf,vl=make_provider()
    try:
        pf.init_gaussian((1.6,1.,0.),(.05,.05,.03));pf.t=2.
        stats=install(pf,c.old.hp.resolve(c.old.MAP_ID)[0]);obs=observation(pf,vl)
        before=pf._weights().copy();result=pf.update_obs(2.,obs,rt.high.HIGH)
        assert result['measured'] and stats['updates']==1
        assert stats['rows'][0]['kl']>1e-12 and not stats['rows'][0]['absolute_fix']
        assert not np.array_equal(before,pf._weights())
        pf.update_obs(2.05,obs,rt.high.HIGH)
        assert stats['updates']==1 and pf.last_scan_t==2.
        pf.update_obs(2.1,None,rt.high.HIGH)
        assert stats['updates']==1 and pf.last_scan_t==2.
    finally:src.close()


def test_unloaded_is_exact_and_instance_local():
    sources=[make_provider() for _ in range(2)]
    try:
        a,b=[x[1] for x in sources];vl=sources[0][2]
        stats=install(a,c.old.hp.resolve(c.old.MAP_ID)[0])
        for src,pf,_ in sources:
            # Synthetic complete table for testing the unloaded delegation.
            table=src.provider.calibration['camera_models']
            table['unloaded']['896,2035,1894,1500']=copy.deepcopy(table['loaded']['896,2035,1894,1500'])
            pf.load.loaded=False;pf.init_gaussian((1.6,1.,0.),(.02,.02,.03));pf.t=2.
            pf.update_obs(2.,observation(pf,vl,0.),rt.high.HIGH)
        np.testing.assert_array_equal(a.px,b.px);np.testing.assert_array_equal(a.logw,b.logw)
        assert a.last_scan_t==b.last_scan_t and stats['candidates']==0
    finally:
        for src,_,_ in sources:src.close()


def test_constant_out_of_map_score_is_not_a_fix():
    src,pf,vl=make_provider()
    try:
        obs=observation(pf,vl)
        pf.init_gaussian((100.,100.,0.),(.01,.01,.01));pf.t=2.
        before=pf.last_scan_t;stats=install(pf,c.old.hp.resolve(c.old.MAP_ID)[0])
        result=pf.update_obs(2.,obs,rt.high.HIGH)
        assert not result['measured'] and stats['candidates']==1 and stats['updates']==0
        assert pf.last_scan_t==before
    finally:src.close()


def test_admission_rejects_more_updates_with_worse_accuracy_and_long_gaps():
    import importlib.util
    path=c.ROOT/'experiments/2026-10-06-s2-realism/summarize_soft_mcl.py'
    spec=importlib.util.spec_from_file_location('soft_score',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.update_metrics(list(range(0,101)),(0,100))['frequency_pass']
    assert not m.update_metrics([1,2,3,4,5,6,99],(0,100))['frequency_pass']
    assert not m.accuracy_pass(dict(rmse_m=.2,p90_m=.4),[dict(rmse_m=.3,p90_m=.3)])
    assert not m.accuracy_pass(dict(rmse_m=.3,p90_m=.2),[dict(rmse_m=.3,p90_m=.3)])
    assert m.accuracy_pass(dict(rmse_m=.2,p90_m=.3),[dict(rmse_m=.3,p90_m=.3)])
