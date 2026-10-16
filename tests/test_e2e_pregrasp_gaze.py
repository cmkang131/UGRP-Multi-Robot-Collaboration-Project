import math
import numpy as np
import pytest
from harness.e2e_pregrasp_gaze import pan,fresh_gaze,recover
from harness.servo_camera_fk import transform_from_commands
from harness.owncam_pair_beam_v2 import pose_of
from tests.test_e2e_align_progress import setup_transport


def test_pan_sign_tracks_body_bearing_under_actual_commanded_camera_fk():
    pose=pose_of('search');(_,r0),_=transform_from_commands(pose,camera_pose='servo_fk_v1')
    next_pan=pan([0,0,0],[1,.4],1500)
    assert next_pan==1580
    pose[6]=next_pan;(_,r1),_=transform_from_commands(pose,camera_pose='servo_fk_v1')
    assert math.atan2(r1[1,2],r1[0,2])>math.atan2(r0[1,2],r0[0,2])
    value=1500
    for _ in range(30):value=pan([0,0,0],[-1,1],value)
    assert value==2167


def test_gaze_is_default_off_and_private_frame_invariant():
    tr=setup_transport(dev_light=True)
    assert fresh_gaze(tr,'r1',[0,1])==[]
    tr.pregrasp_gaze='own_bearing_v1'
    from harness.self_odom_grid import transform
    p=np.array([-.3,.2,.4]);g=np.array([.2,1.]);tf=[2,-4,1.2]
    q=np.r_[transform([p[:2]],tf)[0],p[2]+tf[2]]
    assert pan(p,g,1500)==pan(q,transform([g],tf)[0],1500)


def test_real_pulse_rotates_to_last_observed_grip_after_one_camera_cycle():
    tr=setup_transport(dev_light=True,search_bearing='last_seen_v1');r=tr.robots['r1'];r.carrier_approach={}
    r.goal.explorer.local_pose=np.array([-3.10657,-.86285,-1.56234])
    state={'search_started':120.,'grip':np.array([-3.45063,-1.45008])}
    assert recover(tr,'r1',125.,state) is None
    fine,actions=recover(tr,'r1',127.,state)
    assert not fine and actions[0]['kind']=='mecanum'
    assert actions[0]['turn']<0 and actions[0]['forward']==0 and actions[0]['left']==0
    assert actions[0]['duration_s']==.1
    assert r.carrier_approach['source']=='own_rgb_last_seen_and_own_command_odometry'
    tr.search_bearing='off';assert recover(tr,'r1',200.,state) is None


def test_fresh_own_frame_adds_gaze_to_actual_pregrasp_dispatch():
    from harness.e2e_carrier_approach import advance
    tr=setup_transport(dev_light=True,pregrasp_recovery='bounded_search_v1',pregrasp_gaze='own_bearing_v1')
    tr.robots['r1'].goal.explorer.local_pose=np.array([-1.,-.3,0.])
    _,actions=advance(tr,'r1',2.)
    assert actions[0]['kind']=='look' and actions[0]['pan_pulse']>1500
    assert actions[-1]['kind']=='mecanum'


def test_bundle_requires_both_own_observation_toggles():
    from scripts.run_e2e_ownmap_live import bundle
    from tests.test_e2e18 import options,ROOT
    from harness.e2e_runtime_registration import require_current
    kw=dict(speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1',camera_load='nominal_command_v1',route_tokens='1600_v1',protocol_progress='stage_retry_v1',route_cost='bounded_morphology_v1',align_progress='dev_continue_v1',pregrasp_recovery='bounded_search_v1')
    b=bundle('a'*40,61004,'study_gemma4_31b_v1',**options(),**kw,pregrasp_gaze='own_bearing_v1',search_bearing='last_seen_v1',pulse_admission='finish_active_v1')
    require_current(b,ROOT);assert b['execution_bundle_id']=='e2e18-v230'
    assert 'harness/e2e_pregrasp_gaze.py' in b['source_sha256']
    b['e2e_options']['search_bearing']='off'
    with pytest.raises(ValueError):require_current(b,ROOT)
