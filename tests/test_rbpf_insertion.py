"""Insertion lifecycle regression with deterministic match outcomes; no physics."""
import copy
import json
import numpy as np
import pytest
from harness.rbpf_insertion import install, OPTION
from harness.rbpf_motion_gate import install as motion_install, OPTION as MOTION
from harness.self_wall_memory_motion import SelfWallMemory
from harness.wall_confidence import confidence, weighted_insert
from harness.self_odom_grid import OdomGrid
from tests.test_self_map_prob import CORNER
from tests.test_wall_confidence import FEATURE, SEG


def grid(option=None, settle=None):
    g=SelfWallMemory('r1',self_map='odom_grid_v1',pose_correction='own_map_rbpf_v1',
        motion_model='s2_pulse_v122',wall_confidence='inverse_sensor_v1',
        self_map_options={'settle_s':settle}).self_map
    motion_install(g,rbpf_update=MOTION)
    return g if option is None else install(g,rbpf_insertion=option)


def observe(g,t,i,segments=CORNER,robot='r1'):
    return g.observe_contacts_confident(t=t,frame_id=i,robot_id=robot,segments=segments,
        features=[FEATURE]*len(segments),camera_xy=[0.,0.])


def admit(g):
    g.odom.driver._pose=np.array([1.,0.,0.])
    g.propagate([1.,0.,0.],np.array([.01,.01,.001]))


def test_off_preserves_bytes_rng_and_method_identity():
    a,b=grid(),grid('off')
    method=b._observe
    assert install(b) is b and b._observe==method
    for i,t in enumerate([0.,.2,1.2]):
        for g in (a,b):observe(g,t,i)
        assert json.dumps([a.export(),a.decisions,a.ledger])==json.dumps([b.export(),b.decisions,b.ledger])
        assert a.rng.bit_generator.state==b.rng.bit_generator.state


@pytest.mark.parametrize('reason',['low_overlap','search_boundary','high_residual'])
def test_failed_correction_still_registers_motion_pose_and_resets_gate(monkeypatch,reason):
    g=grid(OPTION)
    observe(g,0.,0)
    def failed(field,points,camera,prior,cov,rng,options):
        return prior.copy(),0.,dict(reason=reason,proposal='motion_fallback')
    monkeypatch.setattr('harness.rbpf_insertion.improved_proposal',failed)
    admit(g)
    observe(g,2.,1)
    event=g.decisions[-1]
    assert event['reason']==reason and event['status']=='rejected'
    assert event['inserted'] and event['inserted_particles']==30 and len(g.ledger)==2
    assert all(m.frames==2 for m in g.maps)
    assert g._motion_gate['processed']==2
    assert g._motion_gate['linear']==g._motion_gate['angular']==0
    assert event['insertion_reason']=='motion_fallback'
    frozen=(json.dumps(g.ledger),copy.deepcopy(g.rng.bit_generator.state))
    observe(g,2.2,2)
    assert g.decisions[-1]['reason']=='gmapping_motion_gate'
    assert json.dumps(g.ledger)==frozen[0] and g.rng.bit_generator.state==frozen[1]


def test_range_settle_duplicate_and_peer_filters_survive():
    g=grid(OPTION)
    observe(g,0.,0)
    before=json.dumps([g.export(),g.decisions])
    observe(g,0.,0)
    assert json.dumps([g.export(),g.decisions])==before
    with pytest.raises(ValueError,match='PEER'):observe(g,1.,1,robot='r2')
    observe(g,2.,2,segments=[[[4.,-.2],[4.,.2]]])
    assert g.decisions[-1]['reason']=='no_near_geometry' and len(g.ledger)==1
    fresh=grid(OPTION,settle=(1.,1.))
    observe(fresh,0.,0)
    assert fresh.decisions[-1]['reason']=='unsettled' and not fresh._motion_gate['processed']


def test_existing_range_variance_tempers_hit_and_carves_old_wall():
    near=confidence(SEG,[0,0],FEATURE,np.zeros((3,3)))
    far=confidence(SEG*3,[0,0],FEATURE,np.zeros((3,3)))
    assert far['sigma_range_m']>near['sigma_range_m'] and 0<far['weight']<near['weight']
    g=OdomGrid('r1')
    weighted_insert(g,[0,0],[SEG],[near['weight']])
    before=g.cells[(10,0)]
    weighted_insert(g,[0,0],[SEG*3],[far['weight']])
    assert g.cells[(10,0)]<before
    assert 0<g.cells[(30,0)]<before


def test_conflicting_rejection_policy_fails_in_both_orders():
    from harness.rbpf_rejection import install as rejection,OPTION as REJECTION
    with pytest.raises(ValueError,match='CONFLICTING'):install(grid(OPTION),rbpf_insertion=OPTION)
    with pytest.raises(ValueError,match='CONFLICTING'):rejection(grid(OPTION),rbpf_rejection=REJECTION)
    with pytest.raises(ValueError,match='CONFLICTING'):install(rejection(grid(),rbpf_rejection=REJECTION),rbpf_insertion=OPTION)
    with pytest.raises(ValueError,match='REQUIRES'):install(OdomGrid('r1'),rbpf_insertion=OPTION)
