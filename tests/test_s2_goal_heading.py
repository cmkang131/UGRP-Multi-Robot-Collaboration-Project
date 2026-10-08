import copy,json,math
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from tests.s2_ci_inputs import portable_s2_inputs

pytestmark = pytest.mark.usefixtures("portable_s2_inputs")
from harness.zone_solo_cyan_goal_heading import install
from harness import zone_solo_cyan_look_before_move as look

def robot(yaw,x=0.):
    profiles=json.loads(Path('configs/s2_motion_v7_pulse_cal_v1.json').read_text())['profiles']
    calls=[]
    r=NS(state='search_move',last_report=NS(x_m=x,y_m=0.,yaw_rad=yaw,initialized=True,
        std_xy_m=.01,std_yaw_rad=.01,last_fix_t=1.),pulse_profiles=profiles,
        pose=NS(provider=NS(loc=NS(_pf=NS(load=NS(loaded=False))))),cal_rows=[],path=[[0.,0.]],path_goal=(0.,0.),
        soft=lambda *a:None,drive=lambda *a,**kw:(calls.append((a,kw)) or ([{'kind':'hold'}],False)))
    install(r,{})
    return r,calls

@pytest.mark.parametrize('yaw',[.08261211626731663,.06176017581013053])
def test_recorded_stalls_issue_rotation_not_lateral(yaw):
    r,calls=robot(yaw,x=.0159);actions,arrived=r.drive((0,0),10)
    assert not arrived and not calls and r.goal_heading['phase']=='heading'
    a=actions[0];assert a['turn']<0 and a['forward']==a['left']==0
    assert abs(yaw+r.pulse_profiles['0:turn:-0.35:0.10']['mean_delta'][2])<=.06

def test_stateful_latch_does_not_reenter_xy_when_rotation_drifts():
    r,calls=robot(.08,x=.02);r.drive((0,0),1)
    r.last_report.x_m=.04;r.last_report.yaw_rad=.075
    actions,arrived=r.drive((0,0),2)
    assert actions[0]['turn'] and not arrived and not calls
    r.last_report.yaw_rad=.02
    actions,arrived=r.drive((0,0),3)
    assert arrived and actions==[{'kind':'hold'}] and not calls
    r.drive((1,0),4);assert len(calls)==1 and r.goal_heading['phase']=='position'

def test_same_goal_already_reached_has_no_new_movement_or_threshold_relaxation():
    r,calls=robot(.06,x=.03);actions,arrived=r.drive((0,0),1)
    assert arrived and actions==[{'kind':'hold'}]
    r,calls=robot(.06001,x=.03001);r.drive((0,0),1)
    assert calls and r.goal_heading['phase']=='position'

def test_real_on_off_drive_and_conditional_admission():
    from harness import zone_s2_goal_heading_contract as c
    from harness import zone_solo_cyan_contract_v106 as legacy
    from scripts.run_s2_look_before_move import runtime_factory
    b=c.bundle('a'*40,1054,look_before_move=look.OPTION);c.require_execution(b)
    assert b['options']==c.old.bundle('a'*40,1054,look_before_move=look.OPTION)['options']
    with pytest.raises(ValueError):c.require_execution(c.bundle('a'*40,1053,look_before_move=look.OPTION))
    r=runtime_factory(b)(legacy.hp.resolve(legacy.MAP_ID)[0],legacy.ROOT/legacy.CALIBRATION,legacy.CALIBRATION_SHA,**b['task'])
    try:
        r.state='search_move';r.last_report=robot(.06176017581013053,x=.0148)[0].last_report
        actions,done=r.drive((0,0),5)
        assert actions[0]['turn'] and not done
        before=(r.drive,r.step,r.record,r.on_frames,r.on_command)
        assert look.attach(r) is r and before==(r.drive,r.step,r.record,r.on_frames,r.on_command)
    finally:r.close()
