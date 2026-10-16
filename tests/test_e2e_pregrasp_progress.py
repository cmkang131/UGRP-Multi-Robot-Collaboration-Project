import numpy as np
from harness.e2e_pregrasp_progress import step,OPTION
from harness.e2e_carrier_approach import advance
from harness.e2e_pregrasp_gaze import recover
from tests.test_e2e_align_progress import setup_transport


def fixture():
    tr=setup_transport(dev_light=True,pregrasp_progress=OPTION,pregrasp_recovery='bounded_search_v1',search_bearing='last_seen_v1')
    for r in tr.robots.values():r.translation_commands=0;r.carrier_approach={}
    return tr,tr.robots['r1'],{}


def test_issued_motion_without_own_progress_backs_up_turns_then_replans():
    tr,r,state=fixture()
    assert step(tr,'r1',0.,state,1.) is None
    for t in range(1,8):
        r.translation_commands+=1;assert step(tr,'r1',float(t),state,1.) is None
    r.translation_commands+=1
    fine,actions=step(tr,'r1',8.,state,1.)
    assert not fine and actions[0]['forward']<0 and actions[0]['duration_s']==.1
    assert not actions[0]['left'] and not actions[0]['turn']
    r.goal.explorer.local_pose[0]-=.13
    step(tr,'r1',8.4,state,1.)
    assert state['progress_watch']['phase']=='turn'
    _,actions=step(tr,'r1',8.8,state,1.)
    assert actions[0]['turn']!=0 and actions[0]['forward']==0
    r.goal.explorer.local_pose[2]=state['progress_watch']['yaw']
    step(tr,'r1',9.2,state,1.)
    assert state['progress_watch']['phase'] is None and state['lost_nav_until']==14.2
    assert [e['event'] for e in tr.events]==['own_pregrasp_no_progress','own_pregrasp_replan']


def test_no_issued_translation_or_real_own_progress_never_triggers_backup():
    tr,r,state=fixture()
    for t in range(30):assert step(tr,'r1',float(t),state,1.) is None
    for t in range(30,60):
        r.translation_commands+=1;r.goal.explorer.local_pose[0]+=.04
        assert step(tr,'r1',float(t),state,1.) is None
    tr.pregrasp_progress='off';del r.translation_commands
    assert step(tr,'r1',99.,state,1.) is None


def test_lost_bearing_navigation_is_bounded_and_cannot_claim_visual_alignment():
    tr,r,state=fixture();advance(tr,'r1',2.)
    state=tr.approach['r1'];state.update(search_started=0.,grip=np.array([0.,0.]))
    r.goal.explorer.local_pose=np.array([-1.,0.,0.]);r.carrier_approach={}
    recover(tr,'r1',9.,state)
    assert state['lost_nav_until']==14.
    r.last_obs['frame_id']=11
    fine,actions=advance(tr,'r1',10.)
    assert not fine and actions[-1]['kind']=='mecanum'
    assert r.carrier_approach['would_stop_path_unavailable']
    r.last_obs['frame_id']=12
    fine,actions=advance(tr,'r1',15.)
    assert not fine and actions==[{'kind':'hold'}]
