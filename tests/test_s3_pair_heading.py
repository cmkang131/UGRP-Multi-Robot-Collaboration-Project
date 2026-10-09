"""Regression for the two saved v147 mixed-axis commands, no physics or truth."""
import math
from types import SimpleNamespace
import pytest
from harness import zone_s3_pair_heading as heading
from harness import zone_s3_no_prior_contract as contract
from harness.zone_solo_cyan_pulse_cal import profile_key


@pytest.fixture(scope='module')
def profiles():
    return contract.controller_config()['pulse_calibration']['profiles']


def test_off_identity():
    obj=object()
    assert heading.attach_driver(obj,None) is obj


@pytest.mark.parametrize('left,turn',[(.021079902479462034,0.),(.02109973424044228,.00009277001542615792)])
def test_saved_mixed_command_is_replaced_before_pulse_model(profiles,left,turn):
    old=dict(kind='mecanum',forward=.11575916745889646,left=left,turn=turn,duration_s=.15)
    with pytest.raises(ValueError,match='one axis'):profile_key(old,False)
    action,p,score=heading.approach_proposal(profiles,(1.,0.,0.),(2.,.5),(2.,.5),math.pi)
    assert action['turn']!=0. and action['forward']==action['left']==0.
    assert profiles[profile_key(action,False)]==p
    assert score['phase']=='rotate_path'


def test_lateral_is_only_final_task_alignment_not_intermediate_waypoint(profiles):
    action,p,score=heading.approach_proposal(profiles,(0.,0.,0.),(.01,.05),(2.,0.),0.)
    assert action.get('left',0)==0
    lateral=next(p for p in profiles.values() if not p['loaded'] and p['axis']=='left')
    from harness.zone_solo_cyan_pulse_cal import action_of
    a=action_of(lateral)
    for distance,alignment in [(.101,True),(.05,False)]:
        with pytest.raises(ValueError,match='final 0.10'):
            heading.validate_pulse(a,profiles,loaded=False,goal_distance=distance,alignment=alignment)
    heading.validate_pulse(a,profiles,loaded=False,goal_distance=.10,alignment=True)


def test_driver_waits_for_full_pulse_coast_and_delayed_feedback(profiles):
    calls=[]
    raw=dict(kind='mecanum',forward=.12,left=.08,turn=.1,duration_s=.15)
    d=SimpleNamespace(outcome=None,path=[(1.,1.)],goal=(1.,1.),goal_yaw=math.pi,
        tick=lambda t: calls.append(t) or [raw],
        loc=SimpleNamespace(estimate=lambda:dict(x=0.,y=0.,yaw=0.)))
    own=SimpleNamespace(pulse_profiles=profiles,last_report=SimpleNamespace(t_est=0.))
    heading.attach_driver(d,own,pair_heading=heading.OPTION)
    a=d.tick(1.)[0];p=profiles[profile_key(a,False)]
    assert d.tick(1.05)==[] and calls==[1.]
    assert d.tick(1.+p['duration_s'])==[dict(kind='hold')]
    end=1.+p['times'][-1]
    assert d.tick(end)==[]  # wall clock alone is insufficient
    own.last_report.t_est=end
    assert heading.moving(d.tick(end)[0]) and len(calls)==2


def test_actual_pair_driver_replaces_transit_mixture_and_keeps_dev_sigma(profiles):
    from tests.test_highpose_relook import executor, StuckPose
    from tests.test_zone_own_executor import Driver
    from harness.zone_own_driver import GuardedDriver
    from harness.zone_s3_dev_light import attach_driver, Audit
    own=executor('r2',StuckPose(sx=.2,sy=.2));fixture=Driver(own);fixture.frame()
    est=dict(initialized=True,x=-.9,y=-.85,yaw=0.,std_xy_m=.28,std_yaw_rad=.1,
        fix_age_s=.1,t=0.,last_fix_t=0.)
    loc=SimpleNamespace(predict_to=lambda t:est.update(t=t),estimate=lambda:dict(est))
    driver=GuardedDriver(loc,own.map,own.params,loaded=False,goal_xy=(-.4,-.6),
        door_xy=own.door_xy,initial_servo=dict(fixture.servo),seed=5,gate=own.gate,guard=own.guard)
    attach_driver(driver,own,Audit());driver.state='drive';driver.state_since=fixture.t
    driver.goal_yaw=0.
    localizer=SimpleNamespace(pulse_profiles=profiles,last_report=SimpleNamespace(t_est=fixture.t))
    heading.attach_driver(driver,localizer,pair_heading=heading.OPTION)
    rows=driver.tick(fixture.t)
    movement=[a for a in rows if heading.moving(a)]
    assert len(movement)==1 and profile_key(movement[0],False) in profiles
    assert sum(bool(movement[0].get(k)) for k in ('forward','left','turn'))==1
    assert movement[0]['left']==0 and est['std_xy_m']==.28


def test_actual_pair_submission_attaches_heading_before_any_control():
    from dataclasses import replace
    from harness.zone_s3_motion_runtime import Runtime
    from tests.test_solo_cyan_v106 import observation
    from harness.zone_s3_dev_light import OPTION as DEV
    config=contract.controller_config()
    config['options'].update(s3_dev_light=DEV,pair_heading=heading.OPTION)
    runtime=Runtime(contract.hp.resolve(contract.old.solo.MAP_ID)[0],contract.inputs()[2]['orders'],
        contract.ROOT/contract.old.solo.CALIBRATION,contract.old.solo.CALIBRATION_SHA,seed=14201,config=config)
    try:
        runtime.initial_commands(0.,{r:{1:2000,3:740,4:2320,5:1320,6:1500} for r in runtime.localizers})
        runtime.boot_finished_at=.1
        runtime.on_frames(.2,{r:observation(.2,1,rid=r) for r in runtime.localizers})
        pair=runtime.pair.producer
        for own in pair.actors.values():
            own.last_report=replace(own.last_report,x_m=-.9,y_m=-.85,yaw_rad=0.,std_xy_m=.28,std_yaw_rad=.01)
        for rid,partner in [('r1','r2'),('r2','r1')]:
            assert runtime.links[rid].submit(rid,'cargoX','B',partner,now=.2)['accepted']
        endpoints=pair.team.sessions[0]['endpoints']
        assert all(hasattr(ep.controller.driver,'s3_heading_audit') for ep in endpoints.values())
        assert pair.record()['pair_heading']['option']==heading.OPTION
    finally:
        runtime.close()
