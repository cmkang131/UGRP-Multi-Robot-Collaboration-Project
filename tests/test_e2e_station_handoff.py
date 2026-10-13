import copy
import math
from types import SimpleNamespace

import numpy as np
import pytest
from harness import e2e_station_handoff as m
from harness.e2e_carrier_approach import advance
from harness.e2e_station_heading import control
from tests.test_e2e_fine_entry import recorded


def aligned_station(mode):
    tr, r = recorded('off')
    tr.approach_commit='memory60_view_v1';tr.station_heading='station20_v1'
    tr.station_handoff=mode
    r.beam=None
    # r49 v265 r1 at 591.2 SIM: .089215m XY remains, final yaw -.001810rad.
    # A remaining leftward position target makes legacy pursuit undo that yaw.
    tr.approach['r2']=dict(station=np.array([0.,.089215138161288,-.0018103768203578952]),
        grip=np.array([.203,.089]),basis=dict(yaw_rad=0.),last_seen=1.)
    return tr, r


@pytest.mark.parametrize('mode',m.OPTIONS)
def test_reached_station_yaw_does_not_restart_opposite_path_turn(mode):
    old, _ = aligned_station('off')
    fine, actions=advance(old,'r2',2.)
    assert not fine and actions[0]['turn']>0
    tr,r=aligned_station(mode)
    assert advance(tr,'r2',2.)==(False,[dict(kind='hold')])
    assert r.carrier_approach['status']=='station_perception_'+mode
    assert not tr.aligned


def test_hysteresis_budget_and_new_observation_retry():
    events=[];tr=SimpleNamespace(station_handoff='hold_v1',event=lambda *a,**k:events.append((a,k)))
    state=dict(last_seen=0.);diag=dict(distance_m=.09,heading_error_rad=.05)
    assert m.active(tr,'r1',1.,state,diag)
    diag['heading_error_rad']=.10
    assert m.active(tr,'r1',2.,state,diag)
    assert not m.active(tr,'r1',13.1,state,diag)
    diag['heading_error_rad']=.01
    assert not m.active(tr,'r1',14.,state,diag)
    state['last_seen']=14.
    assert m.active(tr,'r1',14.,state,diag)
    diag['heading_error_rad']=.16
    assert not m.active(tr,'r1',14.4,state,diag)
    assert 'station_handoff' not in state


def test_station_memory_expiry_and_radius_release_handoff():
    tr,r=aligned_station('hold_v1');state=tr.approach['r2']
    diag=dict(distance_m=.09,heading_error_rad=.01)
    assert control(tr,'r2',2.,state,diag)=='observe'
    diag['distance_m']=.24
    assert control(tr,'r2',2.4,state,diag)=='observe'
    diag['distance_m']=.26
    assert control(tr,'r2',2.8,state,diag) is None
    assert 'station_handoff' not in state
    diag['distance_m']=.09
    assert control(tr,'r2',3.,state,diag)=='observe'
    assert control(tr,'r2',62.,state,diag) is None
    assert 'station_handoff' not in state


def test_pan_only_search_retains_inspect_and_never_marks_ready():
    tr,r=aligned_station('pan_v1');advance(tr,'r2',2.)
    original=dict(r.servo)
    r.last_obs['frame_id']+=1
    assert advance(tr,'r2',4.4)==(False,[dict(kind='hold')])
    assert tr.queue and all(a['kind']=='look' for _,_,a in tr.queue)
    assert tr.queue[-1][2]['pan_pulse']==1250
    assert r.servo==original and not tr.aligned


def test_fresh_assigned_band_can_transfer_to_existing_fine_servo():
    from harness.e2e_fine_entry import install,OPTION
    tr,r=recorded('off');install(tr,OPTION)
    tr.approach_commit='memory60_view_v1';tr.station_heading='station20_v1';tr.station_handoff='hold_v1'
    axis=.04;u=np.array([math.cos(axis),math.sin(axis)]);grip=np.array([.22,.02])
    r.beam.update(grip_base_m=grip.tolist(),axis_heading_rad=axis,pose_own_m=[*(grip+.27*u),axis])
    r.goal.entities['B']={'center_m':(-3*u).tolist()}
    assert advance(tr,'r2',2.)==(True,[])
    assert any(e['event']=='own_station_perception_handoff' for e in tr.events)
    assert not tr.aligned


def test_default_off_parent_and_parameters():
    assert not m.active(object(),'r1',0.,{}, {})
    for mode,version in m.VERSIONS.items():
        b=dict(execution_bundle_id='e2e18-v268',e2e_options={});old=copy.deepcopy(b)
        assert m.compose(b,'off')==() and b==old
        m.compose(b,mode);assert b['execution_bundle_id']==f'e2e18-v{version}'
        with pytest.raises(ValueError):m.compose(b,mode)
