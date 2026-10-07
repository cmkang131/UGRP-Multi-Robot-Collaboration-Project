import json
import numpy as np
import pytest
from scripts import diagnose_s2_load_wall as d
from test_s2_real_carry import make,static,cal,rt
from harness.zone_solo_cyan_real_carry import LOOK_AHEAD,LOOK_AHEAD_OPTION


def test_factorial_and_identical_recorded_excitation():
    assert len(set(d.cases()))==14
    for wall in ('far','near'):
        assert len([c for c in d.cases() if c[0]==wall])==7
    assert d.TIMES==(0.,.95,1.90,2.85,3.80,6.35)
    assert d.ACTION==dict(kind='mecanum',forward=0.,left=.65,turn=0.,duration_s=.65)
    for name in ('high','real_delivery','look_ahead'):
        assert {(c[0],c[2]) for c in d.cases() if c[1]==name}=={('far',False),('far',True),('near',False),('near',True)}


@pytest.mark.parametrize('names,expected',[
    (['r3__v3_wheel_fl_roller_0_body_contact','zone_wall_north'],'wall_wheel'),
    (['zone_wall_north','r3__left_finger'],'wall_finger'),
    (['cargo_box_00_geom','zone_wall_north'],'wall_cargo'),
    (['r3__chassis','zone_wall_north'],'wall_body'),
    (['floor','r3__wheel_fl'],'wheel_other'),
    (['r3__right_finger','cargo_box_00_geom'],'grasp'),
    (['r1__wheel_fl','floor'],None)])
def test_contact_attribution(names,expected):
    assert d.contact_class(names)==expected
    assert d.contact_class(list(reversed(names)))==expected


def test_look_ahead_only_lifts_wrist_and_keeps_grip(static,cal):
    assert LOOK_AHEAD=={1:1500,**rt.high.HIGH,3:1050}
    r=make(static,cal,carry_pose=LOOK_AHEAD_OPTION,setdown_relook='off',camera_profile=__import__('sim.masterpi_camera_review_v3',fromlist=['PROFILE_ID']).PROFILE_ID)
    try:
        r.initial_commands(0.,{'r3':{1:1500,**rt.high.HIGH}});r.last_report=r.pose.report(0.)
        r.state='lift';r.receipt=True;r.drive=lambda *a,**k:([{'kind':'hold'}],False)
        arms=[]
        for i in range(400):
            t=i*.05
            for rid,a in r.step(t):
                r.on_command(rid,t,a)
                if a['kind']=='arm':arms.append((a['servo_id'],a['pulse']))
            if r.state=='carry':break
        assert r.state=='carry' and r.servo[1]==1500 and r.servo[3]==1050
        assert (3,1050) in arms and (1,2000) not in arms
        assert r.record()['carry_pose']['option']==LOOK_AHEAD_OPTION
    finally:r.close()
