import json
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from harness import zone_solo_cyan_beamskip as m
from harness.zone_solo_cyan_landmarks import Measurement,MapFeatures,landmark_likelihood


def test_off_identity_and_record_bytes():
    obj=NS(record=lambda:dict(commands=[dict(vx=.35)],pose=[1.,2.,3.]))
    attrs=dict(obj.__dict__); before=json.dumps(obj.record()).encode()
    assert m.attach(obj) is obj and m.attach(obj,sensor_beamskip='off') is obj
    assert obj.__dict__==attrs and json.dumps(obj.record()).encode()==before
    with pytest.raises(ValueError):m.attach(obj,sensor_beamskip='unknown')


def test_source_ceil_subsample_before_invalid_columns():
    assert np.array_equal(m.beam_indices(96),np.arange(0,96,2))
    assert len(m.beam_indices(59))==59
    points=np.c_[np.arange(96),np.ones(96)]
    cm=NS(origin=np.array([0.,0.,1.]),_rot=np.array([[1,0,0],[0,0,1],[0,-1,0]]),
          floor_point=lambda t:points,t_of_row=lambda r:r)
    obs=NS(columns=np.arange(96),b_lo=np.zeros(96),b_kind=np.ones(96,int))
    obs.b_kind[::4]=0
    assert np.array_equal(m.prob_endpoints(cm,obs),points[np.arange(2,96,4)])
    # Do not compact surviving rays then select every second survivor.
    assert m.prob_endpoints(cm,obs).shape==(24,2)


def test_exact_mixture_log_product_and_convergence_guard():
    distances=np.array([[0.,1.],[.2,1.]])
    field=NS(distances=lambda xy:distances)
    p=np.zeros((2,3));packet=Measurement(np.array([[0.,0.],[1.,0.]]),[])
    parts,q=m.log_components(field,None,p,packet,is_converged=False)
    expected=.5*np.exp(-distances**2/(2*.2**2))+.5/100
    assert np.allclose(parts[0],np.log(expected).sum(1))
    assert not q['beam_skip_enabled'] and q['skipped']==0
    parts,q=m.log_components(field,None,p,packet,is_converged=True)
    assert q['skipped']==1 and not q['fallback_all']
    assert np.allclose(parts[0],np.log(expected[:,0]))


def test_strict_particle_agreement_and_ninety_percent_fallback():
    d=np.full((10,10),1.);d[:3,0]=.1;d[:4,1]=.1
    field=NS(distances=lambda xy:d);packet=Measurement(np.zeros((10,2)),[])
    parts,q=m.log_components(field,None,np.zeros((10,3)),packet,is_converged=True)
    # Exactly 30% is rejected: >=90% rejected restores ALL beams.
    assert q['fallback_all'] and q['skipped']==0
    assert np.allclose(parts[0],np.log(.5*np.exp(-d*d/.08)+.005).sum(1))


def test_landmarks_unchanged_and_missing_wall_identity():
    mapped=MapFeatures(dict(regions={'B':dict(center_m=[0,0],half_extents_m=[1,2],rgba=[0,0,1,1])}))
    f=dict(kind='floor_line',hue=mapped.edges[1]['hue'],endpoints=[[1,-.5],[1,.5]],normal=[-1,0])
    p=np.array([[0.,0.,0.],[.2,.2,.1]])
    field=NS(distances=lambda xy:np.zeros(xy.shape[:-1]))
    parts,_=m.log_components(field,mapped,p,Measurement(np.empty((0,2)),[f]),is_converged=False)
    assert np.all(parts[0]==0)
    assert np.array_equal(parts[1],np.log(landmark_likelihood(mapped,p,[f])))


def test_frozen_gates_and_no_s55_s56_composition():
    root=Path('experiments/2026-10-06-s2-realism')
    c=json.loads((root/'sensor-consistency-criteria.json').read_text())
    assert c['seeds']==[1051,1053,1054,1056,1057,1058,1059,1060,1061]
    assert c['gates']['nees_exceed_fraction_lte']==.2 and c['gates']['unflagged_gt_25cm_lte']==0
    assert m.PARAMS==dict(sigma_hit=.2,z_hit=.5,z_rand=.5,max_beams=60,laser_likelihood_max_dist=2.,range_max_m=100.)
    assert m.BEAM==dict(distance=.5,threshold=.3,error_threshold=.9,converged_distance=.5)
    source=Path(m.__file__).read_text()
    assert 'sensor_consistency import' not in source and 'eval_only' not in source


def test_real_v133_stack_attachment_is_private_and_preserves_floor_features():
    from harness import zone_solo_cyan_contract_v106 as c
    from harness.zone_solo_cyan_bias_tempering import closure
    from scripts.run_s2_landmarks_dev import runtime_factory
    bundle=json.loads(Path('tests/fixtures/s2_ci/v133-bundle.json').read_text())
    runtime=runtime_factory(bundle)(c.hp.resolve(c.MAP_ID)[0],c.ROOT/c.CALIBRATION,c.CALIBRATION_SHA,**bundle['task'])
    try:
        old=closure(runtime.pose.provider.loc._pf.update_obs)['selected']
        assert m.attach(runtime,sensor_beamskip=m.OPTION) is runtime
        new=closure(runtime.pose.provider.loc._pf.update_obs)['selected']
        assert new is not old and new.__globals__ is not old.__globals__
        assert new.__globals__['resample'] is old.__globals__['resample']
        before=old.__globals__['endpoints'];after=new.__globals__['endpoints']
        assert after.__globals__['floor_features'] is before.__globals__['floor_features']
        assert after.__globals__['door_features'] is before.__globals__['door_features']
        assert after.__globals__['endpoints'] is m.prob_endpoints
        assert runtime.record()['sensor_beamskip']['gt_inputs'] is False
        with pytest.raises(ValueError):m.attach(runtime,sensor_beamskip=m.OPTION)
    finally:runtime.close()
