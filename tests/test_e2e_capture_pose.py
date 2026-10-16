import copy
import math

import numpy as np
import pytest
from harness import e2e_capture_pose as m
from harness.e2e_carrier_approach import advance
from harness.e2e_fine_entry import install as fine_install, MPC
from tests.test_e2e_fine_entry import recorded


def premature(mode):
    tr,_=recorded('off');fine_install(tr,MPC)
    tr.approach_commit='memory60_view_v1';tr.station_heading='station20_v1'
    tr.station_handoff='pan_v1';m.install(tr,mode)
    r=tr.robots['r1'];r.goal.explorer.local_pose=np.zeros(3)
    # r50 v268 s61006 r1: full band but 18cm from its SE2 station.
    grip=np.array([.24358282785173083,.09295036050438306]);axis=-.41411
    u=np.array([math.cos(axis),math.sin(axis)])
    r.beam.update(grip_base_m=grip.tolist(),axis_heading_rad=axis,pose_own_m=[*(grip+.27*u),axis])
    r.goal.entities['B']={'center_m':(3*u).tolist()}
    from harness.owncam_pair_beam_v2 import pose_of
    r.servo=pose_of('inspect')
    return tr,r


@pytest.mark.parametrize('mode',m.OPTIONS)
def test_recorded_premature_local_servo_capture_waits_for_station(mode):
    old,_=premature('off');assert advance(old,'r1',2.)[0]
    tr,r=premature(mode)
    fine,actions=advance(tr,'r1',2.)
    assert not fine and not tr.aligned
    assert .17<r.carrier_approach['distance_m']<.20
    assert r.carrier_approach['status']=='navigate_pregrasp'
    assert actions[0]['kind']=='mecanum'


@pytest.mark.parametrize('mode',m.OPTIONS)
def test_near_recorded_station_keeps_fresh_fine_entry(mode):
    tr,r=recorded('off');fine_install(tr,MPC);m.install(tr,mode)
    assert advance(tr,'r2',2.)==(True,[])
    assert not tr.aligned


def test_tracking_pan_requires_new_settled_own_frame_before_base_motion():
    tr,r=premature('pose08_track_v1');s=tr.align['r1']
    grip=[.2594485822838446,.024014262380455485];heading=-.63897
    r.servo[6]=1644;obs=dict(frame_id=444,sim_time=2.,sha256='a'*64)
    phase,pan=s.observe(2.,obs,r.servo,grip,heading)
    assert phase=='pan' and 1300<=pan<=1700 and abs(pan-1644)>=24
    assert not s.audit[-1]['plan']['ready'] and not tr.aligned
    assert tr.approach['r1']['gaze_settle_until']==2.75
    r.servo[6]=pan
    assert s.observe(2.8,obs,r.servo,grip,heading)==('wait',None)
    assert s.observe(2.4,dict(obs,frame_id=445,sim_time=2.4),r.servo,grip,heading)==('wait',None)
    phase,value=s.observe(2.8,dict(obs,frame_id=446,sim_time=2.8),r.servo,grip,heading)
    assert phase=='base' and value['kind']=='mecanum'


def test_tracking_never_skips_the_two_fresh_ready_receipts():
    from harness.zone_s3_coarse_fine import arm
    tr,r=premature('pose08_track_v1');s=tr.align['r1'];r.servo[6]=1500
    grip=[arm.MOUNT_X_M+.155,-.006];obs=dict(frame_id=1,sim_time=2.)
    assert s.observe(2.,obs,r.servo,grip,0.)==('wait',None)
    assert s.observe(2.1,obs,r.servo,grip,0.)==('wait',None)
    phase,plan=s.observe(2.4,dict(frame_id=2,sim_time=2.4),r.servo,grip,0.)
    assert phase=='ready' and plan['ready']


def test_default_off_radius_and_parent_contract():
    tr=object();assert m.admit(tr,float('nan')) and m.radius(tr,.2)==.2
    m.install(tr,'off')
    for mode,version in m.VERSIONS.items():
        b=dict(execution_bundle_id='e2e18-v271',e2e_options={});old=copy.deepcopy(b)
        assert m.compose(b,'off')==() and b==old
        m.compose(b,mode);assert b['execution_bundle_id']==f'e2e18-v{version}'
        assert b['capture_pose_parameters']==m.parameters(mode)
        with pytest.raises(ValueError):m.compose(b,mode)
