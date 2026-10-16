import pytest
from harness.e2e_pulse_admission import Admission,OPTION
from harness.self_pulse_odom import PulseOdometry


def motor():return dict(kind='mecanum',forward=.35,left=0.,turn=0.,duration_s=.1)


def test_actual_odometer_reproducer_waits_for_issued_pulse_without_interpolation():
    old=PulseOdometry();old.command(dict(t=0.,**motor()))
    with pytest.raises(ValueError,match='EARLY_INTERRUPTION'):old.command(dict(t=.05,kind='hold'))
    odom=PulseOdometry();admit=Admission(OPTION)
    for rid,a in admit.step(0.,[('r1',motor())]):odom.command(dict(t=0.,**a))
    assert admit.step(.05,[('r1',dict(kind='hold')),('r1',dict(kind='look',pan_pulse=1580))])==[]
    ready=admit.step(.1,[])
    assert [a['kind'] for _,a in ready]==['look','hold']
    for rid,a in ready:odom.command(dict(t=.1,**a))
    assert odom.servo[6]==1580 and admit.events[0]['until']==.1


def test_latest_per_channel_wins_and_independent_robot_keeps_running():
    a=Admission(OPTION);a.step(0.,[('r1',motor())])
    assert a.step(.05,[('r1',dict(kind='arm',servo_id=3,pulse=750)),('r2',motor())])==[('r2',motor())]
    assert a.step(.075,[('r1',dict(kind='arm',servo_id=3,pulse=760)),('r1',dict(kind='hold'))])==[]
    assert a.step(.1,[])==[('r1',dict(kind='arm',servo_id=3,pulse=760)),('r1',dict(kind='hold'))]
    rows=[('r1',motor()),('r1',dict(kind='hold'))];assert Admission().step(.05,rows) is rows
