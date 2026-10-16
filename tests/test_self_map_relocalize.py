import ast
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from harness.self_map_relocalize import Relocalizer, GridField
from harness.own_map_amcl_vendor import kld, field, augmented


def grid():
    return dict(resolution_m=.1,cells=[[x,y,1 if x in (0,19) or y in (0,19) else -1]
                                      for x in range(20) for y in range(20)])


def test_pinned_function_bodies_and_default_constants():
    folder=Path(__file__).parents[1]/'harness/own_map_amcl_vendor'
    manifest=json.loads((folder/'provenance.json').read_text())
    for name, info in manifest.items():
        data=(folder/(name+'.py')).read_bytes()
        assert hashlib.sha256(data).hexdigest()==info['copy_sha256']
        source=data.decode();lines=source.splitlines(keepends=True)
        digests={hashlib.sha256(''.join(lines[min([n.lineno]+[d.lineno for d in getattr(n,'decorator_list',[])])-1:n.end_lineno]).encode()).hexdigest()
                 for n in ast.parse(source).body if hasattr(n,'end_lineno')}
        assert all(x['sha256'] in digests for x in info['selected'])
    assert kld.PARAMS['max_samples']==100000 and kld.PARAMS['min_samples']==2000
    assert field.PARAMS['sigma_hit_m']==.2
    assert (augmented.ALPHA_SLOW,augmented.ALPHA_FAST)==(.001,.1)


def test_unknown_start_motion_gate_and_map_immutability():
    g=grid();before=json.dumps(g)
    pf=Relocalizer(g,seed=41)
    assert np.ptp(pf.px[:,0])>1.7 and np.ptp(pf.px[:,2])>6.
    assert not np.any(pf.field.raw[np.floor(pf.px[:,1]/.1).astype(int)-pf.field.lo[1],
                                       np.floor(pf.px[:,0]/.1).astype(int)-pf.field.lo[0]]==254)
    servo={3:740,4:2320,5:1320,6:1500}
    pf.step(t=0,points=[[1,0]],delta=[0,0,0],servo=servo)
    r=pf.step(t=.2,points=[[1,0]],delta=[0,0,0],servo=servo)
    assert not r['updated'] and r['reason']=='motion_gate'
    assert before==json.dumps(g)


def test_raster_budget_rejects_before_allocation(monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('allocated raster before budget check')
    monkeypatch.setattr(np,'full',forbidden)
    with pytest.raises(ValueError,match='GRID_RASTER_BUDGET'):
        GridField(dict(resolution_m=.1,cells=[[0,0,-1],[1000000,1000000,1]]))


def test_kld_selective_resampling_preserves_uninformative_belief():
    p=SimpleNamespace(n=20,px=np.zeros((20,3)),logw=np.zeros(20),rng=np.random.default_rng(1),stats={'resamples':0})
    p._weights=lambda:np.ones(20)/20
    policy=kld.Policy();r=policy.measure(p,p._weights(),np.zeros(20),{3:1,4:2,5:3,6:4},True)
    assert not r['resampled'] and r['samples_after']==20
    second=policy.measure(p,p._weights(),np.ones(20)*-.2,{3:1,4:2,5:3,6:4},True)
    assert second['w_fast']<second['w_slow'] and not second['resampled']
    params={**kld.PARAMS,'max_samples':100,'min_samples':20}
    r=kld.resample(p,parameters=params)
    assert r['samples']==100 and r['occupied_bins']==1


def test_goal_comes_only_from_first_confirmed_own_observation():
    path=Path(__file__).parents[1]/'experiments/2026-10-08-own-map-utility/code/replay.py'
    spec=importlib.util.spec_from_file_location('utility_replay',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.remembered_goal([], {}) is None
    candidate=dict(state='locally_confirmed_region',confirmed_t=4.,id=7,center_m=[.3,.7],
                   observations=3,first_t=2.,bounds_m=[[.2,.5],[.4,.9]],confidence=.5)
    r=dict(t=4.,frame_id=2,goal=dict(robot_id='r3',coordinate_frame='r3/own_odom',candidates=[candidate]))
    v=m.remembered_goal([r],{2:dict(sha256='a'*64)})
    assert v['center_m']==[.3,.7] and v['obs_id']=='r3-obs-000002' and v['source']=='own'
    assert v['entity']['id']=='B'
