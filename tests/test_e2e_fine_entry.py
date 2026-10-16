import copy
import math
import numpy as np
import pytest
from harness import e2e_fine_entry as m
from harness.e2e_carrier_approach import advance
from harness.owncam_pair_beam_v2 import pose_of
from tests.test_e2e_align_progress import setup_transport


def recorded(option):
    # r44 v259 s61007 r2, 1336.4 SIM: fresh assigned band, 5.85cm
    # staging error, .456rad axis. The .20rad handoff refused fine control.
    tr=setup_transport(dev_light=True,pregrasp_recovery='bounded_search_v1')
    m.install(tr,option);tr.fine_view='inspect60_v1'
    r=tr.robots['r2'];r.goal.explorer.local_pose=np.zeros(3)
    grip=np.array([.2120599225949866,.038360695576835406]);axis=.45641891760445585
    u=np.array([math.cos(axis),math.sin(axis)])
    r.beam.update(grip_base_m=grip.tolist(),axis_heading_rad=axis,
                  pose_own_m=[*(grip+.27*u),axis])
    r.goal.entities['B']={'center_m':(-3*u).tolist()}
    r.servo=pose_of('inspect')
    return tr,r


def test_recorded_r2_handoff_uses_fresh_servo_without_marking_ready():
    old,r=recorded('off');fine,_=advance(old,'r2',2.)
    assert not fine and r.carrier_approach['correct_end']
    tr,r=recorded(m.OPTION);fine,actions=advance(tr,'r2',2.)
    assert fine and not actions and not tr.aligned
    profile,plan=tr.align['r2'].proposal(r.beam['grip_base_m'],r.beam['axis_heading_rad'])
    assert not plan['ready'] and profile is not None
    assert profile['axis'] in ('forward','turn') and profile['duration_s']==.1


def test_existing_receding_search_escapes_recorded_one_step_dead_end():
    from harness.zone_s3_visual_pose_servo import transform
    outcomes={}
    for mode in (m.OPTION,m.MPC):
        tr,r=recorded(mode);grip,heading=r.beam['grip_base_m'],r.beam['axis_heading_rad']
        for count in range(20):
            profile,plan=tr.align['r2'].proposal(grip,heading)
            if profile is None:break
            grip,heading=transform(grip,heading,profile['mean_delta'])
        outcomes[mode]=(plan['ready'],count)
        assert not tr.aligned  # Prediction is never a physical ready receipt.
    assert outcomes=={m.OPTION:(False,2),m.MPC:(True,5)}


@pytest.mark.parametrize('change',['stale','far_end','too_wide','outside_capture'])
def test_capture_does_not_admit_stale_wrong_end_or_outside_workspace(change):
    tr,r=recorded(m.OPTION)
    if change=='stale':r.beam['rgb']['t_sim']=1.
    elif change=='far_end':r.goal.entities['B']['center_m']=(-np.array(r.goal.entities['B']['center_m'])).tolist()
    elif change=='too_wide':r.beam['grip_base_m'][1]=.11
    else:r.beam['axis_heading_rad']=.61
    assert not advance(tr,'r2',2.)[0]
    assert not tr.aligned


def test_off_parent_and_composition():
    b={'execution_bundle_id':'e2e18-v260','e2e_options':{}};saved=copy.deepcopy(b)
    assert m.compose(b,'off')==() and b==saved and m.heading_limit(object())==.2
    m.compose(b,m.OPTION);assert b['execution_bundle_id']=='e2e18-v263'
    with pytest.raises(ValueError):m.compose(b,m.OPTION)
    b={'execution_bundle_id':'e2e18-v262','e2e_options':{}}
    m.compose(b,m.MPC);assert b['execution_bundle_id']=='e2e18-v264'
