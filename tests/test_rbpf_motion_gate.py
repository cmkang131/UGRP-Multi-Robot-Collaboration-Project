import copy
import json
import numpy as np
import pytest
from harness.rbpf_motion_gate import install,OPTION
from harness.self_map_rbpf import RaoBlackwellizedGrid
from harness.self_wall_memory_motion import SelfWallMemory
from tests.test_self_map_prob import CORNER,observe


def grid(option='off'):
    m=SelfWallMemory('r1',self_map='odom_grid_v1',pose_correction='own_map_rbpf_v1',
        motion_model='s2_pulse_v122',self_map_options={'settle_s':None})
    return m.self_map if option is None else install(m.self_map,rbpf_update=option)


def test_off_byte_golden_and_no_new_fields():
    a,b=grid(),grid(None)
    for i,t in enumerate([0.,.2,1.2]):
        for g in (a,b):observe(g,t,i)
        assert json.dumps([a.export(),a.decisions]).encode()==json.dumps([b.export(),b.decisions]).encode()
    assert 'rbpf_update' not in a.export()
    assert install(a) is a


def test_stationary_scans_cannot_consume_noise_or_collapse_particles():
    g=grid(OPTION);observe(g,0.,0)
    before=(copy.deepcopy(g.rng.bit_generator.state),g.poses.copy(),g.odom.covariance.copy(),
            json.dumps(g.ledger),copy.deepcopy(g.cells))
    for i in range(1,31):observe(g,i*.2,i)
    assert g._motion_gate['processed']==1 and g._motion_gate['skipped']==30
    assert g.rng.bit_generator.state==before[0]
    np.testing.assert_array_equal(g.poses,before[1])
    np.testing.assert_array_equal(g.odom.covariance,before[2])
    assert json.dumps(g.ledger)==before[3] and g.cells==before[4]
    assert g.resamples==0


@pytest.mark.parametrize('delta',[[1.,0.,0.],[0.,0.,.5]])
def test_source_motion_threshold_and_pending_command_covariance(delta):
    g=grid(OPTION);observe(g,0.,0)
    # Synthetic known odometry, never a simulator/GT input.
    g.odom.driver._pose=np.array(delta)
    g.propagate(delta,np.array([.01,.01,.001]))
    observe(g,2.,1)
    assert g._motion_gate['processed']==2 and g.decisions[-1]['matching_attempted']
    assert g._motion_gate['linear']==g._motion_gate['angular']==0


def test_gate_keeps_peer_duplicate_settle_and_neff_rules():
    g=grid(OPTION);observe(g,0.,0);observe(g,.2,1)
    before=json.dumps([g.export(),g.decisions]);observe(g,.2,1)
    assert json.dumps([g.export(),g.decisions])==before
    with pytest.raises(ValueError,match='PEER'):
        g.observe_contacts(t=1.,frame_id=2,segments=CORNER,camera_xy=[0,0],robot_id='r2')
    assert g.resample_if_needed()[1] is None
    g.weights[:]=0;g.weights[0]=1
    assert g.resample_if_needed()[1]==[0]*30
    fresh=install(RaoBlackwellizedGrid('r1'),rbpf_update=OPTION)
    observe(fresh,0.,0)
    assert fresh.decisions[-1]['reason']=='unsettled' and not fresh._motion_gate['processed']


def test_active_forecast_cannot_consume_real_gate_state_or_rng():
    from harness.active_information_gain import forecast
    g=grid(OPTION);observe(g,0.,0)
    frozen=json.dumps([g.export(),g.rng.bit_generator.state,g.decisions])
    assert np.isfinite(forecast(g,[[0,0],[.5,0]],seed=23)['utility'])
    assert json.dumps([g.export(),g.rng.bit_generator.state,g.decisions])==frozen
