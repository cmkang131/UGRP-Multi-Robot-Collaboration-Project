import copy
from types import SimpleNamespace
import numpy as np
import pytest
from harness import e2e_approach_heading as m
from harness.e2e_rpp_path import command
from harness.self_pulse_rotation import selected_model
from tests.test_e2e_fine_view import recorded
from harness.e2e_carrier_approach import advance


@pytest.mark.parametrize('mode',m.OPTIONS)
def test_recorded_corner_bearing_turns_before_straight_pulse(mode):
    # v260/s61006/r46 at 276 SIM: goal 0.312m, body error and bearing
    # below the original 0.785rad cutoff, but the proposed sweep is blocked.
    point=[.22481150234393993,-.21663224629935954]
    plan=dict(coordinate_frame='r2/own_odom',path_m=[[0.,0.],point],status='goal_approach',heading_rad=1.)
    profiles=selected_model('s2_pulse_v122_rotL_v1')['profiles']
    old,_=command(plan,[0.,0.,0.],profiles,robot_id='r2')
    assert old['forward']>0 and old['turn']==0
    new,info=command(plan,[0.,0.,0.],profiles,robot_id='r2',**m.kwargs(SimpleNamespace(approach_heading=mode)))
    assert new['forward']==0 and new['turn']<0 and new['duration_s']==.1
    assert info['phase']=='rotate_path'
    plan['path_m']=[[0.,0.],[.02,0.]];plan['heading_rad']=0.
    assert command(plan,[0.,0.,0.],profiles,robot_id='r2',rotate_min_angle=.1)[0]==dict(kind='hold')


def test_actual_pregrasp_path_passes_explicit_threshold_without_promoting_fine(monkeypatch):
    import harness.e2e_carrier_approach as approach
    tr,r=recorded('off');tr.approach_heading='path10_v1'
    r.goal.explorer.local_pose+=np.array([.6,0.,0.])
    calls=[]
    def follower(*args,**kw):
        calls.append(kw)
        return dict(kind='hold'),dict(phase='test_path')
    monkeypatch.setattr(approach,'rpp_command',follower)
    fine,_=advance(tr,'r2',2.)
    assert not fine and calls and calls[0]['rotate_min_angle']==.1


def test_default_off_and_registration_preserve_parent():
    b={'execution_bundle_id':'e2e18-v260','e2e_options':{}};saved=copy.deepcopy(b)
    assert m.kwargs(object())=={} and m.compose(b,'off')==() and b==saved
    m.compose(b,'path20_v1');assert b['execution_bundle_id']=='e2e18-v262'
    with pytest.raises(ValueError):m.compose(b,'path10_v1')
