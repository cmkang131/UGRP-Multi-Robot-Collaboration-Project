import copy
import numpy as np
import pytest
from harness import e2e_fine_view as m, e2e_approach_commit as viewing
from harness.e2e_carrier_approach import advance
from harness.owncam_pair_beam_v2 import pose_of
from tests.test_e2e_align_progress import setup_transport


def recorded(mode):
    tr=setup_transport(dev_light=True,pregrasp_recovery='bounded_search_v1')
    tr.approach_commit='memory60_view_v1';tr.fine_view=mode
    r=tr.robots['r2'];r.goal.explorer.local_pose=np.array([1.0320081357,.0034172709,-3.0900094792])
    r.beam.update(pose_own_m=[.5450964281,-.0248475678,.0186243589],
                  grip_base_m=[.7575747667,-.0057753406],axis_heading_rad=3.1086338381)
    r.goal.entities['B']={'center_m':[2.,0.]}
    return tr,r


@pytest.mark.parametrize('mode',m.OPTIONS)
def test_recorded_far_band_at_reached_station_requests_assigned_near_view(mode):
    old,r=recorded('off');fine,actions=advance(old,'r2',2.)
    assert not fine and r.carrier_approach['camera']=='search' and not r.carrier_approach['correct_end']
    tr,r=recorded(mode);fine,actions=advance(tr,'r2',2.)
    assert not fine and r.carrier_approach['camera']=='inspect'
    assert r.carrier_approach['status']=='camera_settle' and tr.queue
    # Merely seeing the other band's fresh image must never enable fine/grasp.
    r.servo=pose_of('inspect');tr.queue.clear();r.last_obs['frame_id']=11;r.beam['rgb']['t_sim']=3.
    fine,_=advance(tr,'r2',3.)
    assert not fine and not r.carrier_approach.get('correct_end')
    assert np.allclose(viewing.gaze_target(tr,'r2',True,tr.approach['r2']['grip']),tr.approach['r2']['grip'])


def test_staging_hysteresis_and_stale_frame_do_not_promote_a_grasp():
    tr,r=recorded('stage08_v1');state={'station':np.array([1.,0.,0.])}
    r.goal.explorer.local_pose=np.array([1.07,0.,0.]);assert m.active(tr,'r2',state)
    r.goal.explorer.local_pose[0]=1.15;assert m.active(tr,'r2',state)
    r.goal.explorer.local_pose[0]=1.17;assert not m.active(tr,'r2',state)
    r.goal.explorer.local_pose[0]=1.10;assert not m.active(tr,'r2',state)
    r.beam=None;assert viewing.view(tr,'r2',state,False,.2)[0]=='inspect'
    assert r.beam is None


def test_registration_requires_exact_parent_and_default_does_not_mutate():
    b={'execution_bundle_id':'e2e18-v254','e2e_options':{}}
    before=copy.deepcopy(b);assert m.compose(b,'off')==() and b==before
    m.compose(b,'stage08_v1');assert b['execution_bundle_id']=='e2e18-v257'
    with pytest.raises(ValueError):m.compose(b,'stage20_v1')
