import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from harness import zone_solo_cyan_sensor_consistency as m
from harness.zone_solo_cyan_landmarks import Measurement, MapFeatures, gaussian
from harness.zone_solo_cyan_amcl_update import resample
from test_s2_augmented_start import particle_filter


def test_off_no_mutation_and_bytes_identical():
    obj=NS(record=lambda:dict(commands=[dict(left=.35)],poses=[1.,2.,3.]))
    before=dict(obj.__dict__); data=json.dumps(obj.record()).encode()
    assert m.attach(obj) is obj and m.attach(obj,sensor_consistency='off') is obj
    assert obj.__dict__==before and json.dumps(obj.record()).encode()==data
    with pytest.raises(ValueError):m.attach(obj,sensor_consistency='bad')


def test_table_6_3_density_product_and_no_observation_identity():
    field=NS(distances=lambda xy:abs(xy[:,0]));px=np.array([[0.,0.,0.],[.2,0.,0.]])
    packet=Measurement(np.array([[0.,0.],[0.,0.]]),[])
    actual=m.log_components(field,None,px,packet)
    p=.5*gaussian(np.array([0.,.2]),.2)+.5/100
    assert actual.shape==(1,2) and np.allclose(actual[0],2*np.log(p))
    assert np.all(m.log_components(field,None,px,Measurement(np.empty((0,2)),[]))==0)
    # Merely changing product to a sum of logs must not change its posterior.
    assert np.allclose(np.exp(actual[0]),p*p)


def test_same_mixture_for_feature_and_fixed_sigmas():
    mapped=MapFeatures(dict(regions={'B':dict(center_m=[0,0],half_extents_m=[1,1],rgba=[0,0,1,1])}))
    f=dict(kind='floor_line',hue=mapped.edges[0]['hue'],endpoints=[[-1,-1],[1,-1]],normal=[0,1])
    values=m.feature_density(mapped,np.array([[0.,0.,0.],[50.,50.,0.]]),[f])
    peak=gaussian(0.,.1)*gaussian(0.,np.deg2rad(5))
    assert values[0]==pytest.approx(.5*peak+.5/(6*2*np.pi))
    assert values[1]==pytest.approx(.5/(6*2*np.pi))
    assert m.FEATURE_PARAMS['random_fraction']==.05  # frozen module untouched


def test_selective_resampling_preserves_rng_weights_and_low_mass_particles():
    pf=particle_filter();pf.t=3.;pf.logw=np.log(np.linspace(1,2,pf.n))
    px=pf.px.copy();w=pf.logw.copy();rng=copy.deepcopy(pf.rng.bit_generator.state)
    q=m.selective_resample(pf,resample)
    assert not q['resampled'] and q['ess']>50
    assert np.array_equal(px,pf.px) and np.array_equal(w,pf.logw)
    assert rng==pf.rng.bit_generator.state and pf.stats['resamples']==0
    pf.logw[1:]=-1000
    assert m.selective_resample(pf,resample)['resampled']
    assert pf.stats['resamples']==1 and np.all(pf.px[:,0]==0)


def test_frozen_registration_parameters():
    c=json.loads(Path('experiments/2026-10-06-s2-realism/sensor-consistency-criteria.json').read_text())
    assert c['seeds']==[1051,1053,1054,1056,1057,1058,1059,1060,1061]
    assert c['parameters']==dict(z_hit=.5,z_rand=.5,wall_sigma_m=.2,alpha=.5,ess_fraction=.5)
    assert c['gates']['nees_exceed_fraction_lte']==.2
    assert c['gates']['unflagged_gt_25cm_lte']==0


def test_evaluation_keeps_missing_support_and_singular_covariance_explicit(monkeypatch):
    import importlib
    monkeypatch.syspath_prepend(str(Path('experiments/2026-10-06-s2-realism').resolve()))
    e=importlib.import_module('evaluate_sensor_consistency')
    p=np.zeros((4,3));w=np.full(4,.25)
    a=e.cloud_metrics(p,w,np.array([1.,0.,0.]))
    assert a['mass_10cm_5deg']==0 and a['nees_xy'] is None and a['ess']==4
    p[:,:2]=[[1,0],[-1,0],[0,1],[0,-1]]
    a=e.cloud_metrics(p,w,np.array([1.,0.,0.]))
    assert a['nees_xy']==pytest.approx(2.) and a['mass_10cm_5deg']==.25


def test_same_interior_map_line_has_no_along_line_position_information():
    mapped=MapFeatures(dict(regions={'B':dict(center_m=[0,0],half_extents_m=[1,3],rgba=[0,0,1,1])}))
    f=dict(kind='floor_line',hue=mapped.edges[1]['hue'],endpoints=[[1,-.5],[1,.5]],normal=[-1,0])
    px=np.array([[0.,-.5,0.],[0.,0.,0.],[0.,.5,0.]])
    density=m.feature_density(mapped,px,[f])
    assert np.all(density==density[0])  # no invented constraint along a partial line
