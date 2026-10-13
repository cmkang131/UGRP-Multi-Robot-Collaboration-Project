import copy
import math
import numpy as np
import pytest
from harness import e2e_acquire_standoff as m
from harness import e2e_pregrasp_acquire as acq
from harness.e2e_arm_clearance import Clearance
from tests.test_e2e_align_progress import setup_transport


def lost(center=(-.6,0.,0.),standoff='v1',dev_light=True):
    tr=setup_transport(pregrasp_acquire=acq.OPTION,dev_light=dev_light)
    install_guards(tr)
    r=tr.robots['r2'];r.last_beam=copy.deepcopy(r.beam);r.last_beam['pose_own_m']=list(center)
    r.beam=None;r.goal.explorer.map_to_odom=np.zeros(3);r.goal.explorer.grid=None
    m.install(tr,standoff)
    return tr,r


def install_guards(tr):
    import harness.public_navigation_unknown as u,harness.public_navigation.follower as f
    tr._guards=(u.from_observed_grid,f.projected_clear)


@pytest.fixture(autouse=True)
def stub_costmap(monkeypatch):
    import harness.public_navigation_unknown as u,harness.public_navigation.follower as f
    monkeypatch.setattr(u,'from_observed_grid',lambda *a:None)
    monkeypatch.setattr(f,'projected_clear',lambda *a:True)


def test_defaults_are_off_and_scan_timing_unchanged():
    tr=setup_transport(pregrasp_acquire=acq.OPTION)
    assert m.scan_timing(tr)==(2.,3.)
    tr,r=lost(standoff='off')
    state={};out=acq.acquire(tr,'r2',20.,state,r.goal.entities['B'])
    assert state['acquisition']['phase']!='standoff' and not any(e['event'].startswith('own_beam_lost_standoff') for e in tr.events)


def test_close_loss_backs_off_with_own_reverse_pulses_then_faces_remembered_side():
    tr,r=lost();state={};B=r.goal.entities['B']
    fine,[cmd]=acq.acquire(tr,'r2',20.,state,B)
    assert cmd['kind']=='mecanum' and cmd['forward']<0 and state['acquisition']['phase']=='standoff'
    assert [e['event'] for e in tr.events].count('own_beam_lost_standoff_begin')==1
    # gate holds until a new settled frame; own odometry (not truth) decides distance.
    assert acq.acquire(tr,'r2',20.1,state,B)[1]==[dict(kind='hold')]
    r.goal.explorer.local_pose=np.array([-1.32,0.,0.])
    r.last_obs={'frame_id':11,'sim_time':21.}
    _,acts=acq.acquire(tr,'r2',21.,state,B)
    a=state['acquisition']
    assert a['phase']=='turn' and acts==[dict(kind='hold')]
    end=[e for e in tr.events if e['event']=='own_beam_lost_standoff_end'][0]
    assert end['reason']=='distance' and end['own_odom_displacement_m']>=.3
    assert a['yaw']==pytest.approx(0.,abs=1e-9)  # remembered side is ahead (+x)
    acq.acquire(tr,'r2',21.5,state,B)
    assert a['phase']in('turn','scan') and [e['event'] for e in tr.events].count('own_beam_lost_standoff_begin')==1


def test_far_loss_or_mapping_scan_does_not_back_off():
    tr,r=lost(center=(3.,0.,0.));state={}
    acq.acquire(tr,'r2',20.,state,r.goal.entities['B'])
    assert state['acquisition']['phase']!='standoff'
    tr,r=lost();state={}
    acq.acquire(tr,'r2',20.,state,None)
    assert state['acquisition']['phase']!='standoff'


def test_pulse_cap_and_collision_guard_outside_dev(monkeypatch):
    tr,r=lost(dev_light=False);state={}
    import harness.public_navigation.follower as f
    monkeypatch.setattr(f,'projected_clear',lambda *a:False)
    acq.acquire(tr,'r2',20.,state,r.goal.entities['B'])
    assert state['acquisition']['phase']!='standoff'
    assert [e for e in tr.events if e['event']=='own_beam_lost_standoff_end'][0]['reason']=='collision_guard'


def test_fast_scan_shortens_view_period_and_turn_cap():
    tr=setup_transport(pregrasp_acquire=acq.OPTION);tr.acquire_scan_fast='v1'
    assert m.scan_timing(tr)==(1.2,2.)


def test_align_skip_near_own_station_and_repeat_cap_only_when_enabled():
    tr=setup_transport(pregrasp_acquire=acq.OPTION);tr.state='align'
    pose=np.array([-1.,0.,0.])
    tr.approach['r2']={'station':np.array([-1.2,0.,0.])}
    assert m.skip_reason(tr,'r2',pose,[],'off') is None
    assert m.skip_reason(tr,'r2',pose,[],m.SKIP)=='near_own_station'
    tr.approach['r2']={'station':np.array([-3.,0.,0.])}
    assert m.skip_reason(tr,'r2',pose,[pose[:2]],m.SKIP) is None
    assert m.skip_reason(tr,'r2',pose,[pose[:2],pose[:2]+.1],m.SKIP)=='repeat_location_cap'
    tr.state='mapping'
    assert m.skip_reason(tr,'r2',pose,[pose[:2]]*3,m.SKIP) is None


def test_compose_registered_combinations_only():
    b=lambda:dict(e2e_options={},execution_bundle_id='e2e18-v273')
    x=b();assert m.compose(x,'v1')==('configs/simulation_workflows.d/e2e18_v295.json',) and x['execution_bundle_id']=='e2e18-v295'
    x=b();m.compose(x,'v1','v1','v1');assert x['execution_bundle_id']=='e2e18-v296' and x['workflow_version']=='7.189.0'
    assert m.compose(b())==()
    for key in (('off','v1','off'),('v1','v1','off'),('v1','off','v1')):
        with pytest.raises(ValueError):m.compose(b(),*key)
    with pytest.raises(ValueError):m.compose(dict(e2e_options={},execution_bundle_id='e2e18-v275'),'v1')


def test_clearance_defer_wiring_skips_only_when_enabled_and_logs_sensor_evidence():
    from harness.owncam_pair_beam_v2 import pose_of
    tr=setup_transport(pregrasp_acquire=acq.OPTION);tr.state='align'
    r=tr.robots['r2'];r.servo={**pose_of('search'),1:2000};r.now=0.;r.wall_segments=[]
    tr.approach['r2']={'station':np.array([-1.2,0.,0.])}
    path=[({**pose_of('inspect'),1:2000},.3,.6)]
    c=Clearance('range_wall_v1');tr.events=getattr(tr,'events',[])
    tr.event=lambda now,event,**kw:tr.events.append(dict(t=now,event=event,**kw))
    c.align_skip='v1'
    assert c.defer(tr,'r2',1.,path) is False
    assert [e['event'] for e in tr.events]==['own_arm_clearance_align_skipped']
    assert tr.events[0]['reason']=='near_own_station' and 'range_status' in tr.events[0]
    c2=Clearance('range_wall_v1')
    assert c2.align_skip=='off'
