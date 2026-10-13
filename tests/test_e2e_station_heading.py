import copy
from types import SimpleNamespace
import pytest
from harness import e2e_station_heading as m
from harness.e2e_carrier_approach import advance
from tests.test_e2e_fine_entry import recorded


def test_recorded_near_goal_rotates_toward_grasp_heading_instead_of_orbiting():
    # r44 v259 r2: XY error 5.85cm but final axis +.456rad. Chasing
    # the tiny remaining XY vector turns right, away from the grasp heading.
    outcomes={}
    for mode in ('off',*m.OPTIONS):
        tr,r=recorded('off');tr.station_heading=mode;tr.approach_commit='memory60_view_v1'
        fine,actions=advance(tr,'r2',2.)
        turn=next(a['turn'] for a in actions if a['kind']=='mecanum')
        outcomes[mode]=turn
        assert not fine and not tr.aligned
        if mode!='off':assert r.carrier_approach['status']=='rotate_station_heading'
    assert outcomes['off']<0 and outcomes['station10_v1']>0 and outcomes['station20_v1']>0


def test_turn_budget_memory_expiry_and_settled_new_observation():
    events=[];tr=SimpleNamespace(station_heading='station20_v1',approach_commit='memory60_view_v1',event=lambda *a,**k:events.append((a,k)))
    state={'station':[0,0,0], 'last_seen':0.}
    diag=dict(distance_m=.15,heading_error_rad=.8)
    assert m.control(tr,'r1',1.,state,diag)=='rotate'
    assert m.control(tr,'r1',22.,state,diag) is None
    assert state['station_heading_attempt']['exhausted']
    assert m.control(tr,'r1',61.,state,diag) is None
    assert 'station_heading_attempt' not in state
    state.update(last_seen=62.,progress_watch={'since':0.},motion_until=62.1)
    assert m.control(tr,'r1',62.,state,diag)=='rotate'
    diag['heading_error_rad']=.02
    assert m.control(tr,'r1',62.2,state,diag)=='settle'
    assert 'progress_watch' not in state
    assert m.control(tr,'r1',62.6,state,diag) is None


def test_default_off_composition_and_radius_bound():
    assert m.control(object(),'r1',0.,{}, {}) is None
    b=dict(execution_bundle_id='e2e18-v264',e2e_options={});old=copy.deepcopy(b)
    assert m.compose(b,'off')==() and b==old
    m.compose(b,'station10_v1');assert b['execution_bundle_id']=='e2e18-v265'
    with pytest.raises(ValueError):m.compose(b,'station20_v1')
    tr=SimpleNamespace(station_heading='station10_v1',approach_commit='memory60_view_v1')
    assert m.control(tr,'r1',2.,dict(station=[0,0,0],last_seen=2.),dict(distance_m=.15,heading_error_rad=.8)) is None
