import json
import math
import numpy as np
import pytest
from harness.rbpf_composition import install, OPTION, SEARCH
from harness.rbpf_rejection import install as selective, OPTION as SELECTIVE
from harness.rbpf_manhattan import install as manhattan, OPTION as MANHATTAN
from harness.self_map_rbpf import improved_proposal, GridField
from harness.self_map_csm import sample_segments, CSMOptions
from tests.test_rbpf_insertion import grid as base_grid, observe, admit
from tests.test_rbpf_rejection import fake_match
from tests.test_self_map_prob import CORNER


def grid():
    return selective(base_grid(),rbpf_rejection=SELECTIVE)


def test_off_bytes_rng_and_method_identity():
    a,b=grid(),install(grid())
    for i,t in enumerate([0.,.2,2.]):
        for g in (a,b):
            if i==2:admit(g)
            observe(g,t,i)
        assert json.dumps([a.export(),a.decisions,a.ledger])==json.dumps([b.export(),b.decisions,b.ledger])
        assert a.rng.bit_generator.state==b.rng.bit_generator.state


def test_rejection_inserts_but_neither_weights_nor_resamples(monkeypatch):
    g=install(grid(),rbpf_composition=OPTION)
    observe(g,0.,0)
    g.weights[:]=.001;g.weights[0]=1-.001*29;g.log_weights=np.log(g.weights)
    saved=g.weights.tobytes(),g.log_weights.tobytes()
    monkeypatch.setattr('harness.rbpf_rejection.improved_proposal',fake_match('low_overlap'))
    admit(g);observe(g,2.,1)
    d=g.decisions[-1]
    assert d['status']=='rejected' and d['inserted_particles']==30
    assert len(g.ledger)==2 and all(m.frames==2 for m in g.maps)
    assert not d['resampled'] and not d['sensor_weight_update']
    assert (g.weights.tobytes(),g.log_weights.tobytes())==saved


def test_acceptance_and_manhattan_axes_follow_only_neff_resampling(monkeypatch):
    g=manhattan(install(grid(),rbpf_composition=OPTION),yaw_prior=MANHATTAN)
    observe(g,0.,0)
    axes=g._manhattan_axes.copy()
    g.weights[:]=0;g.weights[:15]=1/15
    assert g.resample_if_needed()[1] is None
    g.weights[:]=0;g.weights[4]=1
    _,parents=g.resample_if_needed()
    assert parents==[4]*30
    np.testing.assert_array_equal(g._manhattan_axes,np.full(30,axes[4]))
    monkeypatch.setattr('harness.rbpf_rejection.improved_proposal',fake_match('improved_proposal',0.))
    admit(g);observe(g,2.,1)
    assert g.decisions[-1]['inserted_particles']==30
    assert g.export()['yaw_prior']==MANHATTAN and g.export()['rbpf_insertion']=='gmapping_range_v1'


def test_wider_candidates_recover_synthetic_rotation_without_gt_interface():
    points=sample_segments(np.asarray(CORNER))
    field=GridField(points)
    prior=np.array([0.,0.,math.radians(15.)])
    cov=np.diag([.02,.02,math.radians(30.)**2])
    args=(field,points,np.zeros(2),prior,cov)
    narrow=improved_proposal(*args,np.random.default_rng(7),CSMOptions())
    wide=improved_proposal(*args,np.random.default_rng(7),CSMOptions(),yaw_window_deg=20.)
    assert narrow[2]['reason']!='improved_proposal'
    assert wide[2]['reason']=='improved_proposal'
    assert abs(wide[2]['proposal_mean'][2])<math.radians(2.)
    assert wide[2]['candidates']>narrow[2]['candidates']
    with pytest.raises(ValueError):
        improved_proposal(*args,np.random.default_rng(7),CSMOptions(),yaw_window_deg=21.)


def test_search_and_composition_do_not_modify_another_grid():
    a,b=grid(),grid()
    install(a,rbpf_composition=OPTION,rbpf_search=SEARCH)
    assert hasattr(a,'_selective_proposal') and not hasattr(b,'_selective_proposal')
    assert a.export()['rbpf_search']==SEARCH
    with pytest.raises(ValueError):install(a,rbpf_composition=OPTION)
    with pytest.raises(ValueError):install(b,rbpf_search=SEARCH)
    with pytest.raises(ValueError):install(manhattan(b,yaw_prior=MANHATTAN),rbpf_composition=OPTION)


def test_range_duplicate_peer_and_settle_checks_remain():
    g=install(grid(),rbpf_composition=OPTION)
    observe(g,0.,0)
    before=json.dumps([g.export(),g.decisions,g.ledger])
    observe(g,0.,0)
    assert json.dumps([g.export(),g.decisions,g.ledger])==before
    with pytest.raises(ValueError,match='PEER'):observe(g,1.,1,robot='r2')
    observe(g,2.,2,segments=[[[4.,0.],[4.,1.]]])
    assert not g.decisions[-1]['inserted']
    g.settle_s=(1.,1.);g.odom.has_servo=False
    observe(g,3.,3)
    assert g.decisions[-1]['reason']=='unsettled'
